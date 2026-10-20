import json

from moatleak.content.scan import content_summary, scan_readers
from moatleak.content.tier1 import TAXONOMY_VERSION
from moatleak.ledger import LedgerRow
from moatleak.registry import Registry
from moatleak.resolve import resolve

REG = Registry.load()
SID = "sess-synthetic-xyz"


def _row(ref, ts, sess, model="claude-opus-5", endpoint="api.anthropic.com", served=None):
    return LedgerRow("claude_code", ref, ts, "direct", endpoint, model, served, session_ref=sess)


def _res(rows):
    return [resolve(r, REG) for r in rows]


def test_conversation_unit_and_union_of_companies():
    a = _row("a", "2026-10-01T00:00:00Z", SID)
    b = _row("b", "2026-10-01T00:01:00Z", SID, "gpt-5", "openrouter.ai", "OpenAI")
    res = _res([a, b])
    out = content_summary(res, {a.row_id: {"credential"}}, {a.row_id}, "2026-09-25")
    assert out["scanned_conversations"] == 1
    (cls,) = out["classes"]
    assert cls["category"] == "credential" and cls["label"] == "Credentials" and cls["conversations"] == 1
    assert {c["name"] for c in cls["companies"]} == {"Anthropic", "OpenAI"}
    assert all(c["conversations"] == 1 for c in cls["companies"])
    blob = json.dumps(out)
    assert SID not in blob and a.row_id not in blob


def test_window_filter_and_unknown_company():
    old = _row("o", "2026-08-01T00:00:00Z", "old")
    new = _row("n", "2026-10-01T00:00:00Z", "new", "zz-model", "openrouter.ai", "Mystery Co")
    res = _res([old, new])
    cl = {old.row_id: {"financial"}, new.row_id: {"financial"}}
    out = content_summary(res, cl, {old.row_id, new.row_id}, "2026-09-25")
    assert out["scanned_conversations"] == 1
    (cls,) = out["classes"]
    assert cls["conversations"] == 1
    assert [c["name"] for c in cls["companies"]] == ["Unknown company"]


def test_empty_and_sorting():
    a = _row("a", "2026-10-01T00:00:00Z", "s1")
    b = _row("b", "2026-10-01T00:00:00Z", "s2")
    out = content_summary(_res([a, b]), {a.row_id: {"personal_data", "credential"},
                                         b.row_id: {"personal_data"}}, {a.row_id, b.row_id}, None)
    assert [(c["category"], c["conversations"]) for c in out["classes"]] == [
        ("personal_data", 2), ("credential", 1)]
    assert content_summary([], {}, set(), None)["classes"] == []


def test_scan_readers_returns_labels_only():
    marker = "marker-phrase-qq"
    class R:
        def iter_content(self, home):
            yield "r1", "mail jane@example.com " + marker
            yield "r2", "nothing here"
    scanned, items = scan_readers([R()], None)
    assert scanned == {"r1", "r2"}
    assert items == [("r1", TAXONOMY_VERSION, "personal_data", "rule", 1.0)]
    assert marker not in repr(items)


def test_earlier_only_class_listed_without_companies():
    old = _row("o", "2026-08-01T00:00:00Z", "old-sess")
    new = _row("n", "2026-10-01T00:00:00Z", "new-sess")
    res = _res([old, new])
    cl = {old.row_id: {"credential"}, new.row_id: {"personal_data"}}
    out = content_summary(res, cl, {old.row_id, new.row_id}, "2026-09-25")
    assert out["scanned_conversations"] == 1 and out["earlier_scanned_conversations"] == 1
    cred = [c for c in out["classes"] if c["category"] == "credential"][0]
    assert cred["conversations"] == 0 and cred["earlier_conversations"] == 1
    assert cred["companies"] == []
    pd = [c for c in out["classes"] if c["category"] == "personal_data"][0]
    assert pd["conversations"] == 1 and pd["earlier_conversations"] == 0
    assert [c["category"] for c in out["classes"]] == ["personal_data", "credential"]
    blob = json.dumps(out)
    for x in ("old-sess", "new-sess", old.row_id, new.row_id):
        assert x not in blob
