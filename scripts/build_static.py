#!/usr/bin/env python3
"""Assemble the static site Vercel serves, into ``public/``.

Every page in this repository links with ABSOLUTE paths -- ``/web/landing/assets/...``,
``/web/site/``, ``/web/datum/`` -- because the Python console serves them as static files from
the repository root and the e2e suite drives them the same way. So the deployed tree has to keep
that shape: publishing ``web/landing`` alone at the domain root would break every asset URL on
the page.

    public/
      index.html          -> redirects to /web/landing/
      web/landing/        the built React landing page (vite output, committed)
      web/site/           the eight generated marketing pages
      web/datum/          the design system pages, fonts and styles

``/web/console/`` is deliberately NOT here: that is the reviewer console, which is a Python
service on Render. ``vercel.json`` rewrites that prefix to the Render origin so both halves sit
behind one domain.

    python scripts/build_static.py

Run ``cd web/app && npm ci && npm run build`` first if ``web/landing`` is stale -- the Vercel
build command does both in order.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "public"

#: Copied verbatim, preserving the ``web/<name>`` prefix the pages link against.
TREES = ("landing", "site", "datum")

REDIRECT = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Errata</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="/web/landing/">
<meta http-equiv="refresh" content="0; url=/web/landing/">
<script>location.replace('/web/landing/' + location.search + location.hash);</script>
</head>
<body>
<p>Continue to <a href="/web/landing/">Errata</a>.</p>
</body>
</html>
"""


def main() -> int:
    # .vercel/ holds the project link (projectId, orgId). Wiping it silently unlinks the
    # directory, and the next `vercel deploy` cheerfully creates a NEW project named after the
    # folder -- "public" -- instead of updating the real one. Preserved across the rebuild.
    link = OUT / ".vercel"
    saved = None
    if link.is_dir():
        saved = Path(tempfile.mkdtemp(prefix="vercel-link-")) / ".vercel"
        shutil.copytree(link, saved)

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "web").mkdir(parents=True)

    if saved is not None:
        shutil.copytree(saved, OUT / ".vercel")
        shutil.rmtree(saved.parent, ignore_errors=True)

    for name in TREES:
        source = REPO_ROOT / "web" / name
        if not source.is_dir():
            print(f"missing {source.relative_to(REPO_ROOT)}", file=sys.stderr)
            return 1
        shutil.copytree(source, OUT / "web" / name)
        count = sum(1 for p in (OUT / "web" / name).rglob("*") if p.is_file())
        print(f"  web/{name:<9} {count:>4} files")

    (OUT / "index.html").write_text(REDIRECT, encoding="utf-8")

    # The routing config travels WITH the output, because public/ is gitignored and this
    # is a prebuilt deploy:  reads vercel.json from the directory it is
    # given. Without this copy the console rewrite and the cache headers are lost on the
    # first rebuild, silently -- the site still serves, and /web/console/ 404s.
    shutil.copy2(REPO_ROOT / "web" / "static-vercel.json", OUT / "vercel.json")

    total = sum(1 for p in OUT.rglob("*") if p.is_file())
    print(f"\npublic/ ready -- {total} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
