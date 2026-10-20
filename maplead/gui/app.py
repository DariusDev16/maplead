"""
MAPLEAD Desktop - application entry point.

    MAPLEAD [--args]            normal launch (MAPLEAD.exe on Windows)
    MAPLEAD --cli [args]        run the terminal wizard instead of the window
    MAPLEAD --doctor            host diagnostics (wizard flag, routed to --cli)
    MAPLEAD --selftest          headless smoke test (builds the UI, runs a demo search)

One binary, two interfaces: the same file is the desktop app and the terminal
wizard. `--cli` (or any flag only the wizard knows, such as `--demo` or
`--doctor`) runs the wizard, everything else opens the window. That is what the
AppImage has always done, and now the Windows .exe too.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from typing import List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .. import host, paths
from ..art import VERSION
from ..providers import PROVIDERS
from . import theme as theme_mod

DESKTOP_ID = "io.github.maplead.Desktop"


# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="maplead-gui",
        description=f"MAPLEAD {VERSION} desktop - interactive Google Maps lead extractor",
        epilog="--cli sends everything after it to the terminal wizard, "
               "e.g.  MAPLEAD --cli --demo",
    )
    p.add_argument("--provider", choices=list(PROVIDERS), help="pre-select a provider")
    p.add_argument("--country", help="pre-select a country (name or ISO code)")
    p.add_argument("--city", help="pre-select a city")
    p.add_argument("--business", help="pre-select a business type")
    p.add_argument("--theme", choices=("dark", "light"), help="force a theme")
    p.add_argument("--selftest", action="store_true",
                   help="headless check: build the window, run a demo search, exit")
    p.add_argument("--version", action="version", version=f"MAPLEAD {VERSION}")
    return p


# --------------------------------------------------------------------------- #
# boot
# --------------------------------------------------------------------------- #

def _argv(argv: Optional[Sequence[str]]) -> List[str]:
    return list(sys.argv[1:] if argv is None else argv)


def _run_cli(args: List[str]) -> int:
    """`--cli` runs the terminal wizard: one binary, two interfaces.

    Everything after the flag is handed to the wizard untouched. Any flag the
    window does not recognise (``--demo``, ``--doctor``, ``-k`` …) lands here
    too, so `MAPLEAD --demo` works without spelling out `--cli`.
    """
    from ..cli import main as cli_main
    return cli_main([a for a in args if a != "--cli"])


def _gui_flags() -> set:
    """Every option string the window's own parser understands."""
    flags = {"-h", "--help", "--gui"}
    for action in build_parser()._actions:
        flags.update(action.option_strings)
    return flags


def _wants_wizard(args: List[str]) -> bool:
    """True when the arguments can only be meant for the terminal wizard.

    The window takes a few flags of its own (``--country``, ``--city`` …) to
    pre-fill the form, so "has arguments" is not enough - anything the window
    does not know how to parse belongs to the wizard.
    """
    if "--cli" in args:
        return True
    known = _gui_flags()
    for arg in args:
        if arg.startswith("-") and arg.split("=", 1)[0] not in known:
            return True
    return False


def _prepare_selftest_streams(argv: Optional[Sequence[str]]) -> None:
    """Give `--selftest` a log file, so the frozen run leaves a trace behind."""
    if not host.frozen() and sys.stdout is not None:
        return
    if "--selftest" not in _argv(argv):
        return
    path = os.path.join(tempfile.gettempdir(), "maplead-selftest.log")
    try:
        stream = open(path, "w", encoding="utf-8", buffering=1)
    except OSError:
        return
    sys.stdout = stream
    sys.stderr = stream
    import faulthandler
    faulthandler.enable(stream)
    print(f"MAPLEAD {VERSION} - frozen self-test, log: {path}")


def _write_crash_log() -> None:
    """Windowed builds have nowhere to print a traceback: keep one on disk."""
    import datetime
    import traceback

    text = (f"\n=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} MAPLEAD {VERSION} ===\n"
            f"{traceback.format_exc()}")
    targets = [os.path.join(tempfile.gettempdir(), "maplead-crash.log")]
    try:
        targets.append(os.path.join(paths.ensure_dir(paths.data_dir()), "crash.log"))
    except Exception:
        pass
    for path in targets:
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(text)
            break
        except OSError:
            continue


def preferred_theme() -> str:
    """Dark by default, light when the desktop asks for it."""
    if os.environ.get("MAPLEAD_LIGHT", "") not in ("", "0", "false", "no"):
        return "light"
    if os.environ.get("MAPLEAD_DARK", "") not in ("", "0", "false", "no"):
        return "dark"
    try:
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.styleHints().colorScheme() == Qt.Light:
            return "light"
    except Exception:
        pass
    return "dark"


def create_app(argv: Optional[Sequence[str]] = None):
    """Boot QApplication and paint the first palette."""
    args = build_parser().parse_args(argv)

    app = QApplication.instance() or QApplication(list(sys.argv[:1]))
    app.setApplicationName("MAPLEAD")
    app.setApplicationDisplayName("MAPLEAD")
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("maplead")
    app.setOrganizationDomain("maplead.local")
    app.setDesktopFileName(DESKTOP_ID)
    app.setQuitOnLastWindowClosed(True)

    # Windows: own the taskbar entry (icon + name) instead of the launcher's
    host.set_app_user_model_id(DESKTOP_ID)

    from PySide6.QtGui import QIcon
    from . import icons
    app.setWindowIcon(QIcon(icons.pixmap("pin", theme_mod.DARK.accent, 64)))

    theme_mod.apply_theme(app, theme_mod.PALETTES[args.theme or preferred_theme()])
    return app, args


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main(argv: Optional[Sequence[str]] = None) -> int:
    args = [a for a in _argv(argv) if a != "--gui"]
    if _wants_wizard(args):
        return _run_cli(args)
    host.quiet_console()                     # double-clicked .exe: hide the console
    _prepare_selftest_streams(args)
    try:
        return _main(args)
    except SystemExit:
        raise
    except BaseException:
        _write_crash_log()
        raise


def _main(argv: Optional[Sequence[str]] = None) -> int:
    paths.load_env()
    app, args = create_app(argv)

    from .main_window import MainWindow

    windows: List = []
    theme_name = args.theme or preferred_theme()
    window = MainWindow(theme_mod.PALETTES[theme_name])

    def swap(name: str) -> None:
        """Rebuild the window under a new palette (icons are palette-bound)."""
        geometry = window.saveGeometry()
        window._save_state()                 # so the new window comes back filled in
        theme_mod.apply_theme(app, theme_mod.PALETTES[name])
        fresh = MainWindow(theme_mod.PALETTES[name])
        fresh.restoreGeometry(geometry)
        fresh.theme_changed.connect(swap)
        fresh.show()
        windows.append(fresh)
        window.setAttribute(Qt.WA_DeleteOnClose, True)
        window.close()

    window.theme_changed.connect(swap)
    window.show()
    windows.append(window)

    _apply_cli_prefill(window, args)

    if args.selftest:
        return selftest(window)
    return app.exec()


def _apply_cli_prefill(window, args) -> None:
    """Honour the few flags a shell/desktop launcher may pass."""
    if args.provider:
        window.provider_combo.setValueByPredicate(lambda p: p == args.provider)
    if args.country:
        from ..data import countries as CO
        hits = CO.find(args.country)
        if hits:
            window.country_combo.setValueByPredicate(lambda c: c is hits[0])
    if args.city:
        window.city_combo.setCurrentText(args.city)
    if args.business:
        window.business_combo.setCurrentText(args.business)


# --------------------------------------------------------------------------- #
# headless self test  (used by the build script and by CI)
# --------------------------------------------------------------------------- #

def selftest(window) -> int:
    """Build-check the window, then run one offline search end to end."""
    import tempfile

    from .worker import HarvestWorker

    print(f"[selftest] window: {window.windowTitle()}")
    print(f"[selftest] keys file   : {paths.user_env_file()}")
    print(f"[selftest] export dir  : {paths.default_export_dir()}")
    print(f"[selftest] theme       : {window.p.name}")
    print(f"[selftest] providers   : {', '.join(PROVIDERS)}")

    # -- fill the form like a user would -------------------------------- #
    window.provider_combo.setValueByPredicate(lambda p: p == "demo")
    window.country_combo.setValueByPredicate(lambda c: c.iso == "de")
    window.region_combo.setCurrentText("Berlin")
    window.city_combo.setCurrentText("Berlin")
    window.business_combo.setCurrentText("Plumber")
    window.limit_spin.setValue(25)
    window.cb_phone.setChecked(True)
    idx = window.format_combo.findData("xlsx")
    if idx >= 0:
        window.format_combo.setCurrentIndex(idx)

    problems = window._problems()
    if problems:
        print("[selftest] FAILED - form validation: " + "; ".join(problems))
        return 1
    print(f"[selftest] plan       : {window.plan_label.text()}")

    spec = window.spec()
    spec.outpath = os.path.join(tempfile.mkdtemp(prefix="maplead-selftest-"),
                               "selftest-leads.xlsx")

    state = {"result": None, "error": None}
    worker = HarvestWorker(spec)
    worker.log.connect(lambda msg, level: print(f"[selftest]   {level:>5} | {msg}"))
    worker.finished.connect(lambda result: state.update(result=result))
    worker.failed.connect(lambda msg, hint: state.update(error=f"{msg} {hint}".strip()))

    worker.run()                     # synchronous: direct connections fire inline

    if state["error"]:
        print(f"[selftest] FAILED: {state['error']}")
        return 1
    result = state["result"]
    if result is None:
        print("[selftest] FAILED: the worker produced no result")
        return 1

    # -- the window must show exactly what the worker produced ---------- #
    window._on_finished(result)
    print(f"[selftest] leads      : {len(result.leads)}")
    print(f"[selftest] table rows : {window.model.rowCount()} x {window.model.columnCount()}")
    print(f"[selftest] exported   : {result.exported} -> {result.outpath}")
    print(f"[selftest] queries    : {len(result.report.queries_run)} "
          f"in {result.report.elapsed:.2f}s")
    print(f"[selftest] stats      : {result.stats['total']} leads, "
          f"{result.stats['with_phone']} phones, "
          f"{result.stats['with_website']} sites")

    ok = (len(result.leads) > 0
          and result.exported
          and os.path.exists(result.outpath)
          and window.model.rowCount() == len(result.leads))
    if not ok:
        print("[selftest] FAILED: inconsistent results")
        return 1

    return 0 if _selftest_widgets(window) else 1


def _selftest_widgets(window) -> bool:
    """Exercise the dialogs and list widgets headlessly."""
    from ..data import fields as FD
    from .keys import KeysDialog
    from .widgets import FieldPickerDialog, SearchCombo

    ok = True

    # --- searchable combo (country picker) -------------------------------- #
    combo: SearchCombo = window.country_combo
    before = combo.currentIndex()
    combo._buffer = "braz"
    combo._apply()
    filtered_label = combo.currentText()
    combo._buffer = ""
    combo._fill(combo.entries())
    combo.setCurrentIndex(before)
    print(f"[selftest] combo filter 'braz' -> {filtered_label!r}")
    ok &= "razil" in filtered_label

    # --- field picker: presets, filters, provider gating ------------------- #
    picker = FieldPickerDialog("google", list(FD.RECOMMENDED), window)
    rec = picker.selected()
    picker._preset("all")
    everything = picker.selected()
    picker._preset("none")
    picker._filter("mail")
    matching = [k for k, b in picker._boxes.items() if not b.isHidden()]
    picker._filter("")
    gated = [k for k, b in picker._boxes.items() if not b.isEnabled()]
    print(f"[selftest] field picker: rec={len(rec)} all={len(everything)} "
          f"none=0 'mail' matches={matching} gated-for-google={len(gated)}")
    ok &= len(rec) > 0 and len(everything) >= len(rec) and len(matching) >= 1
    ok &= "email" in gated          # google cannot return e-mail: must be locked
    picker.deleteLater()

    # --- keys dialog builds and reports ------------------------------------ #
    keys = KeysDialog(window.p, window)
    rows = len(keys.rows)
    keys.rows["outscraper"].verify_result(True, "selftest ok")
    keys.rows["google"].verify_result(False, "selftest failure")
    print(f"[selftest] keys dialog: {rows} providers, file {keys.env_path}")
    ok &= rows >= 5 and "ok" in keys.rows["outscraper"].message.text()
    keys.deleteLater()

    print("[selftest] OK" if ok else "[selftest] FAILED: widget checks")
    return bool(ok)


def run() -> None:
    sys.exit(main())


if __name__ == "__main__":
    run()