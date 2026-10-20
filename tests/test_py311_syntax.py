"""Guard: every source/test file must compile on Python 3.11 (requires-python >= 3.11).

Newer interpreters accept syntax (PEP 701 f-strings) that 3.11 rejects, so compile
the tree with a real 3.11 interpreter when one is available.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = r"""
import pathlib, sys
root = pathlib.Path(sys.argv[1])
for sub in ("src", "tests"):
    for p in sorted((root / sub).rglob("*.py")):
        try:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
        except SyntaxError as e:
            print(f"{p.relative_to(root)}:{e.lineno} {e.msg}")
"""


def test_tree_compiles_on_python311():
    exe = shutil.which("python3.11")
    if exe is None or sys.version_info[:2] == (3, 11):
        pytest.skip("no separate python3.11 available (or running on 3.11 already)")
    r = subprocess.run([exe, "-c", SCRIPT, str(ROOT)], capture_output=True, text=True, timeout=30)
    assert r.stdout.strip() == "", r.stdout
    assert r.returncode == 0, r.stderr
