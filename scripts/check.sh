#!/bin/bash
set -euo pipefail

# Navigate to repo root
cd "$(git rev-parse --show-toplevel)"

# Determine Python binary
if [[ -f .venv/bin/python ]]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

# Step a: Run pytest
echo "Running pytest..."
$PY -m pytest -q || {
  EXIT_CODE=$?
  if [[ $EXIT_CODE -eq 5 ]]; then
    # pytest exit code 5 = no tests collected; this is OK at this stage
    echo "pytest: no tests collected (OK at this stage)"
  else
    exit $EXIT_CODE
  fi
}

# Step b: Privacy scan over git ls-files
echo "Running privacy scan..."
mapfile -d '' files < <(git ls-files -z -- . ':!:docs/notes/' ':!:docs/plans/' ':!:docs/qa-process.md' ':!:docs/naming.md' ':!:scripts/check.sh')
if [ ${#files[@]} -eq 0 ]; then echo 'check.sh: OK'; exit 0; fi
hits=$(mktemp); trap 'rm -f "$hits"' EXIT
set +e
grep -nIH -E \
  -e '/home/[a-z]' -e '/Users/[A-Za-z]' \
  -e 'gen-17[0-9]{8}-[A-Za-z0-9]{20}' -e 'msg_01[A-Za-z0-9]{20,}' -e 'req_[A-Za-z0-9]{20,}' \
  -e '(^|[^A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}' -e 'AKIA[0-9A-Z]{16}' -e 'gh[pousr]_[A-Za-z0-9]{36}' -e 'xox[abprs]-[A-Za-z0-9-]{10,}' \
  -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' -e 'moatleak-private' \
  -- "${files[@]}" >"$hits"; rc1=$?
grep -noIH -E -e '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' -- "${files[@]}" \
  | grep -viE '@example\.(com|org|net)$' >>"$hits"; rc2=("${PIPESTATUS[@]}")
set -e
# grep: 0=match 1=none >=2=error. Errors must fail the gate.
if [ $rc1 -ge 2 ] || [ ${rc2[0]} -ge 2 ] || [ ${rc2[1]} -ge 2 ]; then echo 'PRIVACY SCAN ERROR (grep failed)'; exit 1; fi
if [ -s "$hits" ]; then cat "$hits"; echo 'PRIVACY SCAN FAILED'; exit 1; fi
$PY scripts/privacy_keys.py || { echo 'PRIVACY KEY SCAN FAILED'; exit 1; }
echo 'check.sh: OK'
