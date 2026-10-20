"""Resolve a ledger row to provider, parent, location and legal context."""
import re
from dataclasses import dataclass

from moatleak.ledger import LedgerRow
from moatleak.registry import Registry

_GEO = re.compile(r"^[A-Za-z]{2}$")
_MAKER_PATTERNS = [
    (re.compile(r"^claude-"), "anthropic"),
    (re.compile(r"^(gpt-|o[0-9])"), "openai"),
    (re.compile(r"^gemini-"), "google"),
    (re.compile(r"^deepseek-"), "deepseek"),
]


@dataclass
class Resolved:
    row: LedgerRow
    provider_id: str | None
    provider_name: str
    parent: str | None
    country: str | None
    region_label: str | None
    location_confidence: str
    regimes: list[str]
    parent_id: str | None
    parent_country: str | None
    cloud_host: str | None
    tool: str
    requested_maker: str
    via_router: bool
    parent_display: str | None = None
    access: str = ""


def _known(value):
    return None if value in (None, "unknown", "") else value


def _tool(source: str) -> str:
    if source.startswith("hermes_"):
        return "Hermes"
    if source == "claude_code":
        return "Claude Code"
    return source


def _maker(model: str, registry: Registry) -> str:
    if "/" in model:
        prefix = model.split("/", 1)[0]
        return registry.makers.get(prefix, prefix)
    for pattern, slug in _MAKER_PATTERNS:
        if pattern.match(model):
            return registry.makers.get(slug, slug)
    return "unknown"


def _location(row: LedgerRow, provider: dict | None):
    geo = row.reported_geo
    if geo == "not_available":
        return None, "withheld"
    if geo and _GEO.match(geo):
        return geo.upper(), "reported"
    if provider:
        regions = provider.get("serving_regions") or []
        docs = {r.get("region") for r in regions
                if isinstance(r, dict) and r.get("basis") != "hq" and r.get("region")}
        if len(docs) == 1:
            return next(iter(docs)), "documented"
        hq = provider.get("hq")
        hq_country = _known(hq.get("country")) if isinstance(hq, dict) else None
        if hq_country:
            return hq_country, "hq_inferred"
    return None, "unknown"


def access_method(row: LedgerRow, registry: Registry) -> str:
    """Evidence-based access label; never claims an auth mode (none is logged)."""
    if row.endpoint == "openrouter.ai":
        return "OpenRouter"
    pid = registry.provider_for_endpoint(row.endpoint) if row.endpoint else None
    # "subscription" = legacy rows from older ledger.db files; resolves like "direct".
    if pid and row.route in ("direct", "subscription") and pid in registry.providers:
        return f"{registry.providers[pid]['display_name']} API (direct)"
    if row.endpoint and row.endpoint != "unknown":
        return row.endpoint
    return "Unknown access method"


def resolve(row: LedgerRow, registry: Registry) -> Resolved:
    pid = registry.provider_for_name(row.served_by_raw)
    if pid is None and row.route in ("direct", "subscription"):
        pid = registry.provider_for_endpoint(row.endpoint)
    provider = registry.providers.get(pid) if pid else None
    if provider is None:
        pid = None
    country, confidence = _location(row, provider)
    p = provider or {}
    return Resolved(
        row=row,
        provider_id=pid,
        provider_name=(p.get("display_name") if provider else None) or row.served_by_raw or "Unknown",
        parent=_known(p.get("parent")),
        country=country,
        region_label=None,
        location_confidence=confidence,
        regimes=list(p.get("legal_regimes") or []),
        parent_id=_known(p.get("parent_id")),
        parent_country=_known(p.get("ultimate_parent_country")),
        cloud_host=_known(p.get("cloud_host")),
        tool=_tool(row.source),
        requested_maker=_maker(row.requested_model, registry),
        via_router=row.route == "router",
        parent_display=_known(p.get("parent_display_name")),
        access=access_method(row, registry),
    )
