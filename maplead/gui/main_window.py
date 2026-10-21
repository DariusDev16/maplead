"""
MAPLEAD Desktop - main window.

Left: the 9 wizard answers as a form.  Right: live stats, the leads table and
the activity log.  Everything the terminal wizard asks is on this one screen.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSettings, QSize, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QScrollArea, QSizePolicy,
                               QSpinBox, QSplitter, QToolButton, QVBoxLayout,
                               QWidget)

from .. import exporters, paths
from ..art import VERSION
from ..data import cities as CI
from ..data import countries as CO
from ..data import fields as FD
from ..data import verticals as VT
from ..providers import ORDER, PROVIDERS
from . import icons
from .keys import KeysDialog
from .theme import Palette
from .widgets import (FieldPickerDialog, LeadsFilter, LeadsModel, LogPane,
                      SearchCombo, StatCard, build_table, card, editable_combo,
                      field_label, open_in_desktop)
from .widgets import supports as _supports
from .worker import HarvestWorker, RunResult, SearchSpec

FORMAT_HINTS = {
    "csv": "Universal · Excel, Sheets, CRM import",
    "xlsx": "Formatted workbook + meta sheet",
    "json": "Full fidelity, keeps types",
    "txt": "Human readable list",
    "tsv": "Tab separated, pastes into Sheets",
    "html": "Styled report",
}


class MainWindow(QMainWindow):

    theme_changed = Signal(str)

    def __init__(self, palette: Palette):
        super().__init__()
        self.p = palette
        self.theme_name = palette.name
        self.setWindowTitle(f"MAPLEAD {VERSION} — Google Maps lead extractor")
        self.setMinimumSize(QSize(1080, 700))
        self.resize(1280, 820)

        self.model = LeadsModel(list(FD.RECOMMENDED), self)
        self.proxy = LeadsFilter(self)
        self.proxy.setSourceModel(self.model)

        self._thread: Optional[QThread] = None
        self._worker: Optional[HarvestWorker] = None
        self._fields: List[str] = [f for f in FD.RECOMMENDED]
        self._last_outpath: str = ""
        self._manual_path = False

        self._build()
        self._restore_state()
        self._refresh_provider_status()
        QTimer.singleShot(0, self._apply_provider_defaults)

    # ------------------------------------------------------------------ UI --
    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_topbar())

        split = QSplitter(Qt.Horizontal)  # noqa: E501 - form on the left, data on the right
        split.setChildrenCollapsible(False)
        split.setHandleWidth(10)
        split.addWidget(self._build_left())
        split.addWidget(self._build_right())
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([392, 880])
        outer.addWidget(split, 1)

        # status bar
        bar = self.statusBar()
        self.status_left = QLabel("")
        self.status_right = QLabel("")
        bar.addWidget(self.status_left, 1)
        bar.addPermanentWidget(self.status_right)

        self._build_menu()

    # -- top bar -------------------------------------------------------------
    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(64)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 8, 14, 8)
        lay.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(icons.pixmap("pin", self.p.accent, 26))
        logo.setFixedSize(30, 30)
        lay.addWidget(logo)

        brand = QVBoxLayout()
        brand.setSpacing(0)
        name = QLabel("MAPLEAD")
        name.setObjectName("brand")
        tag = QLabel("Google Maps lead extractor")
        tag.setObjectName("hint")
        brand.addWidget(name)
        brand.addWidget(tag)
        lay.addLayout(brand)
        lay.addSpacing(10)

        self.provider_badge = QLabel("")
        self.provider_badge.setObjectName("badge")
        lay.addWidget(self.provider_badge)
        lay.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setFixedWidth(210)
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        keys_btn = QPushButton("  API keys")
        keys_btn.setIcon(icons.icon("key", self.p.text_dim, 15))
        keys_btn.clicked.connect(self.open_keys)
        lay.addWidget(keys_btn)

        theme_btn = QToolButton()
        theme_btn.setIcon(icons.icon("sun" if self.p.is_dark else "moon",
                                    self.p.text_dim, 17))
        theme_btn.setToolTip("Switch between dark and light")
        theme_btn.clicked.connect(self.toggle_theme)
        lay.addWidget(theme_btn)
        return bar

    # -- left: the wizard form ---------------------------------------------
    def _build_left(self) -> QWidget:
        """Form in a scroll area + a pinned run bar underneath."""
        container = QWidget()
        container.setMinimumWidth(376)
        container.setMaximumWidth(474)
        lay = QVBoxLayout(container)
        lay.setContentsMargins(14, 14, 10, 12)
        lay.setSpacing(10)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        panel = self._build_left_panel()
        panel.setMinimumWidth(348)
        area.setWidget(panel)
        lay.addWidget(area, 1)
        lay.addWidget(self._build_runbar())
        return container

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(460)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(14, 14, 8, 14)
        outer.setSpacing(12)

        # ---- 1 provider -------------------------------------------------- #
        provider_card, pl = card("1 · data provider")
        row = QHBoxLayout()
        self.provider_combo = SearchCombo()
        self.provider_combo.setEntries(
            [(f"{PROVIDERS[n].label}", n) for n in ORDER] + [("Demo (offline sample)", "demo")])
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        row.addWidget(self.provider_combo, 1)
        manage = QPushButton()
        manage.setIcon(icons.icon("sliders", self.p.text_dim, 15))
        manage.setToolTip("Manage API keys")
        manage.clicked.connect(self.open_keys)
        row.addWidget(manage)
        pl.addLayout(row)
        self.provider_note = QLabel("")
        self.provider_note.setObjectName("hint")
        self.provider_note.setWordWrap(True)
        pl.addWidget(self.provider_note)
        outer.addWidget(provider_card)

        # ---- 2-4 location ------------------------------------------------- #
        loc_card, ll = card("2-4 · where")
        self.country_combo = SearchCombo()
        self.country_combo.setEntries([(f"{c.name}  ({c.dial})", c) for c in CO.COUNTRIES])
        self.country_combo.currentIndexChanged.connect(self._on_country_changed)
        ll.addWidget(field_label("Country"))
        ll.addWidget(self.country_combo)

        self.region_combo = editable_combo()
        self.region_combo.lineEdit().setPlaceholderText("region / state (optional)")
        self.region_combo.currentTextChanged.connect(lambda _=None: self._refresh_city_list())
        self.region_combo.lineEdit().setToolTip(
            "Leave empty to search the whole country")
        ll.addWidget(field_label("Region / state"))
        ll.addWidget(self.region_combo)

        self.city_combo = editable_combo()
        self.city_combo.lineEdit().setPlaceholderText("city")
        ll.addWidget(field_label("City"))
        ll.addWidget(self.city_combo)
        outer.addWidget(loc_card)

        # ---- 5 business ---------------------------------------------------- #
        biz_card, bl = card("5 · what business")
        self.business_combo = editable_combo([v.label for v in VT.VERTICALS])
        self.business_combo.setEditable(True)
        self.business_combo.currentTextChanged.connect(self._on_business_changed)
        self.business_combo.lineEdit().setPlaceholderText("type anything, e.g. solar installer")
        bl.addWidget(self.business_combo)
        self.business_note = QLabel("")
        self.business_note.setObjectName("hint")
        self.business_note.setWordWrap(True)
        bl.addWidget(self.business_note)
        outer.addWidget(biz_card)

        # ---- 6 fields ------------------------------------------------------ #
        fields_card, fl = card("6 · fields")
        row = QHBoxLayout()
        self.fields_btn = QPushButton("Choose fields…")
        self.fields_btn.setIcon(icons.icon("list", self.p.text_dim, 15))
        self.fields_btn.clicked.connect(self.choose_fields)
        row.addWidget(self.fields_btn, 1)
        self.fields_count = QLabel("")
        self.fields_count.setObjectName("badge")
        row.addWidget(self.fields_count)
        fl.addLayout(row)
        self.fields_note = QLabel("")
        self.fields_note.setObjectName("hint")
        self.fields_note.setWordWrap(True)
        fl.addWidget(self.fields_note)
        outer.addWidget(fields_card)

        # ---- 7 volume + filters --------------------------------------------- #
        vol_card, vl = card("7 · how many + filters")
        row = QHBoxLayout()
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 100_000)
        self.limit_spin.setValue(60)
        self.limit_spin.setSingleStep(10)
        self.limit_spin.setSuffix(" leads")
        row.addWidget(self.limit_spin, 1)
        self.limit_spin.setToolTip("Target number of leads to collect")
        vl.addLayout(row)

        grid = QGridLayout()
        grid.setSpacing(6)
        self.min_rating = QDoubleSpinBox()
        self.min_rating.setRange(0.0, 5.0)
        self.min_rating.setSingleStep(0.1)
        self.min_rating.setSpecialValueText("no filter")
        self.min_reviews = QSpinBox()
        self.min_reviews.setRange(0, 100_000)
        self.min_reviews.setSpecialValueText("no filter")
        grid.addWidget(field_label("Min rating"), 0, 0)
        grid.addWidget(self.min_rating, 1, 0)
        grid.addWidget(field_label("Min reviews"), 0, 1)
        grid.addWidget(self.min_reviews, 1, 1)
        vl.addLayout(grid)

        self.cb_phone = QCheckBox("Only leads with a phone")
        self.cb_landline = QCheckBox("Skip landline phones")
        self.cb_landline.setToolTip(
            "Drops numbers that look like landlines (Brazil, Portugal, Spain, UK,\n"
            "Germany, France, Italy, Netherlands, Ireland, Australia, Colombia,\n"
            "Peru, Chile). Numbers from countries where mobile and landline share\n"
            "the same format (US, Canada…) cannot be told apart and are kept.")
        self.cb_landline.toggled.connect(self._on_landline_toggled)
        self.cb_site = QCheckBox("Only leads with a website")
        self.cb_closed = QCheckBox("Skip permanently closed")
        self.cb_enrich = QCheckBox("Enrich contacts (Outscraper, extra credits)")
        for box in (self.cb_phone, self.cb_landline, self.cb_site, self.cb_closed,
                    self.cb_enrich):
            box.toggled.connect(self._sync_run_button)
            vl.addWidget(box)
        outer.addWidget(vol_card)

        # ---- 8 output ------------------------------------------------------- #
        out_card, ol = card("8 · export")
        self.format_combo = QComboBox()
        for fmt, label, desc in exporters.FORMATS:
            self.format_combo.addItem(f"{label}  ·  .{fmt}", fmt)
            idx = self.format_combo.count() - 1
            self.format_combo.setItemData(idx, desc, Qt.ToolTipRole)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        ol.addWidget(self.format_combo)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.out_edit = QLineEdit()
        self.out_edit.setReadOnly(True)
        row.addWidget(self.out_edit, 1)
        browse = QPushButton()
        browse.setIcon(icons.icon("folder", self.p.text_dim, 15))
        browse.setToolTip("Choose the output file")
        browse.clicked.connect(self.choose_output)
        row.addWidget(browse)
        ol.addLayout(row)

        row = QHBoxLayout()
        row.setSpacing(6)
        folder = QPushButton("Open folder")
        folder.setIcon(icons.icon("open", self.p.text_dim, 14))
        folder.clicked.connect(lambda: open_in_desktop(
            os.path.dirname(os.path.abspath(self.out_edit.text())) or "."))
        row.addWidget(folder)
        reveal = QPushButton("Reveal last export")
        reveal.setIcon(icons.icon("file", self.p.text_dim, 14))
        reveal.clicked.connect(self.reveal_last)
        row.addWidget(reveal)
        row.addStretch(1)
        ol.addLayout(row)
        outer.addWidget(out_card)
        outer.addStretch(1)
        outer.setSizeConstraint(QVBoxLayout.SetMinimumSize)
        return panel

    def _build_runbar(self) -> QWidget:
        """Primary action, always visible (never scrolls out of reach)."""
        bar = QWidget()
        bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.plan_label = QLabel("")
        self.plan_label.setObjectName("hint")
        self.plan_label.setWordWrap(True)
        self.plan_label.setAlignment(Qt.AlignCenter)
        self.plan_label.setMinimumHeight(30)
        lay.addWidget(self.plan_label)

        self.run_btn = QPushButton("  Run search")
        self.run_btn.setProperty("accent", True)
        self.run_btn.setMinimumHeight(44)
        self.run_btn.setIcon(icons.icon("play", self.p.accent_text, 15))
        self.run_btn.clicked.connect(self.toggle_run)
        lay.addWidget(self.run_btn)
        bar.setMinimumHeight(bar.sizeHint().height())
        return bar

    # -- right: results ------------------------------------------------------
    def _build_right(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(6, 14, 14, 14)
        lay.setSpacing(12)

        # stats
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.stat_leads = StatCard("leads", "–", "", self.p)
        self.stat_phone = StatCard("with phone", "–", "", self.p)
        self.stat_site = StatCard("with website", "–", "", self.p)
        self.stat_rating = StatCard("avg rating", "–", "", self.p)
        self.stat_reviews = StatCard("reviews", "–", "", self.p)
        self.stat_time = StatCard("elapsed", "–", "", self.p)
        for card_widget in (self.stat_leads, self.stat_phone, self.stat_site,
                            self.stat_rating, self.stat_reviews, self.stat_time):
            stats_row.addWidget(card_widget)
        lay.addLayout(stats_row)

        # results card
        results, rl = card()
        head = QHBoxLayout()
        title = QLabel("RESULTS")
        title.setObjectName("cardTitle")
        head.addWidget(title)
        self.result_count = QLabel("")
        self.result_count.setObjectName("hint")
        head.addWidget(self.result_count)
        head.addStretch(1)
        self.filter_edit = QLineEdit()
        self.filter_edit.setObjectName("searchBox")
        self.filter_edit.setPlaceholderText("filter rows…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setFixedWidth(220)
        self.filter_edit.textChanged.connect(self.proxy.setNeedle)
        head.addWidget(self.filter_edit)
        copy_btn = QPushButton("  Copy selection")
        copy_btn.setIcon(icons.icon("copy", self.p.text_dim, 14))
        copy_btn.clicked.connect(self.copy_selection)
        head.addWidget(copy_btn)
        rl.addLayout(head)

        self.table = build_table(self.model, self.proxy)
        self.table.doubleClicked.connect(self.open_row)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.table_menu)
        self.model.widths_changed.connect(self._fit_columns)
        rl.addWidget(self.table, 1)
        lay.addWidget(results, 1)

        # log
        log_card, ll = card("ACTIVITY")
        self.log = LogPane(self.p)
        ll.addWidget(self.log)
        self.log_panel = log_card
        log_card.setMinimumHeight(120)
        log_card.setMaximumHeight(210)
        lay.addWidget(log_card)

        self.log.write("Ready. Pick a provider, a city and a business type, then Run.", "info")
        return panel

    # ------------------------------------------------------------ behaviour --
    def _apply_provider_defaults(self) -> None:
        configured = [n for n in ORDER if PROVIDERS[n].is_configured()]
        if configured:
            self.provider_combo.setValueByPredicate(lambda p: p == configured[0])
        else:
            # nothing configured yet: open on Demo so the app works out of the box
            self.provider_combo.setValueByPredicate(lambda p: p == "demo")
            self.log.write("No API keys found yet - Demo mode is ready to use "
                           "(synthetic leads). Add a real key in API keys…", "warn")
        self._on_provider_changed()
        if not self.city_combo.currentText().strip():
            self.city_combo.setCurrentText("Berlin")
        self._on_business_changed()      # the first text is set before signals hook
        self._update_plan_label()

    def _refresh_provider_status(self) -> None:
        ready = [PROVIDERS[n].label for n in ORDER if PROVIDERS[n].is_configured()]
        if ready:
            self.provider_badge.setText("keys: " + ", ".join(ready))
            self.provider_badge.setObjectName("badgeOk")
        else:
            self.provider_badge.setText("no API keys — demo mode available")
            self.provider_badge.setObjectName("badgeWarn")
        self.provider_badge.style().unpolish(self.provider_badge)
        self.provider_badge.style().polish(self.provider_badge)

    def _on_provider_changed(self) -> None:
        name = self.provider_combo.value() or "demo"
        cls = PROVIDERS[name]
        if name == "demo":
            self.provider_note.setText(
                "Offline synthetic data — no key, no network. Try the whole app instantly.")
        else:
            key = cls.api_key() or ""
            masked = f"{key[:6]}…{key[-4:]}" if len(key) > 12 else ("key detected" if key else "")
            state = "key detected: " + masked if key else \
                f"no key — set {' or '.join(cls.env_keys)} in API keys"
            self.provider_note.setText(f"{state}  ·  up to {cls.per_query_cap} results "
                                       f"per query  ·  {cls.homepage}")
        self._sync_fields_availability()
        self._update_plan_label()
        self._sync_run_button()

    def _on_country_changed(self) -> None:
        country = self.country_combo.value()
        if not country:
            return
        states = list(country.states)
        self.region_combo.blockSignals(True)
        self.region_combo.clear()
        self.region_combo.setEditable(True)
        self.region_combo.addItem("")
        self.region_combo.addItems(states)
        self.region_combo.setCurrentIndex(0)
        self.region_combo.setPlaceholderText(
            f"{len(states)} regions listed — or type one" if states
            else "region / state (optional)")
        self.region_combo.blockSignals(False)
        self._refresh_city_list()

    def _refresh_city_list(self) -> None:
        country = self.country_combo.value()
        if not country:
            return
        region = self.region_combo.currentText().strip()
        names = [name for name, _ in CI.candidates(country.iso, region)]
        self.city_combo.clear()
        self.city_combo.setEditable(True)
        self.city_combo.addItems(names)
        self.city_combo.setInsertPolicy(QComboBox.NoInsert)
        if names:
            self.city_combo.setCurrentText(names[0])
        self.city_combo.setPlaceholderText(
            f"{len(names)} catalogued cities — or type one" if names else "city name")
        self._update_plan_label()

    def _on_business_changed(self) -> None:
        text = self.business_combo.currentText().strip()
        hits = VT.resolve(text) if text else []
        if hits:
            v = hits[0]
            note = f'Searches as “{v.query}”'
            if v.synonyms:
                note += f'  ·  also {", ".join(v.synonyms[:2])}'
            if text.lower() not in (v.label.lower(), v.query.lower()):
                note += f'  ·  matched “{v.label}”'
            self.business_note.setText(note)
        else:
            self.business_note.setText("Free-text search term." if text else "")
        self._update_plan_label()

    def _sync_fields_availability(self) -> None:
        provider = self.provider_combo.value() or "demo"
        self._fields = [f for f in self._fields if _supports(provider, f)]
        if not self._fields:
            self._fields = [f for f in FD.RECOMMENDED if _supports(provider, f)]
        self._refresh_fields_label()

    def _refresh_fields_label(self) -> None:
        provider = self.provider_combo.value() or "demo"
        usable = [f for f in self._fields if _supports(provider, f)]
        self.fields_count.setText(f"{len(usable)} selected")
        groups: Dict[str, int] = {}
        for f in usable:
            groups[FD.group_of(f)] = groups.get(FD.group_of(f), 0) + 1
        self.fields_note.setText("  ".join(f"{g} ×{n}" for g, n in groups.items()))

    def choose_fields(self) -> None:
        provider = self.provider_combo.value() or "demo"
        dlg = FieldPickerDialog(provider, self._fields, self)
        if dlg.exec() == QDialog.Accepted:
            self._fields = dlg.selected() or list(FD.BASIC)
            self._refresh_fields_label()
            self._update_plan_label()

    def _on_format_changed(self) -> None:
        # keep the auto-suggested name in step with the chosen extension
        if not self._manual_path:
            self.out_edit.setText(self._suggest_path())
        self._update_plan_label()

    def _set_result_count(self, text: str) -> None:
        self.result_count.setText(text)
        self.result_count.setVisible(bool(text))

    def choose_output(self) -> None:
        fmt = self.format_combo.currentData() or "csv"
        current = self.out_edit.text() or self._suggest_path()
        start_dir = os.path.dirname(current) or paths.default_export_dir()
        paths.ensure_dir(start_dir)
        chosen, _ = QFileDialog.getSaveFileName(
            self, "Save leads to", current,
            f"{exporters.LABEL[fmt]} (*.{fmt});;All files (*)")
        if chosen:
            if not chosen.lower().endswith(f".{fmt}"):
                chosen += f".{fmt}"
            self.out_edit.setText(chosen)
            self._manual_path = True

    def _suggest_path(self) -> str:
        fmt = self.format_combo.currentData() or "csv"
        country = self.country_combo.value()
        place = (self.city_combo.currentText().strip()
                 or self.region_combo.currentText().strip()
                 or (country.name if country else "leads"))
        business = self.business_combo.currentText().strip() or "leads"
        return exporters.suggest_path(fmt, f"{business}-{place}", paths.default_export_dir())

    def reveal_last(self) -> None:
        if self._last_outpath and os.path.exists(self._last_outpath):
            open_in_desktop(self._last_outpath)
        else:
            open_in_desktop(paths.default_export_dir())

    # -- plan preview --------------------------------------------------------
    def _on_landline_toggled(self, checked: bool) -> None:
        """A landline filter only makes sense when a phone is required."""
        if checked and not self.cb_phone.isChecked():
            self.cb_phone.setChecked(True)
        self._sync_run_button()

    def spec(self) -> SearchSpec:
        country = self.country_combo.value()
        text = self.business_combo.currentText().strip()
        hits = VT.resolve(text)
        vertical = hits[0] if hits else None
        provider = self.provider_combo.value() or "demo"
        fmt = self.format_combo.currentData() or "csv"
        region = self.region_combo.currentText().strip()
        city = self.city_combo.currentText().strip()
        if region and region.lower() == city.lower():
            region = ""            # "Berlin, Berlin, Germany" reads badly
        return SearchSpec(
            provider_name=provider,
            country=country,
            region=region,
            city=city,
            business_label=vertical.label if vertical else text,
            terms=[vertical.query] + list(vertical.synonyms[:2]) if vertical else [text],
            fields=list(self._fields),
            limit=self.limit_spin.value(),
            language=(country.lang if country else "en"),
            min_rating=self.min_rating.value() or None,
            min_reviews=self.min_reviews.value() or None,
            require_phone=self.cb_phone.isChecked(),
            require_website=self.cb_site.isChecked(),
            skip_closed=self.cb_closed.isChecked(),
            skip_landlines=self.cb_landline.isChecked(),
            enrich=self.cb_enrich.isChecked(),
            fmt=fmt,
            outpath=self.out_edit.text() or self._suggest_path(),
            outdir=paths.default_export_dir(),
        )

    def _update_plan_label(self) -> None:
        spec = self.spec()
        problems = self._problems()
        if problems:
            # say *why* Run is greyed out instead of leaving the user guessing
            self.plan_label.setText("⚠  " + problems[0])
            self.plan_label.setStyleSheet(f"color: {self.p.warning};")
        else:
            where = ", ".join(p for p in (spec.city, spec.region,
                                          spec.country.name if spec.country else "") if p)
            queries = ", ".join(spec.terms[:2])
            self.plan_label.setText(
                f"{len(spec.fields)} fields → .{spec.fmt}  ·  “{queries}”"
                f" in {where or '…'}")
            self.plan_label.setStyleSheet("")
        self._sync_run_button()

    def _problems(self) -> List[str]:
        issues: List[str] = []
        spec = self.spec()
        if not spec.city and not spec.region:
            issues.append("pick a city (or a region)")
        if not spec.terms or not spec.terms[0].strip():
            issues.append("choose a business type")
        if not spec.fields:
            issues.append("select at least one field")
        if spec.provider_name != "demo" and not PROVIDERS[spec.provider_name].is_configured():
            issues.append(f"{PROVIDERS[spec.provider_name].label} has no API key — "
                          "open API keys, or switch to Demo")
        return issues

    def _sync_run_button(self) -> None:
        running = self._thread is not None and self._thread.isRunning()
        if running:
            self.run_btn.setText("  Stop")
            self.run_btn.setIcon(icons.icon("stop", self.p.text_dim, 15))
            self.run_btn.setProperty("accent", False)
        else:
            self.run_btn.setText("  Run search")
            self.run_btn.setIcon(icons.icon("play", self.p.accent_text, 15))
            self.run_btn.setProperty("accent", True)
        self.run_btn.setEnabled(not self._problems() or running)
        self.run_btn.style().unpolish(self.run_btn)
        self.run_btn.style().polish(self.run_btn)

    # -- run / stop ----------------------------------------------------------
    def toggle_run(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            self.stop()
            return
        issues = self._problems()
        if issues:
            QMessageBox.warning(self, "Almost there",
                                "Before running:\n\n• " + "\n• ".join(issues))
            return
        self.start()

    def start(self) -> None:
        spec = self.spec()
        self.out_edit.setText(spec.outpath)
        self.model.clear()
        self.proxy.setNeedle("")
        self.filter_edit.clear()
        self._set_result_count("running…")
        self.log.clear()
        self._set_stats(leads=0, phone=0, site=0, rating=None, reviews=0, elapsed=0.0)
        self.table.set_empty_text("Scraping…\n\nresults appear here as they come in")
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self._set_form_enabled(False)

        self._worker = HarvestWorker(spec)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self._on_log)
        self._worker.progress.connect(self.on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._cleanup_thread)
        self._sync_run_button()
        self._thread.start()

    def stop(self) -> None:
        if self._worker is not None:
            self._worker.stop()
        self.log.write("Stop requested — finishing the current query…", "warn")
        self.run_btn.setEnabled(False)

    def _cleanup_thread(self) -> None:
        self._thread = None
        self._worker = None
        self.progress.setVisible(False)
        self._set_form_enabled(True)
        self._sync_run_button()

    def _set_form_enabled(self, enabled: bool) -> None:
        for widget in (self.provider_combo, self.country_combo, self.region_combo,
                       self.city_combo, self.business_combo, self.fields_btn,
                       self.limit_spin, self.min_rating, self.min_reviews,
                       self.cb_phone, self.cb_landline, self.cb_site, self.cb_closed,
                       self.cb_enrich, self.format_combo):
            widget.setEnabled(enabled)
        # keys + theme stay usable mid-run: neither can corrupt a harvest
        self.act_run.setEnabled(not enabled and not self._problems())

    # -- worker callbacks ----------------------------------------------------
    @Slot(str, str)
    def _on_log(self, message: str, level: str) -> None:
        self.log.write(message, level)

    def on_progress(self, value: float) -> None:
        self.progress.setValue(int(value * 100))

    def _on_finished(self, result: RunResult) -> None:
        self.model.set_leads(result.leads, result.columns)
        if not result.leads:
            self.table.set_empty_text(
                "No leads matched those filters.\n\n"
                "Try a bigger limit, a different city spelling,\n"
                "or relax the rating / phone filters.")
        stats = result.stats
        self._set_stats(leads=stats["total"],
                        phone=stats["with_phone"],
                        site=stats["with_website"],
                        rating=stats["avg_rating"],
                        reviews=stats["total_reviews"],
                        elapsed=result.report.elapsed)
        report = result.report
        self.log.write(
            f"Kept {stats['total']} of {report.raw_count} raw results "
            f"({report.duplicates} duplicates, "
            f"{sum(report.filtered.values()) if report.filtered else 0} filtered) "
            f"in {report.elapsed:.1f}s", "ok")
        for err in report.errors[:3]:
            self.log.write(err, "error")
        self._set_result_count(
            f"{stats['total']} rows · {self.proxy.rowCount()} shown"
            if stats["total"] else "no leads matched — try a bigger limit or a "
                                  "different city spelling")
        if result.exported:
            self._last_outpath = result.outpath
            self.status_right.setText(result.outpath)
        if stats["total"] and result.report.raw_count:
            self.status_left.setText(
                f"{stats['total']} leads · {self.proxy.rowCount()} shown after filter")
        if result.error:
            self.log.write(result.error, "error")

    def _on_failed(self, message: str, hint_text: str) -> None:
        self.log.write(message, "error")
        if hint_text:
            self.log.write(hint_text, "warn")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Search failed")
        box.setText(message)
        if hint_text:
            box.setInformativeText(hint_text)
        if self.provider_combo.value() == "demo":
            pass
        else:
            box.setStandardButtons(QMessageBox.Ok)
            open_keys = box.addButton("Open API keys", QMessageBox.ActionRole)
            box.exec()
            if box.clickedButton() is open_keys:
                self.open_keys()
            return
        box.exec()

    def _set_stats(self, leads: int, phone: int, site: int,
                   rating: Optional[float], reviews: int, elapsed: float) -> None:
        def pct(part: int) -> str:
            return f"{round(part * 100 / leads)}%" if leads else "—"

        self.stat_leads.set(str(leads), f"target {self.limit_spin.value()}")
        self.stat_phone.set(pct(phone), f"{phone} with a number")
        self.stat_site.set(pct(site), f"{site} with a URL")
        self.stat_rating.set(f"{rating:.2f} ★" if rating else "–",
                             "average" if rating else "")
        self.stat_reviews.set(f"{reviews:,}", "total reviews")
        self.stat_time.set(f"{elapsed:.1f}s" if elapsed else "–",
                           f"{len(self.model.leads)} rows")
        for widget in (self.stat_leads, self.stat_phone, self.stat_site,
                       self.stat_rating):
            widget.set_accent(self.p.text)
        if leads:
            self.stat_leads.set_accent(self.p.success)

    # -- table actions -------------------------------------------------------
    def _fit_columns(self) -> None:
        """Give every column a width that fits its own content."""
        header = self.table.horizontalHeader()
        for col, width in self.model.column_widths().items():
            header.resizeSection(col, width)

    def copy_selection(self) -> None:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()} \
            if self.table.selectionModel() else set()
        if not rows:
            QMessageBox.information(self, "Copy", "Select one or more rows first.")
            return
        self._copy_rows(sorted(rows), tab=False)

    def _copy_rows(self, rows: List[int], tab: bool) -> None:
        sep = "\t" if tab else ", "
        lines: List[str] = []
        if tab:
            headers = [str(self.model.headerData(c, Qt.Horizontal))
                       for c in range(self.model.columnCount())]
            lines.append(sep.join(headers))
        for row in rows:
            lead = self.model.leads[row]
            cells = []
            for key in self.model.columns:
                text = self.model._display(key, lead.get(key)).replace("\n", " ")
                if not tab and "," in text:       # keep CSV-ish quotes out of the way
                    text = f'"{text}"'
                cells.append(text)
            lines.append(sep.join(cells))
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.log.write(f"Copied {len(rows)} row(s) to the clipboard.", "ok")

    def table_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        lead = self.model.leads[self.proxy.mapToSource(index).row()]
        key = self.model.columns[self.proxy.mapToSource(index).column()]
        menu = QMenu(self)
        act_copy = menu.addAction(icons.icon("copy", self.p.text_dim, 14), "Copy cell")
        act_row = menu.addAction("Copy row")
        act_tsv = menu.addAction("Copy row as TSV")
        act_sheet = menu.addAction("Copy selection as spreadsheet text")
        menu.addSeparator()
        act_maps = menu.addAction(icons.icon("pin", self.p.text_dim, 14), "Open in Google Maps")
        act_site = menu.addAction(icons.icon("external", self.p.text_dim, 14), "Open website")
        act_phone = menu.addAction(icons.icon("search", self.p.text_dim, 14), "Search phone online")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == act_copy:
            QGuiApplication.clipboard().setText(self.model._display(key, lead.get(key)))
            self.log.write("Cell copied.", "ok")
        elif chosen in (act_row, act_tsv):
            row = self.proxy.mapToSource(index).row()
            self._copy_rows([row], tab=chosen is act_tsv)
        elif chosen == act_sheet:
            rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
            self._copy_rows([self.proxy.mapToSource(self.proxy.index(r, 0)).row()
                             for r in rows], tab=True)
        elif chosen == act_maps:
            open_in_desktop(lead.get("maps_url") or lead.get("website") or "")
        elif chosen == act_site:
            if lead.get("website"):
                open_in_desktop(str(lead["website"]))
        elif chosen == act_phone:
            phone = str(lead.get("phone") or "").strip()
            if phone:
                QGuiApplication.openUrl(QUrl(f"https://www.google.com/search?q={phone}"))

    def open_row(self, index) -> None:
        source = self.proxy.mapToSource(index)
        if not source.isValid():
            return
        lead = self.model.leads[source.row()]
        target = lead.get("maps_url") or lead.get("website")
        if target:
            open_in_desktop(str(target))

    # -- dialogs / chrome ----------------------------------------------------
    def open_keys(self) -> None:
        dlg = KeysDialog(self.p, self)
        dlg.exec()
        self._refresh_provider_status()
        self._on_provider_changed()

    def toggle_theme(self) -> None:
        self.theme_name = "light" if self.p.is_dark else "dark"
        self.theme_changed.emit(self.theme_name)

    def _build_menu(self) -> None:
        """Menu bar: the few commands that have no button on screen."""
        bar = self.menuBar()
        bar.setNativeMenuBar(False)

        self.act_keys = QAction("&API keys…", self)
        self.act_keys.setShortcut(QKeySequence("Ctrl+K"))
        self.act_keys.triggered.connect(self.open_keys)

        self.act_theme = QAction("&Toggle theme", self)
        self.act_theme.setShortcut(QKeySequence("Ctrl+J"))
        self.act_theme.triggered.connect(self.toggle_theme)

        self.act_run = QAction("&Run search", self)
        self.act_run.setShortcut(QKeySequence("Ctrl+R"))
        self.act_run.triggered.connect(self.toggle_run)

        act_about = QAction(f"&About MAPLEAD {VERSION}", self)
        act_about.triggered.connect(self.about)

        act_about_qt = QAction("About &Qt", self)
        act_about_qt.triggered.connect(lambda: QMessageBox.aboutQt(self, "MAPLEAD"))

        menu = bar.addMenu("&MAPLEAD")
        menu.addAction(self.act_run)
        menu.addSeparator()
        menu.addAction(self.act_keys)
        menu.addAction(self.act_theme)
        menu.addSeparator()
        menu.addAction(act_about)
        menu.addAction(act_about_qt)

    def about(self) -> None:
        QMessageBox.about(
            self, "About MAPLEAD",
            f"<b>MAPLEAD {VERSION}</b><br>Desktop edition<br><br>"
            f"Google Maps lead extractor — GUI front-end for the same engine the "
            f"CLI uses ({len(CO.COUNTRIES)} countries, {len(VT.VERTICALS)} business "
            f"verticals, {len(FD.FIELDS)} fields, {len(exporters.FORMATS)} formats).<br><br>"
            f"Keys: {paths.user_env_file()}<br>"
            f"Exports: {paths.default_export_dir()}")

    # -- persistence ---------------------------------------------------------
    def _fit_to_screen(self) -> None:
        """A window remembered from a bigger screen must not hide Run/Stop."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        width = min(self.width(), avail.width())
        height = min(self.height(), avail.height())
        if (width, height) != (self.width(), self.height()):
            self.resize(max(self.minimumWidth(), width),
                        max(self.minimumHeight(), height))
        if not avail.intersects(self.frameGeometry()):
            self.move(avail.topLeft())

    def _settings(self) -> QSettings:
        return QSettings("maplead", "maplead-desktop")

    def _restore_state(self) -> None:
        s = self._settings()
        geo = s.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        self._fit_to_screen()
        theme = s.value("theme", self.p.name)
        self.theme_name = theme if theme in ("dark", "light") else self.p.name
        state = s.value("form")
        if state:
            try:
                data = json.loads(state)
            except (TypeError, ValueError):
                data = {}
            self._load_form(data if isinstance(data, dict) else {})
        self._fields = [f for f in self._fields if f in FD.BY_KEY] or list(FD.RECOMMENDED)
        self._refresh_fields_label()
        self._update_plan_label()

    def _load_form(self, data: Dict[str, Any]) -> None:
        try:
            if data.get("provider") in PROVIDERS:
                self.provider_combo.setValueByPredicate(lambda p: p == data["provider"])
            if data.get("country"):
                iso = data["country"]
                self.country_combo.setValueByPredicate(lambda c: c.iso == iso)
            if "region" in data:
                self.region_combo.setCurrentText(data["region"] or "")
            if data.get("city"):
                self.city_combo.setCurrentText(data["city"])
            if data.get("business"):
                self.business_combo.setCurrentText(data["business"])
            if data.get("fields"):
                self._fields = [f for f in data["fields"] if f in FD.BY_KEY]
            self.limit_spin.setValue(int(data.get("limit", 60)))
            self.min_rating.setValue(float(data.get("min_rating", 0) or 0))
            self.min_reviews.setValue(int(data.get("min_reviews", 0) or 0))
            self.cb_phone.setChecked(bool(data.get("require_phone")))
            self.cb_landline.setChecked(bool(data.get("skip_landlines")))
            self.cb_site.setChecked(bool(data.get("require_website")))
            self.cb_closed.setChecked(bool(data.get("skip_closed")))
            self.cb_enrich.setChecked(bool(data.get("enrich")))
            fmt = data.get("format", "csv")
            idx = self.format_combo.findData(fmt)
            if idx >= 0:
                self.format_combo.setCurrentIndex(idx)
            # a hand-picked path is sticky; an auto-suggested one gets a fresh
            # timestamp every launch
            if data.get("outpath"):
                self.out_edit.setText(data["outpath"])
                self._manual_path = True
            else:
                self.out_edit.setText(self._suggest_path())
        except (TypeError, ValueError):
            self.out_edit.setText(self._suggest_path())

    def _save_state(self) -> None:
        spec = self.spec()
        s = self._settings()
        s.setValue("geometry", self.saveGeometry())
        s.setValue("theme", self.theme_name)
        s.setValue("form", json.dumps({
            "provider": spec.provider_name,
            "country": spec.country.iso if spec.country else "",
            "region": spec.region,
            "city": spec.city,
            "business": spec.business_label,
            "fields": self._fields,
            "limit": spec.limit,
            "min_rating": self.min_rating.value(),
            "min_reviews": self.min_reviews.value(),
            "require_phone": spec.require_phone,
            "require_website": spec.require_website,
            "skip_closed": spec.skip_closed,
            "skip_landlines": spec.skip_landlines,
            "enrich": spec.enrich,
            "format": spec.fmt,
            "outpath": self.out_edit.text() if self._manual_path else "",
        }))
        s.sync()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self._thread is not None and self._thread.isRunning():
            if self._worker is not None:
                self._worker.stop()
            self._thread.quit()
            self._thread.wait(4000)
        self._save_state()
        super().closeEvent(event)
