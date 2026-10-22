"""
Contact helpers for the leads panel: WhatsApp deep links and the first-message
template.

Pure standard library on purpose — the GUI uses it, but nothing here knows about
Qt, so the same rules can back a future CLI option. Two jobs:

* **normalise a phone number** into the digits-only form ``wa.me`` expects. Real
  providers return a mix of ``+55 11 91234-5678``, ``(11) 91234-5678`` and bare
  national numbers, and every country hides its trunk ``0`` differently.
* **render the WhatsApp message** from a template with ``{placeholders}`` such as
  ``{nome}``. Values always come from the search result (the lead), never from
  the number itself — a business that never filled in a WhatsApp profile still
  gets its name in the greeting.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import quote

from .data import countries as CO

# ISO (lower-case) -> calling code, from the country catalogue the wizard uses.
DIAL_BY_ISO: Dict[str, str] = {c.iso: c.dial for c in CO.COUNTRIES}

# Countries where a leading 0 is NOT a trunk prefix and must be kept (Italy's
# landlines start with 0; dropping it would dial the wrong number).
_KEEP_LEADING_ZERO = {"it"}

_TOKEN = re.compile(r"\{\s*([A-Za-z_][A-Za-z0-9_-]*)\s*\}")

# The demo/outscraper providers may return this sentinel for a nameless place.
_UNNAMED = "(unnamed business)"

DEFAULT_TEMPLATE = (
    "Olá {nome}! Tudo bem? Encontrei vocês no Google Maps e gostaria de saber "
    "mais sobre os serviços de vocês."
)

# token (without braces) -> short explanation shown as a button tooltip.
PLACEHOLDERS: Tuple[Tuple[str, str], ...] = (
    ("nome", "business name from the search result"),
    ("categoria", "business category"),
    ("cidade", "city"),
    ("estado", "state / region"),
    ("endereco", "full street address"),
    ("telefone", "phone number"),
    ("site", "website URL"),
    ("email", "e-mail address"),
    ("nota", "average rating"),
    ("avaliacoes", "review count"),
    ("saudacao", "Bom dia / Boa tarde / Boa noite"),
)

# accepted spellings, so a Portuguese or an English template both work.
_ALIASES: Dict[str, str] = {
    "name": "nome",
    "business": "nome",
    "empresa": "nome",
    "category": "categoria",
    "city": "cidade",
    "region": "estado",
    "uf": "estado",
    "country": "pais",
    "address": "endereco",
    "street": "endereco",
    "phone": "telefone",
    "whatsapp": "telefone",
    "website": "site",
    "url": "site",
    "rating": "nota",
    "reviews": "avaliacoes",
    "greeting": "saudacao",
}

TOKENS: Tuple[str, ...] = tuple(sorted({k for k, _ in PLACEHOLDERS} | set(_ALIASES)))


# --------------------------------------------------------------------------- #
# phone numbers
# --------------------------------------------------------------------------- #

def digits_only(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _drop_trunk_zero(number: str, iso: str, dial_digits: str = "") -> str:
    """Remove a trunk ``0`` glued right after the country code.

    Providers sometimes hand back ``+49 0151 …`` (the national number keeps its
    trunk prefix), which is not a valid ``wa.me`` number. Italy is exempt: there
    the leading 0 belongs to the national number.
    """
    if iso in _KEEP_LEADING_ZERO or not number:
        return number
    code = dial_digits
    if not code:
        candidates = sorted({digits_only(d) for d in DIAL_BY_ISO.values()
                             if d}, key=len, reverse=True)
        for candidate in candidates:
            if number.startswith(candidate):
                code = candidate
                break
    if code and number.startswith(code):
        rest = number[len(code):]
        if rest.startswith("0"):
            return code + rest[1:]
    return number


def normalize_wa_number(value: Any, dial: str = "", iso: str = "") -> str:
    """Normalise a phone number to ``wa.me`` digits (country code, no ``+``).

    ``+``/``00`` prefixed numbers are taken as already international. Bare
    national numbers get the country dial prepended (after dropping a trunk
    ``0``), and numbers that *look* like they already carry the dial code
    without a ``+`` are left alone. Returns ``""`` when nothing usable is left.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    digits = digits_only(raw)
    if not digits:
        return ""

    iso = (iso or "").strip().lower()
    dial_digits = digits_only(dial) or DIAL_BY_ISO.get(iso, "")

    if raw.startswith("+"):
        return _drop_trunk_zero(digits, iso, dial_digits)
    if raw.startswith("00"):
        return _drop_trunk_zero(digits[2:], iso, dial_digits)

    if not dial_digits:
        return digits

    # "5511912345678" / "351912345678": too long for any national format and the
    # remainder is a plausible national number -> it already carries the code.
    national_len = len(digits) - len(dial_digits)
    if digits.startswith(dial_digits) and (
            (len(digits) >= 12 and 8 <= national_len <= 11)
            or (dial_digits == "1" and len(digits) == 11)):
        number = digits
    else:
        number = digits
        if number.startswith("0") and iso not in _KEEP_LEADING_ZERO:
            number = number.lstrip("0")
        number = dial_digits + number

    # WhatsApp wants the bare country code, never a duplicate.
    number = _drop_trunk_zero(number, iso, dial_digits)
    while number.startswith("00"):
        number = number[2:]
    return number


def whatsapp_number(lead: Mapping[str, Any], dial: str = "", iso: str = "") -> str:
    """Best WhatsApp-capable number for a lead (digits only, ``""`` if none).

    The phone shown next to the button wins; when it looks like a landline and
    the provider also returned a dedicated ``whatsapp`` field, that one is used
    instead.
    """
    from .engine import phone_type

    iso = iso or str(lead.get("country_code") or "")
    phone = str(lead.get("phone") or "").strip()
    wa_field = str(lead.get("whatsapp") or "").strip()

    if phone:
        number = normalize_wa_number(phone, dial, iso)
        if number and wa_field and phone_type(phone, iso, dial) == "landline":
            alt = normalize_wa_number(wa_field, "", iso)
            if alt:
                return alt
        return number
    if wa_field:
        return normalize_wa_number(wa_field, "", iso)
    return ""


def whatsapp_url(number: Any, message: str = "") -> str:
    """``https://wa.me/<digits>`` with an optional pre-filled message."""
    digits = digits_only(number)
    if not digits:
        return ""
    url = f"https://wa.me/{digits}"
    if message:
        url += "?text=" + quote(message, safe="")
    return url


def whatsapp_url_for(lead: Mapping[str, Any], message: str = "",
                     dial: str = "", iso: str = "") -> str:
    return whatsapp_url(whatsapp_number(lead, dial, iso), message)


# --------------------------------------------------------------------------- #
# message template
# --------------------------------------------------------------------------- #

def greeting(when: Optional[datetime.datetime] = None) -> str:
    hour = (when or datetime.datetime.now()).hour
    if 5 <= hour < 12:
        return "Bom dia"
    if 12 <= hour < 18:
        return "Boa tarde"
    return "Boa noite"


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "sim" if value else "não"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if v)
    return str(value).strip()


def placeholder_values(lead: Mapping[str, Any],
                       when: Optional[datetime.datetime] = None) -> Dict[str, str]:
    """Every supported placeholder resolved from one lead."""
    name = str(lead.get("name") or "").strip()
    if name == _UNNAMED:
        name = ""
    rating = lead.get("rating")
    reviews = lead.get("reviews")
    rating_text = ""
    if isinstance(rating, (int, float)):
        rating_text = f"{float(rating):g}"
    reviews_text = ""
    try:
        if reviews not in (None, ""):
            reviews_text = f"{int(reviews):,}"
    except (TypeError, ValueError):
        reviews_text = _text(reviews)

    greeting_text = greeting(when)
    address = _text(lead.get("address") or lead.get("street"))
    city = _text(lead.get("city"))
    region = _text(lead.get("region"))
    if not address:
        address = ", ".join(p for p in (city, region) if p)

    return {
        "nome": name,
        "categoria": _text(lead.get("category")),
        "cidade": city,
        "estado": region,
        "pais": _text(lead.get("country")),
        "endereco": address,
        "telefone": _text(lead.get("phone") or lead.get("whatsapp")),
        "site": _text(lead.get("website")),
        "email": _text(lead.get("email")),
        "nota": rating_text,
        "avaliacoes": reviews_text,
        "saudacao": greeting_text,
    }


def render_template(template: str, lead: Mapping[str, Any],
                    when: Optional[datetime.datetime] = None) -> str:
    """Fill ``{placeholders}`` from the lead and tidy the leftovers.

    Unknown placeholders are kept verbatim (typos stay visible instead of
    silently deleting text) and whitespace around removed values is collapsed,
    so ``Olá {nome}!`` with no name becomes ``Olá!`` rather than ``Olá !``.
    """
    values = placeholder_values(lead, when=when)

    def replace(match: re.Match) -> str:
        key = match.group(1).lower()
        key = _ALIASES.get(key, key)
        if key in values:
            return values[key]
        return match.group(0)

    text = _TOKEN.sub(replace, template or "")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    lines = [line.strip() for line in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines).strip()


def unknown_placeholders(template: str) -> Tuple[str, ...]:
    """Tokens in `template` that would not be replaced, sorted."""
    known = set(TOKENS)
    return tuple(sorted({m.group(1).lower() for m in _TOKEN.finditer(template or "")
                         if m.group(1).lower() not in known}))
