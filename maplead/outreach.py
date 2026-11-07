"""
Bulk WhatsApp outreach: the queue, the safety pacing and the contact history.

Pure standard library, like ``contacts.py`` — the GUI drives the actual sending
(WhatsApp Web inside a Qt window), but every decision about *who* gets a message,
*when* the next one goes out and *whether to ask the user first* lives here, so
it can be tested without a display.

Three pieces:

* :class:`SafetySettings` — random delay between messages, a longer rest after
  every burst, the "this many messages may get the number blocked, continue?"
  threshold and a daily cap. Defaults are conservative on purpose.
* :class:`History` — every number ever messaged, with status and date, stored as
  JSON in the user data folder. Numbers already *sent* are skipped next time.
* :func:`build_queue` — turns the leads the user picked into
  :class:`OutreachItem` s (number + rendered message), dropping duplicates and
  numbers already contacted.
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import random
import tempfile
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import contacts, paths

HISTORY_FILE = "whatsapp-history.json"

# delivery outcomes recorded in the history
SENT = "sent"
FAILED = "failed"
INVALID = "invalid"          # the number is not on WhatsApp
SKIPPED = "skipped"          # the user skipped it during the run

STATUS_LABELS: Dict[str, str] = {
    SENT: "Sent",
    FAILED: "Failed",
    INVALID: "Not on WhatsApp",
    SKIPPED: "Skipped",
}


# --------------------------------------------------------------------------- #
# safety
# --------------------------------------------------------------------------- #

@dataclass
class SafetySettings:
    """How fast the bulk sender may go. All times in seconds."""

    min_delay: int = 45          # random pause between two messages ...
    max_delay: int = 120         # ... somewhere in [min_delay, max_delay]
    burst_size: int = 10         # after this many messages ...
    burst_rest: int = 600        # ... rest this long
    warn_after: int = 25         # ask "continue?" after this many in one run
    daily_limit: int = 50        # ask again once today's total reaches this

    def normalized(self) -> "SafetySettings":
        """A copy with every value clamped into a sane range."""
        lo = max(5, int(self.min_delay))
        hi = max(lo, int(self.max_delay))
        return SafetySettings(
            min_delay=lo,
            max_delay=hi,
            burst_size=max(0, int(self.burst_size)),
            burst_rest=max(0, int(self.burst_rest)),
            warn_after=max(0, int(self.warn_after)),
            daily_limit=max(0, int(self.daily_limit)),
        )

    def to_dict(self) -> Dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]) -> "SafetySettings":
        base = cls()
        if not data:
            return base
        values: Dict[str, int] = {}
        for f in fields(cls):
            raw = data.get(f.name, getattr(base, f.name))
            try:
                values[f.name] = int(raw)
            except (TypeError, ValueError):
                values[f.name] = getattr(base, f.name)
        return cls(**values).normalized()


class Pacer:
    """Decides the wait after each message and when to ask the user.

    ``sent`` counts messages that actually went out in this run (failures and
    invalid numbers do not count towards bursts or the warning — they never
    reached anyone).
    """

    def __init__(self, settings: SafetySettings,
                 rng: Optional[random.Random] = None):
        self.s = settings.normalized()
        self.rng = rng or random.Random()

    def delay_after(self, sent: int) -> Tuple[int, str]:
        """Seconds to wait before the next message, and why."""
        s = self.s
        if s.burst_size and sent > 0 and sent % s.burst_size == 0 and s.burst_rest:
            return s.burst_rest, f"rest after {sent} messages"
        return self.rng.randint(s.min_delay, s.max_delay), "random pause"

    def short_delay(self) -> int:
        """Pause after a number that was not messaged (invalid / failed)."""
        return self.rng.randint(5, 12)

    def needs_warning(self, sent: int) -> bool:
        """True when the run just crossed the "may get blocked" threshold."""
        w = self.s.warn_after
        return bool(w) and sent > 0 and sent % w == 0

    def over_daily_limit(self, sent_today: int) -> bool:
        limit = self.s.daily_limit
        return bool(limit) and sent_today >= limit


# --------------------------------------------------------------------------- #
# history
# --------------------------------------------------------------------------- #

def _now() -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0)


@dataclass
class HistoryEntry:
    number: str
    name: str = ""
    status: str = SENT
    at: str = ""                 # ISO timestamp of the latest attempt
    first_sent: str = ""         # ISO timestamp of the first successful send
    last_sent: str = ""          # ISO timestamp of the latest successful send
    attempts: int = 0
    error: str = ""
    city: str = ""
    category: str = ""


class History:
    """Every number the bulk sender touched, keyed by ``wa.me`` digits."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or paths.state_file(HISTORY_FILE)
        self.entries: Dict[str, HistoryEntry] = {}
        self.load()

    # -- storage ----------------------------------------------------------
    def load(self) -> None:
        self.entries = {}
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        known = {f.name for f in fields(HistoryEntry)}
        for row in data.get("entries", []) if isinstance(data, dict) else []:
            if not isinstance(row, dict) or not row.get("number"):
                continue
            entry = HistoryEntry(**{k: v for k, v in row.items() if k in known})
            self.entries[entry.number] = entry

    def save(self) -> None:
        folder = os.path.dirname(self.path) or "."
        os.makedirs(folder, exist_ok=True)
        payload = {"version": 1,
                   "entries": [asdict(e) for e in self.entries.values()]}
        fd, tmp = tempfile.mkstemp(prefix=".history-", dir=folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # -- queries ----------------------------------------------------------
    def get(self, number: str) -> Optional[HistoryEntry]:
        return self.entries.get(contacts.digits_only(number))

    def was_contacted(self, number: str) -> bool:
        """True once a message to this number actually went out."""
        entry = self.get(number)
        return bool(entry and (entry.status == SENT or entry.first_sent))

    def sent_on(self, day: datetime.date) -> int:
        prefix = day.isoformat()
        return sum(1 for e in self.entries.values()
                   if e.last_sent.startswith(prefix))

    def sent_today(self) -> int:
        return self.sent_on(_now().date())

    # -- updates ----------------------------------------------------------
    def record(self, number: str, status: str, *, name: str = "",
               error: str = "", lead: Optional[Mapping[str, Any]] = None,
               when: Optional[datetime.datetime] = None,
               save: bool = True) -> HistoryEntry:
        digits = contacts.digits_only(number)
        stamp = (when or _now()).isoformat()
        entry = self.entries.get(digits) or HistoryEntry(number=digits)
        entry.name = name or entry.name
        entry.attempts += 1
        entry.at = stamp
        entry.error = error
        if lead:
            entry.city = str(lead.get("city") or entry.city or "")
            entry.category = str(lead.get("category") or entry.category or "")
        # a later failure never hides that the lead was already messaged
        if status == SENT:
            entry.status = SENT
            entry.first_sent = entry.first_sent or stamp
            entry.last_sent = stamp
        elif not entry.first_sent:
            entry.status = status
        self.entries[digits] = entry
        if save:
            self.save()
        return entry

    def forget(self, number: str) -> bool:
        removed = self.entries.pop(contacts.digits_only(number), None) is not None
        if removed:
            self.save()
        return removed

    def export_csv(self, path: str) -> str:
        cols = [f.name for f in fields(HistoryEntry)]
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(cols)
            for entry in sorted(self.entries.values(), key=lambda e: e.at):
                writer.writerow([getattr(entry, c) for c in cols])
        return path


# --------------------------------------------------------------------------- #
# queue
# --------------------------------------------------------------------------- #

@dataclass
class OutreachItem:
    number: str                  # wa.me digits
    name: str
    message: str
    lead: Dict[str, Any] = field(repr=False, default_factory=dict)
    contacted: bool = False      # already in the history as sent
    status: str = ""             # filled in while the run goes


def build_queue(leads: Iterable[Mapping[str, Any]], template: str, *,
                dial: str = "", iso: str = "",
                history: Optional[History] = None,
                skip_contacted: bool = True,
                when: Optional[datetime.datetime] = None) -> List[OutreachItem]:
    """One item per distinct WhatsApp number, in the order given.

    Leads without a usable number are dropped. With ``skip_contacted`` the
    numbers already messaged (per ``history``) are dropped too; otherwise they
    stay in, flagged ``contacted=True`` so the UI can leave them unticked.
    """
    seen = set()
    queue: List[OutreachItem] = []
    for lead in leads:
        number = contacts.whatsapp_number(lead, dial, iso)
        if not number or number in seen:
            continue
        seen.add(number)
        contacted = bool(history and history.was_contacted(number))
        if contacted and skip_contacted:
            continue
        queue.append(OutreachItem(
            number=number,
            name=str(lead.get("name") or "").strip() or number,
            message=contacts.render_template(template, lead, when=when),
            lead=dict(lead),
            contacted=contacted,
        ))
    return queue


def estimate_seconds(count: int, settings: SafetySettings) -> int:
    """Rough duration of a run of `count` messages (average pauses + rests)."""
    if count <= 0:
        return 0
    s = settings.normalized()
    per_message = 15                                   # load + send
    pauses = (count - 1) * (s.min_delay + s.max_delay) / 2
    rests = 0
    if s.burst_size:
        rests = ((count - 1) // s.burst_size) * s.burst_rest
    return int(count * per_message + pauses + rests)


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"


def counts(items: Sequence[OutreachItem]) -> Dict[str, int]:
    out = {SENT: 0, FAILED: 0, INVALID: 0, SKIPPED: 0}
    for item in items:
        if item.status in out:
            out[item.status] += 1
    return out
