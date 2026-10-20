"""Tests for Registry: formats, loader, and lint."""
import pytest
from pathlib import Path
from moatleak.registry import Registry


def write_registry(tmp_path, providers_data, routes_version="2026.10.07", routes_data=None, regimes_data=None):
    """Helper to write synthetic TOML registry under tmp_path."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    providers_dir = data_dir / "providers"
    providers_dir.mkdir()

    # Write providers
    for provider_id, content in providers_data.items():
        (providers_dir / f"{provider_id}.toml").write_text(content)

    # Write routes.toml
    routes_content = f'version = "{routes_version}"\n'
    if routes_data:
        routes_content += routes_data
    (data_dir / "routes.toml").write_text(routes_content)

    # Write regimes.toml
    if regimes_data:
        (data_dir / "regimes.toml").write_text(regimes_data)
    else:
        (data_dir / "regimes.toml").write_text("# empty regimes\n")

    return data_dir


class TestRegistryLoad:
    def test_load_shipped_registry_passes_lint(self):
        """The shipped registry should load and pass lint."""
        reg = Registry.load()
        assert reg.version is not None
        assert isinstance(reg.providers, dict)
        assert isinstance(reg.routes, list)
        assert isinstance(reg.regimes, dict)
        assert reg.lint() == [], f"Shipped registry has lint errors: {reg.lint()}"

    def test_load_synthetic_registry(self, tmp_path):
        """Test loading a minimal 2-provider synthetic registry."""
        provider1 = '''id = "streamlake"
display_name = "StreamLake"
openrouter_names = ["StreamLake"]
openrouter_slug = "streamlake"
aliases = []
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
recognisable = false
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com/streamlake"
claim = "legal_entity"
checked = "2026-10-07"
'''
        provider2 = '''id = "another-ai"
display_name = "Another AI"
legal_entity = "Another AI Corp"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "GB" }
serving_regions = [{ region = "EU", basis = "vendor_docs" }]
cloud_host = "gcp"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com/another"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider1, "another-ai": provider2})
        reg = Registry.load(data_dir)
        assert reg.version == "2026.10.07"
        assert len(reg.providers) == 2
        assert "streamlake" in reg.providers
        assert "another-ai" in reg.providers


class TestProviderForName:
    def test_provider_for_name_display_name(self, tmp_path):
        """provider_for_name finds by display_name (case-insensitive)."""
        provider1 = '''id = "streamlake"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider1})
        reg = Registry.load(data_dir)
        assert reg.provider_for_name("StreamLake") == "streamlake"
        assert reg.provider_for_name("streamlake") == "streamlake"
        assert reg.provider_for_name("STREAMLAKE") == "streamlake"

    def test_provider_for_name_openrouter_names(self, tmp_path):
        """provider_for_name finds by openrouter_names."""
        provider1 = '''id = "streamlake"
display_name = "StreamLake"
openrouter_names = ["StreamLake AI", "SLake"]
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider1})
        reg = Registry.load(data_dir)
        assert reg.provider_for_name("streamlake ai") == "streamlake"
        assert reg.provider_for_name("slake") == "streamlake"

    def test_provider_for_name_aliases(self, tmp_path):
        """provider_for_name finds by aliases."""
        provider1 = '''id = "streamlake"
display_name = "StreamLake"
aliases = ["SL Corp", "StreamLake-old"]
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider1})
        reg = Registry.load(data_dir)
        assert reg.provider_for_name("sl corp") == "streamlake"
        assert reg.provider_for_name("streamlake-old") == "streamlake"

    def test_provider_for_name_none(self, tmp_path):
        """provider_for_name(None) returns None."""
        provider1 = '''id = "streamlake"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider1})
        reg = Registry.load(data_dir)
        assert reg.provider_for_name(None) is None


class TestProviderForEndpoint:
    def test_provider_for_endpoint_found(self, tmp_path):
        """provider_for_endpoint returns provider id for matching endpoint."""
        provider1 = '''id = "streamlake"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        routes_data = '''[[route]]
endpoint = "https://api.openrouter.ai/v1"
provider = "streamlake"
rationale = "default route"
source = "https://example.com"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider1}, routes_data=routes_data)
        reg = Registry.load(data_dir)
        assert reg.provider_for_endpoint("https://api.openrouter.ai/v1") == "streamlake"

    def test_provider_for_endpoint_not_found(self, tmp_path):
        """provider_for_endpoint returns None for unknown endpoint."""
        provider1 = '''id = "streamlake"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider1})
        reg = Registry.load(data_dir)
        assert reg.provider_for_endpoint("https://unknown.example.com") is None


class TestLint:
    def test_lint_required_keys(self, tmp_path):
        """lint detects missing required keys."""
        provider_missing_cloud_host = '''id = "streamlake"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider_missing_cloud_host})
        reg = Registry.load(data_dir)
        problems = reg.lint()
        assert any("cloud_host" in p and "streamlake" in p for p in problems), f"Expected cloud_host missing error; got: {problems}"

    def test_lint_id_format(self, tmp_path):
        """lint detects invalid id format."""
        provider_bad_id = '''id = "stream_lake"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"stream_lake": provider_bad_id})
        reg = Registry.load(data_dir)
        problems = reg.lint()
        assert any("stream_lake" in p and (("format" in p) or ("^[a-z0-9-]+$" in p)) for p in problems), f"Expected id format error; got: {problems}"

    def test_lint_source_url_https(self, tmp_path):
        """lint detects non-https source URLs."""
        provider_bad_source = '''id = "streamlake"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "ftp://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider_bad_source})
        reg = Registry.load(data_dir)
        problems = reg.lint()
        assert any("streamlake" in p and (("url" in p) or ("https" in p)) for p in problems), f"Expected source URL error; got: {problems}"

    def test_lint_missing_source_for_known_field(self, tmp_path):
        """lint detects known field without source."""
        provider_no_source = '''id = "streamlake"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "Acme Corp"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider_no_source})
        reg = Registry.load(data_dir)
        problems = reg.lint()
        assert any("streamlake" in p and "parent" in p for p in problems), f"Expected parent source error; got: {problems}"

    def test_lint_unknown_regime(self, tmp_path):
        """lint detects unknown regime id."""
        provider_bad_regime = '''id = "streamlake"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = ["UNKNOWN-REGIME"]
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider_bad_regime})
        reg = Registry.load(data_dir)
        problems = reg.lint()
        assert any("streamlake" in p and "UNKNOWN-REGIME" in p for p in problems), f"Expected unknown regime error; got: {problems}"

    def test_lint_route_to_missing_provider(self, tmp_path):
        """lint detects route pointing to non-existent provider."""
        provider1 = '''id = "streamlake"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        routes_data = '''[[route]]
endpoint = "https://api.example.com"
provider = "nonexistent"
rationale = "test"
source = "https://example.com"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider1}, routes_data=routes_data)
        reg = Registry.load(data_dir)
        problems = reg.lint()
        assert any("nonexistent" in p and "provider" in p for p in problems), f"Expected missing provider error; got: {problems}"

    def test_lint_alias_collision(self, tmp_path):
        """lint detects alias collision between providers."""
        provider1 = '''id = "streamlake"
display_name = "StreamLake"
aliases = ["SL"]
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        provider2 = '''id = "another-ai"
display_name = "Another AI"
aliases = ["SL"]
legal_entity = "Another AI Corp"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "GB" }
serving_regions = [{ region = "EU", basis = "vendor_docs" }]
cloud_host = "gcp"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider1, "another-ai": provider2})
        reg = Registry.load(data_dir)
        problems = reg.lint()
        assert any("alias" in p.lower() and "collision" in p.lower() for p in problems), f"Expected alias collision error; got: {problems}"

    def test_lint_parent_unknown_but_parent_id_set(self, tmp_path):
        """lint detects parent='unknown' with parent_id set."""
        provider_bad_parent = '''id = "streamlake"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "kuaishou"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider_bad_parent})
        reg = Registry.load(data_dir)
        problems = reg.lint()
        assert any("streamlake" in p and "parent" in p for p in problems), f"Expected parent/parent_id mismatch error; got: {problems}"

    def test_lint_unknown_never_needs_source(self, tmp_path):
        """lint passes when parent is 'unknown' with no source."""
        provider_ok = '''id = "streamlake"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "hq"
checked = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "serving_regions"
checked = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "cloud_host"
checked = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "retention"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider_ok})
        reg = Registry.load(data_dir)
        problems = [p for p in reg.lint() if "streamlake" in p]
        assert problems == [], f"Unexpected lint errors for 'unknown' parent: {problems}"

    def test_lint_serving_regions_basis(self, tmp_path):
        """lint detects invalid serving_regions basis."""
        provider_bad_basis = '''id = "streamlake"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "invalid_basis" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider_bad_basis})
        reg = Registry.load(data_dir)
        problems = reg.lint()
        assert any("streamlake" in p and "basis" in p for p in problems), f"Expected invalid basis error; got: {problems}"


class TestIdStemEnforcement:
    """Tests for rule 2: id must equal file stem."""
    
    def test_id_mismatch_file_stem(self, tmp_path):
        """lint detects when id != file stem."""
        # File is streamlake.toml but id claims to be "other"
        provider = '''id = "other"
display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider})
        reg = Registry.load(data_dir)
        problems = reg.lint()
        # Must report problem mentioning the file (streamlake) and the mismatch
        assert any("streamlake" in p and "id" in p for p in problems), f"Expected id/stem mismatch error; got: {problems}"
    
    def test_id_missing_from_file(self, tmp_path):
        """lint detects when id is missing from provider file."""
        provider = '''display_name = "StreamLake"
legal_entity = "StreamLake Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
'''
        data_dir = write_registry(tmp_path, {"streamlake": provider})
        reg = Registry.load(data_dir)
        problems = reg.lint()
        assert any("streamlake" in p and "id" in p for p in problems), f"Expected missing id error; got: {problems}"


class TestMalformedProviders:
    """Tests for robustness: lint must not crash on malformed files."""
    
    @pytest.mark.parametrize("provider_content,field_name", [
        # display_name missing
        ('''id = "test1"
legal_entity = "Test Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
''', "display_name"),
        # hq not a table
        ('''id = "test2"
display_name = "Test"
legal_entity = "Test Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = "US"
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
''', "hq"),
        # sources not a list of tables
        ('''id = "test3"
display_name = "Test"
legal_entity = "Test Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
sources = "https://example.com"
''', "sources"),
        # serving_regions not a list of tables
        ('''id = "test4"
display_name = "Test"
legal_entity = "Test Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = "US"
cloud_host = "aws"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
''', "serving_regions"),
        # legal_regimes not a list
        ('''id = "test5"
display_name = "Test"
legal_entity = "Test Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "unknown"
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }]
cloud_host = "aws"
legal_regimes = "some-regime"
retention = "unknown"
last_verified = "2026-10-07"
[[sources]]
url = "https://example.com"
claim = "legal_entity"
checked = "2026-10-07"
''', "legal_regimes"),
    ])
    def test_malformed_provider_no_crash(self, tmp_path, provider_content, field_name):
        """lint must not crash on malformed fields; must report problem instead."""
        test_id = f"test{field_name[:3]}"
        data_dir = write_registry(tmp_path, {test_id: provider_content})
        reg = Registry.load(data_dir)
        # Must not raise; must return a list of problems
        problems = reg.lint()
        assert isinstance(problems, list), "lint() must return a list even with malformed data"
        # Should report a problem for this provider
        assert any(test_id in p for p in problems), f"Expected problem mentioning {test_id}; got: {problems}"


class TestMakers:
    def test_makers_loaded(self, tmp_path):
        d = write_registry(tmp_path, {}, routes_data='[makers]\nanthropic = "Anthropic"\n')
        reg = Registry.load(d)
        assert reg.makers == {"anthropic": "Anthropic"}

    def test_bad_maker_entry_lints(self, tmp_path):
        d = write_registry(tmp_path, {}, routes_data='[makers]\nbad = ""\n')
        problems = Registry.load(d).lint()
        assert any("maker" in p and "bad" in p for p in problems)

    def test_makers_absent_defaults_empty(self, tmp_path):
        assert Registry.load(write_registry(tmp_path, {})).makers == {}


class TestCountryCodeLint:
    """Rule 9: country codes are ISO-2 or 'unknown'."""

    def _provider(self, hq='{ country = "US" }', upc="US", region="US"):
        return f'''id = "acme"
display_name = "Acme"
legal_entity = "Acme Inc"
parent = "unknown"
parent_id = "unknown"
ultimate_parent_country = "{upc}"
hq = {hq}
serving_regions = [{{ region = "{region}", basis = "hq" }}]
cloud_host = "unknown"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-08"
'''

    def _lint(self, tmp_path, provider, regimes=None):
        d = write_registry(tmp_path, {"acme": provider}, regimes_data=regimes)
        return Registry.load(d).lint()

    def test_hq_country_bad(self, tmp_path):
        p = self._lint(tmp_path, self._provider(hq='{ country = "usa" }'))
        assert any("acme" in x and "hq.country" in x for x in p), p

    def test_parent_country_bad(self, tmp_path):
        p = self._lint(tmp_path, self._provider(upc="China"))
        assert any("acme" in x and "ultimate_parent_country" in x for x in p), p

    def test_serving_region_bad(self, tmp_path):
        p = self._lint(tmp_path, self._provider(region="us"))
        assert any("acme" in x and "serving_regions" in x for x in p), p

    def test_subdivision_bad(self, tmp_path):
        p = self._lint(tmp_path, self._provider(hq='{ country = "US", subdivision = "California" }'))
        assert any("acme" in x and "subdivision" in x for x in p), p

    def test_subdivision_good_and_unknown_ok(self, tmp_path):
        prov = self._provider(hq='{ country = "US", subdivision = "US-CA" }', upc="unknown", region="unknown")
        p = self._lint(tmp_path, prov)
        assert not any("ISO-2" in x or "subdivision" in x for x in p), p

    def test_regime_country_bad(self, tmp_path):
        reg = '[[regime]]\nid = "X-1"\nname = "X"\ncountry = "usa"\nsummary = "s"\nsource = "https://example.com"\n'
        p = self._lint(tmp_path, self._provider(), regimes=reg)
        assert any("X-1" in x and "country" in x for x in p), p

    def test_regime_eu_ok(self, tmp_path):
        reg = '[[regime]]\nid = "EU-1"\nname = "X"\ncountry = "EU"\nsummary = "s"\nsource = "https://example.com"\n'
        p = self._lint(tmp_path, self._provider(), regimes=reg)
        assert not any("EU-1" in x for x in p), p


class TestParentDisplayNameLint:
    """parent_display_name: required for known parents, absent for unknown, consistent per parent_id."""

    def _provider(self, pid, parent, parent_id, extra=""):
        known = parent != "unknown"
        src = ('\n[[sources]]\nurl = "https://example.com/p"\nclaim = "parent"\nchecked = "2026-10-08"\n'
               if known else "")
        return f'''id = "{pid}"
display_name = "{pid}"
legal_entity = "unknown"
parent = "{parent}"
parent_id = "{parent_id}"
{extra}
ultimate_parent_country = "unknown"
hq = {{ country = "unknown" }}
serving_regions = []
cloud_host = "unknown"
legal_regimes = []
retention = "unknown"
last_verified = "2026-10-08"
{src}'''

    def _lint(self, tmp_path, providers):
        return Registry.load(write_registry(tmp_path, providers)).lint()

    def _pdn(self, tmp_path, parent, parent_id, extra):
        d = tmp_path / f"r{len(list(tmp_path.iterdir()))}"
        d.mkdir()
        return [x for x in self._lint(d, {"acme": self._provider("acme", parent, parent_id, extra)})
                if "parent_display_name" in x]

    def test_known_parent_ok(self, tmp_path):
        assert self._pdn(tmp_path, "Acme Holdings Ltd", "acme", 'parent_display_name = "Acme"') == []

    def test_known_parent_missing(self, tmp_path):
        assert self._pdn(tmp_path, "Acme Holdings Ltd", "acme", "")

    def test_known_parent_empty_or_not_str(self, tmp_path):
        assert self._pdn(tmp_path, "Acme Holdings Ltd", "acme", 'parent_display_name = ""')
        assert self._pdn(tmp_path, "Acme Holdings Ltd", "acme", "parent_display_name = 5")

    def test_known_parent_too_long(self, tmp_path):
        assert self._pdn(tmp_path, "Acme Holdings Ltd", "acme", 'parent_display_name = "%s"' % ("x" * 25))
        assert self._pdn(tmp_path, "Acme Holdings Ltd", "acme", 'parent_display_name = "%s"' % ("x" * 24)) == []

    def test_unknown_parent_must_not_have_it(self, tmp_path):
        assert self._pdn(tmp_path, "unknown", "unknown", 'parent_display_name = "Acme"')
        assert self._pdn(tmp_path, "unknown", "unknown", "") == []

    def test_same_parent_id_same_name(self, tmp_path):
        p = {"a": self._provider("a", "Acme Holdings Ltd", "acme", 'parent_display_name = "Acme"'),
             "b": self._provider("b", "Acme Holdings Ltd", "acme", 'parent_display_name = "Acme Co"')}
        assert [x for x in self._lint(tmp_path, p) if "parent_display_name" in x and "acme" in x]

    def test_same_parent_id_same_name_ok(self, tmp_path):
        p = {"a": self._provider("a", "Acme Holdings Ltd", "acme", 'parent_display_name = "Acme"'),
             "b": self._provider("b", "Acme Holdings Ltd", "acme", 'parent_display_name = "Acme"')}
        assert [x for x in self._lint(tmp_path, p) if "parent_display_name" in x] == []
