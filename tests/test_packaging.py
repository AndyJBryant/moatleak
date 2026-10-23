import re
import tomllib
from pathlib import Path

import moatleak

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_version_matches_package():
    assert PYPROJECT["project"]["version"] == moatleak.__version__


def test_no_runtime_dependencies_and_dev_extra_is_pytest_only():
    assert PYPROJECT["project"]["dependencies"] == []
    dev = PYPROJECT["project"]["optional-dependencies"]["dev"]
    assert len(dev) == 1 and dev[0].startswith("pytest")


def test_licence_files_declared_and_present():
    files = PYPROJECT["project"]["license-files"]
    assert "LICENSE" in files and "LICENSE-DATA" in files
    for name in files:
        assert (ROOT / name).is_file()
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").lstrip().startswith("Apache License")
    data = (ROOT / "LICENSE-DATA").read_text(encoding="utf-8")
    assert "Attribution 4.0 International" in data
    assert "src/moatleak/data/" in data


def test_version_is_final_release_0_1_0():
    v = PYPROJECT["project"]["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", v)
    assert v == "0.1.0" == moatleak.__version__


def test_project_urls_exact():
    assert PYPROJECT["project"]["urls"] == {
        "Homepage": "https://moatleak.ai/",
        "Source": "https://github.com/AndyJBryant/moatleak",
        "Issues": "https://github.com/AndyJBryant/moatleak/issues",
    }


def test_keywords_have_no_openrouter():
    assert "openrouter" not in PYPROJECT["project"]["keywords"]
