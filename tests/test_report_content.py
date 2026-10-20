"""Content section + story-content slide (synthetic payloads only)."""
import re
import xml.etree.ElementTree as ET

from moatleak.report import sections, story
from moatleak.report.render import render
from tests.test_report_payload import _build
from tests.test_report_story import NOTE, NS, _payload, _prov, _root, _texts


def _cls(cat, label, n, companies=(), earlier=0):
    return {"category": cat, "label": label, "conversations": n, "earlier_conversations": earlier,
            "companies": [{"name": a, "country": c, "conversations": k} for a, c, k in companies]}


def _content(classes):
    return {"taxonomy_version": "1", "method": "rule", "scanned_conversations": 383,
            "earlier_scanned_conversations": 50, "classes": classes}


def _with(content, **kw):
    p = _payload(**kw)
    p["content"] = content
    return p


CRED = _cls("credential", "Credentials", 3, [("Alpha", "US", 2), ("Beta", "CN", 1)])
PERS = _cls("personal_data", "Personal data", 40, [("Alpha", "US", 40)])


def test_absent_when_none():
    p = _payload()
    p["content"] = None
    assert sections.content(p) == ""
    b = _build()[0]
    b["content"] = None
    assert 'id="content"' not in render(b)
    assert "story-content" not in [c for c, _ in story.slides(p)]
    assert sections.content(_payload()) == ""  # key missing entirely


def test_nothing_found():
    h = sections.content(_with(_content([])))
    assert 'id="content"' in h
    assert "Nothing sensitive detected by the local scan in 383 conversations." in h
    assert "story-content" not in [c for c, _ in story.slides(_with(_content([])))]


def test_rows_and_chips():
    h = sections.content(_with(_content([CRED, _cls("x", "Nothing here", 1, [("Mystery", None, 1)])])))
    assert "What your prompts contained" in h
    assert "Local scan of 383 conversations in this period (regular expressions, taxonomy v1)" in h
    assert "3 conversations" in h and "1 conversation<" in h
    assert "Conversations handled by: " in h and "processed by" not in h.lower()
    assert "Alpha (United States)" in h and "Beta (China)" in h and "Mystery (??)" in h
    assert "#E5484D" in h and "#3E8EF7" in h and "#8B8D98" in h


def test_earlier_only_class():
    h = sections.content(_with(_content([_cls("credential", "Credentials", 0, [], 4), PERS])))
    assert "+4 in earlier history (companies not recorded)" in h
    first = h.split("Personal data")[0]
    assert "handled by" not in first


def test_escaping():
    c = _cls("credential", "Credentials", 1, [("<b>Evil</b>", "US", 1)])
    h = sections.content(_with(_content([c])))
    assert "<b>Evil" not in h and "&lt;b&gt;Evil" in h


def test_story_slide_priority_and_text():
    p = _with(_content([PERS, CRED]))
    sl = story.slides(p)
    ids = [c for c, _ in sl]
    assert ids.index("story-content") == len(ids) - 2 and ids[-1] == "story-7"
    s = dict(sl)["story-content"]
    root = _root(s)
    t = " ".join(_texts(root))
    assert "3 of your conversations contained credentials." in t
    assert "These conversations were handled by 2 companies in 2 countries: United States, China." in t and "processed by" not in t.lower()
    assert "Local regex scan; no prompt text stored or sent." in t and NOTE in t
    n = len(sl)
    assert f"{n} / {n}" not in t and f"{n - 1} / {n}" in t  # content is the second-to-last slide
    assert 'data-card="story-content"' in s


def test_story_singular_and_unknown():
    c = _cls("credential", "Credentials", 1, [("Alpha", "US", 1)])
    t = " ".join(_texts(_root(dict(story.slides(_with(_content([c]))))["story-content"])))
    assert "1 of your conversations contained credentials." in t
    assert "handled by 1 company in 1 country: United States." in t
    c = _cls("credential", "Credentials", 2, [("Q", None, 2)])
    t = " ".join(_texts(_root(dict(story.slides(_with(_content([c]))))["story-content"])))
    assert "handled by 1 company in an undisclosed location." in t


def test_story_only_in_window_classes():
    p = _with(_content([_cls("credential", "Credentials", 0, [], 5)]))
    assert "story-content" not in [c for c, _ in story.slides(p)]


def test_story_escapes_and_no_regimes_slide():
    c = _cls("credential", "Cred<>", 1, [("A", "US", 1)])
    p = _with(_content([c]), regimes=False)
    sl = story.slides(p)
    assert sl[-1][0] == "story-content"
    _root(sl[-1][1])


def test_render_parses_and_synthetic_payloads():
    for kw in ({"provs": [_prov(1, "Solo", "US", "documented", 5, None, "solo")]},
               {"provs": [_prov(i, f"P{i}", "US", req=3) for i in range(40)]},
               {"share": {"US": .5, "CN": .2, "FR": .1, "DE": .1, "JP": .04, "IN": .03, "BR": .029}},
               {"share": {"US": .997, "CN": .003}}):
        p = _with(_content([CRED, PERS, _cls("x", "Other", 2, [("Unknown company", None, 2)])]), **kw)
        sl = story.slides(p)
        assert "story-content" in [c for c, _ in sl]
        for _, s in sl:
            ET.fromstring(s)
    b = _build()[0]
    b["content"] = _content([CRED, PERS])
    h = render(b)
    assert 'id="content"' in h and "How this was measured" in h and "Tier 1" in sections.methodology(b)
    assert h.index('id="sankey"') < h.index('id="content"') < h.index('id="ledger"')


def test_methodology_without_content():
    assert "Tier 1" not in sections.methodology(_build()[0])


def test_no_ids_or_refs():
    h = sections.content(_with(_content([CRED])))
    s = dict(story.slides(_with(_content([CRED]))))["story-content"]
    for bad in ("row_id", "session", "source_ref", "/home/"):
        assert bad not in h and bad not in s


def test_no_text_to_scan():
    c = _content([])
    c["scanned_conversations"] = 0
    h = sections.content(_with(c))
    assert "No conversations in this period had prompt text to scan." in h and "Nothing sensitive" not in h


def test_story_many_countries_capped_and_above_footer():
    comps = [(f"Co{i}", code, 1) for i, code in enumerate(["CN", "US", "DE", "FR", "JP", "KR", "IN"])]
    p = _with(_content([_cls("credential", "Credentials", 7, comps)]))
    p["country_names"] = {**p.get("country_names", {}), "CN": "China", "US": "United States", "DE": "Germany",
                          "FR": "France", "JP": "Japan", "KR": "South Korea", "IN": "India"}
    s = dict(story.slides(p))["story-content"]
    t = " ".join(_texts(_root(s)))
    assert "in 7 countries: China, United States, Germany and 4 more." in t
    assert "Japan" not in t
    ys = [float(y) for y in re.findall(r'<text[^>]* y="([\d.]+)"[^>]*font-size="32"', s)]
    assert ys and max(ys) <= story._limit(p, "Local regex scan; no prompt text stored or sent.")
