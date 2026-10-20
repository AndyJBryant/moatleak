from moatleak.ledger import LedgerRow, Ledger

def test_row_id_is_stable_and_source_scoped():
    a = LedgerRow(source="hermes_log", source_ref="gen-1", ts="2026-10-01T10:00:00Z",
                  route="router", endpoint="openrouter.ai", requested_model="deepseek/deepseek-v4-flash",
                  served_by_raw="StreamLake", requests=1, evidence="observed")
    b = LedgerRow(**{**a.__dict__})
    assert a.row_id == b.row_id
    assert a.row_id != LedgerRow(**{**a.__dict__, "source": "claude_code"}).row_id

def test_upsert_is_idempotent(tmp_path):
    led = Ledger(tmp_path / "l.db")
    row = LedgerRow(source="x", source_ref="1", ts="2026-10-01", route="direct",
                    endpoint="api.anthropic.com", requested_model="m", served_by_raw=None)
    led.add([row, row]); led.add([row])
    assert led.count() == 1
    assert list(led.rows())[0].endpoint == "api.anthropic.com"


def test_classifications_roundtrip_and_upsert(tmp_path):
    led = Ledger(tmp_path / "l.db")
    items = [("r1", "1", "credential", "rule", 1.0), ("r1", "1", "financial", "rule", 1.0),
             ("r2", "0", "legal", "rule", 1.0)]
    led.add_classifications(items)
    led.add_classifications(items)
    assert led.classifications() == {"r1": {"credential", "financial"}, "r2": {"legal"}}
    assert led.classifications("1") == {"r1": {"credential", "financial"}}
    n = led.db.execute("SELECT COUNT(*) FROM classifications").fetchone()[0]
    assert n == 3


def test_classifications_table_has_no_text_column(tmp_path):
    led = Ledger(tmp_path / "l.db")
    cols = [r[1] for r in led.db.execute("PRAGMA table_info(classifications)")]
    assert cols == ["row_id", "taxonomy_version", "category", "method", "confidence"]
