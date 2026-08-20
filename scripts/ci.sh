#!/usr/bin/env bash
#
# Errata -- the build. Everything that must be true, in one command.
#
#   bash scripts/ci.sh              full run
#   bash scripts/ci.sh --fast       skip the steps that need fetched reference data
#
# This file exists because NFR-7's acceptance criterion is "CI licence check on every build" and
# there was no build. Every honesty mechanism in this repository -- the frozen-split guard, the
# ECLASS content scanner, the licence check, the reproduction receipt -- ran only when somebody
# remembered to type `pytest`. A guard that runs when remembered is a comment with a test framework
# attached.
#
# The same script runs locally and in CI on purpose. A CI pipeline that is a YAML file nobody can
# execute is a second, invisible definition of "correct" that drifts from the first one.
#
# Exit codes: 0 everything passed. 1 something failed. The step that failed is named.

set -uo pipefail
cd "$(dirname "$0")/.."

FAST=0
[[ "${1:-}" == "--fast" ]] && FAST=1

if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    PY=".venv/Scripts/python.exe"
    BIN=".venv/Scripts"
else
    PY=".venv/bin/python"
    BIN=".venv/bin"
fi
[[ -x "$PY" ]] || { echo "No virtualenv. Run scripts/setup.sh first." >&2; exit 1; }

FAILURES=()
step() {
    local name="$1"; shift
    echo
    echo "=============================================================================="
    echo "==> $name"
    echo "=============================================================================="
    if "$@"; then
        echo "--- PASS: $name"
    else
        echo "--- FAIL: $name" >&2
        FAILURES+=("$name")
    fi
}

# ---------------------------------------------------------------------------------------------
# 1. The code itself
# ---------------------------------------------------------------------------------------------

step "ruff -- lint" "$PY" -m ruff check .
# `ruff format --check` is NOT run. The repository was never formatter-managed -- 85 of its 178
# files would be rewritten -- and turning it on here would bury every real change in this build
# under a reformatting diff nobody reviewed. Adopting the formatter is a decision with its own
# commit, not a side effect of introducing CI. Lint is gated; layout is not.

# mypy is installed and, until this file existed, had never been run in anger. It is NOT gating
# yet: turning a type checker on over 12k lines for the first time produces a wall of findings, and
# a wall of findings that blocks the build gets switched off within a day. It runs, it prints, and
# the exit code is ignored -- deliberately and visibly, rather than by being absent.
echo
echo "=============================================================================="
echo "==> mypy -- advisory, NOT gating (see scripts/ci.sh for why)"
echo "=============================================================================="
"$PY" -m mypy --ignore-missing-imports \
    valuesem/src spec/src comparator/src bench/src audit/src scale/src ecosystem/src \
    2>&1 | tail -30 || true
echo "--- advisory only; exit code deliberately ignored"

step "pytest -- the whole suite" "$PY" -m pytest -q

# ---------------------------------------------------------------------------------------------
# 2. The guards that were only ever run by hand
# ---------------------------------------------------------------------------------------------

step "NFR-7 -- licence hygiene" "$BIN/errata-r3" licences
step "FR-9.6 -- the frozen hard-tail split is untouched" "$BIN/errata-r3" split verify
step "FR-9.8 / ADR-003 -- no ECLASS content in the tree" "$BIN/errata-r3" eclass scan

# The check that actually matters for FR-9.8: what `python -m build` put in the wheel. A clean
# working tree says nothing about package-data globs.
step "FR-9.8 -- no ECLASS content in the BUILT distributions" bash -c '
    set -e
    rm -rf var/ci/dist && mkdir -p var/ci/dist
    for d in valuesem spec comparator bench audit scale ecosystem; do
        '"$PY"' -m build --outdir var/ci/dist "$d" >/dev/null
    done
    '"$PY"' - <<PYEOF
from pathlib import Path
from errata_ecosystem.eclass import assert_clean, scan_distribution
built = sorted(Path("var/ci/dist").glob("*"))
assert built, "nothing was built"
assert_clean([scan_distribution(p) for p in built])
print(f"scanned {len(built)} built distribution(s): clean")
PYEOF
'

# ---------------------------------------------------------------------------------------------
# 3. The numbers
# ---------------------------------------------------------------------------------------------

if [[ "$FAST" -eq 1 ]]; then
    echo
    echo "==> --fast: skipping the steps that need fetched reference data"
else
    # These need var/, which is gitignored and reconstructed by scripts/fetch_reference_data.sh.
    # A runner without it skips them rather than failing: the reference corpus is ABB's and ETIM's,
    # not ours to guarantee the availability of (FR-9.5).
    if [[ -d var/spike/datasheets ]] && compgen -G "var/spike/datasheets/*.pdf" >/dev/null; then
        step "R0 gate 1 -- the equivalence suite" "$BIN/errata-r0" equivalence
        step "R3 -- reproduce the published numbers" "$BIN/errata-r3" reproduce
        step "R3 -- the gold set re-derives from the documents" "$BIN/errata-r3" gold verify
    else
        echo
        echo "==> reference data absent; skipping the measured gates."
        echo "    Run: bash scripts/fetch_reference_data.sh"
    fi
fi

# ---------------------------------------------------------------------------------------------

echo
echo "=============================================================================="
if [[ ${#FAILURES[@]} -eq 0 ]]; then
    echo "BUILD PASSED"
    exit 0
fi
echo "BUILD FAILED -- ${#FAILURES[@]} step(s):" >&2
printf '  %s\n' "${FAILURES[@]}" >&2
exit 1
