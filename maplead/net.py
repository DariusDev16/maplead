"""
Tiny JSON HTTP client built on urllib (zero dependencies).
Handles retries, exponential backoff, 429/5xx and pretty error extraction.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

USER_AGENT = "maplead/1.0 (python-urllib)"
DEFAULT_TIMEOUT = 45


class ApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None,
                 provider: str = "", payload: Any = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.provider = provider
        self.payload = payload

    def __str__(self) -> str:  # pragma: no cover
        if self.provider:
            return f"[{self.provider}] {self.message}"
        return self.message


class RateLimiter:
    """Simple minimum-interval throttle (per provider)."""

    def __init__(self, per_second: float = 5.0):
        self.min_interval = 1.0 / per_second if per_second > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        delta = time.time() - self._last
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last = time.time()


def _extract_error(body: bytes, status: int) -> str:
    text = ""
    try:
        text = body.decode("utf-8", "replace")
    except Exception:
        return f"HTTP {status}"
    try:
        data = json.loads(text)
    except Exception:
        text = " ".join(text.split())[:300]
        return f"HTTP {status}: {text}" if text else f"HTTP {status}"
    if isinstance(data, Mapping):
        err = data.get("error")
        if isinstance(err, Mapping):
            msg = err.get("message") or err.get("status") or json.dumps(err)[:300]
            return f"{msg} (HTTP {status})"
        if isinstance(err, str):
            return f"{err} (HTTP {status})"
        for key in ("message", "detail", "info", "error_message", "status_message", "status"):
            if key in data and isinstance(data[key], (str, int)):
                return f"{data[key]} (HTTP {status})"
        tasks = data.get("tasks")
        if isinstance(tasks, list) and tasks:
            t = tasks[0]
            if isinstance(t, Mapping):
                emsg = t.get("status_message")
                if emsg:
                    return f"{emsg} (HTTP {status})"
    if isinstance(data, list) and data:
        return f"{str(data[0])[:280]} (HTTP {status})"
    return f"HTTP {status}: {text[:280]}"


def request_json(method: str, url: str, *,
                 params: Mapping[str, Any] | None = None,
                 body: Any = None,
                 headers: Mapping[str, str] | None = None,
                 timeout: int = DEFAULT_TIMEOUT,
                 retries: int = 3,
                 backoff: float = 1.7,
                 provider: str = "") -> Any:
    """Perform an HTTP request and decode the JSON response."""
    if params:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        if clean:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(clean, doseq=True)

    data = None
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update({k: v for k, v in headers.items() if v})

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                try:
                    return json.loads(raw.decode("utf-8", "replace"))
                except json.JSONDecodeError:
                    return {"_raw": raw.decode("utf-8", "replace")[:20000]}
        except urllib.error.HTTPError as exc:
            raw = exc.read() if hasattr(exc, "read") else b""
            msg = _extract_error(raw, exc.code)
            if exc.code in (400, 401, 403, 404) and exc.code not in (429,):
                raise ApiError(msg, exc.code, provider, raw[:2000]) from None
            last_err = ApiError(msg, exc.code, provider, raw[:2000])
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            if retry_after and retry_after.isdigit():
                time.sleep(min(60, int(retry_after)))
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            last_err = ApiError(f"network error: {reason}", provider=provider)
        except (TimeoutError, OSError) as exc:
            last_err = ApiError(f"connection problem: {exc}", provider=provider)
        except KeyboardInterrupt:
            raise
        if attempt < retries:
            time.sleep(backoff ** attempt + 0.15 * attempt)

    assert last_err is not None
    raise last_err


def get_json(url: str, **kw) -> Any:
    return request_json("GET", url, **kw)


def post_json(url: str, **kw) -> Any:
    return request_json("POST", url, **kw)