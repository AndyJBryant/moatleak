import collections, pytest
from moatleak.readers.hermes import HermesLogReader
from moatleak.readers.claude_code import ClaudeCodeReader

pytestmark = pytest.mark.acceptance


def test_hermes_log_matches_oracle(snapshot):
    home, gt = snapshot
    rows = list(HermesLogReader().iter_rows(home))
    assert len(rows) == gt["hermes_calls"]
    served = collections.Counter(r.served_by_raw or ("Anthropic" if r.endpoint == "api.anthropic.com" else "UNRECORDED") for r in rows)
    assert dict(served) == gt["served_by"]


def test_claude_code_matches_oracle(snapshot):
    home, gt = snapshot
    rows = list(ClaudeCodeReader().iter_rows(home))
    assert len(rows) == gt["claude_code_requests"]
    assert sum(r.reported_geo == "not_available" for r in rows) == gt["claude_code_withheld"]


def test_iter_content_counts_and_keys(snapshot):
    from moatleak.readers.hermes import HermesDbReader
    home, gt = snapshot
    for reader, n_texts, n_ids in ((HermesDbReader(), 2934, 2337), (ClaudeCodeReader(), 43, 6)):
        ids = {r.row_id for r in reader.iter_rows(home)}
        out = [rid for rid, _ in reader.iter_content(home)]
        assert len(out) == n_texts
        assert len(set(out)) == n_ids
        assert set(out) <= ids
