from __future__ import annotations
import re
import sqlite3
import contextlib
from datetime import datetime, timezone
from pathlib import Path
from moatleak.ledger import LedgerRow

LINE = re.compile(
    r"^(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ \w+ (?:\[(?P<sess>[^\]]+)\] )?"
    r"agent\.conversation_loop: API call #\d+: model=(?P<model>\S+) provider=(?P<prov>\S+) "
    r"in=(?P<inp>\d+) out=(?P<out>\d+).*? id=(?P<id>\S+)(?: upstream=(?P<up>.+?))?$")

ENDPOINTS = {"openrouter": ("openrouter.ai", "router"),
             "anthropic": ("api.anthropic.com", "direct")}


class HermesLogReader:
    name = "hermes_log"

    def __init__(self, root: Path | None = None):
        self.root = root

    def _dir(self, home):
        return (self.root or Path(home) / ".hermes") / "logs"

    def detect(self, home):
        return self._dir(home).exists()

    def _get_sorted_files(self, log_dir):
        """Get agent.log* files, filter to numeric rotations + base, sort oldest-first."""
        # Match agent.log and agent.log.<digits> only
        files = []
        for f in log_dir.glob("agent.log*"):
            name = f.name
            if name == "agent.log":
                files.append((-1, f))  # base file, read last (sort order: -1 < any positive)
            else:
                # Extract numeric suffix from agent.log.N
                suffix = name[len("agent.log."):]
                if suffix.isdigit():
                    files.append((int(suffix), f))
                # else: ignore agent.log.gz, agent.log.bak, etc.
        # Sort: highest numeric first (oldest rotation), then base (-1)
        files.sort(reverse=True)
        return [f for _, f in files]

    def iter_rows(self, home):
        files = self._get_sorted_files(self._dir(home))
        seen = set()
        for f in files:
            # Stream lines instead of reading entire file
            with open(f, encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    line = line.rstrip('\n\r')  # strip newline before matching
                    m = LINE.match(line)
                    if not m:
                        continue
                    call_id = m["id"]
                    # Dedupe: skip if we've already seen this call id
                    if call_id in seen:
                        continue
                    seen.add(call_id)
                    endpoint, route = ENDPOINTS.get(m["prov"], (m["prov"], "unknown"))
                    up = m["up"].strip() if m["up"] else None
                    evidence = "observed" if up else ("rule" if route == "direct" else "unknown")
                    # Note: log timestamps are local time; v1 treats them as UTC
                    ts = datetime.strptime(m["ts"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).isoformat()
                    yield LedgerRow(source=self.name, source_ref=call_id, ts=ts, route=route,
                                    endpoint=endpoint, requested_model=m["model"], served_by_raw=up,
                                    input_tokens=int(m["inp"]), output_tokens=int(m["out"]),
                                    evidence=evidence, session_ref=m["sess"])

    def iter_content(self, home):
        return iter(())  # logs contain no prompt text


class HermesDbReader:
    """Reads aggregated usage from Hermes state.db (WAL-mode SQLite)."""
    name = "hermes_db"

    def __init__(self, root: Path | None = None):
        self.root = root

    def _db_path(self, home):
        return (self.root or (Path(home) / ".hermes")) / "state.db"

    def detect(self, home):
        return self._db_path(home).exists()

    def iter_rows(self, home):
        db_path = self._db_path(home).resolve()  # Absolute path for URI
        # Use immutable mode to prevent creation of -wal/-shm files
        conn_str = f"file:{db_path}?mode=ro&immutable=1"
        with contextlib.closing(sqlite3.connect(conn_str, uri=True)) as conn:
            cursor = conn.execute(
                "SELECT session_id, model, billing_provider, billing_base_url, billing_mode, task, "
                "api_call_count, input_tokens, output_tokens, first_seen FROM session_model_usage"
            )
            for row in cursor:
                (session_id, model, billing_provider, billing_base_url, billing_mode, task,
                 api_call_count, input_tokens, output_tokens, first_seen) = row

                # Extract endpoint from billing_base_url
                m = re.match(r"https?://([^/]+)", billing_base_url)
                endpoint = m.group(1) if m else (billing_provider or "unknown")

                # Determine route
                if billing_provider == "openrouter":
                    route = "router"
                elif billing_provider == "anthropic":
                    route = "direct"
                else:
                    route = "unknown"

                # Convert first_seen to ISO-8601 UTC
                ts = datetime.fromtimestamp(first_seen, timezone.utc).isoformat()

                # Create source_ref from 6-part primary key
                source_ref = "|".join([session_id, model, billing_provider, billing_base_url, billing_mode, task])

                # task is None if empty string, else keep the value
                task_val = task if task else None

                yield LedgerRow(
                    source=self.name,
                    source_ref=source_ref,
                    ts=ts,
                    route=route,
                    endpoint=endpoint,
                    requested_model=model,
                    served_by_raw=None,
                    requests=api_call_count,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    evidence="aggregate",
                    session_ref=session_id,
                    task=task_val
                )

    def iter_content(self, home):
        """Yield (row_id, text) for user messages, keyed to the session's earliest ledger row."""
        if not self.detect(home):
            return
        rep = {}  # session_id -> (ts, source_ref, row_id)
        for r in self.iter_rows(home):
            k = (r.ts, r.source_ref)
            if r.session_ref not in rep or k < rep[r.session_ref][:2]:
                rep[r.session_ref] = (r.ts, r.source_ref, r.row_id)
        if not rep:
            return
        db_path = self._db_path(home).resolve()
        with contextlib.closing(sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)) as conn:
            for sid, content in conn.execute(
                    "SELECT session_id, content FROM messages WHERE role = 'user' ORDER BY id"):
                if content and sid in rep:
                    yield rep[sid][2], content
