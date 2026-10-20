"""Tests for moatleak.findings (synthetic fixtures only)."""
from moatleak.findings import dedupe, summarise
from moatleak.ledger import LedgerRow
from moatleak.resolve import Resolved

_n = 0


def mk(name="Alpha", date="2026-09-22", *, pid="UNSET", parent="UNSET", parent_id="UNSET",
       country="US", conf=None, route="router", evidence="observed", source="hermes_log",
       session=None, requests=1, tool=None, model="vendor/model-a", regimes=(), cloud=None, parent_display=None, access=None):
    global _n
    _n += 1
    if pid == "UNSET":
        pid = name.lower().replace(" ", "-") if name != "Unknown" else None
    if parent == "UNSET":
        parent = f"{name} Corp" if pid else None
    if parent_id == "UNSET":
        parent_id = f"{pid}-corp" if pid else None
    if conf is None:
        conf = "reported" if country else "unknown"
    row = LedgerRow(source=source, source_ref=f"gen-1790773241-{_n:04d}", ts=f"{date}T10:00:00Z",
                    route=route, endpoint="example.com", requested_model=model,
                    served_by_raw=name, requests=requests, evidence=evidence, session_ref=session)
    return Resolved(row=row, provider_id=pid, provider_name=name, parent=parent, country=country,
                    region_label=None, location_confidence=conf, regimes=list(regimes),
                    parent_id=parent_id, parent_country=None, cloud_host=cloud,
                    tool=tool or ("Claude Code" if source == "claude_code" else "Hermes"),
                    requested_maker="x", via_router=route == "router",
                    parent_display=parent_display,
                    access=access if access is not None else ("OpenRouter" if route == "router" else "Anthropic API (direct)"))


def test_providers_and_parents():
    s = summarise([
        mk("Alpha", parent="Group One", parent_id="group-one"),
        mk("Beta", parent="Group One", parent_id="group-one", requests=2),
        mk("Gamma", parent=None, parent_id=None, requests=4),
    ])
    assert s.n_providers == 3
    assert s.n_parents_known == 1
    assert s.parents["unknown"] == 4
    assert s.parents["group-one"] == 3
    assert s.parent_names == {"group-one": "Group One"}
    assert s.parent_display_names == {"group-one": "Group One"}  # fallback to legal name
    assert s.total_requests == 7


def test_first_seen_unsorted():
    s = summarise([
        mk("Beta", "2026-09-25"), mk("Alpha", "2026-09-24"), mk("Beta", "2026-09-23"),
        mk("Alpha", "2026-09-26"), mk("Gamma", "2026-09-23"),
    ])
    assert s.first_seen == {"Beta": "2026-09-23", "Alpha": "2026-09-24", "Gamma": "2026-09-23"}
    assert s.new_providers_by_day == {"2026-09-23": ["Beta", "Gamma"], "2026-09-24": ["Alpha"]}


def test_window_and_earlier():
    s = summarise([
        mk("Alpha", "2026-09-22"),
        mk("Beta", "2026-08-01", route="direct", evidence="rule", requests=3, country="CN"),
        mk("Unknown", "2026-08-02", route="direct", evidence="rule", requests=5, country=None),
        mk("Gamma", "2026-05-05", source="hermes_db", evidence="aggregate", requests=10, session="s-X"),
    ])
    assert s.period == ("2026-09-22", "2026-09-22")
    assert s.coverage_note == "Per-call provider data from 2026-09-22."
    assert s.total_requests == 1
    assert s.days_active == 1
    assert s.earlier == {"requests": 18, "unattributed_requests": 5, "first": "2026-05-05",
                         "last": "2026-08-02"}
    assert set(s.providers) == {"Alpha"}
    assert dict(s.countries) == {"US": 1}


def test_no_router_observed_window_is_earliest():
    s = summarise([
        mk("Alpha", "2026-08-01", route="direct", evidence="rule"),
        mk("Beta", "2026-08-05", route="router", evidence="aggregate"),
    ])
    assert s.period == ("2026-08-01", "2026-08-05")
    assert s.total_requests == 2
    assert s.earlier["requests"] == 0 and s.earlier["first"] is None


def test_first_seen_all_history_growth_window():
    s = summarise([
        mk("Claude", "2026-08-15", route="subscription", source="claude_code", country=None,
           conf="withheld"),
        mk("Alpha", "2026-09-22"), mk("Beta", "2026-09-24"),
        mk("Claude", "2026-09-23", route="subscription", source="claude_code"),
    ])
    assert s.period[0] == "2026-09-22"
    assert s.first_seen["Claude"] == "2026-08-15"
    assert s.growth_window == {"first": "2026-09-22", "last": "2026-09-24", "count": 2}


def test_growth_window_empty():
    s = summarise([mk("Alpha", "2026-09-22", route="direct", evidence="rule")])
    assert s.growth_window == {"first": None, "last": None, "count": 0}


def test_sessions_and_fragmentation():
    s = summarise([
        mk("StreamLake", session="s-AAAA", country="CN"),
        mk("Baidu", session="s-AAAA", country="CN"),
        mk("Alpha", session="s-BBBB"),
        mk("Alpha", session="s-CCCC", source="hermes_db", evidence="aggregate", requests=9),
        mk("Beta", session="s-DDDD", evidence="rule"),
    ])
    assert s.sessions_with_provider == 2
    assert s.multi_provider_sessions == 1
    assert s.providers_per_session["s-AAAA"] == {"StreamLake", "Baidu"}
    assert "s-CCCC" not in s.providers_per_session
    assert "s-DDDD" not in s.providers_per_session


def test_undisclosed_and_countries():
    s = summarise([
        mk("Alpha", country="US", requests=6),
        mk("Beta", country="CN", requests=2),
        mk("Claude", country=None, conf="withheld", requests=1),
        mk("Unknown", country=None, requests=1),
    ])
    assert s.countries["withheld"] == 1 and s.countries["unknown"] == 1
    assert s.n_countries_known == 2
    assert s.undisclosed_share == 0.2
    assert s.country_share["US"] == 0.6
    assert s.unknown_provider_requests == 1
    assert s.n_providers == 3
    assert s.confidence["reported"] == 8


def test_withheld_all_history():
    s = summarise([
        mk("Alpha", "2026-09-22"),
        mk("Claude", "2026-08-15", country=None, conf="withheld", source="claude_code",
           route="subscription", requests=3, tool="Claude Code"),
        mk("Claude", "2026-09-25", country=None, conf="withheld", requests=2, tool="Hermes"),
    ])
    assert s.withheld == {"Claude": {"requests": 5, "first": "2026-08-15", "last": "2026-09-25",
                                     "tools": ["Claude Code", "Hermes"]}}
    assert s.countries["withheld"] == 2  # window only


def test_dedupe():
    rows = [
        mk("Alpha", session="s-AAAA"),
        mk("Alpha", session="s-AAAA", source="hermes_db", evidence="aggregate", requests=7),
        mk("Alpha", session="s-ZZZZ", source="hermes_db", evidence="aggregate", requests=4),
        mk("Alpha", session=None, source="hermes_db", evidence="aggregate", requests=2),
    ]
    out = dedupe(rows)
    assert len(out) == 3
    assert sorted(r.row.requests for r in out) == [1, 2, 4]


def test_max_session_spread_tiebreak_and_daily_matrix():
    s = summarise([
        mk("Alpha", session="s-1", country="US"), mk("Beta", session="s-1", country="US"),
        mk("Gamma", session="s-2", country="CN"), mk("Delta", session="s-2", country="CN"),
        mk("Epsilon", session="s-3", country="US"),
        mk("Unknown", session="s-1"),
        mk("Alpha", source="hermes_db", evidence="aggregate", requests=50),
        mk("Beta", evidence="rule", route="direct", requests=3),
    ])
    # s-1 and s-2 tie on providers and countries -> smallest sorted names: Alpha,Beta
    assert s.max_session_spread == {"providers": ["Alpha", "Beta"], "countries": ["US"],
                                    "n_providers": 2, "n_countries": 1}
    assert s.daily_matrix == {"2026-09-22": {"Alpha": 1, "Beta": 4, "Gamma": 1, "Delta": 1,
                                             "Epsilon": 1}}


def test_max_session_spread_prefers_countries():
    s = summarise([
        mk("Alpha", session="s-1", country="US"), mk("Beta", session="s-1", country="US"),
        mk("Gamma", session="s-2", country="CN"), mk("Delta", session="s-2", country="DE"),
    ])
    assert s.max_session_spread["providers"] == ["Delta", "Gamma"]
    assert s.max_session_spread["countries"] == ["CN", "DE"]


def test_context_counters():
    s = summarise([
        mk("Alpha", model="m1", regimes=["r1", "r2"], cloud="self", requests=2),
        mk("Beta", model="m2", regimes=["r1"], cloud="aws", route="direct", evidence="rule"),
        mk("Gamma", model="m1", cloud=None, source="claude_code"),
    ])
    assert s.models == {"m1": 3, "m2": 1}
    assert s.tools == {"Hermes": 3, "Claude Code": 1}
    assert s.regimes == {"r1": 3, "r2": 2}
    assert s.cloud_hosts == {"self": 2, "aws": 1}
    assert s.via_router_requests == 3


def test_empty():
    s = summarise([])
    assert s.period == ("", "") and s.coverage_note == ""
    assert s.total_requests == 0 and s.days_active == 0
    assert s.max_session_spread is None
    assert s.earlier == {"requests": 0, "unattributed_requests": 0, "first": None, "last": None}
    assert s.undisclosed_share == 0.0
    assert not s.providers and not s.first_seen and not s.withheld


def test_parent_display_names_use_short_name():
    s = summarise([mk("Alpha", parent="Group One Holdings Ltd", parent_id="group-one", parent_display="Group One"),
                   mk("Gamma", parent=None, parent_id=None)])
    assert s.parent_names == {"group-one": "Group One Holdings Ltd"}
    assert s.parent_display_names == {"group-one": "Group One"}
    assert s.provider_info["Alpha"]["parent_display"] == "Group One"
    assert s.provider_info["Gamma"]["parent_display"] is None


def test_provider_info():
    s = summarise([
        mk("Alpha", parent="Group One", parent_id="group-one", country=None),
        mk("Alpha", parent="Group One", parent_id="group-one", country="US"),
        mk("Gamma", parent=None, parent_id=None, country=None),
        mk("Unknown", route="direct", evidence="rule"),
    ])
    assert s.provider_info == {
        "Alpha": {"provider_id": "alpha", "parent_id": "group-one", "parent": "Group One",
                  "parent_display": "Group One", "country": "US"},
        "Gamma": {"provider_id": "gamma", "parent_id": None, "parent": None,
                  "parent_display": None, "country": None},
    }
    assert summarise([]).provider_info == {}


def test_routes_and_provider_locations():
    s = summarise([
        mk("Alpha", requests=3, tool="Hermes"),
        mk("Alpha", requests=2, tool="Claude Code", route="direct"),
        mk("Alpha", requests=4, country=None, conf="withheld", route="direct"),
        mk("Unknown", requests=5, country=None),
        mk("Beta", requests=1, country="CN", conf="documented"),
        mk("Alpha", "2026-08-01", route="direct", evidence="rule", requests=50),
    ])
    assert s.routes[("Hermes", "OpenRouter", "Alpha")] == 3
    assert s.routes[("Claude Code", "Anthropic API (direct)", "Alpha")] == 2
    assert s.routes[("Hermes", "Anthropic API (direct)", "Alpha")] == 4
    assert s.routes[("Hermes", "OpenRouter", None)] == 5
    assert sum(s.routes.values()) == sum(s.access.values()) == s.total_requests == 15
    assert s.access == {"OpenRouter": 9, "Anthropic API (direct)": 6}
    assert set(s.provider_locations) == {"Alpha", "Beta"}
    assert dict(s.provider_locations["Alpha"]) == {("US", "reported"): 5, (None, "withheld"): 4}
    assert dict(s.provider_locations["Beta"]) == {("CN", "documented"): 1}


def test_access_and_routes_in_window():
    s = summarise([
        mk("Alpha", "2026-09-22", requests=3),
        mk("Alpha", "2026-09-23", route="direct", requests=2, tool="Claude Code"),
        mk("Unknown", "2026-09-23", requests=5),
        mk("Alpha", "2026-08-01", route="direct", evidence="rule", requests=40),
    ])
    assert s.access == {"OpenRouter": 8, "Anthropic API (direct)": 2}
    assert s.routes == {("Hermes", "OpenRouter", "Alpha"): 3,
                        ("Claude Code", "Anthropic API (direct)", "Alpha"): 2,
                        ("Hermes", "OpenRouter", None): 5}


def test_plain_coverage_note():
    s = summarise([mk("Alpha", "2026-09-25")])
    assert s.coverage_note == "Per-call provider data from 2026-09-25."
