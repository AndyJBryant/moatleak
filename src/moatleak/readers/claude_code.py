from __future__ import annotations
import json
from pathlib import Path
from moatleak.ledger import LedgerRow


def _int(v):
    """Coerce value to int; return 0 if null or non-int."""
    return v if isinstance(v, int) else 0


class ClaudeCodeReader:
    name = "claude_code"

    def __init__(self, root: Path | None = None):
        self.root = root

    def _dir(self, home):
        return (self.root or Path(home) / ".claude") / "projects"

    def detect(self, home):
        return self._dir(home).exists()

    def iter_rows(self, home):
        """Parse Claude Code JSONL files.
        
        Deduplicates by requestId (keeps LAST line), aggregates tokens.
        Route note: all calls are route 'direct' (endpoint api.anthropic.com);
        the auth mode is not recorded per call.
        """
        last = {}
        # Iterate over all *.jsonl files in sorted order for determinism
        for f in sorted(self._dir(home).rglob("*.jsonl")):
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        # Malformed JSON: skip
                        continue
                    # Skip non-dict JSON
                    if not isinstance(d, dict):
                        continue
                    # Only process assistant lines with usage, requestId, and timestamp
                    m = d.get("message")
                    if isinstance(m, dict) and m.get("usage") and d.get("requestId") and d.get("timestamp"):
                        # Keep the LAST line for each requestId
                        last[d["requestId"]] = (d, m)
        
        # Yield deduped rows
        for rid, (d, m) in last.items():
            u = m["usage"]
            yield LedgerRow(
                source=self.name,
                source_ref=rid,
                ts=d["timestamp"],
                route="direct",
                endpoint="api.anthropic.com",
                requested_model=m.get("model", "?"),
                served_by_raw="Anthropic",
                input_tokens=(
                    _int(u.get("input_tokens"))
                    + _int(u.get("cache_read_input_tokens"))
                    + _int(u.get("cache_creation_input_tokens"))
                ),
                output_tokens=_int(u.get("output_tokens")),
                reported_geo=u.get("inference_geo"),
                evidence="observed",
                session_ref=d.get("sessionId"),
            )

    def iter_content(self, home):
        """Yield (row_id, text) for user prompts, keyed to the session's earliest ledger row."""
        if not self.detect(home):
            return
        rep = {}  # sessionId -> (ts, source_ref, row_id)
        for r in self.iter_rows(home):
            k = (r.ts, r.source_ref)
            if r.session_ref not in rep or k < rep[r.session_ref][:2]:
                rep[r.session_ref] = (r.ts, r.source_ref, r.row_id)
        if not rep:
            return
        for f in sorted(self._dir(home).rglob("*.jsonl")):
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(d, dict) or d.get("type") != "user":
                        continue
                    if d.get("isMeta") or "toolUseResult" in d:
                        continue
                    m = d.get("message")
                    if not isinstance(m, dict) or m.get("role") != "user":
                        continue
                    sid = d.get("sessionId")
                    if sid not in rep:
                        continue
                    c = m.get("content")
                    if isinstance(c, list):
                        c = "\n".join(b.get("text") or "" for b in c
                                      if isinstance(b, dict) and b.get("type") == "text"
                                      and isinstance(b.get("text"), str))
                    if isinstance(c, str) and c.strip():
                        yield rep[sid][2], c
