#!/usr/bin/env python3
"""MAPLEAD launcher - works from anywhere: ./maplead.py or python3 maplead.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maplead.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())