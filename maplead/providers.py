"""
Lead providers: pluggable Google-Maps scraper APIs.

    google      official Google Places API (New)      -> GOOGLE_MAPS_API_KEY
    outscraper  outscraper.com (richest field set)    -> OUTSCRAPER_API_KEY
    serpapi     serpapi.com google_maps engine        -> SERPAPI_API_KEY
    dataforseo  dataforseo.com business_data maps     -> DATAFORSEO_LOGIN/PASSWORD
    demo        offline generator, no key needed      -> --demo

Every provider returns the same normalised Lead dicts so the CLI/exporters
stay provider-agnostic.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .net import ApiError, RateLimiter, get_json, post_json

# --------------------------------------------------------------------------- #
# lead model
# --------------------------------------------------------------------------- #


@dataclass
class SearchRequest:
    query: str                 # full text query, e.g. "plumber in Berlin, Germany"
    location: Dict[str, str]   # city / region / country / country_code
    limit: int = 60
    fields: Sequence[str] = ()
    language: str = "en"
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    leads: List[Dict[str, Any]]
    query: str
    exhausted: bool = False    # provider says there is nothing more
    raw_total: int = 0
    error: Optional[str] = None


Lead = Dict[str, Any]


def _blank() -> Lead:
    return {
        "name": "", "category": "", "subcategory": "", "place_id": "",
        "maps_url": "", "status": "", "business_type": "",
        "address": "", "street": "", "city": "", "region": "",
        "postal_code": "", "country": "", "country_code": "",
        "latitude": None, "longitude": None, "distance": None,
        "phone": "", "website": "", "email": "", "whatsapp": "",
        "facebook": "", "instagram": "", "linkedin": "",
        "rating": None, "reviews": None, "price_level": "",
        "hours": "", "open_now": None, "is_chain": None, "chain_name": "",
        "logo_url": "", "photos_count": None, "year_established": None,
        "employees": None,
    }


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def _dig(obj: Any, *path: str, default: Any = "") -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return default if cur is None else cur


def maps_link(place_id: str, lat: Any = None, lon: Any = None) -> str:
    if place_id:
        return f"https://www.google.com/maps/search/?api=1&query={place_id}&query_place_id={place_id}"
    if lat is not None and lon is not None:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    return ""


# --------------------------------------------------------------------------- #
# base
# --------------------------------------------------------------------------- #


class Provider:
    name = "base"
    label = "Base provider"
    env_keys: Tuple[str, ...] = ()
    homepage = ""
    docs = ""
    #: hard ceiling of results the API returns per text query
    per_query_cap = 60

    def __init__(self, **config: Any):
        self.config = config
        self.limiter = RateLimiter(self.config.get("rate", 5.0))

    # -- key detection --------------------------------------------------- #
    @classmethod
    def api_key(cls) -> Optional[str]:
        for var in cls.env_keys:
            val = os.environ.get(var, "").strip()
            if val:
                return val
        return None

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.api_key())

    # -- api ------------------------------------------------------------- #
    def search(self, req: SearchRequest) -> SearchResult:  # pragma: no cover
        raise NotImplementedError

    def validate(self) -> Tuple[bool, str]:
        """Cheap live round-trip to confirm the key works. Raises ApiError if not."""
        raise NotImplementedError

    def supports(self, field_key: str) -> bool:
        from .data import fields as F
        meta = F.BY_KEY.get(field_key)
        return bool(meta and self.name in meta.providers)

    def describe(self) -> str:
        key = self.api_key()
        masked = (key[:6] + "…" + key[-4:]) if key and len(key) > 12 else ("set" if key else "missing")
        return f"{self.label:<14} key: {masked}"


# --------------------------------------------------------------------------- #
# 1. Google Places API (New)
# --------------------------------------------------------------------------- #

_GOOGLE_FIELD_MAP = {
    "name": "displayName",
    "category": "primaryTypeDisplayName",
    "subcategory": "types",
    "place_id": "id",
    "status": "businessStatus",
    "business_type": "businessType",
    "address": "formattedAddress",
    "street": "shortFormattedAddress",
    "latitude": "location",
    "longitude": "location",
    "phone": "nationalPhoneNumber",
    "website": "websiteUri",
    "rating": "rating",
    "reviews": "userRatingCount",
    "price_level": "priceLevel",
    "hours": "regularOpeningHours",
    "open_now": "currentOpeningHours",
    "photos_count": "photos",
}

_GOOGLE_TOP_LEVEL = {"id", "displayName", "formattedAddress", "shortFormattedAddress",
                      "nationalPhoneNumber", "websiteUri", "rating", "userRatingCount",
                      "priceLevel", "businessStatus", "businessType", "location",
                      "regularOpeningHours", "currentOpeningHours", "photos"}

_GOOGLE_PRICE = {0: "Free", 1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}


class GooglePlacesProvider(Provider):
    name = "google"
    label = "Google Places"
    env_keys = ("GOOGLE_MAPS_API_KEY", "GOOGLE_API_KEY")
    homepage = "https://developers.google.com/maps/documentation/places/web-service"
    per_query_cap = 60

    def _mask(self, fields: Sequence[str]) -> str:
        parts: List[str] = []
        for f in fields:
            mapped = _GOOGLE_FIELD_MAP.get(f)
            if not mapped:
                continue
            if mapped in _GOOGLE_TOP_LEVEL:
                parts.append(mapped)
            else:
                parts.append(f"{mapped}.name" if mapped == "types" else mapped)
        base = ["id", "displayName", "formattedAddress", "location"]
        return ",".join(dict.fromkeys(base + parts))

    def validate(self) -> Tuple[bool, str]:
        key = self.api_key()
        if not key:
            return False, "GOOGLE_MAPS_API_KEY is empty"
        resp = post_json(
            "https://places.googleapis.com/v1/places:searchText",
            body={"textQuery": "cafe in New York", "pageSize": 1, "languageCode": "en"},
            headers={"X-Goog-Api-Key": key,
                     "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress"},
            provider=self.name, retries=1, timeout=30,
        )
        n = len(resp.get("places", []) or [])
        return True, f"Places API (New) reachable - test query returned {n} place(s)"

    def _place(self, raw: Dict[str, Any], req: SearchRequest) -> Lead:
        lead = _blank()
        lat = _dig(raw, "location", "latitude")
        lon = _dig(raw, "location", "longitude")
        lead.update({
            "name": _clean(_dig(raw, "displayName", "text")),
            "place_id": raw.get("id", ""),
            "maps_url": maps_link(raw.get("id", ""), lat, lon),
            "category": _clean(_dig(raw, "primaryTypeDisplayName", "text")),
            "business_type": _clean(raw.get("businessType", "")),
            "status": _clean(raw.get("businessStatus", "")),
            "address": _clean(raw.get("formattedAddress", "")),
            "street": _clean(raw.get("shortFormattedAddress", "")),
            "latitude": lat,
            "longitude": lon,
            "phone": _clean(raw.get("nationalPhoneNumber", "")),
            "website": _clean(raw.get("websiteUri", "")),
            "rating": raw.get("rating"),
            "reviews": raw.get("userRatingCount"),
            "price_level": _GOOGLE_PRICE.get(raw.get("priceLevel"), ""),
            "photos_count": len(raw.get("photos", []) or []) or None,
        })
        types = raw.get("types") or []
        lead["subcategory"] = ", ".join(types[:4])
        hours = raw.get("regularOpeningHours") or {}
        if hours.get("weekdayDescriptions"):
            lead["hours"] = " | ".join(hours["weekdayDescriptions"])
        cur = raw.get("currentOpeningHours") or {}
        if "openNow" in cur:
            lead["open_now"] = cur["openNow"]
        loc = req.location
        lead.update({"country": loc.get("country", ""), "country_code": loc.get("country_code", ""),
                     "city": loc.get("city", ""), "region": loc.get("region", "")})
        return lead

    def search(self, req: SearchRequest) -> SearchResult:
        key = self.api_key()
        if not key:
            raise ApiError("GOOGLE_MAPS_API_KEY is not set", provider=self.name)
        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": self._mask(req.fields)}
        body: Dict[str, Any] = {"textQuery": req.query, "pageSize": min(20, max(1, req.limit))}
        if req.language:
            body["languageCode"] = req.language
        if req.location.get("country_code"):
            body["regionCode"] = req.location["country_code"].upper()

        leads: List[Lead] = []
        token = None
        pages = 0
        while len(leads) < req.limit:
            self.limiter.wait()
            if token:
                body = {"pageToken": token}
            resp = post_json(url, body=body, headers=headers, provider=self.name)
            for item in resp.get("places", []) or []:
                leads.append(self._place(item, req))
                if len(leads) >= req.limit:
                    break
            token = resp.get("nextPageToken")
            pages += 1
            if not token or pages >= 3:  # Google caps a text query at 3 pages / 60 results
                break
        return SearchResult(leads=leads, query=req.query, exhausted=not token)


# --------------------------------------------------------------------------- #
# 2. Outscraper
# --------------------------------------------------------------------------- #


class OutscraperProvider(Provider):
    name = "outscraper"
    label = "Outscraper"
    env_keys = ("OUTSCRAPER_API_KEY",)
    homepage = "https://outscraper.com"
    per_query_cap = 200

    def validate(self) -> Tuple[bool, str]:
        key = self.api_key()
        if not key:
            return False, "OUTSCRAPER_API_KEY is empty"
        resp = get_json("https://api.outscraper.com/maps/search",
                        params={"query": "cafe in London", "limit": 1, "api_key": key},
                        provider=self.name, retries=1, timeout=30)
        items = resp.get("data", []) if isinstance(resp, dict) else resp
        return True, f"maps/search reachable - test query returned {len(items or [])} place(s)"

    def _place(self, raw: Dict[str, Any], req: SearchRequest) -> Lead:
        lead = _blank()
        lat, lon = raw.get("latitude"), raw.get("longitude")
        pid = raw.get("place_id", "")
        lead.update({
            "name": _clean(raw.get("title")),
            "place_id": pid,
            "maps_url": raw.get("place_url") or maps_link(pid, lat, lon),
            "category": _clean(raw.get("category")),
            "address": _clean(raw.get("full_address") or raw.get("address")),
            "street": _clean(raw.get("address")),
            "city": _clean(raw.get("city")),
            "region": _clean(raw.get("state")),
            "postal_code": _clean(raw.get("zip_code")),
            "country": _clean(raw.get("country")),
            "country_code": _clean(raw.get("country_code")),
            "latitude": lat,
            "longitude": lon,
            "phone": _clean(raw.get("phone")),
            "website": _clean(raw.get("website")),
            "email": _clean(raw.get("email")),
            "whatsapp": _clean(raw.get("whatsapp")),
            "facebook": _clean(raw.get("facebook")),
            "instagram": _clean(raw.get("instagram")),
            "linkedin": _clean(raw.get("linkedin")),
            "rating": raw.get("rating"),
            "reviews": raw.get("reviews"),
            "price_level": _clean(raw.get("price")),
            "logo_url": _clean(raw.get("logo")),
            "is_chain": raw.get("is_chain"),
            "chain_name": _clean(raw.get("chain_name")),
            "photos_count": raw.get("photos"),
            "year_established": raw.get("year_established"),
            "employees": raw.get("employees"),
        })
        if raw.get("address_info"):
            info = raw["address_info"]
            lead["region"] = _clean(info.get("state") or lead["region"])
            lead["postal_code"] = _clean(info.get("zip_code") or lead["postal_code"])
        return lead

    def search(self, req: SearchRequest) -> SearchResult:
        key = self.api_key()
        if not key:
            raise ApiError("OUTSCRAPER_API_KEY is not set", provider=self.name)
        self.limiter.wait()
        resp = get_json(
            "https://api.outscraper.com/maps/search",
            params={
                "query": req.query,
                "limit": min(req.limit, self.per_query_cap),
                "language": req.language,
                "api_key": key,
            },
            provider=self.name,
        )
        items = resp.get("data", []) if isinstance(resp, dict) else resp
        if not isinstance(items, list):
            items = []
        leads = [self._place(i, req) for i in items if isinstance(i, dict)]
        return SearchResult(leads=leads, query=req.query, exhausted=len(leads) < req.limit)

    def enrich(self, leads: Sequence[Lead], req: SearchRequest) -> int:
        """Optional: pull e-mail / socials for leads that lack them (costs credits)."""
        key = self.api_key()
        if not key:
            return 0
        targets = [l for l in leads if l.get("place_id") and not l.get("email")][:50]
        if not targets:
            return 0
        try:
            self.limiter.wait()
            resp = get_json(
                "https://api.outscraper.com/customers/leads-list",
                params={"placeIds": ",".join(l["place_id"] for l in targets), "api_key": key},
                provider=self.name,
            )
        except ApiError:
            return 0
        items = resp.get("data", []) if isinstance(resp, dict) else resp
        index = {l["place_id"]: l for l in leads}
        hits = 0
        for item in items or []:
            target = index.get(item.get("placeId") or item.get("place_id"))
            if not target:
                continue
            for src, dst in (("emails", "email"), ("facebookLinks", "facebook"),
                             ("instagramLinks", "instagram"), ("linkedinLinks", "linkedin")):
                vals = item.get(src) or []
                if not target.get(dst):
                    if isinstance(vals, dict):
                        val = vals.get("value") or next(iter(vals.values()), "")
                    elif isinstance(vals, list) and vals:
                        val = vals[0]
                    else:
                        val = vals
                    if isinstance(val, str) and val.strip():
                        target[dst] = val.strip()
                        hits += 1
            contacts = item.get("contacts") or []
            if contacts and not target.get("email"):
                for c in contacts:
                    if isinstance(c, dict) and c.get("email"):
                        target["email"] = c["email"]
                        hits += 1
                        break
        return hits


# --------------------------------------------------------------------------- #
# 3. SerpApi
# --------------------------------------------------------------------------- #


class SerpApiProvider(Provider):
    name = "serpapi"
    label = "SerpApi"
    env_keys = ("SERPAPI_API_KEY",)
    homepage = "https://serpapi.com/google-maps-api"
    per_query_cap = 140

    def validate(self) -> Tuple[bool, str]:
        key = self.api_key()
        if not key:
            return False, "SERPAPI_API_KEY is empty"
        resp = get_json("https://serpapi.com/search.json",
                        params={"engine": "google_maps", "q": "cafe in London",
                                "limit": 1, "api_key": key},
                        provider=self.name, retries=1, timeout=30)
        n = len(resp.get("local_results", []) or [])
        return True, f"google_maps engine reachable - test query returned {n} local result(s)"

    def _place(self, raw: Dict[str, Any], req: SearchRequest) -> Lead:
        lead = _blank()
        gps = raw.get("gps_coordinates") or {}
        pid = raw.get("place_id", "")
        lead.update({
            "name": _clean(raw.get("title")),
            "place_id": pid,
            "maps_url": _clean(raw.get("place_id_link")) or maps_link(pid),
            "category": _clean(raw.get("type")),
            "subcategory": _clean(raw.get("types")),
            "address": _clean(raw.get("address")),
            "city": _clean(raw.get("address") or "").split(",")[-1].strip(),
            "country": _clean(req.location.get("country", "")),
            "country_code": _clean(req.location.get("country_code", "")),
            "latitude": gps.get("latitude"),
            "longitude": gps.get("longitude"),
            "phone": _clean(raw.get("phone")),
            "website": _clean(raw.get("website")),
            "rating": raw.get("rating"),
            "reviews": raw.get("reviews"),
            "price_level": _clean(raw.get("price")),
            "status": "OPERATIONAL" if raw.get("open_state") != "Closed" else "CLOSED",
        })
        parts = [p.strip() for p in _clean(raw.get("address", "")).split(",") if p.strip()]
        if len(parts) >= 2:
            lead["address"] = ", ".join(parts[:-1]) if len(parts) > 2 else _clean(raw.get("address"))
        lead["region"] = parts[-2] if len(parts) >= 3 else ""
        if raw.get("open_state"):
            lead["open_now"] = "Open" in str(raw.get("open_state"))
        if raw.get("distance"):
            lead["distance"] = raw.get("distance")
        return lead

    def search(self, req: SearchRequest) -> SearchResult:
        key = self.api_key()
        if not key:
            raise ApiError("SERPAPI_API_KEY is not set", provider=self.name)
        leads: List[Lead] = []
        page = 0
        exhausted = True
        while len(leads) < req.limit and page < 10:
            self.limiter.wait()
            resp = get_json(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_maps",
                    "type": "search",
                    "q": req.query,
                    "hl": req.language or "en",
                    "gl": req.location.get("country_code", ""),
                    "page": page,
                    "api_key": key,
                },
                provider=self.name,
            )
            items = resp.get("local_results") or []
            if not items:
                break
            for item in items:
                leads.append(self._place(item, req))
                if len(leads) >= req.limit:
                    exhausted = False
                    break
            pagination = resp.get("local_results_pagination") or {}
            if pagination.get("next_page") or pagination.get("next"):
                page += 1
                exhausted = False
            else:
                break
        return SearchResult(leads=leads, query=req.query, exhausted=exhausted)


# --------------------------------------------------------------------------- #
# 4. DataForSEO
# --------------------------------------------------------------------------- #

DFS_LOCATION_CODES = {
    "us": 2840, "ca": 2076, "gb": 2826, "au": 2039, "in": 2032, "de": 2756,
    "fr": 2074, "es": 2724, "it": 2759, "nl": 2789, "br": 2076, "mx": 2014,
    "za": 2710, "ng": 2754, "ke": 2548, "ae": 2785, "sa": 2682, "pl": 2916,
    "se": 2752, "ch": 2755, "tr": 2852, "id": 2944, "my": 2894, "sg": 2926,
    "ph": 2933, "th": 2941, "vn": 2961, "pk": 2880, "eg": 2597, "ar": 2012,
    "co": 2025, "cl": 2044, "pe": 2069, "nz": 2554, "ie": 2652, "pt": 2919,
}

# DataForSEO has moved this endpoint between products; try each until one sticks.
DFS_ENDPOINTS = (
    "https://api.dataforseo.com/v3/dataforseo_labs/google/maps/live/advanced",
    "https://api.dataforseo.com/v3/business_data/google/maps/live/advanced",
)


class DataForSeoProvider(Provider):
    name = "dataforseo"
    label = "DataForSEO"
    env_keys = ("DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD")
    homepage = "https://dataforseo.com/apis/google-maps-api"
    per_query_cap = 300

    def __init__(self, **config):
        super().__init__(**config)
        self._auth: Optional[str] = None
        self._locations: Optional[Dict[str, int]] = None

    def _basic_auth(self) -> str:
        if self._auth is None:
            import base64
            login = os.environ.get("DATAFORSEO_LOGIN", "")
            password = os.environ.get("DATAFORSEO_PASSWORD", "")
            if not login or not password:
                raise ApiError("DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD are not set",
                               provider=self.name)
            self._auth = base64.b64encode(f"{login}:{password}".encode()).decode()
        return self._auth

    def location_code(self, country_code: str) -> int:
        """Country ISO -> DataForSEO location_code (API appendix first, table fallback)."""
        cc = (country_code or "").lower()
        if self._locations is None:
            self._locations = dict(DFS_LOCATION_CODES)
            try:
                resp = get_json(
                    "https://api.dataforseo.com/v3/appendix/locations",
                    params={"limit": 1000},
                    headers={"Authorization": f"Basic {self._basic_auth()}"},
                    provider=self.name, retries=1, timeout=25,
                )
                for item in resp.get("results", []) or []:
                    code = item.get("location_code")
                    if code is None:
                        continue
                    for c in item.get("country_code", []) or []:
                        self._locations.setdefault(str(c).lower(), int(code))
            except (ApiError, ValueError, TypeError):
                pass
        return self._locations.get(cc, 2840)

    def validate(self) -> Tuple[bool, str]:
        auth = f"Basic {self._basic_auth()}"
        resp = get_json("https://api.dataforseo.com/v3/appendix/user_data",
                        headers={"Authorization": auth},
                        provider=self.name, retries=1, timeout=30)
        login = (resp.get("login") or "?")
        balance = resp.get("money", {}).get("balance")
        return True, f"credentials OK for login '{login}'" + (
            f" - account balance ${balance}" if balance is not None else "")

    def _place(self, raw: Dict[str, Any], req: SearchRequest) -> Lead:
        lead = _blank()
        addr = raw.get("address_info") or {}
        coords = raw.get("coordinates") or {}
        pid = str(raw.get("place_id") or "")
        lead.update({
            "name": _clean(raw.get("title")),
            "place_id": pid,
            "maps_url": _clean(raw.get("url")) or maps_link(pid),
            "category": _clean(raw.get("category")),
            "address": _clean(raw.get("address")),
            "street": _clean(addr.get("street_address") or addr.get("address_line1")),
            "city": _clean(addr.get("city")),
            "region": _clean(addr.get("region")),
            "postal_code": _clean(addr.get("zip_code") or addr.get("post_code")),
            "country": _clean(addr.get("country_name")),
            "country_code": _clean(addr.get("country_code")).upper(),
            "latitude": coords.get("latitude"),
            "longitude": coords.get("longitude"),
            "phone": _clean(raw.get("phone")),
            "website": _clean(raw.get("url_2") or raw.get("domain")),
            "rating": raw.get("rating"),
            "reviews": raw.get("reviews_count"),
            "price_level": _clean(raw.get("price")),
            "is_chain": raw.get("is_claimed"),
        })
        cid = raw.get("cid")
        if cid:
            lead["maps_url"] = f"https://www.google.com/maps?cid={cid}"
        return lead

    def search(self, req: SearchRequest) -> SearchResult:
        auth = f"Basic {self._basic_auth()}"
        code = self.location_code(req.location.get("country_code", ""))
        task = [{
            "keyword": req.query,
            "language_code": req.language or "en",
            "location_code": code,
            "limit": min(req.limit, self.per_query_cap),
            "depth": 1,
        }]
        if req.extras.get("df_location_code"):
            task[0]["location_code"] = int(req.extras["df_location_code"])

        headers = {"Authorization": auth}
        last_error: Optional[ApiError] = None
        resp: Dict[str, Any] = {}
        for endpoint in DFS_ENDPOINTS:
            self.limiter.wait()
            try:
                resp = post_json(endpoint, body=[task], headers=headers, provider=self.name)
            except ApiError as exc:
                last_error = exc
                if exc.status and exc.status != 404:
                    raise
                continue
            if str(resp.get("status_code", "")) == "40400":
                last_error = ApiError("endpoint not available", 404, self.name, resp)
                continue
            break
        else:
            raise last_error or ApiError("no DataForSEO maps endpoint responded", provider=self.name)

        tasks = resp.get("tasks") or []
        if not tasks:
            return SearchResult(leads=[], query=req.query, exhausted=True)
        status = tasks[0].get("status_code")
        if status and status != 20000:
            raise ApiError(tasks[0].get("status_message", "unknown error"),
                           status, self.name, resp)
        results = tasks[0].get("result") or []
        items = results[0].get("items") if results else []
        leads = [self._place(i, req) for i in (items or []) if isinstance(i, dict)]
        total = results[0].get("se_domain", 0) if results else 0
        return SearchResult(leads=leads, query=req.query,
                            exhausted=len(leads) < req.limit, raw_total=total)


# --------------------------------------------------------------------------- #
# 5. Demo / offline generator
# --------------------------------------------------------------------------- #

_STREETS_EN = ["Main Street", "King Road", "Market Square", "Park Avenue", "Oak Lane",
               "Highland Drive", "Station Road", "Church Street", "Mill Lane", "York Way",
               "Baker Street", "Victoria Road"]
_STREETS_DE = ["Hauptstraße", "Bahnhofstraße", "Marktplatz", "Lindenweg", "Schulstraße",
               "Gartenstraße", "Ringstraße", "Bergstraße", "Kirchgasse", "Waldweg"]
_STREETS_ES = ["Calle Mayor", "Avenida de la Constitución", "Plaza Central", "Paseo del Sol",
               "Calle Real", "Avenida Central", "Plaza Mayor", "Paseo de la Estación"]
_STREETS_FR = ["Rue de la Paix", "Boulevard Saint-Michel", "Place du Marché", "Rue Victor Hugo",
               "Avenue des Champs", "Rue de la République", "Place de la Gare"]
_STREETS_IT = ["Via Roma", "Via Garibaldi", "Piazza Centrale", "Via Dante", "Corso Italia",
               "Via Giuseppe Verdi", "Largo San Marco"]
_STREETS_PT = ["Rua Augusta", "Avenida da República", "Praça do Comércio", "Rua de São João"]
_STREETS_NL = ["Hoofdstraat", "Kerkstraat", "Molenweg", "Dorpsplein", "Julianastraat"]

_STREETS_BY_LANG = {
    "de": _STREETS_DE, "es": _STREETS_ES, "fr": _STREETS_FR, "it": _STREETS_IT,
    "pt": _STREETS_PT, "nl": _STREETS_NL,
}
_PREFIX = ["Bright", "Northern", "Prime", "Urban", "Golden", "Silver", "Royal", "Green",
           "Blue", "Iron", "Sun", "Star", "Elite", "Modern", "Classic"]
_SUFFIX = ["Point", "Center", "House", "Studio", "Group", "Works", "Lab", "Hub",
           "Partners", "Solutions", "Services", "Hub", "Depot", "Corner", "Yard"]
_TAGS = ["24/7", "Family", "Express", "Premium", "Eco", "Pro", "Certified", "Fast",
         "Deluxe", "Local"]


class DemoProvider(Provider):
    """Deterministic synthetic leads so the CLI runs (and demos) with no API key."""

    name = "demo"
    label = "Demo (offline)"
    env_keys = ()
    homepage = "built-in synthetic generator — no key, no network"
    per_query_cap = 120

    def __init__(self, **config):
        super().__init__(**config)
        self._seq = 0

    @classmethod
    def is_configured(cls) -> bool:  # always available
        return True

    @classmethod
    def api_key(cls) -> Optional[str]:
        return "offline"

    def validate(self) -> Tuple[bool, str]:
        return True, "offline generator - no key, no network needed"

    def search(self, req: SearchRequest) -> SearchResult:
        self._seq += 1
        rng = random.Random(f"{req.query}|{req.limit}|{self._seq}")
        phone_cc = req.location.get("dial", "+1")
        city = req.location.get("city") or "Springfield"
        region = req.location.get("region") or ""
        country = req.location.get("country") or ""
        streets = _STREETS_BY_LANG.get((req.language or "en")[:2], _STREETS_EN)
        cat = req.query.split(" in ")[0].strip() or "Local business"
        slug = cat.replace(" ", "-")

        leads: List[Lead] = []
        for i in range(min(req.limit, self.per_query_cap)):
            lead = _blank()
            name = f"{rng.choice(_PREFIX)} {cat.title()} {rng.choice(_SUFFIX)}"
            if rng.random() < 0.25:
                name = f"{city} {cat.title()} #{rng.randint(1, 99)}"
            street = f"{rng.randint(1, 240)} {rng.choice(streets)}"
            rating = round(rng.uniform(3.4, 5.0), 1)
            lat = round(48 + rng.random() * 12, 6)
            lon = round(2 + rng.random() * 26, 6)
            pid = f"DEMO_{slug.upper()[:10]}_{abs(hash(name)) % 10**9}"
            lead.update({
                "name": name,
                "category": cat.title(),
                "subcategory": rng.choice(_TAGS) + " " + cat.title(),
                "place_id": pid,
                "maps_url": maps_link(pid, lat, lon),
                "status": "OPERATIONAL" if rng.random() > 0.08 else "CLOSED_TEMPORARILY",
                "business_type": "",
                "address": f"{street}, {city}" + (f", {region}" if region else ""),
                "street": street,
                "city": city,
                "region": region,
                "postal_code": f"{rng.randint(10000, 99999)}",
                "country": country,
                "country_code": req.location.get("country_code", ""),
                "latitude": lat,
                "longitude": lon,
                "phone": f"{phone_cc} {rng.randint(20, 99)} {rng.randint(100, 999)} {rng.randint(1000, 9999)}",
                "website": f"https://www.{slug.replace(' ', '')}{rng.randint(1, 99)}.example.com",
                "email": f"hello@{slug.replace(' ', '')}{rng.randint(1, 99)}.example.com",
                "whatsapp": f"{phone_cc.replace('+', '')}{rng.randint(30, 99)}{rng.randint(10000000, 99999999)}",
                "facebook": f"https://facebook.com/{slug.replace(' ', '')}{rng.randint(1, 99)}",
                "instagram": f"https://instagram.com/{slug.replace(' ', '')}{rng.randint(1, 99)}",
                "linkedin": f"https://linkedin.com/company/{slug.replace(' ', '-')}{rng.randint(1, 99)}",
                "rating": rating,
                "reviews": rng.randint(3, 1840),
                "price_level": rng.choice(["$", "$$", "$$$", ""]),
                "hours": "Mon-Fri 08:00-18:00 | Sat 09:00-13:00",
                "open_now": rng.random() > 0.35,
                "is_chain": rng.random() < 0.3,
                "chain_name": f"{rng.choice(_PREFIX)} {cat.title()}" if rng.random() < 0.3 else "",
                "logo_url": f"https://logo.example.com/{slug}/{rng.randint(1, 99)}.png",
                "photos_count": rng.randint(0, 220),
                "year_established": rng.randint(1975, 2023),
                "employees": rng.randint(2, 240),
            })
            leads.append(lead)
        return SearchResult(leads=leads, query=req.query,
                            exhausted=req.limit >= self.per_query_cap)


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #

PROVIDERS: Dict[str, type] = {
    "google": GooglePlacesProvider,
    "outscraper": OutscraperProvider,
    "serpapi": SerpApiProvider,
    "dataforseo": DataForSeoProvider,
    "demo": DemoProvider,
}
ORDER: Tuple[str, ...] = ("outscraper", "google", "serpapi", "dataforseo")


def get_provider(name: str, **config) -> Provider:
    key = (name or "").lower().strip()
    if key not in PROVIDERS:
        raise KeyError(f"unknown provider '{name}'. choose one of: {', '.join(PROVIDERS)}")
    return PROVIDERS[key](**config)


def configured_providers() -> List[str]:
    return [n for n in ORDER if PROVIDERS[n].is_configured()]


def auto_provider(prefer: str = "") -> Optional[str]:
    """Pick the best provider for the keys present on this machine."""
    if prefer:
        return prefer if PROVIDERS[prefer].is_configured() else None
    found = configured_providers()
    return found[0] if found else None