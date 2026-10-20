from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import sqlite3
import pytest
from moatleak.readers.hermes import HermesDbReader


def test_detect_finds_db(tmp_path):
    """Test detect() returns True when state.db exists."""
    # When root=tmp_path, HermesDbReader looks for (tmp_path or home/.hermes) / state.db
    # which becomes tmp_path / state.db
    db_path = tmp_path / "state.db"
    db_path.touch()
    
    reader = HermesDbReader(root=tmp_path)
    assert reader.detect(None) is True


def test_detect_returns_false_when_missing(tmp_path):
    """Test detect() returns False when state.db doesn't exist."""
    reader = HermesDbReader(root=tmp_path)
    assert reader.detect(None) is False


def test_iter_rows_reads_db_without_creating_wal_files(tmp_path):
    """Test: iter_rows reads DB in read-only mode without creating -wal/-shm files."""
    # When root=tmp_path, HermesDbReader looks for (tmp_path or home/.hermes) / state.db
    db_path = tmp_path / "state.db"
    
    # Create and populate DB with WAL mode
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE session_model_usage (
            session_id TEXT, model TEXT, billing_provider TEXT, billing_base_url TEXT,
            billing_mode TEXT, task TEXT, api_call_count INT, input_tokens INT, output_tokens INT,
            cache_read_tokens INT, cache_write_tokens INT, reasoning_tokens INT,
            estimated_cost_usd REAL, actual_cost_usd REAL, cost_status TEXT, cost_source TEXT,
            first_seen REAL, last_seen REAL,
            PRIMARY KEY (session_id, model, billing_provider, billing_base_url, billing_mode, task)
        )
    """)
    
    # Insert test rows
    rows = [
        ('sess_a', 'deepseek/deepseek-v4-flash', 'openrouter', 'https://openrouter.ai/api/v1', '',
         '', 5, 100, 10, 0, 0, 0, 0.5, 0.5, 'cached', 'mock', 1790000000.5, 1790000010.0),
        ('sess_b', 'claude-opus-5-5', 'anthropic', 'https://api.anthropic.com', '',
         'title_generation', 1, 50, 5, 0, 0, 0, 0.1, 0.1, 'paid', 'mock', 1790000000.5, 1790000005.0),
        ('sess_a', 'deepseek/deepseek-v4-flash', 'openrouter', 'https://openrouter.ai/api/v1/', '',
         '', 2, 80, 8, 0, 0, 0, 0.4, 0.4, 'cached', 'mock', 1790000000.5, 1790000015.0),
    ]
    
    for row in rows:
        conn.execute(
            "INSERT INTO session_model_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            row
        )
    conn.commit()
    conn.close()
    
    # Now read with HermesDbReader and verify no WAL files are created
    reader = HermesDbReader(root=tmp_path)
    result_rows = list(reader.iter_rows(None))
    
    # Assertions on rows
    assert len(result_rows) == 3
    assert all(r.evidence == "aggregate" for r in result_rows)
    assert all(r.served_by_raw is None for r in result_rows)
    assert result_rows[0].requests == 5
    assert result_rows[1].requests == 1
    assert result_rows[2].requests == 2
    
    # Check endpoints
    endpoints = {r.endpoint for r in result_rows}
    assert endpoints == {"openrouter.ai", "api.anthropic.com"}
    
    # Check routes
    routes = {r.route for r in result_rows}
    assert routes == {"router", "direct"}
    
    # Check timestamps (all from first_seen=1790000000.5)
    expected_ts = datetime.fromtimestamp(1790000000.5, timezone.utc).isoformat()
    assert all(r.ts == expected_ts for r in result_rows)
    
    # Check tasks
    assert result_rows[0].task is None
    assert result_rows[1].task == "title_generation"
    assert result_rows[2].task is None
    
    # Check source_refs (3 distinct ones from 6-part primary key)
    source_refs = {r.source_ref for r in result_rows}
    assert len(source_refs) == 3
    
    # Check row_ids (3 distinct ones)
    row_ids = {r.row_id for r in result_rows}
    assert len(row_ids) == 3
    
    # Critical: verify no -wal or -shm files were created
    assert not (tmp_path / "state.db-wal").exists()
    assert not (tmp_path / "state.db-shm").exists()


def test_iter_content_empty_when_no_db(tmp_path):
    """iter_content yields nothing when state.db is absent."""
    reader = HermesDbReader()
    assert list(reader.iter_content(tmp_path)) == []


def test_iter_rows_robust_to_column_reordering(tmp_path):
    """Regression: columns reordered + extra column doesn't break positional unpacking.
    
    This test would FAIL with SELECT * (positional unpacking would unpack wrong columns),
    but PASSES with explicit SELECT of needed columns.
    """
    db_path = tmp_path / "state.db"
    
    # Create DB with EXTRA column placed first and other columns in different order
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE session_model_usage (
            extra_col TEXT,
            session_id TEXT, 
            model TEXT, 
            billing_provider TEXT, 
            billing_base_url TEXT,
            billing_mode TEXT, 
            task TEXT, 
            api_call_count INT, 
            input_tokens INT, 
            output_tokens INT,
            cache_read_tokens INT, 
            cache_write_tokens INT, 
            reasoning_tokens INT,
            estimated_cost_usd REAL, 
            actual_cost_usd REAL, 
            cost_status TEXT, 
            cost_source TEXT,
            first_seen REAL, 
            last_seen REAL,
            PRIMARY KEY (session_id, model, billing_provider, billing_base_url, billing_mode, task)
        )
    """)
    
    # Insert test row with extra_col value
    conn.execute(
        "INSERT INTO session_model_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ('extra_value', 'sess_x', 'gpt-4', 'anthropic', 'https://api.anthropic.com', '',
         'test_task', 3, 200, 20, 0, 0, 0, 1.0, 1.0, 'paid', 'mock', 1790000000.5, 1790000010.0)
    )
    conn.commit()
    conn.close()
    
    # Read with HermesDbReader - should correctly extract only needed columns by name
    reader = HermesDbReader(root=tmp_path)
    result_rows = list(reader.iter_rows(None))
    
    # Assertions: verify correct values despite reordering
    assert len(result_rows) == 1
    assert result_rows[0].session_ref == 'sess_x'
    assert result_rows[0].requested_model == 'gpt-4'
    assert result_rows[0].requests == 3
    assert result_rows[0].input_tokens == 200
    assert result_rows[0].output_tokens == 20
    assert result_rows[0].endpoint == 'api.anthropic.com'
    assert result_rows[0].route == 'direct'
    assert result_rows[0].task == 'test_task'
    assert result_rows[0].evidence == 'aggregate'
    
    # Verify no WAL files created
    assert not (tmp_path / "state.db-wal").exists()
    assert not (tmp_path / "state.db-shm").exists()


def _content_db(path):
    conn = sqlite3.connect(str(path))
    conn.execute("""CREATE TABLE session_model_usage (
        session_id TEXT, model TEXT, billing_provider TEXT, billing_base_url TEXT,
        billing_mode TEXT, task TEXT, api_call_count INT, input_tokens INT, output_tokens INT,
        first_seen REAL)""")
    conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp REAL)")
    u = "INSERT INTO session_model_usage VALUES (?,?,?,?,?,?,?,?,?,?)"
    conn.execute(u, ("s1", "m-late", "openrouter", "https://openrouter.ai/api", "", "", 1, 1, 1, 2000.0))
    conn.execute(u, ("s1", "m-early", "openrouter", "https://openrouter.ai/api", "", "", 1, 1, 1, 1000.0))
    conn.execute(u, ("s2", "m-x", "anthropic", "https://api.anthropic.com", "", "", 1, 1, 1, 3000.0))
    msgs = [("s1", "user", "alpha"), ("s1", "assistant", "reply"), ("s1", "tool", "toolout"),
            ("s1", "user", None), ("s1", "user", ""), ("s2", "user", "beta"),
            ("s3", "user", "orphan")]
    conn.executemany("INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,1.0)", msgs)
    conn.commit()
    conn.close()


def test_iter_content_keys_to_earliest_session_row(tmp_path):
    _content_db(tmp_path / "state.db")
    reader = HermesDbReader(root=tmp_path)
    rows = list(reader.iter_rows(None))
    ids = {r.row_id for r in rows}
    early = next(r for r in rows if r.requested_model == "m-early")
    s2 = next(r for r in rows if r.session_ref == "s2")
    out = list(reader.iter_content(None))
    assert sorted(out) == sorted([(early.row_id, "alpha"), (s2.row_id, "beta")])
    assert {i for i, _ in out} <= ids


def test_iter_content_leaves_db_dir_unchanged(tmp_path):
    _content_db(tmp_path / "state.db")
    before = sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in tmp_path.iterdir())
    list(HermesDbReader(root=tmp_path).iter_content(None))
    after = sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in tmp_path.iterdir())
    assert before == after
