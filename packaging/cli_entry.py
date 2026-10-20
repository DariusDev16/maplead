"""
Frozen entry point for the MAPLEAD terminal wizard (`maplead.exe` on Windows).

Kept separate from `maplead.py` so the packaged console build has exactly one
main and so the GUI bundle stays free of the wizard's code path.
"""

import multiprocessing
import sys


def _entry() -> int:
    if getattr(sys, "frozen", False):
        multiprocessing.freeze_support()
    from maplead.cli import main
    return main()


if __name__ == "__main__":
    sys.exit(_entry())
