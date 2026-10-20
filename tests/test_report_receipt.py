"""Receipt v2 + prompt passport cards (synthetic fixtures only)."""
import math
import re
import xml.etree.ElementTree as ET

from moatleak.headlines import pct
from moatleak.report import receipt, svg
from moatleak.report.receipt import passport_layout, passport_svg, receipt_svg, section
from tests.test_report_clusters import _countries
from tests.test_report_network import _many

NS = "{http://www.w3.org/2000/svg}"


def _texts(s, cls):
    root = ET.fromstring(s)
    return ["".join(t.itertext()) for t in root.iter(NS + "text") if cls in (t.get("class") or "").split()]


def _snap():
    p, _ = _many(11, unknown_parents=(1,))
    p["providers"][0]["locations"].append({"country": None, "confidence": "withheld", "requests": 4})
    return p


def _check_card(s, card_id):
    root = ET.fromstring(s)
    assert root.get("data-card") == card_id
    assert s.count("http") == s.count("http://www.w3.org/2000/svg") == 1
    for el in root.iter():
        i = el.get("id")
        if i:
            assert i.startswith(card_id + "-"), i
    assert "foreignObject" not in s


def test_receipt_rows_and_parents():
    p = _snap()
    s = receipt_svg(p)
    _check_card(s, "receipt")
    names, subs = _texts(s, "rn"), _texts(s, "rs")
    assert len(names) == 12 and names[-1] == "??"
    assert names[:-1] == [x["name"] for x in p["providers"][:-1]]
    for prov, sub in zip(p["providers"], [x for x in subs if not x.startswith("of which")]):
        if prov["id"] == "unknown":
            assert sub == "—"
        elif prov["parent_id"] is None:
            assert sub == "parent unknown"
        else:
            assert sub == prov["parent"]
    assert sum(x == "parent unknown" for x in subs) == 1
    assert "independent" not in s and "Corp" not in s
    assert subs.count("of which location withheld: 4") == 1


def test_receipt_total_and_tools():
    p = _snap()
    s = receipt_svg(p)
    want = (f"Companies that processed your prompts: {p['counts']['companies']} · "
            f"Countries: {p['counts']['countries']} · Undisclosed: {pct(p['footprint']['undisclosed_share'])}%")
    assert " ".join(_texts(s, "total")) == want
    tools = " ".join(_texts(s, "tools"))
    access = " ".join(_texts(s, "access"))
    assert tools.startswith("Tools: ") and "OpenRouter" not in tools
    assert all(f"{k} {svg.fmt_int(v)}" in tools for k, v in p["tools"].items())
    assert access.startswith("Access: ") and "via OpenRouter" not in s
    assert all(f"{k} {svg.fmt_int(v)}" in access for k, v in p["access"].items())
    p["access"] = {}
    assert not _texts(receipt_svg(p), "access")
    assert p["coverage_note"] in s and "HQ = location inferred from HQ" in s
    assert receipt_svg(p) == receipt_svg(p)


def test_receipt_many_providers_collapses():
    p, _ = _many(30)
    s = receipt_svg(p)
    names = _texts(s, "rn")
    assert len(names) == 12 and names[-1] == "+20 more companies"
    rest = sum(x["requests"] for x in p["providers"][11:])
    assert svg.fmt_int(rest) in _texts(s, "rc")
    ET.fromstring(receipt_svg(_many(1)[0]))


def test_receipt_basis_tags():
    p = _snap()
    s = receipt_svg(p)
    assert set(_texts(s, "basis")) <= {"HQ", "doc", "rep", "??"}
    assert len(_texts(s, "basis")) == 12


def test_cards_escape_tiny_share_and_parse():
    p = _countries(["US"], [1], reqs=[1000])
    p["footprint"]["country_share"]["US"] = 0.002
    p["footprint"]["undisclosed_share"] = 0.002
    for f in (receipt_svg, passport_svg):
        ET.fromstring(f(p))
        assert "&lt;1" in f(p)


def _overlap_free(p):
    lay = passport_layout(p)
    for i, a in enumerate(lay):
        assert 56 <= a["x"] - a["r"] and a["x"] + a["r"] <= 1024 and a["y"] - a["r"] >= 0 and a["y"] + a["r"] <= 1350
        for b in lay[i + 1:]:
            assert math.hypot(a["x"] - b["x"], a["y"] - b["y"]) >= a["r"] + b["r"], (a, b)
    return lay


def test_passport_stamps():
    p = _countries(["US", "CN", "FR", "DE", "JP", "SG", "BR"], [1], reqs=[50])
    p["footprint"]["undisclosed_share"] = 0.05
    lay = _overlap_free(p)
    reals = [x for x in lay if x["kind"] == "country"]
    assert len(reals) == 7 and [x["kind"] for x in lay].count("undisclosed") == 1
    s = passport_svg(p)
    _check_card(s, "passport")
    assert len(_texts(s, "stamp-name")) == 7 and len(_texts(s, "stamp-undis")) == 1
    assert "PROMPT PASSPORT" in " ".join(_texts(s, "ptitle"))
    assert p["coverage_note"] in s and passport_svg(p) == s
    assert all(80 <= x["r"] <= 220 for x in lay)
    p["footprint"]["undisclosed_share"] = 0
    assert "stamp-undis" not in passport_svg(p)


def test_passport_sizes_and_edge_cases():
    p = _countries(["US", "CN"], [1], reqs=[90, 10])
    r = {x["country"]: x["r"] for x in passport_layout(p)}
    assert r["US"] > r["CN"] >= 80
    for q in (_many(1)[0], _many(40)[0], _countries(["US", "CN", "FR", "DE", "JP", "SG", "BR", "IN", "CA", "AU", "MX", "KR"], [1], reqs=[30])):
        _overlap_free(q)
        ET.fromstring(passport_svg(q))


def test_section():
    p = _snap()
    h = section(p)
    assert h.startswith('<section id="receipt"><h2>Your receipt</h2>') and h.endswith("</section>")
    assert 'id="card-receipt"' in h and 'id="card-passport"' in h
    assert section({"empty": True, "total_requests": 0}) == ""


def test_receipt_text_is_monospace():
    s = receipt_svg(_snap())
    style = " ".join(e.text or "" for e in ET.fromstring(s).iter(NS + "style"))
    assert re.search(r"svg \.rcpt text\s*\{[^}]*font-family:ui-monospace", style)


def test_passport_centred_and_legible():
    p = _countries(["US", "CN", "FR"], [1], reqs=[50, 30, 20])
    p["footprint"]["undisclosed_share"] = 0.01
    for q in (p, _countries(["US"], [1], reqs=[10])):
        lay = passport_layout(q)
        cx = (min(a["x"] - a["r"] for a in lay) + max(a["x"] + a["r"] for a in lay)) / 2
        cy = (min(a["y"] - a["r"] for a in lay) + max(a["y"] + a["r"] for a in lay)) / 2
        assert abs(cx - 540) <= 60 and abs(cy - 685) <= 60, (cx, cy)
        _overlap_free(q)
    s = passport_svg(p)
    small = [t for t in ET.fromstring(s).iter(NS + "text") if "undisclosed" in "".join(t.itertext())]
    assert small and all(float(t.get("font-size")) >= 14 for t in small)


def test_basis_note_once_per_card():
    p = _snap()
    note = receipt._basis_note(p)
    assert note
    for s in (receipt_svg(p), passport_svg(p)):
        flat = " ".join(" ".join(ET.fromstring(s).itertext()).split())
        assert flat.count(note) == 1


def test_stamp_names_fit_rings():
    for name in ("UNITED STATES", "UNITED ARAB EMIRATES"):
        for r in (80, 150, 220):
            assert svg.text_width(name, receipt._name_size(name, r), 800) <= 1.3 * r


def test_receipt_long_provider_name_truncated():
    p = _snap()
    long = "A Very Long Provider Company Name Incorporated"
    p["providers"][2]["name"] = long
    names = _texts(receipt_svg(p), "rn")
    assert long not in names and all(len(n) <= 26 for n in names)
    assert names[2] == long[:25] + "…"


def test_receipt_access_label_escaped():
    p = _snap()
    p["access"] = {"x<y>.example.com": 3}
    s = receipt_svg(p)
    ET.fromstring(s)
    assert "x&lt;y&gt;.example.com" in s and "x<y>" not in s
