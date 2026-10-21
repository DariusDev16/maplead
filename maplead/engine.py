"""
Engine: turn a search plan into deduplicated, filtered lead rows.

Google's Places API only returns 60 results per *text query*, so the engine
widens the net by generating query variants (synonyms, neighbourhoods,
"near me" phrasing) until the target volume is reached or variants run out.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .providers import Provider, SearchRequest, SearchResult

# --------------------------------------------------------------------------- #
# query planning
# --------------------------------------------------------------------------- #

_STOP = {"the", "a", "an", "and", "of", "in", "near", "me", "my", "area"}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def location_bits(city: str, region: str, country: str) -> str:
    bits = [b for b in (city, region, country) if b and b.strip()]
    seen, out = set(), []
    for b in bits:
        k = b.strip().lower()
        if k not in seen:
            seen.add(k)
            out.append(b.strip())
    return ", ".join(out)


def build_queries(city: str, region: str, country: str, terms: Sequence[str],
                  limit: int, cap: int, districts: Sequence[str] = ()) -> List[str]:
    """Ordered, de-duplicated query list covering the whole search volume."""
    loc = location_bits(city, region, country)
    queries: List[str] = []
    seen = set()

    def push(q: str) -> None:
        key = q.lower().strip()
        if key and key not in seen and len(key) <= 250:
            seen.add(key)
            queries.append(q)

    # tier 1 - the requested term(s), most specific first
    for term in terms:
        if not term:
            continue
        push(f"{term} in {loc}" if loc else term)

    # tier 2 - needed only if tier 1 cannot fill `limit` (provider per-query cap)
    if len(queries) * cap < limit:
        for term in terms:
            if loc:
                push(f"{term} near {loc}")
        for term in terms:
            for d in districts:
                if loc:
                    push(f"{term} in {d}, {loc}")

    return queries


def district_seeds(region: str, districts: Sequence[str] = ()) -> List[str]:
    out = [d.strip() for d in districts if d and d.strip()]
    if region:
        out.extend([p.strip() for p in re.split(r"[,;/|]", region) if p.strip()])
    seen, uniq = set(), []
    for d in out:
        if d.lower() not in seen:
            seen.add(d.lower())
            uniq.append(d)
    return uniq


# --------------------------------------------------------------------------- #
# normalisation / cleaning
# --------------------------------------------------------------------------- #

def normalize(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Fill derived fields so every row is self-consistent."""
    out = dict(lead)
    name = (out.get("name") or "").strip()
    out["name"] = name or "(unnamed business)"

    if not out.get("maps_url") and out.get("place_id"):
        pid = out["place_id"]
        out["maps_url"] = f"https://www.google.com/maps/search/?api=1&query={pid}&query_place_id={pid}"

    rating = out.get("rating")
    if isinstance(rating, str):
        try:
            out["rating"] = float(rating.rstrip("★ ").strip())
        except ValueError:
            out["rating"] = None

    reviews = out.get("reviews")
    if isinstance(reviews, str):
        m = re.search(r"[\d,]+", reviews)
        out["reviews"] = int(m.group().replace(",", "")) if m else None

    if out.get("website") and not str(out["website"]).startswith("http"):
        out["website"] = f"https://{str(out['website']).lstrip('/')}"

    for key in ("email", "facebook", "instagram", "linkedin", "logo_url", "whatsapp"):
        val = out.get(key)
        if isinstance(val, list):
            val = val[0] if val else ""
        out[key] = (val or "").strip() if isinstance(val, str) else val

    out["_scraped_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    return out


def dedupe_key(lead: Dict[str, Any]) -> str:
    if lead.get("place_id"):
        return f"pid:{str(lead['place_id']).strip().lower()}"
    parts = [
        slug(lead.get("name", "")),
        slug(lead.get("address") or lead.get("street") or ""),
        slug(lead.get("city", "")),
    ]
    return "|".join(parts)


def dedupe(leads: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    seen: Dict[str, Dict[str, Any]] = {}
    dupes = 0
    for lead in leads:
        key = dedupe_key(lead)
        if key in seen:
            dupes += 1
            # keep the richer record
            existing = seen[key]
            if sum(bool(v) for v in lead.values()) > sum(bool(v) for v in existing.values()):
                seen[key] = lead
            continue
        seen[key] = lead
    return list(seen.values()), dupes


# --------------------------------------------------------------------------- #
# phone types (mobile vs landline)
# --------------------------------------------------------------------------- #

# Dial code -> ISO, so a number can be classified even when only the dial is
# known (the plan always carries the ISO, the demo/imported rows may not).
_DIAL_ISO = {
    "55": "br", "351": "pt", "34": "es", "44": "gb", "49": "de", "33": "fr",
    "39": "it", "31": "nl", "353": "ie", "61": "au", "57": "co", "51": "pe",
    "56": "cl",
}
_ISO_DIAL = {iso: dial for dial, iso in _DIAL_ISO.items()}

# Countries whose national numbers start with a trunk "0" that the rules skip.
_TRUNK_ZERO = {"gb", "de", "fr", "nl", "ie", "au"}

# iso -> (mobile regex, landline regex) over the national number. Countries
# where the two formats cannot be told apart (US, Canada, Mexico…) are absent
# on purpose: guessing there would throw away perfectly good mobiles.
_PHONE_RULES = {
    "br": (r"[1-9]{2}9\d{8}", r"[1-9]{2}[2-5]\d{7}"),
    "pt": (r"9\d{8}", r"2\d{8}"),
    "es": (r"[67]\d{8}", r"9\d{8}"),
    "gb": (r"7\d{9}", r"[123]\d{8,9}"),
    "de": (r"1[567]\d{8,9}", r"[2-9]\d{5,11}"),
    "fr": (r"[67]\d{8}", r"[1-59]\d{8}"),
    "it": (r"3\d{8,9}", r"0\d{6,10}"),
    "nl": (r"6\d{8}", r"[1-57]\d{8}"),
    "ie": (r"8[356789]\d{7}", r"[1245679]\d{6,8}"),
    "au": (r"4\d{8}", r"[2378]\d{8}"),
    "co": (r"3\d{9}", r"[1-8]\d{6,9}"),
    "pe": (r"9\d{8}", r"0\d{6,8}"),
    "cl": (r"9\d{8}", r"[2-8]\d{7,8}"),
}


def _match_phone_rule(iso: str, number: str) -> str:
    mobile, landline = _PHONE_RULES[iso]
    if iso in _TRUNK_ZERO and number.startswith("0"):
        number = number[1:]
    if re.fullmatch(mobile, number):
        return "mobile"
    if re.fullmatch(landline, number):
        return "landline"
    return "unknown"


def phone_type(phone: str, country_code: str = "", dial: str = "") -> str:
    """Classify a phone number as ``mobile``, ``landline`` or ``unknown``.

    Google returns national numbers, so the rules are per country and purely
    prefix based: a Brazilian mobile has 9 digits after the area code, a German
    one starts 015/016/017, a French one 06/07, and so on. Numbers from
    countries without a separate mobile range stay ``unknown`` rather than
    being guessed as landlines.
    """
    digits = re.sub(r"\D+", "", phone or "")
    if not digits:
        return "unknown"

    iso = (country_code or "").strip().lower()
    country_dial = re.sub(r"\D+", "", dial or "")
    international = (phone or "").strip().startswith("+")
    if international and not country_dial:
        # "+55 11 91234-5678" carries its own country code
        for code in sorted(_DIAL_ISO, key=len, reverse=True):
            if digits.startswith(code):
                country_dial = code
                break
    if not iso:
        for code in sorted(_DIAL_ISO, key=len, reverse=True):
            if country_dial.startswith(code):
                iso = _DIAL_ISO[code]
                break
    if iso not in _PHONE_RULES:
        return "unknown"

    country_dial = country_dial or _ISO_DIAL.get(iso, "")
    if international and country_dial and digits.startswith(country_dial):
        digits = digits[len(country_dial):]

    kind = _match_phone_rule(iso, digits)
    if kind == "unknown" and not international and country_dial:
        # national number sent with the country code glued on ("5511912345678")
        rest = digits[len(country_dial):]
        if digits.startswith(country_dial) and len(rest) >= 8:
            kind = _match_phone_rule(iso, rest)
    return kind


def apply_filters(leads: Sequence[Dict[str, Any]], min_rating: float | None = None,
                  min_reviews: int | None = None, require_phone: bool = False,
                  require_website: bool = False,
                  skip_closed: bool = False, skip_landlines: bool = False,
                  country_code: str = "",
                  dial: str = "") -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    stats = {"min_rating": 0, "min_reviews": 0, "require_phone": 0,
             "require_website": 0, "skip_closed": 0, "skip_landlines": 0}
    out = []
    for lead in leads:
        if min_rating is not None:
            r = lead.get("rating")
            if r is None or float(r) < min_rating:
                stats["min_rating"] += 1
                continue
        if min_reviews is not None:
            n = lead.get("reviews")
            if n is None or int(n) < min_reviews:
                stats["min_reviews"] += 1
                continue
        if require_phone and not lead.get("phone"):
            stats["require_phone"] += 1
            continue
        if skip_landlines:
            phone = str(lead.get("phone") or "")
            if not phone or phone_type(phone, country_code, dial) == "landline":
                stats["skip_landlines"] += 1
                continue
        if require_website and not lead.get("website"):
            stats["require_website"] += 1
            continue
        if skip_closed and str(lead.get("status", "")).upper().startswith("CLOSED"):
            stats["skip_closed"] += 1
            continue
        out.append(lead)
    return out, stats


# --------------------------------------------------------------------------- #
# plan
# --------------------------------------------------------------------------- #


@dataclass
class SearchPlan:
    provider: Provider
    city: str
    region: str
    country: str
    country_code: str
    dial: str
    terms: List[str]
    fields: List[str]
    limit: int = 60
    language: str = "en"
    min_rating: Optional[float] = None
    min_reviews: Optional[int] = None
    require_phone: bool = False
    require_website: bool = False
    skip_closed: bool = False
    skip_landlines: bool = False
    enrich: bool = False
    districts: List[str] = field(default_factory=list)

    @property
    def location(self) -> Dict[str, str]:
        return {
            "city": self.city, "region": self.region, "country": self.country,
            "country_code": self.country_code, "dial": self.dial,
        }

    @property
    def location_label(self) -> str:
        return location_bits(self.city, self.region, self.country)

    @property
    def label(self) -> str:
        terms = ", ".join(self.terms)
        return f"{terms} in {self.location_label}" if self.location_label else terms

    def queries(self) -> List[str]:
        qs = build_queries(self.city, self.region, self.country, self.terms,
                           self.limit, self.provider.per_query_cap,
                           district_seeds(self.region, self.districts))
        per = self.provider.per_query_cap
        max_needed = max(1, -(-self.limit // max(per, 1)))
        # +2 spare variants: quality filters usually shrink each batch
        return qs[: max(1, max_needed + 2)] if len(qs) > 1 else qs


@dataclass
class HarvestReport:
    queries_run: List[str] = field(default_factory=list)
    raw_count: int = 0
    unique_count: int = 0
    duplicates: int = 0
    filtered: Dict[str, int] = field(default_factory=dict)
    enriched: int = 0
    errors: List[str] = field(default_factory=list)
    elapsed: float = 0.0


def harvest(plan: SearchPlan,
            progress: Callable[[str], None] | None = None,
            should_stop: Callable[[], bool] | None = None) -> Tuple[List[Dict[str, Any]], HarvestReport]:
    """
    Run the plan across query variants until `limit` leads survive filtering,
    or the variants run out. Filtering happens after every batch so a narrow
    quality filter (min rating, phone required) still yields a full result set.
    """
    from .net import ApiError

    t0 = time.time()
    report = HarvestReport()
    collected: List[Dict[str, Any]] = []
    queries = plan.queries()
    unique: List[Dict[str, Any]] = []
    filtered: List[Dict[str, Any]] = []
    last_stats: Dict[str, int] = {}

    if progress:
        progress(f"planning {len(queries)} quer{'y' if len(queries) == 1 else 'ies'} "
                 f"(provider cap {plan.provider.per_query_cap}/query)")

    def settle() -> None:
        nonlocal unique, filtered, last_stats
        unique, dupes = dedupe(collected)
        report.duplicates = dupes
        report.unique_count = len(unique)
        filtered, last_stats = apply_filters(
            unique, plan.min_rating, plan.min_reviews,
            plan.require_phone, plan.require_website, plan.skip_closed,
            plan.skip_landlines, plan.country_code, plan.dial)

    for i, query in enumerate(queries, 1):
        if should_stop and should_stop():
            report.errors.append("stopped by user")
            break
        if len(filtered) >= plan.limit:
            break

        need = plan.limit - len(filtered)
        req = SearchRequest(
            query=query,
            location=plan.location,
            limit=max(need, min(need, plan.provider.per_query_cap)),
            fields=plan.fields,
            language=plan.language,
        )
        if progress:
            progress(f"query {i}/{len(queries)}: {query}")
        try:
            result: SearchResult = plan.provider.search(req)
        except ApiError as exc:
            report.errors.append(str(exc))
            if progress:
                progress(f"query failed: {exc}")
            if i == 1:
                break
            continue
        except KeyboardInterrupt:
            report.errors.append("interrupted")
            break

        report.queries_run.append(query)
        report.raw_count += len(result.leads)
        for lead in result.leads:
            lead = normalize(lead)
            lead["_query"] = query
            lead["_source"] = plan.provider.name
            collected.append(lead)
        settle()
        if progress:
            progress(f"got {len(result.leads)} · {len(filtered)} usable "
                     f"({len(collected)} seen)")

        if result.exhausted:
            break

    settle()
    report.filtered = {k: v for k, v in last_stats.items() if v}
    filtered = filtered[: plan.limit]

    enricher = getattr(plan.provider, "enrich", None)
    if plan.enrich and callable(enricher) and any(f in plan.fields for f in
                                                  ("email", "facebook", "instagram", "linkedin")):
        if progress:
            progress("enriching contacts (may use extra credits)")
        try:
            report.enriched = enricher(filtered, plan)
        except ApiError as exc:
            report.errors.append(f"enrichment failed: {exc}")

    report.elapsed = time.time() - t0
    return filtered, report


# --------------------------------------------------------------------------- #

def summarize(leads: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Quick profile of the harvested set (shown after the run)."""
    def avg(vals: List[float]) -> float:
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    ratings = [float(l["rating"]) for l in leads if isinstance(l.get("rating"), (int, float))]
    review_totals = [int(l["reviews"]) for l in leads
                     if isinstance(l.get("reviews"), (int, float))]
    cities: Dict[str, int] = {}
    cats: Dict[str, int] = {}
    for l in leads:
        if l.get("city"):
            cities[l["city"]] = cities.get(l["city"], 0) + 1
        if l.get("category"):
            cats[l["category"]] = cats.get(l["category"], 0) + 1
    return {
        "total": len(leads),
        "with_phone": sum(1 for l in leads if l.get("phone")),
        "with_website": sum(1 for l in leads if l.get("website")),
        "with_email": sum(1 for l in leads if l.get("email")),
        "avg_rating": avg(ratings),
        "avg_reviews": avg([float(x) for x in review_totals]),
        "total_reviews": sum(review_totals),
        "top_cities": sorted(cities.items(), key=lambda kv: -kv[1])[:5],
        "top_categories": sorted(cats.items(), key=lambda kv: -kv[1])[:5],
    }