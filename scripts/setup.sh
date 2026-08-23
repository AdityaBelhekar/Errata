#!/usr/bin/env bash
#
# Errata -- one-command environment setup.
#
#   bash scripts/setup.sh
#
# Idempotent: safe to re-run. Creates .venv/, installs the pinned third-party set
# from requirements-lock.txt, installs the seven Errata distributions editable in
# dependency order, builds the R2 demonstration corpus, then verifies the install by
# running the full test suite and reproducing the R0 gate-1 number.
#
# Requires: Python >= 3.11 on PATH (verified on 3.14.3).

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    PY=".venv/Scripts/python.exe"
    BIN=".venv/Scripts"
else
    PY=".venv/bin/python"
    BIN=".venv/bin"
fi

echo "==> [1/5] virtualenv"
if [[ ! -x "$PY" ]]; then
    (command -v py >/dev/null 2>&1 && py -3 -m venv .venv) || python3 -m venv .venv || python -m venv .venv
fi
"$PY" --version

echo "==> [2/5] build toolchain"
"$PY" -m pip install --quiet --upgrade pip setuptools wheel

echo "==> [3/5] pinned third-party dependencies"
"$PY" -m pip install --quiet -r requirements-lock.txt

echo "==> [4/6] Errata distributions (editable, dependency order)"
# valuesem has no intra-repo dependency; spec none; comparator needs both; bench needs all three;
# audit (R1) needs spec, valuesem and comparator; scale (R2) needs audit; ecosystem (R3) needs
# bench for the grounding metric it reuses verbatim and audit/scale for the axes it scores.
# bundle owns the page projection (FE-2.5 G-1) and errata-audit imports it, so it is a real
# dependency rather than an optional extra. Leaving it out of this list is what made
# `import errata_audit` fail on a clean checkout while every declared dependency looked met.
"$PY" -m pip install --quiet --no-deps -e ./valuesem -e ./spec -e ./comparator -e ./bench -e ./audit -e ./scale -e ./ecosystem -e ./bundle

echo "==> [5/6] R2 demonstration corpus"
# Generated rather than committed: ten thousand rows of constructed catalog is not source, and a
# repository that commits fixtures at that size teaches everyone to stop reading diffs. The
# generator is deterministic (content-hash mutation, no RNG), so this reproduces byte for byte.
"$PY" scale/tools/build_scale_catalog.py

echo "==> [6/6] verification"
"$PY" -m pytest -q

# `errata-r0 status` returns max(gate codes), and EXIT_INCONCLUSIVE is 3. Gates 2 and 3 are
# NOT MEASURED by design -- deferred on the recorded waiver in PHASES.md §10 -- so a healthy
# install exits 3 here, and under `set -e` that aborted setup before it could say so. The
# status is printed for the reader; it is the pytest line above that gates this script.
"$BIN/errata-r0" status || true

echo
echo "Setup complete."
echo "  tests      : $PY -m pytest -q"
echo "  R0 gates   : $BIN/errata-r0 status"
echo "  demo       : $BIN/errata-demo"
echo "  demo (html): $BIN/errata-demo --html report.html"
echo "  R1 audit   : $BIN/errata-audit sku --random"
echo "  R1 console : $BIN/errata-audit sku --random --html console.html"
echo "  R2 audit   : $BIN/errata-scale run"
echo "  R3 scores  : $BIN/errata-r3 reproduce"
echo "  R3 board   : $BIN/errata-r3 leaderboard --html var/r3/leaderboard.html"
echo "  R2 report  : $BIN/errata-scale run --html var/scale/report.html"
echo "  R2 status  : $BIN/errata-scale status"
