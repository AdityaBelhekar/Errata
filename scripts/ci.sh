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
# 4. The frontend
# ---------------------------------------------------------------------------------------------
#
# Until this section existed, `scripts/ci.sh` had no reference to web/, to npm, or to either
# design gate -- so both gates could be broken by any commit and nothing would notice. The test
# register called that out as blocker B-2, and it was right: 1,335 Python tests covered the domain
# and zero covered what a user touches.
#
# These steps live HERE rather than in the workflow file, for the reason stated at the top of this
# script: a pipeline that only exists as YAML is a second, invisible definition of correct.

step "design -- token lint (LAW: colour, spacing, motion)" "$PY" web/datum/tools/lint-tokens.py
step "design -- contrast law" "$PY" web/datum/tools/contrast.py

# The public site is generated from one shell so eight pages cannot drift into eight navs. The
# generated files are committed because a Python-only install has no Node and the console serves
# them as static files -- so this checks that what is committed is what the generator produces.
step "site -- generated pages are current" "$PY" web/site/build.py --check

if command -v npm >/dev/null 2>&1; then
    # `npm ci`, never `npm install`: ci fails on a lockfile that disagrees with package.json,
    # which is the difference between a reproducible install and a hopeful one.
    step "frontend -- install (npm ci)" bash -c 'cd web/app && npm ci --no-audit --no-fund'
    step "frontend -- typecheck" bash -c 'cd web/app && npx tsc --noEmit'
    step "frontend -- unit (vitest)" bash -c 'cd web/app && npm run test:unit'
    step "frontend -- dependency audit" bash -c 'cd web/app && npm audit --omit=dev --audit-level=high'
    step "frontend -- build" bash -c 'cd web/app && npm run build'

    # web/landing/ is BUILT OUTPUT that is committed, because the Python console serves it and a
    # Python-only install cannot rebuild it. The register warned that committed build output
    # drifts from its source the first time someone edits one without rebuilding -- and it had
    # already happened: an accessibility fix sat in web/app/src for a full run before anyone
    # noticed the served page still carried the old bundle.
    #
    # The build above just regenerated it. If that changed anything, the committed copy was stale.
    step "frontend -- committed build output is not stale" bash -c '
        if ! git diff --quiet -- web/landing; then
            echo "web/landing/ is stale. `cd web/app && npm run build` and commit the result." >&2
            git --no-pager diff --stat -- web/landing >&2
            exit 1
        fi
        echo "web/landing matches its source"
    '

    # Playwright needs browsers, which are a ~150MB download rather than an npm package. A runner
    # without them skips rather than fails -- the same treatment var/ gets above, and for the same
    # reason: a step that cannot run is not a step that failed.
    # All four projects, not just chromium: the config runs chromium, firefox, webkit and a
    # mobile profile, and a guard that checks one of them lets the other three fail as "missing
    # executable" -- 176 such failures in the first run of this section, which is noise that hides
    # whatever real failure sits underneath it.
    if bash -c 'cd web/app && npx playwright install --dry-run chromium firefox webkit' >/dev/null 2>&1; then
        step "frontend -- e2e, axe and visual diff" bash -c 'cd web/app && npm run test:e2e'
    else
        echo
        echo "==> Playwright browsers absent; skipping the browser gates."
        echo "    Run: cd web/app && npx playwright install"
    fi
else
    echo
    echo "==> npm not found; skipping the frontend gates."
    echo "    The design lints above still ran -- they are Python."
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
