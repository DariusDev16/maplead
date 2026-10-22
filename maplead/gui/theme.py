"""
MAPLEAD Desktop - visual language.

Two palettes (dark default, light alternative) drive one stylesheet builder, so
every widget is themed from a single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory


@dataclass(frozen=True)
class Palette:
    name: str
    window: str
    surface: str          # cards / inputs
    surface_alt: str      # headers, hovered rows
    border: str
    text: str
    text_dim: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    warning: str
    danger: str
    selection: str
    is_dark: bool = True

    def c(self, name: str, alpha: int = 255) -> QColor:
        col = QColor(getattr(self, name))
        col.setAlpha(alpha)
        return col


DARK = Palette(
    name="dark",
    window="#0b1120",
    surface="#111c33",
    surface_alt="#16233f",
    border="#24334f",
    text="#e6edf7",
    text_dim="#8496b3",
    accent="#38bdf8",
    accent_hover="#0ea5e9",
    accent_text="#04121f",
    success="#34d399",
    warning="#fbbf24",
    danger="#f87171",
    selection="#1d3b63",
    is_dark=True,
)

LIGHT = Palette(
    name="light",
    window="#f4f6fb",
    surface="#ffffff",
    surface_alt="#eef2f9",
    border="#d3dceb",
    text="#16233c",
    text_dim="#5b6b87",
    accent="#0284c7",
    accent_hover="#0369a1",
    accent_text="#ffffff",
    success="#059669",
    warning="#b45309",
    danger="#dc2626",
    selection="#d8ecff",
    is_dark=False,
)

PALETTES: Dict[str, Palette] = {"dark": DARK, "light": LIGHT}

FONT_STACK = 'Inter, "Segoe UI", Ubuntu, Cantarell, "Noto Sans", "DejaVu Sans", sans-serif'
MONO_STACK = '"JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", Consolas, monospace'


def base_qss(p: Palette) -> str:
    """Widget-level styling; component-specific rules live in their modules."""
    return f"""
    * {{ font-family: {FONT_STACK}; }}

    QWidget {{
        background: {p.window};
        color: {p.text};
        font-size: 13px;
    }}
    /* labels must never paint a slab over their card */
    QLabel {{ background: transparent; }}
    QMainWindow, QDialog {{ background: {p.window}; }}

    /* ---------- inputs ---------- */
    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 6px 10px;
        selection-background-color: {p.selection};
        selection-color: {p.text};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1px solid {p.accent};
    }}
    QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
        color: {p.text_dim};
        background: {p.surface_alt};
    }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
    QComboBox QAbstractItemView {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 4px;
        outline: none;
        selection-background-color: {p.selection};
        selection-color: {p.text};
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button,
    QSpinBox::down-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}

    /* ---------- buttons ---------- */
    QPushButton {{
        background: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 7px 14px;
        color: {p.text};
    }}
    QPushButton:hover {{ border-color: {p.accent}; }}
    QPushButton:pressed {{ background: {p.border}; }}
    QPushButton:disabled {{ color: {p.text_dim}; border-color: {p.border}; }}
    QPushButton[accent="true"] {{
        background: {p.accent};
        color: {p.accent_text};
        border: none;
        font-weight: 600;
    }}
    QPushButton[accent="true"]:hover {{ background: {p.accent_hover}; }}
    QPushButton[accent="true"]:disabled {{ background: {p.border}; color: {p.text_dim}; }}
    QPushButton[danger="true"] {{ color: {p.danger}; }}
    QPushButton[flat="true"] {{
        background: transparent;
        border: none;
        color: {p.text_dim};
        padding: 4px 8px;
    }}
    QPushButton[flat="true"]:hover {{ color: {p.accent}; background: {p.surface_alt}; }}

    /* ---------- checks / radios ---------- */
    QCheckBox, QRadioButton {{ spacing: 8px; padding: 2px 0; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
    QCheckBox::indicator {{
        border: 1px solid {p.border};
        border-radius: 5px;
        background: {p.surface};
    }}
    QCheckBox::indicator:checked {{
        background: {p.accent};
        border-color: {p.accent};
        image: none;
    }}
    QRadioButton::indicator {{
        border: 1px solid {p.border};
        border-radius: 9px;
        background: {p.surface};
    }}
    QRadioButton::indicator:checked {{
        border: 5px solid {p.accent};
        background: {p.surface};
    }}
    QCheckBox:disabled, QRadioButton:disabled {{ color: {p.text_dim}; }}

    /* ---------- scrollbars ---------- */
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 5px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {p.text_dim}; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 5px; min-width: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* ---------- tabs / menus / tooltips ---------- */
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{
        background: transparent;
        color: {p.text_dim};
        padding: 6px 14px;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{ color: {p.accent}; border-bottom-color: {p.accent}; }}
    QMenu {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{ padding: 7px 22px 7px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {p.selection}; }}
    QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 8px; }}
    QToolTip {{
        background: {p.surface};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 5px 8px;
    }}
    QProgressBar {{
        background: {p.surface};
        border: none;
        border-radius: 4px;
        height: 6px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{ background: {p.accent}; border-radius: 4px; }}

    QStatusBar {{ color: {p.text_dim}; border-top: 1px solid {p.border}; }}
    QStatusBar::item {{ border: none; }}
    """


def table_qss(p: Palette) -> str:
    return f"""
    QTableView {{
        background: {p.surface};
        alternate-background-color: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: 10px;
        gridline-color: {p.border};
        selection-background-color: {p.selection};
        selection-color: {p.text};
        outline: none;
    }}
    QTableView::item {{ padding: 5px 7px; border: none; }}
    QTableView::item:selected {{ background: {p.selection}; }}
    QHeaderView::section {{
        background: {p.window};
        color: {p.text_dim};
        padding: 7px 8px;
        border: none;
        border-bottom: 1px solid {p.border};
        font-weight: 600;
        font-size: 11px;
        text-transform: uppercase;
    }}
    QHeaderView::section:hover {{ color: {p.accent}; }}
    QTableCornerButton::section {{ background: {p.window}; border: none; }}
    """


def component_qss(p: Palette) -> str:
    """Rules for the custom widgets defined in widgets.py."""
    return f"""
    QFrame#card {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 12px;
    }}
    QFrame#topbar {{ background: {p.window}; border-bottom: 1px solid {p.border}; }}
    QFrame#statCard {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 12px;
    }}
    QLabel#cardTitle {{
        color: {p.text_dim};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.2px;
    }}
    QLabel#statValue {{ font-size: 21px; font-weight: 700; color: {p.text}; }}
    QLabel#statLabel {{ color: {p.text_dim}; font-size: 11px; }}
    QLabel#hint {{ color: {p.text_dim}; font-size: 11px; }}
    QLabel#muted {{ color: {p.text_dim}; }}
    QLabel#brand {{ font-size: 17px; font-weight: 700; letter-spacing: 3px; color: {p.text}; }}
    QLabel#badge {{
        background: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: 9px;
        padding: 1px 8px;
        color: {p.text_dim};
        font-size: 11px;
    }}
    QLabel#badgeOk {{ background: {p.surface_alt}; border: 1px solid {p.success};
                      color: {p.success}; border-radius: 9px; padding: 1px 8px; font-size: 11px; }}
    QLabel#badgeWarn {{ background: {p.surface_alt}; border: 1px solid {p.warning};
                       color: {p.warning}; border-radius: 9px; padding: 1px 8px; font-size: 11px; }}
    QLabel#fieldLabel {{ color: {p.text_dim}; font-size: 11px; font-weight: 600; }}
    QTextEdit#log {{
        background: {p.window};
        border: 1px solid {p.border};
        border-radius: 10px;
        font-family: {MONO_STACK};
        font-size: 11.5px;
        padding: 6px;
    }}
    QLineEdit#searchBox {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 16px;
        padding: 5px 12px;
    }}
    QListWidget, QListView {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 10px;
        outline: none;
    }}
    QListWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
    QListWidget::item:selected {{ background: {p.selection}; }}
    QToolButton {{
        background: transparent; border: 1px solid {p.border};
        border-radius: 8px; padding: 5px;
    }}
    QToolButton:hover {{ border-color: {p.accent}; }}
    QSplitter::handle {{ background: transparent; }}
    QSplitter::handle:hover {{ background: {p.border}; }}

    /* ---------- leads panel ---------- */
    QFrame#panelHeader {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 12px;
    }}
    QLabel#panelTitle {{ font-size: 18px; font-weight: 700; color: {p.text}; }}
    QLabel#panelSub {{ color: {p.text_dim}; font-size: 12px; }}
    QFrame#leadCard {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 14px;
    }}
    QFrame#leadCard:hover {{ border-color: {p.accent}; }}
    QLabel#leadName {{ font-size: 16px; font-weight: 700; color: {p.text}; }}
    QLabel#leadMeta {{ color: {p.text_dim}; font-size: 12px; }}
    QLabel#leadRating {{ color: {p.warning}; font-size: 13px; font-weight: 700; }}
    QLabel#leadFieldLabel {{
        color: {p.text_dim}; font-size: 10px; font-weight: 700;
        letter-spacing: 0.6px;
    }}
    QLabel#leadValue {{ color: {p.text}; font-size: 12.5px; }}
    QLabel#leadMuted {{ color: {p.text_dim}; font-size: 12.5px; }}
    QLabel#linkLabel {{ color: {p.accent}; font-weight: 600; }}
    QLabel[chip="true"] {{
        background: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 1px 7px;
        color: {p.text_dim};
        font-size: 11px;
    }}
    QLabel[chip="true"][tone="ok"] {{ color: {p.success}; border-color: {p.success}; }}
    QLabel[chip="true"][tone="warn"] {{ color: {p.warning}; border-color: {p.warning}; }}
    QLabel[chip="true"][tone="bad"] {{ color: {p.danger}; border-color: {p.danger}; }}
    QLabel[chip="true"][tone="wa"] {{ color: #25d366; border-color: #25d366; }}
    QPushButton#waBtn {{
        background: #25d366;
        color: #06281c;
        border: none;
        border-radius: 8px;
        padding: 6px 12px;
        font-weight: 700;
    }}
    QPushButton#waBtn:hover {{ background: #1ebe5b; }}
    QPushButton#waBtn:pressed {{ background: #17a34f; }}
    QPushButton#waBtn:disabled {{ background: {p.border}; color: {p.text_dim}; }}
    QPushButton[chip="true"] {{
        background: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: 14px;
        padding: 4px 12px;
        color: {p.text_dim};
    }}
    QPushButton[chip="true"]:hover {{ border-color: {p.accent}; color: {p.text}; }}
    QPushButton[chip="true"]:checked {{
        background: {p.accent};
        border-color: {p.accent};
        color: {p.accent_text};
        font-weight: 700;
    }}
    QFrame#templateCard {{
        background: {p.window};
        border: 1px solid {p.border};
        border-radius: 10px;
    }}
    """


def apply_theme(app: QApplication, palette: Palette) -> None:
    """Install the Qt palette + stylesheet for one of our themes."""
    app.setStyle(QStyleFactory.create("Fusion"))

    q = QPalette()
    q.setColor(QPalette.Window, p_c(palette.window))
    q.setColor(QPalette.WindowText, p_c(palette.text))
    q.setColor(QPalette.Base, p_c(palette.surface))
    q.setColor(QPalette.AlternateBase, p_c(palette.surface_alt))
    q.setColor(QPalette.Text, p_c(palette.text))
    q.setColor(QPalette.Button, p_c(palette.surface_alt))
    q.setColor(QPalette.ButtonText, p_c(palette.text))
    q.setColor(QPalette.Highlight, p_c(palette.accent))
    q.setColor(QPalette.HighlightedText, p_c(palette.accent_text))
    q.setColor(QPalette.ToolTipBase, p_c(palette.surface))
    q.setColor(QPalette.ToolTipText, p_c(palette.text))
    q.setColor(QPalette.PlaceholderText, p_c(palette.text_dim))
    q.setColor(QPalette.Disabled, QPalette.Text, p_c(palette.text_dim))
    q.setColor(QPalette.Disabled, QPalette.ButtonText, p_c(palette.text_dim))
    q.setColor(QPalette.Disabled, QPalette.WindowText, p_c(palette.text_dim))
    app.setPalette(q)
    app.setStyleSheet(base_qss(palette) + table_qss(palette) + component_qss(palette))


def p_c(hex_color: str) -> QColor:
    return QColor(hex_color)