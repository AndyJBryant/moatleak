"""Text-level checks on .github/workflows/release.yml (no YAML parser in the repo)."""
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release.yml"


def _text() -> str:
    assert WORKFLOW.is_file(), "release.yml is missing"
    return WORKFLOW.read_text(encoding="utf-8")


def test_exists():
    assert _text().strip()


def test_id_token_write_exactly_twice():
    assert _text().count("id-token: write") == 2


def test_no_stored_credentials():
    text = _text().lower()
    forbidden = ["secrets" + ".", "pass" + "word", "api-" + "tok" + "en", "api_" + "tok" + "en"]
    for word in forbidden:
        assert word not in text, word


def test_uses_pypi_publish_action():
    assert "pypa/gh-action-pypi-publish@release/v1" in _text()


def test_both_environments_present():
    text = _text()
    assert "name: pypi" in text
    assert "name: testpypi" in text


def test_testpypi_repository_url():
    assert "repository-url: https://test.pypi.org/legacy/" in _text()


def test_pypi_job_gated_on_release_event():
    assert "if: github.event_name == 'release'" in _text()


def test_testpypi_job_gated_on_dispatch():
    assert "if: github.event_name == 'workflow_dispatch'" in _text()


def test_tag_check_present():
    text = _text()
    assert 'test "${GITHUB_REF_NAME}" = "v${v}"' in text
