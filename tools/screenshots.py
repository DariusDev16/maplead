"""
Regenerate the screenshots used in the README.

Needs a real display (an X11 / Wayland session) and, for the one with real
leads in it, an API key. Everything else runs on the built-in demo provider.

    python tools/screenshots.py [output-dir]

The user's own window state (~/.config/maplead/maplead-desktop.conf) is saved
and restored, so generating the docs never disturbs their session.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "screenshots")
SETTINGS = os.path.expanduser("~/.config/maplead/maplead-desktop.conf")

WIN_W, WIN_H = 1352, 726          # fits a 1366x768 panel


def _restore_state():
    """Keep the user's saved form/window state out of the screenshot run."""
    backup = None
    if os.path.exists(SETTINGS):
        backup = tempfile.mktemp(prefix="maplead-settings-")
        shutil.copy2(SETTINGS, backup)
    return backup


def _put_state(backup):
    if backup and os.path.exists(backup):
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        shutil.copy2(backup, SETTINGS)
        os.remove(backup)


def _mask_keys() -> None:
    """Replace real API keys in the environment with an obviously fake one.

    The window shows a masked key (``a765dc…41dc``); publishing even that much
    of someone's live key in a repo screenshot is not worth it.
    """
    from maplead.providers import PROVIDERS

    for name in PROVIDERS:
        cls = PROVIDERS[name]
        for var in cls.env_keys:
            if os.environ.get(var):
                os.environ[var] = "0demo0fake000key0not0real0xyz1"


def _hide_keys() -> None:
    from maplead.providers import PROVIDERS

    for name in PROVIDERS:
        for var in PROVIDERS[name].env_keys:
            os.environ.pop(var, None)


def main() -> int:
    if os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ.pop("QT_QPA_PLATFORM", None)     # real fonts, real screen
    os.makedirs(OUT, exist_ok=True)

    from PySide6.QtCore import QCoreApplication

    from maplead import paths
    from maplead.data import fields as FD
    from maplead.gui import app as gui_app
    from maplead.gui import theme as theme_mod
    from maplead.gui.keys import KeysDialog
    from maplead.gui.main_window import MainWindow
    from maplead.gui.widgets import FieldPickerDialog
    from maplead.gui.worker import HarvestWorker

    paths.load_env()
    backup = _restore_state()
    try:
        qapp, args = gui_app.create_app([])

        def shoot(widget, name: str, size=None, settle: float = 0.7) -> str:
            widget.show()
            if size:
                widget.resize(*size)
            QCoreApplication.processEvents()
            time.sleep(settle)
            QCoreApplication.processEvents()
            path = os.path.join(OUT, name)
            widget.grab().save(path)
            print("  ", path)
            return path

        # ---------------------------------------------------------- dark UI
        win = MainWindow(theme_mod.PALETTES["dark"])

        win.provider_combo.setValueByPredicate(lambda p: p == "serpapi")
        win.country_combo.setValueByPredicate(lambda c: c.iso == "pt")
        win.city_combo.setCurrentText("Cascais")
        win.business_combo.setCurrentText("Veterinary clinic")
        win.limit_spin.setValue(40)
        win.cb_phone.setChecked(True)
        QCoreApplication.processEvents()

        if win._problems():
            # no SerpApi key available -> show honest synthetic data instead
            print("  (no live provider key: shooting with demo data)")
            win.provider_combo.setValueByPredicate(lambda p: p == "demo")
            win.country_combo.setValueByPredicate(lambda c: c.iso == "de")
            win.city_combo.setCurrentText("Berlin")
            win.business_combo.setCurrentText("Veterinary clinic")
            QCoreApplication.processEvents()

        spec = win.spec()
        spec.outpath = os.path.join(tempfile.gettempdir(), "maplead-shot.csv")
        state: dict = {}
        worker = HarvestWorker(spec)
        worker.finished.connect(lambda r: state.update(result=r))
        worker.failed.connect(lambda m, h: state.update(error=f"{m} {h}"))
        worker.run()
        if "error" in state:
            print("  search failed:", state["error"], file=sys.stderr)
            return 1
        result = state["result"]
        win._on_finished(result)

        # a) no real key fragments, b) a realistic export path in the status bar
        _mask_keys()
        win._refresh_provider_status()
        win._on_provider_changed()
        win.status_right.setText("~/Documents/maplead/veterinary-clinic-cascais.csv")
        shoot(win, "app-dark.png", (WIN_W, WIN_H))

        # ------------------------------------------------------- light theme
        theme_mod.apply_theme(qapp, theme_mod.PALETTES["light"])
        light = MainWindow(theme_mod.PALETTES["light"])
        light._on_finished(result)
        light._refresh_provider_status()
        light._on_provider_changed()
        light.status_right.setText("~/Documents/maplead/veterinary-clinic-cascais.csv")
        shoot(light, "app-light.png", (WIN_W, WIN_H))
        theme_mod.apply_theme(qapp, theme_mod.PALETTES["dark"])

        # ------------------------------------------------------- dialogs ----
        picker = FieldPickerDialog("outscraper", list(FD.RECOMMENDED), win)
        shoot(picker, "fields.png", (720, 650))
        picker.close()

        keys = KeysDialog(theme_mod.PALETTES["dark"], win)
        shoot(keys, "api-keys.png", (740, 720))
        keys.close()

        # ------------------------------------------------- empty first run ---
        from PySide6.QtCore import QSettings
        QSettings("maplead", "maplead-desktop").clear()
        _hide_keys()          # what a brand-new machine really looks like
        fresh = MainWindow(theme_mod.PALETTES["dark"])
        shoot(fresh, "first-run.png", (WIN_W, WIN_H))
        fresh.close()
        win.close()
        light.close()
        return 0
    finally:
        _put_state(backup)


if __name__ == "__main__":
    sys.exit(main())