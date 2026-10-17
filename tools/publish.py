"""
Publish the repository to GitHub over the REST API.

Useful when this machine has no system-wide git and no FUSE-free SSH client —
which is exactly the case on a locked-down desktop: all this needs is `curl`
and a Personal Access Token.

    # one-off
    python tools/publish.py --token ghp_xxx --repo maplead

    # safer: keep the token out of the shell history
    read -rs TOKEN && printf '%s' "$TOKEN" > ~/.maplead-github-token && chmod 600 ~/.maplead-github-token
    python tools/publish.py --repo maplead          # reads the file above
    rm -f ~/.maplead-github-token

What it does: creates the repository (if missing), uploads every tracked file
through the git-data API (blobs for binaries, inline content for text), then
creates the commit and points ``main`` at it. Re-running is safe: it detects an
existing repository and only updates the branch when the tree differs.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = os.path.expanduser("~/.maplead-github-token")
API = "https://api.github.com"
DESCRIPTION = (
    "Interactive Google Maps lead extractor. Desktop app for Linux (single-file AppImage, Qt6) + a zero-dependency terminal wizard, both on the same engine: 4 lead APIs, 65 countries, 68 business verticals, 35 fields, 6 export formats."
)

TOPICS = ["leads", "google-maps", "scraper", "qt6", "appimage", "linux",
          "business-directory", "outscraper", "serpapi", "python"]


# --------------------------------------------------------------------------- #
# plumbing
# --------------------------------------------------------------------------- #

def get_token(arg: str | None) -> str:
    """--token, then GITHUB_TOKEN, then ~/.maplead-github-token, then `gh auth`."""
    token = arg or os.environ.get("GITHUB_TOKEN", "").strip()
    if not token and os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, encoding="utf-8") as fh:
            token = fh.read().strip()
    if not token:
        try:                                   # reuse an existing `gh auth login`
            token = subprocess.run(["gh", "auth", "token"],
                                   capture_output=True, text=True,
                                   check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            token = ""
    if not token:
        sys.exit("no token: pass --token, set GITHUB_TOKEN, write " + TOKEN_FILE
                 + ", or run `gh auth login`")
    return token


def call(method: str, url: str, token: str, payload=None, accept="application/vnd.github+json"):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "maplead-publish",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail).get("message", detail)
        except ValueError:
            pass
        raise SystemExit(f"{method} {url} -> HTTP {exc.code}: {detail}") from None


def tracked_files() -> list[tuple[str, str]]:
    """(relative path, absolute path) for everything git would commit."""
    try:
        out = subprocess.run(["git", "-C", ROOT, "ls-files", "-z"],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        sys.exit("git not available, or this is not a repository yet")
    return [(rel, os.path.join(ROOT, rel)) for rel in out.split("\0") if rel]


# --------------------------------------------------------------------------- #
# steps
# --------------------------------------------------------------------------- #

def ensure_repo(token: str, repo: str, private: bool) -> dict:
    """Create the repository; tolerate 'already exists'."""
    try:
        return call("POST", f"{API}/user/repos", token, {
            "name": repo,
            "description": DESCRIPTION,
            "private": private,
            "auto_init": False,
            "has_wiki": False,
            "has_issues": True,
            "topics": TOPICS,
        })
    except SystemExit as exc:
        text = str(exc)
        if "HTTP 422" not in text and "already exists" not in text:
            raise                      # 422 on create == the name is taken
        print("  repository already exists, continuing")
        return call("GET", f"{API}/repos/{login(token)}/{repo}", token)


def login(token: str) -> str:
    return call("GET", f"{API}/user", token)["login"]


def upload_tree(token: str, owner: str, repo: str, files) -> str:
    """One tree request; binaries go up as separate base64 blobs."""
    entries, blobs = [], {}
    for rel, path in files:
        raw = open(path, "rb").read()
        guessed = mimetypes.guess_type(rel)[0] or ""
        if raw[:8] == b"\x89PNG\r\n\x1a\n" or guessed.startswith("image/"):
            blobs[rel] = base64.b64encode(raw).decode()
        else:
            try:
                entries.append({"path": rel, "mode": "100644", "type": "blob",
                                "content": raw.decode("utf-8")})
            except UnicodeDecodeError:
                blobs[rel] = base64.b64encode(raw).decode()

    for rel, b64 in blobs.items():
        sha = call("POST", f"{API}/repos/{owner}/{repo}/git/blobs", token,
                   {"content": b64, "encoding": "base64"})["sha"]
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": sha})
        print(f"    blob {rel}")

    tree = call("POST", f"{API}/repos/{owner}/{repo}/git/trees", token,
                {"tree": entries})
    if tree.get("truncated"):
        sys.exit("tree came back truncated - too many files for one request")
    print(f"  tree: {len(entries)} entries")
    return tree["sha"]


def seed_if_empty(token: str, owner: str, repo: str) -> None:
    """The git-data API refuses blobs on a repository with no commits.

    Creating one placeholder commit through the contents API unblocks it.
    """
    try:
        call("GET", f"{API}/repos/{owner}/{repo}/git/ref/heads/main", token)
        return                                   # main already exists
    except SystemExit:
        pass
    print("  seeding empty repository…")
    call("PUT", f"{API}/repos/{owner}/{repo}/contents/.gitkeep", token, {
        "message": "init",
        "content": base64.b64encode(b"").decode(),
        "branch": "main",
    })


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="repository name, e.g. maplead")
    ap.add_argument("--token", help="PAT with the 'repo' scope")
    ap.add_argument("--private", action="store_true", help="create it private")
    ap.add_argument("--message", default=None, help="commit message")
    args = ap.parse_args()

    token = get_token(args.token)
    user = login(token)
    owner, repo = user, args.repo
    print(f"  authenticated as {user}")

    print("  repository:")
    info = ensure_repo(token, repo, args.private)
    owner = info.get("owner", {}).get("login", owner)

    files = tracked_files()
    seed_if_empty(token, owner, repo)
    print(f"  uploading {len(files)} tracked files")
    tree_sha = upload_tree(token, owner, repo, files)

    message = args.message
    if not message:
        try:
            message = subprocess.run(
                ["git", "-C", ROOT, "log", "-1", "--pretty=%s"],
                capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            message = "MAPLEAD"

    parent = None
    ref = f"{API}/repos/{owner}/{repo}/git/ref/heads/main"
    try:
        parent = call("GET", ref, token)["object"]["sha"]
    except SystemExit:
        pass                                   # empty repository

    commit = call("POST", f"{API}/repos/{owner}/{repo}/git/commits", token, {
        "message": message,
        "tree": tree_sha,
        **({"parents": [parent]} if parent else {}),
    })["sha"]

    if parent:
        call("PATCH", ref, token, {"sha": commit, "force": True})
    else:
        call("POST", f"{API}/repos/{owner}/{repo}/git/refs", token,
             {"ref": "refs/heads/main", "sha": commit})

    url = f"https://github.com/{owner}/{repo}"
    print(f"\n  published: {url}")
    print(f"  commit:    {commit[:10]}  {message}")
    print(f"\n  next:  git -C {ROOT} remote add origin {url}.git")
    print("        git -C %s fetch origin && git -C %s reset --soft origin/main" % (ROOT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())