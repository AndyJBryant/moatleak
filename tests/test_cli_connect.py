import subprocess
import sys

import pytest
from moatleak.cli import main
from moatleak.connectors import openrouter as orc
from moatleak.ledger import Ledger

KEY = "sk-" + "or-v1-" + "k" * 24
VAR = "TEST_MGMT_KEY_VAR"
ITEMS = [{"date": "2026-09-30", "endpoint_id": "e1", "model": "ex/model-a",
          "provider_name": "ExampleCloud", "requests": 5, "prompt_tokens": 1, "completion_tokens": 2},
         {"date": "2026-09-29", "endpoint_id": "e1", "model": "ex/model-a",
          "provider_name": "ExampleCloud", "requests": 2}]


@pytest.fixture
def calls(monkeypatch):
    rec = []

    def fake(key, date=None, **kw):
        rec.append((key, date))
        return ITEMS
    monkeypatch.setattr(orc, "fetch_activity", fake)
    monkeypatch.setenv(VAR, KEY)
    return rec


def _run(out, *extra):
    return main(["connect", "openrouter", "--key-env", VAR, "--out", str(out), *extra])


def _answer(monkeypatch, v):
    def inp(prompt=""):
        if isinstance(v, BaseException):
            raise v
        return v
    monkeypatch.setattr("builtins.input", inp)


@pytest.mark.parametrize("ans", ["n", "", "maybe", EOFError()])
def test_declined_makes_no_call(calls, tmp_path, monkeypatch, capsys, ans):
    _answer(monkeypatch, ans)
    out = tmp_path / "out"
    assert _run(out) == 1
    assert calls == [] and not out.exists()
    assert "Aborted: no request was made." in capsys.readouterr().out


@pytest.mark.parametrize("ans", ["y", " YES "])
def test_yes_answer_stores(calls, tmp_path, monkeypatch, capsys, ans):
    _answer(monkeypatch, ans)
    out = tmp_path / "out"
    assert _run(out) == 0
    assert len(calls) == 1
    rows = list(Ledger(out / "ledger.db").rows())
    assert len(rows) == 2 and {r.source for r in rows} == {"openrouter_activity"}
    o = capsys.readouterr().out
    assert "Stored 2 OpenRouter activity rows for 2 days (first 2026-09-29, last 2026-09-30)" in o
    assert "GET https://openrouter.ai/api/v1/activity" in o and f"from ${VAR}" in o


def test_yes_flag_does_not_prompt(calls, tmp_path, monkeypatch):
    _answer(monkeypatch, AssertionError("prompted"))
    assert _run(tmp_path / "out", "--yes", "--date", "2026-09-30") == 0
    assert calls == [(KEY, "2026-09-30")]


def test_dry_run(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("must not be called")
    monkeypatch.setattr(orc, "fetch_activity", boom)
    monkeypatch.setattr(orc, "read_key", boom)
    monkeypatch.delenv(VAR, raising=False)
    out = tmp_path / "out"
    assert _run(out, "--dry-run") == 0
    o = capsys.readouterr().out
    assert "GET https://openrouter.ai/api/v1/activity" in o and "is NOT set" in o
    assert "Dry run: no request was made." in o and not out.exists()
    assert "management key from $" + VAR in o
    monkeypatch.setenv(VAR, KEY)
    assert _run(out, "--dry-run") == 0
    o = capsys.readouterr().out
    assert "is set" in o and KEY not in o


def test_missing_var(calls, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(VAR)
    assert _run(tmp_path / "out", "--yes") == 2
    assert VAR in capsys.readouterr().err and calls == []


def test_key_never_leaks(calls, tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    assert _run(out, "--yes") == 0
    c = capsys.readouterr()
    assert KEY not in c.out and KEY not in c.err
    for f in out.rglob("*"):
        if f.is_file():
            assert KEY.encode() not in f.read_bytes()


def test_connector_error(tmp_path, monkeypatch, capsys):
    def bad(key, date=None, **kw):
        raise orc.ConnectorError("boom")
    monkeypatch.setattr(orc, "fetch_activity", bad)
    monkeypatch.setenv(VAR, KEY)
    assert _run(tmp_path / "out", "--yes") == 1
    assert "boom" in capsys.readouterr().err


def test_scan_and_sources_never_import_connectors(tmp_path):
    for argv in (["scan", "--home", str(tmp_path), "--out", str(tmp_path / "o")],
                 ["sources", "--home", str(tmp_path)]):
        code = ("import sys; from moatleak.cli import main; "
                f"main({argv!r}); print('moatleak.connectors' in sys.modules)")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert r.stdout.strip().splitlines()[-1] == "False", r.stderr


def test_scan_read_oserror(tmp_path, monkeypatch, capsys):
    class Bad:
        name = "bad"

        def detect(self, h):
            return True

        def iter_rows(self, h):
            raise PermissionError(13, "Permission denied")
    monkeypatch.setattr("moatleak.cli.all_readers", lambda: [Bad()])
    assert main(["scan", "--home", str(tmp_path), "--out", str(tmp_path / "o")]) == 1
    err = capsys.readouterr().err
    assert err.startswith(f"moatleak: cannot read {tmp_path}: Permission denied")
