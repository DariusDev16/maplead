"""
Platform glue: the small differences between Linux, macOS and Windows.

Nothing here knows about leads or Qt - it only answers questions the rest of the
package keeps asking:

* can this console show ANSI colours and Unicode box drawing?
* which folder does the desktop call "Documents"?
* how do I hand a file or URL to the default application?
* where is the sibling executable in a frozen Windows bundle?

Windows needs two things the other platforms get for free: the console has to be
switched into UTF-8 + virtual-terminal mode before escape codes or "╭─╮" mean
anything, and a windowed .exe has no ``sys.stdout`` at all.
"""

from __future__ import annotations

import os
import subprocess
import sys

WINDOWS = sys.platform.startswith("win")
MACOS = sys.platform == "darwin"
LINUX = not WINDOWS and not MACOS

# filled in by enable_console()
ANSI = True
UNICODE = True
_console_done = False
CONSOLE_INFO: dict[str, object] = {}

# Windows console mode flag: ENABLE_VIRTUAL_TERMINAL_PROCESSING
_ENABLE_VT = 0x0004
_STD_OUTPUT_HANDLE = -11
_STD_ERROR_HANDLE = -12


# --------------------------------------------------------------------------- #
# console
# --------------------------------------------------------------------------- #

def _stream(name: str):
    return getattr(sys, name, None)


def _utf8(name: str) -> None:
    """Re-encode one of the standard streams as UTF-8 (Windows defaults to cp1252)."""
    stream = _stream(name)
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        pass


def _windows_console() -> bool:
    """Switch the attached console to UTF-8 and VT sequences; True when colours work."""
    info = CONSOLE_INFO
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError as exc:               # pragma: no cover - Windows always has ctypes
        info["error"] = f"import ctypes: {exc}"
        return False

    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetStdHandle.restype = wintypes.HANDLE
        k32.GetStdHandle.argtypes = [wintypes.DWORD]
        k32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    except (AttributeError, OSError) as exc:  # pragma: no cover - very old Windows
        info["error"] = f"kernel32: {exc}"
        return False

    try:
        k32.SetConsoleOutputCP(65001)         # UTF-8
        k32.SetConsoleCP(65001)
    except (AttributeError, OSError):        # pragma: no cover
        pass

    enabled = False
    invalid = {0, None, wintypes.HANDLE(-1).value}
    for handle_id in (_STD_OUTPUT_HANDLE, _STD_ERROR_HANDLE):
        handle = k32.GetStdHandle(handle_id)
        if handle in invalid:
            info[f"handle{handle_id}"] = "redirected"
            continue                              # redirected: nothing to configure
        mode = wintypes.DWORD()
        got = bool(k32.GetConsoleMode(handle, ctypes.byref(mode)))
        if not got:
            info[f"handle{handle_id}"] = f"GetConsoleMode failed ({ctypes.get_last_error()})"
            continue
        set_ok = bool(k32.SetConsoleMode(handle, mode.value | _ENABLE_VT))
        info[f"handle{handle_id}"] = f"mode={mode.value:#x} vt={set_ok}"
        if set_ok:
            enabled = True
    return enabled


def enable_console() -> bool:
    """Prepare stdout/stderr once. Returns True when ANSI colour is safe."""
    global _console_done, ANSI, UNICODE
    if _console_done:
        return ANSI
    _console_done = True

    CONSOLE_INFO.update({
        "frozen": frozen(),
        "python": sys.version.split()[0],
        "stdout": type(_stream("stdout")).__name__,
        "isatty": stdout_is_tty(),
        "encoding": getattr(_stream("stdout"), "encoding", None),
    })

    if not WINDOWS:
        return ANSI

    _utf8("stdout")
    _utf8("stderr")
    _utf8("stdin")
    ANSI = _windows_console()

    encoding = (getattr(_stream("stdout"), "encoding", "") or "").lower()
    UNICODE = encoding.replace("-", "").startswith("utf")
    CONSOLE_INFO.update({"ansi": ANSI, "unicode": UNICODE})
    return ANSI


def diagnose() -> dict:
    """Everything `maplead --doctor` needs about the current host."""
    enable_console()
    return dict(WINDOWS=WINDOWS, MACOS=MACOS, frozen=frozen(),
                executable=sys.executable, console=dict(CONSOLE_INFO))


def console_unicode() -> bool:
    """True when box-drawing characters can be written without a UnicodeEncodeError."""
    enable_console()
    return UNICODE


def stdout_is_tty() -> bool:
    stream = _stream("stdout")
    if stream is None:
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


# --------------------------------------------------------------------------- #
# frozen bundles / launching siblings
# --------------------------------------------------------------------------- #

def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def executable_dir() -> str:
    """Folder of the .exe in a frozen build, the project root otherwise."""
    if frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sibling_gui() -> str | None:
    """Path to MAPLEAD.exe next to a frozen CLI build (Windows onedir layout)."""
    if not frozen():
        return None
    base = executable_dir()
    names = ("MAPLEAD.exe", "MAPLEAD", "maplead-gui.exe") if WINDOWS else ("MAPLEAD", "maplead-gui")
    for name in names:
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate):
            return candidate
    return None


def spawn(path: str, args: "list[str] | None" = None) -> bool:
    """Start another executable without waiting for it."""
    try:
        kwargs = {}
        if WINDOWS:
            # DETACHED_PROCESS: the GUI must outlive the console window it was started from
            kwargs["creationflags"] = 0x00000008
            kwargs["close_fds"] = True
        subprocess.Popen([path, *(args or [])], **kwargs)  # noqa: S603 - our own binary
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# desktop integration
# --------------------------------------------------------------------------- #

def open_path(target: str) -> bool:
    """Open a file, folder or URL with whatever the desktop registered for it."""
    if not target:
        return False
    try:
        if WINDOWS:
            os.startfile(target)              # type: ignore[attr-defined]
        elif MACOS:
            subprocess.Popen(["open", target],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", target],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def set_app_user_model_id(app_id: str) -> None:
    """Give the Windows taskbar our icon/name instead of python.exe's."""
    if not WINDOWS:
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:                          # pragma: no cover - best effort
        pass
