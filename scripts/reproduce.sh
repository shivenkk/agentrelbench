#!/usr/bin/env bash
# One-command analysis-level reproduction of the paper's results.
#
# Scope: released merged verdicts -> tested estimators -> all four figures and
# every headline number in Section 5. This does NOT re-run the instrument: that
# needs the EnterpriseOps-Gym containers and provider credentials, and is
# documented separately in the README. Re-running would also be the wrong thing
# to do here, because the campaign numbers are records of runs that already
# happened and the runs are stochastic by the paper's own finding.
#
# Every step below fails loudly. There is no step whose output a human has to
# eyeball to know whether it passed.
#
# Usage: scripts/reproduce.sh            (creates .reproduce-venv/)
#        VENV=/tmp/v scripts/reproduce.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

VENV="${VENV:-$REPO/.reproduce-venv}"
PY="${PYTHON:-python3}"

echo "== 1/5 environment =="
"$PY" --version
rm -rf "$VENV"
"$PY" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet ".[figures]"
echo "  installed agentrelbench + figure dependencies into $VENV"

echo "== 2/5 released data present =="
python - <<'PY'
import hashlib, json, sys
from pathlib import Path
missing, bad = [], []
for man in sorted(Path("runs").glob("**/*.manifest.json")):
    m = json.loads(man.read_text())
    data = Path("runs") / m["file"]
    if not data.exists():
        missing.append(m["file"]); continue
    got = hashlib.sha256(data.read_bytes()).hexdigest()
    if got != m["sha256"]:
        bad.append(f'{m["file"]}: sha256 {got[:12]} != recorded {m["sha256"][:12]}')
    rows = sum(1 for _ in data.open())
    if rows != m["rows"]:
        bad.append(f'{m["file"]}: {rows} rows != recorded {m["rows"]}')
if missing or bad:
    for x in missing: print(f"  MISSING {x}")
    for x in bad: print(f"  CORRUPT {x}")
    sys.exit(1)
print(f"  {len(list(Path('runs').glob('**/*.manifest.json')))} released files match their manifests (sha256 + row count)")
PY

echo "== 3/5 estimator test suite =="
python -m pip install --quiet ".[dev]"
python -m pytest -q tests/test_estimators.py tests/test_audit_numbers.py tests/test_task_staging.py

echo "== 4/5 regenerate figures and Appendix E (asserts every Section 5 number) =="
python scripts/make_figures.py
python scripts/make_appendix_e.py

echo "== 5/5 audit the manuscript's numbers against the run data =="
python scripts/audit_numbers.py

echo
echo "REPRODUCE OK: figures regenerated, Appendix E tables regenerated, and every"
echo "Section 5 number re-derived from the released verdicts under assertions."
