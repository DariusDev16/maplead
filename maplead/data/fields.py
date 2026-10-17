"""
The "what do you want to extract" catalogue.

Each field declares which providers can actually return it, so the CLI can warn
about silent gaps (e.g. e-mail needs Outscraper enrichment).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    group: str
    providers: Tuple[str, ...]
    kind: str = "text"     # text | number | url | bool
    note: str = ""
    enriched: bool = False  # only via paid enrichment endpoint

    @property
    def provider_note(self) -> str:
        """Human list of the services that can return this field."""
        pretty = {"google": "Google Places", "outscraper": "Outscraper",
                  "serpapi": "SerpApi", "dataforseo": "DataForSEO", "demo": "Demo"}
        return " / ".join(pretty.get(p, p.title()) for p in self.providers)


def _f(key, label, group, providers, kind="text", note="", enriched=False) -> Field:
    return Field(key, label, group, tuple(providers), kind, note, enriched)


_ALL = ("google", "outscraper", "serpapi", "dataforseo", "demo")

FIELDS: Tuple[Field, ...] = (
    # identity
    _f("name", "Business name", "Identity", _ALL),
    _f("category", "Business category / type", "Identity", _ALL),
    _f("subcategory", "Secondary categories", "Identity", ("google", "serpapi", "demo")),
    _f("place_id", "Google place_id", "Identity", _ALL),
    _f("maps_url", "Google Maps link", "Identity", _ALL, "url"),
    _f("status", "Operational status", "Identity", ("google", "serpapi", "dataforseo", "outscraper", "demo"),
       note="OPERATIONAL / CLOSED_TEMPORARILY"),
    _f("business_type", "Business type label", "Identity", ("google", "demo")),

    # location
    _f("address", "Full street address", "Location", _ALL),
    _f("street", "Street + number", "Location", ("outscraper", "serpapi", "dataforseo", "demo")),
    _f("city", "City", "Location", _ALL),
    _f("region", "State / province", "Location", _ALL),
    _f("postal_code", "Postcode / ZIP", "Location", _ALL),
    _f("country", "Country", "Location", _ALL),
    _f("country_code", "Country code", "Location", _ALL),
    _f("latitude", "Latitude", "Location", _ALL, "number"),
    _f("longitude", "Longitude", "Location", _ALL, "number"),
    _f("distance", "Distance (search result)", "Location", ("serpapi", "demo"), "number"),

    # contact
    _f("phone", "Phone number", "Contact", _ALL),
    _f("website", "Website", "Contact", _ALL, "url"),
    _f("email", "E-mail address", "Contact", ("outscraper", "demo"), "url",
       note="Outscraper enrichment or --demo", enriched=True),
    _f("whatsapp", "WhatsApp number", "Contact", ("outscraper", "demo"), enriched=True),
    _f("facebook", "Facebook page", "Contact", ("outscraper", "demo"), "url", enriched=True),
    _f("instagram", "Instagram profile", "Contact", ("outscraper", "demo"), "url", enriched=True),
    _f("linkedin", "LinkedIn company page", "Contact", ("outscraper", "demo"), "url", enriched=True),

    # reputation
    _f("rating", "Average rating", "Reputation", _ALL, "number"),
    _f("reviews", "Review count", "Reputation", _ALL, "number"),
    _f("price_level", "Price level", "Reputation", _ALL, note="$ / $$ / $$$, Value for money"),

    # operations
    _f("hours", "Opening hours", "Operations", ("google", "outscraper", "demo")),
    _f("open_now", "Open now", "Operations", ("google", "serpapi", "outscraper", "demo"), "bool"),
    _f("is_chain", "Is a chain", "Operations", ("outscraper", "dataforseo", "demo"), "bool"),
    _f("chain_name", "Chain / brand name", "Operations", ("outscraper", "dataforseo", "demo")),
    _f("logo_url", "Logo image URL", "Operations", ("outscraper", "demo"), "url"),
    _f("photos_count", "Photos on Google", "Operations", ("outscraper", "google", "demo"), "number"),
    _f("year_established", "Year established", "Operations", ("outscraper", "demo"), "number",
       enriched=True),
    _f("employees", "Employee count", "Operations", ("outscraper", "demo"), "number", enriched=True),
)

BY_KEY: Dict[str, Field] = {f.key: f for f in FIELDS}
GROUPS: Tuple[str, ...] = tuple(dict.fromkeys(f.group for f in FIELDS))

# what a sales team usually wants first
RECOMMENDED: Tuple[str, ...] = (
    "name", "category", "address", "city", "region", "postal_code", "country",
    "phone", "website", "rating", "reviews", "place_id", "maps_url",
)

# the always-present spine
BASIC: Tuple[str, ...] = ("name", "category", "address", "city", "phone", "website", "maps_url")

SALES_READY: Tuple[str, ...] = (
    "name", "category", "address", "city", "region", "postal_code", "country", "country_code",
    "phone", "website", "email", "rating", "reviews", "maps_url", "place_id", "status",
)

EVERYTHING: Tuple[str, ...] = tuple(f.key for f in FIELDS)

PRESETS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("rec", "recommended sales fields", RECOMMENDED),
    ("basic", "just the essentials", BASIC),
    ("sales", "sales-ready + e-mail", SALES_READY),
    ("all", "every field the API returns", EVERYTHING),
)


def group_of(key: str) -> str:
    return BY_KEY[key].group if key in BY_KEY else "Other"


def supported_by(keys: Sequence[str], provider: str) -> List[str]:
    return [k for k in keys if k in BY_KEY and provider in BY_KEY[k].providers]


def unsupported_by(keys: Sequence[str], provider: str) -> List[str]:
    return [k for k in keys if k in BY_KEY and provider not in BY_KEY[k].providers]


def parse_selection(raw: str) -> List[str]:
    """Parse 'name,phone,rating' / 'all' / 'rec' / 'basic' / 'sales' / csv of keys."""
    t = (raw or "").strip().lower()
    if not t:
        return []
    if t in ("all", "*"):
        return list(EVERYTHING)
    for pkey, _, keys in PRESETS:
        if t == pkey:
            return list(keys)
    out: List[str] = []
    for chunk in t.replace(";", ",").split(","):
        chunk = chunk.strip().lower().replace(" ", "_")
        if not chunk:
            continue
        if chunk in BY_KEY:
            out.append(chunk)
            continue
        hits = [k for k in BY_KEY if chunk in k]
        out.extend(hits)
    seen, res = set(), []
    for k in out:
        if k not in seen:
            seen.add(k)
            res.append(k)
    return res