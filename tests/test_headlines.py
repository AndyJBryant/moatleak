"""Tests for moatleak.headlines (synthetic fixtures only)."""
from moatleak.findings import summarise
from moatleak.headlines import COUNTRY_NAMES, Headline, country_name, country_phrase, headlines, pct
from moatleak.registry import Registry
from tests.test_findings import mk


class _Prov(dict):
    def __init__(self, rec):
        super().__init__()
        self.rec = set(rec)

    def __getitem__(self, k):
        return {"recognisable": k in self.rec}


class FakeReg:
    def __init__(self, recognisable=()):
        self.providers = _Prov(recognisable)


def kinds(hs):
    return [h.kind for h in hs]


def get(hs, kind):
    return next((h for h in hs if h.kind == kind), None)


def H(rows, rec=()):
    return headlines(summarise(rows), FakeReg(rec))


def countries_rows(*specs):
    """specs: (country, requests)."""
    return [mk(f"P{i}", country=c, requests=n, parent=None, parent_id=None)
            for i, (c, n) in enumerate(specs)]


# ---- helpers
def test_pct_and_country_name():
    assert pct(0.003) == "<1" and pct(0.006) == "1" and pct(0.0) == "0" and pct(0.634) == "63"
    assert country_name("US") == "United States" and country_name("ZZ") == "ZZ"


def test_country_names_cover_shipped_registry():
    reg = Registry.load()
    for p in reg.providers.values():
        hq = p.get("hq")
        for c in (hq.get("country") if isinstance(hq, dict) else None, p.get("ultimate_parent_country")):
            if c and c != "unknown":
                assert c in COUNTRY_NAMES, c
    for c in "US CN SG FR GB DE IE NL LU SE FI CH CA JP KR IN TW HK IL AU AE".split():
        assert c in COUNTRY_NAMES


def test_empty():
    assert headlines(summarise([]), FakeReg()) == []


# ---- 1 countries
def test_countries_threshold():
    assert get(H(countries_rows(("US", 20), ("CN", 80))), "countries")
    assert get(H(countries_rows(("US", 199), ("CN", 801))), "countries")  # top is CN .801
    rows = [mk(f"P{i}", country=f"C{i}", requests=1) for i in range(5)]
    assert get(H(rows), "countries")  # 0.20 passes
    rows = [mk(f"P{i}", country=f"C{i}", requests=1) for i in range(6)]
    assert get(H(rows), "countries") is None  # 1/6 < .2


def test_countries_just_below():
    rows = [mk("A", country="US", requests=199), mk("B", country=None, conf="unknown", requests=801)]
    assert get(H(rows), "countries") is None
    rows = [mk("A", country="US", requests=200), mk("B", country=None, conf="unknown", requests=800)]
    h = get(H(rows), "countries")
    assert h and h.value == 20


def test_country_phrase():
    assert [country_phrase(c) for c in ("US", "GB", "NL", "AE", "CN", "ZZ")] == [
        "the United States", "the United Kingdom", "the Netherlands",
        "the United Arab Emirates", "China", "ZZ"]


def test_countries_text_1_2_3():
    h = get(H(countries_rows(("US", 10))), "countries")
    assert h.text == "100% of your prompts were processed by companies headquartered in the United States."
    h = get(H(countries_rows(("US", 6), ("CN", 4))), "countries")
    assert h.text == ("60% of your prompts were processed by companies headquartered in the United States, "
                      "40% in China.")
    assert h.value == 60 and h.names == ["United States", "China"]
    h = get(H(countries_rows(("US", 5), ("CN", 3), ("SG", 2), ("FR", 1))), "countries")
    assert h.text == ("45% of your prompts were processed by companies headquartered in the United States, "
                      "27% in China and 18% in Singapore.")
    assert len(h.names) == 3


def test_countries_footnote_and_lt1():
    rows = [mk("A", country="US", requests=300, conf="hq_inferred"),
            mk("B", country="CN", requests=100, conf="reported"),
            mk("C", country=None, conf="withheld", requests=1)]
    h = get(H(rows), "countries")
    assert h.footnote == ("Location basis: HQ-inferred 75%, reported by provider 25%, withheld <1%. "
                          "Per-call provider data from 2026-09-22.")


# ---- 2 extent
def test_extent_threshold_and_clauses():
    rows = [mk(n, parent=f"G{i}", parent_id=f"g{i}", country=f"C{i}") for i, n in enumerate("ABC")]
    h = get(H(rows), "extent")
    assert h.text == "3 companies. 3 parent groups. 3 countries." and h.value == 3
    assert get(H(rows[:2]), "extent") is None


def test_extent_omit_and_singular():
    rows = [mk("A", parent="G", parent_id="g", country="US"), mk("B", parent="G", parent_id="g", country="US"),
            mk("C", parent="G", parent_id="g", country="US", requests=5)]
    h = get(H(rows), "extent")
    assert h.text == "3 companies. 1 parent group. 1 country."
    assert h.names == ["C", "A", "B"]
    rows = [mk(n, parent=None, parent_id=None, country=None, conf="unknown") for n in "ABC"]
    h = get(H(rows), "extent")
    assert h.text == "3 companies."


def test_extent_footnote():
    rows = [mk("A"), mk("B", parent=None, parent_id=None, requests=3),
            mk("C", parent=None, parent_id=None, requests=2)]
    h = get(H(rows), "extent")
    assert h.footnote == ("Parent group unknown for 2 companies: B, C. "
                          "A company not owned by another group counts as its own parent group. "
                          "Per-call provider data from 2026-09-22.")
    rows = [mk("A"), mk("B", parent=None, parent_id=None), mk("C")]
    assert get(H(rows), "extent").footnote.startswith("Parent group unknown for 1 company: B. ")
    rows = [mk("A"), mk("B"), mk("C")]
    assert get(H(rows), "extent").footnote.startswith("A company not owned")


# ---- 3 names
def test_names_none_recognisable():
    assert get(H([mk("A")]), "names") is None


def test_names_labels():
    rows = [mk("A", requests=9, parent="Big Group", parent_id="big"), mk("B", requests=5),
            mk("C", requests=3, pid="c", parent="C", parent_id="c"), mk("D", requests=1)]
    h = get(H(rows, rec=["a"]), "names")
    assert h.text == "Including Big Group." and h.value == 1 and h.names == ["Big Group"]
    assert h.footnote == "A is owned by Big Group. Ownership from the moatleak registry (sourced)."
    h = get(H(rows, rec=["a", "b"]), "names")
    assert h.text == "Including Big Group and B Corp."
    h = get(H(rows, rec=["a", "b", "c", "d"]), "names")
    assert h.text == "Including Big Group, B Corp and C." and h.value == 3
    assert h.footnote == ("A is owned by Big Group. B is owned by B Corp. "
                          "Ownership from the moatleak registry (sourced).")


def test_names_use_short_parent_label_and_legal_footnote():
    rows = [mk("A", requests=9, parent="Big Group Technology Ltd", parent_id="big", parent_display="Big Group"),
            mk("B", requests=5, parent="Other Holdings", parent_id="oth")]
    h = get(H(rows, rec=["a", "b"]), "names")
    assert h.text == "Including Big Group and Other Holdings." and h.names == ["Big Group", "Other Holdings"]
    assert h.footnote == ("A is owned by Big Group Technology Ltd. B is owned by Other Holdings. "
                          "Ownership from the moatleak registry (sourced).")


def test_names_no_parent_sentence_and_dedupe():
    rows = [mk("A", requests=5, parent=None, parent_id=None),
            mk("B", requests=4, parent="Grp", parent_id="g"), mk("C", requests=3, parent="Grp", parent_id="g")]
    h = get(H(rows, rec=["a", "b", "c"]), "names")
    assert h.text == "Including A and Grp." and h.names == ["A", "Grp"]
    assert h.footnote == "B is owned by Grp. Ownership from the moatleak registry (sourced)."
    h = get(H(rows[:1], rec=["a"]), "names")
    assert h.text == "Including A." and h.footnote == "Ownership from the moatleak registry (sourced)."


def test_names_never_unknown_parents():
    rows = [mk("A", requests=5, parent=None, parent_id=None),
            mk("B", requests=9, parent="Hidden", parent_id="h")]
    h = get(H(rows, rec=["a"]), "names")
    assert h.names == ["A"] and "Hidden" not in h.text + h.footnote


def test_names_self_parent_uses_provider_name():
    rows = [mk("Baidu", pid="baidu", parent="Baidu Inc", parent_id="baidu")]
    h = get(H(rows, rec=["baidu"]), "names")
    assert h.names == ["Baidu"] and h.footnote == "Ownership from the moatleak registry (sourced)."


# ---- 4 session_spread
def test_spread():
    rows = [mk("A", session="s-A", country="US"), mk("B", session="s-A", country="CN")]
    h = get(H(rows), "session_spread")
    assert h.text == "One conversation was split across 2 companies in 2 countries."
    assert h.value == 2 and h.names == ["A", "B"]
    assert h.footnote == ("1 of 1 conversations with per-call provider data used more than one company. "
                          "Per-call provider data from 2026-09-22.")
    rows = [mk("A", session="s-A", country="US"), mk("B", session="s-A", country="US")]
    assert get(H(rows), "session_spread").text == "One conversation was split across 2 companies."
    assert get(H([mk("A", session="s-A"), mk("A", session="s-B")]), "session_spread") is None


# ---- 5 growth (strict: companies first seen on period[0] are not new)
def test_growth_excludes_first_day_and_lists_it():
    rows = [mk("Z", "2026-09-22"), mk("Y", "2026-09-22"), mk("A", "2026-09-23"),
            mk("B", "2026-09-25"), mk("C", "2026-09-30")]
    h = get(H(rows), "growth")
    assert h.text == "3 new companies joined your network in 8 days." and h.value == 3
    assert h.names == ["A", "B", "C"]
    assert h.footnote == ("Not counted: Y, Z, already serving you on 2026-09-22, when per-call "
                          "provider data starts. Per-call provider data from 2026-09-22.")


def test_growth_ignores_companies_first_seen_before_window():
    rows = [mk("Early", "2026-08-15", route="direct", evidence="documented", source="claude_code"),
            mk("Z", "2026-09-22"), mk("A", "2026-09-23"), mk("B", "2026-09-24"), mk("C", "2026-09-25")]
    s = summarise(rows)
    assert s.period[0] == "2026-09-22" and s.earlier["requests"] == 1
    h = get(headlines(s, FakeReg()), "growth")
    assert h.names == ["A", "B", "C"]
    assert "Early" not in h.footnote and "Z" in h.footnote


def test_growth_thresholds():
    base = mk("Z", "2026-09-22")
    two = [base, mk("A", "2026-09-23"), mk("B", "2026-09-24")]
    assert get(H(two), "growth") is None
    three = two + [mk("C", "2026-10-06")]  # 09-23..10-06 = exactly 14 days
    h = get(H(three), "growth")
    assert h.value == 3 and h.text == "3 new companies joined your network in 14 days."
    spread = two + [mk("C", "2026-10-07")]
    assert get(H(spread), "growth") is None


def test_growth_best_span_and_tie_rule():
    rows = [mk("Z", "2026-09-22"), mk("A", "2026-09-25"), mk("B", "2026-09-26"), mk("C", "2026-09-27"),
            mk("D", "2026-10-20"), mk("E", "2026-10-21"), mk("F", "2026-10-22")]
    h = get(H(rows), "growth")
    assert h.value == 3 and h.names == ["A", "B", "C"]  # earliest start wins ties
    rows = [mk("Z", "2026-09-22"), mk("A", "2026-09-23"), mk("B", "2026-09-24"), mk("C", "2026-09-25"),
            mk("D", "2026-09-26")]
    assert get(H(rows), "growth").names == ["A", "B", "C", "D"]


def test_growth_footnote_is_coverage_note_without_first_day_companies():
    # Z is an unattributed row on period[0], so it is not in first_seen and nothing is "not counted";
    # the earlier non-router row (Early) keeps period[0] from being a router-only day
    rows = [mk("Early", "2026-09-20", route="direct", evidence="documented", source="claude_code"),
            mk("Z", "2026-09-22", pid=None, parent=None, parent_id=None, country=None),
            mk("A", "2026-09-23"), mk("B", "2026-09-24"), mk("C", "2026-09-25")]
    s = summarise(rows)
    h = get(headlines(s, FakeReg()), "growth")
    assert h.names == ["A", "B", "C"] and h.footnote == s.coverage_note


# ---- 6 withheld
def test_withheld():
    def rows(n):
        return [mk("A", country=None, conf="withheld", requests=n, tool="Claude Code"),
                mk("A", "2026-09-25", country=None, conf="withheld", requests=1, tool="Hermes")]
    h = get(H(rows(19)), "withheld")
    assert h and h.value == 20
    assert get(H(rows(18)), "withheld") is None
    h = get(H(rows(20)), "withheld")
    assert h.text == "A withheld the location of 21 of your prompts."
    assert h.names == ["A"]
    assert h.footnote == ("Claude Code, Hermes, 2026-09-22 to 2026-09-25: "
                          "the provider reported the location as not available.")


def test_withheld_picks_largest():
    rows = [mk("A", country=None, conf="withheld", requests=25), mk("B", country=None, conf="withheld", requests=30)]
    assert get(H(rows), "withheld").names == ["B"]


# ---- ordering
def test_order():
    rows = [mk("A", "2026-09-22", session="s-1", country="US", conf="reported", requests=50, parent="G", parent_id="g"),
            mk("B", "2026-09-23", session="s-1", country="CN", parent="H", parent_id="h", requests=40),
            mk("C", "2026-09-24", session="s-2", country="CN", parent="I", parent_id="i", requests=30),
            mk("D", "2026-09-25", country=None, conf="withheld", requests=25)]
    hs = H(rows, rec=["a"])
    assert kinds(hs) == ["countries", "extent", "names", "session_spread", "growth", "withheld"]
    assert all(isinstance(h, Headline) for h in hs)
