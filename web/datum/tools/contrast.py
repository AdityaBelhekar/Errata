"""
DATUM — contrast gate.

Blueprint §6.7: "contrast is asserted in CI. A token change that drops any pair
below target fails the build."

This file is that assertion. It parses the OKLCH palette out of
`web/datum/styles/tokens.css`, resolves the semantic layer for both themes,
converts OKLCH -> Oklab -> linear sRGB -> sRGB, and computes WCAG 2.x contrast
ratios. Nothing here is copied from the blueprint's table: every number this
prints was computed from the token file that actually ships.

Ground rule 1 applies (HANDOFF.md §8): never print a number you did not derive.
Where a computed ratio disagrees with the blueprint's stated ratio, this tool
prints both, and the disagreement is reported rather than smoothed.

Usage:
    python web/datum/tools/contrast.py            # print the table, exit 1 on failure
    python web/datum/tools/contrast.py --md       # markdown table for the phase report
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

TOKENS = Path(__file__).resolve().parents[1] / "styles" / "tokens.css"

# ── colour maths ──────────────────────────────────────────────────────────────
# Oklab <-> linear sRGB matrices: Björn Ottosson, "A perceptual color space for
# image processing" (2020), the published M1-inverse / M2-inverse pair.

_LMS_FROM_OKLAB = (
    (1.0, 0.3963377774, 0.2158037573),
    (1.0, -0.1055613458, -0.0638541728),
    (1.0, -0.0894841775, -1.2914855480),
)
_LRGB_FROM_LMS = (
    (4.0767416621, -3.3077115913, 0.2309699292),
    (-1.2684380046, 2.6097574011, -0.3413193965),
    (-0.0041960863, -0.7034186147, 1.7076147010),
)


def oklch_to_srgb(L: float, C: float, H: float):
    """OKLCH (L 0..1, C, H in degrees) -> sRGB 0..1, clipped to gamut."""
    h = math.radians(H)
    a, b = C * math.cos(h), C * math.sin(h)
    lms = [m[0] * L + m[1] * a + m[2] * b for m in _LMS_FROM_OKLAB]
    lms = [v ** 3 for v in lms]
    lin = [sum(m[i] * lms[i] for i in range(3)) for m in _LRGB_FROM_LMS]
    return tuple(_encode(min(1.0, max(0.0, v))) for v in lin)


def _encode(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def _decode(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb) -> float:
    r, g, b = (_decode(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg, bg) -> float:
    a, b = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def over(fg, bg):
    """Composite a straight-alpha colour over an opaque one, in linear light."""
    r, g, b, alpha = fg
    return tuple(
        _encode(_decode(f) * alpha + _decode(k) * (1 - alpha))
        for f, k in zip((r, g, b), bg, strict=True)
    )


def hexof(rgb) -> str:
    return "#" + "".join(f"{round(c * 255):02X}" for c in rgb)


# ── token parsing ─────────────────────────────────────────────────────────────

_OKLCH = re.compile(r"oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)")
_RGBA = re.compile(
    r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)"
)
_HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
_DARK_BLOCK = re.compile(r':root\[data-theme="dark"\][^{]*\{(.*?)\n\}', re.S)


def parse_blocks(css: str):
    """Return {'light': {token: raw}, 'dark': {token: raw}}.

    Everything declared on bare `:root` before the first `@media` is the palette
    plus the LIGHT semantic base (blueprint §6.6: light is the base definition).
    The explicit `[data-theme="dark"]` block supplies the dark overrides — the
    same values the `prefers-color-scheme` block carries, by construction.
    """
    head = css.split("@media", 1)[0]
    light = {name: value.strip() for name, value in _DECL.findall(head)}
    dark = dict(light)
    m = _DARK_BLOCK.search(css)
    if not m:
        raise RuntimeError("no :root[data-theme=dark] block found in tokens.css")
    for name, value in _DECL.findall(m.group(1)):
        dark[name] = value.strip()
    return {"light": light, "dark": dark}


def resolve(token: str, scope, depth: int = 0):
    """Resolve a token to (r,g,b) or (r,g,b,a), following var() indirection."""
    if depth > 12:
        raise RuntimeError(f"var() cycle at {token}")
    raw = scope.get(token)
    if raw is None:
        raise KeyError(f"undefined token {token}")
    v = raw.strip()
    ref = re.fullmatch(r"var\((--[\w-]+)\)", v)
    if ref:
        return resolve(ref.group(1), scope, depth + 1)
    m = _OKLCH.search(v)
    if m:
        return oklch_to_srgb(float(m.group(1)), float(m.group(2)), float(m.group(3)))
    m = _RGBA.search(v)
    if m:
        r, g, b = (float(m.group(i)) / 255 for i in (1, 2, 3))
        a = float(m.group(4)) if m.group(4) else 1.0
        return (r, g, b, a) if a < 1.0 else (r, g, b)
    m = _HEX.search(v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i: i + 2], 16) / 255 for i in (0, 2, 4))
    raise ValueError(f"cannot resolve {token} = {raw!r}")


# ── the assertion table ───────────────────────────────────────────────────────
# Targets: 7.0 = WCAG AAA body · 4.5 = AA body · 3.0 = AA non-text contrast
# (SC 1.4.11), which is the right target for a focus ring and a UI boundary.

PAIRS = [
    # Text pairs are asserted against the *worst* ground the token may legally
    # land on in that theme, not against a convenient one. In dark that is
    # --surface-3 (the lightest graphite); in light it is --surface-3 (the
    # darkest bone). Passing there means passing everywhere.
    ("--text-1", "--bg-void", "dark", 7.0, "body on the void"),
    ("--text-2", "--surface-3", "dark", 4.5, "secondary, worst ground"),
    ("--text-3", "--surface-3", "dark", 4.5, "tertiary, worst ground"),
    ("--signal-text", "--surface-3", "dark", 4.5, "signal as type, worst ground"),
    ("--settled", "--surface-3", "dark", 4.5, "reconciled, worst ground"),
    ("--evidence-text", "--evidence-bg", "dark", 7.0, "paper, dark theme"),
    ("--focus-ring", "--bg-void", "dark", 3.0, "focus ring on the void"),
    ("--signal", "--surface-1", "dark", 3.0, "signal as plane (SC 1.4.11)"),
    ("--signal", "--evidence-bg", "dark", 3.0, "the 2px reveal on paper"),
    ("--edge-strong", "--surface-1", "dark", 1.0, "hairline (reported, not gated)"),

    ("--text-1", "--bg-void", "light", 7.0, "body on the void"),
    ("--text-2", "--surface-3", "light", 4.5, "secondary, worst ground"),
    ("--text-3", "--surface-3", "light", 4.5, "tertiary, worst ground"),
    ("--signal-text", "--surface-3", "light", 4.5, "signal as type, worst ground"),
    ("--settled", "--surface-3", "light", 4.5, "reconciled, worst ground"),
    ("--evidence-text", "--evidence-bg", "light", 7.0, "paper, light theme"),
    ("--focus-ring", "--bg-void", "light", 3.0, "focus ring on the void"),
    ("--signal", "--surface-1", "light", 3.0, "signal as plane (SC 1.4.11)"),
    ("--signal", "--evidence-bg", "light", 3.0, "the 2px reveal on paper"),
    ("--edge-strong", "--surface-1", "light", 1.0, "hairline (reported, not gated)"),
]

# What blueprint §6.7 claims, for the pairs it lists. Present so that any
# disagreement is visible rather than quietly overwritten.
BLUEPRINT_CLAIM = {
    # Only the two pairs whose ground is unchanged from §6.7 are comparable.
    ("--text-1", "--bg-void", "dark"): 16.9,
    ("--text-1", "--bg-void", "light"): 14.6,
}


def measure(css: str):
    blocks = parse_blocks(css)
    rows = []
    for fg_t, bg_t, theme, target, label in PAIRS:
        scope = blocks[theme]
        bg = resolve(bg_t, scope)
        fg = resolve(fg_t, scope)
        if len(fg) == 4:
            fg = over(fg, bg)
        ratio = contrast(fg, bg)
        claim = BLUEPRINT_CLAIM.get((fg_t, bg_t, theme))
        drift = claim if claim is not None and abs(claim - ratio) > 0.15 else None
        rows.append(
            dict(
                fg=fg_t, bg=bg_t, theme=theme, target=target, label=label,
                fg_hex=hexof(fg), bg_hex=hexof(bg), ratio=ratio,
                ok=ratio >= target, drift=drift,
            )
        )
    return rows


def main() -> int:
    rows = measure(TOKENS.read_text(encoding="utf-8"))
    md = "--md" in sys.argv
    failures = [r for r in rows if not r["ok"]]
    drifts = [r for r in rows if r["drift"] is not None]

    if md:
        print("| Pair | Theme | Fore | Ground | Measured | Target | |")
        print("|---|---|---|---|---:|---:|---|")
        for r in rows:
            mark = "—" if r["target"] == 1.0 else ("PASS" if r["ok"] else "**FAIL**")
            note = f"<br><sub>§6.7 states {r['drift']}</sub>" if r["drift"] else ""
            print(
                f"| `{r['fg']}` on `{r['bg']}` | {r['theme']} | `{r['fg_hex']}` | "
                f"`{r['bg_hex']}` | **{r['ratio']:.2f}:1** | "
                f"{'—' if r['target'] == 1.0 else format(r['target'], '.1f')} | {mark}{note} |"
            )
        return 1 if failures else 0

    print(f"DATUM contrast gate — {TOKENS}")
    print("-" * 84)
    for r in rows:
        mark = "-- " if r["target"] == 1.0 else ("ok " if r["ok"] else "FAIL")
        drift = f"   [§6.7 states {r['drift']}]" if r["drift"] else ""
        print(
            f"{mark} {r['theme']:<5} {r['fg']:<16} on {r['bg']:<14}"
            f"{r['ratio']:7.2f}:1  (>= {r['target']:.1f})  {r['label']}{drift}"
        )
    print("-" * 84)
    if drifts:
        print(
            f"\n{len(drifts)} pair(s) differ from blueprint §6.7 by more than 0.15.\n"
            "Reported, not corrected: tokens.css is the source of truth and §6.7\n"
            "carries an erratum. See docs/frontend/FE-1-SCHEMATIC.md.\n"
        )
    if failures:
        print(f"{len(failures)} pair(s) below target — contrast gate FAILS.")
        return 1
    print(f"All {len(PAIRS)} pairs meet target. Contrast gate PASSES.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
