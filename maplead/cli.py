"""
MAPLEAD - interactive Google Maps lead extractor.

Flow:  banner -> provider -> country -> region -> city -> business type
       -> fields to extract -> how many -> filters -> output format -> run
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Optional, Sequence

from . import art, engine, exporters, host, paths, ui
from .art import VERSION, c
from .data import cities as CI
from .data import countries as CO
from .data import fields as FD
from .data import verticals as VT
from .net import ApiError
from .providers import ORDER, PROVIDERS, get_provider

APP = "MAPLEAD"
STEP_TOTAL = 9

# .env lives next to the tool when it is there (portable installs), otherwise in
# the per-user config dir (%APPDATA% on Windows, XDG on Linux) - resolved once so
# every message shows the real path.
ENV_FILE = paths.env_file()


# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="maplead",
        description=f"{APP} v{VERSION} - interactive Google Maps lead extractor "
                    f"(Google Places / Outscraper / SerpApi / DataForSEO).",
        epilog="Run with no arguments for the guided wizard.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--provider", choices=list(PROVIDERS),
                   help="lead-scraper API to use (default: auto-detect from keys)")
    p.add_argument("-k", "--api", "--set-key", dest="api", action="store_true",
                   help="API KEY SETUP: pick a provider, paste the key, verify it, save it")
    p.add_argument("--api-provider", choices=list(PROVIDERS),
                   help="skip the picker and set the key for this provider")
    p.add_argument("--check-keys", action="store_true",
                   help="live-test every stored API key and report")
    p.add_argument("--remove-keys", action="store_true",
                   help="wipe the keys stored in .env")
    p.add_argument("--demo", action="store_true",
                   help="use the offline synthetic provider (no API key, instant)")
    p.add_argument("--country", help="country name or ISO code, e.g. Germany / DE")
    p.add_argument("--region", help="state / province (optional)")
    p.add_argument("--city", help="city, e.g. Berlin")
    p.add_argument("--business", help="business type, e.g. plumber / dentist / 'car wash'")
    p.add_argument("--fields", help="fields to extract: name,phone,rating / all / rec / sales")
    p.add_argument("--limit", type=int, help="how many leads to collect (default 60)")
    p.add_argument("--format", choices=[f for f, _, _ in exporters.FORMATS],
                   help="output file format")
    p.add_argument("--out", help="output file path")
    p.add_argument("--outdir", default="leads", help="output folder when --out is omitted")
    p.add_argument("--min-rating", type=float, help="drop leads rated below this")
    p.add_argument("--min-reviews", type=int, help="drop leads with fewer reviews")
    p.add_argument("--require-phone", action="store_true", help="only keep leads with a phone")
    p.add_argument("--skip-landlines", action="store_true",
                   help="drop landline numbers, keep mobiles (numbers that cannot "
                        "be classified, e.g. US, are kept)")
    p.add_argument("--require-website", action="store_true", help="only keep leads with a website")
    p.add_argument("--skip-closed", action="store_true", help="drop permanently closed places")
    p.add_argument("--enrich", action="store_true",
                   help="run contact enrichment (Outscraper only)")
    p.add_argument("--all-columns", action="store_true",
                   help="export every field the API returned, not just the selected ones")
    p.add_argument("--language", help="API language code (default: from country)")
    p.add_argument("--yes", action="store_true", help="non-interactive: accept defaults for prompts")
    p.add_argument("--json", action="store_true", help="print the leads to stdout as JSON")
    p.add_argument("--no-banner", action="store_true", help="hide the ASCII art")
    p.add_argument("--list-providers", action="store_true", help="show provider status and exit")
    p.add_argument("--list-fields", action="store_true", help="show the field catalogue and exit")
    p.add_argument("--doctor", action="store_true",
                   help="print environment diagnostics (for bug reports) and exit")
    p.add_argument("--gui", action="store_true",
                   help="launch the MAPLEAD desktop app instead of the terminal wizard")
    p.add_argument("--version", action="version", version=f"{APP} {VERSION}")
    return p


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def provider_status_rows() -> List[List[str]]:
    rows = []
    for name in (*ORDER, "demo"):
        cls = PROVIDERS[name]
        if name == "demo":
            state, detail = "ready", "offline synthetic data"
        elif cls.is_configured():
            key = cls.api_key() or ""
            state = c("configured", "green", bold=True)
            detail = f"{cls.env_keys[0]} = {key[:6]}…{key[-4:]}" if len(key) > 12 else cls.env_keys[0]
        else:
            state = c("no key", "yellow")
            detail = "set " + " or ".join(cls.env_keys)
        rows.append([name, cls.label, state, detail])
    return rows


def print_provider_status() -> None:
    ui.out()
    ui.out(ui.panel("api providers", [
        ui.pad(c(name, "yellow", bold=True), 12) + f" {PROVIDERS[name].label}"
        for name in PROVIDERS
    ], color="cyan"))
    ui.out()
    ui.out(ui.table(["id", "service", "status", "api key"],
                    provider_status_rows(), aligns=["left", "left", "left", "left"]))
    ui.out()
    ui.hint("keys are read from environment variables or a .env file next to the tool")
    ui.hint("run with --demo to try the whole flow with zero setup")
    ui.out()


def field_rows(provider: str | None) -> List[List[str]]:
    rows = []
    for f in FD.FIELDS:
        if provider and provider in f.providers:
            avail = c("yes", "green")
        elif provider:
            avail = c("no", "yellow")
        else:
            avail = c("yes", "green")
        note = f.note
        if f.enriched and provider and provider not in ("outscraper", "demo"):
            note = (note + " " if note else "") + c("needs enrichment", "yellow")
        rows.append([f.key, f.group, avail, note])
    return rows


def print_field_catalogue(provider: str | None) -> None:
    ui.out()
    ui.out(ui.table(["field", "group", "available", "note"], field_rows(provider),
                     aligns=["left", "left", "left", "left"]))
    ui.out()
    ui.hint("presets:  rec (recommended)   basic   sales   all")
    ui.out()


def print_diagnostics() -> None:
    """`--doctor`: what this build thinks its host looks like (bug reports)."""
    import platform

    diag = host.diagnose()
    rows = [
        ("maplead", f"{VERSION}{' (frozen)' if diag['frozen'] else ' (source)'}"),
        ("python", f"{platform.python_version()} · {platform.machine()}"),
        ("platform", platform.platform(terse=True)),
        ("console", "tty" if diag["console"].get("isatty") else "redirected"),
        ("encoding", str(diag["console"].get("encoding"))),
        ("ansi / unicode", f"{art.ANSI_OK} / {art.UNICODE}"),
        ("colour", "on" if art.COLOR else "off (plain output)"),
        ("config", paths.config_dir()),
        ("data", paths.data_dir()),
        ("exports", paths.default_export_dir()),
        ("env file", paths.env_file()),
        ("executable", diag["executable"]),
    ]
    ui.out()
    ui.out(ui.table(["what", "value"], rows, aligns=["left", "left"]))
    detail = "  ".join(f"{k}={v}" for k, v in diag["console"].items()
                       if k not in ("isatty", "encoding"))
    if detail:
        ui.out()
        ui.hint("console detail: " + detail)
    ui.out()


def detect_provider(explicit: str | None, demo: bool, interactive: bool) -> Optional[str]:
    if demo:
        return "demo"
    if explicit:
        cls = PROVIDERS[explicit]
        if cls.is_configured():
            return explicit
        ui.warn(f"no API key found for {cls.label} ({', '.join(cls.env_keys)})")
        if demo or not interactive:
            return "demo"
        return ask_provider()
    found = [n for n in ORDER if PROVIDERS[n].is_configured()]
    if found:
        return found[0]
    return None


def ask_provider() -> str:
    items = list(PROVIDERS)
    choice = ui.ask_choice(
        "Which lead-scraper API should I use?",
        items,
        labeler=lambda n: f"{PROVIDERS[n].label}  ({PROVIDERS[n].name})",
        sublabeler=lambda n: (
            "✓ key detected: " + (PROVIDERS[n].api_key() or "")[:14] + "…"
            if PROVIDERS[n].is_configured() else
            f"needs {' or '.join(PROVIDERS[n].env_keys)}"
        ),
        default_index=ORDER.index("outscraper") if "outscraper" in ORDER else 0,
        extra=[("demo", "offline sample data, no key needed")],
    )
    return choice


def ask_country() -> CO.Country:
    table = {(c.name, c.dial): c for c in CO.COUNTRIES}
    items = list(table)
    ui.out()
    ui.hint(f"type any country name to filter · {len(CO.COUNTRIES)} countries available")
    while True:
        key = ui.ask_choice(
            "Which country do you want leads from?",
            items,
            labeler=lambda k: k[0],
            sublabeler=lambda k: f"{k[1]}   ·   {len(CO.BY_NAME[k[0].lower()].states)} regions"
            if CO.BY_NAME[k[0].lower()].states else f"{k[1]}",
            extra=[("other", "type a country name not in the list")],
            min_col=30, max_cols=3,
        )
        if key == "other":
            name = ui.ask_text("Country name or ISO code", required=True)
            hits = CO.find(name)
            if not hits:
                ui.error(f"'{name}' is not in the country list")
                continue
            if len(hits) == 1:
                return hits[0]
            pick = ui.ask_choice("Did you mean", hits, labeler=lambda x: x.label(),
                                 min_col=40, max_cols=2)
            return pick
        return table[key]


def ask_region(country: CO.Country) -> str:
    """Region / state, or '' when the user has no idea (search whole country)."""
    if country.states:
        picks = ui.ask_choice(
            f"Which {country.name} region / state? (pick one, or type your own)",
            list(country.states),
            labeler=lambda s: s,
            extra=[("__other__", "type a different region"),
                   ("__any__", "I don't know — search the whole country")],
            default_index=0,
            min_col=26, max_cols=3,
        )
        if picks == "__other__":
            return ui.ask_text("Region / state", placeholder=country.states[0],
                               allow_skip=True)
        if picks == "__any__":
            return ""
        return picks
    return ui.ask_text(
        "Region / state / province",
        placeholder="(skip if not applicable)",
        allow_skip=True,
    )


def ask_city(country: CO.Country, region: str) -> str:
    """
    City with ready-made options - never a blank box.

    * region chosen    -> the cities of that region are listed
    * "I don't know"    -> every catalogued city in the country, each tagged
                          with its region, so the list is browsable
    * region is a city -> it comes back as option 1 (Japan/Norway/Singapore
                          list cities where other countries list states)
    * anything else    -> one word away, type it
    """
    where = region or country.name
    hints = CI.candidates(country.iso, region)

    if not hints:
        ui.hint(f"no city list for {where} — just type the city name")
        return ui.ask_text(f"Which city in {where}?", required=True,
                           placeholder="e.g. Berlin")

    sub = {name: reg for name, reg in hints if reg}
    items = [name for name, _ in hints]
    region_is_city = bool(region) and CI.is_city(country.iso, region)
    region_filtered = bool(region) and bool(CI.match_region(country.iso, region))

    if region_is_city:
        items = [region] + [n for n in items if n != region]
        sub[region] = f"“{region}” is a city — keep it as the search centre"
    elif not region_filtered:
        ui.hint(f"no city list narrowed to {where} — showing {len(items)} cities "
                f"across {country.name} · type to filter")

    spread = len({sub[n] for n in items if n in sub}) > 1
    pick = ui.ask_choice(
        f"Which city in {where}?",
        items,
        labeler=lambda n: n,
        sublabeler=(lambda n: sub.get(n, "")) if (spread or region_is_city) else None,
        extra=[("__other__", "type a city that is not in the list")],
        min_col=32, max_cols=3,
    )
    if pick == "__other__":
        return ui.ask_text("City name", required=True, placeholder=items[0])
    return pick


def ask_business() -> tuple[str, List[str]]:
    """Return (display term, search term list)."""
    items = list(VT.VERTICALS)
    pick = ui.ask_choice(
        "What type of local business are you hunting leads for?",
        items,
        labeler=lambda v: f"{v.label}",
        sublabeler=lambda v: (
            (v.tips + "   ") if v.tips else ""
        ) + c("searches as ", "white", dim=True) + c(f'“{v.query}”', "white", dim=True)
        + (c(f'  also: {", ".join(v.synonyms[:3])}', "white", dim=True) if v.synonyms else ""),
        default_index=0,
        extra=[("__custom__", "type your own business type")],
        min_col=42, max_cols=2,
    )
    if pick != "__custom__":
        return pick.label, [pick.query] + list(pick.synonyms[:2])

    while True:
        text = ui.ask_text("Business type", required=True,
                           placeholder="e.g. solar panel installer")
        hits = VT.resolve(text)
        if not hits:
            if ui.ask_yesno(f"No catalog match for '{text}'. Use it as-is?", True):
                return text, [text]
            continue
        if len(hits) == 1:
            return hits[0].label, [hits[0].query] + list(hits[0].synonyms[:2])
        pick2 = ui.ask_choice("Did you mean", hits, labeler=lambda v: v.label,
                              sublabeler=lambda v: f'“{v.query}”')
        return pick2.label, [pick2.query] + list(pick2.synonyms[:2])


def ask_fields(provider_name: str) -> List[str]:
    items = []
    for f in FD.FIELDS:
        mark = "" if provider_name in f.providers else c(" (unavailable)", "yellow")
        items.append((f.key, f.group + " · " + f.label + mark))
    chosen = ui.ask_multiselect(
        "What do you want to extract from these leads?",
        items, recommended=FD.RECOMMENDED, presets=FD.PRESETS,
    )
    return chosen


def ask_format(default: str = "csv") -> str:
    pick = ui.ask_choice(
        "Which file format should I export to?",
        list(exporters.FORMATS),
        labeler=lambda t: f"{t[1]:<6} .{t[0]}",
        sublabeler=lambda t: t[2],
        default_index=[f for f, _, _ in exporters.FORMATS].index(default)
        if default in [f for f, _, _ in exporters.FORMATS] else 0,
        min_col=42, max_cols=2,
    )
    return pick[0]


# --------------------------------------------------------------------------- #
# main wizard
# --------------------------------------------------------------------------- #

def run_wizard(args: argparse.Namespace) -> int:
    # Fully-specified command lines skip every prompt (script-friendly).
    complete = all([args.country, args.city, args.business, args.fields,
                    args.limit, args.format])
    auto = args.yes or complete

    # ---- banner ---------------------------------------------------------
    if not args.no_banner:
        found = [n for n in ORDER if PROVIDERS[n].is_configured()]
        status = (f"api keys detected → {'  ·  '.join(PROVIDERS[n].label for n in found)}"
                  if found else "no api keys found · offline demo mode available")
        ui.out()
        ui.out(art.banner(status=status))

    # ---- 1/9 provider ---------------------------------------------------
    ui.step(1, STEP_TOTAL, "data provider")
    provider_name = detect_provider(args.provider, args.demo, not auto)
    if not provider_name:
        ui.warn("no API key found for any online provider.")
        ui.hint("add one in 10 seconds:   ./maplead.py --api")
        ui.hint("or set it by hand:      OUTSCRAPER_API_KEY=xxx  in .env / your shell")
        if auto:
            provider_name = "demo"
        else:
            if not ui.ask_yesno("Continue in offline demo mode instead?", True):
                return 2
            provider_name = "demo"
    provider = get_provider(provider_name)
    ui.info(f"{c(provider.label, 'yellow', bold=True)} · per-query cap "
            f"{provider.per_query_cap} results · {provider.homepage}")

    # ---- 2/9 country ----------------------------------------------------
    ui.step(2, STEP_TOTAL, "country")
    country: CO.Country
    if args.country:
        hits = CO.find(args.country)
        if not hits:
            ui.error(f"unknown country '{args.country}'")
            return 2
        country = hits[0]
    else:
        country = ask_country()
    ui.info(f"{c(country.name, 'white', bold=True)} {c(country.dial, 'cyan')} "
            f"{c('· API language: ' + country.lang, 'white', dim=True)}")

    # ---- 3/9 region -----------------------------------------------------
    ui.step(3, STEP_TOTAL, "region / state")
    if args.region is not None:
        region = args.region
    elif auto:
        region = ""
    else:
        region = ask_region(country)
    ui.info(c(region or "(whole country)", "white", bold=True))

    # ---- 4/9 city --------------------------------------------------------
    ui.step(4, STEP_TOTAL, "city")
    if args.city:
        city = args.city
    elif auto:
        ui.error("--city is required in non-interactive mode")
        return 2
    else:
        city = ask_city(country, region)
    ui.info(c(city or f"(everywhere in {region or country.name})", "white", bold=True))

    # ---- 5/9 business type ----------------------------------------------
    ui.step(5, STEP_TOTAL, "business type")
    if args.business:
        hits = VT.resolve(args.business)
        if hits:
            v = hits[0]
            business_label, terms = v.label, [v.query] + list(v.synonyms[:2])
        else:
            business_label, terms = args.business, [args.business]
    elif auto:
        ui.error("--business is required in non-interactive mode")
        return 2
    else:
        business_label, terms = ask_business()
    ui.info(c(business_label, "white", bold=True) + c(f"   queries: {', '.join(terms)}", "white", dim=True))

    # ---- 6/9 fields ------------------------------------------------------
    ui.step(6, STEP_TOTAL, "fields to extract")
    if args.fields:
        chosen = FD.parse_selection(args.fields)
        if not chosen:
            ui.error(f"could not parse fields '{args.fields}'")
            return 2
    elif auto:
        chosen = [f for f in FD.RECOMMENDED if provider.supports(f)]
    else:
        chosen = ask_fields(provider.name)
    chosen = [f for f in chosen if provider.supports(f)]
    unsupported = [f for f in FD.parse_selection(args.fields)] if args.fields else []
    unsupported = [f for f in unsupported if f not in chosen]
    if unsupported:
        ui.warn("these fields are not available from this provider and were dropped: "
                + ", ".join(unsupported))
    grouped: Dict[str, List[str]] = {}
    for f in chosen:
        grouped.setdefault(FD.group_of(f), []).append(f)
    for grp, keys in grouped.items():
        ui.info(f"{c(grp, 'cyan'):<22} {c('·'.join(keys), 'white')}")

    # ---- 7/9 volume + filters -------------------------------------------
    ui.step(7, STEP_TOTAL, "how many leads")
    limit = args.limit or (120 if not auto else 40)
    if not args.limit and not auto:
        limit = ui.ask_number("Target number of leads", 60, minimum=1, maximum=100_000)
    ui.info(f"{c(str(limit), 'yellow', bold=True)} unique leads")
    if not auto and not args.min_rating:
        raw = ui.ask_text("Minimum rating (0 = no filter, blank = skip)", allow_skip=True)
        if raw:
            try:
                args.min_rating = float(raw)
                ui.info(c(f"dropping anything rated below {args.min_rating} ★", "white"))
            except ValueError:
                ui.warn(f"'{raw}' is not a number - ignoring")
    if not auto:
        args.require_phone = args.require_phone or ui.ask_yesno(
            "Only keep leads that have a phone number?", False)
        args.skip_landlines = args.skip_landlines or ui.ask_yesno(
            "Skip landlines (keep mobile numbers)?", False)
        args.require_website = args.require_website or ui.ask_yesno(
            "Only keep leads that have a website?", False)

    if args.skip_landlines:            # a phone type filter implies a phone
        args.require_phone = True

    # ---- 8/9 format ------------------------------------------------------
    ui.step(8, STEP_TOTAL, "output format")
    fmt = args.format or (ask_format() if not auto else "csv")
    place = city or region or country.name
    outpath = args.out or exporters.suggest_path(fmt, f"{business_label}-{place}", args.outdir)
    ui.info(f"{c(exporters.LABEL[fmt], 'yellow', bold=True)} {c(exporters.DESC[fmt], 'white', dim=True)}")
    ui.info(f"file → {c(outpath, 'white', bold=True)}")

    # ---- summary ---------------------------------------------------------
    plan = engine.SearchPlan(
        provider=provider, city=city, region=region, country=country.name,
        country_code=country.iso, dial=country.dial, terms=terms, fields=chosen,
        limit=limit, language=args.language or country.lang,
        min_rating=args.min_rating, min_reviews=args.min_reviews,
        require_phone=args.require_phone, require_website=args.require_website,
        skip_closed=args.skip_closed, enrich=args.enrich,
        skip_landlines=args.skip_landlines,
    )
    ui.out()
    ui.out(ui.panel("search plan", [
        f"{c('provider', 'cyan')}  {provider.label} ({provider.name})",
        f"{c('location', 'cyan')}  {plan.location_label}",
        f"{c('business', 'cyan')}  {business_label}",
        f"{c('fields', 'cyan')}    {len(chosen)} selected",
        f"{c('target', 'cyan')}    {limit} leads",
        f"{c('output', 'cyan')}    {outpath}",
    ], color="magenta"))

    if not auto:
        if not ui.ask_yesno("Start scraping?", True):
            ui.info("cancelled.")
            return 0

    # ---- 9/9 run ---------------------------------------------------------
    ui.step(9, STEP_TOTAL, "scraping")
    return do_scrape(plan, fmt, outpath, chosen, args)


def do_scrape(plan: engine.SearchPlan, fmt: str, outpath: str,
              chosen: Sequence[str], args: argparse.Namespace) -> int:
    prog = ui.Progress("scraping", total=plan.limit)

    def note(msg: str) -> None:
        prog.update(msg)

    try:
        leads, report = engine.harvest(plan, progress=note)
    except KeyboardInterrupt:
        prog.stop()
        ui.out()
        ui.warn("interrupted.")
        return 130
    except ApiError as exc:
        prog.stop()
        ui.out()
        ui.error(str(exc))
        if plan.provider.name == "demo":
            return 1
        ui.hint("check the key, the provider plan/quota, and your network.")
        return 1
    prog.done(f"{len(leads)} leads in {report.elapsed:.1f}s")

    if not leads:
        ui.warn("no leads matched. try: a bigger limit, a different city spelling, "
                "or relax the filters.")
        for e in report.errors:
            ui.error(e)
        return 1

    # ---- preview ---------------------------------------------------------
    stats = engine.summarize(leads)
    ui.out()
    rows = []
    for lead in leads[:10]:
        rows.append([
            ui.trunc(lead.get("name", ""), 30),
            ui.trunc(lead.get("category", ""), 18),
            ui.trunc(lead.get("city", "") or lead.get("region", ""), 14),
            lead.get("phone", ""),
            lead.get("rating", "") or "",
            lead.get("reviews", "") or "",
            ui.trunc(lead.get("website", ""), 26),
        ])
    ui.out(ui.table(["business", "category", "city", "phone", "rating", "reviews", "website"],
                    rows, aligns=["left", "left", "left", "left", "right", "right", "left"]))
    if len(leads) > 10:
        ui.out()
        ui.hint(f"... and {len(leads) - 10} more")

    # ---- stats -----------------------------------------------------------
    filtered_total = sum(report.filtered.values())
    detail = ""
    if filtered_total:
        detail = c("   " + ", ".join(f"{k.replace('_', ' ')}: {v}"
                                     for k, v in report.filtered.items()), "white", dim=True)
    ui.out()
    ui.out(ui.panel("harvest report", [
        f"{c('raw results', 'cyan')}         {report.raw_count}",
        f"{c('duplicates removed', 'cyan')}   {report.duplicates}",
        f"{c('filtered out', 'cyan')}         {filtered_total}{detail}",
        f"{c('kept', 'cyan')}                 {c(str(len(leads)), 'green', bold=True)}",
        f"{c('with phone', 'cyan')}           {stats['with_phone']} "
        f"{c('(' + pct(stats['with_phone'], len(leads)) + ')', 'white', dim=True)}",
        f"{c('with website', 'cyan')}         {stats['with_website']} "
        f"{c('(' + pct(stats['with_website'], len(leads)) + ')', 'white', dim=True)}",
        f"{c('avg rating', 'cyan')}           {stats['avg_rating']} "
        f"{c('★', 'yellow')}   {c('total reviews: ' + str(stats['total_reviews']), 'white', dim=True)}",
        f"{c('queries run', 'cyan')}          {len(report.queries_run)}"
        f"{c(f' in {report.elapsed:.1f}s', 'white', dim=True)}",
    ], color="cyan"))
    if stats["top_cities"]:
        ui.out()
        ui.hint("top cities: " + "  ·  ".join(f"{n} ({k})" for n, k in stats["top_cities"][:4]))
    if len(leads) < plan.limit:
        ui.warn(f"got {len(leads)} of the {plan.limit} you asked for "
                f"— filters and duplicates removed the rest. "
                f"raise --limit or relax the filters.")
    if report.errors:
        for e in report.errors[:3]:
            ui.error(e)

    # ---- export ----------------------------------------------------------
    ui.out()
    include_extra = bool(getattr(args, "all_columns", False)) or \
        len(chosen) >= 0.8 * len(FD.FIELDS)
    columns = exporters.build_columns(chosen, leads, include_extra=include_extra)
    meta = {
        "query": (f"{plan.terms[0]} in {plan.location_label}"
                  if plan.location_label else plan.terms[0]),
        "location": plan.location_label,
        "business": ", ".join(plan.terms),
        "provider": f"{plan.provider.label} ({plan.provider.name})",
        "fields": len(columns),
        "generated_at": time_str(),
    }
    ui.info(f"writing {len(columns)} columns × {len(leads)} rows → {c(outpath, 'white', bold=True)}")
    if include_extra:
        ui.hint("every field the API returned is included (you selected almost everything)")
    try:
        info = exporters.write(fmt, outpath, leads, columns, meta)
    except OSError as exc:
        ui.error(f"could not write file: {exc}")
        return 1

    size = human_size(info["bytes"])
    ui.out()
    ui.out(art.success_block(
        f"{len(leads)} leads exported to {os.path.basename(outpath)}",
        f"{os.path.abspath(outpath)}  ·  {size}  ·  {info['columns']} columns  ·  .{fmt}"))

    if args.json:
        import json as _json
        ui.out(_json.dumps(leads, ensure_ascii=False, indent=2, default=str))
    return 0


def pct(part: int, whole: int) -> str:
    return f"{round(part * 100 / whole)}%" if whole else "0%"


def human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value, i = float(n), 0
    while value >= 1024 and i < len(units) - 1:
        value /= 1024.0
        i += 1
    return f"{value:.0f} {units[i]}" if units[i] == "B" else f"{value:.1f} {units[i]}"


def time_str() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

def load_dotenv(path: str | None = None) -> str:
    """Load KEY=VALUE pairs from .env without clobbering the real environment.

    Looks next to the tool first, then in the user config dir, then in the
    current directory. Returns the file that was used (or would be written).
    """
    return paths.load_env(path)


def save_key(key: str, value: str, path: str | None = None) -> str:
    """Write KEY=VALUE into .env, preserving comments and other keys."""
    return paths.save_env_key(key, value, path or ENV_FILE)


def clear_key(key: str, path: str | None = None) -> bool:
    return paths.clear_env_key(key, path or ENV_FILE)


# --------------------------------------------------------------------------- #
# --api : paste a key, validate it, save it
# --------------------------------------------------------------------------- #

_ERROR_HINTS = (
    ("REQUEST_INVALID_API_KEY", "that key is not valid for this API"),
    ("API key not valid", "that key is not valid for this API"),
    ("API_KEY_INVALID", "that key is not valid for this API"),
    ("PERMISSION_DENIED", "key is valid but Places API (New) is probably not enabled "
                          "on the project - enable it + billing in Google Cloud Console"),
    ("Invalid API key", "that key is not valid for this API"),
    ("403", "the key was rejected - check the plan / quota on the provider's dashboard"),
    ("401", "authentication failed - double-check the key you pasted"),
    ("429", "rate limited right now - wait a minute and try again"),
    ("ENABLE", "the API is not enabled on your project yet"),
)


def explain_error(exc: Exception) -> str:
    msg = str(exc)
    for needle, hint in _ERROR_HINTS:
        if needle.lower() in msg.lower():
            return hint
    return ""


def check_key(provider_name: str, quiet: bool = False) -> bool:
    """Live-validate one provider's stored key."""
    provider = get_provider(provider_name)
    if provider_name != "demo" and not provider.is_configured():
        ui.error(f"{provider.label}: no key set")
        return False
    if not quiet:
        ui.info(f"testing {c(provider.label, 'yellow', bold=True)}…")
    try:
        ok, message = provider.validate()
    except ApiError as exc:
        ui.error(str(exc))
        hint = explain_error(exc)
        if hint:
            ui.hint(hint)
        return False
    except Exception as exc:  # network trouble, etc.
        ui.error(f"could not reach the API: {exc}")
        return False
    ui.ok(f"{provider.label}: {message}")
    return ok


def run_api_setup(args: argparse.Namespace) -> int:
    """The --api wizard: pick a provider, paste the key, verify, save."""
    ui.out()
    ui.out(art.banner(status="api key setup"))

    chosen = args.api_provider
    if not chosen:
        items = [n for n in PROVIDERS if n != "demo"]
        chosen = ui.ask_choice(
            "Which service is your API key for?",
            items,
            labeler=lambda n: f"{PROVIDERS[n].label}  ({n})",
            sublabeler=lambda n: (
                "✓ key already set — you'll replace it"
                if PROVIDERS[n].is_configured()
                else f"paste it after: {', '.join(PROVIDERS[n].env_keys)}"
            ),
            extra=[("demo", "skip keys entirely, use offline sample data")],
        )
        if chosen == "demo":
            ui.out()
            ui.ok("no key needed - run the demo with:")
            ui.out(f"   {c('./maplead.py --demo', 'yellow', bold=True)}")
            return 0

    cls = PROVIDERS[chosen]
    ui.out()
    ui.out(ui.panel(f"set {cls.label}", [
        f"env var   {', '.join(cls.env_keys) if cls.env_keys else '(none - this provider needs no key)'}",
        f"get one   {cls.homepage}",
        f"saved to  {ENV_FILE if cls.env_keys else '(nothing to save)'}",
    ], color="cyan"))

    values: Dict[str, str] = {}
    for var in cls.env_keys:
        existing = os.environ.get(var, "").strip()
        raw = ui.ask_text(f"paste your {var}", default=existing if existing else "",
                          placeholder="paste the key, then press enter")
        raw = raw.strip().strip("'\"")
        if not raw:
            ui.error(f"{var} cannot be empty")
            return 2
        values[var] = raw

    # save first so validate() reads it from the environment
    if values:
        for var, val in values.items():
            save_key(var, val)
        ui.out()
        ui.ok(f"saved to {c(os.path.abspath(ENV_FILE), 'white', bold=True)} "
             f"{c('(chmod 600)', 'white', dim=True)}")
    else:
        ui.out()
        ui.info(f"{cls.label} needs no credentials - nothing to save.")

    valid = check_key(chosen)
    if valid:
        ui.out()
        ui.info("you are ready. next:")
        ui.out(f"   {c('./maplead.py', 'yellow', bold=True)}"
               f"   {c('→ interactive wizard', 'white', dim=True)}")
        if not args.yes and ui.ask_yesno("Start the lead wizard now?", True):
            args.provider = chosen
            ui.out()
            return run_wizard(args)
    else:
        ui.hint("the key is saved anyway — fix it and re-run:  ./maplead.py --api " + chosen)
    return 0 if valid else 1


def remove_keys(args: argparse.Namespace) -> int:
    only = getattr(args, "remove_key", None)
    targets = [only] if only else list(PROVIDERS)
    hit_any = False
    for name in targets:
        cls = PROVIDERS[name]
        if name == "demo":
            continue
        for var in cls.env_keys:
            if clear_key(var):
                hit_any = True
                ui.ok(f"cleared {var}")
    if not hit_any:
        ui.info("no stored keys to remove")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)

    try:
        if args.gui:
            passthrough = ["--provider", args.provider] if args.provider else []
            # the single binary links Qt, so the window is just a function call away
            try:
                from .gui.app import main as gui_main
            except ImportError as exc:
                ui.error(f"the desktop app needs PySide6 ({exc}).")
                ui.hint("pip install PySide6-Essentials   -or-   use the terminal wizard.")
                return 3
            return gui_main(passthrough)
        if args.api:
            return run_api_setup(args)
        if args.check_keys:
            ui.out()
            ui.out(art.banner(status="api key check", compact=True))
            names = [args.provider] if args.provider else [n for n in ORDER]
            results = [check_key(n) for n in names]
            ui.out()
            if not any(results):
                ui.warn("no working key found")
                ui.hint("set one with:  ./maplead.py --api")
            return 0 if any(results) else 1
        if args.remove_keys:
            return remove_keys(args)
        if args.list_providers:
            print_provider_status()
            return 0
        if args.list_fields:
            print_field_catalogue(args.provider)
            return 0
        if args.doctor:
            print_diagnostics()
            return 0
        return run_wizard(args)
    except KeyboardInterrupt:
        ui.out()
        ui.warn("aborted - nothing was changed.")
        return 130
    except Exception as exc:  # last-resort: never dump a raw traceback at users
        ui.out()
        ui.error(f"unexpected error: {exc}")
        if os.environ.get("MAPLEAD_DEBUG"):
            import traceback
            traceback.print_exc()
        else:
            ui.hint("set MAPLEAD_DEBUG=1 to see the full traceback")
        return 1


if __name__ == "__main__":
    sys.exit(main())