"""Growth timeline card + animated section (synthetic fixtures only)."""
import xml.etree.ElementTree as ET
from datetime import date, timedelta

from moatleak.report import svg, timeline
from moatleak.report.timeline import section, timeline_svg

NS = "{http://www.w3.org/2000/svg}"
NOTE = "Synthetic coverage note."
DAILY = "Daily counts exclude aggregate Hermes DB rows, which carry only a session start time."


def _days(start, n):
    d = date.fromisoformat(start)
    return [(d + timedelta(days=i)).isoformat() for i in range(n)]


def _p(days, provs, growth=True, spread=True, **extra):
    """provs = [(name, country, confidence, requests, first_seen|None)]."""
    matrix = {d: {} for d in days}
    for name, _c, _k, req, fs in provs:
        if fs in matrix:
            matrix[fs][name] = max(req // 3, 1)
            matrix[days[-1]][name] = 1
    heads = []
    new = [n for n, _c, _k, _r, fs in provs if fs and fs > days[0]]
    if growth and new:
        heads.append({"kind": "growth", "text": f"{len(new)} new companies joined your network in 9 days.",
                      "value": len(new), "names": new, "footnote": "Strict growth footnote."})
    if spread:
        heads.append({"kind": "session_spread", "text": "One session touched 3 companies.", "value": 3,
                      "names": [], "footnote": "Spread footnote."})
    p = {"total_requests": 100, "coverage_note": NOTE, "empty": False,
         "period": [days[0], days[-1]], "counts": {"companies": len(provs)},
         "providers": [{"id": n, "name": n, "requests": r, "country": c, "first_seen": fs,
                        "locations": [{"country": c, "confidence": k, "requests": r}]}
                       for n, c, k, r, fs in provs]
         + [{"id": "unknown", "name": "Unknown company", "requests": 8, "country": None, "first_seen": None,
             "locations": [{"country": None, "confidence": "unknown", "requests": 8}]}],
         "headlines": heads, "withheld": [],
         "timeline": {"days": days, "daily_matrix": matrix,
                      "first_seen": {n: fs for n, _c, _k, _r, fs in provs if fs},
                      "data_start": days[0], "coverage_note": NOTE, "footnote": DAILY}}
    p.update(extra)
    return p


def _snap():
    days = _days("2026-09-22", 16)
    provs = [("Alpha", "US", "documented", 300, "2026-08-15"),
             ("Beta", "CN", "hq_inferred", 90, "2026-09-22"),
             ("Gamma", "CN", "hq_inferred", 80, "2026-09-22"),
             ("Delta", "US", "hq_inferred", 70, "2026-09-23"),
             ("Epsilon", "FR", "hq_inferred", 60, "2026-09-23"),
             ("Zeta", "US", "hq_inferred", 50, "2026-09-24"),
             ("Eta", "US", "hq_inferred", 40, "2026-09-24"),
             ("Theta", "US", "hq_inferred", 30, "2026-09-29"),
             ("Iota", "SG", "hq_inferred", 20, "2026-09-30"),
             ("Kappa", "US", "hq_inferred", 10, "2026-10-01")]
    return _p(days, provs)


def _root(p):
    return ET.fromstring(timeline_svg(p))


def _texts(root):
    return [" ".join("".join(t.itertext()).split()) for t in root.iter(NS + "text")]


def _cls(root, c):
    return [e for e in root.iter() if c in (e.get("class") or "").split()]


def test_snapshot_shape():
    p = _snap()
    s = timeline_svg(p)
    root = ET.fromstring(s)
    assert root.get("data-card") == "timeline" and root.get("width") == "1080" and root.get("height") == "1350"
    rows = _cls(root, "tl-row")
    assert len(rows) == 10
    assert [r.get("style") for r in rows] == [f"--i:{i}" for i in range(10)]
    assert len(_cls(root, "tl-day")) == 16
    first = _cls(root, "tl-first")
    assert len(first) == 10 - 1  # every provider except the early one has an outline
    assert len([e for e in first if e.get("stroke-dasharray")]) == 2
    texts = _texts(root)
    assert "first seen 15 Aug" in texts
    assert "7 new companies joined your network in 9 days." in " ".join(texts)
    assert any(NOTE in t for t in " ".join(texts).split("\n")) or NOTE in " ".join(texts)
    assert DAILY in " ".join(texts)
    assert "Unknown company" not in " ".join(texts)
    ids = [e.get("id") for e in root.iter() if e.get("id")]
    assert ids and all(i.startswith("timeline-") for i in ids)
    assert "@keyframes" not in s and "foreignObject" not in s


def test_big_number_and_days():
    assert "7 new companies in 9 days" in _texts(_root(_snap()))


def test_row_order_and_early_arrow():
    root = _root(_snap())
    names = [[t for t in _texts(r)][0] for r in _cls(root, "tl-row")]
    assert names == ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta", "Iota", "Kappa"]
    assert len(_cls(root, "tl-arrow")) == 1
    assert any("no per-call provider data before 22 Sep" in " ".join(_texts(root)).replace("\n", " ")
               or "no per-call provider data" in t for t in _texts(root))


def test_key_lines():
    t = " ".join(_texts(_root(_snap())))
    assert "Darker cell = more requests that day" in t
    assert "Dashed outline = already serving you when per-call data starts (22 Sep)" in t
    p = _p(_days("2026-09-22", 5), [("A", "US", "documented", 9, "2026-09-23")])
    assert "Dashed outline" not in " ".join(_texts(_root(p)))


def test_month_labels_generic():
    days = _days("2026-01-28", 35)  # 28 Jan .. 3 Mar
    p = _p(days, [("A", "US", "documented", 9, "2026-01-30"), ("B", "CN", "hq_inferred", 5, "2026-02-10")])
    t = _texts(_root(p))
    heads = [x for x in t if x[:3] in ("Jan", "Feb", "Mar") and len(x) <= 8]
    assert [h[:3] for h in heads] == ["Jan", "Feb", "Mar"]


def test_ninety_days_weekly():
    days = _days("2026-07-01", 90)
    p = _p(days, [("A", "US", "documented", 9, "2026-07-05"), ("B", "CN", "hq_inferred", 5, "2026-08-10")])
    root = _root(p)
    assert len(_cls(root, "tl-day")) < 20
    assert any(x.startswith("w/c ") for x in _texts(root))


def test_many_providers_cap_rows():
    days = _days("2026-09-22", 16)
    provs = [(f"P{i:02d}", "US", "hq_inferred", 100 - i, days[i % 16]) for i in range(40)]
    root = _root(_p(days, provs))
    rows = _cls(root, "tl-row")
    assert 0 < len(rows) < 40
    k = 40 - len(rows)
    assert f"+{k} more companies (see the table below)" in _texts(root)
    for r in rows:
        hs = [float(e.get("height")) for e in r.iter(NS + "rect")]
        assert max(hs) <= 24
    _inside(root)


def _inside(root):
    for t in root.iter(NS + "text"):
        if "rotate" in (t.get("transform") or ""):
            continue
        x, y = float(t.get("x", 0)), float(t.get("y", 0))
        txt = "".join(t.itertext())
        w = svg.text_width(txt, float(t.get("font-size", 16)), int(t.get("font-weight", 600)))
        a = t.get("text-anchor", "start")
        lo, hi = (x, x + w) if a == "start" else (x - w, x) if a == "end" else (x - w / 2, x + w / 2)
        if t.get("font-size") != "54" and not t.get("data-card"):
            assert lo >= 0 and hi <= 1080 + 1, (txt, lo, hi)
        assert y <= 1350
    for r in root.iter(NS + "rect"):
        if r.get("height") and r.get("y"):
            assert float(r.get("y")) + float(r.get("height")) <= 1350


def test_no_growth_headline():
    p = _p(_days("2026-09-22", 6), [("A", "US", "documented", 9, "2026-09-22")], growth=False)
    t = " ".join(_texts(_root(p)))
    assert "new companies" not in t and "companies served you" in t


def test_missing_spread_box_omitted():
    p = _p(_days("2026-09-22", 6), [("A", "US", "documented", 9, "2026-09-23")], spread=False)
    t = " ".join(_texts(_root(p)))
    assert "One session" not in t and "Spread footnote" not in t


def test_edge_payloads_parse_and_fit():
    days = _days("2026-09-22", 16)
    one = _p(days, [("Solo", "US", "documented", 5, "2026-09-23")])
    seven = _p(days, [(f"C{i}", c, "hq_inferred", 10 + i, days[i]) for i, c in
                      enumerate(["CN", "US", "FR", "SG", "JP", "IN", "BR"])])
    tiny = _p(days, [("Tiny", "CN", "hq_inferred", 1, "2026-09-23"), ("Big", "US", "documented", 9999, "2026-09-24")])
    esc = _p(days, [("A<&>", "CN", "hq_inferred", 5, "2026-09-23")])
    for p in (one, seven, tiny, esc):
        _inside(_root(p))
    assert "A&lt;&amp;&gt;" in timeline_svg(esc)


def test_section_animation_outside_svg():
    p = _snap()
    h = section(p)
    assert h.startswith('<section id="timeline"><h2>Your network keeps growing</h2>')
    assert "prefers-reduced-motion" in h and "@keyframes tlin" in h and "#card-timeline .tl-row" in h
    assert 'id="card-timeline"' in h and "<svg" in h and h.endswith("</section>")
    assert "@keyframes" not in timeline_svg(p)
    assert section({"empty": True, "total_requests": 0}) == ""


def test_no_empty_band_under_big_number():
    s = timeline_svg(_snap())
    root = ET.fromstring(s)
    month = [float(t.get("y")) for t in root.iter(NS + "text") if (t.text or "").startswith("Sep")]
    assert month and min(month) - 240 <= 60  # big-number baseline is y=240


def test_solo_view_disables_animation():
    from moatleak.report.render import render
    from tests.test_report_payload import _build
    html = render(_build()[0])
    assert "classList.add('solo')" in html or 'classList.add("solo")' in html
    assert ".solo *{animation:none!important}" in html
