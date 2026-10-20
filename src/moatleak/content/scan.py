"""Run Tier 1 over reader content and summarise per conversation. Text is never kept."""
from __future__ import annotations

from collections import Counter, defaultdict

from moatleak.content import tier1
from moatleak.findings import dedupe

_UNKNOWN = "Unknown company"


def scan_readers(readers, home):
    scanned: set[str] = set()
    items: list[tuple[str, str, str, str, float]] = []
    for rd in readers:
        for row_id, text in rd.iter_content(home):
            scanned.add(row_id)
            for cat in sorted(tier1.classify(text)):
                items.append((row_id, tier1.TAXONOMY_VERSION, cat, "rule", 1.0))
    return scanned, sorted(set(items))


def content_summary(resolved, classified, scanned, start):
    sess_of = {r.row.row_id: r.row.session_ref for r in resolved if r.row.session_ref}
    comp: dict[str, dict[str, str | None]] = defaultdict(dict)  # session -> name -> country
    for r in dedupe(resolved):
        sref = r.row.session_ref
        if not sref or (start and r.row.ts[:10] < start):
            continue
        if r.provider_id:
            comp[sref][r.provider_name] = r.country
        else:
            comp[sref].setdefault(_UNKNOWN, None)
    scanned_sessions = {sess_of[i] for i in scanned if sess_of.get(i) in comp}
    earlier_scanned = {sess_of[i] for i in scanned if i in sess_of and sess_of[i] not in comp}
    cats: dict[str, set[str]] = defaultdict(set)
    early: dict[str, set[str]] = defaultdict(set)
    for rid, cs in classified.items():
        s = sess_of.get(rid)
        if not s:
            continue
        for c in cs:
            (cats if s in comp else early)[c].add(s)
    classes = []
    for cat in set(cats) | set(early):
        sessions = cats.get(cat, set())
        cnt: Counter = Counter()
        ctry: dict[str, str | None] = {}
        for s in sessions:
            for name, country in comp[s].items():
                cnt[name] += 1
                ctry[name] = country
        label = tier1.TAXONOMY.get("classes", {}).get(cat, {}).get("label", cat)
        classes.append({
            "category": cat, "label": label, "conversations": len(sessions),
            "earlier_conversations": len(early.get(cat, ())),
            "companies": [{"name": n, "country": ctry[n], "conversations": c}
                          for n, c in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))]})
    classes.sort(key=lambda c: (-c["conversations"], -c["earlier_conversations"], c["category"]))
    return {"taxonomy_version": tier1.TAXONOMY_VERSION, "method": "rule",
            "scanned_conversations": len(scanned_sessions),
            "earlier_scanned_conversations": len(earlier_scanned), "classes": classes}
