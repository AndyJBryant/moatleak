"""render() skeleton tests: order, offline, payload embedding, ledger, empty state."""
import json
import re

from moatleak.report import render as render_mod
from moatleak.report import sections
from moatleak.report.render import CTA_URL, PROJECT_URL, render
from tests.test_report_payload import _build, _rows
from tests.test_findings import mk

ORDER = ["hero", "footprint", "timeline", "story", "receipt", "sankey"]


def _html(payload=None):
    return render(payload or _build()[0])


def _pos(h, sid):
    m = re.search(rf'<(?:section|header)[^>]*\bid="{sid}"', h)
    assert m, sid
    return m.start()


def test_doctype_and_section_order():
    h = _html()
    assert h.lower().startswith("<!doctype html>")
    ids = ["header"] + ORDER + ["ledger", "methodology", "cta"]
    pos = [_pos(h, i) for i in ids]
    assert pos == sorted(pos)


def test_no_pending_sections():
    h = _html()
    assert 'class="pending"' not in h
    assert '<section id="hero"><h2>Your inference network</h2>' in h


def test_offline():
    p = _build()[0]
    h = render(p)
    allowed = {CTA_URL, PROJECT_URL, "http://www.w3.org/2000/svg"}
    allowed |= {r["source"] for r in p["footprint"]["regimes"] if r["source"]}
    allowed |= {x["parent_source"] for x in p["providers"] if x["parent_source"]}
    for u in re.findall(r"https?://[^\s\"'<>)]+", h):
        assert u in allowed, u
    for bad in ("<link", " src=", "@import", "url(http"):
        assert bad not in h
    assert CTA_URL == "https://horizenlabs.io/?ref=moatleak"
    assert PROJECT_URL == "https://moatleak.ai/"


def test_payload_embedded_once_and_roundtrips():
    p = _build()[0]
    h = render(p)
    ms = re.findall(r'<script type="application/json" id="moatleak-payload">(.*?)</script>', h, re.S)
    assert len(ms) == 1
    assert json.loads(ms[0].replace("<\\/", "</")) == p
    assert 'id="moatleak-export"' in h


def test_payload_breakout_and_escaping():
    p = _build()[0]
    p["providers"][0]["name"] = "Evil</script><b>x"
    p["headlines"][0]["text"] = "<img src=x onerror=1>"
    h = render(p)
    assert "</script><b>" not in h
    visible = re.sub(r'<script type="application/json".*?</script>', "", h, flags=re.S)
    assert "<img src=x" not in visible
    assert "Evil&lt;/script&gt;&lt;b&gt;x" in h


def test_title():
    h = _html()
    assert "<title>moatleak · your AI inference network · 22 Sep – 25 Sep 2026</title>" in h


def test_header_earlier_line():
    h = _html()
    assert "Your AI inference network" in h
    assert "Before 22 Sep: 40 earlier requests since 1 Aug 2026; " in h
    p = _build()[0]
    p["earlier"] = {"requests": 0, "unattributed_requests": 0, "first": None, "last": None}
    assert "earlier requests" not in render(p)


def test_ledger_rows():
    p = _build()[0]
    h = render(p)
    rows = {re.sub(r"<[^>]+>", " ", r) for r in re.findall(r"<tr>.*?</tr>", h, re.S)}
    ledger = [r for r in rows if "Delta" in r]
    assert len(ledger) == 1 and "unknown" in ledger[0] and "Delta Corp" not in ledger[0]
    unk = [r for r in rows if "??" in r]
    assert len(unk) == 1
    alpha = [r for r in rows if "Alpha" in r][0]
    assert "reported by provider 3" in alpha and "withheld 2" in alpha
    assert 'href="https://example.com/alpha/parent"' in h
    assert "SECRET" not in h


def test_methodology():
    h = _html()
    assert "How this was measured" in h
    assert "Network clues such as IP geolocation are not location evidence." in h
    assert "No card claims a datacenter." in h
    assert "CLOUD Act" in h and "https://example.com/cloud" in h
    assert "test-1" in h and "Synthetic summary." in h
    assert "HQ-inferred" in h


def test_cta_only_link():
    h = _html()
    assert f'<a href="{CTA_URL}"' in h and "Deploy Sovereign AI at your company →" in h
    assert "interim link until the project site" in open(render_mod.__file__).read()


def test_empty_payload():
    from moatleak.findings import summarise
    from moatleak.headlines import headlines
    from moatleak.report.payload import report_payload
    from tests.test_report_payload import _registry
    s = summarise([])
    reg = _registry()
    p = report_payload(s, headlines(s, reg), reg)
    assert p["empty"]
    h = render(p)
    assert "No AI usage with provider data was found in the scanned logs." in h
    assert 'id="methodology"' in h and 'id="cta"' in h
    for sid in ORDER + ["ledger"]:
        assert f'id="{sid}"' not in h


def test_template_placeholders():
    import importlib.resources as r
    t = (r.files("moatleak.report") / "template.html").read_text(encoding="utf-8")
    assert sorted(set(re.findall(r"\$(\w+)", t))) == ["body", "payload", "title"]


def test_sections_importable():
    assert callable(sections.header) and callable(sections.ledger)
