from __future__ import annotations
import hashlib
import sqlite3
import dataclasses
from dataclasses import dataclass
from pathlib import Path

# "subscription" is legacy: old ledger.db files may still hold such rows.
ROUTES = {"router", "direct", "subscription", "unknown"}
EVIDENCE = {"observed", "aggregate", "rule", "unknown"}


@dataclass
class LedgerRow:
    source: str                 # hermes_log | hermes_db | claude_code
    source_ref: str             # call id / requestId / composite key — never content
    ts: str                     # ISO-8601 UTC (date-only allowed for aggregates)
    route: str                  # see ROUTES
    endpoint: str               # host, e.g. "openrouter.ai", "api.anthropic.com"
    requested_model: str
    served_by_raw: str | None   # provider name exactly as reported, None if not reported
    requests: int = 1
    input_tokens: int = 0
    output_tokens: int = 0
    reported_geo: str | None = None   # e.g. "us", "not_available"
    evidence: str = "unknown"
    session_ref: str | None = None
    task: str | None = None

    @property
    def row_id(self) -> str:
        return hashlib.sha256(f"{self.source}|{self.source_ref}".encode()).hexdigest()[:16]


_FIELDS = [f.name for f in dataclasses.fields(LedgerRow)]


class Ledger:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        cols = ", ".join(_FIELDS)
        self.db.execute(f"CREATE TABLE IF NOT EXISTS ledger (row_id TEXT PRIMARY KEY, {cols})")
        self.db.execute("""CREATE TABLE IF NOT EXISTS classifications (
            row_id TEXT, taxonomy_version TEXT, category TEXT, method TEXT,
            confidence REAL, PRIMARY KEY (row_id, taxonomy_version, category, method))""")

    def add(self, rows):
        q = f"INSERT OR REPLACE INTO ledger VALUES (?, {', '.join('?' * len(_FIELDS))})"
        self.db.executemany(q, [(r.row_id, *(getattr(r, f) for f in _FIELDS)) for r in rows])
        self.db.commit()

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]

    def rows(self):
        for rec in self.db.execute(f"SELECT {', '.join(_FIELDS)} FROM ledger ORDER BY ts"):
            yield LedgerRow(*rec)

    def add_classifications(self, items):
        self.db.executemany("INSERT OR REPLACE INTO classifications VALUES (?, ?, ?, ?, ?)", list(items))
        self.db.commit()

    def classifications(self, taxonomy_version=None):
        q, a = "SELECT row_id, category FROM classifications", ()
        if taxonomy_version is not None:
            q, a = q + " WHERE taxonomy_version = ?", (taxonomy_version,)
        out: dict[str, set[str]] = {}
        for rid, cat in self.db.execute(q, a):
            out.setdefault(rid, set()).add(cat)
        return out
