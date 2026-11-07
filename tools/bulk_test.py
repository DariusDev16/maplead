#!/usr/bin/env python3
"""
Try the bulk WhatsApp sender on your OWN numbers, without a search.

    .venv-gui/bin/python tools/bulk_test.py                  # asks for the numbers
    .venv-gui/bin/python tools/bulk_test.py +351912345678 +351934567890

Never test with demo leads: their numbers are made up and may belong to real
people. Each number becomes a fake lead ("Teste 1", "Teste 2"…) so the saved
message template is rendered exactly like it would be for a real lead. The
history is the real one, so the numbers show as "Contacted" afterwards; use
``--forget`` to remove them from the history again.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main(argv) -> int:
    forget = "--forget" in argv
    numbers = [a for a in argv if not a.startswith("--")]

    from maplead import outreach
    if forget:
        history = outreach.History()
        for number in numbers:
            print(number, "removed" if history.forget(number) else "not in history")
        return 0

    from maplead.gui import app as app_mod
    qapp, _ = app_mod.create_app([])
    from PySide6.QtWidgets import QInputDialog
    from maplead.gui import bulk_sender, theme

    if not numbers:
        text, ok = QInputDialog.getText(
            None, "Bulk WhatsApp test",
            "Your own test numbers, with country code, separated by spaces\n"
            "(e.g. +351912345678 +351934567890):")
        if not ok:
            return 0
        numbers = text.replace(",", " ").split()
    if not numbers:
        return 0

    leads = [{"name": f"Teste {i}", "phone": n, "city": "Sintra",
              "category": "Teste"} for i, n in enumerate(numbers, 1)]
    palette = theme.PALETTES[app_mod.preferred_theme()]
    window = bulk_sender.open_bulk_sender(leads, palette,
                                          filter_label="test numbers")
    if window is None:
        return 0
    window.finished.connect(qapp.quit)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
