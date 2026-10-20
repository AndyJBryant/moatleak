import subprocess
import sys
import time
from pathlib import Path

import pytest

from moatleak.content import tier1
from moatleak.content.tier1 import DETECTORS, TAXONOMY, classify, detect

ROOT = Path(__file__).resolve().parent.parent

POS = {
    "aws_access_key": "id " + "AK" + "IA" + "Q" * 16,
    "gcp_api_key": "k " + "AI" + "za" + "a" * 35,
    "gcp_service_account": '{"type": "service' + '_account"}',
    "anthropic_key": "sk" + "-ant-" + "a" * 24,
    "openai_style_key": "sk" + "-proj-" + "b" * 24,
    "github_token": "gh" + "p_" + "a" * 36,
    "slack_token": "xo" + "xb-" + "1234567890" + "ab",
    "private_key": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "jwt": "ey" + "J" + "a" * 12 + ".ey" + "J" + "b" * 12 + "." + "c" * 12,
    "password_assignment": "password" + "=hunter22x",
    "email": "write to jane.doe@example.com now",
    "phone_e164": "call +44 7700 900123 today",
    "uk_ni_number": "ni " + "AB 12 34 56 C",
    "passport_number": "passport no: " + "X1234567" + "8",
    "iban": "pay " + "GB82 WEST 1234 5698 7654 32",
    "payment_card": "card " + "4111 1111 " + "1111 1111",
    "private_ip": "host 192.168.1.20 up",
    "internal_hostname": "see db01.corp.local and ci.build.internal",
}
NEG = {
    "aws_access_key": "AK" + "IA" + "short",
    "gcp_api_key": "AI" + "za" + "tooshort",
    "gcp_service_account": '{"type": "user"}',
    "anthropic_key": "sk" + "-proj-" + "b" * 24,
    "openai_style_key": "sk" + "-ant-" + "a" * 24,
    "github_token": "gh" + "p_" + "a" * 10,
    "slack_token": "xo" + "xb-1",
    "private_key": "-----BEGIN " + "CERTIFICATE-----",
    "jwt": "ey" + "Jabc.def",
    "password_assignment": "the password is important",
    "email": "user at example dot com",
    "phone_e164": "call 0044 7700 900123",
    "uk_ni_number": "ni " + "DQ 12 34 56 C",
    "passport_number": "my passport is expired",
    "iban": "pay " + "GB82 WEST 1234 5698 7654 33",
    "payment_card": "card " + "4111 1111 " + "1111 1112",
    "private_ip": "host 8.8.8.8 and 192.168.1.300",
    "internal_hostname": "visit example.com",
}


def test_names_covered():
    assert {d.name for d in DETECTORS} == set(POS) == set(NEG)


@pytest.mark.parametrize("name", sorted(POS))
def test_positive(name):
    assert name in detect(POS[name])


@pytest.mark.parametrize("name", sorted(NEG))
def test_negative(name):
    assert name not in detect(NEG[name])


def test_sk_ant_not_openai():
    got = detect(POS["anthropic_key"])
    assert "anthropic_key" in got and "openai_style_key" not in got


def test_classify():
    assert classify("just some plain prose about cats") == set()
    assert classify(POS["aws_access_key"] + " " + POS["email"]) == {"credential", "personal_data"}
    assert classify(POS["iban"]) == {"financial"}
    assert classify(POS["private_ip"]) == {"infrastructure"}
    assert "none" not in classify(POS["email"])


def test_categories_in_taxonomy():
    assert tier1.TAXONOMY_VERSION == TAXONOMY["version"] == "1"
    for d in DETECTORS:
        assert d.category in TAXONOMY["classes"]
    for c in TAXONOMY["classes"].values():
        assert c["label"] and c["description"]
    assert set(tier1.CREDENTIAL_KEY_DETECTORS) <= set(DETECTORS)


def test_no_leak():
    secret = "AK" + "IA" + "Z" * 16
    t = "x " + secret + " y a@example.com"
    assert secret not in repr(detect(t)) + repr(classify(t))
    assert "a@example.com" not in repr(detect(t))


def test_performance():
    text = ("lorem ipsum dolor sit amet 12345 foo-bar baz@ 10.0 " * 4200)[:200_000]
    t = time.time()
    classify(text)
    assert time.time() - t < 1.0


def _git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


def _run(cwd):
    scripts = Path(cwd) / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "privacy_keys.py").write_bytes((ROOT / "scripts/privacy_keys.py").read_bytes())
    if not (Path(cwd) / "src").exists():
        (Path(cwd) / "src").symlink_to(ROOT / "src")
    return subprocess.run([sys.executable, str(scripts / "privacy_keys.py")],
                          cwd=cwd, capture_output=True, text=True)


def test_privacy_keys_script(tmp_path):
    _git(tmp_path, "init", "-q")
    key = "gh" + "p_" + "q" * 36
    (tmp_path / "a.txt").write_text("token " + key + "\n")
    _git(tmp_path, "add", "a.txt")
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "a.txt:1: github_token" in r.stdout
    assert key not in r.stdout + r.stderr
    (tmp_path / "a.txt").write_text("clean\n")
    _git(tmp_path, "add", "a.txt")
    r = _run(tmp_path)
    assert r.returncode == 0 and "privacy_keys: OK" in r.stdout


def _t(text):
    t0 = time.time()
    classify(text)
    return time.time() - t0


@pytest.mark.parametrize("unit", ["a-", "1.", "a."])
def test_no_redos_hostname(unit):
    assert _t(unit * 100_000) < 1.0


def test_no_redos_email():
    assert _t("a." * 100_000) < 1.0
    assert _t("x@" * 100_000) < 1.0


@pytest.mark.parametrize("s", ["DB_PASSWORD=hunter22", "export MYSQL_PWD=abcd1234"])
def test_password_prefixed(s):
    assert "credential" in classify(s)


def test_password_reset_url_no_value():
    assert classify("see password_reset_url for details") == set()


@pytest.mark.parametrize("s", ["x = settings.local", "self.internal", "foo.local"])
def test_hostname_code_not_flagged(s):
    assert "infrastructure" not in classify(s)


@pytest.mark.parametrize("s", ["db01.corp.local", "ci.build.internal", "nas.home.arpa"])
def test_hostname_flagged(s):
    assert "infrastructure" in classify(s)


def test_ip_guards():
    assert "private_ip" not in detect("v 1.10.0.0.1 x")
    assert "private_ip" in detect("v 10.0.0.1 x")


def test_card_trailing_digit_guard():
    assert "payment_card" not in detect("n " + "4111 1111 1111 1111" + "5")
    assert "payment_card" in detect("n " + "4111 1111 1111 1111")


def test_privacy_keys_latin1_and_root(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "privacy_keys.py").write_bytes((ROOT / "scripts/privacy_keys.py").read_bytes())
    (tmp_path / "src").symlink_to(ROOT / "src")
    _git(tmp_path, "init", "-q")
    key = "gh" + "p_" + "q" * 36
    (tmp_path / "l.txt").write_bytes(("caf\xe9 " + key + "\n").encode("latin-1"))
    _git(tmp_path, "add", "l.txt")
    # cwd elsewhere: root derives from the script path
    r = subprocess.run([sys.executable, str(scripts / "privacy_keys.py")], cwd="/",
                       capture_output=True, text=True)
    assert r.returncode == 1 and "l.txt:1: github_token" in r.stdout


def test_privacy_keys_oserror(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "privacy_keys.py").write_bytes((ROOT / "scripts/privacy_keys.py").read_bytes())
    (tmp_path / "src").symlink_to(ROOT / "src")
    _git(tmp_path, "init", "-q")
    (tmp_path / "d.txt").write_text("x")
    _git(tmp_path, "add", "d.txt")
    (tmp_path / "d.txt").unlink()
    (tmp_path / "d.txt").mkdir()  # tracked path exists but unreadable as file
    r = subprocess.run([sys.executable, str(scripts / "privacy_keys.py")], cwd="/",
                       capture_output=True, text=True)
    assert r.returncode == 1 and "d.txt" in r.stdout + r.stderr
