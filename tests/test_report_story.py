"""Story slide cards (synthetic fixtures only)."""
import re
import xml.etree.ElementTree as ET

import pytest

from moatleak.report import story, svg

NS = "{http://www.w3.org/2000/svg}"
NOTE = "Synthetic coverage note."
EXTENT_FOOT = "Parent group unknown for 1 company: Delta. Synthetic extent footnote."


def _prov(i, name, country, conf="hq_inferred", req=10, parent=None, pid=None):
    pid = pid or f"p{i}"
    return {"id": pid, "name": name, "requests": req, "country": country,
            "parent_id": parent, "parent": None, "first_seen": f"2026-09-{22 + i % 8:02d}",
            "locations": [{"country": country, "confidence": conf, "requests": req}]}


def _payload(provs=None, growth=True, withheld=True, regimes=True, share=None, earlier=True):
    provs = provs or [
        _prov(1, "Alpha", "US", "documented", 300, "alpha", "alpha"),
        _prov(2, "Beta", "CN", "hq_inferred", 90, "grp", "beta"),
        _prov(3, "Gamma", "CN", "hq_inferred", 80, "grp", "gamma"),
        _prov(4, "Delta", "FR", "hq_inferred", 60),
    ]
    provs = provs + [{"id": "unknown", "name": "Unknown company", "requests": 8, "country": None,
                      "parent_id": None, "parent": None, "first_seen": None,
                      "locations": [{"country": None, "confidence": "unknown", "requests": 8}]}]
    share = share or {"US": 0.6, "CN": 0.3, "FR": 0.07}
    nodes = [{"id": "parent:alpha", "label": "Alpha", "layer": "parent", "requests": 300, "country": "US"},
             {"id": "parent:grp", "label": "Group One", "layer": "parent", "requests": 170, "country": "CN"}]
    heads = [{"kind": "countries", "text": "60% of your prompts were processed by companies "
              "headquartered in the United States, 30% in China.", "value": 60,
              "names": ["United States", "China", "France"], "footnote": "Location basis: x."},
             {"kind": "extent", "text": "4 companies.", "value": 4, "names": [], "footnote": EXTENT_FOOT}]
    fs = {"Beta": "2026-09-23", "Gamma": "2026-09-24", "Delta": "2026-09-30"}
    if growth:
        heads.append({"kind": "growth", "text": "3 new companies joined your network in 8 days.",
                      "value": 3, "names": ["Beta", "Gamma", "Delta"], "footnote": "Growth footnote."})
    if withheld:
        heads.append({"kind": "withheld", "text": "Alpha withheld the location of 217 of your prompts.",
                      "value": 217, "names": ["Alpha"], "footnote": "Withheld footnote."})
    return {
        "empty": False, "period": ["2026-09-22", "2026-10-07"], "days": 16, "total_requests": 1174,
        "coverage_note": NOTE,
        "earlier": ({"requests": 9023, "first": "2026-05-05", "unattributed_requests": 7847}
                    if earlier else {"requests": 0, "first": None, "unattributed_requests": 0}),
        "counts": {"companies": len(provs) - 1, "parent_groups": 2, "countries": 3},
        "headlines": heads, "country_names": {"US": "United States", "CN": "China", "FR": "France"},
        "providers": provs, "network": {"nodes": nodes, "edges": []},
        "footprint": {"countries": {}, "country_share": share, "undisclosed_share": 0.03,
                      "regimes": ([{"id": f"r{i}", "name": f"Regime {i}", "country": c, "share": s}
                                   for i, (c, s) in enumerate([("US", .6), ("CN", .3), ("FR", .1)])]
                                  if regimes else [])},
        "timeline": {"first_seen": fs},
        "withheld": [{"provider": "Alpha", "requests": 217, "first": "2026-08-15",
                      "last": "2026-09-25", "tools": ["Claude Code"]}],
    }


def _root(s):
    return ET.fromstring(s)


def _texts(root):
    return [t.text or "" for t in root.iter(NS + "text")]


def _chips(root):
    return [(float(r.get("x")), float(r.get("y")), float(r.get("width")), float(r.get("height")))
            for r in root.iter(NS + "rect") if r.get("class") == "chip"]


def test_seven_slides_in_order():
    sl = story.slides(_payload())
    assert [c for c, _ in sl] == [f"story-{i}" for i in range(1, 8)]
    kinds = [_root(s).get("data-headline") for _, s in sl]
    assert kinds == ["volume", "extent", "extent", "countries", "growth", "withheld", "regimes"]
    for i, (cid, s) in enumerate(sl, 1):
        root = _root(s)
        assert f"{i} / 7" in _texts(root)
        assert any(NOTE in t for t in _texts(root)) or NOTE in s
        assert "http" not in s.replace("http://www.w3.org/2000/svg", "")
        ids = re.findall(r' id="([^"]+)"', s)
        assert ids and all(x.startswith(cid) for x in ids)
        assert f"url(#{cid}-bg)" in s


def test_renumbering_when_slides_skipped():
    p = _payload(growth=False, withheld=False, regimes=False)
    sl = story.slides(p)
    assert [c for c, _ in sl] == ["story-1", "story-2", "story-3", "story-4"]
    for i, (cid, s) in enumerate(sl, 1):
        assert f"{i} / 4" in _texts(_root(s))
        assert f'data-card="{cid}"' in s


def test_slide_texts():
    t = {i: " | ".join(_texts(_root(s))) for i, (_, s) in enumerate(story.slides(_payload()), 1)}
    assert "In 16 days you sent" in t[1] and "1,174" in t[1] and "prompts to AI." in t[1]
    assert "Plus 9,023 earlier prompts since 5 May; for 7,847 of them" in t[1]
    assert "They were processed by" in t[2] and "companies." in t[2] and "??" in t[2]
    assert "Owned by" in t[3] and "groups, in 3 countries." in t[3]
    assert "60%" in t[4] and "30%" in t[4] and "United States" in t[4]
    assert "3 new companies joined your | network in" in t[5] and "days." in t[5]
    assert "Beta" in t[5] and "23 Sep" in t[5]
    assert "Alpha withheld the location of" in t[6] and "217" in t[6]
    assert "15 Aug – 25 Sep 2026" in t[6]
    assert "Claude Code, 15 Aug to 25 Sep 2026: the provider reported the | location as not available." in t[6]
    assert "Who can legally demand them" in t[7] and "Regime 0" in t[7]


def test_no_earlier_line_when_none():
    t = " ".join(_texts(_root(story.slides(_payload(earlier=False))[0][1])))
    assert "earlier prompts" not in t


def test_groups_slide_labels_and_unknown_parents():
    p = _payload()
    t = _texts(_root(story.slides(p)[2][1]))
    allowed = {n["label"] for n in p["network"]["nodes"] if n["layer"] == "parent"}
    assert {"Alpha", "Group One"} <= set(t)
    assert "Beta" not in t and "Gamma" not in t
    assert "Parent group unknown for 1 company: Delta." in t
    assert allowed == {"Alpha", "Group One"}
    # providers without a parent are listed exactly (Unknown company excluded)
    p["providers"][0]["parent_id"] = None
    t = _texts(_root(story.slides(p)[2][1]))
    assert "Parent group unknown for 2 companies: Alpha, Delta." in t


def test_no_groups_slide_without_parents():
    p = _payload()
    p["counts"]["parent_groups"] = 0
    assert "Owned by" not in " ".join(_texts(_root(story.slides(p)[2][1])))
    assert len(story.slides(p)) == 6


def test_single_company_singular():
    p = _payload(provs=[_prov(1, "Solo", "US", "documented", 50)], growth=False, withheld=False)
    p["counts"]["companies"] = 1
    t = " ".join(_texts(_root(story.slides(p)[1][1])))
    assert "company." in t and "companies." not in t
    for _, s in story.slides(p):
        _root(s)


def test_forty_providers_capped_and_no_overlap():
    provs = [_prov(i, f"Company-{i:02d} with a rather long name", "US" if i % 2 else "SG", req=100 - i)
             for i in range(40)]
    p = _payload(provs=provs)
    p["counts"]["companies"] = 40
    root = _root(story.slides(p)[1][1])
    texts = _texts(root)
    chips = _chips(root)
    assert any(re.fullmatch(r"\+\d+ more", x) for x in texts)
    assert len(chips) <= 19
    for x, y, w, h in chips:
        assert x >= 56 and x + w <= 1080 - 56 and y + h <= 1350
    for i, a in enumerate(chips):
        for b in chips[i + 1:]:
            assert a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]
    for _, s in story.slides(p):
        _root(s)


def test_chips_stay_above_footnote_even_with_long_footnote():
    p = _payload()
    p["headlines"][1]["footnote"] = "Long footnote. " * 30
    root = _root(story.slides(p)[1][1])
    foot_y = min(float(t.get("y")) for t in root.iter(NS + "text") if t.get("font-size") == "15")
    assert all(y + h < foot_y for _, y, _, h in _chips(root))


def test_seven_countries_and_tiny_share_escaped():
    codes = ["US", "CN", "FR", "SG", "JP", "CA", "IN"]
    provs = [_prov(i, f"Co{i}", c, req=100 - i) for i, c in enumerate(codes)]
    share = {"US": .4, "CN": .3, "FR": .2, "SG": .05, "JP": .03, "CA": .017, "IN": .003}
    p = _payload(provs=provs, share=share)
    p["country_names"].update({"SG": "Singapore", "JP": "Japan", "CA": "Canada", "IN": "India"})
    p["headlines"][0]["names"] = ["India", "United States", "China"]
    s = story.slides(p)[3][1]
    root = _root(s)
    assert "&lt;1%" in s and "<1%" in _texts(root)
    p["footprint"]["regimes"][0]["share"] = 0.001
    s7 = story.slides(p)[-1][1]
    assert "&lt;1%" in s7
    _root(s7)
    for _, s in story.slides(p):
        _root(s)


def test_regimes_capped_at_five():
    p = _payload()
    p["footprint"]["regimes"] = [{"id": f"r{i}", "name": f"Regime {i}", "country": "US", "share": .5 - i / 20}
                                 for i in range(8)]
    t = _texts(_root(story.slides(p)[-1][1]))
    assert "Regime 4" in t and "Regime 5" not in t and "+3 more" in t


def test_escaping_of_names():
    p = _payload(provs=[_prov(1, "A<b>&Co", "US", "documented", 50)], growth=False)
    for _, s in story.slides(p):
        _root(s)


def test_section_and_empty():
    h = story.section(_payload())
    assert h.startswith('<section id="story"><h2>Your AI footprint, slide by slide</h2>')
    assert h.count("<figure") == 7 and h.endswith("</section>")
    assert story.section({"empty": True, "total_requests": 0}) == ""


def test_card_background_does_not_change_default_output():
    a = svg.card({"coverage_note": "n", "period": [None, None]}, "c", 100, 100, "")
    assert 'fill="#F6F4EE"' in a and "linearGradient" not in a
    b = svg.card({"coverage_note": "n", "period": [None, None]}, "c", 100, 100, "", dark=True,
                 background=("url(#c-bg)", '<linearGradient id="c-bg"/>'))
    assert 'fill="url(#c-bg)"' in b and '<linearGradient id="c-bg"/>' in b


def _block_bounds(root):
    top, bot = [], []
    for e in root.iter():
        if e.tag == NS + "text" and e.get("font-size") not in ("15", "24") or \
                e.tag == NS + "text" and e.get("font-size") == "24" and "/" not in (e.text or ""):
            y, sz = float(e.get("y")), float(e.get("font-size"))
            if y < 1200 and y > 120:
                top.append(y - 0.8 * sz)
                bot.append(y + 0.25 * sz)
        elif e.tag == NS + "rect" and e.get("class") in ("chip", "badge", "cta", "seg"):
            top.append(float(e.get("y")))
            bot.append(float(e.get("y")) + float(e.get("height")))
    return min(top), max(bot)


def test_content_block_vertically_centred():
    for cid, s in story.slides(_payload()):
        top, bot = _block_bounds(_root(s))
        assert abs((top + bot) / 2 - (110 + 1220) / 2) <= 60, (cid, top, bot)


def test_wrap_balanced_no_single_word_last_line():
    for text in ("Anthropic withheld the location of", "Your prompts were sent to"):
        for mc in range(12, 40):
            lines = story._wrap_balanced(text, mc)
            assert len(lines) == 1 or len(lines[-1].split()) >= 2, (text, mc, lines)
    assert svg.wrap("Anthropic withheld the location of", 32)[-1] == "of"  # the unbalanced original
    assert story._wrap_balanced("Anthropic withheld the location of", 32) == ["Anthropic withheld the", "location of"]


def test_centre_respects_limit():
    block = svg_text = '<text x="56" y="300" font-size="60" fill="#fff">x</text>'
    top, bot = story._bounds(block)
    out = story._centre(block, bot + 5)
    assert story._bounds(out)[1] <= bot + 5 + 0.1
    low = story._centre(block, 5000)
    assert abs(sum(story._bounds(low)) / 2 - (110 + 1220) / 2) < 1


def test_centre_never_shifts_up_on_overflow():
    block = ('<text x="56" y="300" font-size="60" fill="#fff">a</text>'
             '<rect x="56" y="300" width="100" height="1500"/>')
    top, _ = story._bounds(block)
    out = story._centre(block, 5000)
    assert story._bounds(out)[0] >= top - 0.1


def test_no_drawn_cta_on_any_slide():
    for _cid, s in story.slides(_payload()):
        assert "Deploy Sovereign AI" not in s
        assert 'class="cta"' not in s


def _content_payload(label, ncountries=1):
    p = _payload()
    codes = [f"C{i}" for i in range(ncountries)]
    p["country_names"] = {c: f"Country number {i} of many" for i, c in enumerate(codes)}
    p["content"] = {"classes": [{"category": "personal_data", "label": label, "conversations": 1234,
                                 "companies": [{"name": f"Co{i}", "country": c} for i, c in enumerate(codes)]}]}
    return p


def _content_svg(p):
    return dict(story.slides(p))["story-content"]


@pytest.mark.parametrize("label", ["Personal data", "Credentials"])
def test_content_note_verbatim_and_ordered(label):
    root = _root(_content_svg(_content_payload(label, 2)))
    note = f"{label} identified using basic heuristics; nothing was stored or sent by moatleak."
    ts = [(float(t.get("y")), t.text or "") for t in root.iter(NS + "text")]
    sub = min(y for y, tx in ts if tx.startswith("These conversations"))
    head = max(y for y, tx in ts if "contained" in tx or tx.endswith(f"{label.lower()}."))
    mid = [tx for y, tx in ts if head < y < sub]
    assert " ".join(mid) == note


def _content_body_bottom_and_footer_top(label, ncountries=7):
    root = _root(_content_svg(_content_payload(label, ncountries)))
    texts = [(float(t.get("y")), t.get("font-size")) for t in root.iter(NS + "text")]
    footer_top = min(y for y, fs in texts if fs == "15") - 15
    body = [(y, float(fs)) for y, fs in texts if y > 120 and fs not in ("15", "24")]
    assert body
    return max(y + 0.25 * fs for y, fs in body), footer_top


def test_content_slide_fits_with_long_label_and_seven_countries():
    bottom, footer_top = _content_body_bottom_and_footer_top(
        "An extremely long content class label for testing")
    assert bottom < footer_top - 10
