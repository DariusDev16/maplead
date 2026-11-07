"""
Bulk WhatsApp sender: pick leads, then let WhatsApp Web send them one by one.

Two windows:

* :class:`BulkSendDialog` — the leads from the panel's current filter with a
  checkbox each (numbers already messaged come unticked), a preview of the
  message every lead will get, and the safety settings (pauses, rests, the
  "continue?" threshold, the daily cap).
* :class:`WhatsAppSenderWindow` — WhatsApp Web inside the app (QtWebEngine, its
  own persistent profile, so the QR code is scanned once). A one-second state
  machine opens ``web.whatsapp.com/send?phone=…&text=…`` for each lead, waits for
  the send button, clicks it, confirms the composer emptied, records the result
  in the history and waits the pause the :class:`~maplead.outreach.Pacer` picks.

Everything WhatsApp-Web specific (selectors, texts) is in the ``_JS_*`` scripts
below — when WhatsApp changes its page, that is the only place to adjust.
QtWebEngine is imported lazily: a build without it still runs, and the panel
explains why bulk sending is unavailable.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton,
                               QSpinBox, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .. import contacts, outreach, paths
from . import icons
from .theme import Palette
from .widgets import LogPane, card, field_label

_SETTINGS_ORG = "maplead"
_SETTINGS_APP = "maplead-desktop"
_SAFETY_KEY = "whatsapp/bulk_safety"

WHATSAPP_WEB = "https://web.whatsapp.com/"
WHATSAPP_SEND = WHATSAPP_WEB + "send"

# seconds
OPEN_TIMEOUT = 60            # chat must open (or be reported invalid) by then
VERIFY_TIMEOUT = 20          # the composer must empty after clicking send
ENTER_FALLBACK_AT = 5        # press Enter ourselves if the click did nothing


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #

def load_safety() -> outreach.SafetySettings:
    value = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(_SAFETY_KEY, "")
    try:
        data = json.loads(str(value)) if value else None
    except ValueError:
        data = None
    return outreach.SafetySettings.from_dict(data)


def save_safety(settings: outreach.SafetySettings) -> None:
    store = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    store.setValue(_SAFETY_KEY, json.dumps(settings.normalized().to_dict()))
    store.sync()


def webengine_available() -> bool:
    import importlib
    try:
        importlib.import_module("PySide6.QtWebEngineCore")
        importlib.import_module("PySide6.QtWebEngineWidgets")
    except ImportError:
        return False
    return True


# --------------------------------------------------------------------------- #
# WhatsApp Web scripts (the only page-specific part)
# --------------------------------------------------------------------------- #

_JS_HELPERS = r"""
var mlq = function (list) {
  for (var i = 0; i < list.length; i++) {
    var el = document.querySelector(list[i]);
    if (el) return el;
  }
  return null;
};
var mlSend = function () {
  return mlq(['[data-icon="send"]', '[data-icon="wds-ic-send-filled"]',
              'span[data-icon*="send"]', 'button[aria-label="Send"]',
              'button[aria-label="Enviar"]', 'div[aria-label="Send"]',
              'div[aria-label="Enviar"]']);
};
var mlComposer = function () {
  return mlq(['footer div[contenteditable="true"]',
              'div[contenteditable="true"][data-tab="10"]',
              '#main div[contenteditable="true"][role="textbox"]']);
};
"""

_JS_PROBE = _JS_HELPERS + r"""
(function () {
  var side = mlq(['#pane-side', '[data-testid="chat-list"]',
                  'div[aria-label="Chat list"]', 'div[aria-label="Lista de conversas"]',
                  'div[aria-label="Lista de chats"]']);
  var qr = mlq(['canvas[aria-label*="QR"]', 'canvas[aria-label*="qr"]',
                'div[data-ref] canvas', '[data-testid="qrcode"]']);
  var dialog = mlq(['[data-animate-modal-popup="true"]', 'div[role="dialog"]']);
  var composer = mlComposer();
  return JSON.stringify({
    logged: !!side || !!composer,
    qr: !!qr,
    dialog: dialog ? (dialog.innerText || '').slice(0, 400) : '',
    send: !!mlSend(),
    composer: composer ? (composer.innerText || '').trim().length : -1
  });
})();
"""

_JS_CLICK_SEND = _JS_HELPERS + r"""
(function () {
  var el = mlSend();
  if (!el) return false;
  var btn = el.closest('button') || el.closest('[role="button"]') || el;
  btn.click();
  return true;
})();
"""

_JS_FOCUS_COMPOSER = _JS_HELPERS + r"""
(function () {
  var c = mlComposer();
  if (!c) return false;
  c.focus();
  return true;
})();
"""

# texts of the popup WhatsApp shows for a number that has no account
_INVALID_RE = re.compile(r"invalid|inv[áa]lid|no v[áa]lido|ung[üu]ltig|non valide|"
                         r"not on whatsapp|n[ãa]o est[áa] no whatsapp", re.I)
# popups that are only a "please wait"
_LOADING_RE = re.compile(r"starting chat|iniciando|loading|carregando|cargando", re.I)


def _profile():
    """The persistent WhatsApp Web profile (shared by every sender window)."""
    from PySide6.QtWebEngineCore import QWebEngineProfile

    app = QApplication.instance()
    existing = getattr(app, "_maplead_wa_profile", None)
    if existing is not None:
        return existing
    profile = QWebEngineProfile("maplead-whatsapp", app)
    storage = paths.ensure_dir(os.path.join(paths.data_dir(), "whatsapp-web"))
    profile.setPersistentStoragePath(storage)
    profile.setCachePath(os.path.join(storage, "cache"))
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
    # WhatsApp Web refuses browsers it does not recognise; drop the Qt token so
    # the engine presents itself as the Chromium it really is.
    agent = re.sub(r"\s*QtWebEngine/\S+", "", profile.httpUserAgent())
    profile.setHttpUserAgent(agent)
    app._maplead_wa_profile = profile
    return profile


# --------------------------------------------------------------------------- #
# setup dialog: pick the leads and the safety settings
# --------------------------------------------------------------------------- #

class BulkSendDialog(QDialog):
    """Review the queue, tick who gets the message, then start."""

    COL_CHECK, COL_NAME, COL_NUMBER, COL_STATUS = range(4)

    def __init__(self, leads: Sequence[Dict[str, Any]], palette: Palette, *,
                 dial: str = "", country_code: str = "",
                 filter_label: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.p = palette
        self._dial = dial
        self._iso = (country_code or "").lower()
        self._leads = list(leads)
        self.history = outreach.History()
        self.safety = load_safety()
        self.items: List[outreach.OutreachItem] = []
        self.selected: List[outreach.OutreachItem] = []

        self.setWindowTitle("MAPLEAD — bulk WhatsApp")
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
        title = QLabel("BULK WHATSAPP")
        title.setObjectName("panelTitle")
        titles.addWidget(title)
        self.sub_label = QLabel("")
        self.sub_label.setObjectName("panelSub")
        titles.addWidget(self.sub_label)
        hl.addLayout(titles)
        hl.addStretch(1)
        message_btn = QPushButton("  Edit message")
        message_btn.setIcon(icons.icon("chat", self.p.text_dim, 15))
        message_btn.clicked.connect(self._edit_template)
        hl.addWidget(message_btn)
        root.addWidget(header)
        self._filter_label = filter_label

        # leads + preview ------------------------------------------------------
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)

        leads_card, lc = card("Leads to message")
        tools = QHBoxLayout()
        tools.setSpacing(6)
        for label, mode in (("All", "all"), ("None", "none"),
                            ("Not contacted", "new")):
            button = QPushButton(label)
            button.setProperty("flat", True)
            button.clicked.connect(lambda _=False, m=mode: self._tick(m))
            tools.addWidget(button)
        tools.addStretch(1)
        lc.addLayout(tools)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "Business", "WhatsApp", "History"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(self.COL_CHECK, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(self.COL_NAME, QHeaderView.Stretch)
        head.setSectionResizeMode(self.COL_NUMBER, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeToContents)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.currentCellChanged.connect(lambda *_: self._sync_preview())
        lc.addWidget(self.table, 1)
        split.addWidget(leads_card)

        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(12)

        preview_card, pc = card("Message preview")
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(110)
        pc.addWidget(self.preview)
        sl.addWidget(preview_card, 1)

        safety_card, sc = card("Safety")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        s = self.safety
        self.min_delay = self._spin(5, 3600, s.min_delay, " s")
        self.max_delay = self._spin(5, 3600, s.max_delay, " s")
        self.burst_size = self._spin(0, 500, s.burst_size, " msgs")
        self.burst_rest = self._spin(0, 240, s.burst_rest // 60, " min")
        self.warn_after = self._spin(0, 1000, s.warn_after, " msgs")
        self.daily_limit = self._spin(0, 2000, s.daily_limit, " msgs")
        rows = (
            ("Pause from", self.min_delay, "Shortest random pause between two messages"),
            ("Pause up to", self.max_delay, "Longest random pause between two messages"),
            ("Rest every", self.burst_size, "After this many messages, take a longer rest (0 = never)"),
            ("Rest for", self.burst_rest, "Length of that rest"),
            ("Ask after", self.warn_after,
             "Stop and ask whether to continue every time this many messages went out (0 = never)"),
            ("Daily limit", self.daily_limit,
             "Ask before going over this many messages today (0 = no limit)"),
        )
        for i, (label, spin, tip) in enumerate(rows):
            grid.addWidget(field_label(label, tip), i // 2, (i % 2) * 2)
            spin.setToolTip(tip)
            spin.valueChanged.connect(self._sync_footer)
            grid.addWidget(spin, i // 2, (i % 2) * 2 + 1)
        sc.addLayout(grid)
        risk = QLabel("Automated messages go against WhatsApp's terms. The pauses "
                      "lower the risk of the number being restricted, they do not "
                      "remove it — prefer a number used only for prospecting.")
        risk.setObjectName("hint")
        risk.setWordWrap(True)
        sc.addWidget(risk)
        sl.addWidget(safety_card)
        split.addWidget(side)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([640, 420])
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
        self.start_btn = QPushButton("  Start sending")
        self.start_btn.setProperty("accent", True)
        self.start_btn.setIcon(icons.icon("play", self.p.accent_text, 13))
        self.start_btn.clicked.connect(self.accept)
        footer.addWidget(self.start_btn)
        root.addLayout(footer)

        self._fill()

    # -- building -------------------------------------------------------------
    @staticmethod
    def _spin(lo: int, hi: int, value: int, suffix: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(max(lo, min(hi, int(value))))
        spin.setSuffix(suffix)
        return spin

    def _template(self) -> str:
        from .lead_panel import load_message_template
        return load_message_template()

    def _fill(self) -> None:
        self.items = outreach.build_queue(
            self._leads, self._template(), dial=self._dial, iso=self._iso,
            history=self.history, skip_contacted=False)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check.setCheckState(Qt.Unchecked if item.contacted else Qt.Checked)
            self.table.setItem(row, self.COL_CHECK, check)
            name_cell = QTableWidgetItem(item.name)
            name_cell.setToolTip(item.name)
            self.table.setItem(row, self.COL_NAME, name_cell)
            self.table.setItem(row, self.COL_NUMBER, QTableWidgetItem("+" + item.number))
            entry = self.history.get(item.number)
            if entry and item.contacted:
                when = (entry.last_sent or entry.first_sent or entry.at)[:10]
                text = f"Contacted {when[8:10]}/{when[5:7]}" if len(when) == 10 else "Contacted"
            elif entry:
                text = outreach.STATUS_LABELS.get(entry.status, entry.status)
            else:
                text = "New"
            status = QTableWidgetItem(text)
            if item.contacted:
                status.setForeground(self.p.c("warning"))
            elif entry:
                status.setForeground(self.p.c("text_dim"))
            self.table.setItem(row, self.COL_STATUS, status)
        self.table.blockSignals(False)
        if self.items:
            self.table.setCurrentCell(0, self.COL_NAME)
        skipped = len(self._leads) - len(self.items)
        contacted = sum(1 for i in self.items if i.contacted)
        parts = [self._filter_label or "current filter",
                 f"{len(self.items)} with WhatsApp"]
        if contacted:
            parts.append(f"{contacted} already contacted")
        if skipped:
            parts.append(f"{skipped} without a usable number / duplicates")
        self.sub_label.setText(" · ".join(parts))
        self._sync_preview()
        self._sync_footer()

    # -- interaction ------------------------------------------------------------
    def _tick(self, mode: str) -> None:
        self.table.blockSignals(True)
        for row, item in enumerate(self.items):
            on = (mode == "all") or (mode == "new" and not item.contacted)
            self.table.item(row, self.COL_CHECK).setCheckState(
                Qt.Checked if on else Qt.Unchecked)
        self.table.blockSignals(False)
        self._sync_footer()

    def _on_item_changed(self, cell: QTableWidgetItem) -> None:
        if cell.column() == self.COL_CHECK:
            self._sync_footer()

    def _checked(self) -> List[outreach.OutreachItem]:
        return [item for row, item in enumerate(self.items)
                if self.table.item(row, self.COL_CHECK).checkState() == Qt.Checked]

    def _sync_preview(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.items):
            item = self.items[row]
            self.preview.setPlainText(
                f"To: {item.name}  (+{item.number})\n\n"
                + (item.message or "(empty message)"))
        else:
            self.preview.setPlainText("No lead with a WhatsApp number in this filter.")

    def current_safety(self) -> outreach.SafetySettings:
        return outreach.SafetySettings(
            min_delay=self.min_delay.value(),
            max_delay=self.max_delay.value(),
            burst_size=self.burst_size.value(),
            burst_rest=self.burst_rest.value() * 60,
            warn_after=self.warn_after.value(),
            daily_limit=self.daily_limit.value(),
        ).normalized()

    def _sync_footer(self, *_: Any) -> None:
        chosen = self._checked()
        safety = self.current_safety()
        today = self.history.sent_today()
        limit = f"/{safety.daily_limit}" if safety.daily_limit else ""
        eta = outreach.format_duration(outreach.estimate_seconds(len(chosen), safety))
        text = (f"{len(chosen)} selected · sent today {today}{limit} · "
                f"about {eta} with these pauses")
        if safety.daily_limit and today + len(chosen) > safety.daily_limit:
            text += " · goes over the daily limit (you will be asked)"
        self.summary.setText(text)
        self.start_btn.setEnabled(bool(chosen))

    def _edit_template(self) -> None:
        from .lead_panel import WhatsAppTemplateDialog
        dialog = WhatsAppTemplateDialog(self._leads, self.p, parent=self)
        if dialog.exec() == QDialog.Accepted:
            ticks = {item.number: self.table.item(row, self.COL_CHECK).checkState()
                     for row, item in enumerate(self.items)}
            self._fill()
            self.table.blockSignals(True)
            for row, item in enumerate(self.items):
                if item.number in ticks:
                    self.table.item(row, self.COL_CHECK).setCheckState(ticks[item.number])
            self.table.blockSignals(False)
            self._sync_footer()

    def accept(self) -> None:  # noqa: D102 (Qt API)
        self.selected = self._checked()
        if not self.selected:
            return
        self.safety = self.current_safety()
        save_safety(self.safety)
        super().accept()


# --------------------------------------------------------------------------- #
# the sender
# --------------------------------------------------------------------------- #

class WhatsAppSenderWindow(QDialog):
    """WhatsApp Web inside MAPLEAD, sending the queue with safety pauses."""

    history_changed = Signal()

    # states of the one-second loop
    IDLE, LOGIN, OPENING, VERIFYING, WAITING, DONE = (
        "idle", "login", "opening", "verifying", "waiting", "done")

    def __init__(self, items: Sequence[outreach.OutreachItem],
                 safety: outreach.SafetySettings, palette: Palette, *,
                 history: Optional[outreach.History] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self.p = palette
        self.items: List[outreach.OutreachItem] = list(items)
        for item in self.items:
            item.status = ""
        self.safety = safety.normalized()
        self.pacer = outreach.Pacer(self.safety)
        self.history = history or outreach.History()

        self._state = self.IDLE
        self._index = -1                 # item being handled
        self._elapsed = 0                # seconds in the current state
        self._remaining = 0              # countdown while WAITING
        self._wait_reason = ""
        self._sent_run = 0
        self._paused = False
        self._probing = False
        self._daily_ok = False           # user agreed to go over the cap
        self._enter_tried = False
        self._loaded = False             # the current lead's page finished loading

        self.setWindowTitle("MAPLEAD — WhatsApp sender")
        self.setModal(False)
        self.setMinimumSize(1100, 700)
        self.resize(1320, 860)
        self.setSizeGripEnabled(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint
                            | Qt.WindowCloseButtonHint)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        self.view = QWebEngineView(self)
        self.page = QWebEnginePage(_profile(), self.view)
        self.view.setPage(self.page)
        self.page.loadStarted.connect(lambda: setattr(self, "_loaded", False))
        self.page.loadFinished.connect(lambda ok: setattr(self, "_loaded", True))
        root.addWidget(self.view, 1)

        side = QWidget()
        side.setFixedWidth(340)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(12)

        status_card, stc = card("Bulk send")
        self.state_label = QLabel("")
        self.state_label.setObjectName("panelTitle")
        self.state_label.setWordWrap(True)
        stc.addWidget(self.state_label)
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("hint")
        self.detail_label.setWordWrap(True)
        stc.addWidget(self.detail_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, max(1, len(self.items)))
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        stc.addWidget(self.progress)
        self.counts_label = QLabel("")
        self.counts_label.setObjectName("hint")
        stc.addWidget(self.counts_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self._toggle_pause)
        buttons.addWidget(self.pause_btn)
        self.skip_btn = QPushButton("Skip lead")
        self.skip_btn.setToolTip("Do not message the current lead; go to the next one")
        self.skip_btn.clicked.connect(self._skip)
        buttons.addWidget(self.skip_btn)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setProperty("danger", True)
        self.stop_btn.clicked.connect(self._confirm_stop)
        buttons.addWidget(self.stop_btn)
        stc.addLayout(buttons)
        sl.addWidget(status_card)

        log_card, lc = card("Activity")
        self.log = LogPane(self.p)
        lc.addWidget(self.log)
        sl.addWidget(log_card, 1)

        hint = QLabel("Keep this window open while it sends. You can minimise "
                      "it; closing it stops the run. The WhatsApp session is "
                      "kept for next time.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        sl.addWidget(hint)
        root.addWidget(side)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

        self._sync_counts()
        self.log.write(f"{len(self.items)} lead(s) queued · pause "
                       f"{self.safety.min_delay}-{self.safety.max_delay} s · rest "
                       f"{self.safety.burst_rest // 60} min every "
                       f"{self.safety.burst_size or '∞'} · ask after "
                       f"{self.safety.warn_after or '∞'}", "info")

    # -- lifecycle ------------------------------------------------------------
    def start(self) -> None:
        self._set_state(self.LOGIN, "Opening WhatsApp Web…",
                        "If a QR code shows up, scan it with WhatsApp on your "
                        "phone (Linked devices). This is needed only once.")
        self.page.load(QUrl(WHATSAPP_WEB))
        self.timer.start()

    def _set_state(self, state: str, title: str = "", detail: str = "") -> None:
        self._state = state
        self._elapsed = 0
        if title:
            self.state_label.setText(title)
        self.detail_label.setText(detail)
        running = state not in (self.DONE, self.IDLE)
        self.pause_btn.setEnabled(running)
        self.skip_btn.setEnabled(state in (self.OPENING, self.VERIFYING, self.WAITING))
        self.stop_btn.setEnabled(running)

    def _sync_counts(self) -> None:
        c = outreach.counts(self.items)
        done = sum(c.values())
        self.progress.setValue(done)
        self.counts_label.setText(
            f"{done}/{len(self.items)} done · sent {c[outreach.SENT]} · "
            f"not on WhatsApp {c[outreach.INVALID]} · failed {c[outreach.FAILED]}"
            + (f" · skipped {c[outreach.SKIPPED]}" if c[outreach.SKIPPED] else ""))

    def _current(self) -> Optional[outreach.OutreachItem]:
        if 0 <= self._index < len(self.items):
            return self.items[self._index]
        return None

    # -- the loop ---------------------------------------------------------------
    def _tick(self) -> None:
        if self._state == self.WAITING:
            if self._paused:
                self.detail_label.setText(
                    f"Paused · next lead in {outreach.format_duration(self._remaining)}")
                return
            self._remaining -= 1
            nxt = self._next_index()
            who = self.items[nxt].name if nxt is not None else ""
            self.detail_label.setText(
                f"{self._wait_reason.capitalize()} · next: {who} in "
                f"{outreach.format_duration(self._remaining)}")
            if self._remaining <= 0:
                self._open_next()
            return
        if self._state in (self.LOGIN, self.OPENING, self.VERIFYING):
            self._elapsed += 1
            # never probe the previous lead's page while the next one loads
            if self._state == self.OPENING and not self._loaded:
                if self._elapsed >= OPEN_TIMEOUT:
                    self._finish(outreach.FAILED, "WhatsApp Web did not load")
                return
            if not self._probing:
                self._probing = True
                self.page.runJavaScript(_JS_PROBE, 0, self._on_probe)

    def _on_probe(self, raw: Any) -> None:
        self._probing = False
        try:
            info = json.loads(raw) if isinstance(raw, str) else {}
        except ValueError:
            info = {}
        state = self._state

        if state == self.LOGIN:
            if info.get("logged"):
                self.log.write("WhatsApp Web is ready", "ok")
                self._open_next()
            elif info.get("qr"):
                self.state_label.setText("Scan the QR code")
                self.detail_label.setText(
                    "On your phone: WhatsApp → Settings → Linked devices → "
                    "Link a device. Sending starts by itself once you are in.")
            return

        item = self._current()
        if item is None:
            return

        if state == self.OPENING:
            dialog = str(info.get("dialog") or "")
            if dialog and _INVALID_RE.search(dialog) and not _LOADING_RE.search(dialog):
                self._finish(outreach.INVALID)
            elif info.get("send"):
                self.page.runJavaScript(_JS_CLICK_SEND, 0, self._on_clicked)
            elif info.get("qr") and not info.get("logged"):
                self.log.write("WhatsApp Web logged out — scan the QR code again", "warn")
                self._index -= 1
                self._set_state(self.LOGIN, "Scan the QR code", "Session expired.")
            elif self._elapsed >= OPEN_TIMEOUT:
                self._finish(outreach.FAILED, "the chat did not open in time")
            return

        if state == self.VERIFYING:
            composer = info.get("composer", -1)
            if composer == 0 and not info.get("send"):
                self._finish(outreach.SENT)
            elif self._elapsed >= VERIFY_TIMEOUT:
                self._finish(outreach.FAILED, "WhatsApp did not confirm the send")
            elif self._elapsed >= ENTER_FALLBACK_AT and not self._enter_tried:
                self._enter_tried = True
                self.page.runJavaScript(_JS_FOCUS_COMPOSER, 0,
                                        lambda ok: self._press_enter() if ok else None)

    def _on_clicked(self, ok: Any) -> None:
        if self._state != self.OPENING:
            return
        if ok:
            self._enter_tried = False
            item = self._current()
            self._set_state(self.VERIFYING, f"Sending to {item.name if item else ''}…",
                            "Waiting for WhatsApp to confirm.")

    def _press_enter(self) -> None:
        target = self.view.focusProxy() or self.view
        for kind in (QEvent.KeyPress, QEvent.KeyRelease):
            QApplication.sendEvent(target, QKeyEvent(kind, Qt.Key_Return,
                                                     Qt.NoModifier, "\r"))

    def _next_index(self) -> Optional[int]:
        nxt = self._index + 1
        return nxt if nxt < len(self.items) else None

    def _open_next(self) -> None:
        nxt = self._next_index()
        if nxt is None:
            self._done("All leads handled")
            return
        # daily cap: ask once per run before going over it
        if (not self._daily_ok
                and self.pacer.over_daily_limit(self.history.sent_today())):
            self.timer.stop()
            answer = QMessageBox.question(
                self, "Daily limit reached",
                f"{self.history.sent_today()} messages were already sent today "
                f"(your limit is {self.safety.daily_limit}).\n\n"
                "Going over it raises the chance of WhatsApp restricting or "
                "blocking this number.\n\nContinue anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                self._done("Stopped at the daily limit")
                return
            self._daily_ok = True
            self.log.write("Daily limit passed — continuing on your confirmation", "warn")
            self.timer.start()

        self._index = nxt
        item = self.items[nxt]
        from .lead_panel import load_message_template
        # rendered now, so {saudacao} matches the time it is actually sent
        item.message = contacts.render_template(load_message_template(), item.lead)
        url = (f"{WHATSAPP_SEND}?phone={item.number}"
               f"&text={quote(item.message, safe='')}")
        self._set_state(self.OPENING, f"Opening {item.name}",
                        f"+{item.number} · lead {nxt + 1} of {len(self.items)}")
        self.log.write(f"→ {item.name} (+{item.number})", "query")
        self._loaded = False
        self.page.load(QUrl(url))

    def _finish(self, status: str, error: str = "") -> None:
        item = self._current()
        if item is None:
            return
        item.status = status
        try:
            self.history.record(item.number, status, name=item.name,
                                error=error, lead=item.lead)
        except OSError as exc:
            self.log.write(f"Could not save the history: {exc}", "error")
        self.history_changed.emit()
        label = outreach.STATUS_LABELS.get(status, status)
        level = {outreach.SENT: "ok", outreach.INVALID: "warn",
                 outreach.SKIPPED: "info"}.get(status, "error")
        self.log.write(f"   {label}" + (f" — {error}" if error else ""), level)
        self._sync_counts()

        if self._next_index() is None:
            self._done("All leads handled")
            return

        if status == outreach.SENT:
            self._sent_run += 1
            if self.pacer.needs_warning(self._sent_run):
                self.timer.stop()
                answer = QMessageBox.question(
                    self, "Keep sending?",
                    f"{self._sent_run} messages were sent in this run.\n\n"
                    "After this many messages WhatsApp may restrict or block "
                    "the number. Do you want to continue?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if answer != QMessageBox.Yes:
                    self._done(f"Stopped after {self._sent_run} messages")
                    return
                self.log.write("Continuing on your confirmation", "warn")
                self.timer.start()
            delay, reason = self.pacer.delay_after(self._sent_run)
        else:
            delay, reason = self.pacer.short_delay(), "short pause"
        self._remaining = delay
        self._wait_reason = reason
        self._set_state(self.WAITING, "Waiting" if not self._paused else "Paused", "")
        if reason.startswith("rest"):
            self.log.write(f"Resting {outreach.format_duration(delay)} "
                           f"({reason})", "info")

    def _done(self, title: str) -> None:
        self.timer.stop()
        c = outreach.counts(self.items)
        self._set_state(self.DONE, title,
                        f"Sent {c[outreach.SENT]} · not on WhatsApp "
                        f"{c[outreach.INVALID]} · failed {c[outreach.FAILED]}. "
                        "The history is saved; these numbers are skipped next time.")
        self.log.write(title, "ok")
        self.pause_btn.setText("Pause")
        self._paused = False

    # -- controls -----------------------------------------------------------------
    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_btn.setText("Resume" if self._paused else "Pause")
        if self._paused:
            self.log.write("Paused — the current lead finishes, then it waits", "warn")
            if self._state == self.WAITING:
                self.state_label.setText("Paused")
        else:
            self.log.write("Resumed", "info")
            if self._state == self.WAITING:
                self.state_label.setText("Waiting")

    def _skip(self) -> None:
        if self._state in (self.OPENING, self.VERIFYING):
            self._finish(outreach.SKIPPED, "skipped by you")
        elif self._state == self.WAITING:
            nxt = self._next_index()
            if nxt is None:
                return
            self._index = nxt
            self._finish(outreach.SKIPPED, "skipped by you")

    def is_running(self) -> bool:
        return self._state not in (self.IDLE, self.DONE)

    def _confirm_stop(self) -> bool:
        if not self.is_running():
            return True
        answer = QMessageBox.question(
            self, "Stop sending?",
            "Stop the bulk send? Leads not reached yet stay unmarked and can be "
            "sent later.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._done("Stopped by you")
            return True
        return False

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self.is_running() and not self._confirm_stop():
            event.ignore()
            return
        self.timer.stop()
        self.page.load(QUrl("about:blank"))
        super().closeEvent(event)


def open_bulk_sender(leads: Sequence[Dict[str, Any]], palette: Palette, *,
                     dial: str = "", country_code: str = "",
                     filter_label: str = "",
                     parent: Optional[QWidget] = None
                     ) -> Optional[WhatsAppSenderWindow]:
    """Setup dialog → sender window. Returns the window (or None if cancelled)."""
    if not webengine_available():
        QMessageBox.warning(
            parent, "Bulk WhatsApp",
            "This build of MAPLEAD has no web engine (QtWebEngine), which bulk "
            "sending needs to run WhatsApp Web.\n\nInstall PySide6-WebEngine or "
            "use a release build that includes it.")
        return None
    dialog = BulkSendDialog(leads, palette, dial=dial, country_code=country_code,
                            filter_label=filter_label, parent=parent)
    if not dialog.items:
        QMessageBox.information(
            parent, "Bulk WhatsApp",
            "None of the leads in this filter has a phone number that can be "
            "opened in WhatsApp.")
        return None
    if dialog.exec() != QDialog.Accepted or not dialog.selected:
        return None
    window = WhatsAppSenderWindow(dialog.selected, dialog.safety, palette,
                                  history=dialog.history, parent=parent)
    window.setAttribute(Qt.WA_DeleteOnClose, True)
    window.show()
    window.start()
    return window
