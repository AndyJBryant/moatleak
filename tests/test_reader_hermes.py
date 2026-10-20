from pathlib import Path
from moatleak.readers.hermes import HermesLogReader

FIX = Path(__file__).parent / "fixtures" / "hermes"


def test_parses_api_calls():
    rows = list(HermesLogReader(root=FIX).iter_rows(None))
    assert len(rows) == 4
    a, b, c, d = rows
    assert (a.served_by_raw, a.route, a.endpoint, a.evidence) == ("StreamLake", "router", "openrouter.ai", "observed")
    assert b.served_by_raw == "Baidu" and b.input_tokens == 6555
    assert c.served_by_raw is None and c.evidence == "unknown"
    assert (d.endpoint, d.route, d.served_by_raw, d.evidence) == ("api.anthropic.com", "direct", None, "rule")
    assert a.source_ref == "gen-1790773241-AAAA" and a.session_ref.startswith("cron_")


def test_rotation_file_selection_and_order(tmp_path):
    """Test: numeric rotation ordering, filtering, and streaming."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    
    # Create synthetic API call lines in fixture shape, distinct IDs, different timestamps
    base_line = "2026-10-01 10:00:41,001 INFO [cron_abc_20261001_100000] agent.conversation_loop: API call #1: model=deepseek/deepseek-v4-flash provider=openrouter in=100 out=10 total=110 latency=1.0s id={} upstream=Baidu"
    
    # Write agent.log.10 (oldest rotation, should be read first)
    (logs_dir / "agent.log.10").write_text(base_line.format("gen-1790000001-AAAA") + "\n")
    
    # Write agent.log.2
    (logs_dir / "agent.log.2").write_text(base_line.format("gen-1790000002-BBBB") + "\n")
    
    # Write agent.log (current, should be read last)
    (logs_dir / "agent.log").write_text(base_line.format("gen-1790000003-CCCC") + "\n")
    
    # Write agent.log.gz (should be ignored)
    (logs_dir / "agent.log.gz").write_text(base_line.format("gen-1790000004-DDDD") + "\n")
    
    rows = list(HermesLogReader(root=tmp_path).iter_rows(None))
    
    # Should have 3 rows (ignoring .gz), in order: .10, .2, base
    assert len(rows) == 3
    assert rows[0].source_ref == "gen-1790000001-AAAA"  # from .10
    assert rows[1].source_ref == "gen-1790000002-BBBB"  # from .2
    assert rows[2].source_ref == "gen-1790000003-CCCC"  # from .log


def test_dedupe_call_id_first_occurrence_wins(tmp_path):
    """Test: same call id in multiple files yields exactly once (first occurrence)."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    
    base_line = "2026-10-01 10:00:41,001 INFO [cron_abc_20261001_100000] agent.conversation_loop: API call #1: model=deepseek/deepseek-v4-flash provider=openrouter in=100 out=10 total=110 latency=1.0s id=gen-1790000001-AAAA upstream=Baidu"
    other_line = "2026-10-01 10:00:42,001 INFO [cron_abc_20261001_100000] agent.conversation_loop: API call #1: model=deepseek/deepseek-v4-flash provider=openrouter in=200 out=20 total=220 latency=1.1s id=gen-1790000002-BBBB upstream=StreamLake"
    
    # Write agent.log.1 (older rotation) with gen-1790000001-AAAA
    (logs_dir / "agent.log.1").write_text(base_line + "\n")
    
    # Write agent.log (current) with same id + different id
    (logs_dir / "agent.log").write_text(base_line + "\n" + other_line + "\n")
    
    rows = list(HermesLogReader(root=tmp_path).iter_rows(None))
    
    # Should have 2 rows total: gen-1790000001-AAAA (from .1, first) and gen-1790000002-BBBB (from .log)
    assert len(rows) == 2
    assert rows[0].source_ref == "gen-1790000001-AAAA"
    assert rows[0].served_by_raw == "Baidu"  # from .1, not overwritten by .log
    assert rows[1].source_ref == "gen-1790000002-BBBB"
    assert rows[1].served_by_raw == "StreamLake"


def test_log_reader_iter_content_is_empty():
    from moatleak.readers.hermes import HermesLogReader
    assert list(HermesLogReader().iter_content(None)) == []
