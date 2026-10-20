#!/usr/bin/env python3
"""Repo privacy scan reusing the Tier 1 credential-key regexes. Prints path:line: name, never the match."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from moatleak.content.tier1 import CREDENTIAL_KEY_DETECTORS  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", ".", ":!:docs/notes/", ":!:docs/plans/", ":!:docs/qa-process.md", ":!:docs/naming.md", ":!:scripts/check.sh"],
        capture_output=True, check=True, cwd=ROOT,
    ).stdout
    hits = []
    for rel in filter(None, out.split(b"\0")):
        path = rel.decode("utf-8", "replace")
        full = ROOT / path
        try:
            text = full.read_bytes().decode("utf-8", "replace")
        except OSError:
            if not full.exists():
                continue
            print(f"{path}: unreadable")
            return 1
        if "\0" in text:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for d in CREDENTIAL_KEY_DETECTORS:
                if d.pattern.search(line):
                    hits.append(f"{path}:{n}: {d.name}")
    if hits:
        print("\n".join(hits))
        return 1
    print("privacy_keys: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
