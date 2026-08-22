"""FR-1.4 / FR-1.6 -- the canonical text layer, and the page geometry that keeps products apart.

The acceptance criterion for FR-1.4 is not "extracts text". It is:

    "Deterministic for identical input bytes and identical extractor version; cached;
     version-stamped."

All three words are load-bearing, and the reason is ``Evidence.char_span``: a claim stores an
offset into *this* layer, so a claim made in March is only reconstructible in September if the same
bytes still produce the same offsets. An extraction pass that quietly reorders words between
releases invalidates every stored span while every test still passes. So the version is stamped
into the layer, the layer is cached by ``(content hash, version)`` rather than by path, and the
ordering is whatever the extractor gave -- never "improved" in place.

**What R1 inherited from the annotation engine, and what it did not.** That engine (now
``errata_ecosystem.goldbuild``, formerly ``spike/``, throwaway by
decision D-2) established that PyMuPDF's ``"words"`` extraction is stable for these documents and
that word boxes -- not cell rectangles -- are the right grounding unit. Those are *findings*, and
the P3 fence permits inheriting findings. The code here is written fresh and carries three things
it deliberately did not have:

* a **cache** keyed on content hash, which FR-1.4 requires and a one-shot annotator had no
  need of;
* **column bands** (FR-1.6), so a two-column catalog page cannot bleed one product's value onto
  the product beside it;
* **page geometry**, so evidence can be re-rendered on the page it came from (FR-7.2).

Scope, stated honestly: born-digital PDFs. A scanned page produces a layer with no words, and
:attr:`TextLayer.is_born_digital` says so at the point of extraction rather than letting the caller
discover it later as a mysteriously empty result. There is no OCR here, and a document that needs
one is declined with ``LAYOUT_UNREADABLE`` rather than guessed at.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pymupdf

__all__ = [
    "COLUMN_GAP_FRACTION",
    "IMAGE_DOMINATED_RATIO",
    "JOIN",
    "LAYOUT_VERSION",
    "ColumnBand",
    "Page",
    "TextLayer",
    "Word",
    "extract_layer",
    "layer_cache_key",
]

#: Stamped into every layer. Bump on any change that could move a char offset -- the join
#: character, the word ordering, the source library. A stored ``char_span`` is meaningless without
#: the version that produced it, which is why the two always travel together.
LAYOUT_VERSION = "errata-layout/1.0.0"

#: The single character joining words in the canonical layer. Deliberately not configurable: it is
#: part of the offset arithmetic, and a parameter here would let two callers build two different
#: canonical layers from one document and both call them canonical.
JOIN = " "

#: A horizontal gap wider than this fraction of the page width reads as a column boundary rather
#: than as word spacing. Chosen from page geometry -- a catalog gutter is centimetres, inter-word
#: spacing is millimetres -- and NOT tuned against an accuracy score. Tuning a layout constant
#: until the audit agrees with itself more often is fitting the instrument to the answer.
COLUMN_GAP_FRACTION = 0.06

#: A page whose image blocks cover at least this fraction of it is a picture, not a typeset page.
#: See ADR-004. Measured, not guessed: the two real datasheets on hand -- photographs, wiring
#: diagrams and dimension drawings included -- peak at 0.191, and a scanned page is 1.0. This sits
#: 3.1x above the highest observed born-digital page and 0.4 below a scan, in the middle of a gap
#: nothing occupies.
#:
#: It is set from that separation and NOT from a coverage target. Moving it in the direction that
#: recovers coverage needs a new ADR and a reviewer who is not the person whose number it restores
#: -- the failure mode this repository already has one instance of (MIN_CONTRAST, 1.5 -> 1.25).
IMAGE_DOMINATED_RATIO = 0.60


@dataclass(frozen=True, slots=True)
class Word:
    """One word, its span in the canonical layer, and where it sits on the page."""

    text: str
    page: int
    """1-indexed, matching ``Evidence.page`` which is ``Field(ge=1)``."""

    start: int
    end: int
    x0: float
    y0: float
    x1: float
    y1: float
    block: int = 0
    line: int = 0

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)


@dataclass(frozen=True, slots=True)
class Page:
    number: int
    width: float
    height: float

    image_area_ratio: float = 0.0
    """Fraction of the page covered by image blocks, 0..1, measured at extraction (ADR-004).

    Carried on the page rather than computed on demand because it is a property of the bytes that
    were extracted, and recomputing it later means reopening a document that may no longer be
    reachable at the same URL -- the case the document register exists to catch.
    """

    @property
    def is_image_dominated(self) -> bool:
        """The page is a picture. Any text over it is an OCR guess, not the document's own bytes."""
        return self.image_area_ratio >= IMAGE_DOMINATED_RATIO


@dataclass(frozen=True, slots=True)
class ColumnBand:
    """A vertical band of a page holding one column of content (FR-1.6).

    Bands exist so that "the value nearest the product name" can never quietly mean "the value
    belonging to the product in the next column". A single-column page yields one band covering it,
    so nothing downstream needs a special case for the common shape.
    """

    page: int
    index: int
    x0: float
    x1: float

    def contains(self, word: Word) -> bool:
        centre = (word.x0 + word.x1) / 2
        return self.x0 <= centre <= self.x1


@dataclass(frozen=True, slots=True)
class TextLayer:
    """The canonical text of one document revision, plus the map back to the page."""

    text: str
    words: tuple[Word, ...]
    pages: tuple[Page, ...]
    columns: tuple[ColumnBand, ...]
    layout_version: str = LAYOUT_VERSION
    document_sha256: str = ""

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def sha256(self) -> str:
        """Hash of the canonical text. Two extractions of the same bytes must agree here, and the
        determinism test asserts exactly that rather than trusting the library to be stable."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def is_born_digital(self) -> bool:
        """True when the document carries a text layer at all.

        Deliberately the weakest possible test -- *any* extracted word -- and it took a revision to
        get there. The annotation engine uses "at least 20 words a page", which is a reasonable
        description of
        a datasheet and a bad *decision rule*: a sparse but perfectly readable page then declined
        with ``LAYOUT_UNREADABLE``, which says the layout defeated us when in fact the document is
        readable and simply does not state the value.

        The distinction matters because the two produce different declined reasons, and a reason
        that misdescribes what happened is worse than no reason. A scan without OCR yields zero
        words and is genuinely unreadable; a thin page yields few words and then declines with
        ``no_span_available``, which is the truth.
        """
        return bool(self.words)

    @property
    def ocr_over_scan_pages(self) -> tuple[int, ...]:
        """Page numbers that carry words *and* are image-dominated -- i.e. OCR over a scan."""
        carrying = {word.page for word in self.words}
        return tuple(
            page.number
            for page in self.pages
            if page.number in carrying and page.is_image_dominated
        )

    @property
    def is_ocr_over_scan(self) -> bool:
        """Every page carrying text is a picture: the text layer is OCR output (ADR-004).

        This is orthogonal to :attr:`is_born_digital`, not a refinement of it. That property
        distinguishes *unreadable* (no words) from *thin* (few words), a distinction its own
        docstring records as having taken a revision to get right. OCR-over-scan is a third thing:
        plenty of words, all of them a model's reading of pixels rather than the document's
        character stream. Grounding a claim in them cites something the document does not say, and
        the boxes cannot land because they were never in the same coordinate space as the span.

        **Every** page carrying words, not most: a document with one scanned insert among fifteen
        typeset pages is not an OCR-over-scan document, and declining it whole would throw away
        fifteen good pages to avoid one bad one.
        """
        carrying = {word.page for word in self.words}
        if not carrying:
            return False
        return len(self.ocr_over_scan_pages) == len(carrying)

    @property
    def words_per_page(self) -> float:
        return len(self.words) / self.page_count if self.page_count else 0.0

    @property
    def is_sparse(self) -> bool:
        """Fewer than 20 words a page: readable, but thin enough to be worth saying so in a report.
        A signal for the reader, never a decision -- see :attr:`is_born_digital`."""
        return self.page_count > 0 and self.words_per_page < 20

    def page(self, number: int) -> Page | None:
        for page in self.pages:
            if page.number == number:
                return page
        return None

    def words_on_page(self, number: int) -> tuple[Word, ...]:
        return tuple(w for w in self.words if w.page == number)

    def column_of(self, word: Word) -> ColumnBand | None:
        for band in self.columns:
            if band.page == word.page and band.contains(word):
                return band
        return None

    def words_in_box(
        self, page: int, box: tuple[float, float, float, float], *, min_overlap: float = 0.5
    ) -> tuple[Word, ...]:
        """Words whose own area falls mostly inside ``box``.

        This is how a table cell becomes the *words* it contains. ExtractBench grounds at word
        level -- Appendix B.4 p.23 of arXiv 2607.29677 says so explicitly -- so evidence is the
        words, never the cell rectangle. A cell box is several times the area of the value inside
        it and would make IoU >= 0.5 trivial to satisfy.
        """
        x0, y0, x1, y1 = box
        hits = []
        for word in self.words_on_page(page):
            ix0, iy0 = max(word.x0, x0), max(word.y0, y0)
            ix1, iy1 = min(word.x1, x1), min(word.y1, y1)
            inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
            area = (word.x1 - word.x0) * (word.y1 - word.y0)
            if area > 0 and inter / area >= min_overlap:
                hits.append(word)
        return tuple(hits)

    def words_in_span(self, start: int, end: int) -> tuple[Word, ...]:
        """The words a char span covers -- the inverse of ``Evidence.char_span``.

        FR-7.8: what a reviewer was looking at is reconstructed from stored state rather than
        regenerated by re-running the extractor. The stored state is the span; this is the
        function that turns it back into boxes on a page.
        """
        return tuple(w for w in self.words if w.start < end and w.end > start)

    def snippet(self, start: int, end: int, *, context: int = 40) -> str:
        return self.text[max(0, start - context) : min(len(self.text), end + context)]



def _image_area_ratio(page: pymupdf.Page) -> float:
    """Fraction of ``page`` covered by image blocks, clamped to 1.0 (ADR-004).

    Overlapping images are summed rather than unioned, so the figure is an upper bound on coverage.
    That is the safe direction: it can only push a page towards being called a picture, and a page
    wrongly called a picture is declined and visible, while a scan wrongly called typeset is
    grounded and silent.
    """
    area = abs(page.rect.width * page.rect.height)
    if area <= 0:
        return 0.0
    covered = 0.0
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") == 1:  # 1 == image, 0 == text
            x0, y0, x1, y1 = block["bbox"]
            covered += abs((x1 - x0) * (y1 - y0))
    return min(covered / area, 1.0)


def layer_cache_key(document_sha256: str) -> str:
    """The cache identity: content hash plus extractor version, never the file path.

    Keying on the path would hand back a stale layer for a supplier who reposted a revised
    datasheet under the same filename -- precisely the case the document register exists to catch.
    """
    return f"{document_sha256}@{LAYOUT_VERSION}"


_CACHE: dict[str, TextLayer] = {}


def extract_layer(
    path: Path | str, *, document_sha256: str = "", use_cache: bool = True
) -> TextLayer:
    """Build (or return the cached) canonical layer for a PDF.

    Word order is PyMuPDF's reading order -- not sorted, not reflowed. Deliberate: reading order is
    stable for identical bytes, and any "improvement" to the ordering moves every offset after it
    and is therefore a version bump, not a patch.
    """
    path = Path(path)
    digest = document_sha256 or hashlib.sha256(path.read_bytes()).hexdigest()
    key = layer_cache_key(digest)
    if use_cache and key in _CACHE:
        return _CACHE[key]

    document = pymupdf.open(path)
    words: list[Word] = []
    parts: list[str] = []
    pages: list[Page] = []
    offset = 0

    for page_index, page in enumerate(document, start=1):
        pages.append(
            Page(
                number=page_index,
                width=float(page.rect.width),
                height=float(page.rect.height),
                image_area_ratio=_image_area_ratio(page),
            )
        )
        for x0, y0, x1, y1, text, block, line, _word_index in page.get_text("words"):
            words.append(
                Word(
                    text=text,
                    page=page_index,
                    start=offset,
                    end=offset + len(text),
                    x0=float(x0),
                    y0=float(y0),
                    x1=float(x1),
                    y1=float(y1),
                    block=int(block),
                    line=int(line),
                )
            )
            parts.append(text)
            offset += len(text) + len(JOIN)

    layer = TextLayer(
        text=JOIN.join(parts),
        words=tuple(words),
        pages=tuple(pages),
        columns=tuple(_column_bands(tuple(words), tuple(pages))),
        document_sha256=digest,
    )
    if use_cache:
        _CACHE[key] = layer
    return layer


def _crosses_a_block(cut: float, extents: list[list[float]]) -> bool:
    """Whether any text block spans this x position.

    A table row is one block running the width of the table, so the whitespace between its columns
    is not a gutter however wide it looks.
    """
    return any(x0 < cut < x1 for x0, x1 in extents)


def _column_bands(words: tuple[Word, ...], pages: tuple[Page, ...]) -> list[ColumnBand]:
    """Split each page into vertical bands separated by gutters (FR-1.6).

    Two observations, in order, and the second is what stops a table from being mistaken for two
    products:

    1. Project every word onto the x axis and find the whitespace wider than
       ``COLUMN_GAP_FRACTION`` of the page.
    2. **Reject any gap that a text block spans.** A table row is one block running the width of
       the table, so the whitespace between its columns is not a gutter however wide it looks; a
       genuine two-column page has blocks that stop at the gutter. Without this, a wide-column
       ordering table splits into one "column" per table column, and the text-window fallback can
       never find a value at all.

    It observes whitespace and block extents rather than inferring intent, so it can fail in only
    one direction -- merging columns that sit close together, which makes the audit *more* likely to
    decline and never more likely to attribute a value to the wrong product.
    """
    bands: list[ColumnBand] = []
    for page in pages:
        page_words = [w for w in words if w.page == page.number]
        spans = sorted(((w.x0, w.x1) for w in page_words), key=lambda s: s[0])
        if not spans:
            bands.append(ColumnBand(page=page.number, index=0, x0=0.0, x1=page.width))
            continue

        blocks: dict[int, list[float]] = {}
        for word in page_words:
            extent = blocks.setdefault(word.block, [word.x0, word.x1])
            extent[0] = min(extent[0], word.x0)
            extent[1] = max(extent[1], word.x1)

        extents = list(blocks.values())
        gutter = page.width * COLUMN_GAP_FRACTION
        groups: list[list[float]] = [[spans[0][0], spans[0][1]]]
        for x0, x1 in spans[1:]:
            gap = x0 - groups[-1][1]
            cut = groups[-1][1] + gap / 2
            if gap > gutter and not _crosses_a_block(cut, extents):
                groups.append([x0, x1])
            else:
                groups[-1][1] = max(groups[-1][1], x1)

        for index, (x0, x1) in enumerate(groups):
            # Widen each band to the midpoint of its gutters so that a word straddling an edge
            # still lands in exactly one band. The bands must tile the page: a word belonging to no
            # band would be silently unattributable, which is the failure FR-1.6 is about.
            left = 0.0 if index == 0 else (groups[index - 1][1] + x0) / 2
            right = page.width if index == len(groups) - 1 else (x1 + groups[index + 1][0]) / 2
            bands.append(ColumnBand(page=page.number, index=index, x0=left, x1=right))
    return bands
