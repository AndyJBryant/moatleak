import csv
import json

import pytest
from moatleak.cli import main

pytestmark = pytest.mark.acceptance


def _listing(home):
    return sorted((str(p.relative_to(home)), p.stat().st_size, p.stat().st_mtime_ns)
                  for p in home.rglob("*"))


def test_cli_scan_snapshot(snapshot, tmp_path):
    home, gt = snapshot
    before = _listing(home)
    out = tmp_path / "out"
    assert main(["scan", "--home", str(home), "--out", str(out)]) == 0
    assert _listing(home) == before
    p = json.loads((out / "summary.json").read_text())
    assert p["total_requests"] == 1174
    assert p["period"] == ["2026-09-22", "2026-10-07"]
    assert (p["counts"]["companies"], p["counts"]["parent_groups"], p["counts"]["countries"]) == (10, 8, 2)
    cs = p["footprint"]["country_share"]
    assert round(cs["US"] * 100) == 63 and round(cs["CN"] * 100) == 36
    assert round(p["footprint"]["undisclosed_share"] * 100) == 1
    growth = [h for h in p["headlines"] if h["kind"] == "growth"]
    assert growth and growth[0]["text"] == "7 new companies joined your network in 9 days."
    assert p["fragmentation"]["multi_provider_sessions"] == 57
    assert p["fragmentation"]["max_session_spread"]["n_providers"] == 3
    assert sum(w["requests"] for w in p["withheld"]) == gt["claude_code_withheld"]
    with open(out / "ledger.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1162 + 2420 + 220
    assert not [r for r in rows if r["route"] == "subscription"]
    assert {r["route"] for r in rows if r["source"] == "claude_code"} == {"direct"}
    assert sum(r["source"] == "claude_code" for r in rows) == 220
    assert "<svg" in (out / "report.html").read_text()


def test_cli_scan_content_snapshot(snapshot, tmp_path):
    home, gt = snapshot
    before = _listing(home)
    out = tmp_path / "out"
    assert main(["scan", "--scan-content", "--home", str(home), "--out", str(out)]) == 0
    assert _listing(home) == before
    p = json.loads((out / "summary.json").read_text())
    assert p["content"] is not None and p["content"]["scanned_conversations"] > 0
    assert p["total_requests"] == 1174 and p["counts"]["companies"] == 10
    assert sum(w["requests"] for w in p["withheld"]) == gt["claude_code_withheld"]
