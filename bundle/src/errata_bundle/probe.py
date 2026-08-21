"""FE-2.5's gate: does the evidence box land on the words? Measured in pixels, by registration.

The acceptance criterion for FR-7.2 is *"box lands on the value's words, not the paragraph or
page"*, and until this module existed the only way to check it was to look. Looking is not a gate:
a box two lines low is obvious, a box four pixels low is not, and four pixels is enough to clip a
digit off the top of ``16 A`` at 8pt.

The measurement, and why it is not the obvious one
--------------------------------------------------

The obvious measurement is: draw the projected box, find the ink bounding box near it, compare.
That was the first three versions of this file, and every one of them reported a confident wrong
answer, because *ink near a word is not the same thing as ink of that word*:

1. A flat search margin caught the next word along the line.
2. Clipping along the line only caught the line above and below.
3. Clipping against a *sampled* word list clipped nothing, because the real neighbours had been
   sampled away.

All three reported the same figure -- ``9.0px``, which is the search margin plus one: the signature
of "ink fills the window" rather than of any displacement. And once all three were fixed, the real
documents still showed ~8.6px on 39% of words, for a reason no amount of clipping addresses:
**a datasheet is full of ink that is not a glyph.** Table rules, cell borders, logos and dimension
lines sit within a few pixels of the text, and a bounding-box method attributes them to the nearest
word. The synthetic fixtures were clean throughout, because they are text on white — which is
exactly how a bad instrument passes its own tests.

So the metric here is **registration**, not bounding boxes, and it asks a better question:

    Of all the small displacements of this box, which one covers the most ink?

If the projection is right the answer is ``(0, 0)``. If boxes are drifting nine pixels down, the
answer is ``(0, -9)`` on every word, and it says so. Table rules do not move the argmax — they sit
outside the box at every candidate offset, raising the noise floor without shifting the peak. This
is ordinary image registration, and it is robust for the reason registration generally is.

Three numbers come out:

``offset``    the ``(dx, dy)`` displacement, in rendered pixels, that best covers the word's ink.
              **(0, 0) is the correct answer. This is the error term.**
``coverage``  fraction of the projected box that is ink at the best offset. A sanity floor: a word
              covering 2% of its own box was probably not rendered.
``contrast``  peak ink over the *mean* ink across the whole search grid. How confidently the peak
              is a peak. Near 1.0 means the box sits on something uniform — a filled cell, a
              barcode, a solid rule — and the offset it reports is not meaningful.

              An earlier version used a fixed one-line-away control instead, and it was wrong for
              an obvious reason once seen: on a dense datasheet, one line away is *another line of
              text* with much the same ink density, so the ratio sat near 1.0 and the probe
              declared 80% of perfectly good words unmeasurable. Peak-against-grid-mean has no
              such blind spot, and the grid is already computed.

What this does not measure
--------------------------

Whether the *right* word was selected. That is grounding accuracy, scored by
``errata-r3 corpus score`` against ExtractBench's metric, and it is a different question from
whether the box drawn around the chosen word is in the right place. Conflating the two is how a
coordinate bug hides behind a grounding score.
"""

from __future__ import annotations

import statistics
from array import array
from dataclasses import dataclass

import pymupdf

from .geometry import Box, PageProjection, project_page

__all__ = [
    "DARK_THRESHOLD",
    "MAX_OFFSET_PX",
    "MIN_CONTRAST",
    "MIN_COVERAGE",
    "PageProbe",
    "WordProbe",
    "probe_document",
    "probe_page",
]

#: A pixel counts as ink below this luminance (0-255). Datasheet body text is near-black on white;
#: 160 admits antialiased edges without admitting a light-grey table fill. Chosen from the page,
#: not tuned until the numbers looked good -- tuning a threshold until a projection passes is
#: fitting the instrument to the answer.
DARK_THRESHOLD = 160

#: Half-width of the registration search, in rendered pixels. At zoom 2 a body line is ~20px tall,
#: so +/-10 covers half a line each way: wide enough to find a real drift's peak, narrow enough
#: that the peak cannot be the line above.
MAX_OFFSET_PX = 10

#: Below this ink fraction at the best offset the word is unmeasurable rather than correct. A box
#: over blank paper registers a perfect (0, 0) and means nothing.
MIN_COVERAGE = 0.02

#: Peak ink must beat the search grid's mean by this factor for the offset to be believed. 1.25 is
#: a weak requirement on purpose: it is here to reject uniform fills and solid rules, not to select
#: comfortable words. Words it rejects are counted and reported, never silently dropped.
MIN_CONTRAST = 1.25


@dataclass(frozen=True, slots=True)
class WordProbe:
    """One word's projection, registered against the ink actually rendered."""

    text: str
    page: int
    projected: Box
    offset: tuple[int, int]
    coverage: float
    contrast: float

    @property
    def displacement(self) -> float:
        """Magnitude of the registration offset, in pixels. Zero is correct."""
        dx, dy = self.offset
        return (dx * dx + dy * dy) ** 0.5

    @property
    def measurable(self) -> bool:
        """Whether this word carries enough distinct ink for its offset to mean anything.

        Counted and reported separately rather than silently dropped: a corpus where half the words
        are unmeasurable is a finding about the corpus, and averaging them in as zeros would hide it
        behind a good-looking mean.
        """
        return self.coverage >= MIN_COVERAGE and self.contrast >= MIN_CONTRAST


@dataclass(frozen=True, slots=True)
class PageProbe:
    page: int
    projection: PageProjection
    words: tuple[WordProbe, ...]

    @property
    def measurable(self) -> tuple[WordProbe, ...]:
        return tuple(w for w in self.words if w.measurable)

    @property
    def unmeasurable(self) -> tuple[WordProbe, ...]:
        return tuple(w for w in self.words if not w.measurable)

    @property
    def max_displacement(self) -> float:
        return max((w.displacement for w in self.measurable), default=0.0)

    @property
    def mean_displacement(self) -> float:
        m = self.measurable
        return statistics.fmean([w.displacement for w in m]) if m else 0.0

    @property
    def modal_offset(self) -> tuple[int, int]:
        """The most common offset across measurable words.

        This is the number that matters for a *systematic* fault. One word off by three pixels is a
        glyph with an unusual bounding box; every word off by the same three pixels is a broken
        transform, and only the mode tells those apart.
        """
        m = self.measurable
        if not m:
            return (0, 0)
        counts: dict[tuple[int, int], int] = {}
        for w in m:
            counts[w.offset] = counts.get(w.offset, 0) + 1
        return max(counts.items(), key=lambda kv: (kv[1], -abs(kv[0][0]) - abs(kv[0][1])))[0]

    @property
    def agreement(self) -> float:
        """Fraction of measurable words registering at the modal offset."""
        m = self.measurable
        if not m:
            return 0.0
        mode = self.modal_offset
        return sum(1 for w in m if w.offset == mode) / len(m)

    @property
    def clean(self) -> bool:
        """The gate: no systematic displacement, and most words agree.

        Deliberately not "every word is at (0, 0)". Individual glyphs legitimately register a pixel
        off — an accent, a descender, a full stop whose ink is a fifth of its box. A gate demanding
        perfection on every word would fail on typography and teach everyone to ignore it. What must
        be zero is the **mode**.
        """
        return self.modal_offset == (0, 0) and self.agreement >= 0.6


def _ink_integral(pixmap: pymupdf.Pixmap, threshold: int) -> tuple[array, int, int]:
    """Summed-area table of the ink mask, so any box's ink count costs four lookups.

    Built once per page. Without it, a 21x21 offset search over 40 words would re-count the same
    pixels hundreds of thousands of times and the gate would be too slow to run — which is the same
    as not having one.

    ``array('i')`` rather than a list of lists: 2M int32 is 8MB and contiguous, where the nested
    list would be ~80MB of boxed integers.
    """
    w, h, n, stride = pixmap.width, pixmap.height, pixmap.n, pixmap.stride
    samples = pixmap.samples
    row_w = w + 1
    integral = array("i", bytes(4 * row_w * (h + 1)))
    for y in range(h):
        base = y * stride
        cur = (y + 1) * row_w
        prev = y * row_w
        running = 0
        for x in range(w):
            off = base + x * n
            # Minimum channel as luminance: dark ink is dark in every channel, and the minimum will
            # not mistake a saturated colour for ink the way a mean would.
            if (
                samples[off] < threshold
                and samples[off + 1] < threshold
                and samples[off + 2] < threshold
            ):
                running += 1
            integral[cur + x + 1] = integral[prev + x + 1] + running
    return integral, w, h


def _count(integral: array, w: int, h: int, box: Box) -> int:
    """Ink pixels inside ``box``, clamped to the page. Four lookups."""
    x0 = max(0, min(w, int(box[0])))
    y0 = max(0, min(h, int(box[1])))
    x1 = max(0, min(w, int(box[2])))
    y1 = max(0, min(h, int(box[3])))
    if x1 <= x0 or y1 <= y0:
        return 0
    row = w + 1
    return (
        integral[y1 * row + x1]
        - integral[y0 * row + x1]
        - integral[y1 * row + x0]
        + integral[y0 * row + x0]
    )


def probe_page(
    page: pymupdf.Page,
    words: list,
    *,
    report: list[int] | None = None,
    zoom: float = 2.0,
    max_offset: int = MAX_OFFSET_PX,
    threshold: int = DARK_THRESHOLD,
) -> PageProbe:
    """Project every reported word and register it against the rendered ink.

    ``words`` is any sequence of objects carrying ``.text`` and ``.bbox`` in PDF user space --
    ``errata_audit.layout.Word`` satisfies it, and so does a test fixture, deliberately: the probe
    must be runnable against a synthetic page whose true geometry is known.
    """
    projection, pixmap = project_page(page, zoom=zoom)
    integral, pw, ph = _ink_integral(pixmap, threshold)

    indices = range(len(words)) if report is None else report
    probes: list[WordProbe] = []

    for i in indices:
        word = words[i]
        box = projection.to_pixels(word.bbox)
        bw, bh = box[2] - box[0], box[3] - box[1]
        area = bw * bh
        if area <= 0:
            probes.append(WordProbe(word.text, projection.page, box, (0, 0), 0.0, 0.0))
            continue

        best, best_count, total, n_offsets = (0, 0), -1, 0, 0
        for dy in range(-max_offset, max_offset + 1):
            for dx in range(-max_offset, max_offset + 1):
                c = _count(
                    integral, pw, ph,
                    (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy),
                )
                total += c
                n_offsets += 1
                # Ties resolve to the smaller displacement. A word on a solid fill covers the same
                # ink at every offset; reporting (0, 0) and flagging it low-contrast is honest,
                # where reporting whichever offset the loop happened to reach first is noise.
                if c > best_count or (
                    c == best_count and (dx * dx + dy * dy) < (best[0] ** 2 + best[1] ** 2)
                ):
                    best_count, best = c, (dx, dy)

        coverage = best_count / area
        mean_count = total / n_offsets if n_offsets else 0.0
        contrast = (best_count / mean_count) if mean_count > 0 else float("inf")

        probes.append(
            WordProbe(
                text=word.text,
                page=projection.page,
                projected=box,
                offset=best,
                coverage=coverage,
                contrast=contrast,
            )
        )

    return PageProbe(page=projection.page, projection=projection, words=tuple(probes))


def probe_document(
    path,
    *,
    pages: int = 2,
    words_per_page: int = 40,
    zoom: float = 2.0,
) -> list[PageProbe]:
    """Probe the first ``pages`` pages of a document, sampling evenly across each page."""
    document = pymupdf.open(path)
    out: list[PageProbe] = []
    try:
        for index in range(min(pages, len(document))):
            page = document[index]
            raw = page.get_text("words")
            if not raw:
                continue

            class _W:
                __slots__ = ("bbox", "text")

                def __init__(self, entry):
                    self.bbox = (entry[0], entry[1], entry[2], entry[3])
                    self.text = entry[4]

            everything = [_W(e) for e in raw]
            # A stride rather than the first N: the first N words of a datasheet page are the
            # header block, and a projection fault in the body would never be reached.
            step = max(1, len(everything) // words_per_page)
            report = list(range(0, len(everything), step))[:words_per_page]
            out.append(probe_page(page, everything, report=report, zoom=zoom))
    finally:
        document.close()
    return out
