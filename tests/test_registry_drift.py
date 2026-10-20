"""Tests for tools/registry_drift.py (offline registry drift check)."""
import ast
import importlib.util
import json
import pathlib

import pytest
from moatleak.registry import Registry

ROOT = pathlib.Path(__file__).parent.parent
TOOLS = ROOT / "tools"
BANNED = {"socket", "urllib", "http", "ssl", "requests", "httpx", "aiohttp", "ftplib", "smtplib"}

ALPHA = '''id = "alpha"
display_name = "Alpha Labs"
openrouter_names = ["Alpha"]
hq = { country = "US" }
serving_regions = [{ region = "US", basis = "openrouter_api" }, { region = "EU", basis = "vendor_docs" }]
'''
BETA = '''id = "beta"
display_name = "Beta"
hq = { country = "unknown" }
serving_regions = []
'''


def _load_tool():
    spec = importlib.util.spec_from_file_location("registry_drift", TOOLS / "registry_drift.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def tool():
    return _load_tool()


@pytest.fixture
def reg_dir(tmp_path):
    root = tmp_path / "reg"
    (root / "providers").mkdir(parents=True)
    (root / "providers" / "alpha.toml").write_text(ALPHA)
    (root / "providers" / "beta.toml").write_text(BETA)
    (root / "routes.toml").write_text('version = "2026.10.07"\n')
    (root / "regimes.toml").write_text("# empty\n")
    return root


@pytest.fixture
def registry(reg_dir):
    return Registry.load(reg_dir)


def entry(name, hq=None, dcs=None):
    return {"name": name, "slug": name.lower(), "headquarters": hq, "datacenters": dcs}


def test_no_drift(tool, registry):
    cat = {"data": [entry("Alpha", "US", ["US"]), entry("Beta", "FR", ["DE"])]}
    assert tool.drift(cat, registry) == {
        "unmatched": [], "hq_mismatch": [], "dc_mismatch": [], "missing": []}


def test_unmatched(tool, registry):
    cat = {"data": [entry("Alpha"), entry("Zeta"), entry("Gamma")]}
    assert tool.drift(cat, registry)["unmatched"] == ["Gamma", "Zeta"]


def test_hq_mismatch_and_unknown_registry_hq_skipped(tool, registry):
    cat = {"data": [entry("Alpha", "CN"), entry("Beta", "CN")]}
    assert tool.drift(cat, registry)["hq_mismatch"] == [("alpha", "US", "CN")]


def test_dc_mismatch(tool, registry):
    cat = {"data": [entry("Alpha", None, ["SG", "CN"]), entry("Beta", None, ["US"])]}
    assert tool.drift(cat, registry)["dc_mismatch"] == [("alpha", ["US"], ["CN", "SG"])]


def test_dc_set_equality_ignores_order_and_dupes(tool, registry):
    cat = {"data": [entry("Alpha", None, ["US", "US"])]}
    assert tool.drift(cat, registry)["dc_mismatch"] == []


def test_null_or_empty_hq_dcs_ignored(tool, registry):
    cat = {"data": [entry("Alpha", None, None), entry("Beta", None, [])]}
    d = tool.drift(cat, registry)
    assert d["hq_mismatch"] == [] and d["dc_mismatch"] == []


def test_missing(tool, registry):
    d = tool.drift({"data": [entry("Beta")]}, registry)
    assert d["missing"] == ["alpha"]


def _write(tmp_path, obj, name="cat.json"):
    p = tmp_path / name
    p.write_text(json.dumps(obj))
    return p


def test_main_clean(tool, tmp_path, reg_dir, capsys):
    p = _write(tmp_path, {"data": [entry("Alpha", "US", ["US"])]})
    assert tool.main(["--from-file", str(p), "--registry", str(reg_dir)]) == 0
    assert "none" in capsys.readouterr().out


def test_main_drift(tool, tmp_path, reg_dir, capsys):
    p = _write(tmp_path, {"data": [entry("Alpha", "CN", ["US"]), entry("Zeta")]})
    assert tool.main(["--from-file", str(p), "--registry", str(reg_dir)]) == 1
    out = capsys.readouterr().out
    assert "Zeta" in out and "alpha" in out


def test_main_missing_file(tool, tmp_path, reg_dir, capsys):
    rc = tool.main(["--from-file", str(tmp_path / "nope.json"), "--registry", str(reg_dir)])
    assert rc == 2
    assert capsys.readouterr().err.strip()


def test_main_invalid_json(tool, tmp_path, reg_dir, capsys):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    assert tool.main(["--from-file", str(p), "--registry", str(reg_dir)]) == 2
    assert capsys.readouterr().err.strip()


def test_main_no_data_list(tool, tmp_path, reg_dir):
    p = _write(tmp_path, {"data": "x"})
    assert tool.main(["--from-file", str(p), "--registry", str(reg_dir)]) == 2


def test_from_file_is_required(tool):
    with pytest.raises(SystemExit):
        tool.main([])


def _imports(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module.split(".")[0]


def test_tools_have_no_network_imports():
    files = list(TOOLS.glob("*.py"))
    assert files
    for py in files:
        assert not (BANNED & set(_imports(py))), py.name
