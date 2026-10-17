"""
Frozen entry point for the PyInstaller build.

Kept separate from maplead-gui.py so the frozen binary has one obvious main and
so `--windowed` mode still shows errors on stderr when MAPLEAD_DEBUG is set.
"""

import multiprocessing
import os
import sys


def _entry() -> int:
    if getattr(sys, "frozen", False):
        multiprocessing.freeze_support()      # harmless, but keeps Qt threads happy
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    from maplead.gui.app import main
    return main()


if __name__ == "__main__":
    sys.exit(_entry())