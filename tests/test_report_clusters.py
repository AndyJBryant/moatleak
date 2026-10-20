"""Country-cluster share cards: layout + SVG (synthetic fixtures only)."""
import re
import xml.etree.ElementTree as ET

from moatleak.report import hero
from moatleak.report.clusters import clusters_layout, clusters_svg
from moatleak.report.network import radial_svg
from tests.test_report_network import _many, _overlap
from tests.test_report_payload import _build

SIZES = ((1080, 1350, False), (1200, 630, True))


def _text_of(svg):
    root = ET.fromstring(svg)
    return " ".join("".join(t.itertext()) for t in root.iter("{http://www.w3.org/2000/svg}text"))


def _gap(lab, n):
    nx = min(max(n["x"], lab["x"]), lab["x"] + lab["w"])
    ny = min(max(n["y"], lab["y"]), lab["y"] + lab["h"])
    return ((nx - n["x"]) ** 2 + (ny - n["y"]) ** 2) ** 0.5 - n["r"]


def _check(payload, w, h, wide):
    svg = clusters_svg(payload, wide=wide)
    root = ET.fromstring(svg)
    assert root.get("width") == str(w) and root.get("height") == str(h)
    assert payload["coverage_note"] in _text_of(svg)
    assert clusters_svg(payload, wide=wide) == svg
    lay = clusters_layout(payload, w, h)
    labs = lay["labels"]
    nd = {n["id"]: n for n in lay["nodes"]}
    circles = [n for n in lay["nodes"] if n["id"].startswith("country:")]
    for i, a in enumerate(labs):
        assert (40 if not wide else 0) <= a["x"] and a["x"] + a["w"] <= (w - 40 if not wide else w), a
        n = nd[a["id"]]  # label clears the node's dashed/solid halo (r + 8)
        if a["id"].startswith("provider:"):
            assert _gap(a, n) >= 8 - 0.5, (a["text"], _gap(a, n))
        assert 40 <= a["y"] and a["y"] + a["h"] <= (h - 100 if not wide else h - 10), a
        assert _gap(a, nd[a["id"]]) <= 40, (a["text"], _gap(a, nd[a["id"]]))
        for b in labs[i + 1:]:
            assert not _overlap(a, b), (a["text"], b["text"])
        for c in circles:  # labels never cross a country circle
            nx = min(max(c["x"], a["x"]), a["x"] + a["w"])
            ny = min(max(c["y"], a["y"]), a["y"] + a["h"])
            assert ((nx - c["x"]) ** 2 + (ny - c["y"]) ** 2) ** 0.5 >= c["r"], (a["text"], c["id"])
    return svg, lay


def test_single_provider_both_sizes():
    p, _, _ = _build()
    one = dict(p, providers=p["providers"][:1])
    for w, h, wide in SIZES:
        _check(one, w, h, wide)


def test_ten_and_forty_providers_both_sizes():
    for n in (1, 10, 40):
        p, _ = _many(n, unknown_parents={2, 5} if n > 5 else ())
        for w, h, wide in SIZES:
            _check(p, w, h, wide)


def test_unknown_parent_and_same_name_and_different_parent():
    p, _ = _many(10, unknown_parents={2, 5})
    tall = clusters_svg(p)
    assert tall.count("parent unknown") == 2 and "Prov02 Corp" not in tall
    assert "parent unknown" not in clusters_svg(p, wide=True)
    q, _, _ = _build()
    lab = {x["text"]: x for x in clusters_layout(q, 1080, 1350)["labels"]}
    assert "Group One" in _text_of(clusters_svg(q))
    assert lab["Alpha"]["sub"] is None
    assert any(x["sub"] == "Group One" for x in lab.values())


def test_plus_k_more():
    p, _ = _many(40)
    per: dict = {}
    for pr in p["providers"]:
        per[pr["country"]] = per.get(pr["country"], 0) + 1
    for wide, cap in ((False, 8), (True, 6)):
        txt = _text_of(clusters_svg(p, wide=wide))
        for c, n in per.items():
            if n > cap:
                assert f"+{n - cap} more" in txt, (c, n, wide)
    small, _ = _many(5)
    assert "more" not in _text_of(clusters_svg(small))


def test_unknown_cluster_and_percentages():
    p, _ = _many(10)
    txt = _text_of(clusters_svg(p))
    assert "??" in txt and "Unknown company" in txt and "%" in txt


def test_ids_scoped():
    p, _ = _many(10)
    for wide, pre in ((False, "hero-"), (True, "hero-wide-")):
        ids = re.findall(r'\bid=\"([^\"]+)\"', clusters_svg(p, wide=wide))
        assert ids and all(i.startswith(pre) for i in ids)
    assert 'data-card="hero"' in clusters_svg(p) and 'data-card="hero-wide"' in clusters_svg(p, wide=True)


def test_section_has_share_cards_and_radial_unchanged():
    p, _, _ = _build()
    out = hero.section(p)
    assert "Share cards" in out and 'id="card-hero"' in out and 'id="card-hero-wide"' in out
    assert out.index("card-hero-radial") < out.index("Share cards") < out.index('id="card-hero"')
    assert radial_svg(p) == radial_svg(p)


def test_unknown_cluster_shows_percentage_both_sizes():
    p, _ = _many(10)
    assert p["footprint"]["undisclosed_share"] > 0
    from moatleak.headlines import pct
    want = f"{pct(p['footprint']['undisclosed_share'])}%"
    for wide in (False, True):
        root = ET.fromstring(clusters_svg(p, wide=wide))
        ns = "{http://www.w3.org/2000/svg}text"
        texts = ["".join(t.itertext()) for t in root.iter(ns)]
        assert want in texts and "??" in texts
        small = [float(t.get("font-size")) for t in root.iter(ns)
                 if "".join(t.itertext()) in ("unknown", "/ withheld")]
        assert small and min(small) >= 13


def test_you_edges_avoid_foreign_provider_nodes():
    for p in (_many(10, unknown_parents={2, 5})[0], _many(40)[0], _build()[0]):
        owner = {f"provider:{q['id']}": f"country:{q['country'] or 'unknown'}" for q in p["providers"]}
        lay = clusters_layout(p, 1080, 1350)
        assert lay["you_edges"]
        for e in lay["you_edges"]:
            assert len(e["points"]) >= 30
            for n in lay["nodes"]:
                if owner.get(n["id"], e["id"]) == e["id"]:
                    continue
                for (x, y) in e["points"]:
                    assert ((x - n["x"]) ** 2 + (y - n["y"]) ** 2) ** 0.5 > n["r"], (e["id"], n["id"])


def _countries(codes, per, reqs=None):
    from moatleak.findings import summarise
    from moatleak.headlines import headlines
    from moatleak.registry import Registry
    from moatleak.report.payload import report_payload
    from tests.test_findings import mk
    from tests.test_report_payload import _prov
    provs, rows = {}, []
    for ci, cc in enumerate(codes):
        for j in range(per[ci % len(per)]):
            pid = f"c{ci}p{j}"
            name = f"Co{ci}x{j}"
            provs[pid] = _prov(pid, name, f"{pid}-co", name)
            rows.append(mk(name, "2026-09-22", pid=pid, parent=f"{name} Corp", parent_id=f"{pid}-co",
                           parent_display=name, country=cc, requests=(reqs or [50 - 3 * ci])[ci % len(reqs or [0])]))
    rows.append(mk("Unknown", "2026-09-25", country=None, requests=4))
    s = summarise(rows)
    reg = Registry(provs, {}, {}, "t")
    return report_payload(s, headlines(s, reg), reg)


def test_tiny_share_is_escaped():
    p = _countries(["US"], [1], reqs=[1000])
    p["footprint"]["country_share"]["US"] = 0.002
    for w, h, wide in SIZES:
        svg = clusters_svg(p, wide=wide)
        ET.fromstring(svg)
        assert "&lt;1%" in svg


def test_many_countries_merge_and_fit():
    five = _countries(["US", "CN", "FR", "SG", "JP"], [1, 2, 3])
    seven = _countries(["US", "CN", "FR", "SG", "JP", "DE", "IN"], [1, 2, 3])
    for p, other in ((five, True), (seven, True)):
        for w, h, wide in SIZES:
            svg, lay = _check(p, w, h, wide)
            assert lay["fail"] == 0, (w, lay["fail"])
            cl = [n for n in lay["nodes"] if n["id"].startswith("country:")]
            assert len(cl) <= 6  # 4 countries + merged + ??
            assert ("Other countries" in _text_of(svg)) is other
            for n in lay["nodes"]:
                assert n["r"] <= n["x"] <= w - n["r"] and n["r"] <= n["y"] <= h - n["r"]
    tall = clusters_svg(seven)
    assert "Japan" in tall or "India" in tall or "Germany" in tall
