"""Sankey card/section (synthetic fixtures only)."""
import xml.etree.ElementTree as ET

from moatleak.findings import summarise
from moatleak.headlines import headlines
from moatleak.registry import Registry
from moatleak.report import sankey, svg
from moatleak.report.payload import report_payload
from tests.test_findings import mk
from tests.test_report_clusters import _countries, _text_of
from tests.test_report_network import _many
from tests.test_report_payload import _build, _prov


def _snapshot_like():
    """Direct + router paths, known and unknown parents, unknown company, withheld country."""
    provs = {"a": _prov("a", "Alpha", "a-co", "Alpha Group"), "b": _prov("b", "Beta", "b-co", "Beta"),
             "u": _prov("u", "Mystery", None, None, source=False)}
    rows = [mk("Alpha", "2026-09-25", pid="a", parent="Alpha Group Ltd", parent_id="a-co",
               parent_display="Alpha Group", country="US", requests=50, tool="Hermes", route="direct"),
            mk("Beta", "2026-09-25", pid="b", parent="Beta Ltd", parent_id="b-co",
               parent_display="Beta", country="CN", requests=30, tool="Hermes", route="router"),
            mk("Beta", "2026-09-25", pid="b", parent="Beta Ltd", parent_id="b-co",
               parent_display="Beta", country="CN", requests=5, tool="Claude Code", route="router"),
            mk("Mystery", "2026-09-25", pid="u", parent=None, parent_id=None, parent_display=None, country="US", requests=20, tool="Claude Code",
               route="direct"),
            mk("Alpha", "2026-09-25", pid="a", parent="Alpha Group Ltd", parent_id="a-co",
               parent_display="Alpha Group", country=None, conf="withheld", requests=4, tool="Hermes", route="direct"),
            mk("Unknown", "2026-09-25", country=None, requests=7, tool="Hermes")]
    s = summarise(rows)
    reg = Registry(provs, {}, {}, "t")
    return report_payload(s, headlines(s, reg), reg)


def _flows(lay):
    return [(f["source"], f["target"], f["requests"]) for f in lay["flows"]]


def _check_labels(p):
    lay = sankey.sankey_layout(p)
    labs = lay["labels"]
    for i, a in enumerate(labs):
        assert 0 <= a["x"] and a["x"] + a["w"] <= 1080 and a["y"] >= 0
        for b in labs[i + 1:]:
            assert (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                    or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"]), (a["text"], b["text"])
    return lay


def test_conservation():
    p = _snapshot_like()
    lay = sankey.sankey_layout(p)
    fl, nd = _flows(lay), {n["id"]: n for n in lay["nodes"]}
    for n in lay["nodes"]:
        if n["col"] in (1, 2):
            ins = sum(r for a, b, r in fl if b == n["id"])
            outs = sum(r for a, b, r in fl if a == n["id"])
            assert ins == outs, n["label"]
        if n["col"] == 2:
            req = next(x["requests"] for x in p["providers"] if f"provider:{x['id']}" == n["id"])
            assert n["requests"] == req
    assert sum(r for a, b, r in fl if nd[a]["col"] == 0) == p["total_requests"]
    assert sum(r for a, b, r in fl if nd[b]["col"] == 4) == p["total_requests"]


def test_column_membership_and_vocabulary():
    for p in (_snapshot_like(), _many(40, unknown_parents={2, 5})[0]):
        lay = sankey.sankey_layout(p)
        for n in lay["nodes"]:
            kind = n["id"].split(":", 1)[0]
            assert n["col"] == {"tool": 0, "access": 1, "provider": 2, "parent": 3, "country": 4}[kind], n["id"]
            assert "subscription" not in n["label"].lower() and "oauth" not in n["label"].lower()
        assert not any(n["label"] in ("Hermes", "Claude Code") for n in lay["nodes"] if n["col"] != 0)
        assert not any(n["label"] == "OpenRouter" for n in lay["nodes"] if n["col"] != 1)
    lay = sankey.sankey_layout(_snapshot_like())
    assert {n["label"] for n in lay["nodes"] if n["col"] == 0} == {"Hermes", "Claude Code"}
    assert {n["label"] for n in lay["nodes"] if n["col"] == 1} == {"OpenRouter", "Anthropic API (direct)"}
    fl = {(a, b): r for a, b, r in _flows(lay)}
    assert fl[("tool:Hermes", "access:OpenRouter")] == 37
    assert fl[("tool:Claude Code", "access:OpenRouter")] == 5


def test_titles_and_label_room():
    for p in (_snapshot_like(), _many(40, unknown_parents={2, 5})[0]):
        out = sankey.sankey_svg(p)
        txt = _text_of(out)
        for name in ("TOOL", "ACCESS METHOD", "COMPANY", "PARENT GROUP", "COUNTRY"):
            assert name in txt
        lay = sankey.sankey_layout(p)
        col = {n["id"]: n["col"] for n in lay["nodes"]}
        for lb in lay["labels"]:
            c = col[lb["id"]]
            if c < 4:
                assert lb["x"] + lb["w"] <= sankey._X[c + 1] - 8, lb["text"]
    lay = sankey.sankey_layout(_snapshot_like())
    lab = {lb["id"]: lb["text"] for lb in lay["labels"]}
    assert lab["access:Anthropic API (direct)"].startswith("Anthropic API (direct) · ")


def test_labels_nearest_own_node():
    p = _snapshot_like()
    lay = sankey.sankey_layout(p)
    nd = {n["id"]: n for n in lay["nodes"]}
    for lb in lay["labels"]:
        own = nd[lb["id"]]
        ly = lb["y"] + lb["h"] / 2
        near = min((n for n in lay["nodes"] if n["col"] == own["col"]),
                   key=lambda n: abs(n["y"] + n["h"] / 2 - ly))
        assert near["id"] == own["id"]


def test_parent_unknown_iff_unparented_provider():
    p = _snapshot_like()
    labels = {n["label"] for n in sankey.sankey_layout(p)["nodes"]}
    assert "Parent unknown" in labels and "Alpha Group" in labels
    only_known = _many(3)[0]
    assert "Parent unknown" not in {n["label"] for n in sankey.sankey_layout(only_known)["nodes"]}


def test_node_labels_only_payload_names():
    p = _snapshot_like()
    allowed = ({x["name"] for x in p["providers"]} | {x["label"] for x in p["network"]["nodes"]}
               | {"OpenRouter", "Anthropic API (direct)", "Hermes", "Claude Code", "Parent unknown"} | set(p["country_names"].values())
               | {"Withheld", "Unknown"})
    for n in sankey.sankey_layout(p)["nodes"]:
        assert n["label"] in allowed, n["label"]


def test_unknown_company_skips_parent_column():
    lay = sankey.sankey_layout(_snapshot_like())
    nd = {n["id"]: n for n in lay["nodes"]}
    assert any(a == "provider:unknown" and nd[b]["col"] == 4 for a, b, _ in _flows(lay))
    assert not any(a == "provider:unknown" and nd[b]["col"] == 3 for a, b, _ in _flows(lay))


def test_min_heights_and_column_fit():
    p, _ = _many(40)
    lay = sankey.sankey_layout(p)
    assert all(n["h"] >= 3 for n in lay["nodes"])
    for c in range(5):
        col = [n for n in lay["nodes"] if n["col"] == c]
        assert max(n["y"] + n["h"] for n in col) <= 215 + 1000 + 0.01


def test_one_and_forty_providers():
    solo = summarise([mk("Solo", "2026-09-25", requests=5, tool="Hermes", route="direct")])
    reg = Registry({"solo": _prov("solo", "Solo", "solo-co", "Solo")}, {}, {}, "t")
    ps = [report_payload(solo, headlines(solo, reg), reg), _many(40, unknown_parents={2, 5})[0]]
    for p in ps:
        out = sankey.sankey_svg(p)
        root = ET.fromstring(out)
        assert root.get("width") == "1080" and root.get("height") == "1350"
        assert p["coverage_note"] in _text_of(out)
        assert "Band width = number of requests." in _text_of(out)
        ids = [e.get("id") for e in root.iter() if e.get("id")]
        assert ids and all(i.startswith("sankey-") for i in ids)
        _check_labels(p)
        assert sankey.sankey_svg(p) == out
    lay = sankey.sankey_layout(ps[1])
    assert len(lay["labels"]) + len(lay["hidden"]) == len(lay["nodes"])
    assert bool(lay["hidden"]) == ("Also:" in _text_of(sankey.sankey_svg(ps[1])))


def test_seven_countries_and_tiny_share():
    p = _countries(["US", "CN", "FR", "DE", "JP", "CA", "IN"], [1], reqs=[50, 40, 30, 20, 10, 9, 8])
    ET.fromstring(sankey.sankey_svg(p))
    _check_labels(p)
    q = _countries(["US"], [1], reqs=[1000])
    q["network"]["nodes"][0]["label"] = "A <1% & co"
    ET.fromstring(sankey.sankey_svg(q))


def test_escaping_of_names():
    p = _snapshot_like()
    for n in p["network"]["nodes"]:
        if n["label"] == "Alpha":
            n["label"] = "Al<&>pha"
    out = sankey.sankey_svg(p)
    ET.fromstring(out)
    assert "Al<&>pha" not in out


def test_section():
    p = _build()[0]
    h = sankey.section(p)
    assert h.startswith('<section id="sankey"><h2>How your prompts flowed</h2><figure class="card" id="card-sankey"')
    assert h.endswith("</section>")
    assert sankey.section(dict(p, empty=True)) == ""


def test_band_offsets_monotonic_and_labels_visible():
    for p in (_snapshot_like(), _many(40, unknown_parents={2, 5})[0]):
        lay = sankey.sankey_layout(p)
        nd = {n["id"]: n for n in lay["nodes"]}
        cy = {i: n["y"] + n["h"] / 2 for i, n in nd.items()}
        for i in nd:
            outs = [(cy[f["target"]], f["y0"]) for f in lay["flows"] if f["source"] == i]
            ins = [(cy[f["source"]], f["y1"]) for f in lay["flows"] if f["target"] == i]
            for pairs in (outs, ins):
                pairs.sort()
                ys = [y for _, y in pairs]
                assert ys == sorted(ys)
    lay = sankey.sankey_layout(_snapshot_like())
    assert not lay["hidden"] and len(lay["labels"]) == len(lay["nodes"])
    _check_labels(_snapshot_like())


def _country_order(lay):
    return [n["label"] for n in sorted((n for n in lay["nodes"] if n["col"] == 4), key=lambda n: n["y"])]


def test_node_order_country_and_unknown_last():
    lay = sankey.sankey_layout(_snapshot_like())
    cn = _country_order(lay)
    assert cn[-1] == "Unknown"
    assert cn.index("Withheld") < cn.index("United States")  # same top parent feeds both
    comp = [n["label"] for n in lay["nodes"] if n["col"] == 2]
    assert comp[-1] == "Unknown company"
    cols3 = [n for n in lay["nodes"] if n["col"] == 4]
    assert all(n["y"] >= 215 and n["y"] + n["h"] <= 1215.01 for n in cols3)


def test_withheld_band_crosses_no_other_band():
    lay = sankey.sankey_layout(_snapshot_like())
    bands = [(f["source"], f["target"], f["y0"], f["y1"], f["requests"]) for f in lay["flows"]
             if f["source"].startswith("parent:") and f["target"].startswith("country:")]
    wh = [b for b in bands if b[1] == "country:withheld"]
    assert wh
    for a1, b1, y0a, y1a, na in wh:
        for a2, b2, y0b, y1b, nb in bands:
            if (a2, b2) == (a1, b1):
                continue
            ca1, ca2 = y0a + max(sankey._MIN, na * lay["scale"]) / 2, y0b + max(sankey._MIN, nb * lay["scale"]) / 2
            cb1, cb2 = y1a + max(sankey._MIN, na * lay["scale"]) / 2, y1b + max(sankey._MIN, nb * lay["scale"]) / 2
            assert (ca1 - ca2) * (cb1 - cb2) >= 0, (a2, b2)


def test_withheld_from_bottom_parent_sits_before_unknown():
    provs = {"a": _prov("a", "Alpha", "a-co", "Alpha Group"), "b": _prov("b", "Beta", "b-co", "Beta")}
    rows = [mk("Alpha", "2026-09-25", pid="a", parent="Alpha Group Ltd", parent_id="a-co",
               parent_display="Alpha Group", country="US", requests=50, tool="Hermes", route="direct"),
            mk("Beta", "2026-09-25", pid="b", parent="Beta Ltd", parent_id="b-co", parent_display="Beta",
               country="CN", requests=30, tool="Hermes", route="direct"),
            mk("Gamma", "2026-09-25", pid="b", parent="Beta Ltd", parent_id="b-co", parent_display="Beta",
               country=None, conf="withheld", requests=3, tool="Hermes", route="direct"),
            mk("Unknown", "2026-09-25", country=None, requests=7, tool="Hermes")]
    s = summarise(rows)
    reg = Registry(provs, {}, {}, "t")
    cn = _country_order(sankey.sankey_layout(report_payload(s, headlines(s, reg), reg)))
    assert cn == ["United States", "China", "Withheld", "Unknown"], cn


def test_displaced_labels_get_leader_lines():
    lay = sankey.sankey_layout(_many(40, unknown_parents={2, 5})[0])
    moved = [lb for lb in lay["labels"] if lb["leader"]]
    assert moved or not lay["labels"]
    out = sankey.sankey_svg(_many(40, unknown_parents={2, 5})[0])
    assert out.count("sankey-leader-") == len(moved)


def test_parent_unknown_ordered_by_barycentre():
    """Unparented company in the middle of the company column: 'Parent unknown' is not forced last."""
    provs = {k: _prov(k, n, c, d, source=c is not None) for k, n, c, d in
             (("a", "Alpha", "a-co", "Alpha Group"), ("u", "Mystery", None, None), ("k", "Kappa", "k-co", "Kappa"))}
    def r(n, pid, par, country, req):
        return mk(n, "2026-09-25", pid=pid, parent=par and par + " Ltd", parent_id=par and pid + "-co",
                  parent_display=par, country=country, requests=req, tool="Hermes", route="direct")
    rows = [r("Alpha", "a", "Alpha Group", "US", 50), r("Mystery", "u", None, "US", 40),
            r("Kappa", "k", "Kappa", "CN", 30)]
    s = summarise(rows)
    reg = Registry(provs, {}, {}, "t")
    lay = sankey.sankey_layout(report_payload(s, headlines(s, reg), reg))
    par = [n["label"] for n in sorted((n for n in lay["nodes"] if n["col"] == 3), key=lambda n: n["y"])]
    assert par == ["Alpha Group", "Parent unknown", "Kappa"]


def test_snapshot_like_names_never_trimmed():
    names = ["Anthropic", "OpenInference", "OpenAI"]
    provs = {k: _prov(k, n, k + "-co", n) for k, n in zip("abc", names)}
    provs["u"] = _prov("u", "Mystery", None, None, source=False)
    rows = [mk(n, "2026-09-25", pid=k, parent=n + " Ltd", parent_id=k + "-co", parent_display=n,
               country=("US", "CN", "US")[i], requests=(321, 700, 20)[i], tool="Hermes", route=("direct", "router", "router")[i])
            for i, (k, n) in enumerate(zip("abc", names))]
    rows += [mk("Mystery", "2026-09-25", pid="u", parent=None, parent_id=None, parent_display=None,
                country="CN", requests=383, tool="Claude Code", route="router"),
             mk("Unknown", "2026-09-25", country=None, requests=8, tool="Claude Code")]
    s = summarise(rows)
    reg = Registry(provs, {}, {}, "t")
    for p in (report_payload(s, headlines(s, reg), reg), _snapshot_like()):
        lay = sankey.sankey_layout(p)
        col = {n["id"]: n["col"] for n in lay["nodes"]}
        assert not lay["hidden"]
        for lb in lay["labels"]:
            assert "…" not in lb["text"], lb["text"]
            c = col[lb["id"]]
            if c < 4:
                assert lb["x"] + lb["w"] <= sankey._X[c + 1] - 8, lb["text"]
    lay = sankey.sankey_layout(_snapshot_like())
    names_ = {lb["text"].rsplit(" · ", 1)[0] for lb in lay["labels"]}
    assert {"Unknown company", "Parent unknown", "Anthropic API (direct)"} <= names_
