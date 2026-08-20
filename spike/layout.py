"""FR-1.4 — canonical, char-indexed text layer with a per-word bbox map.

The acceptance criterion is not "extracts text". It is:

    "Deterministic for identical input bytes and identical extractor version; cached;
     version-stamped."

Determinism is the whole point. `Evidence.char_span` is an offset into *this* layer, so a claim
made last month is only reconstructible if the same bytes still produce the same offsets. An
extractor that reorders words between versions silently invalidates every stored span while every
test still passes -- which is why the version is stamped into the layer itself rather than left
implicit.

**Scope, per the P3 fence:** born-digital PDFs only. Both ABB S200 datasheets carry real embedded
text layers, so OCR is not on the critical path for the gate-2 corpus. A scanned page produces a
layer with no words, and `is_born_digital` says so rather than the caller discovering it later as
a mysteriously empty extraction.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pymupdf

#: Stamped into every layer. Bump it whenever anything changes that could move a char offset --
#: the joining character, the word ordering, the source library. A stored `char_span` is only
#: meaningful alongside the version that produced it.
LAYOUT_VERSION = "spike-layout/1.0.0"

#: The single character joining words in the canonical layer. Not configurable: it is part of the
#: offset arithmetic, and making it a parameter would let two callers produce two different layers
#: from one document.
JOIN = " "


@dataclass(frozen=True, slots=True)
class Word:
    """One word, its span in the canonical layer, and where it sits on the page."""

    text: str
    page: int
    """1-indexed, matching `Evidence.page` which is `Field(ge=1)`."""

    start: int
    end: int
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


@dataclass(frozen=True, slots=True)
class TextLayer:
    """The canonical text of one document revision, plus the map back to the page."""

    text: str
    words: tuple[Word, ...]
    page_count: int
    layout_version: str = LAYOUT_VERSION

    @property
    def sha256(self) -> str:
        """Hash of the canonical text. Two extractions of the same bytes must agree here."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def is_born_digital(self) -> bool:
        """A rough but honest signal: fewer than 20 words a page means there is no usable text
        layer and the document needs OCR. Stated rather than discovered downstream."""
        return self.page_count > 0 and len(self.words) >= 20 * self.page_count

    def words_on_page(self, page: int) -> tuple[Word, ...]:
        return tuple(w for w in self.words if w.page == page)

    def words_in_box(
        self, page: int, box: tuple[float, float, float, float], *, min_overlap: float = 0.5
    ) -> tuple[Word, ...]:
        """Words whose area falls mostly inside ``box``.

        Used to turn a table cell into the *word* boxes it contains. ExtractBench grounds at word
        level, so gold evidence is the words, not the cell rectangle -- a cell box is far larger
        than the value inside it and would make IoU trivially easy to satisfy, flattering the
        grounding score for no reason.
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

    def snippet(self, start: int, end: int, *, context: int = 40) -> str:
        return self.text[max(0, start - context) : min(len(self.text), end + context)]


def extract_layer(path: Path | str) -> TextLayer:
    """Build the canonical layer for a PDF.

    Word order is whatever PyMuPDF's ``"words"`` extraction gives, which is its reading order --
    NOT sorted, NOT reflowed. That is deliberate: reading order is stable for identical bytes, and
    any "improvement" to the ordering is a version bump because it moves every offset after it.
    """
    document = pymupdf.open(Path(path))
    words: list[Word] = []
    parts: list[str] = []
    offset = 0

    for page_index, page in enumerate(document, start=1):
        for x0, y0, x1, y1, text, *_ in page.get_text("words"):
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
                )
            )
            parts.append(text)
            offset += len(text) + len(JOIN)

    return TextLayer(
        text=JOIN.join(parts),
        words=tuple(words),
        page_count=len(document),
    )
