#!/usr/bin/env python
"""Generate the public site from one shell and one page per content file.

Why a generator and not eight hand-written pages
------------------------------------------------

There were two pages and they had already drifted: ``index.html`` linked its
stylesheets relatively (``../datum/styles/``) and ``404.html`` absolutely
(``/web/datum/styles/``). Two pages, one difference, and the difference is the
one that breaks a 404 served from a nested path -- which is the only path a 404
is ever served from.

That is the whole argument. A nav repeated by hand across eight pages is eight
chances to update seven of them, and the failure is invisible until someone
lands on the eighth. So the shell lives here once, and the pages are content.

The generated files ARE committed. The Python console serves ``web/`` as static
files (FE-SYSTEM-REVIEW §4, Q1 -> C, recorded in ``web/app/vite.config.ts``), and
a Python-only install has no Node and no way to run a build. Committing the
output means the thing that ships is the thing in the tree.

Committed build output drifts from its source -- the test register says so and it
is right. So ``--check`` re-renders and compares, and ``scripts/ci.sh`` runs it.
The drift becomes a failing build instead of a surprise.

    python web/site/build.py            write the pages
    python web/site/build.py --check    fail if what is committed is stale
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"

#: Every stylesheet and script is referenced from the server root, never relatively. A relative
#: path resolves against the current URL, so the same markup means different files on `/web/site/`
#: and on a 404 served from `/anything/deep/`. This is the drift that prompted the generator.
BASE = "/web"


@dataclass(frozen=True)
class Page:
    """One page: what it is called, what it says, and whether it is navigable."""

    slug: str
    title: str
    description: str
    nav_label: str = ""
    """Empty means the page exists but is not in the primary nav -- 404 and 500 are reachable by
    happening to you, not by being chosen."""

    main_class: str = "shell rhythm-l"
    robots: str = ""
    footer: str = "ERRATA · DATUM v1.0"
    scene: bool = False
    """Pages whose hero is the WebGL procession. They carry the `nogl` init line."""

    status: str = ""
    """A banner stating what this page is NOT, printed above the content.

    Most of these pages describe work that is partly unbuilt or unmeasured. FR-9.1 exists to stop
    a target being published as a measurement, and the same rule applies to a page: if a surface
    would leave a reader believing something is finished when it is not, the page says so on its
    face. Not in a footnote -- readers do not read footnotes and the ones who do are not the ones
    the claim would mislead.
    """


#: Order here is the order in the nav.
PAGES: tuple[Page, ...] = (
    Page(
        slug="index",
        title="Errata — your catalog is a reflection",
        description=(
            "A verification layer for industrial product data. It grades data. "
            "It does not create data."
        ),
        nav_label="Home",
        main_class="",
        footer=(
            "ERRATA · DATUM v1.0 · THE STILL WATER — nothing on this page is a shipped surface."
        ),
    ),
    Page(
        slug="method",
        title="Errata — method",
        description="How a value becomes evidence, and where the system refuses to answer.",
        nav_label="Method",
    ),
    Page(
        slug="benchmark",
        title="Errata — benchmark",
        description="What has been measured, against what, and what the numbers do not show.",
        nav_label="Benchmark",
        status=(
            "R0 gate 2 is measured and its asymmetry is <strong>not confirmed</strong>. "
            "Gate 3 is not measured at all. This page reports that rather than working around it."
        ),
    ),
    Page(
        slug="errata",
        title="Errata — errata",
        description="Defects found in this product, by us, published before anyone asks.",
        nav_label="Errata",
    ),
    Page(
        slug="pricing",
        title="Errata — pricing",
        description="What it costs, and what the cost depends on.",
        nav_label="Pricing",
        status=(
            "FR-8.7's tiered execution and cost report are <strong>not built</strong>. "
            "Every figure below is an intention, not a quote."
        ),
    ),
    Page(
        slug="docs",
        title="Errata — documentation",
        description="Running it, reading its output, and checking its work.",
        nav_label="Docs",
    ),
    Page(
        slug="404",
        title="Errata — not found",
        description="",
        main_class="shell rhythm-l poche",
        robots="noindex",
    ),
    Page(
        slug="500",
        title="Errata — something failed",
        description="",
        main_class="shell rhythm-l poche",
        robots="noindex",
    ),
)

#: Surfaces that are not pages of this site but must be reachable from it.
EXTERNAL_NAV: tuple[tuple[str, str], ...] = (
    ("Console", f"{BASE}/console/"),
    ("Design system", f"{BASE}/datum/"),
)


def _nav(current: Page) -> str:
    """The primary nav.

    Mobile collapse is a ``<details>`` element rather than a scripted disclosure. It opens with no
    JavaScript, it is focusable and operable from the keyboard without any code of ours, and it
    announces its own expanded state to a screen reader -- three things a scripted `div` gets wrong
    by default. L-7 says navigation is keyboard-reachable with the canvas deleted; the cheapest way
    to keep that true is not to write the widget.
    """
    links = []
    for page in PAGES:
        if not page.nav_label:
            continue
        href = f"{BASE}/site/" if page.slug == "index" else f"{BASE}/site/{page.slug}.html"
        current_attr = ' aria-current="page"' if page.slug == current.slug else ""
        links.append(f'<a href="{href}"{current_attr}>{page.nav_label}</a>')
    for label, href in EXTERNAL_NAV:
        links.append(f'<a href="{href}">{label}</a>')

    link_html = "\n      ".join(links)
    return f"""<nav class="site-nav" aria-label="Primary">
  <a class="wordmark" href="{BASE}/site/">ERRATA</a>

  <details class="nav-disclosure">
    <summary class="t-micro" aria-label="Menu">Menu</summary>
    <div class="nav-links t-micro">
      {link_html}
    </div>
  </details>

  <div class="theme-toggle" data-theme-toggle>
    <button type="button" data-mode="system">Sys</button>
    <button type="button" data-mode="light">Light</button>
    <button type="button" data-mode="dark">Dark</button>
  </div>
</nav>"""


def _head(page: Page) -> str:
    nogl = (
        "\n    if (new URLSearchParams(location.search).get('nogl') === '1')"
        "\n      document.documentElement.setAttribute('data-gl', 'off');"
        if page.scene
        else ""
    )
    description = (
        f'\n<meta name="description" content="{page.description}">' if page.description else ""
    )
    robots = f'\n<meta name="robots" content="{page.robots}">' if page.robots else ""

    # The theme script is INLINE and must stay inline: it runs before first paint to set
    # `data-theme`, and a linked file would paint the wrong theme first and correct it, which is
    # the flash §6.6 exists to prevent.
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page.title}</title>{description}{robots}

<script>
(function () {{
  try {{
    var t = localStorage.getItem('errata-theme');
    if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);{nogl}
  }} catch (e) {{}}
}})();
</script>

<link rel="stylesheet" href="{BASE}/datum/styles/tokens.css">
<link rel="stylesheet" href="{BASE}/datum/styles/type.css">
<link rel="stylesheet" href="{BASE}/datum/styles/base.css">
<link rel="stylesheet" href="{BASE}/datum/styles/components.css">
<link rel="stylesheet" href="{BASE}/site/shell.css">
<link rel="stylesheet" href="{BASE}/site/site.css">"""


def render(page: Page) -> str:
    body = (CONTENT / f"{page.slug}.html").read_text(encoding="utf-8").rstrip()
    main_class = f' class="{page.main_class}"' if page.main_class else ""

    status = ""
    if page.status:
        status = (
            '\n<div class="status-banner t-micro" role="note">\n'
            f"  {page.status}\n"
            "</div>\n"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<!-- GENERATED by web/site/build.py from content/{page.slug}.html. Do not edit this file:
     edit the content file or the generator. `python web/site/build.py --check` fails the
     build when this file and its source disagree. -->
{_head(page)}
</head>

<body class="datum-field">

<a class="skip-link t-body" href="#main">Skip to content</a>

<!-- §8.1 LAW — the datum appears on every page, 404 and 500 included. Not decoration: a page
     that drops the system's spine has stopped being part of the product at the moment the
     reader most needs to believe it still is. -->
<div class="datum" aria-hidden="true"></div>

{_nav(page)}
{status}
<main id="main"{main_class}>
{body}
</main>

<footer class="shell site-footer t-micro">
  {page.footer}
</footer>

<script src="{BASE}/datum/theme.js"></script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit non-zero if any committed page is stale",
    )
    args = parser.parse_args()

    stale: list[str] = []
    for page in PAGES:
        target = ROOT / f"{page.slug}.html"
        rendered = render(page)
        if args.check:
            existing = target.read_text(encoding="utf-8") if target.exists() else ""
            if existing != rendered:
                stale.append(page.slug)
        else:
            target.write_text(rendered, encoding="utf-8")
            print(f"  wrote {target.relative_to(ROOT.parent.parent)}")

    if args.check:
        if stale:
            print(
                "These committed pages disagree with the generator: " + ", ".join(stale),
                file=sys.stderr,
            )
            print("Run: python web/site/build.py", file=sys.stderr)
            return 1
        print(f"all {len(PAGES)} pages are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
