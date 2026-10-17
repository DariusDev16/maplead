"""
Frozen entry point for the PyInstaller build (Linux AppImage and Windows exe).

Kept separate from the launchers so the frozen binary has one obvious main, and
so a windowed Windows build - which has no stdout at all - can still print its
self-test report to a file and pop a dialog with the verdict.
"""

import multiprocessing
import os
import sys
import tempfile


def _attach_a_console_or_a_file() -> None:
    """Windows/py2exe windowed builds have sys.stdout == None.

    Redirect it to a log file so `--selftest` (and anything that prints) still
    works, and tell the app that it has to report back through a message box.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    target = os.path.join(tempfile.gettempdir(), "maplead-selftest.log")
    handle = open(target, "w", encoding="utf-8", buffering=1)
    sys.stdout = handle
    sys.stderr = handle
    os.environ["MAPLEAD_WINDOWED"] = "1"
    os.environ["MAPLEAD_SELFTEST_LOG"] = target


def _entry() -> int:
    if getattr(sys, "frozen", False):
        multiprocessing.freeze_support()      # harmless, but keeps Qt threads happy
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    if "--selftest" in sys.argv:
        _attach_a_console_or_a_file()
    from maplead.gui.app import main
    return main()


if __name__ == "__main__":
    sys.exit(_entry())