"""
The leads panel: the results as cards instead of a grid or a spreadsheet.

Opened from the results header (or ``Ctrl+P``), it renders every field the user
selected as a readable card — links open with one click, and each phone number
gets a WhatsApp button that starts the conversation with a saved message whose
``{nome}`` and friends come from the lead itself.

Design notes:

* cards are built from plain labels and layouts only, so the theme's single
  ``QWidget`` background rule never paints slabs inside a card;
* the list is paged (`PAGE` cards per batch) and the search is debounced, so a
  100k-lead result stays responsive;
* the message template lives in ``QSettings`` (same store as the window state).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote, urlsplit

from PySide6.QtCore import QRectF, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QGuiApplication, QPainter,
                           QPainterPath, QTextCursor)
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from .. import contacts
from ..data import fields as FD
from . import icons
from .theme import Palette
from .widgets import display_value, header_label, open_in_desktop

_SETTINGS_ORG = "maplead"
_SETTINGS_APP = "maplead-desktop"
_TEMPLATE_KEY = "whatsapp/message_template"

FILTERS: Tuple[Tuple[str, str], ...] = (
    ("all", "All leads"),
    ("wa", "Has WhatsApp"),
    ("phone", "Has phone"),
    ("site", "Has website"),
    ("nos", "No website"),
    ("email", "Has e-mail"),
)

SORTS: Tuple[Tuple[str, str], ...] = (
    ("source", "Original order"),
    ("rating", "Top rating"),
    ("reviews", "Most reviews"),
    ("name", "Name A-Z"),
)

# --------------------------------------------------------------------------- #
# message template storage
# --------------------------------------------------------------------------- #

def load_message_template() -> str:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    value = settings.value(_TEMPLATE_KEY, None)
    if value is None:
        return contacts.DEFAULT_TEMPLATE
    return str(value)


def save_message_template(text: str) -> None:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.setValue(_TEMPLATE_KEY, text)
    settings.sync()


# --------------------------------------------------------------------------- #
# small widgets
# --------------------------------------------------------------------------- #

class ClickableLabel(QLabel):
    """A label that behaves like a link (mouse and keyboard)."""

    clicked = Signal()

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class RatingBar(QWidget):
    """Five rounded segments; the filled part follows the rating exactly."""

    def __init__(self, rating: Any, palette: Palette,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        try:
            self.rating = float(rating)
        except (TypeError, ValueError):
            self.rating = 0.0
        self.p = palette
        self.setFixedSize(96, 9)
        self.setToolTip(f"{self.rating:.1f} / 5" if self.rating else "no rating")

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        segment, gap = 16.0, 4.0
        base = QColor(self.p.border)
        fill = QColor(self.p.accent)
        painter.setPen(Qt.NoPen)
        for i in range(5):
            x = i * (segment + gap)
            rect = QRectF(x, 0.0, segment, float(self.height()))
            painter.setBrush(base)
            painter.drawRoundedRect(rect, 3.0, 3.0)
            fraction = max(0.0, min(1.0, self.rating - i))
            if fraction <= 0:
                continue
            path = QPainterPath()
            path.addRoundedRect(rect, 3.0, 3.0)
            painter.save()
            painter.setClipPath(path)
            painter.setBrush(fill)
            painter.drawRect(QRectF(x, 0.0, segment * fraction, float(self.height())))
            painter.restore()


def chip(text: str, tone: str = "") -> QLabel:
    label = QLabel(text)
    label.setProperty("chip", True)
    if tone:
        label.setProperty("tone", tone)
    return label


def _icon_label(name: str, color: str, size: int = 14) -> QLabel:
    label = QLabel()
    label.setPixmap(icons.pixmap(name, color, size))
    label.setFixedSize(size + 1, size + 1)
    return label


def _host(url: str) -> str:
    try:
        host = urlsplit(str(url)).netloc
    except ValueError:
        host = ""
    return host[4:] if host.startswith("www.") else (host or str(url))


def _plain(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("leadValue")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


# --------------------------------------------------------------------------- #
# message template dialog
# --------------------------------------------------------------------------- #

class WhatsAppTemplateDialog(QDialog):
    """Write the first message once; placeholders come from the lead."""

    def __init__(self, leads: Sequence[Dict[str, Any]], palette: Palette,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.p = palette
        self.setWindowTitle("WhatsApp first message")
        self.setMinimumSize(680, 560)
        self._leads = [lead for lead in leads if lead.get("name")][:60]

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(10)

        hint_text = ("Pre-filled every time you open a lead in WhatsApp. Write the "
                     "message once here; placeholders are filled from the search "
                     "result (never from WhatsApp), so the business name is always "
                     "the one the scrape returned.")
        hint = QLabel(hint_text)
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Type your message…")
        self.editor.setPlainText(load_message_template())
        self.editor.moveCursor(QTextCursor.End)
        self.editor.setMinimumHeight(110)
        self.editor.setMaximumHeight(180)
        self.editor.textChanged.connect(self._sync)
        root.addWidget(self.editor)

        tokens_caption = QLabel("PLACEHOLDERS — click to insert")
        tokens_caption.setObjectName("cardTitle")
        root.addWidget(tokens_caption)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        for i, (token, description) in enumerate(contacts.PLACEHOLDERS):
            button = QPushButton("{" + token + "}")
            button.setProperty("flat", True)
            button.setToolTip(description)
            button.clicked.connect(
                lambda _=False, t=token: self._insert("{" + t + "}"))
            grid.addWidget(button, i // 4, i % 4)
        root.addLayout(grid)

        preview_row = QHBoxLayout()
        preview_caption = QLabel("PREVIEW")
        preview_caption.setObjectName("cardTitle")
        preview_row.addWidget(preview_caption)
        preview_row.addStretch(1)
        self.sample_combo = QComboBox()
        for index, lead in enumerate(self._leads):
            self.sample_combo.addItem(str(lead.get("name") or f"Lead {index + 1}"),
                                      index)
        if not self._leads:
            self.sample_combo.addItem("(no lead in this result)", -1)
            self.sample_combo.setEnabled(False)
        self.sample_combo.currentIndexChanged.connect(self._sync)
        preview_row.addWidget(self.sample_combo)
        root.addLayout(preview_row)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(80)
        self.preview.setMaximumHeight(140)
        root.addWidget(self.preview)

        self.warning = QLabel("")
        self.warning.setObjectName("hint")
        self.warning.setWordWrap(True)
        root.addWidget(self.warning)

        buttons = QHBoxLayout()
        reset = QPushButton("Restore default")
        reset.setProperty("flat", True)
        reset.clicked.connect(self._reset)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Save message")
        save.setProperty("accent", True)
        save.clicked.connect(self.accept)
        buttons.addWidget(save)
        root.addLayout(buttons)

        self._sync()

    # -- helpers -------------------------------------------------------------
    def _sample(self) -> Dict[str, Any]:
        index = self.sample_combo.currentData()
        if isinstance(index, int) and 0 <= index < len(self._leads):
            return self._leads[index]
        return {
            "name": "Padaria São João", "category": "Padaria", "city": "São Paulo",
            "region": "SP", "country": "Brazil", "address": "Rua Augusta, 100",
            "phone": "+55 11 91234-5678", "website": "https://exemplo.com",
            "email": "contato@exemplo.com", "rating": 4.7, "reviews": 128,
        }

    def _insert(self, token: str) -> None:
        self.editor.insertPlainText(token)
        self.editor.setFocus()

    def _reset(self) -> None:
        self.editor.setPlainText(contacts.DEFAULT_TEMPLATE)
        self.editor.moveCursor(QTextCursor.End)

    def _sync(self) -> None:
        template = self.editor.toPlainText()
        rendered = contacts.render_template(template, self._sample())
        self.preview.setPlainText(rendered or "(empty message — WhatsApp opens "
                                             "with no text)")
        unknown = contacts.unknown_placeholders(template)
        if unknown:
            self.warning.setText(
                "⚠  Unknown placeholder(s) kept as-is: "
                + ", ".join("{" + u + "}" for u in unknown))
            self.warning.setStyleSheet(f"color: {self.p.warning};")
        else:
            self.warning.setText("")
            self.warning.setStyleSheet("")

    def template(self) -> str:
        return self.editor.toPlainText().strip()

    def accept(self) -> None:  # noqa: D102 (Qt API)
        save_message_template(self.template())
        super().accept()


# --------------------------------------------------------------------------- #
# the panel
# --------------------------------------------------------------------------- #

class LeadsPanel(QDialog):
    """Card view of the harvested leads, with WhatsApp outreach built in."""

    PAGE = 40

    def __init__(self, leads: Sequence[Dict[str, Any]], columns: Sequence[str],
                 palette: Palette, *, dial: str = "", country_code: str = "",
                 subtitle: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.p = palette
        self._leads: List[Dict[str, Any]] = list(leads)
        self._columns: List[str] = list(columns)
        self._dial = dial or ""
        self._iso = (country_code or "").lower()
        self._subtitle = subtitle
        self._template = load_message_template()
        self._filter_key = "all"
        self._limit = self.PAGE
        self._visible: List[Dict[str, Any]] = []
        self._blobs: List[str] = []
        self._has_phone: List[bool] = []
        self._has_wa: List[bool] = []
        self._has_site: List[bool] = []
        self._has_email: List[bool] = []
        self._rendered = 0
        # typing in the search box rebuilds the cards: debounce it
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(lambda: self._apply_filters(reset=True))

        self.setWindowTitle("MAPLEAD — leads panel")
        self.setModal(False)
        self.setMinimumSize(1000, 620)
        self.resize(1180, 800)
        self.setSizeGripEnabled(True)
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowMinMaxButtonsHint
                            | Qt.WindowCloseButtonHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)
        root.addWidget(self._build_header())

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cards_host = QWidget()
        self.cards = QVBoxLayout(self.cards_host)
        self.cards.setContentsMargins(2, 2, 8, 2)
        self.cards.setSpacing(10)
        self.cards.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.cards_host)
        root.addWidget(self.scroll, 1)

        root.addLayout(self._build_footer())

        self._precompute()
        self._apply_filters(reset=True)

    # ------------------------------------------------------------------ UI --
    def _build_header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("panelHeader")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.title_label = QLabel("LEADS PANEL")
        self.title_label.setObjectName("panelTitle")
        titles.addWidget(self.title_label)
        self.sub_label = QLabel(self._subtitle or f"{len(self._leads)} leads")
        self.sub_label.setObjectName("panelSub")
        titles.addWidget(self.sub_label)
        row.addLayout(titles)
        row.addStretch(1)

        message_btn = QPushButton("  WhatsApp message")
        message_btn.setIcon(icons.icon("chat", self.p.text_dim, 15))
        message_btn.setToolTip("Edit the message that opens with every WhatsApp chat")
        message_btn.clicked.connect(self.edit_template)
        row.addWidget(message_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        row.addWidget(close_btn)
        lay.addLayout(row)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.search = QLineEdit()
        self.search.setObjectName("searchBox")
        self.search.setPlaceholderText("search name, address, category…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search_changed)
        row.addWidget(self.search, 1)

        self.sort_combo = QComboBox()
        for key, label in SORTS:
            self.sort_combo.addItem(label, key)
        self.sort_combo.currentIndexChanged.connect(
            lambda _=None: self._apply_filters(reset=True))
        row.addWidget(self.sort_combo)
        lay.addLayout(row)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        for key, label in FILTERS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("chip", True)
            button.setChecked(key == self._filter_key)
            button.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self._chip_group.addButton(button)
            row.addWidget(button)
        row.addStretch(1)
        lay.addLayout(row)
        return frame

    def _build_footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(10)
        self.count_label = QLabel("")
        self.count_label.setObjectName("hint")
        row.addWidget(self.count_label)
        row.addStretch(1)
        self.status_label = QLabel("Links open in your browser · WhatsApp uses the "
                                   "saved message")
        self.status_label.setObjectName("hint")
        row.addWidget(self.status_label)
        self.more_btn = QPushButton("Show more")
        self.more_btn.clicked.connect(self._show_more)
        self.more_btn.setVisible(False)
        row.addWidget(self.more_btn)
        return row

    # ------------------------------------------------------------- data --
    def _precompute(self) -> None:
        dial, iso = self._dial, self._iso
        self._blobs = [
            " ".join(str(lead.get(col) or "") for col in self._columns).lower()
            for lead in self._leads]
        self._has_phone = [bool(str(lead.get("phone") or "").strip())
                           for lead in self._leads]
        self._has_wa = [bool(contacts.whatsapp_number(lead, dial, iso))
                        for lead in self._leads]
        self._has_site = [bool(str(lead.get("website") or "").strip())
                          for lead in self._leads]
        self._has_email = [bool(str(lead.get("email") or "").strip())
                           for lead in self._leads]

    def set_leads(self, leads: Sequence[Dict[str, Any]],
                  columns: Optional[Sequence[str]] = None) -> None:
        """Swap the data (a new search finished while the panel was open)."""
        self._leads = list(leads)
        if columns is not None:
            self._columns = list(columns)
        if not self._subtitle:
            self.sub_label.setText(f"{len(self._leads)} leads")
        self._precompute()
        self._apply_filters(reset=True)

    def set_context(self, dial: str, country_code: str) -> None:
        """Update the calling code used to normalise WhatsApp numbers."""
        self._dial = dial or ""
        self._iso = (country_code or "").lower()
        self._precompute()
        self._apply_filters(reset=False)

    def visible_count(self) -> int:
        return len(self._visible)

    def rendered_count(self) -> int:
        return self._rendered

    # ---------------------------------------------------------- filtering --
    def _set_filter(self, key: str) -> None:
        self._filter_key = key
        self._apply_filters(reset=True)

    def _on_search_changed(self) -> None:
        self._search_timer.start()

    def _passes(self, index: int, needle: str) -> bool:
        if needle and needle not in self._blobs[index]:
            return False
        key = self._filter_key
        if key == "wa":
            return self._has_wa[index]
        if key == "phone":
            return self._has_phone[index]
        if key == "site":
            return self._has_site[index]
        if key == "nos":
            return not self._has_site[index]
        if key == "email":
            return self._has_email[index]
        return True

    @staticmethod
    def _sort_key(index: int, lead: Dict[str, Any], mode: str) -> Tuple:
        name = str(lead.get("name") or "").lower()
        if mode == "rating":
            rating = lead.get("rating")
            known = isinstance(rating, (int, float))
            return (0 if known else 1, -(float(rating) if known else 0.0), name)
        if mode == "reviews":
            reviews = lead.get("reviews")
            known = isinstance(reviews, (int, float))
            return (0 if known else 1, -(float(reviews) if known else 0.0), name)
        if mode == "name":
            return (name,)
        return (index,)

    def _apply_filters(self, reset: bool) -> None:
        needle = self.search.text().strip().lower() if hasattr(self, "search") else ""
        mode = self.sort_combo.currentData() if hasattr(self, "sort_combo") else "source"
        indices = [i for i in range(len(self._leads)) if self._passes(i, needle)]
        indices.sort(key=lambda i: self._sort_key(i, self._leads[i], mode or "source"))
        self._visible = [self._leads[i] for i in indices]
        if reset:
            self._limit = self.PAGE
        self._rebuild()

    def _show_more(self) -> None:
        self._limit += self.PAGE
        self._rebuild()

    # ------------------------------------------------------------ cards --
    def _clear_cards(self) -> None:
        while self.cards.count():
            item = self.cards.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # take out of the widget tree right away; deleteLater alone
                # would leave the old cards painted until the event loop runs
                widget.setParent(None)
                widget.deleteLater()

    def _rebuild(self) -> None:
        self._clear_cards()
        shown = self._visible[: self._limit]
        self._rendered = 0
        if not shown:
            empty = QLabel("No leads match this filter.\n\n"
                           "Clear the search box or pick another chip.")
            empty.setObjectName("hint")
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(120)
            self.cards.addWidget(empty)
        else:
            for index, lead in enumerate(shown):
                self.cards.addWidget(self._card(lead, index))
                self._rendered += 1
        self.cards.addStretch(1)
        total = len(self._visible)
        self.count_label.setText(
            f"Showing {len(shown)} of {total} lead{'s' if total != 1 else ''}")
        self.more_btn.setVisible(len(shown) < total)
        self.scroll.verticalScrollBar().setValue(0)

    def _has(self, key: str) -> bool:
        return key in self._columns

    def _show_wa(self, lead: Dict[str, Any]) -> bool:
        """A WhatsApp button only when the user picked a phone-ish field."""
        if not (self._has("phone") or self._has("whatsapp")):
            return False
        return bool(contacts.whatsapp_number(lead, self._dial, self._iso))

    def _url_and_text(self, key: str, text: str,
                      lead: Dict[str, Any]) -> Tuple[str, str]:
        """(url to open, text to show) for one field value."""
        raw = lead.get(key)
        value = str(raw if raw is not None else text).strip()
        if key in ("website", "logo_url"):
            return value, _host(value)
        if key == "maps_url":
            return value, "Google Maps"
        if key == "place_id":
            return (f"https://www.google.com/maps/search/?api=1&query_place_id={value}",
                    text)
        if key in ("facebook", "instagram", "linkedin"):
            return value, key.capitalize()
        if key == "email":
            return f"mailto:{value}", text
        if key == "phone":
            return f"tel:{contacts.digits_only(value)}", text
        if key == "whatsapp":
            return "", text          # handled by a WhatsApp callback
        return "", text

    def _presence_chips(self, lead: Dict[str, Any]) -> List[QLabel]:
        chips: List[QLabel] = []
        if self._has("website") and str(lead.get("website") or "").strip():
            chips.append(chip("Website", "ok"))
        if self._has("phone") and str(lead.get("phone") or "").strip():
            chips.append(chip("Phone", "ok"))
        if self._show_wa(lead):
            chips.append(chip("WhatsApp", "wa"))
        if self._has("email") and str(lead.get("email") or "").strip():
            chips.append(chip("E-mail", "ok"))
        status = str(lead.get("status") or "").upper()
        if self._has("status") and status.startswith("CLOSED"):
            chips.append(chip("Closed", "bad"))
        elif self._has("open_now") and lead.get("open_now") is not None:
            chips.append(chip("Open now" if lead["open_now"] else "Closed now",
                              "ok" if lead["open_now"] else "warn"))
        return chips[:5]

    def _card(self, lead: Dict[str, Any], index: int) -> QWidget:
        frame = QFrame()
        frame.setObjectName("leadCard")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(16, 12, 16, 14)
        outer.setSpacing(9)
        # selected fields already represented somewhere on the card; everything
        # else goes to the detail grid, including selected-but-empty fields
        shown = {"name"}

        top = QHBoxLayout()
        top.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(3)

        name_row = QHBoxLayout()
        name_row.setSpacing(7)
        title = str(lead.get("name") or "").strip() or f"Lead {index + 1}"
        name_label = QLabel(title)
        name_label.setObjectName("leadName")
        name_label.setWordWrap(True)
        name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        name_row.addWidget(name_label)
        for presence in self._presence_chips(lead):
            name_row.addWidget(presence)
        name_row.addStretch(1)
        left.addLayout(name_row)

        if self._has("category") and str(lead.get("category") or "").strip():
            category = QLabel(str(lead["category"]))
            category.setObjectName("leadMeta")
            category.setWordWrap(True)
            left.addWidget(category)
            shown.add("category")

        place_keys = [key for key in ("city", "region")
                      if self._has(key) and lead.get(key)]
        place_bits = [str(lead[key]).strip() for key in place_keys]
        address_text = ""
        if self._has("address") and str(lead.get("address") or "").strip():
            address_text = str(lead["address"]).strip()
            shown.add("address")
        elif self._has("street") and str(lead.get("street") or "").strip():
            address_text = str(lead["street"]).strip()
            shown.add("street")
        if not address_text:
            address_text = ", ".join(place_bits)
            shown.update(place_keys)
        if address_text:
            maps_target = str(lead.get("maps_url") or "").strip()
            if not maps_target:
                query = ", ".join(p for p in [title, address_text] if p)
                maps_target = ("https://www.google.com/maps/search/?api=1&query="
                               + quote(query))
            address_row = QHBoxLayout()
            address_row.setSpacing(6)
            address_row.addWidget(_icon_label("pin", self.p.text_dim, 14))
            address = ClickableLabel(address_text)
            address.setObjectName("linkLabel")
            address.setWordWrap(True)
            address.setToolTip("Open in Google Maps")
            address.clicked.connect(lambda u=maps_target: self._open_url(u))
            address_row.addWidget(address, 1)
            left.addLayout(address_row)
        top.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(6)
        right.setAlignment(Qt.AlignRight | Qt.AlignTop)
        if self._has("rating") and lead.get("rating") is not None:
            rating_row = QHBoxLayout()
            rating_row.setSpacing(7)
            rating_row.setAlignment(Qt.AlignRight)
            rating_row.addStretch(1)
            rating_row.addWidget(RatingBar(lead.get("rating"), self.p))
            rating_label = QLabel(str(display_value("rating", lead.get("rating")))
                                  .split()[-1])
            rating_label.setObjectName("leadRating")
            rating_row.addWidget(rating_label)
            shown.add("rating")
            if self._has("reviews") and lead.get("reviews") is not None:
                rating_row.addWidget(chip(f"{int(lead['reviews']):,} reviews"))
                shown.add("reviews")
            right.addLayout(rating_row)
        elif self._has("reviews") and lead.get("reviews") is not None:
            right.addWidget(chip(f"{int(lead['reviews']):,} reviews"))
            shown.add("reviews")

        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addStretch(1)
        maps_url = str(lead.get("maps_url") or "").strip()
        if maps_url and (self._has("maps_url") or self._has("address")):
            maps_btn = QPushButton("Maps")
            maps_btn.setProperty("flat", True)
            maps_btn.setIcon(icons.icon("pin", self.p.text_dim, 13))
            maps_btn.clicked.connect(lambda u=maps_url: self._open_url(u))
            actions.addWidget(maps_btn)
            shown.add("maps_url")
        website = str(lead.get("website") or "").strip()
        if website and self._has("website"):
            site_btn = QPushButton("Website")
            site_btn.setProperty("flat", True)
            site_btn.setIcon(icons.icon("globe", self.p.text_dim, 13))
            site_btn.clicked.connect(lambda u=website: self._open_url(u))
            actions.addWidget(site_btn)
            shown.add("website")
        if self._show_wa(lead):
            wa_btn = QPushButton("  WhatsApp")
            wa_btn.setObjectName("waBtn")
            wa_btn.setIcon(icons.icon("chat", "#06281c", 14))
            wa_btn.setToolTip("Open this number in WhatsApp with your saved message")
            wa_btn.clicked.connect(lambda _=False, l=lead: self._send_whatsapp(l))
            actions.addWidget(wa_btn)
        copy_btn = QPushButton()
        copy_btn.setProperty("flat", True)
        copy_btn.setIcon(icons.icon("copy", self.p.text_dim, 13))
        copy_btn.setToolTip("Copy this lead (TSV)")
        copy_btn.clicked.connect(lambda _=False, l=lead: self._copy_lead(l))
        actions.addWidget(copy_btn)
        right.addLayout(actions)
        top.addLayout(right)
        outer.addLayout(top)

        contact_row, contact_shown = self._contact_row(lead)
        shown.update(contact_shown)
        if contact_shown:
            outer.addLayout(contact_row)

        details = [key for key in self._columns if key not in shown]
        if details:
            rule = QFrame()
            rule.setFixedHeight(1)
            rule.setStyleSheet(f"background: {self.p.border}; border: none;")
            outer.addWidget(rule)
            caption = QLabel("FIELDS FROM THIS SEARCH")
            caption.setObjectName("leadFieldLabel")
            outer.addWidget(caption)
            grid = QGridLayout()
            grid.setHorizontalSpacing(20)
            grid.setVerticalSpacing(4)
            for position, key in enumerate(details):
                column = position % 3
                row = (position // 3) * 2
                meta = FD.BY_KEY.get(key)
                label = QLabel(meta.label if meta else header_label(key))
                label.setObjectName("leadFieldLabel")
                label.setWordWrap(True)
                grid.addWidget(label, row, column)
                value = self._detail_widget(key, lead)
                grid.addWidget(value, row + 1, column)
            for column in range(3):
                grid.setColumnStretch(column, 1)
            outer.addLayout(grid)
        return frame

    def _detail_widget(self, key: str, lead: Dict[str, Any]):
        value = lead.get(key)
        text = display_value(key, value)
        if not text:
            label = QLabel("—")
            label.setObjectName("leadMuted")
            label.setWordWrap(True)
            return label
        if key == "whatsapp":
            link = ClickableLabel(text)
            link.setObjectName("linkLabel")
            link.setToolTip("Open in WhatsApp with your saved message")
            link.clicked.connect(lambda _=False, l=lead: self._send_whatsapp(l))
            return link
        url, label_text = self._url_and_text(key, text, lead)
        if url:
            link = ClickableLabel(label_text)
            link.setObjectName("linkLabel")
            link.setToolTip(url)
            link.clicked.connect(lambda u=url: self._open_url(u))
            return link
        return _plain(text)

    def _contact_row(self, lead: Dict[str, Any]) -> Tuple[QHBoxLayout, set]:
        row = QHBoxLayout()
        row.setSpacing(6)
        shown: set = set()
        phone = str(lead.get("phone") or "").strip()
        if self._has("phone") and phone:
            row.addWidget(_icon_label("phone", self.p.text_dim, 14))
            number = ClickableLabel(phone)
            number.setObjectName("linkLabel")
            number.setToolTip("Call this number")
            number.clicked.connect(
                lambda u=f"tel:{contacts.digits_only(phone)}": self._open_url(u))
            row.addWidget(number)
            shown.add("phone")
            if self._show_wa(lead):
                wa_btn = QPushButton("WhatsApp")
                wa_btn.setObjectName("waBtn")
                wa_btn.setIcon(icons.icon("chat", "#06281c", 13))
                wa_btn.setToolTip("Open in WhatsApp with your saved message")
                wa_btn.clicked.connect(
                    lambda _=False, l=lead: self._send_whatsapp(l))
                row.addWidget(wa_btn)
            row.addSpacing(14)
        elif self._has("whatsapp") and self._show_wa(lead):
            row.addWidget(_icon_label("chat", "#25d366", 14))
            wa_btn = QPushButton("WhatsApp")
            wa_btn.setObjectName("waBtn")
            wa_btn.setIcon(icons.icon("chat", "#06281c", 13))
            wa_btn.setToolTip("Open in WhatsApp with your saved message")
            wa_btn.clicked.connect(lambda _=False, l=lead: self._send_whatsapp(l))
            row.addWidget(wa_btn)
            row.addSpacing(14)
            shown.add("whatsapp")
        website = str(lead.get("website") or "").strip()
        if self._has("website") and website:
            row.addWidget(_icon_label("globe", self.p.text_dim, 14))
            link = ClickableLabel(_host(website))
            link.setObjectName("linkLabel")
            link.setToolTip(website)
            link.clicked.connect(lambda u=website: self._open_url(u))
            row.addWidget(link)
            row.addSpacing(14)
            shown.add("website")
        email = str(lead.get("email") or "").strip()
        if self._has("email") and email:
            row.addWidget(_icon_label("mail", self.p.text_dim, 14))
            link = ClickableLabel(email)
            link.setObjectName("linkLabel")
            link.setToolTip("Send an e-mail")
            link.clicked.connect(lambda u=f"mailto:{email}": self._open_url(u))
            row.addWidget(link)
            row.addSpacing(14)
            shown.add("email")
        for key in ("facebook", "instagram", "linkedin"):
            url = str(lead.get(key) or "").strip()
            if self._has(key) and url:
                link = ClickableLabel(key.capitalize())
                link.setObjectName("linkLabel")
                link.setToolTip(url)
                link.clicked.connect(lambda u=url: self._open_url(u))
                row.addWidget(link)
                row.addSpacing(12)
                shown.add(key)
        if shown:
            row.addStretch(1)
        return row, shown

    # ---------------------------------------------------------- actions --
    def _open_url(self, url: str) -> None:
        if not url:
            return
        if QDesktopServices.openUrl(QUrl(url)) or open_in_desktop(url):
            self._status(f"Opened {_host(url) if url.startswith('http') else url}")
        else:
            self._status(f"Could not open {url}")

    def _send_whatsapp(self, lead: Dict[str, Any]) -> None:
        message = contacts.render_template(self._template, lead)
        url = contacts.whatsapp_url_for(lead, message, dial=self._dial,
                                        iso=self._iso)
        if not url:
            QMessageBox.information(
                self, "WhatsApp",
                "This lead has no phone number that can be opened in WhatsApp.")
            return
        name = str(lead.get("name") or "lead")
        if QDesktopServices.openUrl(QUrl(url)) or open_in_desktop(url):
            self._status(f"WhatsApp opened for {name} — message pre-filled")
        else:
            self._status(f"Could not open WhatsApp for {name}")

    def _copy_lead(self, lead: Dict[str, Any]) -> None:
        header = "\t".join(header_label(key) for key in self._columns)
        values = "\t".join(
            display_value(key, lead.get(key)).replace("\n", " ")
            for key in self._columns)
        QGuiApplication.clipboard().setText(f"{header}\n{values}")
        self._status(f"Copied “{lead.get('name') or 'lead'}” to the clipboard")

    def edit_template(self) -> None:
        window = WhatsAppTemplateDialog(self._leads, self.p, parent=self)
        if window.exec() == QDialog.Accepted:
            self._template = load_message_template()
            self._status("WhatsApp message saved — it opens with every chat")

    def _status(self, text: str) -> None:
        self.status_label.setText(text)
