#!/usr/bin/env bash
#
# Errata -- reference-data fetcher.
#
#   bash scripts/fetch_reference_data.sh
#
# Reconstructs the reference corpus described by data/reference/manifest.json into
# var/reference/ (gitignored). Verifies each artifact's sha256 against the manifest
# BEFORE unpacking, and refuses to proceed on a mismatch -- a changed upstream file
# is a finding, not something to absorb silently (FR-1.3).
#
# Idempotent: an artifact already present with the right hash is not re-downloaded.
#
# This is the FR-9.5 pattern applied to our own inputs: the repository carries URLs
# and content hashes, never the payload.
#
# Licence note: ETIM 10.0 is Open Data Commons Attribution (ODC-By). Attribution is
# required wherever its content is surfaced. See NOTICE.

set -euo pipefail
cd "$(dirname "$0")/.."

MANIFEST="data/reference/manifest.json"
DEST_ROOT="var/reference"

if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    PY=".venv/Scripts/python.exe"
else
    PY=".venv/bin/python"
fi
[[ -x "$PY" ]] || { echo "No virtualenv. Run scripts/setup.sh first." >&2; exit 1; }

# Emit "id<TAB>url<TAB>sha256<TAB>dest", one artifact per line. Python is told to use
# "\n" verbatim: on Windows it otherwise rewrites newlines and leaves a stray carriage
# return on the last field, which then corrupts every path built from it.
"$PY" - "$MANIFEST" <<'PYEOF' | while IFS=$'\t' read -r id url sha dest name; do
import json, posixpath, sys, urllib.parse
sys.stdout.reconfigure(newline="\n")
for a in json.load(open(sys.argv[1], encoding="utf-8"))["artifacts"]:
    # Mirrors often serve a generic basename ("data.csv"). An artifact may name the file it
    # should land as; otherwise take the last path segment of the URL.
    fn = a.get("filename") or posixpath.basename(urllib.parse.urlparse(a["url"]).path)
    print("\t".join([a["id"], a["url"], a["sha256"], a["dest"], fn]))
PYEOF
    file="${dest}${name}"
    mkdir -p "$dest"

    if [[ -f "$file" ]] && [[ "$(sha256sum "$file" | cut -d' ' -f1)" == "$sha" ]]; then
        echo "==> ${id}: already present, hash verified"
    else
        echo "==> ${id}: fetching"
        echo "    $url"
        curl -fsSL --max-time 900 -o "$file" "$url"
        got="$(sha256sum "$file" | cut -d' ' -f1)"
        if [[ "$got" != "$sha" ]]; then
            echo "!!! SHA256 MISMATCH for ${id}" >&2
            echo "    expected $sha" >&2
            echo "    got      $got" >&2
            echo "    Upstream changed. Do NOT edit the manifest to make this pass --" >&2
            echo "    investigate, then record a new revision linked to the prior (FR-1.3)." >&2
            exit 1
        fi
        echo "    hash verified: $got"
    fi

    if [[ "$file" == *.zip ]]; then
        unzip -o -q "$file" -d "${dest}extracted"
        echo "    unpacked -> ${dest}extracted"
    fi
done

echo
echo "Reference data ready under ${DEST_ROOT}/."
echo "Gaps that are NOT obtainable are enumerated in ${MANIFEST} under \"not_obtained\"."
