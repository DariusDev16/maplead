"""
Inline SVG icon set (no image files, no icon theme dependency).

Every icon is drawn as a 24x24 stroke path, so it re-colours with the theme and
stays crisp at any size.
"""

from __future__ import annotations

from typing import Dict

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_STROKE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    "{body}</svg>"
)

_FILL = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{color}" '
    'stroke="{color}" stroke-width="2" stroke-linejoin="round">{body}</svg>'
)

PATHS: Dict[str, str] = {
    # --- navigation / actions -------------------------------------------- #
    "play": _FILL.format(color="{color}", body='<path d="M7 4.5 L19 12 L7 19.5 Z" stroke="none"/>'),
    "stop": _FILL.format(color="{color}", body='<rect x="6" y="6" width="12" height="12" rx="2" stroke="none"/>'),
    "search": _STROKE.format(color="{color}", body='<circle cx="11" cy="11" r="7"/>'
                                                    '<path d="M20 20l-4.2-4.2"/>'),
    "refresh": _STROKE.format(color="{color}", body='<path d="M21 12a9 9 0 1 1-2.6-6.4"/>'
                                                   '<path d="M21 3v6h-6"/>'),
    "copy": _STROKE.format(color="{color}", body='<rect x="9" y="9" width="12" height="12" rx="2"/>'
                                                '<path d="M5 15V5a2 2 0 0 1 2-2h10"/>'),
    "check": _STROKE.format(color="{color}", body='<path d="M20 6 9 17l-5-5"/>'),
    "close": _STROKE.format(color="{color}", body='<path d="M18 6 6 18M6 6l12 12"/>'),
    "alert": _STROKE.format(color="{color}", body='<path d="M12 3.5 22 20H2z"/>'
                                                  '<path d="M12 10v4M12 17.5v.01"/>'),
    "plus": _STROKE.format(color="{color}", body='<path d="M12 5v14M5 12h14"/>'),
    "trash": _STROKE.format(color="{color}", body='<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>'),
    "external": _STROKE.format(color="{color}", body='<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
                                                      '<path d="M15 3h6v6M21 3l-9 9"/>'),
    "phone": _STROKE.format(color="{color}", body='<path d="M5 3h3l2 5-2.3 1.7a15 15 0 0 0 5.6 5.6L15 13l5 2v3a2 2 0 0 1-2.2 2A17 17 0 0 1 3 5.2 2 2 0 0 1 5 3z"/>'),
    "mail": _STROKE.format(color="{color}", body='<rect x="3" y="5" width="18" height="14" rx="2"/>'
                                                 '<path d="M3.5 6.5 12 13l8.5-6.5"/>'),
    "chat": _STROKE.format(color="{color}", body='<path d="M21 11.5a8.5 8.5 0 0 1-12.4 7.6L4 20.5l1.4-4.3A8.5 8.5 0 1 1 21 11.5z"/>'
                                                 '<path d="M8.5 9.4h7M8.5 13h4.5"/>'),
    "download": _STROKE.format(color="{color}", body='<path d="M12 3v12M7.5 10.5 12 15l4.5-4.5"/>'
                                                     '<path d="M4 20h16"/>'),

    # --- files / folders -------------------------------------------------- #
    "file": _STROKE.format(color="{color}", body='<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
                                                 '<path d="M14 3v5h5"/>'),
    "folder": _STROKE.format(color="{color}", body='<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
    "sheet": _STROKE.format(color="{color}", body='<rect x="3.5" y="4" width="17" height="16" rx="2"/>'
                                                  '<path d="M3.5 9.5h17M9.5 9.5V20M3.5 15h17"/>'),
    "open": _STROKE.format(color="{color}", body='<path d="M4 20h16M6 16l1-4h9l3 4"/>'
                                                '<path d="M9 12 11 4h4l2 8"/>'),

    # --- keys / settings --------------------------------------------------- #
    "key": _STROKE.format(color="{color}", body='<circle cx="8" cy="14" r="4"/>'
                                               '<path d="M11 11 20 2M17 5l2.5 2.5M14.5 7.5 17 10"/>'),
    "sliders": _STROKE.format(color="{color}", body='<path d="M4 21v-6M4 11V3M12 21v-9M12 8V3M20 21v-4M20 13V3"/>'
                                                    '<path d="M1.5 15h5M9.5 8h5M17.5 17h5"/>'),
    "list": _STROKE.format(color="{color}", body='<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>'),
    "pin": _STROKE.format(color="{color}", body='<path d="M12 21.5s7-6.7 7-11.5a7 7 0 1 0-14 0c0 4.8 7 11.5 7 11.5z"/>'
                                                '<circle cx="12" cy="10" r="2.6"/>'),
    "globe": _STROKE.format(color="{color}", body='<circle cx="12" cy="12" r="9"/>'
                                                 '<path d="M3 12h18M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z"/>'),
    "building": _STROKE.format(color="{color}", body='<path d="M4 21V4h9v17M13 9h7v12M2 21h20"/>'
                                                   '<path d="M7 8h3M7 12h3M7 16h3M16 13h1M16 17h1"/>'),
    "star": _FILL.format(color="{color}", body='<path d="M12 3.6l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.5 9.8l5.9-.9z" stroke="none"/>'),

    # --- ui state ---------------------------------------------------------- #
    "moon": _STROKE.format(color="{color}", body='<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>'),
    "sun": _STROKE.format(color="{color}", body='<circle cx="12" cy="12" r="4"/>'
                                                 '<path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.5 1.5M17.6 17.6l1.5 1.5M19.1 4.9l-1.5 1.5M6.4 17.6l-1.5 1.5"/>'),
    "chevron": _STROKE.format(color="{color}", body='<path d="M6 9l6 6 6-6"/>'),
    "chevron-right": _STROKE.format(color="{color}", body='<path d="M9 6l6 6-6 6"/>'),
    "info": _STROKE.format(color="{color}", body='<circle cx="12" cy="12" r="9"/>'
                                                '<path d="M12 11v5M12 8h.01"/>'),
    "lock": _STROKE.format(color="{color}", body='<rect x="4.5" y="10" width="15" height="10" rx="2"/>'
                                               '<path d="M8 10V7.5a4 4 0 0 1 8 0V10"/>'),
    "eye": _STROKE.format(color="{color}", body='<path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/>'
                                              '<circle cx="12" cy="12" r="2.8"/>'),
    "table": _STROKE.format(color="{color}", body='<rect x="3" y="4" width="18" height="16" rx="2"/>'
                                                '<path d="M3 9.5h18M3 15h18M9 9.5V20"/>'),
}

_CACHE: Dict[tuple, QIcon] = {}


def svg(name: str, color: str = "#e6edf7") -> bytes:
    template = PATHS.get(name, PATHS["info"]).format(color=color)
    return template.encode("utf-8")


def pixmap(name: str, color: str = "#e6edf7", size: int = 18) -> QPixmap:
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.transparent)
    renderer = QSvgRenderer(QByteArray(svg(name, color)))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return pm


def icon(name: str, color: str = "#e6edf7", size: int = 18) -> QIcon:
    """Cached themed icon."""
    key = (name, color, size)
    if key not in _CACHE:
        ico = QIcon()
        for scale in (1, 2):                      # crisp on hidpi
            ico.addPixmap(pixmap(name, color, size * scale))
        _CACHE[key] = ico
    return _CACHE[key]