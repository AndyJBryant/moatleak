"""Registry loader, formats, and lint."""
import re
import tomllib
from pathlib import Path
from importlib.resources import files


REQUIRED_PROVIDER_KEYS = {
    "id", "display_name", "legal_entity", "hq", "serving_regions",
    "legal_regimes", "retention", "last_verified", "sources"
}
NETWORK_FIELDS = ("parent", "parent_id", "ultimate_parent_country", "cloud_host")
SOURCED_FIELDS = (
    "legal_entity", "parent", "ultimate_parent_country", "hq",
    "serving_regions", "cloud_host", "retention"
)
VALID_BASIS = {"openrouter_api", "vendor_docs", "hq"}


class Registry:
    """Registry of AI providers, routes, and legal regimes."""

    def __init__(self, providers, routes, regimes, version, makers=None):
        self.providers = providers
        self.routes = routes
        self.regimes = regimes
        self.version = version
        self.makers = makers or {}
        self._alias = {}
        for p in providers.values():
            # Skip if no id (will be reported by lint)
            p_id = p.get("id")
            if not p_id:
                continue
            
            # Skip building aliases if display_name is missing or not a string
            display_name = p.get("display_name")
            if not isinstance(display_name, str):
                continue
            
            openrouter_names = p.get("openrouter_names", [])
            if not isinstance(openrouter_names, list):
                openrouter_names = []
            
            aliases = p.get("aliases", [])
            if not isinstance(aliases, list):
                aliases = []
            
            for name in [display_name, *openrouter_names, *aliases]:
                if name and isinstance(name, str):
                    self._alias[name.casefold()] = p_id

    @classmethod
    def load(cls, root=None):
        """Load registry from TOML files.
        
        Args:
            root: Path to data directory (default: shipped moatleak/data)
        
        Returns:
            Registry instance
        """
        if root is None:
            root = Path(str(files("moatleak") / "data"))
        else:
            root = Path(root)

        # Load providers
        providers = {}
        providers_dir = root / "providers"
        if providers_dir.exists():
            for provider_file in sorted(providers_dir.glob("*.toml")):
                with open(provider_file, "rb") as f:
                    provider_data = tomllib.load(f)
                    provider_id = provider_file.stem
                    # Store the file stem separately for lint validation
                    provider_data["_stem"] = provider_id
                    # Don't overwrite the file's own id; keep it as-is for lint to validate
                    # (Lint will check if id matches stem)
                    providers[provider_id] = provider_data

        # Load routes
        routes = []
        makers = {}
        routes_file = root / "routes.toml"
        if routes_file.exists():
            with open(routes_file, "rb") as f:
                routes_data = tomllib.load(f)
                version = routes_data.get("version")
                routes = routes_data.get("route", [])
                makers = routes_data.get("makers", {})
        else:
            version = None

        # Load regimes
        regimes = {}
        regimes_file = root / "regimes.toml"
        if regimes_file.exists():
            with open(regimes_file, "rb") as f:
                regimes_data = tomllib.load(f)
                for regime in regimes_data.get("regime", []):
                    regimes[regime["id"]] = regime

        return cls(providers, routes, regimes, version, makers)

    def provider_for_name(self, raw):
        """Find provider id by display_name, openrouter_names, or aliases.
        
        Args:
            raw: Name to look up (case-insensitive)
        
        Returns:
            Provider id or None
        """
        if not raw:
            return None
        return self._alias.get(raw.casefold())

    def provider_for_endpoint(self, endpoint):
        """Find provider id by endpoint from routes.
        
        Args:
            endpoint: Endpoint URL
        
        Returns:
            Provider id or None
        """
        for route in self.routes:
            if route.get("endpoint") == endpoint:
                return route.get("provider")
        return None

    def lint(self) -> list[str]:
        """Lint registry for consistency and completeness.
        
        Returns:
            List of human-readable problems (empty = clean)
        """
        problems = []

        # Track alias collisions
        alias_map = {}
        for p_id, provider in self.providers.items():
            display_name = provider.get("display_name")
            if isinstance(display_name, str):
                casefolded = display_name.casefold()
                if casefolded in alias_map and alias_map[casefolded] != p_id:
                    problems.append(f"Alias collision: '{display_name}' maps to both '{alias_map[casefolded]}' and '{p_id}'")
                alias_map[casefolded] = p_id
            
            openrouter_names = provider.get("openrouter_names", [])
            if isinstance(openrouter_names, list):
                for name in openrouter_names:
                    if name and isinstance(name, str):
                        casefolded = name.casefold()
                        if casefolded in alias_map and alias_map[casefolded] != p_id:
                            problems.append(f"Alias collision: '{name}' maps to both '{alias_map[casefolded]}' and '{p_id}'")
                        alias_map[casefolded] = p_id
            
            aliases = provider.get("aliases", [])
            if isinstance(aliases, list):
                for name in aliases:
                    if name and isinstance(name, str):
                        casefolded = name.casefold()
                        if casefolded in alias_map and alias_map[casefolded] != p_id:
                            problems.append(f"Alias collision: '{name}' maps to both '{alias_map[casefolded]}' and '{p_id}'")
                        alias_map[casefolded] = p_id

        for p_id, provider in self.providers.items():
            # Rule 2: Check id matches file stem
            stem = provider.get("_stem")
            file_id = provider.get("id")
            if not file_id:
                problems.append(f"{p_id}: id is missing from file")
            elif file_id != stem:
                problems.append(f"{p_id}: id value '{file_id}' does not match file stem '{stem}'")
            
            # Rule 1: Required keys present
            missing = REQUIRED_PROVIDER_KEYS - set(provider.keys())
            for key in missing:
                problems.append(f"{p_id}: missing required field '{key}'")

            # Also check network fields
            for field in NETWORK_FIELDS:
                if field not in provider:
                    problems.append(f"{p_id}: missing required field '{field}'")

            # Rule 2: id format (only check if id exists)
            if file_id and not re.match(r"^[a-z0-9-]+$", file_id):
                problems.append(f"{p_id}: id format invalid, must match ^[a-z0-9-]+$")

            # Rule 3 & 4: Source validation
            sources_by_claim = {}
            sources_value = provider.get("sources")
            if sources_value is not None:
                # sources must be a list of tables (dicts)
                if not isinstance(sources_value, list):
                    problems.append(f"{p_id}: sources must be a list, got {type(sources_value).__name__}")
                else:
                    for source in sources_value:
                        if not isinstance(source, dict):
                            problems.append(f"{p_id}: each source entry must be a table, got {type(source).__name__}")
                            continue
                        
                        url = source.get("url", "")
                        if not url.startswith(("https://", "http://")):
                            problems.append(f"{p_id}: source URL must be https:// or http://")
                        
                        claim = source.get("claim")
                        if not claim:
                            problems.append(f"{p_id}: source missing 'claim'")
                        else:
                            if claim not in SOURCED_FIELDS and claim != "parent_id":
                                problems.append(f"{p_id}: source claim '{claim}' not in SOURCED_FIELDS")
                        
                        checked = source.get("checked")
                        if not checked:
                            problems.append(f"{p_id}: source missing 'checked' date")
                        
                        if claim:
                            if claim not in sources_by_claim:
                                sources_by_claim[claim] = []
                            sources_by_claim[claim].append(source)

            # Rule 4: Known fields must have sources
            for field in SOURCED_FIELDS:
                value = provider.get(field)
                is_known = False
                if field == "hq":
                    # hq must be a dict with country key
                    if isinstance(value, dict):
                        is_known = value.get("country") != "unknown"
                    else:
                        if value is not None:
                            problems.append(f"{p_id}: hq must be a table, got {type(value).__name__}")
                elif field == "serving_regions":
                    # serving_regions must be a list of dicts
                    if isinstance(value, list) and value:
                        is_known = True
                    elif value is not None and not isinstance(value, list):
                        problems.append(f"{p_id}: serving_regions must be a list, got {type(value).__name__}")
                else:
                    is_known = value and value != "unknown"
                
                if is_known and field not in sources_by_claim:
                    problems.append(f"{p_id}: field '{field}' is known but has no source")

            # Rule 4: parent/parent_id consistency
            parent = provider.get("parent")
            parent_id = provider.get("parent_id")
            if parent == "unknown" and parent_id != "unknown":
                problems.append(f"{p_id}: parent is 'unknown' but parent_id is '{parent_id}'")

            # parent_display_name: required iff the parent is known
            pdn = provider.get("parent_display_name")
            if parent and parent != "unknown":
                if not (isinstance(pdn, str) and pdn.strip()):
                    problems.append(f"{p_id}: parent is known but parent_display_name is missing or not a non-empty string")
                elif len(pdn) > 24:
                    problems.append(f"{p_id}: parent_display_name '{pdn}' exceeds 24 characters")
            elif pdn is not None:
                problems.append(f"{p_id}: parent is unknown but parent_display_name is set")

            # Rule 5: Legal regimes must exist
            legal_regimes = provider.get("legal_regimes")
            if isinstance(legal_regimes, list):
                for regime_id in legal_regimes:
                    if regime_id not in self.regimes:
                        problems.append(f"{p_id}: legal_regimes contains unknown regime '{regime_id}'")
            elif legal_regimes is not None:
                problems.append(f"{p_id}: legal_regimes must be a list, got {type(legal_regimes).__name__}")

            # Rule 8: serving_regions basis
            serving_regions = provider.get("serving_regions")
            if isinstance(serving_regions, list):
                for region in serving_regions:
                    if not isinstance(region, dict):
                        problems.append(f"{p_id}: each serving_regions entry must be a table, got {type(region).__name__}")
                        continue
                    basis = region.get("basis")
                    if basis not in VALID_BASIS:
                        problems.append(f"{p_id}: serving_regions basis '{basis}' not in {VALID_BASIS}")

        # parent_display_name must agree across providers sharing a parent_id
        names_by_parent = {}
        for p_id, provider in self.providers.items():
            pid_ = provider.get("parent_id")
            pdn = provider.get("parent_display_name")
            if pid_ and pid_ != "unknown" and isinstance(pdn, str):
                names_by_parent.setdefault(pid_, {}).setdefault(pdn, []).append(p_id)
        for pid_, names in names_by_parent.items():
            if len(names) > 1:
                problems.append(f"parent_id '{pid_}': inconsistent parent_display_name {sorted(names)}")

        # Rule 5: Regime validity
        for regime_id, regime in self.regimes.items():
            if "id" not in regime:
                problems.append(f"regime missing 'id'")
            if "name" not in regime:
                problems.append(f"{regime_id}: regime missing 'name'")
            if "country" not in regime:
                problems.append(f"{regime_id}: regime missing 'country'")
            if "summary" not in regime:
                problems.append(f"{regime_id}: regime missing 'summary'")
            else:
                summary = regime.get("summary", "")
                if len(summary) > 140:
                    problems.append(f"{regime_id}: regime summary exceeds 140 chars")
            if "source" not in regime:
                problems.append(f"{regime_id}: regime missing 'source'")
            else:
                source = regime.get("source", "")
                if not source.startswith(("https://", "http://")):
                    problems.append(f"{regime_id}: regime source must be https:// or http://")

        # Rule 6: Routes must point to existing providers
        for i, route in enumerate(self.routes):
            provider = route.get("provider")
            if provider and provider not in self.providers:
                problems.append(f"route[{i}]: provider '{provider}' does not exist")
            
            if "endpoint" not in route:
                problems.append(f"route[{i}]: missing 'endpoint'")
            if "rationale" not in route:
                problems.append(f"route[{i}]: missing 'rationale'")
            if "source" not in route:
                problems.append(f"route[{i}]: missing 'source'")

        # Rule 9: country codes are ISO-2 (or "unknown")
        def _bad_cc(v):
            return v != "unknown" and not (isinstance(v, str) and re.fullmatch(r"[A-Z]{2}", v))

        for p_id, provider in self.providers.items():
            hq = provider.get("hq")
            if isinstance(hq, dict):
                if "country" in hq and _bad_cc(hq["country"]):
                    problems.append(f"{p_id}: hq.country '{hq['country']}' is not ISO-2 or 'unknown'")
                sub = hq.get("subdivision")
                if sub is not None and not (isinstance(sub, str) and re.fullmatch(r"[A-Z]{2}-[A-Z0-9]{1,3}", sub)):
                    problems.append(f"{p_id}: hq.subdivision '{sub}' must match ^[A-Z]{{2}}-[A-Z0-9]{{1,3}}$")
            upc = provider.get("ultimate_parent_country")
            if upc is not None and _bad_cc(upc):
                problems.append(f"{p_id}: ultimate_parent_country '{upc}' is not ISO-2 or 'unknown'")
            regions = provider.get("serving_regions")
            if isinstance(regions, list):
                for region in regions:
                    if isinstance(region, dict) and "region" in region and _bad_cc(region["region"]):
                        problems.append(f"{p_id}: serving_regions region '{region['region']}' is not ISO-2 or 'unknown'")
        for regime_id, regime in self.regimes.items():
            if "country" in regime and _bad_cc(regime["country"]):
                problems.append(f"{regime_id}: regime country '{regime['country']}' is not ISO-2 or 'unknown'")

        # Makers: slug -> display name, both non-empty strings
        for key, value in self.makers.items():
            if not (isinstance(key, str) and key and isinstance(value, str) and value):
                problems.append(f"makers: entry '{key}' must map a non-empty string to a non-empty string")

        return sorted(set(problems))
