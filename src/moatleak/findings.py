"""Aggregate resolved ledger rows into network, footprint, growth and fragmentation metrics."""
from collections import Counter
import dataclasses
from dataclasses import dataclass, field

from moatleak.resolve import Resolved

_DAILY_EVIDENCE = {"observed", "rule", "provider_api"}
_ACTIVITY = "openrouter_activity"


@dataclass
class Summary:
    period: tuple[str, str] = ("", "")
    total_requests: int = 0
    days_active: int = 0
    coverage_note: str = ""
    earlier: dict = field(default_factory=lambda: {
        "requests": 0, "unattributed_requests": 0, "first": None, "last": None})
    providers: Counter = field(default_factory=Counter)
    unknown_provider_requests: int = 0
    parents: Counter = field(default_factory=Counter)
    parent_names: dict = field(default_factory=dict)
    parent_display_names: dict = field(default_factory=dict)
    countries: Counter = field(default_factory=Counter)
    confidence: Counter = field(default_factory=Counter)
    regimes: Counter = field(default_factory=Counter)
    cloud_hosts: Counter = field(default_factory=Counter)
    n_providers: int = 0
    n_parents_known: int = 0
    n_countries_known: int = 0
    country_share: dict = field(default_factory=dict)
    undisclosed_share: float = 0.0
    first_seen: dict = field(default_factory=dict)
    new_providers_by_day: dict = field(default_factory=dict)
    growth_window: dict = field(default_factory=lambda: {"first": None, "last": None, "count": 0})
    providers_per_session: dict = field(default_factory=dict)
    sessions_with_provider: int = 0
    multi_provider_sessions: int = 0
    max_session_spread: dict | None = None
    daily_matrix: dict = field(default_factory=dict)
    withheld: dict = field(default_factory=dict)
    models: Counter = field(default_factory=Counter)
    tools: Counter = field(default_factory=Counter)
    via_router_requests: int = 0
    provider_info: dict = field(default_factory=dict)
    access: Counter = field(default_factory=Counter)
    routes: Counter = field(default_factory=Counter)
    provider_locations: dict = field(default_factory=dict)


def _date(r: Resolved) -> str:
    return r.row.ts[:10]


def dedupe(resolved: list[Resolved]) -> list[Resolved]:
    """Drop hermes_db rows whose session_ref appears on any hermes_log row."""
    logged = {r.row.session_ref for r in resolved
              if r.row.source == "hermes_log" and r.row.session_ref}
    return [r for r in resolved
            if not (r.row.source == "hermes_db" and r.row.session_ref in logged)]


def _is_log_router(r: Resolved) -> bool:
    return r.row.route == "router" and r.row.source != _ACTIVITY


def _top_up(rows: list[Resolved], covered: set[str]) -> list[Resolved]:
    """Volume rows: activity tops up per-call logs (max per covered day and provider)."""
    logged: Counter = Counter()
    for r in rows:
        if _is_log_router(r) and _date(r) in covered and r.provider_id is not None:
            logged[(_date(r), r.provider_name)] += r.row.requests
    out: list[Resolved] = []
    act: dict[tuple, list[Resolved]] = {}
    for r in rows:
        d = _date(r)
        if d in covered and _is_log_router(r) and r.provider_id is None:
            continue  # aggregate rows without provider: activity covers those calls
        if r.row.source == _ACTIVITY and r.provider_id is not None:
            act.setdefault((d, r.provider_name), []).append(r)
        else:
            out.append(r)
    for key, group in act.items():
        excess = logged[key]
        for r in sorted(group, key=lambda x: x.row.source_ref):
            n = r.row.requests
            cut = min(n, excess)
            excess -= cut
            keep = n - cut
            if keep <= 0:
                continue
            if keep == n:
                out.append(r)
                continue
            row = dataclasses.replace(
                r.row, requests=keep,
                input_tokens=int(r.row.input_tokens * keep / n),
                output_tokens=int(r.row.output_tokens * keep / n))
            out.append(dataclasses.replace(r, row=row))
    return out


def summarise(resolved: list[Resolved]) -> Summary:
    rows = dedupe(resolved)
    s = Summary()
    if not rows:
        return s

    # Activity tops up the per-call logs: per covered day and provider the volume is
    # max(activity, logged); logged calls keep their tool, only the surplus is "Unknown tool".
    covered = {_date(r) for r in rows if r.row.source == _ACTIVITY}
    vol = _top_up(rows, covered) if covered else rows
    percall = [_date(r) for r in rows if r.row.route == "router" and r.row.evidence == "observed"]
    api = [_date(r) for r in rows if r.row.evidence == "provider_api"]
    starts = percall + api
    start = min(starts) if starts else min(_date(r) for r in vol or rows)
    end = max(_date(r) for r in vol or rows)
    s.period = (start, end)
    if covered:
        b = min(percall) if percall else start
        s.coverage_note = (f"Daily OpenRouter activity from {min(covered)}; "
                           f"per-call provider data from {b}.")
    else:
        s.coverage_note = f"Per-call provider data from {start}."

    inwin = [r for r in vol if _date(r) >= start]
    before = [r for r in vol if _date(r) < start]

    if before:
        dates = [_date(r) for r in before]
        s.earlier = {
            "requests": sum(r.row.requests for r in before),
            "unattributed_requests": sum(r.row.requests for r in before if r.provider_id is None),
            "first": min(dates), "last": max(dates),
        }

    s.total_requests = sum(r.row.requests for r in inwin)
    s.days_active = len({_date(r) for r in inwin})

    for r in inwin:
        n = r.row.requests
        if r.provider_id is not None:
            s.providers[r.provider_name] += n
            info = s.provider_info.setdefault(r.provider_name, {
                "provider_id": r.provider_id, "parent_id": r.parent_id,
                "parent": r.parent,
                "parent_display": (r.parent_display or r.parent) if r.parent else None,
                "country": None})
            if info["country"] is None and r.country:
                info["country"] = r.country
            s.provider_locations.setdefault(r.provider_name, Counter())[
                (r.country or None, r.location_confidence)] += n
        else:
            s.unknown_provider_requests += n
        s.access[r.access] += n
        s.routes[(r.tool, r.access, r.provider_name if r.provider_id is not None else None)] += n
        s.parents[r.parent_id or "unknown"] += n
        if r.parent_id and r.parent:
            s.parent_names[r.parent_id] = r.parent
            s.parent_display_names[r.parent_id] = r.parent_display or r.parent
        s.countries[r.country if r.country else r.location_confidence] += n
        s.confidence[r.location_confidence] += n
        for regime in r.regimes:
            s.regimes[regime] += n
        if r.cloud_host:
            s.cloud_hosts[r.cloud_host] += n
        s.models[r.row.requested_model] += n
        s.tools[r.tool] += n
        if r.via_router:
            s.via_router_requests += n
        if r.provider_id is not None and r.row.evidence in _DAILY_EVIDENCE:
            day = s.daily_matrix.setdefault(_date(r), {})
            day[r.provider_name] = day.get(r.provider_name, 0) + n

    s.n_providers = len(s.providers)
    s.n_parents_known = sum(1 for k in s.parents if k != "unknown")
    s.n_countries_known = sum(1 for k in s.countries if k not in ("withheld", "unknown"))
    if s.total_requests:
        s.country_share = {k: v / s.total_requests for k, v in s.countries.items()}
        s.undisclosed_share = (s.countries["withheld"] + s.countries["unknown"]) / s.total_requests

    # Growth: all history
    for r in rows:
        if r.row.evidence in ("observed", "provider_api") and r.provider_id is not None:
            d = _date(r)
            if r.provider_name not in s.first_seen or d < s.first_seen[r.provider_name]:
                s.first_seen[r.provider_name] = d
    by_day: dict[str, list[str]] = {}
    for name, d in s.first_seen.items():
        by_day.setdefault(d, []).append(name)
    s.new_providers_by_day = {d: sorted(v) for d, v in sorted(by_day.items())}
    gw = sorted(d for d in s.first_seen.values() if d >= start)
    if gw:
        s.growth_window = {"first": gw[0], "last": gw[-1], "count": len(gw)}

    # Fragmentation: in window, observed, provider and session known
    countries_per_session: dict[str, set] = {}
    for r in rows:
        if _date(r) < start:
            continue
        if r.row.evidence == "observed" and r.provider_id is not None and r.row.session_ref:
            ref = r.row.session_ref
            s.providers_per_session.setdefault(ref, set()).add(r.provider_name)
            cs = countries_per_session.setdefault(ref, set())
            if r.country:
                cs.add(r.country)
    s.sessions_with_provider = len(s.providers_per_session)
    s.multi_provider_sessions = sum(1 for v in s.providers_per_session.values() if len(v) >= 2)
    best = None
    for ref, names in s.providers_per_session.items():
        names_t = tuple(sorted(names))
        cs = sorted(countries_per_session[ref])
        key = (-len(names_t), -len(cs), names_t)
        if best is None or key < best[0]:
            best = (key, names_t, cs)
    if best:
        s.max_session_spread = {"providers": list(best[1]), "countries": best[2],
                                "n_providers": len(best[1]), "n_countries": len(best[2])}

    # Withheld: all history
    for r in rows:
        if r.location_confidence != "withheld":
            continue
        w = s.withheld.setdefault(r.provider_name, {
            "requests": 0, "first": _date(r), "last": _date(r), "tools": set()})
        w["requests"] += r.row.requests
        w["first"] = min(w["first"], _date(r))
        w["last"] = max(w["last"], _date(r))
        w["tools"].add(r.tool)
    for w in s.withheld.values():
        w["tools"] = sorted(w["tools"])
    return s
