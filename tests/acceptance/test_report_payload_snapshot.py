import json

import pytest
from moatleak.findings import summarise
from moatleak.headlines import headlines
from moatleak.readers import all_readers
from moatleak.registry import Registry
from moatleak.report.payload import report_payload
from moatleak.resolve import resolve

pytestmark = pytest.mark.acceptance


@pytest.fixture(scope="module")
def built(snapshot):
    home, _ = snapshot
    reg = Registry.load()
    rows = [r for rd in all_readers() for r in rd.iter_rows(home)]
    s = summarise([resolve(r, reg) for r in rows])
    return report_payload(s, headlines(s, reg), reg), reg, rows


def test_counts_and_shape(built):
    p, _, _ = built
    assert p["counts"]["companies"] == 10 and p["counts"]["parent_groups"] == 8
    assert p["counts"]["countries"] == 2
    assert p["total_requests"] == 1174 and p["days"] == 16
    assert len(p["providers"]) == 11
    assert p["providers"][-1]["id"] == "unknown" and p["providers"][-1]["requests"] == 8
    assert not p["empty"]


def test_parent_nodes(built):
    p, reg, _ = built
    parents = [n for n in p["network"]["nodes"] if n["layer"] == "parent"]
    assert len(parents) == 8
    labels = {n["label"] for n in parents}
    assert "Relace" not in labels and "GMI Cloud" not in labels
    nodes = {n["id"] for n in p["network"]["nodes"]}
    assert all(e["source"] in nodes and e["target"] in nodes for e in p["network"]["edges"])
    for n in parents:
        pid = n["id"].split(":", 1)[1]
        urls = {src["url"] for prov in reg.providers.values() if prov.get("parent_id") == pid
                for src in prov.get("sources", []) if src.get("claim") == "parent"}
        assert n["source"] in urls


def test_privacy(built):
    p, _, rows = built
    text = json.dumps(p)
    assert len(text) < 300_000
    assert "/home/" not in text and "/Users/" not in text
    refs = {r.session_ref for r in rows if r.session_ref} | {r.source_ref for r in rows if r.source_ref}
    assert refs
    assert not [ref for ref in refs if ref in text]
    stack = [p]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            assert not {"session_ref", "source_ref", "providers_per_session"} & set(o)
            stack += o.values()
        elif isinstance(o, list):
            stack += o


def test_access_and_routes(built):
    p, _, _ = built
    assert p["access"] == {"OpenRouter": 853, "Anthropic API (direct)": 321}
    assert sum(r["requests"] for r in p["routes"]) == p["total_requests"] == 1174
    got = {(r["tool"], r["access"], r["provider"], r["requests"]) for r in p["routes"]}
    assert ("Claude Code", "Anthropic API (direct)", "Anthropic", 4) in got
    assert ("Hermes", "OpenRouter", "Unknown company", 8) in got
