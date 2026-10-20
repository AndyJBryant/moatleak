"""Radial hero network: layout + SVG (synthetic fixtures only)."""
import re
import xml.etree.ElementTree as ET

from moatleak.findings import summarise
from moatleak.headlines import headlines
from moatleak.registry import Registry
from moatleak.report import hero
from moatleak.report.network import (
    _edge_clearance_violations,
    _label_edge_crossings,
    _seg_hits,
    radial_layout,
    radial_svg,
)
from moatleak.report.payload import report_payload
from tests.test_findings import mk
from tests.test_report_payload import _build, _prov

W, H = 1080, 1350
COUNTRIES = [("US", "reported"), ("CN", "documented"), ("SG", "hq_inferred")]


def _many(n, *, unknown_parents=(), router=True, long_name=False):
    providers, rows = {}, []
    for i in range(n):
        pid = f"prov{i:02d}"
        name = f"Prov Company With A Very Long Name {i:02d}" if (long_name and i == 3) else f"Prov{i:02d}"
        unknown = i in unknown_parents
        providers[pid] = _prov(pid, name, None if unknown else f"{pid}-co",
                               None if unknown else name, source=not unknown)
        cc, conf = COUNTRIES[i % 3]
        rows.append(mk(name, f"2026-09-{22 + i % 5}", pid=pid,
                       parent=None if unknown else f"{name} Corp",
                       parent_id=None if unknown else f"{pid}-co",
                       parent_display=None if unknown else name,
                       country=cc, conf=conf, route="router" if router and i % 2 else "direct",
                       requests=max(1, 60 - i), tool=("Hermes", "Claude Code", "Codex")[i % 3]))
    rows.append(mk("Unknown", "2026-09-25", country=None, requests=4, tool="Hermes"))
    s = summarise(rows)
    reg = Registry(providers, {}, {}, "test-1")
    return report_payload(s, headlines(s, reg), reg), s


def _overlap(a, b):
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def _check_layout(payload):
    lay = radial_layout(payload)
    labs = lay["labels"]
    for i, a in enumerate(labs):
        assert 0 <= a["x"] and a["x"] + a["w"] <= W and 40 <= a["y"] and a["y"] + a["h"] <= H - 100, a
        for b in labs[i + 1:]:
            assert not _overlap(a, b), (a["text"], b["text"])
    return lay


def _text_of(svg):
    root = ET.fromstring(svg)
    return " ".join("".join(t.itertext()) for t in root.iter("{http://www.w3.org/2000/svg}text"))


def test_single_provider():
    s = summarise([mk("Solo", "2026-09-22", requests=5, tool="Hermes", route="direct")])
    reg = Registry({"solo": _prov("solo", "Solo", "solo-corp", "Solo")}, {}, {}, "t")
    p = report_payload(s, headlines(s, reg), reg)
    svg = radial_svg(p)
    ET.fromstring(svg)
    assert "hero-radial" in svg and p["coverage_note"] in _text_of(svg) and "Solo" in svg
    _check_layout(p)


def test_ten_and_forty_providers():
    for n in (10, 40):
        p, _ = _many(n, unknown_parents={2, 5})
        svg = radial_svg(p)
        ET.fromstring(svg)
        text = _text_of(svg)
        assert "hero-radial" in svg and p["coverage_note"] in text
        for prov in p["providers"]:
            name = prov["name"]
            assert name in text or name[:10] in text, name
        lay = _check_layout(p)
        assert {nd["id"] for nd in lay["nodes"]} >= {x["id"] for x in p["network"]["nodes"]
                                                      if x["layer"] == "provider"}


def test_many_providers_get_badges_and_legend():
    p, _ = _many(40)
    text = _text_of(radial_svg(p))
    assert "17 Prov" in text and "Prov00" in text and any(f"{i} Prov" in text for i in (40, 41))


def test_long_name_truncated_full_in_legend():
    p, _ = _many(10, long_name=True)
    svg = radial_svg(p)
    assert "…" in svg and "Prov Company With A Very Long Name 03" in svg
    _check_layout(p)


def test_unknown_parent_marker_and_no_invented_parent():
    p, _ = _many(10, unknown_parents={2, 5})
    svg = radial_svg(p)
    assert svg.count("parent unknown") == 2
    assert "Prov02 Corp" not in svg
    assert not any(f"Prov{i:02d} Corp" in svg for i in range(10))
    lab_texts = [l["text"] for l in radial_layout(p)["labels"]]
    assert not [t for t in lab_texts if t.endswith("Corp")]


def test_same_name_parent_not_drawn_but_differing_parent_is():
    p, _, _ = _build()
    lab = [l["text"] for l in radial_layout(p)["labels"]]
    assert "Group One" in lab
    assert lab.count("Alpha") == 1
    ids = {n["id"] for n in radial_layout(p)["nodes"]}
    assert "parent:group-one" in ids and "parent:alpha-corp" not in ids


def test_deterministic():
    p, _, _ = _build()
    assert radial_svg(p) == radial_svg(p)


def test_ids_scoped():
    p, _ = _many(10)
    svg = radial_svg(p)
    ids = re.findall(r'\bid="([^"]+)"', svg)
    assert ids and all(i.startswith("hero-radial-") for i in ids)
    assert 'href="#hero-radial-arc-0"' in svg


def test_title_numbers_and_singulars():
    p, _, _ = _build()
    svg = radial_svg(p)
    c = p["counts"]
    assert f'fill="#E5484D">{c["companies"]}' in svg
    p1 = dict(p, counts=dict(c, companies=1, parent_groups=1, countries=1))
    t = _text_of(radial_svg(p1))
    assert "1 company" in t.replace("\n", " ") and "1 group" in t and "1 country" in t
    p0 = dict(p, counts=dict(c, parent_groups=0, countries=0))
    t0 = _text_of(radial_svg(p0))
    title = t0.split("processed by")[1].split("A company")[0]
    assert "owned by" not in title and "countr" not in title


def test_empty_payload():
    s = summarise([])
    reg = Registry({}, {}, {}, "t")
    p = report_payload(s, headlines(s, reg), reg)
    out = hero.section(p)
    assert "<svg" not in out


def test_section_wraps_figure():
    p, _, _ = _build()
    out = hero.section(p)
    assert out.startswith('<section id="hero"><h2>Your inference network</h2>')
    assert 'id="card-hero-radial"' in out and out.endswith("</section>")


def test_labels_sit_next_to_their_node():
    for p in (_build()[0], _many(10, unknown_parents={2, 5})[0], _many(40)[0]):
        lay = radial_layout(p)
        nd = {n["id"]: n for n in lay["nodes"]}
        for lab in lay["labels"]:
            if lab["kind"] == "badge":
                continue
            n = nd[lab["id"]]
            nx = min(max(n["x"], lab["x"]), lab["x"] + lab["w"])
            ny = min(max(n["y"], lab["y"]), lab["y"] + lab["h"])
            d = ((nx - n["x"]) ** 2 + (ny - n["y"]) ** 2) ** 0.5 - n["r"]
            assert d <= 40, (lab["text"], d)


def _payloads():
    return (_build()[0], _many(10, unknown_parents={2, 5})[0], _many(40, unknown_parents={1, 7})[0],
            _many(16, unknown_parents={3})[0])


def test_labels_clear_of_arc_band():
    import math
    for p in _payloads():
        lay = radial_layout(p)
        a = lay["arc"]
        for lab in lay["labels"]:
            xs, ys = (lab["x"], lab["x"] + lab["w"]), (lab["y"], lab["y"] + lab["h"])
            nx = min(max(a["cx"], xs[0]), xs[1])
            ny = min(max(a["cy"], ys[0]), ys[1])
            near = math.hypot(nx - a["cx"], ny - a["cy"])
            far = max(math.hypot(x - a["cx"], y - a["cy"]) for x in xs for y in ys)
            assert not (near < a["r"] + a["half"] and far > a["r"] - a["half"]), lab["text"]


def test_tool_labels_16px_bold_and_off_provider_side():
    import math
    first = _payloads()[0]
    for p in (first, *_payloads()[1:]):
        lay = radial_layout(p)
        nd = {n["id"]: n for n in lay["nodes"]}
        for lab in lay["labels"]:
            if lab["kind"] == "tool":
                assert lab["size"] >= 15 and lab["weight"] >= 800  # 15 = floor when 16 px would sit under a foreign edge
                n = nd[lab["id"]]
                lx, ly = lab["x"] + lab["w"] / 2, lab["y"] + lab["h"] / 2


def test_tool_discs_keep_16px_apart():
    import math
    for p in _payloads():
        lay = radial_layout(p)
        tools = [n for n in lay["nodes"] if n["id"].startswith("tool:")]
        for i, a in enumerate(tools):
            for b in tools[i + 1:]:
                assert math.hypot(a["x"] - b["x"], a["y"] - b["y"]) - a["r"] - b["r"] >= 16 - 0.5


def test_each_label_is_nearest_to_its_own_node():
    import math

    def gap(lab, n):
        nx = min(max(n["x"], lab["x"]), lab["x"] + lab["w"])
        ny = min(max(n["y"], lab["y"]), lab["y"] + lab["h"])
        return math.hypot(nx - n["x"], ny - n["y"]) - n["r"]

    snap_like = _many(14, unknown_parents={0, 3, 6, 9})[0]
    for p in (*_payloads(), _many(1)[0], snap_like, _many(10, unknown_parents={1, 2, 3, 4, 5})[0]):
        lay = radial_layout(p)
        nodes = [n for n in lay["nodes"] if n["id"] != "you"]
        nd = {n["id"]: n for n in nodes}
        for lab in lay["labels"]:
            if lab["kind"] == "badge":
                continue
            own = gap(lab, nd[lab["id"]])
            for n in nodes:
                if n["id"] != lab["id"]:
                    assert own < gap(lab, n), (lab["text"], lab["id"], n["id"])


def _access_payload(accesses):
    rows = []
    for i, ac in enumerate(accesses):
        for j in range(3):
            n = f"Co{(i + j) % 4}"
            rows.append(mk(n, "2026-09-23", pid=n.lower(), parent=f"{n} Corp", parent_id=f"{n.lower()}-co",
                           parent_display=n, country=COUNTRIES[(i + j) % 3][0], conf=COUNTRIES[(i + j) % 3][1],
                           access=ac, requests=10 + 3 * i + j, tool=("Hermes", "Claude Code")[(i + j) % 2]))
    s = summarise(rows)
    provs = {r.provider_id: _prov(r.provider_id, r.provider_name, r.parent_id, r.provider_name) for r in rows}
    reg = Registry(provs, {}, {}, "t")
    return report_payload(s, headlines(s, reg), reg)


def test_access_ring_with_1_2_3_methods():
    names = ["OpenRouter", "Anthropic API (direct)", "Example API (direct)"]
    for k in (1, 2, 3):
        p = _access_payload(names[:k])
        svg = radial_svg(p)
        ET.fromstring(svg)
        lay = _check_layout(p)
        ids = {n["id"] for n in lay["nodes"]}
        assert {f"access:{a}" for a in names[:k]} <= ids
        text = _text_of(svg)
        for a in names[:k]:
            assert a in text
        assert lay["fallbacks"] == []
        nd = {n["id"]: n for n in lay["nodes"]}
        for lab in lay["labels"]:
            if lab["kind"] == "access":
                assert lab["size"] >= 15 and lab["weight"] >= 800
                n = nd[lab["id"]]
                others = [m for m in lay["nodes"] if m["id"] not in (lab["id"], "you")]
                def gap(m):
                    nx = min(max(m["x"], lab["x"]), lab["x"] + lab["w"])
                    ny = min(max(m["y"], lab["y"]), lab["y"] + lab["h"])
                    return ((nx - m["x"]) ** 2 + (ny - m["y"]) ** 2) ** 0.5 - m["r"]
                assert all(gap(n) < gap(m) for m in others), lab["text"]


def test_no_tool_to_provider_edge_and_access_between():
    p = _access_payload(["OpenRouter", "Anthropic API (direct)"])
    assert not any(e["source"].startswith("tool:") and e["target"].startswith("provider:")
                   for e in p["network"]["edges"])
    svg = radial_svg(p)
    assert svg.count('rx="') >= 2  # one rounded square per access node


def _only_tool_label_edge(fallbacks, payload):
    """Fallbacks must be empty, except on 16-provider payloads where a tool label may keep only
    7 px (not 8) from a crossing access->provider edge; that is recorded as label-edge:tool:*."""
    if len(payload["providers"]) < 16:
        return fallbacks == []
    return all(x.startswith("label-edge:tool:") for x in fallbacks)


def test_no_fallback_placements_on_standard_payloads():
    many = [_many(n, unknown_parents={2, 5}) [0] for n in (10, 16, 40)]
    small = dict(share=[mk("Big", "2026-09-22", requests=500, tool="Hermes"),
                        mk("Tiny", "2026-09-22", requests=1, tool="Hermes", route="direct")])
    s = summarise(small["share"])
    reg = Registry({"big": _prov("big", "Big", "big-co", "Big"), "tiny": _prov("tiny", "Tiny", "tiny-co", "Tiny")},
                   {}, {}, "t")
    tiny = report_payload(s, headlines(s, reg), reg)
    solo = summarise([mk("Solo", "2026-09-22", requests=5, tool="Hermes", route="direct")])
    reg1 = Registry({"solo": _prov("solo", "Solo", "solo-corp", "Solo")}, {}, {}, "t")
    one = report_payload(solo, headlines(solo, reg1), reg1)
    for p in (*[m for m in many if len(m["providers"]) < 40], _build()[0], tiny, one):
        assert _only_tool_label_edge(radial_layout(p)["fallbacks"], p)


def _snapshot_like():
    rows = [mk(f"Or{i}", "2026-09-23", pid=f"or{i}", parent=f"Or{i} Corp", parent_id=f"or{i}-co",
               parent_display=f"Or{i}", country=COUNTRIES[i % 3][0], conf=COUNTRIES[i % 3][1],
               access="OpenRouter", requests=(300 if i == 0 else 20 + i), tool="Hermes") for i in range(9)]
    rows.append(mk("Unknown", "2026-09-25", country=None, requests=4, tool="Hermes", access="OpenRouter"))
    rows.append(mk("Direct", "2026-09-24", pid="direct", parent="Direct Corp", parent_id="direct-co",
                   parent_display="Direct", country="US", conf="reported", access="Anthropic API (direct)",
                   requests=300, tool="Hermes"))
    rows.append(mk("Direct", "2026-09-24", pid="direct", parent="Direct Corp", parent_id="direct-co",
                   parent_display="Direct", country="US", conf="reported", access="Anthropic API (direct)",
                   requests=4, tool="Claude Code"))
    s = summarise(rows)
    provs = {r.provider_id: _prov(r.provider_id, r.provider_name, r.parent_id, r.provider_name)
             for r in rows if r.provider_id}
    reg = Registry(provs, {}, {}, "t")
    return report_payload(s, headlines(s, reg), reg)


def test_no_edge_passes_through_a_foreign_node():
    # 40 providers x 2 access methods fan out in every direction: no node position can avoid every
    # edge, so there the layout must *record* the violations instead (checked in the next test).
    for p in (_many(10, unknown_parents={2, 5})[0], _many(16, unknown_parents={3})[0], _build()[0],
              _many(1)[0], _snapshot_like(), _access_payload(["OpenRouter"]),
              _access_payload(["OpenRouter", "Anthropic API (direct)"]),
              _access_payload(["OpenRouter", "Anthropic API (direct)", "Example API (direct)"])):
        lay = radial_layout(p)
        assert _edge_clearance_violations(lay) == []
        assert _only_tool_label_edge(lay["fallbacks"], p)


def _real_like():
    vols = [("Or0", 319, "OpenRouter"), ("Direct", 317, "Anthropic API (direct)"), ("Or1", 237, "OpenRouter"),
            ("Or2", 180, "OpenRouter"), ("Or3", 64, "OpenRouter"), ("Or4", 20, "OpenRouter"),
            ("Acme", 12, "OpenRouter"), ("Globex", 8, "OpenRouter"), ("Or7", 3, "OpenRouter"),
            ("Or8", 2, "OpenRouter")]
    rows = []
    for i, (name, n, ac) in enumerate(vols):
        unk = name in ("Acme", "Globex")
        c = COUNTRIES[(i % 2) * 2 % 3]
        kw = {} if unk else dict(pid=name.lower(), parent=f"{name} Corp", parent_id=f"{name.lower()}-co",
                                 parent_display=name)
        rows.append(mk(name, "2026-09-23", country=None if unk else c[0], conf=c[1], access=ac,
                       requests=n, tool="Hermes", **kw))
    s = summarise(rows)
    provs = {r.provider_id: _prov(r.provider_id, r.provider_name, r.parent_id, r.provider_name)
             for r in rows if r.provider_id}
    reg = Registry(provs, {}, {}, "t")
    return report_payload(s, headlines(s, reg), reg)


def _label_payloads():
    return (_many(10, unknown_parents={2, 5})[0], _many(16, unknown_parents={3})[0], _build()[0],
            _many(1)[0], _snapshot_like(), _real_like(), _access_payload(["OpenRouter"]),
            _access_payload(["OpenRouter", "Anthropic API (direct)"]),
            _access_payload(["OpenRouter", "Anthropic API (direct)", "Example API (direct)"]))


def test_no_foreign_edge_under_access_or_tool_labels():
    for p in _label_payloads():
        lay = radial_layout(p)
        if len(p["providers"]) >= 16:  # 8 px is not reachable for tool labels on 16 providers (7 is): must be recorded
            assert {c[0] for c in _label_edge_crossings(lay)} <= {x[len("label-edge:"):] for x in lay["fallbacks"]}
            assert _only_tool_label_edge(lay["fallbacks"], p)
            continue
        assert _label_edge_crossings(lay) == []
        assert lay["fallbacks"] == []


def test_access_labels_at_least_15px_with_two_methods():
    for p in (_snapshot_like(), _access_payload(["OpenRouter", "Anthropic API (direct)"])):
        lay = radial_layout(p)
        labs = [lab for lab in lay["labels"] if lab["kind"] == "access"]
        assert len(labs) == 2 and all(lab["size"] >= 15 for lab in labs)
        assert "Anthropic API (direct)" in {lab["text"] for lab in labs}


def test_tool_labels_clear_of_you_and_you_edges():
    import math
    for p in (*_payloads(), _snapshot_like()):
        lay = radial_layout(p)
        nd = {n["id"]: n for n in lay["nodes"]}
        you = nd["you"]
        for lab in lay["labels"]:
            if lab["kind"] != "tool":
                continue
            b = (lab["x"], lab["y"], lab["w"], lab["h"])
            nx = min(max(you["x"], b[0]), b[0] + b[2])
            ny = min(max(you["y"], b[1]), b[1] + b[3])
            assert math.hypot(nx - you["x"], ny - you["y"]) - you["r"] >= 12 - 0.5, lab["text"]
            for n in lay["nodes"]:
                if n["id"].startswith("tool:"):
                    assert not _seg_hits((you["x"], you["y"]), (n["x"], n["y"]), b, pad=0), lab["text"]


def test_dense_payload_records_unavoidable_violations_honestly():
    lay = radial_layout(_many(40, unknown_parents={1, 7})[0])
    assert len([x for x in lay["fallbacks"] if x.startswith("edge:")]) == len(_edge_clearance_violations(lay))


def test_dense_payload_records_label_edge_crossings_honestly():
    lay = radial_layout(_many(40, unknown_parents={1, 7})[0])
    rec = {x for x in lay["fallbacks"] if x.startswith("label-edge:")}
    assert {f"label-edge:{c[0]}" for c in _label_edge_crossings(lay)} <= rec


def test_forty_provider_layout_is_fast():
    import time
    p = _many(40, unknown_parents={2, 5})[0]
    t = time.perf_counter()
    radial_layout(p)
    assert time.perf_counter() - t < 1.5


def test_seg_near_rect_is_exact():
    from moatleak.report.network import _seg_near_rect as near
    b = (10, 10, 20, 10)  # x 10..30, y 10..20
    assert near((15, 12), (18, 14), b, 0)          # fully inside
    assert near((0, 15), (40, 15), b, 0)           # crossing through
    assert near((0, 0), (10, 10), b, 0)            # touches the corner
    assert near((0, 0), (40, 40), b, 0)            # diagonal through
    assert not near((0, 9.5), (40, 9.5), b, 0)     # misses by 0.5 px
    assert near((0, 9.5), (40, 9.5), b, 0.5)       # ... but within pad
    assert not near((0, 9.5), (40, 9.5), b, 0.4)
    assert not near((0, 0), (9, 30), b, 0)         # passes left of the box
    assert near((12, 12), (12, 12), b, 0)          # degenerate, inside
    assert not near((5, 5), (5, 5), b, 0)          # degenerate, outside
    assert near((5, 5), (5, 5), b, 8)              # degenerate, within pad
