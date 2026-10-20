"""The report data contract: report_payload() is the only data the report sees."""
from datetime import date, timedelta

from moatleak import __version__
from moatleak.headlines import CONF_LABELS, country_name

_FOOTNOTE = "Daily counts exclude aggregate Hermes DB rows, which carry only a session start time."
_SPECIAL = {"withheld": "Withheld", "unknown": "Unknown"}


def _known(v):
    return None if v in (None, "", "unknown") else v


def _parent_source(provider: dict) -> str | None:
    for src in provider.get("sources", []):
        if src.get("claim") == "parent":
            return src.get("url")
    return None


def _days(period) -> list[str]:
    if not period[0] or not period[1]:
        return []
    d, end = date.fromisoformat(period[0]), date.fromisoformat(period[1])
    out = []
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _providers(summary, registry) -> list[dict]:
    out = []
    for name, total in summary.providers.items():
        info = summary.provider_info[name]
        reg = registry.providers.get(info["provider_id"], {})
        locs = summary.provider_locations.get(name, {})
        locations = [{"country": c, "confidence": conf, "requests": n}
                     for (c, conf), n in sorted(
                         locs.items(), key=lambda kv: (-kv[1], kv[0][0] or "", kv[0][1]))]
        by_country: dict = {}
        for (c, _conf), n in locs.items():
            if c is not None:
                by_country[c] = by_country.get(c, 0) + n
        primary = sorted(by_country.items(), key=lambda kv: (-kv[1], kv[0]))
        parent_id = info["parent_id"]
        short = info["parent_display"] if parent_id else None
        out.append({
            "id": info["provider_id"], "name": name, "requests": total,
            "country": primary[0][0] if primary else None,
            "locations": locations,
            "parent_id": parent_id, "parent": short,
            "parent_legal": info["parent"] if parent_id else None,
            "parent_source": _parent_source(reg) if parent_id else None,
            "parent_same_name": bool(parent_id and short and short.casefold() == name.casefold()),
            "first_seen": summary.first_seen.get(name),
            "recognisable": bool(reg.get("recognisable", False)),
        })
    out.sort(key=lambda p: (-p["requests"], p["name"]))
    if summary.unknown_provider_requests > 0:
        n = summary.unknown_provider_requests
        out.append({
            "id": "unknown", "name": "Unknown company", "requests": n, "country": None,
            "locations": [{"country": None, "confidence": "unknown", "requests": n}],
            "parent_id": None, "parent": None, "parent_legal": None, "parent_source": None,
            "parent_same_name": False, "first_seen": None, "recognisable": False})
    return out


def _loc_key(country, confidence) -> str:
    return country if country is not None else confidence


def _network(summary, registry, providers, footprint_countries) -> dict:
    nodes = {}
    edges: dict = {}

    def node(nid, label, layer, requests, **extra):
        if requests > 0:
            nodes[nid] = {"id": nid, "label": label, "layer": layer, "requests": requests, **extra}

    def edge(a, b, n):
        if n > 0:
            edges[(a, b)] = edges.get((a, b), 0) + n

    node("you", "You", "you", summary.total_requests)
    for tool, n in summary.tools.items():
        node(f"tool:{tool}", tool, "tool", n)
        edge("you", f"tool:{tool}", n)
    for label, n in summary.access.items():
        node(f"access:{label}", label, "access", n)

    pid_of = {p["name"]: f"provider:{p['id']}" for p in providers}
    for (tool, label, pname), n in summary.routes.items():
        target = pid_of["Unknown company"] if pname is None else pid_of[pname]
        edge(f"tool:{tool}", f"access:{label}", n)
        edge(f"access:{label}", target, n)

    parents: dict = {}
    for p in providers:
        conf: dict = {}
        for loc in p["locations"]:
            conf[loc["confidence"]] = conf.get(loc["confidence"], 0) + loc["requests"]
        top_conf = sorted(conf.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        nid = f"provider:{p['id']}"
        node(nid, p["name"], "provider", p["requests"], country=p["country"],
             confidence=top_conf, parent_id=p["parent_id"])
        if p["parent_id"]:
            par = parents.setdefault(p["parent_id"], {"providers": []})
            par["providers"].append(p)
            edge(nid, f"parent:{p['parent_id']}", p["requests"])
        for loc in p["locations"]:
            src = f"parent:{p['parent_id']}" if p["parent_id"] else nid
            edge(src, f"country:{_loc_key(loc['country'], loc['confidence'])}", loc["requests"])

    for parent_id, par in parents.items():
        provs = par["providers"]
        reg = registry.providers.get(provs[0]["id"], {})
        node(f"parent:{parent_id}", provs[0]["parent"], "parent",
             sum(p["requests"] for p in provs), legal_name=provs[0]["parent_legal"],
             source=provs[0]["parent_source"], country=_known(reg.get("ultimate_parent_country")),
             parent_same_name=all(p["parent_same_name"] for p in provs))

    for key, n in footprint_countries.items():
        node(f"country:{key}", _SPECIAL.get(key) or country_name(key), "country", n)

    return {"nodes": list(nodes.values()),
            "edges": [{"source": a, "target": b, "requests": n} for (a, b), n in edges.items()]}


def report_payload(summary, headlines, registry, *, include_models: bool = True,
                   content: dict | None = None) -> dict:
    total = summary.total_requests
    providers = _providers(summary, registry)
    countries = dict(summary.countries)

    regimes = []
    for rid, n in summary.regimes.items():
        r = registry.regimes.get(rid, {})
        regimes.append({"id": rid, "name": r.get("name", rid), "country": r.get("country"),
                        "summary": r.get("summary", ""), "source": r.get("source"),
                        "requests": n, "share": n / total if total else 0.0})
    regimes.sort(key=lambda r: (-r["requests"], r["id"]))

    codes = {c for c in countries if c not in _SPECIAL}
    codes |= {loc["country"] for p in providers for loc in p["locations"] if loc["country"]}
    codes |= {r["country"] for r in regimes if r["country"]}
    for p in providers:
        codes.add(_known(registry.providers.get(p["id"], {}).get("ultimate_parent_country")))
    if summary.max_session_spread:
        codes |= set(summary.max_session_spread["countries"])
    codes.discard(None)

    spread = summary.max_session_spread
    return {
        "content": content,
        "schema": 1, "tool_version": __version__, "registry_version": registry.version,
        "empty": total == 0,
        "period": list(summary.period) if total else [None, None],
        "days": len(_days(summary.period)),
        "days_active": summary.days_active,
        "total_requests": total,
        "coverage_note": summary.coverage_note,
        "earlier": dict(summary.earlier),
        "counts": {
            "companies": summary.n_providers, "parent_groups": summary.n_parents_known,
            "countries": summary.n_countries_known,
            "unknown_provider_requests": summary.unknown_provider_requests,
            "via_router_requests": summary.via_router_requests,
            "sessions_with_provider": summary.sessions_with_provider,
            "multi_provider_sessions": summary.multi_provider_sessions,
        },
        "headlines": [{"kind": h.kind, "text": h.text, "value": h.value, "names": list(h.names),
                       "footnote": h.footnote} for h in headlines],
        "country_names": {c: country_name(c) for c in sorted(codes)},
        "providers": providers,
        "network": _network(summary, registry, providers, countries),
        "footprint": {
            "countries": countries, "country_share": dict(summary.country_share),
            "undisclosed_share": summary.undisclosed_share,
            "confidence": dict(summary.confidence), "regimes": regimes,
        },
        "timeline": {
            "days": _days(summary.period),
            "daily_matrix": {d: dict(v) for d, v in summary.daily_matrix.items()},
            "first_seen": {p["name"]: p["first_seen"] for p in providers if p["first_seen"]},
            "data_start": summary.period[0] if total else None,
            "coverage_note": summary.coverage_note, "footnote": _FOOTNOTE,
        },
        "fragmentation": {
            "multi_provider_sessions": summary.multi_provider_sessions,
            "sessions_with_provider": summary.sessions_with_provider,
            "max_session_spread": (
                {"providers": list(spread["providers"]), "countries": list(spread["countries"]),
                 "n_providers": spread["n_providers"], "n_countries": spread["n_countries"]}
                if spread else None),
        },
        "withheld": sorted(
            ({"provider": n, "requests": w["requests"], "first": w["first"], "last": w["last"],
              "tools": list(w["tools"])} for n, w in summary.withheld.items()),
            key=lambda w: (-w["requests"], w["provider"])),
        "include_models": include_models,
        "models": ([{"slug": k, "requests": v} for k, v in
                    sorted(summary.models.items(), key=lambda kv: (-kv[1], kv[0]))]
                   if include_models else []),
        "tools": dict(summary.tools),
        "access": dict(sorted(summary.access.items(), key=lambda kv: (-kv[1], kv[0]))),
        "routes": sorted(
            ({"tool": t, "access": a, "provider": pn or "Unknown company", "requests": n}
             for (t, a, pn), n in summary.routes.items()),
            key=lambda e: (-e["requests"], e["tool"], e["access"], e["provider"])),
        "confidence_labels": dict(CONF_LABELS),
    }
