"""
Background work.

Everything that touches the network (harvesting, key validation) runs on a
QThread so the window never freezes; results come back as signals.
"""

from __future__ import annotations

import datetime
import os
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from .. import engine, exporters, paths
from ..data import countries as CO
from ..data import fields as FD
from ..net import ApiError
from ..providers import Provider, get_provider


@dataclass
class SearchSpec:
    """Everything the GUI collects before a run."""

    provider_name: str = "demo"
    country: Optional[CO.Country] = None
    region: str = ""
    city: str = ""
    business_label: str = ""
    terms: List[str] = field(default_factory=list)
    fields: List[str] = field(default_factory=list)
    limit: int = 60
    language: str = "en"
    min_rating: Optional[float] = None
    min_reviews: Optional[int] = None
    require_phone: bool = False
    require_website: bool = False
    skip_closed: bool = False
    enrich: bool = False
    fmt: str = "csv"
    outpath: str = ""
    outdir: str = ""


@dataclass
class RunResult:
    leads: List[Dict[str, Any]]
    report: engine.HarvestReport
    stats: Dict[str, Any]
    columns: List[str]
    outpath: str
    fmt: str
    exported: bool = False
    error: str = ""
    error_hint: str = ""


def build_plan(spec: SearchSpec) -> engine.SearchPlan:
    """Turn the GUI inputs into the same SearchPlan the CLI builds."""
    provider: Provider = get_provider(spec.provider_name)
    country = spec.country or CO.find("United States")[0]
    fields = [f for f in spec.fields if provider.supports(f)]
    return engine.SearchPlan(
        provider=provider,
        city=spec.city,
        region=spec.region,
        country=country.name,
        country_code=country.iso,
        dial=country.dial,
        terms=list(spec.terms) or [spec.business_label or "business"],
        fields=fields,
        limit=max(1, spec.limit),
        language=spec.language or country.lang,
        min_rating=spec.min_rating,
        min_reviews=spec.min_reviews,
        require_phone=spec.require_phone,
        require_website=spec.require_website,
        skip_closed=spec.skip_closed,
        enrich=spec.enrich,
    )


_ERROR_HINTS = (
    ("REQUEST_INVALID_API_KEY", "That key is not valid for this API."),
    ("API key not valid", "That key is not valid for this API."),
    ("API_KEY_INVALID", "That key is not valid for this API."),
    ("Invalid API key", "That key is not valid for this API."),
    ("PERMISSION_DENIED", "Key is valid, but Places API (New) is probably not enabled "
                          "on the project - enable it and billing in Google Cloud Console."),
    ("403", "The key was rejected - check the plan / quota on the provider dashboard."),
    ("401", "Authentication failed - double-check the key you pasted."),
    ("429", "Rate limited right now - wait a minute and try again."),
    ("ENABLE", "The API is not enabled on your project yet."),
)


def explain(exc: Exception) -> str:
    msg = str(exc).lower()
    for needle, hint in _ERROR_HINTS:
        if needle.lower() in msg:
            return hint
    return ""


class HarvestWorker(QObject):
    """Runs engine.harvest + export off the GUI thread."""

    log = Signal(str, str)          # message, level
    progress = Signal(float)        # 0..1
    finished = Signal(object)        # RunResult
    failed = Signal(str, str)        # message, hint

    def __init__(self, spec: SearchSpec, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.spec = spec
        self._stop = False
        self._queries = 1
        self._value = 0.0

    def stop(self) -> None:
        self._stop = True

    # -- slot ---------------------------------------------------------------
    def run(self) -> None:
        spec = self.spec
        try:
            plan = build_plan(spec)
        except Exception as exc:
            self.failed.emit(f"Could not build the search: {exc}", "")
            return

        self._queries = max(1, len(plan.queries()))
        self.log.emit(f"Plan: {plan.label}", "query")
        self.log.emit(f"Provider {plan.provider.label} · up to "
                      f"{plan.provider.per_query_cap} results per query", "info")

        try:
            leads, report = engine.harvest(
                plan,
                progress=self._on_progress,
                should_stop=lambda: self._stop,
            )
        except ApiError as exc:
            self.failed.emit(str(exc), explain(exc))
            return
        except Exception as exc:
            detail = traceback.format_exc(limit=3) if _debug() else ""
            self.failed.emit(f"Unexpected error: {exc}", detail)
            return

        if self._stop:
            self.log.emit("Stopped by user.", "warn")

        stats = engine.summarize(leads)
        include_extra = len(spec.fields) >= 0.8 * len(FD.FIELDS)
        columns = exporters.build_columns(plan.fields, leads, include_extra=include_extra)
        meta = {
            "query": f"{plan.terms[0]} in {plan.location_label}" if plan.location_label
                     else plan.terms[0],
            "location": plan.location_label,
            "business": ", ".join(plan.terms),
            "provider": f"{plan.provider.label} ({plan.provider.name})",
            "fields": len(columns),
            "generated_at": _now(),
        }
        result = RunResult(leads=leads, report=report, stats=stats,
                           columns=columns, outpath=spec.outpath, fmt=spec.fmt)

        if leads and spec.outpath:
            try:
                paths.ensure_dir(os.path.dirname(os.path.abspath(spec.outpath)) or ".")
                info = exporters.write(spec.fmt, spec.outpath, leads, columns, meta)
                result.exported = True
                self.log.emit(f"Wrote {info['rows']} rows × {info['columns']} columns "
                              f"→ {spec.outpath}", "ok")
            except OSError as exc:
                result.error = f"Could not write {spec.outpath}: {exc}"
                self.log.emit(result.error, "error")
        self.finished.emit(result)
        self.progress.emit(1.0)

    # -- progress ------------------------------------------------------------
    def _on_progress(self, message: str) -> None:
        level = "error" if message.startswith(("query failed", "stopped")) else "query"
        self.log.emit(message, level)
        if message.startswith("query "):
            try:
                done = int(message.split()[1].split("/")[0]) - 1
            except (IndexError, ValueError):
                done = 0
            self._value = min(0.95, (done + 0.5) / self._queries)
        self.progress.emit(self._value)


class ValidateWorker(QObject):
    """Live key check for one provider (blocking, off the GUI thread)."""

    done = Signal(str, bool, str)   # provider, ok, message

    def __init__(self, provider_name: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.provider_name = provider_name

    def run(self) -> None:
        try:
            provider = get_provider(self.provider_name)
            ok, message = provider.validate()
        except ApiError as exc:
            self.done.emit(self.provider_name, False, f"{exc} — {explain(exc)}")
            return
        except Exception as exc:
            self.done.emit(self.provider_name, False, f"Could not reach the API: {exc}")
            return
        self.done.emit(self.provider_name, ok, message)


def _debug() -> bool:
    return os.environ.get("MAPLEAD_DEBUG", "") not in ("", "0", "false", "no")


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")