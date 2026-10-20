from __future__ import annotations
import argparse
import csv
import dataclasses
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

from moatleak import __version__
from moatleak.content.scan import content_summary, scan_readers
from moatleak.content.tier1 import TAXONOMY_VERSION
from moatleak.findings import summarise
from moatleak.headlines import headlines
from moatleak.ledger import Ledger, LedgerRow
from moatleak.readers import all_readers
from moatleak.registry import Registry
from moatleak.report import render as report_render
from moatleak.report.payload import report_payload
from moatleak.resolve import resolve

_FIELDS = [f.name for f in dataclasses.fields(LedgerRow)]


def _iso_date(s: str) -> str:
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {s!r}")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="moatleak")
    p.add_argument("--version", action="version", version=f"moatleak {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="read local AI-tool logs and write a report")
    sc.add_argument("--home", type=Path, default=None)
    sc.add_argument("--out", type=Path, default=Path("moatleak-report"))
    sc.add_argument("--since", type=_iso_date, default=None, metavar="YYYY-MM-DD")
    sc.add_argument("--no-models", action="store_true")
    sc.add_argument("--scan-content", action="store_true",
                    help="Also scan prompt text locally for credentials/personal data (Tier 1). "
                         "Text never leaves this machine and is never stored; only category labels are saved.")
    so = sub.add_parser("sources", help="show which AI-tool data sources are detected")
    so.add_argument("--home", type=Path, default=None)
    return p


def _safe(v):
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def _scan(a) -> int:
    home = a.home or Path.home()
    out = a.out
    try:
        readers = [rd for rd in all_readers() if rd.detect(home)]
        rows = [r for rd in readers for r in rd.iter_rows(home)]
    except OSError as e:
        print(f"moatleak: cannot read {home}: {getattr(e, 'strerror', None) or e}", file=sys.stderr)
        return 1
    try:
        out.mkdir(parents=True, exist_ok=True)
        ledger = Ledger(out / "ledger.db")
        try:
            ledger.add(rows)
            scanned, classified = set(), {}
            if a.scan_content:
                scanned, items = scan_readers(readers, home)
                ledger.add_classifications(items)
                classified = ledger.classifications(TAXONOMY_VERSION)
            allrows = list(ledger.rows())
        finally:
            ledger.db.close()
    except (OSError, sqlite3.Error) as e:
        return _write_fail(out, e)
    earlier = len({r.row_id for r in allrows} - {r.row_id for r in rows})
    if not readers:
        msg = f"No supported AI tool data found under {home}"
        if allrows:
            msg += f"; the report is built from the existing ledger in {out}"
        print(msg + ".")
    if earlier > 0:
        print(f"Note: {out}/ledger.db already held {earlier:,} rows from earlier runs; "
              "they are included (logs rotate, so history is kept). "
              "To start fresh, use a new --out or delete that file.")
    if a.since:
        allrows = [r for r in allrows if r.ts[:10] >= a.since]
    reg = Registry.load()
    res = [resolve(r, reg) for r in allrows]
    s = summarise(res)
    content = (content_summary(res, classified, scanned, s.period[0] or None)
               if a.scan_content else None)
    payload = report_payload(s, headlines(s, reg), reg, include_models=not a.no_models,
                             content=content)
    try:
        (out / "report.html").write_text(report_render.render(payload), encoding="utf-8")
        (out / "summary.json").write_text(
            json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        with open(out / "ledger.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["row_id", *_FIELDS, "provider", "parent", "country",
                        "location_confidence", "access"])
            for x in res:
                w.writerow([_safe(c) for c in (
                    x.row.row_id, *(getattr(x.row, f) for f in _FIELDS), x.provider_name,
                    x.parent, x.country, x.location_confidence, x.access)])
    except OSError as e:
        return _write_fail(out, e)
    for h in payload["headlines"]:
        print(h["text"])
    if content is not None:
        def _e(n):
            return f" (+{n:,} earlier)" if n else ""
        found = " · ".join(f"{c['label']} {c['conversations']}{_e(c['earlier_conversations'])}"
                           for c in content["classes"])
        print(f"Content scan (local): {content['scanned_conversations']:,} conversations scanned "
              f"in the window{_e(content['earlier_scanned_conversations'])}; "
              f"found: {found or 'nothing detected'}")
    print()
    print(f"Report: {(out / 'report.html').resolve()}")
    print(f"Also wrote: ledger.csv, summary.json, ledger.db in {out}")
    print("No network calls were made.")
    return 0


def _write_fail(out, e) -> int:
    reason = getattr(e, "strerror", None) or str(e)
    print(f"moatleak: cannot write to {out}: {reason}", file=sys.stderr)
    return 1


def _sources(a) -> int:
    home = a.home or Path.home()
    for rd in all_readers():
        if rd.detect(home):
            print(f"{rd.name}  detected  {sum(1 for _ in rd.iter_rows(home)):,} rows")
        else:
            print(f"{rd.name}  not found")
    return 0


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    return _scan(a) if a.cmd == "scan" else _sources(a)
