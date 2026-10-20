from __future__ import annotations
from pathlib import Path
from typing import Iterator, Protocol
from moatleak.ledger import LedgerRow


class Reader(Protocol):
    name: str
    def detect(self, home: Path) -> bool: ...
    def iter_rows(self, home: Path) -> Iterator[LedgerRow]: ...
    # Content is a separate, explicit path. Never called unless --scan-content.
    def iter_content(self, home: Path) -> Iterator[tuple[str, str]]: ...  # (row_id, text)


def all_readers() -> list[Reader]:
    from .hermes import HermesLogReader, HermesDbReader
    from .claude_code import ClaudeCodeReader
    return [HermesLogReader(), HermesDbReader(), ClaudeCodeReader()]
