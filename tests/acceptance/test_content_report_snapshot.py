import json
import re
import subprocess
import sys

import pytest

pytestmark = pytest.mark.acceptance


def test_content_report(snapshot, tmp_path):
    home, _ = snapshot
    out = tmp_path / "out"
    r = subprocess.run([sys.executable, "-m", "moatleak", "scan", "--scan-content", "--home", str(home),
                        "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-300:]
    html = next(out.rglob("*.html")).read_text()
    assert '<section id="content">' in html
    m = re.search(r'data-card="story-content".*?</svg>', html, re.S)
    c = json.loads((out / "summary.json").read_text())["content"]
    if any(k["conversations"] > 0 for k in c["classes"]):
        assert m and "Local regex scan; no prompt text stored or sent." in m.group(0)
    else:
        assert m is None
