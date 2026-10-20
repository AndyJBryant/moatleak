import pytest
from moatleak.findings import summarise
from moatleak.headlines import headlines, pct, country_name, COUNTRY_NAMES
from moatleak.readers import all_readers
from moatleak.readers.claude_code import ClaudeCodeReader
from moatleak.readers.hermes import HermesLogReader
from moatleak.registry import Registry
from moatleak.resolve import resolve

pytestmark = pytest.mark.acceptance


@pytest.fixture(scope="module")
def reg():
    return Registry.load()


@pytest.fixture(scope="module")
def disp(reg):
    return lambda n: reg.providers[reg.provider_for_name(n)]["display_name"]


@pytest.fixture(scope="module")
def cc(snapshot):
    home, _ = snapshot
    return list(ClaudeCodeReader().iter_rows(home))


@pytest.fixture(scope="module")
def hermes_log_rows(snapshot):
    home, _ = snapshot
    return list(HermesLogReader().iter_rows(home))


@pytest.fixture(scope="module")
def full(snapshot, reg):
    home, _ = snapshot
    return summarise([resolve(r, reg) for rd in all_readers() for r in rd.iter_rows(home)])


def test_hermes_log_findings_match_oracle(snapshot, reg, disp, hermes_log_rows):
    _, gt = snapshot
    s = summarise([resolve(r, reg) for r in hermes_log_rows])
    assert s.total_requests == gt["hermes_calls"]
    assert tuple(s.period) == tuple(gt["period"])
    assert dict(s.providers) == {disp(n): c for n, c in gt["served_by"].items() if n != "UNRECORDED"}
    assert s.unknown_provider_requests == gt["served_by"].get("UNRECORDED", 0)
    assert s.first_seen == {disp(n): d for n, d in gt["first_seen"].items()}
    assert s.sessions_with_provider == gt["sessions_with_upstream"]
    assert s.multi_provider_sessions == gt["multi_provider_sessions"]
    assert s.max_session_spread["n_providers"] == gt["max_providers_in_session"]


def test_full_scan_matches_oracle_with_explained_differences(snapshot, disp, cc, full):
    _, gt = snapshot
    s = full
    start = gt["period"][0]
    cc_in = [r for r in cc if r.ts[:10] >= start]
    assert tuple(s.period) == tuple(gt["period"])
    assert s.n_providers == len(gt["distinct_companies"])
    assert set(s.providers) == {disp(n) for n in gt["distinct_companies"]}
    for n in gt["distinct_companies"]:
        expected = gt["served_by"][n]
        if n == "Anthropic":
            expected += sum(r.requests for r in cc_in)
        assert s.providers[disp(n)] == expected, n
    oracle_first = {disp(n): d for n, d in gt["first_seen"].items()}
    assert {k: v for k, v in s.first_seen.items() if v >= start} == oracle_first
    assert all(v < start for k, v in s.first_seen.items() if k not in oracle_first)
    assert "Anthropic" in s.first_seen and s.first_seen["Anthropic"] < start
    assert s.growth_window["count"] == len(gt["first_seen"])
    assert s.multi_provider_sessions == gt["multi_provider_sessions"]
    assert s.max_session_spread["n_providers"] == gt["max_providers_in_session"]
    assert s.sessions_with_provider == gt["sessions_with_upstream"] + len(
        {r.session_ref for r in cc_in if r.session_ref})
    assert sum(v["requests"] for v in s.withheld.values()) == gt["claude_code_withheld"]


def test_headlines_trace_to_summary_and_registry(snapshot, reg, full, hermes_log_rows, cc):
    s = full
    hs = headlines(s, reg)
    assert [h.kind for h in hs] == ["countries", "extent", "names", "session_spread", "growth", "withheld"]
    by = {h.kind: h for h in hs}
    inverse = {country_name(c): c for c in COUNTRY_NAMES}

    h = by["countries"]
    assert h.names
    reg_countries = set()
    for info in s.provider_info.values():
        p = reg.providers[info["provider_id"]]
        reg_countries.add((p.get("hq") or {}).get("country"))
        reg_countries.add(p.get("ultimate_parent_country"))
    assert reg_countries
    for name in h.names:
        c = inverse[name]
        assert c in s.countries
        assert f"{pct(s.country_share[c])}% " in h.text and name in h.text
        assert c in reg_countries

    h = by["extent"]
    n, p, c = s.n_providers, s.n_parents_known, s.n_countries_known
    clauses = [f"{n} companies."]
    if p:
        clauses.append("1 parent group." if p == 1 else f"{p} parent groups.")
    if c:
        clauses.append("1 country." if c == 1 else f"{c} countries.")
    assert h.text == " ".join(clauses)
    assert h.value == s.n_providers

    h = by["names"]
    assert h.names
    assert h.text == "Including Anthropic, Kuaishou and Baidu."
    verified_parents = 0
    for label in h.names:
        assert label.lower() != "unknown"
        if label in s.providers:
            continue
        srcs = [i for i in s.provider_info.values()
                if i["parent_id"] is not None and i["parent_display"] == label]
        assert srcs, label
        assert any(
            src.get("claim") == "parent"
            for i in srcs for src in reg.providers[i["provider_id"]].get("sources", []))
        verified_parents += 1
    assert verified_parents >= 1
    for info in s.provider_info.values():
        if info["parent_id"] is None:
            assert info["parent_display"] is None
            assert info["parent"] not in h.names or info["parent"] is None
    for parent_id, short in s.parent_display_names.items():
        assert short in {p.get("parent_display_name") for p in reg.providers.values()
                         if p.get("parent_id") == parent_id}

    h = by["session_spread"]
    assert h.value == s.max_session_spread["n_providers"]
    assert h.names == s.max_session_spread["providers"]

    h = by["growth"]
    assert h.names
    assert h.value == len(h.names)
    assert all(n in s.first_seen for n in h.names)
    assert all(s.first_seen[n] > s.period[0] for n in h.names)
    assert h.value == 7 and h.text == "7 new companies joined your network in 9 days."
    assert h.footnote.startswith("Not counted: Baidu, StreamLake, already serving you on 2026-09-22")

    h = by["withheld"]
    assert h.value == s.withheld[h.names[0]]["requests"]

    refs = {r.session_ref for r in hermes_log_rows if r.session_ref}
    refs |= {r.session_ref for r in cc if r.session_ref}
    refs |= {r.source_ref for r in hermes_log_rows[:20] if r.source_ref}
    assert refs
    for h in hs:
        for t in (h.text, h.footnote):
            assert "/home/" not in t
            assert not any(ref in t for ref in refs)
