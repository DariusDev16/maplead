"""
API key manager: paste a key per provider, verify it live, save it to the
per-user config file (~/.config/maplead/.env on Linux,
%APPDATA%\\maplead\\.env on Windows).  Mirrors the CLI's `--api` wizard.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .. import paths
from ..providers import ORDER, PROVIDERS
from . import icons
from .theme import Palette
from .widgets import card, hint

_PROVIDER_ORDER: List[str] = list(ORDER) + ["demo"]

_ENV_KEY_NAMES = {
    "outscraper": "OUTSCRAPER_API_KEY",
    "google": "GOOGLE_MAPS_API_KEY",
    "serpapi": "SERPAPI_API_KEY",
    "dataforseo": "DATAFORSEO_LOGIN / PASSWORD",
}


class ProviderRow(QFrame):
    """One provider: key fields, live status, save / clear buttons."""

    changed = Signal()

    def __init__(self, name: str, palette: Palette, env_path: str,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.name = name
        self.palette_ = palette
        self.env_path = env_path
        self.setObjectName("card")
        self.cls = PROVIDERS[name]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(8)

        # -- title row ------------------------------------------------------ #
        top = QHBoxLayout()
        title = QLabel(self.cls.label)
        title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {palette.text};")
        top.addWidget(title)
        self.status = QLabel("")
        self.status.setObjectName("badge")
        top.addWidget(self.status)
        top.addStretch(1)
        home = QPushButton("  Get a key")
        home.setProperty("flat", True)
        home.setIcon(icons.icon("external", palette.text_dim, 14))
        home.setToolTip(self.cls.homepage or "")
        home.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.cls.homepage)))
        top.addWidget(home)
        lay.addLayout(top)

        if name == "demo":
            lay.addWidget(hint("Built-in generator: synthetic leads, no network, "
                                "no key. Handy to try the app or demo it."))
            self.status.setText("always ready")
            self.status.setObjectName("badgeOk")
            return

        self.fields: Dict[str, QLineEdit] = {}
        for var in self.cls.env_keys:
            row = QHBoxLayout()
            row.setSpacing(8)
            var_label = QLabel(var)
            var_label.setStyleSheet(
                f"font-family: monospace; font-size: 10px; color: {palette.text_dim};")
            var_label.setMinimumWidth(150)
            var_label.setToolTip(f"Environment variable: {var}")
            row.addWidget(var_label)
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.Password)
            edit.setPlaceholderText("paste the key")
            edit.setText(os.environ.get(var, ""))
            edit.textChanged.connect(self._dirty)
            self.fields[var] = edit
            row.addWidget(edit, 1)
            show = QPushButton()
            show.setIcon(icons.icon("eye", palette.text_dim, 15))
            show.setProperty("flat", True)
            show.setToolTip("show / hide")
            show.clicked.connect(lambda _=False, e=edit, b=show: self._toggle_echo(e, b))
            row.addWidget(show)
            lay.addLayout(row)

        # -- actions -------------------------------------------------------- #
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.save_btn = QPushButton("Save & verify")
        self.save_btn.setProperty("accent", True)
        self.save_btn.clicked.connect(lambda: self._save(verify=True))
        actions.addWidget(self.save_btn)
        plain = QPushButton("Save only")
        plain.setProperty("flat", True)
        plain.clicked.connect(lambda: self._save(verify=False))
        actions.addWidget(plain)
        clear = QPushButton("Remove")
        clear.setProperty("flat", True)
        clear.setProperty("danger", True)
        clear.setIcon(icons.icon("trash", palette.danger, 14))
        clear.clicked.connect(self._clear)
        actions.addWidget(clear)
        actions.addStretch(1)
        lay.addLayout(actions)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setObjectName("hint")
        self.message.setVisible(False)
        lay.addWidget(self.message)

        self._refresh()

    # -- behaviour -----------------------------------------------------------
    def _toggle_echo(self, edit: QLineEdit, button: QPushButton) -> None:
        hidden = edit.echoMode() == QLineEdit.Password
        edit.setEchoMode(QLineEdit.Normal if hidden else QLineEdit.Password)
        button.setIcon(icons.icon("eye" if hidden else "lock",
                                  self.palette_.text_dim, 15))

    def _dirty(self) -> None:
        self._set_status("unsaved", "badgeWarn")

    def _set_status(self, text: str, kind: str = "badge") -> None:
        self.status.setText(text)
        self.status.setObjectName(kind)

    def _refresh(self) -> None:
        if self.name == "demo":
            return
        if self.cls.is_configured():
            self._set_status("key detected", "badgeOk")
        else:
            self._set_status("no key yet", "badgeWarn")

    def _save(self, verify: bool) -> None:
        values = {var: edit.text().strip().strip("'\"")
                  for var, edit in self.fields.items()}
        missing = [var for var, val in values.items() if not val]
        if missing:
            self._say(f"Fill in {', '.join(missing)} (or use Remove to clear it).",
                      self.palette_.warning)
            return
        for var, val in values.items():
            paths.save_env_key(var, val, self.env_path)
        self._refresh()
        self.changed.emit()
        if verify:
            self._say("Saved. Verifying with a live request…", self.palette_.text_dim)
        else:
            self._say(f"Saved to {self.env_path} (chmod 600)", self.palette_.success)

    def _clear(self) -> None:
        for var in self.fields:
            paths.clear_env_key(var, self.env_path)
            self.fields[var].clear()
        self._refresh()
        self.changed.emit()
        self._say("Key removed from the config file.", self.palette_.text_dim)

    def _say(self, text: str, color: str) -> None:
        self.message.setText(f'<span style="color:{color}">{text}</span>')
        self.message.setVisible(bool(text))

    def verify_result(self, ok: bool, message: str) -> None:
        if ok:
            self._say(f"✓ {message}", self.palette_.success)
            self._set_status("working key", "badgeOk")
        else:
            self._say(f"✕ {message}", self.palette_.danger)
            self._set_status("check the key", "badgeWarn")


class KeysDialog(QDialog):
    """The provider/key manager window."""

    def __init__(self, palette: Palette, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.palette_ = palette
        self.env_path = paths.user_env_file()
        self.setWindowTitle("MAPLEAD — API keys")
        self.setMinimumSize(700, 560)
        self.resize(740, 760)
        self._threads: List[QThread] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        intro, intro_lay = card()
        head = QHBoxLayout()
        title = QLabel("API keys")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {palette.text};")
        head.addWidget(title)
        head.addStretch(1)
        intro_lay.addLayout(head)
        intro_lay.addWidget(hint(
            f"Keys are stored in <code>{self.env_path}</code> (readable only by your "
            f"user) and are never sent anywhere except the provider you pick. Real "
            f"environment variables always win over this file."))
        root.addWidget(intro)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        holder = QWidget()
        holder_lay = QVBoxLayout(holder)
        holder_lay.setContentsMargins(0, 0, 6, 0)
        holder_lay.setSpacing(10)
        self.rows: Dict[str, ProviderRow] = {}
        for name in _PROVIDER_ORDER:
            row = ProviderRow(name, palette, self.env_path, holder)
            row.changed.connect(self._on_changed)
            holder_lay.addWidget(row)
            self.rows[name] = row
        holder_lay.addStretch(1)
        holder_lay.setSizeConstraint(QVBoxLayout.SetMinimumSize)
        area.setWidget(holder)
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(area, 1)

        foot = QHBoxLayout()
        self.env_label = QLabel("")
        self.env_label.setObjectName("hint")
        self.env_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        foot.addWidget(self.env_label, 1)
        self.check_all = QPushButton("Check all saved keys")
        self.check_all.setIcon(icons.icon("refresh", palette.text_dim, 15))
        self.check_all.clicked.connect(lambda: self._check_all())
        foot.addWidget(self.check_all)
        close = QPushButton("Done")
        close.setProperty("accent", True)
        close.clicked.connect(self.accept)
        foot.addWidget(close)
        root.addLayout(foot)

        self._on_changed()

    # -- helpers -------------------------------------------------------------
    def _on_changed(self) -> None:
        configured = [n for n in ORDER if PROVIDERS[n].is_configured()]
        self.env_label.setText(
            f"{len(configured)} of {len(ORDER)} providers ready "
            f"({', '.join(PROVIDERS[n].label for n in configured) if configured else 'none'})"
            f"   ·   {self.env_path}")

    def _check_all(self) -> None:
        targets = [n for n in ORDER if PROVIDERS[n].is_configured()]
        if not targets:
            self.rows["google"]._say("No keys saved yet - paste one above.", self.palette_.warning)
            return
        for name in targets:
            self.rows[name]._say("Checking…", self.palette_.text_dim)
            self._verify(name)

    def _verify(self, name: str) -> None:
        from .worker import ValidateWorker
        worker = ValidateWorker(name)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_verified)
        worker.done.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        self._threads.append(thread)
        thread.start()

    def _on_verified(self, name: str, ok: bool, message: str) -> None:
        self.rows[name].verify_result(ok, message)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        for thread in self._threads:
            if thread.isRunning():
                thread.quit()
                thread.wait(2500)
        super().closeEvent(event)