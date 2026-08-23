#!/usr/bin/env python3
"""Fetch only the reference artifacts the reviewer console needs to boot.

``scripts/fetch_reference_data.sh`` reconstructs the whole corpus and runs under ``set -e``, so
one unreachable publisher aborts the run. Two of them are unreachable as of 23 August 2026 --
``everyspec.com`` and ``data.ok.gov`` both answer 403 to an automated request -- and neither
serves anything ``errata-audit serve`` reads. On a deploy that script therefore fails the build
over files the running service never opens.

This fetches the three that the console does need, and nothing else:

    etim-10.0-all-sectors-csv-metric   the class model  -> var/reference/etim/
    abb-s200-2CDC002142D0207           a datasheet      -> var/spike/datasheets/
    abb-s200muc-1SXP403008B0202        a datasheet      -> var/spike/datasheets/

Every file is still checked against the sha256 in ``data/reference/manifest.json`` before it is
kept, which is the property that matters: this is a smaller fetch, not a less verified one. A
hash mismatch is a hard failure exactly as it is in the shell script -- an upstream document that
CHANGED is a finding (FR-1.3), and a deploy is not the place to discover it quietly.

    python scripts/fetch_deploy_data.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "data" / "reference" / "manifest.json"

#: What the console reads. Listed rather than inferred: a deploy that silently starts depending
#: on a fourth document should fail here, where the reason is obvious, rather than at boot.
NEEDED = (
    "etim-10.0-all-sectors-csv-metric",
    "abb-s200-2CDC002142D0207",
    "abb-s200muc-1SXP403008B0202",
)

TIMEOUT = 600


def _artifacts(node: object) -> list[dict]:
    """Every leaf in the manifest that carries a url, wherever it sits in the tree."""
    found: list[dict] = []
    if isinstance(node, dict):
        if "url" in node:
            found.append(node)
        else:
            for value in node.values():
                found.extend(_artifacts(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_artifacts(value))
    return found


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "errata-deploy/1.0"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_id = {a.get("id"): a for a in _artifacts(manifest)}

    missing_ids = [name for name in NEEDED if name not in by_id]
    if missing_ids:
        print(f"manifest has no entry for: {', '.join(missing_ids)}", file=sys.stderr)
        return 1

    for name in NEEDED:
        artifact = by_id[name]
        url = artifact["url"]
        expected = artifact["sha256"]
        dest_dir = REPO_ROOT / artifact["dest"]
        filename = artifact.get("filename") or url.rsplit("/", 1)[-1]
        dest = dest_dir / filename
        dest_dir.mkdir(parents=True, exist_ok=True)

        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == expected:
            print(f"==> {name}: already present, hash verified")
        else:
            print(f"==> {name}: fetching\n    {url}")
            payload = _download(url)
            got = hashlib.sha256(payload).hexdigest()
            if got != expected:
                print(
                    f"    HASH MISMATCH\n      expected {expected}\n      got      {got}\n"
                    "    Refusing to keep it. The published document changed, or something is "
                    "between us and the publisher.",
                    file=sys.stderr,
                )
                return 1
            dest.write_bytes(payload)
            print(f"    hash verified: {got}")

        # The ETIM release ships as a zip and the loader reads the extracted CSVs beside it.
        if dest.suffix == ".zip":
            extracted = dest_dir / "extracted"
            if not extracted.exists():
                extracted.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(dest) as archive:
                    archive.extractall(extracted)
                print(f"    unpacked -> {extracted.relative_to(REPO_ROOT)}")

    print("\nconsole reference data ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
