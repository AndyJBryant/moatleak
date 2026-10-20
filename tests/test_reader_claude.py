from pathlib import Path
import tempfile
from moatleak.readers.claude_code import ClaudeCodeReader

FIX = Path(__file__).parent / "fixtures" / "claude"


def test_parses_claude_code_rows():
    """Test: parse Claude Code JSONL, dedupe by requestId, aggregate tokens."""
    rows = list(ClaudeCodeReader(root=FIX).iter_rows(None))
    assert len(rows) == 2
    
    # Get rows in order; determine which is req_A and req_B
    row_by_ref = {r.source_ref: r for r in rows}
    assert set(row_by_ref.keys()) == {"req_A", "req_B"}
    
    # Check common fields
    for row in rows:
        assert row.endpoint == "api.anthropic.com"
        assert row.route == "direct"
        assert row.served_by_raw == "Anthropic"
        assert row.evidence == "observed"
        assert row.source == "claude_code"
    
    # Check reported_geo set
    assert {r.reported_geo for r in rows} == {"not_available", "us"}
    
    # req_A: dedupe to LAST line, aggregate tokens
    a = row_by_ref["req_A"]
    assert a.input_tokens == 10 + 100 + 5  # 115
    assert a.output_tokens == 50
    assert a.ts == "2026-09-20T10:00:01.000Z"  # timestamp from last line
    assert a.session_ref == "00000000-0000-4000-8000-000000000001"
    assert a.requested_model == "claude-opus-5"
    assert a.reported_geo == "not_available"
    
    # req_B: single line
    b = row_by_ref["req_B"]
    assert b.input_tokens == 7
    assert b.output_tokens == 3
    assert b.ts == "2026-09-20T10:05:00.000Z"
    assert b.reported_geo == "us"


def test_detect_fixture():
    """Test: detect() returns True for fixture path."""
    assert ClaudeCodeReader(root=FIX).detect(None) is True


def test_detect_tmpdir():
    """Test: detect() returns False for missing .claude/projects."""
    with tempfile.TemporaryDirectory() as tmp:
        assert ClaudeCodeReader(root=Path(tmp)).detect(None) is False


def test_malformed_json_skipped():
    """Test: malformed (non-JSON) lines are skipped without error."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        projects_dir = tmp_path / "projects" / "p1"
        projects_dir.mkdir(parents=True)
        
        # Write a JSONL with one bad line, one good line
        jsonl_file = projects_dir / "mixed.jsonl"
        jsonl_file.write_text(
            "not valid json\n"
            '{"type": "assistant", "requestId": "req_X", "timestamp": "2026-09-20T10:00:00.000Z", "sessionId": "s1", "message": {"model": "test", "usage": {"input_tokens": 5, "output_tokens": 2, "inference_geo": "us"}}}\n'
        )
        
        rows = list(ClaudeCodeReader(root=tmp_path).iter_rows(None))
        assert len(rows) == 1
        assert rows[0].source_ref == "req_X"


def test_missing_timestamp_skipped():
    """Test: usage line without timestamp is skipped without error."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        projects_dir = tmp_path / "projects" / "p1"
        projects_dir.mkdir(parents=True)
        
        # Write a JSONL with one line missing timestamp, one good line
        jsonl_file = projects_dir / "no_ts.jsonl"
        jsonl_file.write_text(
            '{"type": "assistant", "requestId": "req_NoTS", "sessionId": "s1", "message": {"model": "test", "usage": {"input_tokens": 5, "output_tokens": 2, "inference_geo": "us"}}}\n'
            '{"type": "assistant", "requestId": "req_Good", "timestamp": "2026-09-20T10:00:00.000Z", "sessionId": "s1", "message": {"model": "test", "usage": {"input_tokens": 5, "output_tokens": 2, "inference_geo": "us"}}}\n'
        )
        
        rows = list(ClaudeCodeReader(root=tmp_path).iter_rows(None))
        assert len(rows) == 1
        assert rows[0].source_ref == "req_Good"


def test_null_tokens_coerced_to_zero():
    """Test: usage line with null token fields yields 0 without error."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        projects_dir = tmp_path / "projects" / "p1"
        projects_dir.mkdir(parents=True)
        
        # Write a JSONL with null tokens and non-int tokens
        jsonl_file = projects_dir / "null_tokens.jsonl"
        jsonl_file.write_text(
            '{"type": "assistant", "requestId": "req_Null", "timestamp": "2026-09-20T10:00:00.000Z", "sessionId": "s1", "message": {"model": "test", "usage": {"input_tokens": null, "output_tokens": "invalid", "cache_read_input_tokens": null, "cache_creation_input_tokens": 5, "inference_geo": "us"}}}\n'
        )
        
        rows = list(ClaudeCodeReader(root=tmp_path).iter_rows(None))
        assert len(rows) == 1
        assert rows[0].source_ref == "req_Null"
        assert rows[0].input_tokens == 0 + 0 + 5  # null->0, null->0, 5
        assert rows[0].output_tokens == 0  # "invalid"->0


def _w(path, lines):
    import json
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def _asst(rid, ts, sid):
    return {"type": "assistant", "sessionId": sid, "requestId": rid, "timestamp": ts,
            "message": {"role": "assistant", "model": "m", "usage": {"input_tokens": 1, "output_tokens": 1}}}


def _usr(sid, content, **extra):
    d = {"type": "user", "sessionId": sid, "message": {"role": "user", "content": content}}
    d.update(extra)
    return d


def test_iter_content_extracts_prompts_and_keys_to_earliest_row(tmp_path):
    proj = tmp_path / "projects" / "p"
    proj.mkdir(parents=True)
    _w(proj / "a.jsonl", [
        _asst("req_late", "2026-09-20T11:00:00.000Z", "sA"),
        _asst("req_early", "2026-09-20T10:00:00.000Z", "sA"),
        _usr("sA", "plain text"),
        _usr("sA", [{"type": "text", "text": "one"}, {"type": "text", "text": "two"},
                    {"type": "tool_result", "content": "zzz"}]),
        _usr("sA", "meta text", isMeta=True),
        _usr("sA", [{"type": "tool_result", "content": "zzz"}], toolUseResult={"x": 1}),
        _usr("sA", [{"type": "image", "source": {}}]),
        _usr("sA", "   "),
        _usr("sNone", "no ledger rows"),
    ])
    reader = ClaudeCodeReader(root=tmp_path)
    rows = {r.source_ref: r for r in reader.iter_rows(None)}
    out = list(reader.iter_content(None))
    rid = rows["req_early"].row_id
    assert out == [(rid, "plain text"), (rid, "one\ntwo")]
