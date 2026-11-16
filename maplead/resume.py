"""
Where a long run stopped, so it can be picked up again.

Turbo mode and the bulk sender both write one small JSON record when they start,
stop or finish: when it happened, which search/lead was on screen and how much
is left. The setup dialogs read it back and show a reminder, so the user knows
where the last run stopped and can continue from there.

Pure standard library, like ``turbo.py`` and ``outreach.py`` — no Qt here.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
from typing import Any, Dict, Optional

from . import paths


def now() -> str:
    """The timestamp written into a reminder (seconds are enough)."""
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def when_text(value: Any) -> str:
    """``13/11 14:32`` for an ISO timestamp; the raw text when it cannot be read."""
    raw = str(value or "").strip()
    try:
        moment = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return raw
    return moment.strftime("%d/%m %H:%M")


def as_int(value: Any, default: int = 0) -> int:
    """``int(value)`` without letting a hand-edited file break the dialog."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _atomic_write(path: str, payload: Dict[str, Any]) -> None:
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".reminder-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Reminder:
    """One "last run" record, kept in its own file in the user data folder.

    ``last`` is an empty dict when there is nothing to show. Callers can store
    whichever fields they need; the GUI reads them back with ``.get()``.
    """

    def __init__(self, filename: str, path: Optional[str] = None):
        self.path = path or paths.state_file(filename)
        self.last: Dict[str, Any] = {}
        self.load()

    # -- storage ----------------------------------------------------------
    def load(self) -> None:
        self.last = {}
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        last = data.get("last") if isinstance(data, dict) else None
        if isinstance(last, dict):
            self.last = dict(last)

    def save(self) -> None:
        _atomic_write(self.path, {"version": 1, "last": self.last or None})

    # -- updates ----------------------------------------------------------
    def remember(self, **fields: Any) -> Dict[str, Any]:
        """Replace the record with ``fields`` plus the current timestamp."""
        self.last = {"at": now()}
        self.last.update(fields)
        self.save()
        return self.last

    def clear(self) -> None:
        self.last = {}
        self.save()
