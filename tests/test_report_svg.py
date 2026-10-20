"""Unit tests for the shared SVG helpers (synthetic payloads only)."""
import re
import xml.etree.ElementTree as ET

from moatleak.report import svg

NOTE = "Coverage: synthetic note about logs."
PAYLOAD = {"period": ["2026-09-22", "2026-10-07"], "coverage_note": NOTE}


def test_country_key_and_color():
    assert svg.country_key("CN") == "CN" and svg.country_key("US") == "US"
    assert svg.country_key("FR") == "EU" and svg.country_key("DE") == "EU"
    assert svg.country_key("SG") == "OTHER" and svg.country_key("CH") == "OTHER"
    for v in (None, "withheld", "unknown"):
        assert svg.country_key(v) == "GREY"
    assert len(svg.EU_CODES) == 27
    assert svg.color("CN") == "#E5484D" and svg.color(None) == "#8B8D98"
    assert svg.color("FR") == "#F5C518" and svg.color("SG") == "#30A46C"


def test_fill():
    assert svg.fill("CN", "hq_inferred", "c1") == "url(#c1-hatch-CN)"
    assert svg.fill("FR", "hq_inferred", "c1") == "url(#c1-hatch-EU)"
    assert svg.fill("US", "reported", "c1") == "#3E8EF7"
    assert svg.fill("US", "documented", "c1") == "#3E8EF7"
    assert svg.fill(None, "hq_inferred", "c1") == "#8B8D98"
    assert svg.fill("withheld", "withheld", "c1") == "#8B8D98"
    assert svg.fill("unknown", "hq_inferred", "c1") == "#8B8D98"


def test_text_helpers():
    assert svg.esc('a<b>&"c\'') == "a&lt;b&gt;&amp;&quot;c&#x27;"
    assert svg.fmt_int(1174) == "1,174" and svg.fmt_int(5) == "5"
    assert svg.short_date("2026-09-22") == "22 Sep" and svg.short_date("2026-10-07") == "7 Oct"
    assert svg.wrap("aa bb cc dd", 5) == ["aa bb", "cc dd"]
    assert svg.wrap("supercalifragilistic is", 5) == ["supercalifragilistic", "is"]
    assert svg.wrap("", 10) == []
    assert svg.text_width("abcd", 10) == 4 * 10 * 0.56
    assert svg.text_width("abcd", 10, 800) > svg.text_width("abcd", 10)


def test_period_label():
    assert svg.period_label(PAYLOAD) == "22 Sep – 7 Oct 2026"
    assert svg.period_label({"period": ["2025-12-30", "2026-01-02"]}) == "30 Dec 2025 – 2 Jan 2026"
    assert svg.period_label({"period": ["2026-09-22", "2026-09-22"]}) == "22 Sep 2026"
    assert svg.period_label({"period": [None, None]}) == ""


def test_footnote_dedupe():
    assert svg.footnote(PAYLOAD, "Extra.") == "Extra. " + NOTE
    assert svg.footnote(PAYLOAD) == NOTE
    assert svg.footnote(PAYLOAD, "Pre " + NOTE) == "Pre " + NOTE


def test_hatch_defs_scoped():
    d = svg.hatch_defs("abc")
    for k in ("CN", "US", "EU", "OTHER", "GREY"):
        assert f'id="abc-hatch-{k}"' in d


def _card(cid="c1", **kw):
    return svg.card(PAYLOAD, cid, 1200, 630, '<rect x="1" y="1" width="2" height="2"/>', **kw)


def test_card_standalone_svg():
    s = _card(title="A fairly long headline that should wrap onto more than one line of text here")
    root = ET.fromstring(s)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.get("width") == "1200" and root.get("height") == "630"
    assert root.get("viewBox") == "0 0 1200 630" and root.get("data-card") == "c1"
    assert NOTE in s and "moatleak" in s and "22 Sep – 7 Oct 2026" in s
    assert "foreignObject" not in s and "href" not in s
    assert [m for m in re.findall(r"http\S*", s) if m != 'http://www.w3.org/2000/svg"'] == []
    assert "<style>" in s and "Segoe UI" in s


def test_card_dark_and_no_duplicate_ids():
    page = _card("c1") + _card("c2", dark=True)
    ids = re.findall(r'\bid="([^"]+)"', page)
    assert len(ids) == len(set(ids)) and ids
    assert svg.INK in _card("c3", dark=True)


def test_figure():
    f = svg.figure("c1", _card(), caption="Cap <x>")
    assert f.startswith('<figure class="card" id="card-c1" data-w="1200" data-h="630">')
    assert "<figcaption>Cap &lt;x&gt;</figcaption>" in f
    assert "figcaption" not in svg.figure("c1", _card())
