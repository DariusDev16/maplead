#!/usr/bin/env python3
"""
MAPLEAD Desktop launcher.

    ./maplead-gui.py               start the desktop app
    ./maplead-gui.py --selftest    headless check (no display needed)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maplead.gui.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())