"""Export script, toolbar, project URL, payload/href hardening."""
import json
import re
import shutil
import subprocess

import pytest

from moatleak.report.render import CTA_URL, PROJECT_URL, render
from tests.test_report_payload import _build


def _script(h):
    m = re.search(r'<script id="moatleak-export">(.*?)</script>', h, re.S)
    assert m
    return m.group(1)


def test_export_script_present():
    h = render(_build()[0])
    js = _script(h)
    assert not re.search(r"Task \d", js) and len(js) > 1500
    assert "card-tools" in h and "selftest-result" in js and "toBlob" in js
    assert "http" not in js
    assert h.count('data-project-url="https://horizenlabs.io/"') == 1
    assert re.search(r'<body[^>]* data-project-url="' + re.escape(PROJECT_URL) + '"', h)
    assert PROJECT_URL == "https://horizenlabs.io/"
    assert "data-project-url" not in json.dumps(_build()[0])


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_export_script_parses(tmp_path):
    f = tmp_path / "x.js"
    f.write_text(_script(render(_build()[0])))
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_payload_lt_escaped():
    p = _build()[0]
    base = render(p).count("<script")
    p["models"] = [{"slug": "<!--<script>"}]
    p["headlines"][0]["text"] = "<!--<script>"
    h = render(p)
    assert h.count("<script") == base
    m = re.search(r'<script type="application/json" id="moatleak-payload">(.*?)</script>', h, re.S)
    assert "<" not in m.group(1)
    assert json.loads(m.group(1)) == p


def test_hostile_source_not_linked():
    p = _build()[0]
    p["providers"][0]["parent"] = "Par"
    p["providers"][0]["parent_source"] = "javascript:alert(1)"
    for r in p["footprint"]["regimes"]:
        r["source"] = "javascript:alert(1)"
    h = render(p)
    assert 'href="javascript' not in h and "javascript:alert(1)" not in re.sub(
        r'<script type="application/json".*?</script>', "", h, flags=re.S)
    assert "Par" in h


def test_good_source_linked_with_noopener():
    h = render(_build()[0])
    for m in re.finditer(r'<a href="https?://[^"]*"[^>]*>(?:source|[^<]*)</a>', h):
        if CTA_URL in m.group(0):
            continue
        assert 'rel="noopener"' in m.group(0), m.group(0)


def test_card_count_includes_story_content():
    p = _build()[0]
    base = render(p).count('data-card="')
    p["content"] = {"taxonomy_version": "1", "method": "rule", "scanned_conversations": 5,
                    "earlier_scanned_conversations": 0,
                    "classes": [{"category": "credential", "label": "Credentials", "conversations": 1,
                                 "earlier_conversations": 0,
                                 "companies": [{"name": "Alpha", "country": "US", "conversations": 1}]}]}
    assert render(p).count('data-card="') == base + 1
