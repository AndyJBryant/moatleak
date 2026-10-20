"""Footprint tiles + legal regimes card/section (synthetic fixtures only)."""
import re
import xml.etree.ElementTree as ET

from moatleak.headlines import pct
from moatleak.report import footprint, svg
from moatleak.report.footprint import footprint_svg, legend_layout, section, tile_counts
from tests.test_report_clusters import _countries, _text_of
from tests.test_report_network import _many
from tests.test_report_payload import _build

NS = "{http://www.w3.org/2000/svg}"


def _p(locs, total=None, **extra):
    """Minimal payload: locs = [(country|None, confidence, requests)] on one provider."""
    n = sum(r for _, _, r in locs)
    p = {"total_requests": total or n, "coverage_note": "Synthetic coverage note.",
         "period": ["2026-09-22", "2026-09-25"], "empty": False,
         "providers": [{"id": "x", "name": "X", "requests": n,
                        "locations": [{"country": c, "confidence": k, "requests": r} for c, k, r in locs]}],
         "country_names": {"CN": "China", "US": "United States", "FR": "France"},
         "headlines": [],
         "counts": {"countries": len({c for c, _, _ in locs if c})},
         "footprint": {"countries": {}, "country_share": {}, "undisclosed_share": 0.0,
                       "confidence": {}, "regimes": []}}
    p.update(extra)
    return p


def _sum(cats):
    return {(c["country"], c["kind"]): c["tiles"] for c in cats}


def test_tiles_snapshot_numbers():
    p = _p([("CN", "hq_inferred", 417), ("US", "hq_inferred", 647), ("US", "documented", 98),
            (None, "withheld", 4), (None, "unknown", 8)])
    cats = tile_counts(p)
    assert sum(c["tiles"] for c in cats) == 200
    assert _sum(cats) == {("CN", "hatched"): 71, ("US", "hatched"): 110, ("US", "solid"): 17,
                          (None, "withheld"): 1, (None, "unknown"): 1}
    assert tile_counts(p) == cats


def test_tiles_category_order():
    p = _p([("CN", "hq_inferred", 417), ("US", "hq_inferred", 647), ("US", "documented", 98),
            (None, "withheld", 4), (None, "unknown", 8)])
    kinds = [(c["country"], c["kind"]) for c in tile_counts(p)]
    assert kinds == [("US", "hatched"), ("US", "solid"), ("CN", "hatched"),
                     (None, "withheld"), (None, "unknown")]


def test_tiles_never_hide_nonzero_and_omit_zero():
    p = _p([("US", "documented", 999_999), ("CN", "hq_inferred", 1)])
    cats = tile_counts(p)
    assert sum(c["tiles"] for c in cats) == 200
    assert _sum(cats)[("CN", "hatched")] == 1
    assert all(c["requests"] > 0 for c in cats)
    assert len(cats) == 2


def test_tiles_single_country_and_empty():
    cats = tile_counts(_p([("FR", "reported", 5)]))
    assert len(cats) == 1 and cats[0]["tiles"] == 200 and cats[0]["kind"] == "solid"
    assert tile_counts(_p([])) == []


def test_tiles_custom_n():
    cats = tile_counts(_p([("US", "reported", 3), ("CN", "reported", 1)]), n=10)
    assert sum(c["tiles"] for c in cats) == 10


def _regimes(p, n=2, shares=None):
    out = []
    for i in range(n):
        out.append({"id": f"R{i}", "name": f"Regime Number {i}", "country": "US",
                    "summary": "Synthetic summary of what this law lets an agency do. " * 2,
                    "source": f"https://example.com/law/{i}", "requests": 10, "share": 0.5 - i * 0.01})
    p["footprint"]["regimes"] = out
    return p


def _full():
    p = _p([("CN", "hq_inferred", 417), ("US", "hq_inferred", 647), ("US", "documented", 98),
            (None, "withheld", 4), (None, "unknown", 8)])
    p["footprint"].update(
        countries={"CN": 417, "US": 745, "withheld": 4, "unknown": 8},
        country_share={"CN": 417 / 1174, "US": 745 / 1174, "withheld": 4 / 1174, "unknown": 8 / 1174},
        undisclosed_share=12 / 1174)
    return _regimes(p, 4)


def _parse(s):
    return ET.fromstring(s)


def _check_svg(p):
    s = footprint_svg(p)
    root = _parse(s)
    assert root.get("width") == "1080" and root.get("height") == "1350"
    assert root.get("data-card") == "footprint"
    assert len([r for r in root.iter(NS + "rect") if r.get("class") == "tile"]) == 200
    assert p["coverage_note"] in _text_of(s)
    assert footprint_svg(p) == s
    for i in re.findall(r'\bid="([^"]+)"', s):
        assert i.startswith("footprint-"), i
    assert s.count("http") == 1  # only the xmlns
    return s


def test_svg_full_card():
    p = _full()
    s = _check_svg(p)
    txt = _text_of(s)
    for r in p["footprint"]["regimes"]:
        assert r["name"] in txt
    assert "Where your prompts went" in txt and "2 countries" in txt and "1% undisclosed" in txt
    assert "?? unknown" in txt and "withheld" in txt and "1 tile = 5.9 prompts" in txt
    assert "all HQ-inferred" in txt and "98 documented" in txt
    assert "0.7%" in txt and "0.3%" in txt
    assert "Regime shares include requests whose location was withheld." in txt


def test_svg_no_pointer_labels_when_absent():
    p = _p([("US", "documented", 10)])
    p["footprint"].update(countries={"US": 10}, country_share={"US": 1.0})
    s = _check_svg(p)
    txt = _text_of(s)
    assert "?? unknown" not in txt and "withheld" not in txt and "undisclosed" not in txt
    assert "1 country" in txt and "1 countries" not in txt


def test_svg_tiny_country_escaped():
    p = _p([("US", "documented", 1000), ("FR", "reported", 1)])
    p["footprint"].update(countries={"US": 1000, "FR": 1},
                          country_share={"US": 0.998, "FR": 0.002})
    s = _check_svg(p)
    assert "&lt;1%" in s


def test_legend_wraps_and_groups_other():
    codes = ["US", "CN", "FR", "SG", "JP", "DE", "IN", "BR", "CA", "KR"]
    p = _countries(codes, [1], reqs=[100 - 7 * i for i in range(10)])
    s = _check_svg(p)
    assert "Other countries" in _text_of(s)
    items = legend_layout(p)
    assert len({it["y"] for it in items}) >= 2
    assert all(it["col"] < 5 for it in items)
    for i, a in enumerate(items):
        assert 56 <= a["x"] and a["x"] + a["w"] <= 1080 - 56
        for line, size, weight in a["texts"]:
            assert svg.text_width(line, size, weight) <= a["w"] - 42 + 1, (line, a["w"])
        for b in items[i + 1:]:
            assert (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                    or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"]), (a, b)


def test_required_synthetic_payloads():
    _check_svg(_build()[0])
    _check_svg(_countries(["US"], [1]))
    _check_svg(_many(40)[0])
    _check_svg(_many(10)[0])
    seven = _countries(["US", "CN", "FR", "SG", "JP", "DE", "IN"], [1, 2, 3])
    s = _check_svg(seven)
    assert "7 countries" in _text_of(s)


def test_many_regimes_capped():
    p = _regimes(_full(), 9)
    s = _check_svg(p)
    txt = _text_of(s)
    assert "more regimes (listed in the report)" in txt
    shown = sum(1 for r in p["footprint"]["regimes"] if r["name"] in txt)
    assert 1 <= shown <= 4
    # no regime-text beyond the footnote area
    root = _parse(s)
    ys = [float(t.get("y") or 0) for t in root.iter(NS + "text")]
    assert max(ys) <= 1350


def test_regimes_footnote_absent_when_shares_equal():
    p = _p([("US", "documented", 10)])
    p["footprint"].update(countries={"US": 10}, country_share={"US": 1.0})
    p["footprint"]["regimes"] = [{"id": "R", "name": "Law", "country": "US", "summary": "S.",
                                  "source": "https://example.com/l", "requests": 10, "share": 1.0}]
    assert "Regime shares include" not in _text_of(_check_svg(p))


def test_section_links_and_empty():
    p = _full()
    out = section(p)
    assert out.startswith('<section id="footprint">') and "<h2>Where your prompts went</h2>" in out
    assert 'id="card-footprint"' in out and "Laws that can compel access" in out
    for r in p["footprint"]["regimes"]:
        assert f'href="{r["source"]}"' in out
        assert r["name"] in out
    assert section({"empty": True}) == ""
    assert footprint.section(_p([])) is not None


def test_tile_grid_is_centred():
    s = footprint_svg(_full())
    xs = [float(m) for m in re.findall(r'class="tile" x="([\d.]+)"', s)]
    assert xs
    assert abs(min(xs) - (1080 - (max(xs) + footprint._TS))) <= 1
