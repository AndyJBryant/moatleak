"""Tests for the resolver (synthetic registry)."""
import pytest
from moatleak.ledger import LedgerRow
from moatleak.registry import Registry
from moatleak.resolve import resolve
from tests.test_registry import write_registry


def prov(pid, name, parent, parent_id, upc, hq, regions="[]", regimes="[]", extra=""):
    return f'''id = "{pid}"
display_name = "{name}"
{extra}
legal_entity = "{name} Ltd"
parent = "{parent}"
parent_id = "{parent_id}"
ultimate_parent_country = "{upc}"
hq = {{ country = "{hq}" }}
serving_regions = {regions}
cloud_host = "unknown"
legal_regimes = {regimes}
retention = "unknown"
last_verified = "2026-10-07"
'''


ROUTES = '''[makers]
anthropic = "Anthropic"
deepseek = "DeepSeek"
openai = "OpenAI"

[[route]]
endpoint = "api.anthropic.com"
provider = "anthropic"
rationale = "r"
source = "https://example.com"

[[route]]
endpoint = "openrouter.ai"
provider = "anthropic"
rationale = "r"
source = "https://example.com"
'''


@pytest.fixture
def reg(tmp_path):
    p = {
        "streamlake": prov("streamlake", "StreamLake", "Kuaishou Technology", "kuaishou", "CN", "CN",
                           regimes='["CN-NIL-ART7", "CN-DSL"]',
                           extra='openrouter_names = ["StreamLake"]\nparent_display_name = "Kuaishou"'),
        "anthropic": prov("anthropic", "Anthropic", "Anthropic", "anthropic", "US", "US"),
        "mystery": prov("mystery", "Mystery", "unknown", "unknown", "unknown", "unknown"),
        "docs-co": prov("docs-co", "DocsCo", "unknown", "unknown", "unknown", "US",
                        regions='[{ region = "DE", basis = "vendor_docs" }, { region = "US", basis = "hq" }]'),
        "two-co": prov("two-co", "TwoCo", "unknown", "unknown", "unknown", "FR",
                       regions='[{ region = "DE", basis = "vendor_docs" }, { region = "IE", basis = "openrouter_api" }]'),
    }
    return Registry.load(write_registry(tmp_path, p, routes_data=ROUTES))


def row(**kw):
    base = dict(source="hermes_log", source_ref="r1", ts="2026-10-01T00:00:00Z", route="router",
                endpoint="openrouter.ai", requested_model="deepseek/deepseek-v4-flash", served_by_raw=None)
    base.update(kw)
    return LedgerRow(**base)


def test_streamlake_router(reg):
    r = resolve(row(served_by_raw="StreamLake"), reg)
    assert r.provider_id == "streamlake"
    assert r.provider_name == "StreamLake"
    assert (r.country, r.location_confidence) == ("CN", "hq_inferred")
    assert r.parent == "Kuaishou Technology" and r.parent_id == "kuaishou" and r.parent_country == "CN"
    assert r.via_router is True
    assert r.regimes == ["CN-NIL-ART7", "CN-DSL"]
    assert r.region_label is None
    assert r.cloud_host is None
    assert r.requested_maker == "DeepSeek"
    assert r.parent_display == "Kuaishou"


def test_unknown_parent(reg):
    r = resolve(row(served_by_raw="Mystery"), reg)
    assert r.parent is None and r.parent_id is None and r.parent_country is None
    assert r.parent_display is None
    assert (r.country, r.location_confidence) == (None, "unknown")


def test_claude_code_withheld(reg):
    r = resolve(row(source="claude_code", route="subscription", endpoint="api.anthropic.com",
                    requested_model="claude-opus-4-8", reported_geo="not_available"), reg)
    assert r.provider_id == "anthropic"
    assert (r.country, r.location_confidence) == (None, "withheld")
    assert r.tool == "Claude Code"
    assert r.requested_maker == "Anthropic"
    assert r.via_router is False


def test_direct_route_rule(reg):
    r = resolve(row(route="direct", endpoint="api.anthropic.com"), reg)
    assert r.provider_id == "anthropic"
    assert (r.country, r.location_confidence) == ("US", "hq_inferred")
    assert r.tool == "Hermes"


def test_reported_geo(reg):
    r = resolve(row(served_by_raw="StreamLake", reported_geo="us"), reg)
    assert (r.country, r.location_confidence) == ("US", "reported")


def test_documented(reg):
    r = resolve(row(served_by_raw="DocsCo"), reg)
    assert (r.country, r.location_confidence) == ("DE", "documented")


def test_two_regions_fall_through(reg):
    r = resolve(row(served_by_raw="TwoCo"), reg)
    assert (r.country, r.location_confidence) == ("FR", "hq_inferred")


def test_unknown_upstream(reg):
    r = resolve(row(served_by_raw="NoSuchCo"), reg)
    assert r.provider_id is None and r.provider_name == "NoSuchCo"
    assert (r.country, r.location_confidence) == (None, "unknown")
    assert r.regimes == [] and r.parent is None


def test_router_without_upstream_not_router_provider(reg):
    r = resolve(row(), reg)
    assert r.provider_id is None and r.provider_name == "Unknown"


@pytest.mark.parametrize("model,maker", [
    ("deepseek/deepseek-v4-flash", "DeepSeek"), ("unlisted/x", "unlisted"),
    ("claude-opus-4-8", "Anthropic"), ("gpt-5", "OpenAI"), ("mystery-model", "unknown"),
])
def test_requested_maker(reg, model, maker):
    assert resolve(row(requested_model=model), reg).requested_maker == maker


@pytest.mark.parametrize("src,tool", [("hermes_db", "Hermes"), ("other", "other")])
def test_tool(reg, src, tool):
    assert resolve(row(source=src), reg).tool == tool


def test_access_method_labels(reg):
    from moatleak.resolve import access_method
    assert access_method(row(), reg) == "OpenRouter"
    assert access_method(row(route="direct", endpoint="api.anthropic.com"), reg) == "Anthropic API (direct)"
    cc = access_method(row(source="claude_code", route="subscription", endpoint="api.anthropic.com"), reg)
    assert cc == "Anthropic API (direct)" and "subscription" not in cc and "OAuth" not in cc
    assert access_method(row(route="unknown", endpoint="llm.example.com"), reg) == "llm.example.com"
    assert access_method(row(route="unknown", endpoint=""), reg) == "Unknown access method"
    assert resolve(row(route="direct", endpoint="api.anthropic.com"), reg).access == "Anthropic API (direct)"
