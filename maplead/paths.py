"""
Where MAPLEAD keeps its configuration, API keys and exports.

XDG-aware so the GUI works from a read-only AppImage bundle:

    config  $XDG_CONFIG_HOME/maplead/.env      (keys, window geometry)
    data    $XDG_DATA_HOME/maplead/            (state, history)
    exports ~/Documents/maplead/               (lead files)

The CLI keeps preferring a legacy `.env` that sits next to the tool, so old
installs behave exactly as before; the GUI always uses the config dir.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

APP_ID = "maplead"
APP_TITLE = "MAPLEAD"
PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------- #
# directories
# --------------------------------------------------------------------------- #

def _base_dir(env_var: str, fallback: str) -> str:
    base = os.environ.get(env_var, "").strip()
    if base and os.path.isabs(base):
        return base
    return os.path.join(os.path.expanduser("~"), fallback)


def config_dir() -> str:
    return os.path.join(_base_dir("XDG_CONFIG_HOME", ".config"), APP_ID)


def data_dir() -> str:
    return os.path.join(_base_dir("XDG_DATA_HOME", ".local/share"), APP_ID)


def _user_dirs(key: str) -> Optional[str]:
    """Resolve an XDG user-dirs key ($HOME/Documents, ...) when published."""
    for candidate in (os.path.join(_base_dir("XDG_CONFIG_HOME", ".config"), "user-dirs.dirs"),):
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                for line in fh:
                    m = re.match(rf'\s*{key}\s*=\s*"(.*)"\s*$', line)
                    if m:
                        raw = m.group(1)
                        raw = raw.replace("$HOME", os.path.expanduser("~"))
                        return raw if os.path.isabs(raw) else None
        except OSError:
            continue
    return None


def documents_dir() -> str:
    return _user_dirs("XDG_DOCUMENTS_DIR") or os.path.join(os.path.expanduser("~"), "Documents")


def default_export_dir() -> str:
    return os.path.join(documents_dir(), APP_ID)


def ensure_dir(path: str) -> str:
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


# --------------------------------------------------------------------------- #
# env / key storage
# --------------------------------------------------------------------------- #

def user_env_file() -> str:
    return os.path.join(config_dir(), ".env")


def legacy_env_file() -> str:
    """The `.env` next to the source tree (CLI behaviour, kept for compat)."""
    return os.path.join(PACKAGE_DIR, ".env")


def env_file() -> str:
    """Where new keys get written: keep honouring an existing legacy `.env`."""
    legacy = legacy_env_file()
    if os.path.exists(legacy):
        return legacy
    return user_env_file()


def env_candidates() -> List[str]:
    """Every place a key may live, most specific first."""
    order = [env_file(), user_env_file(), legacy_env_file(),
             os.path.join(os.getcwd(), ".env")]
    seen, out = set(), []
    for path in order:
        real = os.path.abspath(path)
        if real not in seen:
            seen.add(real)
            out.append(path)
    return out


def load_env(path: Optional[str] = None) -> str:
    """Load KEY=VALUE pairs without clobbering the real environment.

    Returns the file that was used (or would be written for new keys).
    """
    used = env_file()
    for candidate in env_candidates():
        if not os.path.exists(candidate):
            continue
        used = candidate
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and not os.environ.get(key):
                        os.environ[key] = val
        except OSError:
            pass
        break
    return used


def read_env_file(path: Optional[str] = None) -> Dict[str, str]:
    """Parse a .env file without exporting anything to os.environ."""
    target = path or env_file()
    values: Dict[str, str] = {}
    try:
        with open(target, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip().strip("'\"")
    except OSError:
        pass
    return values


def save_env_key(key: str, value: str, path: Optional[str] = None) -> str:
    """Write KEY=VALUE into the env file, preserving comments and other keys."""
    target = path or env_file()
    lines: List[str] = []
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            lines = []
    replaced = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}" if value else f"{key}="
            replaced = True
            break
    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{key}={value}" if value else f"{key}=")
    parent = os.path.dirname(os.path.abspath(target))
    if parent:
        ensure_dir(parent)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip("\n") + "\n")
    try:
        os.chmod(target, 0o600)          # it holds secrets
    except OSError:
        pass
    os.environ[key] = value
    return target


def clear_env_key(key: str, path: Optional[str] = None) -> bool:
    target = path or env_file()
    if not os.path.exists(target):
        return False
    try:
        with open(target, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return False
    hit = False
    for i, line in enumerate(lines):
        if "=" in line and not line.strip().startswith("#") \
                and line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}="
            hit = True
    if hit:
        try:
            with open(target, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines).rstrip("\n") + "\n")
        except OSError:
            return False
    os.environ.pop(key, None)
    return hit


# --------------------------------------------------------------------------- #
# GUI state
# --------------------------------------------------------------------------- #

def state_file(name: str) -> str:
    return os.path.join(ensure_dir(data_dir()), name)