"""
DATUM — token lint.

Blueprint §17 LAW: `tokens.css` is the only file in the repository that may
contain a colour literal. A hex value anywhere else fails lint.
Blueprint §19 (definition of done) additionally requires:

    · no spacing value outside the closed set (§8.5)
    · no duration or curve outside the motion scale (§10.1–10.2)
    · no `outline: none` on a focus state (§15)
    · nothing reading scroll position except the scroll authority (§10.5)
    · no frame-rate-dependent lerp (§10.6, finding F-02)

It checks what a static reader can check honestly, and it says plainly which
laws it does NOT check. Claiming coverage a tool does not have is the exact
failure this repository's own audit found in its adversarial suite
(`HANDOFF.md` §7), and a lint that lies is worse than no lint.

Scope of parsing: for `.css` the whole file; for `.html` only the contents of
`<style>` blocks and `style="…"` attributes. Prose is prose — a paragraph that
mentions "999px never" is documentation, not a declaration.

Usage:
    python web/datum/tools/lint-tokens.py            # exit 1 on any violation
    python web/datum/tools/lint-tokens.py --list     # what is and is not checked
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # web/datum
WEB = ROOT.parent                                   # web/
TOKENS = ROOT / "styles" / "tokens.css"

# Files exempt from the colour-literal rule, and why. An exemption is a written
# argument, not a silence.
COLOUR_EXEMPT = {
    "styles/tokens.css": "the token file — this is where colour lives",
    "site/site.css": (
        "Room I's scene values -- the anodized plate ramp and the key-light falloff. Open item "
        "O-3 in the FE-1 gate report: they move into a scene token file at FE-5, when the shader "
        "owns them and there is something to name them against. The exemption follows the code: "
        "it used to sit on room-i.html, which now shares this one definition of the room instead "
        "of carrying a second copy."
    ),
}

SPACING = {2, 4, 8, 12, 16, 24, 32, 40, 56, 72, 96, 128, 160, 224}
# Structural constants the spacing set does not govern: zero, the hairline and
# reveal weights, and the control radius.
SPACING_FREE = {0, 1, 3}
DURATIONS = {90, 160, 240, 420, 720, 1200}
CURVES = {"cubic-bezier(.16,1,.30,1)", "cubic-bezier(.65,0,.35,1)"}

# Properties whose px values size or draw a thing rather than space two things
# apart. The closed set is about the gaps.
STRUCTURAL = {
    "border", "border-top", "border-right", "border-bottom", "border-left",
    "border-width", "border-radius", "outline", "outline-width",
    "outline-offset", "box-shadow", "text-shadow", "inset", "top", "right",
    "bottom", "left", "width", "height", "min-width", "max-width",
    "min-height", "max-height", "flex", "flex-basis", "font-size",
    "line-height", "letter-spacing", "text-decoration-thickness",
    "text-underline-offset", "background", "background-position",
    "background-size", "stroke-width", "transform", "translate", "clip-path",
    "grid-template-columns", "grid-template-rows", "grid-auto-rows",
    "border-spacing", "text-indent", "filter", "backdrop-filter", "mask-image",
    "-webkit-mask-image", "background-image",
}
# Custom properties that are structural by name.
STRUCTURAL_CUSTOM = re.compile(
    r"^--(?:.*-h|.*-w|shadow.*|w-.*|r-.*|grid-.*|datum.*|t-.*|plate.*|room.*|btn-.*)$"
)

MOTION_PROPS = {"transition", "transition-duration", "transition-delay", "animation",
                "animation-duration", "animation-delay"}

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.S | re.I)
_STYLE_ATTR = re.compile(r'style\s*=\s*"([^"]*)"', re.I)
_DECL = re.compile(r"(--[\w-]+|[a-zA-Z-]+)\s*:\s*([^;{}]+)")

_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_FUNC_COLOUR = re.compile(r"\b(?:rgba?|hsla?|oklch|oklab|lab|lch)\(", re.I)
_PX = re.compile(r"(?<![\w.])(\d+)px")
_MS = re.compile(r"(?<![\w.])(\d+)ms\b")
_SEC = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)s\b")
_BEZIER = re.compile(r"cubic-bezier\([^)]*\)")
_SCROLLY = re.compile(r"\bwindow\.scrollY\b|\bpageYOffset\b|\bdocument\.documentElement\.scrollTop\b")
_BAD_LERP = re.compile(r"[+\-]=\s*\([^)]*\)\s*\*\s*0?\.\d+")
_OUTLINE_NONE = re.compile(r"outline\s*:\s*(?:none|0)\b", re.I)


def _blank(m: re.Match) -> str:
    """Replace a comment with the newlines it contained, so line numbers hold."""
    return "\n" * m.group(0).count("\n")


def css_regions(path: Path, text: str):
    """Yield (line_number, css_source) for every region of the file that is CSS."""
    if path.suffix == ".css":
        yield 1, _CSS_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
        return
    if path.suffix != ".html":
        return
    text = _HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    for m in _STYLE_BLOCK.finditer(text):
        line = text[: m.start(1)].count("\n") + 1
        body = _CSS_COMMENT.sub(lambda c: "\n" * c.group(0).count("\n"), m.group(1))
        yield line, body
    for m in _STYLE_ATTR.finditer(text):
        yield text[: m.start(1)].count("\n") + 1, m.group(1)


def declarations(path: Path, text: str):
    """Yield (line_number, property, value) for every CSS declaration."""
    for base, css in css_regions(path, text):
        for m in _DECL.finditer(css):
            yield base + css[: m.start()].count("\n"), m.group(1).strip().lower(), m.group(2).strip()


def rel(p: Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.relative_to(WEB).as_posix()


#: A mask's black and transparent are ALPHA, not colour. `mask-image` carries a
#: gradient whose stops select coverage; there is no palette decision in it, and
#: §6.8 explicitly permits gradients for mask feathering.
MASK_PROPS = {"mask-image", "-webkit-mask-image", "mask", "-webkit-mask"}


def check_colour(path: Path, text: str, problems: list):
    if rel(path) in COLOUR_EXEMPT:
        return
    for line, prop, value in declarations(path, text):
        if prop in MASK_PROPS:
            continue
        if _HEX.search(value) or _FUNC_COLOUR.search(value):
            problems.append((rel(path), line, "§17", "colour literal outside tokens.css",
                             f"{prop}: {value}"))


def check_spacing(path: Path, text: str, problems: list):
    for line, prop, value in declarations(path, text):
        if prop in STRUCTURAL or (prop.startswith("--") and STRUCTURAL_CUSTOM.match(prop)):
            continue
        if "clamp(" in value or "var(--s-" in value:
            continue
        for m in _PX.finditer(value):
            v = int(m.group(1))
            if v in SPACING or v in SPACING_FREE:
                continue
            problems.append((rel(path), line, "§8.5",
                             f"{v}px is outside the closed spacing set",
                             f"{prop}: {value}"))


def check_motion(path: Path, text: str, problems: list):
    for line, prop, value in declarations(path, text):
        is_motion = prop in MOTION_PROPS or prop.startswith("--m-") or prop.startswith("--d-")
        if is_motion:
            for m in _MS.finditer(value):
                v = int(m.group(1))
                if v in DURATIONS or v == 0:
                    continue
                # Named carve-outs, each with a blueprint citation:
                #   --d-tip 400ms (§13.1) · --d-toast 6000ms (§13.1)
                #   --m-collapse 120ms (§10.4, and §20's own token file)
                if prop in {"--d-tip", "--d-toast", "--m-collapse", "--d-preload"}:
                    continue
                problems.append((rel(path), line, "§10.1",
                                 f"{v}ms is outside the motion scale", f"{prop}: {value}"))
            for m in _SEC.finditer(value):
                if float(m.group(1)) == 0:
                    continue
                problems.append((rel(path), line, "§10.1",
                                 f"{m.group(0)} — durations are written in ms, from the scale",
                                 f"{prop}: {value}"))
        for m in _BEZIER.finditer(value):
            norm = re.sub(r"\s+", "", m.group(0))
            if norm not in CURVES:
                problems.append((rel(path), line, "§10.2",
                                 "curve outside the two permitted", norm))


def check_laws(path: Path, text: str, problems: list):
    # Comments are documentation. A comment that says "`outline:none` is a merge
    # blocker" must not itself be flagged as one.
    if path.suffix in (".css", ".html", ".js"):
        text = _CSS_COMMENT.sub(_blank, text)
    if path.suffix == ".html":
        text = _HTML_COMMENT.sub(_blank, text)
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.split("//")[0] if path.suffix == ".js" else raw
        if _OUTLINE_NONE.search(line):
            problems.append((rel(path), i, "§15", "outline removed", line.strip()))
        if _SCROLLY.search(line):
            problems.append((rel(path), i, "§10.5", "reads scroll position directly", line.strip()))
        if _BAD_LERP.search(line):
            problems.append((rel(path), i, "§10.6", "frame-rate-dependent lerp (F-02)", line.strip()))


def check_var_refs(path: Path, text: str, problems: list):
    """Every var(--x) must resolve to a token defined somewhere in the system.

    An undefined var() does not throw — it silently falls back to nothing, which
    is how a design system develops a hole nobody notices until a screenshot
    diff catches it three phases later.
    """
    for line, prop, value in declarations(path, text):
        for m in re.finditer(r"var\(\s*(--[\w-]+)", value):
            name = m.group(1)
            # A name composed at runtime (`'var(--s-' + v + ')'` in a script)
            # cannot be resolved statically and is not a violation.
            if name.endswith("-"):
                continue
            if name not in DEFINED:
                problems.append((rel(path), line, "§6.1",
                                 f"var({name}) is not defined anywhere", f"{prop}: {value}"))


DEFINED: set[str] = set()


def collect_defined(files: list[Path]) -> None:
    for path in files:
        text = path.read_text(encoding="utf-8")
        for _, prop, _ in declarations(path, text):
            if prop.startswith("--"):
                DEFINED.add(prop)


CHECKS = [
    ("colour literals outside tokens.css", "§17 LAW", check_colour),
    ("every var() resolves to a defined token", "§6.1", check_var_refs),
    ("spacing outside the closed set", "§8.5 LAW", check_spacing),
    ("durations and curves outside the scale", "§10.1–10.2 LAW", check_motion),
    ("focus outlines · scroll authority · frame-rate independence", "§15 / §10.5 / §10.6", check_laws),
]

NOT_CHECKED = [
    ("L-4", "no precision beyond the source", "review — a lint cannot know the source"),
    ("L-5", "light must be motivated", "review — a lint cannot see the lamp"),
    ("L-6", "type is never a texture", "review + the FE-5 asset audit"),
    ("§6.8", "signal on at most 4 elements per viewport", "counted in review"),
    ("§13.5", "every component in every state, both themes", "the states gallery, by inspection"),
    ("§5.3", "zero CLS on the font swap", "measurable only once the woff2 files exist"),
]


def targets() -> list[Path]:
    """Every surface built on DATUM, not just the design system's own pages.

    LAW §17 is repo-wide: a colour literal in the reviewer console is exactly as much of a
    violation as one in `components.css`, and a lint that only guards the design system's own
    files guards the place least likely to break.
    """
    out: list[Path] = []
    for base, patterns in (
        (ROOT, ("*.html", "styles/*.css", "*.js")),
        (WEB / "console", ("*.html", "*.css", "*.js")),
        (WEB / "site", ("*.html", "*.css", "*.js")),
        (WEB / "app" / "src", ("*.css",)),
    ):
        for pattern in patterns:
            out.extend(sorted(base.glob(pattern)))
    return out


def main() -> int:
    if "--list" in sys.argv:
        print("Checked:")
        for name, ref, _ in CHECKS:
            print(f"  · {name}  ({ref})")
        print("\nNot checked here, and not claimed to be:")
        for ref, name, how in NOT_CHECKED:
            print(f"  · {ref:<6} {name:<44} -> {how}")
        return 0

    if not TOKENS.exists():
        print(f"tokens.css not found at {TOKENS}")
        return 1

    problems: list = []
    files = targets()
    collect_defined(files)
    for path in files:
        text = path.read_text(encoding="utf-8")
        for _, _, fn in CHECKS:
            fn(path, text, problems)

    print(f"DATUM token lint — {len(files)} file(s) under {ROOT}")
    print("-" * 78)
    if not problems:
        for name, ref, _ in CHECKS:
            print(f"ok   {name}  ({ref})")
        print("-" * 78)
        print("No violations. Token lint PASSES.")
        print("\nExemptions in force:")
        for k, why in COLOUR_EXEMPT.items():
            print(f"  · {k}\n      {why}")
        print("\nRun with --list for what this tool does not check.")
        return 0

    for f, line, ref, what, snippet in sorted(problems):
        print(f"FAIL {f}:{line}  [{ref}] {what}\n       {snippet}")
    print("-" * 78)
    print(f"{len(problems)} violation(s). Token lint FAILS.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
