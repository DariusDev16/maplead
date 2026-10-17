"""
Frozen entry point for the PyInstaller build (Linux AppImage and Windows exe).

Kept separate from the launchers so the frozen binary has one obvious main, and
so a windowed Windows build - which has no usable stdout - can still print its
self-test report and pop a dialog with the verdict.
"""

import multiprocessing
import os
import sys
import tempfile


def _reconfigure(stream) -> bool:
    """Force UTF-8 with a lenient fallback so a stray '→' cannot kill a run.

    A windowed build launched from a console inherits a cp1252 stream on
    Windows, where '→' or '★' raise UnicodeEncodeError.
    """
    if stream is None:
        return False
    try:
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        return True
    except (AttributeError, ValueError, OSError):
        return False


def prepare_streams() -> None:
    """Guarantee that print() works, or fall back to a log file."""
    stdout_ok = _reconfigure(sys.stdout)
    stderr_ok = _reconfigure(sys.stderr)

    if stdout_ok and stderr_ok:
        return

    target = os.path.join(tempfile.gettempdir(), "maplead-selftest.log")
    try:
        handle = open(target, "w", encoding="utf-8", errors="backslashreplace",
                      buffering=1)
    except OSError:
        return
    sys.stdout = handle
    sys.stderr = handle
    os.environ["MAPLEAD_WINDOWED"] = "1"
    os.environ["MAPLEAD_SELFTEST_LOG"] = target


def _entry() -> int:
    if getattr(sys, "frozen", False):
        multiprocessing.freeze_support()      # harmless, but keeps Qt threads happy
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    if "--selftest" in sys.argv:
        prepare_streams()
    from maplead.gui.app import main
    return main()


if __name__ == "__main__":
    sys.exit(_entry())