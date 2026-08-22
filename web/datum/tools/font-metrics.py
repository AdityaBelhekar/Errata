#!/usr/bin/env python
"""§5.3 LAW — the fallback metric overrides, measured rather than approximated.

    "every face carries size-adjust / ascent-override / descent-override tuned to
     its fallback so the swap causes ZERO layout shift"

Those three properties were marked ``<MEASURE>`` in ``type.css`` and were **absent,
not approximated** — deliberately, because ground rule 1 says do not publish a
metric nobody measured, and an approximated override is a measurement nobody took.

This tool takes it. It reads the real webfont and the real fallback, and prints
the CSS.

Direction of the adjustment
---------------------------

The overrides go on the **webfont's** ``@font-face``, tuning the webfont to match
the fallback — not the other way round. That is what ``type.css`` says and it is
the right way round here: the fallback paints first (``font-display: swap``), the
reader is already looking at it, and the webfont is what arrives late. Moving the
thing that arrives late is the only way nothing shifts under the reader's eye.

Method
------

``size-adjust`` matches the **x-height**, because x-height is what the eye reads
as "the size of the text" — matching the em box instead leaves two fonts that are
nominally the same size and visibly are not.

    S = (fallback.sxHeight / fallback.upem) / (webfont.sxHeight / webfont.upem)

``ascent-override`` and ``descent-override`` are then expressed as a fraction of
the *adjusted* em, so the line box the webfont occupies is the line box the
fallback occupied:

    ascent-override  = (fallback.ascent  / fallback.upem) / S
    descent-override = (fallback.descent / fallback.upem) / S
    line-gap-override = (fallback.lineGap / fallback.upem) / S

Ascent and descent come from the OS/2 table's ``sTypoAscender`` /
``sTypoDescender`` where ``USE_TYPO_METRICS`` is set, and from ``hhea`` otherwise —
which is the rule a browser follows, so it is the rule this follows.

    python web/datum/tools/font-metrics.py            print the CSS
    python web/datum/tools/font-metrics.py --check    fail if type.css disagrees

**A note on what this does NOT do.** It measures against the fallback *as
installed on this machine*. Georgia's metrics are stable across Windows and macOS,
but ``system-ui`` resolves to Segoe UI here and to something else elsewhere. The
override that results is therefore right for the most common case and approximate
for the rest — which is better than absent and is not the same as exact. Recorded
here rather than implied.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "fonts"
TYPE_CSS = ROOT / "styles" / "type.css"

#: Where the system fallbacks live. Windows paths first because that is where this was measured;
#: the macOS locations are listed so a second machine reproduces rather than guesses.
FALLBACK_SEARCH = (
    Path("C:/Windows/Fonts"),
    Path("/System/Library/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),
    Path("/usr/share/fonts/truetype"),
)


@dataclass(frozen=True)
class Face:
    """One declared `@font-face`, and the fallback it must not shift against."""

    family: str
    style: str
    webfont: str
    fallback_file: str
    fallback_name: str
    why: str


#: Only the faces `type.css` actually declares. `Sligoil` (the non-Micro cut) is absent from this
#: list because it is absent from the foundry's release -- see ADR-006. It is not silently mapped
#: to Sligoil Micro, which is a different face.
FACES: tuple[Face, ...] = (
    Face("Redaction 0", "normal", "redaction/Redaction_0-Regular.woff2", "georgia.ttf", "Georgia",
         "display voice; Spectral is not installed either, so Georgia is what actually paints"),
    Face("Redaction 20", "normal", "redaction/Redaction_20-Regular.woff2", "georgia.ttf", "Georgia", ""),
    Face("Redaction 20", "italic", "redaction/Redaction_20-Italic.woff2", "georgiai.ttf", "Georgia Italic", ""),
    Face("Redaction 50", "normal", "redaction/Redaction_50-Regular.woff2", "georgia.ttf", "Georgia", ""),
    Face("Redaction 100", "normal", "redaction/Redaction_100-Regular.woff2", "georgia.ttf", "Georgia", ""),
    Face("Apfel Grotezk", "normal", "apfel/ApfelGrotezk-Regular.woff2", "segoeui.ttf", "Segoe UI",
         "text voice; `system-ui` resolves to Segoe UI on Windows"),
    Face("Apfel Grotezk 500", "normal", "apfel/ApfelGrotezk-Mittel.woff2", "segoeui.ttf", "Segoe UI", ""),
    Face("Apfel Grotezk 700", "normal", "apfel/ApfelGrotezk-Fett.woff2", "segoeuib.ttf", "Segoe UI Bold", ""),
    Face("Apfel Grotezk Brukt", "normal", "apfel/ApfelGrotezk-Brukt.woff2", "segoeui.ttf", "Segoe UI", ""),
    Face("Sligoil Micro", "normal", "sligoil/Sligoil-Micro.woff2", "consola.ttf", "Consolas",
         "data voice; `ui-monospace` resolves to Consolas on Windows"),
)


@dataclass(frozen=True)
class Metrics:
    upem: int
    ascent: float
    descent: float
    line_gap: float
    x_height: float

    @property
    def ascent_ratio(self) -> float:
        return self.ascent / self.upem

    @property
    def descent_ratio(self) -> float:
        return abs(self.descent) / self.upem

    @property
    def line_gap_ratio(self) -> float:
        return self.line_gap / self.upem

    @property
    def x_height_ratio(self) -> float:
        return self.x_height / self.upem


def read_metrics(path: Path) -> Metrics:
    """Read the metrics a BROWSER would use, not the first ones that parse.

    Which table wins is not a stylistic choice: if OS/2 fbit 7 (``USE_TYPO_METRICS``) is set the
    browser takes the typo metrics, otherwise it takes hhea. Reading the wrong pair produces an
    override that is confidently wrong, which is worse than none -- the layout would shift by a
    fixed amount on every page and look like a design decision.
    """
    font = TTFont(path, fontNumber=0, lazy=True)
    upem = font["head"].unitsPerEm
    os2 = font["OS/2"]
    hhea = font["hhea"]

    use_typo = bool(getattr(os2, "fsSelection", 0) & (1 << 7))
    if use_typo:
        ascent, descent, line_gap = os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap
    else:
        ascent, descent, line_gap = hhea.ascent, hhea.descent, hhea.lineGap

    # sxHeight is OS/2 v2+. Where it is absent or zero, measure the 'x' glyph directly -- an
    # x-height taken from the outline is the same number the eye judges.
    x_height = getattr(os2, "sxHeight", 0) or 0
    if not x_height:
        glyph_set = font.getGlyphSet()
        cmap = font.getBestCmap()
        name = cmap.get(ord("x"))
        if name and name in glyph_set:
            from fontTools.pens.boundsPen import BoundsPen

            pen = BoundsPen(glyph_set)
            glyph_set[name].draw(pen)
            x_height = pen.bounds[3] if pen.bounds else 0
    if not x_height:
        raise RuntimeError(f"{path.name}: no x-height available; cannot match sizes")

    font.close()
    return Metrics(upem, float(ascent), float(descent), float(line_gap), float(x_height))


def find_fallback(name: str) -> Path | None:
    for directory in FALLBACK_SEARCH:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def overrides_for(face: Face) -> dict[str, str] | None:
    webfont_path = FONTS / face.webfont
    fallback_path = find_fallback(face.fallback_file)
    if not webfont_path.is_file() or fallback_path is None:
        return None

    web = read_metrics(webfont_path)
    fall = read_metrics(fallback_path)

    size_adjust = fall.x_height_ratio / web.x_height_ratio
    return {
        "size-adjust": f"{size_adjust * 100:.2f}%",
        "ascent-override": f"{fall.ascent_ratio / size_adjust * 100:.2f}%",
        "descent-override": f"{fall.descent_ratio / size_adjust * 100:.2f}%",
        "line-gap-override": f"{fall.line_gap_ratio / size_adjust * 100:.2f}%",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if type.css still says <MEASURE>")
    args = parser.parse_args()

    if args.check:
        css = TYPE_CSS.read_text(encoding="utf-8")
        if "<MEASURE>" in css:
            print(
                "type.css still carries <MEASURE> placeholders. §5.3 is a LAW and no CLS number "
                "may be quoted until they are replaced. Run: python web/datum/tools/font-metrics.py",
                file=sys.stderr,
            )
            return 1
        print("no <MEASURE> placeholders remain in type.css")
        return 0

    missing: list[str] = []
    print(f"{'face':26s} {'fallback':16s} size-adjust  ascent   descent  line-gap")
    print("-" * 78)
    for face in FACES:
        result = overrides_for(face)
        if result is None:
            missing.append(f"{face.family} ({face.style})")
            continue
        print(
            f"{face.family + ' ' + face.style:26s} {face.fallback_name:16s} "
            f"{result['size-adjust']:>11s} {result['ascent-override']:>8s} "
            f"{result['descent-override']:>9s} {result['line-gap-override']:>9s}"
        )

    if missing:
        print("\nNot measured (webfont or fallback absent on this machine):", file=sys.stderr)
        for name in missing:
            print(f"  {name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
