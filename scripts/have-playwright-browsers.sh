#!/usr/bin/env bash
#
# Are the Playwright browsers actually on this machine?
#
#   bash scripts/have-playwright-browsers.sh   -> exit 0 present, exit 1 absent
#
# This exists because the check it replaces did not work. scripts/ci.sh guarded its browser
# gates with:
#
#     npx playwright install --dry-run chromium firefox webkit
#
# `--dry-run` PRINTS what it would download and exits 0 whether or not a single browser is on
# disk. So the guard always said "present", the e2e step always ran, and on a machine with no
# browsers every test failed on `browserType.launch: Executable doesn't exist` -- 429 of them.
# That is precisely the noise the guard was introduced to prevent.
#
# What --dry-run prints that IS usable is one "Install location:" line per browser, covering
# the pieces a version check would miss -- chromium_headless_shell and ffmpeg are separate
# downloads from chromium itself, and the headless shell is what `headless: true` actually
# launches. This checks every path it names.
#
# node performs the existence test rather than `[[ -e ]]`: the paths come back in native
# Windows form (C:\Users\...\ms-playwright\chromium-1234) and bash tests on those are
# unreliable under Git Bash, which is the shell scripts/ci.sh runs in on Windows.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

command -v npx >/dev/null 2>&1 || exit 1
command -v node >/dev/null 2>&1 || exit 1

cd "$ROOT/web/app" || exit 1

npx playwright install --dry-run chromium firefox webkit 2>/dev/null \
    | sed -n 's/^[[:space:]]*Install location:[[:space:]]*//p' \
    | sed 's/[[:space:]]*$//' \
    | node "$ROOT/scripts/browsers-present.mjs"
