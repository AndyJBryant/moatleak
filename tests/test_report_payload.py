"""Contract + privacy tests for report_payload (synthetic fixtures only)."""
import json

from moatleak import __version__
from moatleak.findings import summarise
from moatleak.headlines import headlines
from moatleak.registry import Registry
from moatleak.report.payload import report_payload
from tests.test_findings import mk

SECRET_SESSIONS = ["s-SECRET-AAAA", "s-SECRET-BBBB", "s-SECRET-CCCC"]
FORBIDDEN_KEYS = {"session_ref", "source_ref", "providers_per_session"}


def _prov(pid, name, parent_id, parent_display, *, parent_country="US", source=True, rec=True):
    p = {"id": pid, "display_name": name, "recognisable": rec,
         "parent_id": parent_id, "parent_display_name": parent_display,
         "ultimate_parent_country": parent_country, "sources": []}
    if source:
        p["sources"].append({"url": f"https://example.com/{pid}/parent", "claim": "parent"})
    return p


def _registry():
    providers = {
        "alpha": _prov("alpha", "Alpha", "alpha-corp", "Alpha"),
        "beta": _prov("beta", "Beta", "group-one", "Group One", parent_country="CN"),
        "gamma": _prov("gamma", "Gamma", "group-one", "Group One", parent_country="CN"),
        "delta": _prov("delta", "Delta", None, None, parent_country="unknown", source=False, rec=False),
    }
    regimes = {
        "US-CLOUD-ACT": {"id": "US-CLOUD-ACT", "name": "CLOUD Act", "country": "US",
                         "summary": "Synthetic summary.", "source": "https://example.com/cloud"},
        "GDPR": {"id": "GDPR", "name": "GDPR", "country": "EU",
                 "summary": "Synthetic GDPR.", "source": "https://example.com/gdpr"},
    }
    return Registry(providers, {}, regimes, "test-1")


def _rows():
    return [
        mk("Alpha", "2026-09-22", parent="Alpha, PBC", parent_id="alpha-corp", parent_display="Alpha",
           session=SECRET_SESSIONS[0], requests=3, regimes=["US-CLOUD-ACT"]),
        mk("Alpha", "2026-09-23", parent="Alpha, PBC", parent_id="alpha-corp", parent_display="Alpha",
           country=None, conf="withheld", route="direct", requests=2, tool="Claude Code",
           session=SECRET_SESSIONS[1]),
        mk("Beta", "2026-09-23", parent="Group One Ltd", parent_id="group-one", parent_display="Group One",
           country="CN", conf="documented", session=SECRET_SESSIONS[0], requests=4),
        mk("Gamma", "2026-09-24", parent="Group One Ltd", parent_id="group-one", parent_display="Group One",
           country="SG", conf="hq_inferred", session=SECRET_SESSIONS[0], requests=1, regimes=["GDPR"]),
        mk("Delta", "2026-09-24", parent=None, parent_id=None, country="FR", conf="hq_inferred",
           session=SECRET_SESSIONS[2], requests=2),
        mk("Unknown", "2026-09-25", country=None, requests=5),
        mk("Alpha", "2026-08-01", route="direct", evidence="rule", requests=40),
    ]


def _build(include_models=True, rows=None, reg=None):
    s = summarise(rows if rows is not None else _rows())
    reg = reg or _registry()
    return report_payload(s, headlines(s, reg), reg, include_models=include_models), s, reg


def _walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield "key", k
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)
    else:
        yield "val", o


def test_header_and_counts():
    p, s, reg = _build()
    assert p["schema"] == 1 and p["tool_version"] == __version__ and p["registry_version"] == "test-1"
    assert p["empty"] is False
    assert p["period"] == ["2026-09-22", "2026-09-25"] and p["days"] == 4
    assert p["total_requests"] == 17 and p["days_active"] == 4
    assert p["earlier"]["requests"] == 40
    assert p["counts"] == {"companies": 4, "parent_groups": 2, "countries": 4,
                           "unknown_provider_requests": 5, "via_router_requests": 15,
                           "sessions_with_provider": 3, "multi_provider_sessions": 1}
    assert [h["kind"] for h in p["headlines"]] == [h.kind for h in headlines(s, reg)]
    assert p["tools"] == {"Hermes": 15, "Claude Code": 2}
    assert p["confidence_labels"]["hq_inferred"] == "HQ-inferred"
    assert p["country_names"]["US"] == "United States" and p["country_names"]["EU"] == "European Union"
    assert p["country_names"]["CN"] == "China"


def test_providers_list():
    p, _, _ = _build()
    names = [x["name"] for x in p["providers"]]
    assert names == ["Alpha", "Beta", "Delta", "Gamma", "Unknown company"]
    by = {x["name"]: x for x in p["providers"]}
    assert [x["requests"] for x in p["providers"][:-1]] == sorted(
        (x["requests"] for x in p["providers"][:-1]), reverse=True)
    a = by["Alpha"]
    assert a["id"] == "alpha" and a["requests"] == 5 and a["country"] == "US"
    assert a["locations"] == [{"country": "US", "confidence": "reported", "requests": 3},
                              {"country": None, "confidence": "withheld", "requests": 2}]
    assert a["parent_id"] == "alpha-corp" and a["parent"] == "Alpha" and a["parent_legal"] == "Alpha, PBC"
    assert a["parent_source"] == "https://example.com/alpha/parent"
    assert a["parent_same_name"] is True and a["recognisable"] is True
    assert a["first_seen"] == "2026-09-22"
    b = by["Beta"]
    assert b["parent_same_name"] is False and b["parent"] == "Group One"
    d = by["Delta"]
    assert d["parent_id"] is None and d["parent"] is None and d["parent_source"] is None
    assert d["parent_same_name"] is False and d["country"] == "FR"
    u = by["Unknown company"]
    assert u["id"] == "unknown" and u["requests"] == 5 and u["country"] is None
    assert u["locations"] == [{"country": None, "confidence": "unknown", "requests": 5}]
    assert u["first_seen"] is None and u["parent_same_name"] is False and u["recognisable"] is False


def test_network_structure():
    p, s, reg = _build()
    nodes = {n["id"]: n for n in p["network"]["nodes"]}
    edges = {(e["source"], e["target"]): e["requests"] for e in p["network"]["edges"]}
    assert len(edges) == len(p["network"]["edges"])
    for (a, b) in edges:
        assert a in nodes and b in nodes
    assert all(n["requests"] > 0 for n in nodes.values())
    assert nodes["you"]["requests"] == 17
    assert nodes["access:OpenRouter"]["requests"] == 15 and nodes["access:OpenRouter"]["layer"] == "access"
    assert not any(n["layer"] == "router" for n in nodes.values())
    parents = {n["id"]: n for n in nodes.values() if n["layer"] == "parent"}
    assert set(parents) == {"parent:alpha-corp", "parent:group-one"}
    g = parents["parent:group-one"]
    assert g["label"] == "Group One" and g["legal_name"] == "Group One Ltd"
    assert g["country"] == "CN" and g["parent_same_name"] is False and g["requests"] == 5
    assert parents["parent:alpha-corp"]["parent_same_name"] is True
    # unknown parent: straight to country
    assert ("provider:delta", "country:FR") in edges
    assert ("provider:unknown", "country:unknown") in edges
    assert not any(t.startswith("parent:") for (sx, t) in edges if sx == "provider:delta")
    assert nodes["country:withheld"]["label"] == "Withheld" and nodes["country:unknown"]["label"] == "Unknown"
    assert nodes["country:CN"]["label"] == "China"
    assert edges[("tool:Hermes", "access:OpenRouter")] == 15
    assert edges[("tool:Claude Code", "access:Anthropic API (direct)")] == 2
    assert edges[("access:OpenRouter", "provider:unknown")] == 5
    assert not any(a.startswith("tool:") and b.startswith("provider:") for (a, b) in edges)
    tot = p["total_requests"]
    assert sum(v for (a, b), v in edges.items() if a.startswith("tool:")) == tot
    assert sum(v for (a, b), v in edges.items() if a.startswith("access:")) == tot
    assert nodes["provider:alpha"]["confidence"] == "reported"
    assert nodes["provider:alpha"]["country"] == "US"
    assert nodes["provider:alpha"]["parent_id"] == "alpha-corp"


def test_network_sums_and_parent_sources():
    p, s, reg = _build()
    nodes = {n["id"]: n for n in p["network"]["nodes"]}
    edges = p["network"]["edges"]
    assert sum(e["requests"] for e in edges if e["source"] == "you") == s.total_requests
    for nid, n in nodes.items():
        if n["layer"] != "provider":
            continue
        inc = sum(e["requests"] for e in edges if e["target"] == nid)
        out = sum(e["requests"] for e in edges if e["source"] == nid)
        assert inc == out == n["requests"], nid
    for nid, n in nodes.items():
        if n["layer"] == "country":
            inc = sum(e["requests"] for e in edges if e["target"] == nid)
            assert inc == n["requests"], nid
        if n["layer"] != "parent":
            continue
        pid = nid.split(":", 1)[1]
        attached = [reg.providers[x["id"]] for x in p["providers"]
                    if x["parent_id"] == pid and x["id"] in reg.providers]
        assert attached and all(a["parent_id"] == pid for a in attached)
        urls = {src["url"] for a in attached for src in a["sources"] if src["claim"] == "parent"}
        assert n["source"] in urls


def test_footprint_timeline_other_sections():
    p, s, _ = _build()
    f = p["footprint"]
    assert f["countries"] == {"US": 3, "withheld": 2, "CN": 4, "SG": 1, "FR": 2, "unknown": 5}
    assert abs(f["country_share"]["CN"] - 4 / 17) < 1e-9
    assert abs(f["undisclosed_share"] - 7 / 17) < 1e-9
    assert f["confidence"]["reported"] == 3
    assert [r["id"] for r in f["regimes"]] == ["US-CLOUD-ACT", "GDPR"]
    assert f["regimes"][0]["id"] == "US-CLOUD-ACT" and f["regimes"][0]["share"] == 3 / 17
    assert f["regimes"][0]["name"] == "CLOUD Act" and f["regimes"][0]["source"] == "https://example.com/cloud"
    t = p["timeline"]
    assert t["days"] == ["2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"]
    assert t["data_start"] == "2026-09-22" and t["coverage_note"] == p["coverage_note"]
    assert set(t["first_seen"]) == {"Alpha", "Beta", "Gamma", "Delta"}
    assert t["footnote"] == "Daily counts exclude aggregate Hermes DB rows, which carry only a session start time."
    fr = p["fragmentation"]
    assert fr["max_session_spread"]["n_providers"] == 3
    assert p["withheld"] == [{"provider": "Alpha", "requests": 2, "first": "2026-09-23",
                              "last": "2026-09-23", "tools": ["Claude Code"]}]
    assert p["include_models"] is True and p["models"] == [{"slug": "vendor/model-a", "requests": 17}]
    assert p["coverage_note"] in p["headlines"][0]["footnote"]


def test_include_models_false():
    p, _, _ = _build(include_models=False)
    assert p["include_models"] is False and p["models"] == []


def test_privacy_and_serialisable():
    p, _, _ = _build()
    text = json.dumps(p)
    assert json.loads(text) == p
    for kind, v in _walk(p):
        if kind == "key":
            assert isinstance(v, str) and v not in FORBIDDEN_KEYS
        elif isinstance(v, str):
            assert "/home/" not in v and "/Users/" not in v
            assert "gen-1790773241" not in v and "SECRET" not in v
    assert "s-SECRET" not in text and "gen-1790773241" not in text


def test_size_budget():
    rows = []
    for i in range(40):
        for d in range(1, 31):
            rows.append(mk(f"Prov{i:02d}", f"2026-09-{d:02d}", country="US" if i % 2 else "CN",
                           session=f"s-SECRET-{i}-{d}"))
    reg = _registry()
    for i in range(40):
        reg.providers[f"prov{i:02d}"] = _prov(f"prov{i:02d}", f"Prov{i:02d}", f"prov{i:02d}-corp", f"Prov{i:02d}")
    p, _, _ = _build(rows=rows, reg=reg)
    assert len(json.dumps(p)) < 300_000


def test_empty():
    s = summarise([])
    reg = _registry()
    p = report_payload(s, headlines(s, reg), reg)
    assert p["empty"] is True and p["total_requests"] == 0 and p["providers"] == []
    assert p["days"] == 0 and p["timeline"]["days"] == []
    json.dumps(p)


def test_access_and_routes():
    p, _, _ = _build()
    assert p["access"] == {"OpenRouter": 15, "Anthropic API (direct)": 2}
    assert list(p["access"]) == ["OpenRouter", "Anthropic API (direct)"]
    assert {"tool": "Hermes", "access": "OpenRouter", "provider": "Unknown company", "requests": 5} in p["routes"]
    assert sum(r["requests"] for r in p["routes"]) == p["total_requests"]
    keys = [(-r["requests"], r["tool"], r["access"], r["provider"]) for r in p["routes"]]
    assert keys == sorted(keys)
