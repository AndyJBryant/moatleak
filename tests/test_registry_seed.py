"""Seed registry tests against the shipped data."""
import pytest
from moatleak.ledger import LedgerRow
from moatleak.registry import Registry
from moatleak.resolve import resolve

SEED = {"anthropic", "streamlake", "baidu", "gmicloud", "relace"}
EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
      "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}
REGIMES_FOR = {
    "US": {"US-CLOUD-ACT", "US-FISA-702"},
    "CN": {"CN-NIL-ART7", "CN-DSL"},
    "SG": {"SG-PDPA"},
    "unknown": set(),
    **{c: {"EU-GDPR"} for c in EU},
}


@pytest.fixture(scope="module")
def reg():
    return Registry.load()


def test_seed_present_and_lint_clean(reg):
    assert SEED <= set(reg.providers)
    assert reg.lint() == []


def test_streamlake(reg):
    assert reg.provider_for_name("StreamLake") == "streamlake"
    p = reg.providers["streamlake"]
    assert p["parent_id"] == "kuaishou"
    assert p["ultimate_parent_country"] == "CN"
    assert p["hq"]["country"] == "CN"
    assert "SG-PDPA" not in p["legal_regimes"]


def test_anthropic_route(reg):
    assert reg.provider_for_endpoint("api.anthropic.com") == "anthropic"


def test_regimes(reg):
    assert set(reg.regimes) == {"US-CLOUD-ACT", "US-FISA-702", "CN-NIL-ART7", "CN-DSL", "EU-GDPR", "SG-PDPA"}
    for r in reg.regimes.values():
        assert len(r["summary"]) <= 140


def test_legal_regimes_derived_from_hq_and_parent_country(reg):
    for pid, p in reg.providers.items():
        expected = REGIMES_FOR[p["hq"]["country"]] | REGIMES_FOR[p["ultimate_parent_country"]]
        assert set(p["legal_regimes"]) == expected, pid


def test_resolver_smoke(reg):
    row = LedgerRow(source="hermes_log", source_ref="gen-1790000000-AAAA", ts="2026-01-01T00:00:00+00:00",
                    route="router", endpoint="openrouter.ai", requested_model="deepseek/deepseek-v4-flash",
                    served_by_raw="StreamLake")
    r = resolve(row, reg)
    assert r.parent_id == "kuaishou"
    assert r.parent_country == "CN"
    assert r.country == "CN"
    assert r.location_confidence == "hq_inferred"


def test_country_names_cover_registry_codes(reg):
    from moatleak.headlines import COUNTRY_NAMES
    codes = set()
    for p in reg.providers.values():
        hq = p.get("hq")
        if isinstance(hq, dict):
            codes.add(hq.get("country"))
        codes.add(p.get("ultimate_parent_country"))
        for r in p.get("serving_regions") or []:
            codes.add(r.get("region"))
    for r in reg.regimes.values():
        codes.add(r.get("country"))
    codes -= {None, "unknown", "EU"}  # "EU" = the GDPR regime's bloc code, not a country
    assert codes
    assert codes <= set(COUNTRY_NAMES), sorted(codes - set(COUNTRY_NAMES))


def test_parent_display_names_shipped(reg):
    for pid, p in reg.providers.items():
        if p.get("parent") == "unknown":
            assert "parent_display_name" not in p, pid
        else:
            assert 0 < len(p["parent_display_name"]) <= 24, pid
