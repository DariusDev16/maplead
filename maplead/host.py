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
# frozen bundles / the shared console
# --------------------------------------------------------------------------- #

def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def executable_dir() -> str:
    """Folder of the .exe in a frozen build, the project root otherwise."""
    if frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _process_tree() -> tuple:
    """(pid -> parent pid, pid -> exe name) for every process we can see."""
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260),
            ]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        snapshot = k32.CreateToolhelp32Snapshot(0x00000002, 0)   # TH32CS_SNAPPROCESS
        if snapshot in (0, None, wintypes.HANDLE(-1).value):
            return {}, {}
        try:
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
            parents, names = {}, {}
            ok = k32.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                parents[entry.th32ProcessID] = entry.th32ParentProcessID
                names[entry.th32ProcessID] = (entry.szExeFile or "").lower()
                ok = k32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            k32.CloseHandle(snapshot)
        return parents, names
    except Exception:                          # pragma: no cover - best effort
        return {}, {}


def _ancestor_names(limit: int = 6) -> "list[str]":
    """Exe names of our ancestors, nearest first (empty list when unsure)."""
    parents, names = _process_tree()
    if not parents:
        return []
    found = []
    pid = parents.get(os.getpid(), 0)
    while pid and len(found) < limit:
        found.append(names.get(pid, ""))
        pid = parents.get(pid, 0)
    return found


def quiet_console() -> None:
    """Hide the console window when the desktop (not a shell) started us.

    MAPLEAD.exe is a console-subsystem binary so that `MAPLEAD --cli` behaves
    like a real terminal program (cmd waits for it, the wizard owns stdin).
    The price is a console window when the same .exe is double-clicked, so the
    GUI path hides it again - but never when a shell owns it.

    A onefile build has a bootloader between us and whoever launched us
    (explorer.exe -> MAPLEAD.exe -> us), so the self-named ancestors are
    skipped before deciding.
    """
    if not WINDOWS or not frozen():
        return
    own = os.path.basename(sys.executable).lower()
    owner = ""
    for name in _ancestor_names():
        if name == own:                        # the onefile bootloader
            continue
        owner = name
        break
    if owner not in ("", "explorer.exe"):
        return
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        k32.GetConsoleWindow.restype = wintypes.HWND
        window = k32.GetConsoleWindow()
        if window:
            user32.ShowWindow(window, 0)       # SW_HIDE
    except Exception:                          # pragma: no cover - best effort
        pass


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
