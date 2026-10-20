"""Tier 1 content classifier: local regex detectors. Never returns matched text."""
from __future__ import annotations

import importlib.resources
import re
import tomllib
from dataclasses import dataclass
from typing import Callable

TAXONOMY: dict = tomllib.loads(
    importlib.resources.files("moatleak").joinpath("data/taxonomy.toml").read_text("utf-8")
)
TAXONOMY_VERSION: str = TAXONOMY["version"]


@dataclass(frozen=True)
class Detector:
    name: str
    category: str
    pattern: re.Pattern
    validate: Callable[[str], bool] | None = None


def _luhn(s: str) -> bool:
    d = [int(c) for c in s if c.isdigit()]
    if not 13 <= len(d) <= 19:
        return False
    tot = 0
    for i, n in enumerate(reversed(d)):
        if i % 2:
            n *= 2
            if n > 9:
                n -= 9
        tot += n
    return tot % 10 == 0


def _iban(s: str) -> bool:
    s = s.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    r = s[4:] + s[:4]
    try:
        return int("".join(str(int(c, 36)) for c in r)) % 97 == 1
    except ValueError:
        return False


def _has_digit(s: str) -> bool:
    return any(c.isdigit() for c in s.split()[-1])


def _ip(s: str) -> bool:
    p = [int(x) for x in s.split(".")]
    if any(x > 255 for x in p):
        return False
    return p[0] == 10 or (p[0] == 172 and 16 <= p[1] <= 31) or (p[0] == 192 and p[1] == 168)


_CODE_RECEIVERS = frozenset({"self", "this", "settings", "config", "os", "obj", "cls", "app"})


def _host(s: str) -> bool:
    return s.split(".", 1)[0] not in _CODE_RECEIVERS


def _d(name, cat, pat, validate=None, flags=0):
    return Detector(name, cat, re.compile(pat, flags), validate)


_CRED_KEYS = (
    _d("aws_access_key", "credential", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    _d("gcp_api_key", "credential", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    _d("anthropic_key", "credential", r"\bsk-ant-[A-Za-z0-9_\-]{20,}"),
    _d("openai_style_key", "credential", r"\bsk-(?!ant-)[A-Za-z0-9_\-]{20,}"),
    _d("github_token", "credential", r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{22,}"),
    _d("slack_token", "credential", r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    _d("private_key", "credential", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    _d("jwt", "credential", r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
)
CREDENTIAL_KEY_DETECTORS: tuple[Detector, ...] = _CRED_KEYS

DETECTORS: tuple[Detector, ...] = (
    _CRED_KEYS[:2]
    + (_d("gcp_service_account", "credential", r'"type"\s*:\s*"service_account"'),)
    + _CRED_KEYS[2:]
    + (
        _d("password_assignment", "credential",
           r"""(?<![A-Za-z])(?:password|passwd|pwd)\s*[=:]\s*["']?[^\s"'<>]{4,}""", None, re.I),
        _d("email", "personal_data", r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@(?:[A-Za-z0-9-]{1,63}\.){1,8}[A-Za-z]{2,24}\b"),
        _d("phone_e164", "personal_data", r"(?<![\w+])\+[1-9](?:[ \-]?\d){7,14}\b"),
        _d("uk_ni_number", "personal_data", r"\b[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z] ?\d{2} ?\d{2} ?\d{2} ?[A-D]\b"),
        _d("passport_number", "personal_data",
           r"\bpassport\b[^\n\d]{0,20}\b[A-Z0-9]{8,9}\b", _has_digit, re.I),
        _d("iban", "financial", r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b", _iban),
        _d("payment_card", "financial", r"\b[3-6]\d{3}(?:[ -]?\d){9,15}(?!\d)\b", _luhn),
        _d("private_ip", "infrastructure",
           r"(?<![\d.])\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\d.])", _ip),
        _d("internal_hostname", "infrastructure",
           r"(?<![A-Za-z0-9.-])(?:(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.){2,8}"
           r"(?:internal|local|lan|corp|intranet)"
           r"|(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.){1,8}home\.arpa)\b", _host),
    )
)


def detect(text: str) -> set[str]:
    """Names of detectors that fired (validated). Never returns matched text."""
    out: set[str] = set()
    for d in DETECTORS:
        for m in d.pattern.finditer(text):
            if d.validate is None or d.validate(m.group(0)):
                out.add(d.name)
                break
    return out


def classify(text: str) -> set[str]:
    """Categories that fired; never 'none'."""
    names = detect(text)
    return {d.category for d in DETECTORS if d.name in names}
