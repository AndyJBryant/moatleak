import csv, json, shutil, subprocess, sys
from pathlib import Path

import pytest
import moatleak
from moatleak.cli import main
from moatleak.ledger import Ledger
from moatleak.headlines import headlines
from moatleak.findings import summarise
from moatleak.readers import all_readers
from moatleak.registry import Registry
from moatleak.resolve import resolve

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    shutil.copytree(FIX / "hermes" / "logs", h / ".hermes" / "logs")
    shutil.copytree(FIX / "claude" / "projects", h / ".claude" / "projects")
    return h


def _rows(h):
    return [r for rd in all_readers() if rd.detect(h) for r in rd.iter_rows(h)]


def _scan(home, out, *extra):
    return main(["scan", "--home", str(home), "--out", str(out), *extra])


def _csv(out):
    with open(out / "ledger.csv", newline="") as fh:
        return list(csv.reader(fh))


def test_scan_writes_files(home, tmp_path, capsys):
    out = tmp_path / "out"
    assert _scan(home, out) == 0
    text = capsys.readouterr().out
    for f in ("report.html", "summary.json", "ledger.csv", "ledger.db"):
        assert (out / f).exists()
    assert f"Report: {(out / 'report.html').resolve()}" in text
    assert "No network calls were made." in text
    rows = _rows(home)
    reg = Registry.load()
    s = summarise([resolve(r, reg) for r in rows])
    payload = json.loads((out / "summary.json").read_text())
    assert payload["headlines"][0]["kind"] == headlines(s, reg)[0].kind
    assert payload["headlines"][0]["text"] in text
    with open(out / "ledger.csv", newline="") as fh:
        data = list(csv.reader(fh))
    assert "access" in data[0] and data[0][0] == "row_id"
    assert len(data) - 1 == len({r.row_id for r in rows})


def test_no_models(home, tmp_path):
    out = tmp_path / "out"
    _scan(home, out, "--no-models")
    p = json.loads((out / "summary.json").read_text())
    assert p["models"] == [] and p["include_models"] is False


def test_since_filters(home, tmp_path):
    out = tmp_path / "out"
    assert _scan(home, out, "--since", "2099-01-01") == 0
    assert json.loads((out / "summary.json").read_text())["empty"] is True
    assert len(_csv(out)) == 1


def test_rerun_no_duplicates(home, tmp_path, capsys):
    out = tmp_path / "out"
    _scan(home, out)
    capsys.readouterr()
    _scan(home, out)
    text = capsys.readouterr().out
    assert "from earlier runs" not in text
    assert len(_csv(out)) - 1 == len({r.row_id for r in _rows(home)})


def test_earlier_rows_kept(home, tmp_path, capsys):
    out = tmp_path / "out"
    _scan(home, out)
    shutil.rmtree(home / ".claude")
    capsys.readouterr()
    _scan(home, out)
    assert "already held" in capsys.readouterr().out
    assert len(_csv(out)) - 1 > len(_rows(home))


def test_empty_home(tmp_path, capsys):
    h = tmp_path / "empty"
    h.mkdir()
    out = tmp_path / "out"
    assert _scan(h, out) == 0
    assert "No supported AI tool data found" in capsys.readouterr().out
    assert (out / "report.html").exists() and (out / "summary.json").exists()


def test_sources(home, capsys):
    before = sorted(p.relative_to(home) for p in home.rglob("*"))
    assert main(["sources", "--home", str(home)]) == 0
    text = capsys.readouterr().out
    assert len(text.strip().splitlines()) == 3
    assert "detected" in text and "not found" in text
    assert before == sorted(p.relative_to(home) for p in home.rglob("*"))


def test_bad_since(home, tmp_path):
    with pytest.raises(SystemExit) as e:
        _scan(home, tmp_path / "o", "--since", "nope")
    assert e.value.code == 2


def test_no_network(home, tmp_path, monkeypatch):
    import socket

    def boom(*a, **k):
        raise AssertionError("network")
    monkeypatch.setattr(socket, "socket", boom)
    assert _scan(home, tmp_path / "out") == 0
    code = ("import sys; from moatleak.cli import main; "
            f"main(['scan','--home',{str(home)!r},'--out',{str(tmp_path / 'o2')!r}]); "
            "print('moatleak.connectors' in sys.modules)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.stdout.strip().splitlines()[-1] == "False", r.stderr


def test_version():
    r = subprocess.run([sys.executable, "-m", "moatleak", "--version"], capture_output=True, text=True)
    assert r.returncode == 0 and f"moatleak {moatleak.__version__}" in (r.stdout + r.stderr)


def test_two_homes_notice(home, tmp_path, capsys):
    out = tmp_path / "out"
    h2 = tmp_path / "home2"
    shutil.copytree(FIX / "claude" / "projects", h2 / ".claude" / "projects")
    h1 = tmp_path / "home1"
    shutil.copytree(FIX / "hermes" / "logs", h1 / ".hermes" / "logs")
    _scan(h1, out)
    n1 = len(_rows(h1))
    capsys.readouterr()
    _scan(h2, out)
    text = capsys.readouterr().out
    assert f"already held {n1:,} rows from earlier runs" in text
    assert text.index("Note:") < text.index("Report:")
    assert len(_csv(out)) - 1 == n1 + len(_rows(h2))


def test_empty_home_with_ledger(home, tmp_path, capsys):
    out = tmp_path / "out"
    _scan(home, out)
    e = tmp_path / "empty"
    e.mkdir()
    capsys.readouterr()
    assert _scan(e, out) == 0
    assert "the report is built from the existing ledger" in capsys.readouterr().out


def test_bad_out(home, tmp_path, capsys):
    f = tmp_path / "afile"
    f.write_text("x")
    assert _scan(home, f) == 1
    err = capsys.readouterr().err
    assert err.startswith("moatleak: cannot write to") and "Traceback" not in err


def test_csv_formula_guard(tmp_path):
    from moatleak.cli import _safe
    for c in "=+-@":
        assert _safe(c + "cmd") == "'" + c + "cmd"
    assert _safe("ok") == "ok" and _safe(5) == 5


def test_iter_content_never_called_without_flag(home, tmp_path, monkeypatch):
    import moatleak.cli as cli
    real = cli.all_readers

    class Boom:
        def __init__(self, rd):
            self._rd = rd
            self.name = rd.name
        def detect(self, h):
            return self._rd.detect(h)
        def iter_rows(self, h):
            return self._rd.iter_rows(h)
        def iter_content(self, h):
            raise AssertionError("iter_content called")

    monkeypatch.setattr(cli, "all_readers", lambda: [Boom(r) for r in real()])
    out = tmp_path / "out"
    assert _scan(home, out) == 0
    assert json.loads((out / "summary.json").read_text())["content"] is None
    assert Ledger(out / "ledger.db").classifications() == {}


def _content_home(tmp_path):
    secret = "gh" + "p_" + "Z" * 36
    email = "jane@example.com"
    marker = "uniquemarkerphrase zebra-quokka"
    h = tmp_path / "chome"
    d = h / ".claude" / "projects" / "p"
    d.mkdir(parents=True)
    sid = "00000000-0000-4000-8000-0000000000aa"
    lines = [
        {"type": "user", "sessionId": sid, "timestamp": "2026-09-20T09:59:00.000Z",
         "message": {"role": "user", "content": f"{marker} {secret} {email}"}},
        {"type": "assistant", "requestId": "req_X", "timestamp": "2026-09-20T10:00:00.000Z",
         "sessionId": sid, "message": {"model": "claude-opus-5", "usage": {
             "input_tokens": 10, "output_tokens": 1, "cache_read_input_tokens": 0,
             "cache_creation_input_tokens": 0, "inference_geo": "not_available"}}},
    ]
    (d / "s.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return h, (secret, email, marker)


def test_scan_content_persists_no_text(tmp_path, capsys):
    h, needles = _content_home(tmp_path)
    out = tmp_path / "out"
    assert _scan(h, out, "--scan-content") == 0
    assert "Content scan (local): 1 conversations scanned" in capsys.readouterr().out
    cl = Ledger(out / "ledger.db").classifications("1")
    assert {c for cs in cl.values() for c in cs} == {"credential", "personal_data"}
    p = json.loads((out / "summary.json").read_text())
    cred = [c for c in p["content"]["classes"] if c["category"] == "credential"][0]
    assert "Anthropic" in [c["name"] for c in cred["companies"]]
    files = [f for f in out.rglob("*") if f.is_file()]
    assert len(files) >= 4
    for f in files:
        data = f.read_bytes()
        for n in needles:
            assert n.encode() not in data, f.name


def test_scan_content_line_reports_earlier(home, tmp_path, capsys):
    secret = "gh" + "p_" + "Y" * 36
    d = home / ".claude" / "projects" / "old"
    d.mkdir(parents=True)
    sid = "00000000-0000-4000-8000-0000000000b1"
    lines = [
        {"type": "user", "sessionId": sid, "timestamp": "2001-01-01T09:59:00.000Z",
         "message": {"role": "user", "content": secret}},
        {"type": "assistant", "requestId": "req_old1", "timestamp": "2001-01-01T10:00:00.000Z",
         "sessionId": sid, "message": {"model": "claude-opus-5", "usage": {
             "input_tokens": 10, "output_tokens": 1, "cache_read_input_tokens": 0,
             "cache_creation_input_tokens": 0, "inference_geo": "not_available"}}}]
    (d / "o.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    out = tmp_path / "out"
    assert _scan(home, out, "--scan-content") == 0
    text = capsys.readouterr().out
    assert "earlier); found:" in text and "Credentials 0 (+1 earlier)" in text
    p = json.loads((out / "summary.json").read_text())["content"]
    assert p["earlier_scanned_conversations"] >= 1
