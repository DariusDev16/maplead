"""
Reusable GUI pieces: cards, stat tiles, a keyboard-filterable combo, the field
picker dialog, the results table model and the activity log.
"""

from __future__ import annotations

import html
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QSortFilterProxyModel,
                            Qt, Signal)
from PySide6.QtGui import QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QDialog,
                               QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSizePolicy, QTableView, QTextEdit, QVBoxLayout,
                               QWidget)

from ..data import fields as FD
from .theme import Palette

_ANY = object()


# --------------------------------------------------------------------------- #
# small building blocks
# --------------------------------------------------------------------------- #

def card(title: str = "", parent: Optional[QWidget] = None) -> Tuple[QFrame, QVBoxLayout]:
    frame = QFrame(parent)
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 11, 14, 13)
    lay.setSpacing(8)
    if title:
        lbl = QLabel(title.upper())
        lbl.setObjectName("cardTitle")
        lay.addWidget(lbl)
    return frame, lay


def field_label(text: str, tip: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("fieldLabel")
    if tip:
        lbl.setToolTip(tip)
    return lbl


def hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("hint")
    lbl.setWordWrap(True)
    return lbl


def supports(provider: str, field_key: str) -> bool:
    """Can `provider` return `field_key`? (same rule the CLI and engine use)"""
    meta = FD.BY_KEY.get(field_key)
    return bool(meta and provider in meta.providers)


def separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet("background: palette(border); border: none;")
    return line


class StatCard(QFrame):
    """Big number + caption, used across the results header."""

    def __init__(self, label: str, value: str = "-", sub: str = "",
                 palette: Optional[Palette] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self._label = label
        self._value = QLabel(value)
        self._value.setObjectName("statValue")
        self._sub = QLabel(sub)
        self._sub.setObjectName("statLabel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(2)
        cap = QLabel(label.upper())
        cap.setObjectName("statLabel")
        lay.addWidget(cap)
        lay.addWidget(self._value)
        lay.addWidget(self._sub)
        self.setMinimumWidth(112)

    def set(self, value: str, sub: str = "") -> None:
        self._value.setText(value)
        self._sub.setText(sub)

    def set_accent(self, color: str) -> None:
        self._value.setStyleSheet(f"color: {color};")


# --------------------------------------------------------------------------- #
# combo boxes
# --------------------------------------------------------------------------- #

class SearchCombo(QComboBox):
    """
    Read-only combo you narrow down by typing (the terminal CLI lists in
    columns; on screen a filtered popup is the equivalent).

    Type to filter, Backspace to widen the search, Enter/Esc to finish.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._entries: List[Tuple[str, Any]] = []
        self._buffer = ""
        self.setModel(QStandardItemModel(self))
        self.setInsertPolicy(QComboBox.NoInsert)
        self.view().setUniformItemSizes(True)

    # -- data ---------------------------------------------------------------
    def setEntries(self, entries: Sequence[Tuple[str, Any]]) -> None:
        self._entries = list(entries)
        self._buffer = ""
        self._fill(self._entries)
        if self._entries:
            self.setCurrentIndex(0)

    def _fill(self, entries: Sequence[Tuple[str, Any]]) -> None:
        model = QStandardItemModel(self)
        for label, _ in entries:
            item = QStandardItem(label)
            item.setEditable(False)
            model.appendRow(item)
        self.setModel(model)

    def entries(self) -> List[Tuple[str, Any]]:
        return list(self._entries)

    def value(self) -> Any:
        if self.currentIndex() < 0 or self.currentIndex() >= len(self._entries):
            return None
        return self._entries[self.currentIndex()][1]

    def setValueByPredicate(self, predicate: Callable[[Any], bool]) -> bool:
        for i, (_, payload) in enumerate(self._entries):
            if predicate(payload):
                self.setCurrentIndex(i)
                return True
        return False

    # -- keyboard filtering --------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.hidePopup()
            return
        if key == Qt.Key_Escape:
            self._buffer = ""
            self._fill(self._entries)
            self.hidePopup()
            return
        text = event.text()
        if key == Qt.Key_Backspace:
            self._buffer = self._buffer[:-1]
            self._apply()
            return
        if key == Qt.Key_Space and not text.strip():
            return
        if text and text.isprintable() and not event.modifiers():
            self._buffer += text
            self._apply()
            return
        super().keyPressEvent(event)

    def _apply(self) -> None:
        needle = self._buffer.strip().lower()
        if not needle:
            self._fill(self._entries)
            return
        hits = [(label, payload) for label, payload in self._entries
                if needle in label.lower()]
        if not hits:                      # fall back to the whole list
            self._fill(self._entries)
            return
        self._fill(hits)
        self.setCurrentIndex(0)
        if not self.view().isVisible():
            self.showPopup()


def editable_combo(items: Sequence[str] = (), parent: Optional[QWidget] = None) -> QComboBox:
    """Editable combo + fuzzy completer, so free text is always allowed."""
    combo = QComboBox(parent)
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.addItems(list(items))
    completer = combo.completer()
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    completer.setFilterMode(Qt.MatchContains)
    completer.setCompletionMode(QCompleter.PopupCompletion)
    line = combo.lineEdit()
    if line is not None:
        line.setPlaceholderText("type anything")
    return combo


PROVIDER_NAMES = {"google": "Google Places", "outscraper": "Outscraper",
                   "serpapi": "SerpApi", "dataforseo": "DataForSEO",
                   "demo": "Demo mode"}


def _needs_label(meta: FD.Field, provider: str) -> str:
    """Why a field is greyed out: the first service that could return it."""
    if meta.enriched and "outscraper" in meta.providers:
        return "Outscraper"
    names = [PROVIDER_NAMES.get(p, p.title()) for p in meta.providers
             if p not in (provider, "demo")]
    return names[0] if names else "n/a"


# --------------------------------------------------------------------------- #
# field picker
# --------------------------------------------------------------------------- #

class FieldPickerDialog(QDialog):
    """Grouped, searchable multi-select over the whole field catalogue."""

    def __init__(self, provider: str, selected: Sequence[str],
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.provider = provider
        self.setWindowTitle("Fields to extract")
        self.setMinimumSize(620, 560)
        self._boxes: Dict[str, QCheckBox] = {}
        self._initial = list(selected)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.search = QLineEdit()
        self.search.setObjectName("searchBox")
        self.search.setPlaceholderText("filter fields…")
        self.search.setClearButtonEnabled(True)
        head.addWidget(self.search, 1)
        for key, label in (("rec", "Recommended"), ("basic", "Basic"),
                           ("sales", "Sales-ready"), ("all", "All"), ("none", "None")):
            btn = QPushButton(label)
            btn.setProperty("flat", True)
            btn.clicked.connect(lambda _=False, k=key: self._preset(k))
            head.addWidget(btn)
        root.addLayout(head)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        self._grid = QVBoxLayout(holder)
        self._grid.setContentsMargins(2, 2, 6, 2)
        self._grid.setSpacing(4)
        self._grids: Dict[str, Tuple[QWidget, QGridLayout]] = {}
        for group in FD.GROUPS:
            keys = [f.key for f in FD.FIELDS if f.group == group]
            head_lbl = field_label(group)
            self._grid.addWidget(head_lbl)
            body = QWidget()
            gl = QGridLayout(body)
            gl.setContentsMargins(6, 2, 0, 6)
            gl.setSpacing(2)
            for i, key in enumerate(keys):
                meta = FD.BY_KEY[key]
                usable = provider in meta.providers
                box = QCheckBox(f"{meta.label}")
                box.setProperty("key", key)
                box.setChecked(key in selected)
                box.setEnabled(usable)
                if not usable:
                    box.setText(f"{meta.label}  ·  {_needs_label(meta, provider)}")
                    box.setToolTip(
                        f"{PROVIDER_NAMES.get(provider, provider)} cannot return this field. "
                        f"Available from: {meta.provider_note}")
                else:
                    tip = meta.note or f"{meta.key} · {meta.kind}"
                    if meta.enriched:
                        tip = f"{tip}  ·  needs Outscraper enrichment (extra credits)"
                    box.setToolTip(tip)
                box.toggled.connect(self._on_toggle)
                gl.addWidget(box, i // 2, i % 2)
                self._boxes[key] = box
            self._grid.addWidget(body)
            self._grids[group] = (body, gl)
        self._grid.addStretch(1)
        self._grid.setSizeConstraint(QVBoxLayout.SetMinimumSize)
        area.setWidget(holder)
        root.addWidget(area, 1)

        self.counter = QLabel("")
        self.counter.setObjectName("hint")
        root.addWidget(self.counter)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Use these fields")
        buttons.button(QDialogButtonBox.Ok).setProperty("accent", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.search.textChanged.connect(self._filter)
        self._sync()

    # -- helpers -------------------------------------------------------------
    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        for key, box in self._boxes.items():
            meta = FD.BY_KEY[key]
            match = not needle or needle in meta.label.lower() or needle in key \
                or needle in meta.group.lower()
            box.setVisible(match)
            if needle:
                body, _ = self._grids[meta.group]
                body.setVisible(any(
                    not self._boxes[k].isHidden()
                    for k in (f.key for f in FD.FIELDS if f.group == meta.group)))

    def _preset(self, key: str) -> None:
        table = {name: keys for name, _, keys in FD.PRESETS}
        wanted: List[str] = [] if key == "none" else list(table.get(key, ()))
        for k, box in self._boxes.items():
            if box.isEnabled():
                box.setChecked(k in wanted)
        self._sync()

    def _on_toggle(self) -> None:
        self._sync()

    def _sync(self) -> None:
        chosen = self.selected()
        avail = sum(1 for b in self._boxes.values() if b.isEnabled())
        self.counter.setText(f"{len(chosen)} of {avail} fields selected "
                             f"(columns in the exported file)")

    # -- api -----------------------------------------------------------------
    def selected(self) -> List[str]:
        """Checked fields, in catalogue order."""
        return [f.key for f in FD.FIELDS if self._boxes.get(f.key)
                and self._boxes[f.key].isChecked()]

    def selected_initial(self) -> List[str]:
        return list(self._initial)


# --------------------------------------------------------------------------- #
# results table
# --------------------------------------------------------------------------- #

_LINK_COLUMNS = {"maps_url", "website", "facebook", "instagram", "linkedin",
                 "logo_url", "whatsapp", "phone", "email"}
_NUMERIC = {"rating", "reviews", "photos_count", "employees", "year_established",
            "latitude", "longitude", "distance"}

# short column captions - the catalogue label is too long for a table header
_SHORT_HEADERS = {
    "name": "Business",
    "category": "Category",
    "subcategory": "Subcategory",
    "place_id": "Place ID",
    "maps_url": "Maps link",
    "business_type": "Type",
    "address": "Address",
    "street": "Street",
    "city": "City",
    "region": "Region",
    "postal_code": "Postcode",
    "country_code": "CC",
    "latitude": "Lat",
    "longitude": "Lon",
    "is_chain": "Chain",
    "chain_name": "Brand",
    "logo_url": "Logo",
    "photos_count": "Photos",
    "year_established": "Founded",
    "price_level": "Price",
    "open_now": "Open now",
}

_MIN_WIDTH = {"name": 190, "address": 220, "website": 190, "maps_url": 150,
              "phone": 130, "rating": 120, "category": 140}


def header_label(key: str) -> str:
    return _SHORT_HEADERS.get(key) or key.replace("_", " ").capitalize()


class LeadsModel(QAbstractTableModel):
    """Table model over a list of lead dicts; columns follow the field keys."""

    def __init__(self, columns: Sequence[str], parent=None):
        super().__init__(parent)
        self.columns = list(columns)
        self.leads: List[Dict[str, Any]] = []

    # -- Qt ------------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.leads)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        lead = self.leads[index.row()]
        key = self.columns[index.column()]
        value = lead.get(key)

        if role == Qt.DisplayRole:
            return self._display(key, value)
        if role == Qt.ToolTipRole:
            text = self._display(key, value)
            extra = {
                "maps_url": "Double-click to open in Google Maps",
                "website": "Double-click to open the website",
            }.get(key)
            if not text and value is not None:
                text = str(value)
            return f"{text}{chr(10) + extra if extra else ''}" if text else None
        if role == Qt.TextAlignmentRole:
            if key in _NUMERIC and isinstance(value, (int, float)):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.UserRole:
            return value
        return None

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return header_label(self.columns[section])
        return section + 1

    # -- api -----------------------------------------------------------------
    def set_leads(self, leads: Sequence[Dict[str, Any]], columns: Optional[Sequence[str]] = None):
        self.beginResetModel()
        self.leads = list(leads)
        if columns is not None:
            self.columns = list(columns)
        self.endResetModel()
        self.widths_changed.emit()

    def column_widths(self) -> Dict[int, int]:
        """Size columns to their content, within sane bounds."""
        widths: Dict[int, int] = {}
        for col, key in enumerate(self.columns):
            longest = 0
            for lead in self.leads[:200]:
                longest = max(longest, len(self._display(key, lead.get(key))))
            header = len(header_label(key))
            target = max(longest, header) + 22
            widths[col] = max(_MIN_WIDTH.get(key, 80), min(target, 320))
        return widths

    widths_changed = Signal()

    def clear(self) -> None:
        self.set_leads([], self.columns)

    @staticmethod
    def _display(key: str, value: Any) -> str:
        if value is None:
            return ""
        if key == "rating":
            try:
                stars = "★" * int(float(value))
                return f"{stars} {value}"
            except (TypeError, ValueError):
                return str(value)
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, float):
            return f"{value:g}"
        if isinstance(value, (list, tuple)):
            return ", ".join(str(v) for v in value)[:120]
        if isinstance(value, dict):
            import json
            return json.dumps(value, ensure_ascii=False)[:120]
        return str(value)


class LeadsFilter(QSortFilterProxyModel):
    """Free-text filter across every visible column."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._needle = ""
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def setNeedle(self, needle: str) -> None:  # noqa: N802 (Qt style)
        self._needle = needle.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:  # noqa: N802
        if not self._needle:
            return True
        model = self.sourceModel()
        for col in range(model.columnCount(parent)):
            value = model.data(model.index(row, col, parent), Qt.DisplayRole)
            if value and self._needle in str(value).lower():
                return True
        return False


class LeadsTable(QTableView):
    """Results grid with an empty-state message and sane column defaults."""

    def __init__(self, proxy: "LeadsFilter", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setModel(proxy)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.ExtendedSelection)
        self.setEditTriggers(QTableView.NoEditTriggers)
        self.setWordWrap(False)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(30)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setSectionsClickable(True)
        self.setHorizontalScrollMode(QTableView.ScrollPerPixel)
        self.setVerticalScrollMode(QTableView.ScrollPerPixel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.empty_text = QLabel(
            "No leads yet.\n\nPick a provider, a city and a business type,\n"
            "then press Run search  (Ctrl+R)",
            self.viewport())
        self.empty_text.setAlignment(Qt.AlignCenter)
        self.empty_text.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.empty_text.setStyleSheet("color: palette(mid); font-size: 13px;")

        for signal in (proxy.modelReset, proxy.rowsInserted, proxy.rowsRemoved,
                       proxy.layoutChanged):
            signal.connect(self._sync_placeholder)

    # -- Qt ------------------------------------------------------------------
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_placeholder()

    # -- internals -----------------------------------------------------------
    def _sync_placeholder(self) -> None:
        model = self.model()
        empty = model is None or model.rowCount() == 0
        self.empty_text.setGeometry(self.viewport().rect())
        self.empty_text.setVisible(empty and self.isVisibleTo(self.parentWidget()))

    def set_empty_text(self, text: str) -> None:
        self.empty_text.setText(text)
        self._sync_placeholder()


def build_table(model: LeadsModel, proxy: LeadsFilter) -> LeadsTable:
    return LeadsTable(proxy)


# --------------------------------------------------------------------------- #
# activity log
# --------------------------------------------------------------------------- #

class LogPane(QWidget):
    """Timestamped, colour-coded activity feed."""

    LEVEL_COLORS = {
        "info": "text_dim",
        "ok": "success",
        "warn": "warning",
        "error": "danger",
        "query": "accent",
    }

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.palette_ = palette
        self.view = QTextEdit()
        self.view.setObjectName("log")
        self.view.setReadOnly(True)
        self.view.document().setMaximumBlockCount(600)
        font = QFont("monospace")
        font.setStyleHint(QFont.Monospace)
        self.view.setFont(font)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)

    def write(self, message: str, level: str = "info") -> None:
        import datetime
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        color = getattr(self.palette_, self.LEVEL_COLORS.get(level, "text_dim"))
        self.view.append(
            f'<div style="white-space:pre-wrap"><span style="color:{self.palette_.text_dim}">'
            f'{stamp}</span> <span style="color:{color}">{html.escape(str(message))}</span></div>')

    def clear(self) -> None:
        self.view.clear()


def elide(text: str, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def open_in_desktop(path_or_url: str) -> bool:
    """Hand a URL or file to the desktop's default handler."""
    import subprocess
    import sys
    try:
        if sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", path_or_url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path_or_url])
        else:  # pragma: no cover - windows fallback
            os_startfile(path_or_url)
        return True
    except Exception:
        return False


def os_startfile(path: str) -> None:  # pragma: no cover
    import os
    os.startfile(path)  # type: ignore[attr-defined]
