"""
Turbo mode: search city by city, business by business, and message every match.

Two windows, built on the bulk sender (nothing about WhatsApp Web is redone here):

* :class:`TurboSetupDialog` — tick the cities and the business types, pick the
  lead filter (*No website* by default), the leads per search and the safety
  settings. The message is the one saved in the leads panel.
* :class:`TurboWindow` — a :class:`~maplead.gui.bulk_sender.WhatsAppSenderWindow`
  whose queue refills itself: when the leads of one (city, business) search are
  all handled it runs the next search, filters the result, queues the leads not
  contacted yet and keeps sending. It ends after the last business of the last
  city, or when the user stops it.

The order of the steps, the filter and the "already done" memory are in
``maplead/turbo.py``.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QSpinBox, QSplitter, QVBoxLayout,
                               QWidget)

from .. import outreach, turbo
from ..data import cities as CI
from ..data import fields as FD
from ..data import verticals as VT
from ..providers import PROVIDERS
from . import icons
from .bulk_sender import (SafetyForm, WhatsAppSenderWindow, load_safety,
                          save_safety, webengine_available)
from .theme import Palette
from .widgets import card, field_label
from .worker import HarvestWorker, RunResult, SearchSpec

_SETTINGS_ORG = "maplead"
_SETTINGS_APP = "maplead-desktop"
_SETUP_KEY = "turbo/setup"

# the columns a turbo search always asks for: the filter and the message need them
_NEEDED_FIELDS = ("name", "category", "city", "phone", "website", "whatsapp", "email")

MAX_SEARCH_FAILURES = 3      # in a row, before the run gives up


def _load_setup() -> Dict[str, Any]:
    value = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(_SETUP_KEY, "")
    try:
        data = json.loads(str(value)) if value else {}
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def _save_setup(data: Dict[str, Any]) -> None:
    store = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    store.setValue(_SETUP_KEY, json.dumps(data))
    store.sync()


# --------------------------------------------------------------------------- #
# a checklist with All / None and a box to add your own entry
# --------------------------------------------------------------------------- #

class _Checklist(QFrame):
    changed = Signal()

    def __init__(self, title: str, placeholder: str,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._names: set = set()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, lay = card(title)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        for label, state in (("All", Qt.Checked), ("None", Qt.Unchecked)):
            button = QPushButton(label)
            button.setProperty("flat", True)
            button.clicked.connect(lambda _=False, s=state: self._tick_all(s))
            tools.addWidget(button)
        tools.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("hint")
        tools.addWidget(self.count_label)
        lay.addLayout(tools)

        self.list = QListWidget()
        self.list.itemChanged.connect(self._on_changed)
        lay.addWidget(self.list, 1)

        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self.add_edit = QLineEdit()
        self.add_edit.setPlaceholderText(placeholder)
        self.add_edit.returnPressed.connect(self._add_typed)
        add_row.addWidget(self.add_edit, 1)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_typed)
        add_row.addWidget(add_btn)
        lay.addLayout(add_row)
        outer.addWidget(frame)

    def add(self, text: str, data: Any = None, checked: bool = True,
            top: bool = False) -> bool:
        """Append an entry; call :meth:`refresh` once the batch is in."""
        text = (text or "").strip()
        if not text or text.lower() in self._names:
            return False
        self._names.add(text.lower())
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        item.setData(Qt.UserRole, data)
        self.list.blockSignals(True)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        if top:
            self.list.insertItem(0, item)
        else:
            self.list.addItem(item)
        self.list.blockSignals(False)
        return True

    def refresh(self) -> None:
        self._on_changed()

    def entries(self, checked_only: bool = True) -> List[Tuple[str, Any]]:
        out: List[Tuple[str, Any]] = []
        for row in range(self.list.count()):
            item = self.list.item(row)
            if not checked_only or item.checkState() == Qt.Checked:
                out.append((item.text(), item.data(Qt.UserRole)))
        return out

    def unchecked(self) -> List[str]:
        return [self.list.item(r).text() for r in range(self.list.count())
                if self.list.item(r).checkState() != Qt.Checked]

    def _tick_all(self, state: Qt.CheckState) -> None:
        self.list.blockSignals(True)
        for row in range(self.list.count()):
            self.list.item(row).setCheckState(state)
        self.list.blockSignals(False)
        self._on_changed()

    def _add_typed(self) -> None:
        text = self.add_edit.text().strip()
        if text:
            self.add(text, data="custom", top=True)
            self.add_edit.clear()
            self.refresh()

    def _on_changed(self, *_: Any) -> None:
        self.count_label.setText(
            f"{len(self.entries())} of {self.list.count()} selected")
        self.changed.emit()


# --------------------------------------------------------------------------- #
# setup dialog
# --------------------------------------------------------------------------- #

class TurboSetupDialog(QDialog):
    """Choose the cities, the business types, the filter and the pacing."""

    def __init__(self, base: SearchSpec, palette: Palette, *,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.p = palette
        self.base = base
        self._iso = base.country.iso if base.country else ""
        self.progress = turbo.Progress()
        self.safety = load_safety()
        self.steps: List[turbo.Step] = []
        self.filter_key = turbo.DEFAULT_FILTER
        self.limit = base.limit
        saved = _load_setup()
        per_country = saved.get("countries", {}).get(self._iso, {}) \
            if isinstance(saved.get("countries"), dict) else {}

        self.setWindowTitle("MAPLEAD — turbo mode")
        self.setMinimumSize(900, 640)
        self.resize(1120, 760)
        self.setSizeGripEnabled(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)

        # header -------------------------------------------------------------
        header = QFrame()
        header.setObjectName("panelHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 12, 16, 12)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("TURBO MODE")
        title.setObjectName("panelTitle")
        titles.addWidget(title)
        where = ", ".join(p for p in (base.region,
                                      base.country.name if base.country else "") if p)
        provider = PROVIDERS[base.provider_name].label \
            if base.provider_name in PROVIDERS else base.provider_name
        sub = QLabel(" · ".join(p for p in (where, provider) if p))
        sub.setObjectName("panelSub")
        titles.addWidget(sub)
        hl.addLayout(titles)
        hl.addStretch(1)
        message_btn = QPushButton("  Edit message")
        message_btn.setIcon(icons.icon("chat", self.p.text_dim, 15))
        message_btn.clicked.connect(self._edit_template)
        hl.addWidget(message_btn)
        root.addWidget(header)

        # lists + options ------------------------------------------------------
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)

        self.cities = _Checklist("Cities, in this order", "add a city")
        off = {str(c).lower() for c in per_country.get("cities_off", [])}
        for city, region in CI.candidates(self._iso, base.region):
            self.cities.add(city, data=region, checked=city.lower() not in off)
        for city in per_country.get("custom_cities", []):
            self.cities.add(str(city), data="custom", top=True,
                            checked=str(city).lower() not in off)
        if base.city:
            self.cities.add(base.city, data=base.region, top=True)
        self.cities.refresh()
        split.addWidget(self.cities)

        self.businesses = _Checklist("Business types, in this order",
                                     "add a business type")
        off = {str(b).lower() for b in saved.get("businesses_off", [])}
        for vertical in VT.VERTICALS:
            self.businesses.add(vertical.label, checked=vertical.label.lower() not in off)
        for business in saved.get("custom_businesses", []):
            self.businesses.add(str(business), data="custom", top=True,
                                checked=str(business).lower() not in off)
        self.businesses.refresh()
        split.addWidget(self.businesses)

        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(12)

        run_card, rc = card("Who gets the message")
        tip = "Only the leads that pass this filter are messaged"
        rc.addWidget(field_label("Lead filter", tip))
        self.filter_combo = QComboBox()
        self.filter_combo.setToolTip(tip)
        for key, label in turbo.FILTERS:
            self.filter_combo.addItem(label, key)
        index = self.filter_combo.findData(saved.get("filter", turbo.DEFAULT_FILTER))
        self.filter_combo.setCurrentIndex(max(0, index))
        self.filter_combo.currentIndexChanged.connect(self._sync_footer)
        rc.addWidget(self.filter_combo)
        tip = "How many leads each search (one business type in one city) collects"
        rc.addWidget(field_label("Leads per search", tip))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 100_000)
        self.limit_spin.setSingleStep(10)
        self.limit_spin.setSuffix(" leads")
        self.limit_spin.setToolTip(tip)
        try:
            self.limit_spin.setValue(int(saved.get("limit", base.limit)))
        except (TypeError, ValueError):
            self.limit_spin.setValue(base.limit)
        rc.addWidget(self.limit_spin)
        resume = QHBoxLayout()
        resume.setSpacing(6)
        self.skip_done = QCheckBox("Skip searches already finished")
        self.skip_done.setToolTip("Continue where the last turbo run stopped instead "
                                  "of running the same searches again")
        self.skip_done.setChecked(bool(saved.get("skip_done", True)))
        self.skip_done.toggled.connect(self._sync_footer)
        resume.addWidget(self.skip_done, 1)
        reset = QPushButton("Forget")
        reset.setProperty("flat", True)
        reset.setToolTip("Forget which searches were already finished")
        reset.clicked.connect(self._reset_progress)
        resume.addWidget(reset)
        rc.addLayout(resume)
        note = QLabel("Leads already messaged are always skipped.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        rc.addWidget(note)
        sl.addWidget(run_card)

        preview_card, pc = card("Message")
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(90)
        pc.addWidget(self.preview)
        sl.addWidget(preview_card, 1)

        self.safety_form = SafetyForm(self.safety)
        self.safety_form.changed.connect(self._sync_footer)
        sl.addWidget(self.safety_form)
        split.addWidget(side)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 2)
        split.setStretchFactor(2, 3)
        split.setSizes([310, 310, 440])
        root.addWidget(split, 1)

        # footer ---------------------------------------------------------------
        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.summary = QLabel("")
        self.summary.setObjectName("hint")
        self.summary.setWordWrap(True)
        footer.addWidget(self.summary, 1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        self.start_btn = QPushButton("  Start turbo")
        self.start_btn.setProperty("accent", True)
        self.start_btn.setIcon(icons.icon("play", self.p.accent_text, 13))
        self.start_btn.clicked.connect(self.accept)
        footer.addWidget(self.start_btn)
        root.addLayout(footer)

        self.cities.changed.connect(self._sync_footer)
        self.businesses.changed.connect(self._sync_footer)
        self._sync_preview()
        self._sync_footer()

    # -- state ------------------------------------------------------------------
    def _all_steps(self) -> List[turbo.Step]:
        cities = [(name, "" if region == "custom" else (region or self.base.region))
                  for name, region in self.cities.entries()]
        return turbo.build_steps(cities, [b for b, _ in self.businesses.entries()])

    def _pending_steps(self) -> List[turbo.Step]:
        steps = self._all_steps()
        if self.skip_done.isChecked():
            return self.progress.pending(self._iso, steps,
                                         self.filter_combo.currentData())
        return steps

    def _sync_preview(self) -> None:
        from .lead_panel import load_message_template
        self.preview.setPlainText(load_message_template() or "(empty message)")

    def _sync_footer(self, *_: Any) -> None:
        cities = len(self.cities.entries())
        businesses = len(self.businesses.entries())
        total = len(self._all_steps())
        pending = len(self._pending_steps())
        text = (f"{cities} cities × {businesses} business types = "
                f"{total} searches")
        if pending != total:
            text += f" · {total - pending} already finished, {pending} to run"
        text += " · every search uses provider credits"
        self.summary.setText(text)
        self.start_btn.setEnabled(pending > 0)

    def _reset_progress(self) -> None:
        if not self.progress.done:
            return
        answer = QMessageBox.question(
            self, "Forget finished searches?",
            f"{len(self.progress.done)} finished searches are remembered. "
            "Forget them, so turbo mode runs them again?\n\nLeads already "
            "messaged stay in the contact history and are not messaged twice.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            try:
                self.progress.clear()
            except OSError as exc:
                QMessageBox.warning(self, "Turbo mode",
                                    f"Could not save the progress file: {exc}")
            self._sync_footer()

    def _edit_template(self) -> None:
        from .lead_panel import WhatsAppTemplateDialog
        if WhatsAppTemplateDialog([], self.p, parent=self).exec() == QDialog.Accepted:
            self._sync_preview()

    def accept(self) -> None:  # noqa: D102 (Qt API)
        self.steps = self._pending_steps()
        if not self.steps:
            return
        self.filter_key = self.filter_combo.currentData()
        self.limit = self.limit_spin.value()
        self.safety = self.safety_form.value()
        save_safety(self.safety)
        saved = _load_setup()
        countries = saved.get("countries")
        if not isinstance(countries, dict):
            countries = {}
        countries[self._iso] = {
            "cities_off": self.cities.unchecked(),
            "custom_cities": [name for name, data in self.cities.entries(False)
                              if data == "custom"],
        }
        _save_setup({
            "countries": countries,
            "businesses_off": self.businesses.unchecked(),
            "custom_businesses": [name for name, data in self.businesses.entries(False)
                                  if data == "custom"],
            "filter": self.filter_key,
            "limit": self.limit,
            "skip_done": self.skip_done.isChecked(),
        })
        super().accept()


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #

class TurboWindow(WhatsAppSenderWindow):
    """The bulk sender, refilling its queue from one search after another."""

    batch_ready = Signal(object, object)     # SearchSpec, RunResult

    SEARCHING = "searching"

    def __init__(self, steps: Sequence[turbo.Step], base: SearchSpec,
                 filter_key: str, safety: outreach.SafetySettings,
                 palette: Palette, *,
                 progress: Optional[turbo.Progress] = None,
                 history: Optional[outreach.History] = None,
                 parent: Optional[QWidget] = None):
        self.steps: List[turbo.Step] = list(steps)
        self.base = base
        self.filter_key = filter_key
        self.turbo_progress = progress or turbo.Progress()
        self._step_index = -1
        self._step_ok = False            # the current step's search succeeded
        self._failures = 0               # failed searches in a row
        self._searches = 0
        self._spec: Optional[SearchSpec] = None
        self._worker: Optional[HarvestWorker] = None
        self._thread: Optional[QThread] = None
        super().__init__([], safety, palette, history=history, parent=parent)
        self.setWindowTitle("MAPLEAD — turbo mode")

    # -- queue hooks --------------------------------------------------------------
    def _log_intro(self) -> None:
        label = dict(turbo.FILTERS).get(self.filter_key, self.filter_key)
        cities = len({s.city.lower() for s in self.steps})
        self.log.write(f"Turbo: {len(self.steps)} searches in {cities} cities · "
                       f"filter “{label}” · " + self._safety_summary(), "info")

    def _more_coming(self) -> bool:
        return self._step_index < len(self.steps) - 1

    def _queue_exhausted(self) -> None:
        self._close_step()
        self._start_next_step()

    def _close_step(self) -> None:
        """Remember the step whose leads were all handled."""
        if not (0 <= self._step_index < len(self.steps)) or not self._step_ok:
            return
        self._step_ok = False
        iso = self.base.country.iso if self.base.country else ""
        try:
            self.turbo_progress.mark(
                turbo.step_key(iso, self.steps[self._step_index], self.filter_key))
        except OSError as exc:
            self.log.write(f"Could not save the turbo progress: {exc}", "error")

    # -- searching ----------------------------------------------------------------
    def _spec_for(self, step: turbo.Step) -> SearchSpec:
        label, terms = turbo.business_terms(step.business)
        region = step.region
        if region and region.lower() == step.city.lower():
            region = ""
        fields = list(self.base.fields)
        fields += [f for f in _NEEDED_FIELDS if f in FD.BY_KEY and f not in fields]
        return dataclasses.replace(
            self.base, city=step.city, region=region, business_label=label,
            terms=terms, fields=fields, require_phone=True,
            require_website=self.filter_key == "site")

    def _start_next_step(self) -> None:
        self._step_index += 1
        if self._step_index >= len(self.steps):
            self._done("Turbo finished — every city and business type handled")
            return
        step = self.steps[self._step_index]
        new_city = (self._step_index == 0
                    or self.steps[self._step_index - 1].city != step.city)
        if new_city:
            self.log.write(f"City: {step.city}", "ok")
        self._set_state(self.SEARCHING, f"Searching {step.label}",
                        f"Search {self._step_index + 1} of {len(self.steps)}")
        self.log.write(f"Search {self._step_index + 1}/{len(self.steps)}: "
                       f"{step.label}", "query")
        self._searches += 1
        self._spec = self._spec_for(step)
        worker = HarvestWorker(self._spec)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_search_finished)
        worker.failed.connect(self._on_search_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._worker, self._thread = worker, thread
        thread.start()

    def _wait_then_continue(self, seconds: int, reason: str) -> None:
        """Go on through the one-second loop, so Pause keeps working."""
        self._remaining = max(1, seconds)
        self._wait_reason = reason
        self._set_state(self.WAITING, "Paused" if self._paused else "Waiting", "")

    def _on_search_finished(self, result: RunResult) -> None:
        if self._state != self.SEARCHING:
            return                       # the run was stopped meanwhile
        self._worker = None
        self._failures = 0
        self._step_ok = not result.error
        matches = turbo.filter_leads(result.leads, self.filter_key)
        country = self.base.country
        from .lead_panel import load_message_template
        items = outreach.build_queue(
            matches, load_message_template(),
            dial=country.dial if country else "",
            iso=country.iso if country else "",
            history=self.history, skip_contacted=True)
        queued = {item.number for item in self.items}
        items = [item for item in items if item.number not in queued]
        label = dict(turbo.FILTERS).get(self.filter_key, self.filter_key)
        self.log.write(f"   {len(result.leads)} leads · {len(matches)} pass "
                       f"“{label}” · {len(items)} to message",
                       "ok" if items else "info")
        for error in result.report.errors[:2]:
            self.log.write(f"   {error}", "error")
        self.batch_ready.emit(self._spec, result)
        if items:
            self._extend_items(items)
            self._wait_then_continue(3, "search done")
        else:
            self._wait_then_continue(self.pacer.short_delay(), "nothing to send")

    def _on_search_failed(self, message: str, hint_text: str) -> None:
        if self._state != self.SEARCHING:
            return
        self._worker = None
        self._step_ok = False
        self._failures += 1
        self.log.write(f"   Search failed — {message}", "error")
        if hint_text:
            self.log.write(f"   {hint_text}", "warn")
        if self._failures >= MAX_SEARCH_FAILURES:
            self._done(f"Stopped — {self._failures} searches failed in a row")
            return
        self._wait_then_continue(self.pacer.short_delay(), "search failed")

    # -- ending -------------------------------------------------------------------
    def _done(self, title: str) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker = None
        super()._done(title)
        left = max(0, len(self.steps) - self._step_index - 1)
        self.log.write(f"{self._searches} searches run"
                       + (f" · {left} not reached — start turbo mode again to "
                          f"continue from there" if left else ""), "info")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().closeEvent(event)
        if event.isAccepted() and self._thread is not None:
            try:
                if self._thread.isRunning():
                    self._thread.quit()
                    self._thread.wait(4000)
            except RuntimeError:         # already deleted by Qt
                pass


def open_turbo(base: SearchSpec, palette: Palette, *,
               parent: Optional[QWidget] = None) -> Optional[TurboWindow]:
    """Setup dialog → turbo window. Returns the window (or None if cancelled)."""
    if not webengine_available():
        QMessageBox.warning(
            parent, "Turbo mode",
            "This build of MAPLEAD has no web engine (QtWebEngine), which turbo "
            "mode needs to run WhatsApp Web.\n\nInstall PySide6-WebEngine or "
            "use a release build that includes it.")
        return None
    dialog = TurboSetupDialog(base, palette, parent=parent)
    if dialog.exec() != QDialog.Accepted or not dialog.steps:
        return None
    spec = dataclasses.replace(base, limit=dialog.limit)
    window = TurboWindow(dialog.steps, spec, dialog.filter_key, dialog.safety,
                         palette, progress=dialog.progress, parent=parent)
    window.setAttribute(Qt.WA_DeleteOnClose, True)
    window.show()
    window.start()
    return window
