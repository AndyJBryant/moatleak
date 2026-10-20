"""Offline registry drift check.

Compares a saved OpenRouter provider catalogue (GET /api/v1/providers, saved by
the user) against the moatleak registry. No network access.

Usage: python tools/registry_drift.py --from-file PATH [--registry DIR]
"""
import argparse
import json
import sys
from pathlib import Path

try:
    from moatleak.registry import Registry
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from moatleak.registry import Registry


def drift(catalogue: dict, registry) -> dict:
    unmatched, hq_mismatch, dc_mismatch = [], [], []
    seen_names = set()
    for item in catalogue.get("data", []):
        name = item.get("name")
        if isinstance(name, str):
            seen_names.add(name.casefold())
        pid = registry.provider_for_name(name)
        if pid is None:
            unmatched.append(name)
            continue
        prov = registry.providers.get(pid, {})
        hq = item.get("headquarters")
        reg_hq = (prov.get("hq") or {}).get("country")
        if hq is not None and reg_hq is not None and reg_hq != "unknown" and reg_hq != hq:
            hq_mismatch.append((pid, reg_hq, hq))
        dcs = item.get("datacenters")
        if isinstance(dcs, list) and dcs:
            reg_regions = {
                r.get("region")
                for r in prov.get("serving_regions", [])
                if r.get("basis") == "openrouter_api"
            }
            if reg_regions and reg_regions != set(dcs):
                dc_mismatch.append((pid, sorted(reg_regions), sorted(set(dcs))))
    missing = []
    for pid, prov in registry.providers.items():
        names = prov.get("openrouter_names") or []
        if names and not any(n.casefold() in seen_names for n in names):
            missing.append(pid)
    return {
        "unmatched": sorted(unmatched),
        "hq_mismatch": sorted(hq_mismatch),
        "dc_mismatch": sorted(dc_mismatch),
        "missing": sorted(missing),
    }


def _report(result: dict) -> None:
    titles = {
        "unmatched": "Catalogue providers not in registry",
        "hq_mismatch": "HQ mismatch (provider, registry, catalogue)",
        "dc_mismatch": "Datacenter mismatch (provider, registry, catalogue)",
        "missing": "Registry providers absent from catalogue",
    }
    for key, title in titles.items():
        print(f"{title}:")
        if not result[key]:
            print("  none")
        for row in result[key]:
            print(f"  {row}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Offline OpenRouter registry drift check")
    ap.add_argument("--from-file", required=True, help="saved /api/v1/providers JSON")
    ap.add_argument("--registry", default=None, help="registry root dir (default: shipped)")
    args = ap.parse_args(argv)
    try:
        with open(args.from_file, encoding="utf-8") as f:
            catalogue = json.load(f)
    except (OSError, ValueError) as e:
        print(f"error: cannot read catalogue: {e}", file=sys.stderr)
        return 2
    if not isinstance(catalogue, dict) or not isinstance(catalogue.get("data"), list):
        print("error: catalogue has no 'data' list", file=sys.stderr)
        return 2
    try:
        registry = Registry.load(args.registry)
    except Exception as e:  # bad registry dir / TOML
        print(f"error: cannot load registry: {e}", file=sys.stderr)
        return 2
    result = drift(catalogue, registry)
    _report(result)
    return 0 if not any(result.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
