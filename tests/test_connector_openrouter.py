import io
import json
import urllib.error
import urllib.request

import pytest

from moatleak.connectors import openrouter as orc
from moatleak.connectors.openrouter import (
    ConnectorError, activity_url, fetch_activity, read_key, rows_from_activity,
)

KEY = "sk-" + "or-v1-" + "x" * 24


@pytest.fixture(autouse=True)
def _no_net(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("real network call")
    monkeypatch.setattr(urllib.request, "urlopen", boom)


class _Resp:
    def __init__(self, body):
        self._b = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._b


def make_opener(body=b'{"data": []}', calls=None):
    def opener(req, timeout=None):
        if calls is not None:
            calls.append(req)
        return _Resp(body)
    return opener


def raising(exc):
    def opener(req, timeout=None):
        raise exc
    return opener


def no_key(exc):
    s = str(exc.value)
    assert KEY not in s and KEY not in repr(exc.value)


def test_url_default_and_date():
    assert activity_url() == "https://openrouter.ai/api/v1/activity"
    assert activity_url("2026-09-30").endswith("?date=2026-09-30")


@pytest.mark.parametrize("bad", ["2026-9-30", "yesterday", "2026-09-30&x=1", ""])
def test_invalid_date_no_call(bad):
    calls = []
    with pytest.raises(ConnectorError):
        fetch_activity(KEY, date=bad, opener=make_opener(calls=calls))
    assert calls == []


def test_fetch_request_shape():
    calls = []
    items = [{"model": "m"}]
    out = fetch_activity(KEY, opener=make_opener(json.dumps({"data": items}).encode(), calls))
    assert out == items
    r = calls[0]
    assert r.full_url == "https://openrouter.ai/api/v1/activity"
    assert r.get_method() == "GET"
    assert r.get_header("Authorization") == "Bearer " + KEY
    fetch_activity(KEY, date="2026-09-30", opener=make_opener(calls=calls))
    assert calls[1].full_url.endswith("?date=2026-09-30")


def test_read_key():
    assert read_key("X_KEY", {"X_KEY": "  abc \n"}) == "abc"
    for env in ({}, {"X_KEY": ""}, {"X_KEY": "  "}):
        with pytest.raises(ConnectorError) as e:
            read_key("X_KEY", env)
        assert "Environment variable X_KEY is not set" in str(e.value)


def test_read_key_rejects_bad_chars():
    for bad in ("ab\ncd", "ab cd", "ab\x00cd", "k\u00e9y", "ab\tcd"):
        with pytest.raises(ConnectorError) as e:
            read_key("X_KEY", {"X_KEY": bad})
        assert "contains invalid characters" in str(e.value)
        assert bad.strip() not in str(e.value)


def test_fetch_value_errors_are_scrubbed():
    secret = "sec" + "ret-value"
    for exc in (ValueError("bad header " + secret), UnicodeEncodeError("ascii", secret, 0, 1, "x")):
        def opener(req, timeout=None, exc=exc):
            raise exc
        with pytest.raises(ConnectorError) as e:
            fetch_activity(secret, opener=opener)
        assert secret not in str(e.value)
        assert e.value.__cause__ is None and e.value.__suppress_context__


def _http(code, msg="Only management keys can perform this operation"):
    body = json.dumps({"error": {"code": code, "message": msg}}).encode()
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(body))


def test_http_403():
    with pytest.raises(ConnectorError) as e:
        fetch_activity(KEY, opener=raising(_http(403)))
    assert "403" in str(e.value) and "management key" in str(e.value)
    no_key(e)


def test_http_401():
    with pytest.raises(ConnectorError) as e:
        fetch_activity(KEY, opener=raising(_http(401, "Missing Authentication header")))
    assert "401" in str(e.value) and "Missing Authentication" in str(e.value)
    no_key(e)


def test_http_error_echoing_key_is_not_leaked():
    with pytest.raises(ConnectorError) as e:
        fetch_activity(KEY, opener=raising(_http(500, "bad " + KEY)))
    no_key(e)


def test_url_error_and_timeout():
    for exc in (urllib.error.URLError("down"), TimeoutError("slow")):
        with pytest.raises(ConnectorError) as e:
            fetch_activity(KEY, opener=raising(exc))
        no_key(e)


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"x": 1}', b'{"data": {}}', b"\xff"])
def test_bad_body(body):
    with pytest.raises(ConnectorError) as e:
        fetch_activity(KEY, opener=make_opener(body))
    no_key(e)


def item(**kw):
    d = {"date": "2026-09-30", "endpoint_id": "ep1", "model": "ex/model-a",
         "provider_name": "ExampleCloud", "requests": 5, "prompt_tokens": 50,
         "completion_tokens": 125, "usage": 0.01}
    d.update(kw)
    return d


def test_rows_mapping():
    (r,) = rows_from_activity([item()])
    assert r.source == "openrouter_activity"
    assert r.source_ref == "2026-09-30|ep1|ex/model-a"
    assert r.ts == "2026-09-30" and r.route == "router"
    assert r.endpoint == "openrouter.ai" and r.requested_model == "ex/model-a"
    assert r.served_by_raw == "ExampleCloud"
    assert (r.requests, r.input_tokens, r.output_tokens) == (5, 50, 125)
    assert r.evidence == "provider_api"


def test_rows_sum_duplicates_and_missing_fields():
    rows = rows_from_activity([item(), item(requests=2, prompt_tokens=None, completion_tokens=3),
                               item(endpoint_id=None, provider_name=None)])
    assert len(rows) == 2
    by = {r.source_ref: r for r in rows}
    s = by["2026-09-30|ep1|ex/model-a"]
    assert (s.requests, s.input_tokens, s.output_tokens) == (7, 50, 128)
    m = by["2026-09-30||ex/model-a"]
    assert m.served_by_raw is None


def test_rows_skip_bad():
    bad = ["str", None, item(date="2026-9-30"), item(date=None), item(model=None),
           item(model=""), item(requests=0), item(requests=-1)]
    assert rows_from_activity(bad) == []


def test_rows_order_and_stable_id():
    items = [item(date="2026-10-01"), item(model="ex/b"), item(date="2026-09-29")]
    a = rows_from_activity(items)
    b = rows_from_activity(list(reversed(items)))
    keys = [(r.ts, r.source_ref) for r in a]
    assert keys == sorted(keys)
    assert [r.row_id for r in a] == [r.row_id for r in b]


def test_date_must_be_real_and_ascii():
    for bad in ("2026-13-45", "2026-02-30", "\u0662\u0660\u0662\u0666-09-30"):
        with pytest.raises(ConnectorError):
            activity_url(bad)


def test_int_overflow():
    (r,) = rows_from_activity([item(requests=1, prompt_tokens=float("inf"))])
    assert r.input_tokens == 0


def test_server_message_reads_at_most_4096():
    sizes = []

    class Body(io.BytesIO):
        def read(self, n=-1):
            sizes.append(n)
            return super().read(n)
    e = urllib.error.HTTPError("u", 500, "x", {}, Body(b"{}"))
    orc._server_message(e)
    assert sizes == [4096]


def test_default_opener_refuses_redirects(monkeypatch):
    seen = []

    class FakeOpener:
        def open(self, req, timeout=None):
            h = [x for x in handlers if isinstance(x, urllib.request.HTTPRedirectHandler)][0]
            seen.append(req.get_header("Authorization"))
            h.redirect_request(req, None, 302, "Found", {}, "https://evil.example.com/")

    handlers = []

    def fake_build(*hs):
        handlers.extend(h() if isinstance(h, type) else h for h in hs)
        return FakeOpener()
    monkeypatch.setattr(urllib.request, "build_opener", fake_build)
    with pytest.raises(ConnectorError, match="unexpected redirect"):
        fetch_activity(KEY)
    assert seen
