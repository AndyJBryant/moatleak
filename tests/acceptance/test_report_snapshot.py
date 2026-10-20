import re
import xml.etree.ElementTree as ET

import pytest
from moatleak.findings import summarise
from moatleak.headlines import headlines
from moatleak.readers import all_readers
from moatleak.registry import Registry
from moatleak.report import render as R
from moatleak.report.payload import report_payload
from moatleak.resolve import resolve

pytestmark = pytest.mark.acceptance

IDS = ["hero-radial", "hero", "hero-wide", "footprint", "timeline",
       *[f"story-{i}" for i in range(1, 8)], "receipt", "passport", "sankey"]


@pytest.fixture(scope="module")
def built(snapshot):
    home, _ = snapshot
    reg = Registry.load()
    rows = [r for rd in all_readers() for r in rd.iter_rows(home)]
    s = summarise([resolve(r, reg) for r in rows])
    p = report_payload(s, headlines(s, reg), reg)
    return p, reg, rows, R.render(p)


def _cards(html):
    out = {}
    for m in re.finditer(r"<svg\b[^>]*class=\"card-svg\".*?</svg>", html, re.S):
        root = ET.fromstring(m.group(0))
        out.setdefault(root.get("data-card"), []).append(root)
    return out


def _text(root):
    return " ".join("".join(t.itertext()) for t in root.iter() if t.tag.endswith("}text") or t.tag == "text")


def _strings(o, key=None):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _strings(v, k)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v, key)
    elif isinstance(o, str):
        yield key, o


def test_card_ids_once(built):
    cards = _cards(built[3])
    assert sorted(cards) == sorted(IDS)
    assert all(len(v) == 1 for v in cards.values())


def test_coverage_note_in_every_card(built):
    p, _, _, html = built
    note = p["coverage_note"]
    for cid, roots in _cards(html).items():
        assert note in re.sub(r"\s+", " ", _text(roots[0])), cid


def test_offline(built):
    p, reg, _, html = built
    allowed = {R.CTA_URL, R.PROJECT_URL, "http://www.w3.org/2000/svg"}
    allowed |= {v for k, v in _strings(p) if k in ("source", "parent_source") and v.startswith("http")}
    allowed |= {s for prov in reg.providers.values() for s in [prov.get("parent_source")] if s}
    import html as H
    for u in re.findall(r"https?://[^\s\"'<>)]+", html):
        assert H.unescape(u) in allowed, u
    assert "<link" not in html and " src=" not in html and "@import" not in html
    assert "url(http" not in html


def test_privacy(built):
    _, _, rows, html = built
    refs = {r.session_ref for r in rows if r.session_ref} | {r.source_ref for r in rows if r.source_ref}
    assert refs
    assert not [x for x in refs if x in html]
    assert "/home/" not in html and "/Users/" not in html


def test_no_invented_parents(built):
    p, reg, _, html = built
    node_labels = {n["label"] for n in p["network"]["nodes"] if n["layer"] == "parent"}
    names = set()
    for prov in reg.providers.values():
        for k in ("parent_display_name", "parent"):
            v = prov.get(k)
            if v and v.lower() != "unknown":
                names.add(v)
    present = {pn for pn in names if any(pn in _text(r[0]) for r in _cards(html).values())}
    for pn in present:
        assert pn in node_labels or any(pn in lab for lab in node_labels) or any(
            prov.get("parent") == pn and prov.get("parent_display_name") in node_labels
            for prov in reg.providers.values()), pn
    # providers whose registry parent is unknown are labelled so, never given a name
    unk = [x for x in p["providers"] if reg.providers.get(x["id"], {}).get("parent") == "unknown"]
    assert unk
    for x in unk:
        assert x["name"] not in node_labels
        assert "parent unknown" in re.sub(r"\s+", " ", html)
        assert any(x["name"] in _text(root[0]) for root in [_cards(html)["receipt"]])
    assert "parent unknown" in _text(_cards(html)["receipt"][0]).lower()
    ledger = re.search(r'<section id="ledger">.*?</section>', html, re.S).group(0)
    import html as H
    cells = {H.unescape(m.group(1)): m.group(2) for m in
             re.finditer(r"<tr><td>(.*?)</td><td>(.*?)</td>", ledger)}
    for x in unk:
        assert cells[x["name"]] == "unknown", x["name"]


def test_footprint_and_withheld(built, snapshot):
    _, gt = snapshot
    cards = _cards(built[3])
    fp = _text(cards["footprint"][0])
    assert "Withheld" in fp or "withheld" in fp
    assert "??" in fp or "Unknown" in fp
    withheld = sum(w["requests"] for w in built[0]["withheld"])
    assert withheld == gt["claude_code_withheld"]
    assert f"{withheld:,}" in _text(cards["story-6"][0])
