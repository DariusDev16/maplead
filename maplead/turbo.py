"""
Turbo mode: walk a list of cities and, in each one, a list of business types.

For every (city, business) pair the GUI runs a search, keeps the leads that pass
the chosen filter (for example *No website*) and hands them to the bulk WhatsApp
sender; when that queue is empty it moves to the next business, and after the
last business to the next city.

Pure standard library, like ``outreach.py``: the order of the steps, the lead
filter and the "already done" memory live here so they can be tested without a
display. The GUI part is ``maplead/gui/turbo.py``.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import contacts, paths
from .data import verticals as VT

PROGRESS_FILE = "turbo-progress.json"

# lead filters the turbo run can apply (key, label) — the keys match the leads
# panel's filters, so "No website" means the same thing in both places
FILTERS: Tuple[Tuple[str, str], ...] = (
    ("nos", "No website"),
    ("site", "Has website"),
    ("email", "Has e-mail"),
    ("wa", "Every lead with WhatsApp"),
)
DEFAULT_FILTER = "nos"


def business_terms(text: str) -> Tuple[str, List[str]]:
    """The label and the search phrases for a business typed or picked."""
    text = (text or "").strip()
    hits = VT.resolve(text) if text else []
    if hits:
        vertical = hits[0]
        return vertical.label, [vertical.query] + list(vertical.synonyms[:2])
    return text, [text]


def passes_filter(lead: Mapping[str, Any], key: str) -> bool:
    if key == "nos":
        return not contacts.has_real_website(lead)
    if key == "site":
        return contacts.has_real_website(lead)
    if key == "email":
        return bool(str(lead.get("email") or "").strip())
    return True


def filter_leads(leads: Iterable[Mapping[str, Any]], key: str) -> List[Mapping[str, Any]]:
    return [lead for lead in leads if passes_filter(lead, key)]


# --------------------------------------------------------------------------- #
# steps
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Step:
    city: str
    region: str
    business: str

    @property
    def label(self) -> str:
        return f"{self.business} in {self.city}"


def build_steps(cities: Sequence[Tuple[str, str]],
                businesses: Sequence[str]) -> List[Step]:
    """City by city, every business in order: (city 1, biz 1), (city 1, biz 2)…"""
    steps: List[Step] = []
    seen = set()
    for city, region in cities:
        city = (city or "").strip()
        if not city:
            continue
        for business in businesses:
            business = (business or "").strip()
            key = (city.lower(), business.lower())
            if not business or key in seen:
                continue
            seen.add(key)
            steps.append(Step(city=city, region=(region or "").strip(),
                              business=business))
    return steps


def step_key(iso: str, step: Step, filter_key: str) -> str:
    return "|".join(part.strip().lower()
                    for part in (iso or "", step.city, step.business, filter_key))


# --------------------------------------------------------------------------- #
# progress memory
# --------------------------------------------------------------------------- #

class Progress:
    """Which (country, city, business, filter) steps a turbo run already finished.

    A step is recorded once its search ran and every lead it produced was
    handled, so stopping and starting again continues where the run left off
    instead of paying for the same searches twice.
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path or paths.state_file(PROGRESS_FILE)
        self.done: Dict[str, str] = {}
        self.load()

    def load(self) -> None:
        self.done = {}
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        done = data.get("done") if isinstance(data, dict) else None
        if isinstance(done, dict):
            self.done = {str(k): str(v) for k, v in done.items()}

    def save(self) -> None:
        folder = os.path.dirname(self.path) or "."
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".turbo-", dir=folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "done": self.done}, fh,
                          ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def is_done(self, key: str) -> bool:
        return key in self.done

    def mark(self, key: str) -> None:
        self.done[key] = datetime.datetime.now().replace(microsecond=0).isoformat()
        self.save()

    def clear(self) -> None:
        self.done = {}
        self.save()

    def pending(self, iso: str, steps: Sequence[Step], filter_key: str) -> List[Step]:
        return [s for s in steps if not self.is_done(step_key(iso, s, filter_key))]
