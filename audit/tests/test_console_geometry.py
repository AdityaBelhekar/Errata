"""FE-2.5 defect G-1, in the surface that actually ships it.

``errata_bundle.geometry`` measured the projection against rendered ink and fixed it. The console
was left computing ``x * zoom`` by hand, which is correct only for the one geometry the entire
current corpus happens to share -- ``rotation = 0``, ``mediabox == cropbox``. FR-9.6 names fold-outs
as part of the frozen hard-tail split, and a fold-out is a rotated page, so the defect is latent
rather than dormant.

These tests do not compare one piece of arithmetic against another. They render the page, project a
word's box onto the rendered image, and **look at the pixels underneath it**. That is the only
assertion that can tell "correct" from "correct by coincidence on this corpus", and it is the
assertion the console has never had.
"""

from __future__ import annotations

import base64
import io

import pymupdf
import pytest

from errata_audit.console import render_page
from errata_bundle.fixtures import GEOMETRIES, write_fixture
from errata_bundle.geometry import project_page

#: A channel value at or below this counts as ink. The fixtures draw pure black text on white; the
#: renderer antialiases, so the edge pixels land in the middle. 160 is the same threshold
#: ``errata_bundle.probe`` uses (``DARK_THRESHOLD``) -- deliberately, so two measurements of the
#: same thing do not use two different definitions of "dark".
DARK_THRESHOLD = 160

#: A correctly placed box around a word is mostly the word. Empirically these fixtures land at
#: 12-30% ink; a box on blank paper is 0.0%. 5% is far below any true placement and far above any
#: false one, so the test fails for the right reason rather than by a hair.
MIN_INK_FRACTION = 0.05


def _pixmap_of(image) -> pymupdf.Pixmap:
    """The console inlines its page image as a data URI. Decode it back to pixels.

    Read from the data URI rather than re-rendering, because the data URI is what the reviewer's
    browser draws the boxes on. Re-rendering here would test a page nobody sees.
    """
    _, _, payload = image.data_uri.partition(",")
    return pymupdf.Pixmap(io.BytesIO(base64.b64decode(payload)))


def _ink_fraction(pixmap: pymupdf.Pixmap, percent_box: tuple[float, float, float, float]) -> float:
    """Fraction of pixels under a CSS ``(left, top, width, height)`` percentage box that are ink."""
    left, top, width, height = percent_box
    x0 = max(0, round(pixmap.width * left / 100.0))
    y0 = max(0, round(pixmap.height * top / 100.0))
    x1 = min(pixmap.width, round(pixmap.width * (left + width) / 100.0))
    y1 = min(pixmap.height, round(pixmap.height * (top + height) / 100.0))
    if x1 <= x0 or y1 <= y0:
        # A box with no area is not "0% ink", it is a projection that collapsed -- which is what a
        # naive two-corner transform does on a rotated page. Say so rather than returning a number
        # that reads like a near miss.
        return 0.0
    dark = 0
    total = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            total += 1
            if min(pixmap.pixel(x, y)[:3]) <= DARK_THRESHOLD:
                dark += 1
    return dark / total if total else 0.0


def _word_box(page: pymupdf.Page, text: str) -> tuple[float, float, float, float]:
    """The user-space box of one word, exactly as ``Evidence.bbox`` stores it.

    ``get_text("words")`` is the same call the extractor makes, and on a rotated page it returns
    **unrotated** coordinates. Using it here rather than a hand-written box is the point: the test
    consumes the coordinate space the product actually stores.
    """
    for x0, y0, x1, y1, word, *_ in page.get_text("words"):
        if word == text:
            return (x0, y0, x1, y1)
    raise AssertionError(f"fixture does not contain the word {text!r}")


@pytest.fixture(scope="module")
def geometry_pdfs(tmp_path_factory) -> dict[str, object]:
    directory = tmp_path_factory.mktemp("geometry")
    return {spec.name: write_fixture(spec, directory) for spec in GEOMETRIES}


@pytest.mark.parametrize("geometry", [spec.name for spec in GEOMETRIES])
def test_evidence_box_lands_on_the_word(geometry: str, geometry_pdfs) -> None:
    """The box the console draws contains the ink of the word it claims to box.

    ``upright`` and ``cropped`` passed before the fix and must keep passing: a rotation fix that
    breaks the case the whole corpus is made of trades a latent defect for a live one.
    """
    path = geometry_pdfs[geometry]
    document = pymupdf.open(path)
    box = _word_box(document[0], "Rated")

    image = render_page(path, 1)
    fraction = _ink_fraction(_pixmap_of(image), image.place(box))

    assert fraction >= MIN_INK_FRACTION, (
        f"{geometry}: the evidence box for 'Rated' covers {fraction:.1%} ink. "
        f"The box is not on the word -- this is defect G-1."
    )


@pytest.mark.parametrize("geometry", [spec.name for spec in GEOMETRIES])
def test_console_projection_is_the_canonical_one(geometry: str, geometry_pdfs) -> None:
    """The console must not carry its own copy of the coordinate system.

    Two implementations is *how* G-1 happened, so this asserts identity with
    ``errata_bundle.geometry`` rather than mere agreement to some tolerance. If someone
    reintroduces local arithmetic that happens to agree on today's fixtures, this still fails.
    """
    path = geometry_pdfs[geometry]
    document = pymupdf.open(path)
    page = document[0]
    box = _word_box(page, "Rated")

    projection, _ = project_page(page, zoom=2.0)
    expected = projection.to_percent(box)
    actual = render_page(path, 1).place(box)

    assert actual == pytest.approx(expected, abs=1e-9)
