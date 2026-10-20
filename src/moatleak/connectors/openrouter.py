"""OpenRouter activity connector (the only network code in moatleak).

Reads GET /api/v1/activity with a user-supplied management key and maps the
result to ledger rows. The key is never included in any message or output.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import urllib.error
import urllib.request

from moatleak.ledger import LedgerRow

ACTIVITY_URL = "https://openrouter.ai/api/v1/activity"
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class ConnectorError(Exception):
    pass


def activity_url(date: str | None = None) -> str:
    if date is None:
        return ACTIVITY_URL
    if not isinstance(date, str) or not _DATE_RE.fullmatch(date):
        raise ConnectorError("date must be in YYYY-MM-DD format")
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise ConnectorError("date must be a real calendar date (YYYY-MM-DD)") from None
    return f"{ACTIVITY_URL}?date={date}"


def read_key(env_name: str, environ=None) -> str:
    env = os.environ if environ is None else environ
    value = (env.get(env_name) or "").strip()
    if not value:
        raise ConnectorError(f"Environment variable {env_name} is not set")
    if not all(0x21 <= ord(c) <= 0x7E for c in value):
        raise ConnectorError(f"Environment variable {env_name} contains invalid characters")
    return value


def _scrub(text: str, key: str) -> str:
    return text.replace(key, "***") if key else text


def _server_message(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read(4096).decode("utf-8", "replace"))
        msg = body["error"]["message"]
        if isinstance(msg, str):
            return msg[:200]
    except Exception:
        pass
    return str(exc.reason or "error")[:200]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ConnectorError("unexpected redirect")


def _default_open(req, timeout=None):
    return urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout)


def fetch_activity(key: str, *, date: str | None = None, opener=None,
                   timeout: float = 30) -> list[dict]:
    url = activity_url(date)
    opener = opener or _default_open
    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    try:
        with opener(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        msg = f"OpenRouter returned HTTP {e.code}: {_scrub(_server_message(e), key)}"
        if e.code == 403:
            msg += " — this endpoint needs a management key"
        raise ConnectorError(msg) from None
    except urllib.error.URLError as e:
        raise ConnectorError(
            "Could not reach OpenRouter: " + _scrub(str(e.reason)[:100], key)) from None
    except TimeoutError:
        raise ConnectorError("Request to OpenRouter timed out") from None
    except OSError as e:
        raise ConnectorError(
            "Network error talking to OpenRouter: " + _scrub(type(e).__name__, key)) from None
    except (ValueError, UnicodeError) as e:
        raise ConnectorError(
            "Could not send the request: " + type(e).__name__) from None
    try:
        body = json.loads(raw)
    except (ValueError, TypeError):
        raise ConnectorError("OpenRouter returned invalid JSON") from None
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        raise ConnectorError("OpenRouter response has no 'data' list")
    return data


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def rows_from_activity(items: list[dict]) -> list[LedgerRow]:
    acc: dict[tuple[str, str, str], dict] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        date, model = it.get("date"), it.get("model")
        if not isinstance(date, str) or not _DATE_RE.fullmatch(date):
            continue
        if not isinstance(model, str) or not model:
            continue
        reqs = _int(it.get("requests"))
        if reqs <= 0:
            continue
        ep = it.get("endpoint_id")
        ep = ep if isinstance(ep, str) else ""
        a = acc.setdefault((date, ep, model),
                           {"prov": None, "req": 0, "in": 0, "out": 0})
        a["req"] += reqs
        a["in"] += _int(it.get("prompt_tokens"))
        a["out"] += _int(it.get("completion_tokens"))
        prov = it.get("provider_name")
        if a["prov"] is None and isinstance(prov, str) and prov:
            a["prov"] = prov
    rows = [
        LedgerRow(source="openrouter_activity", source_ref=f"{d}|{ep}|{m}", ts=d,
                  route="router", endpoint="openrouter.ai", requested_model=m,
                  served_by_raw=a["prov"], requests=a["req"],
                  input_tokens=a["in"], output_tokens=a["out"],
                  evidence="provider_api")
        for (d, ep, m), a in acc.items()
    ]
    rows.sort(key=lambda r: (r.ts, r.source_ref))
    return rows
