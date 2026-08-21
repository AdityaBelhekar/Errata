"""FE-2.5 — the coordinate system, pinned.

Two kinds of test here and the distinction matters:

* **Regression tests for defect G-1.** Page rotation. These assert that the naive transform is
  *wrong* as well as that ours is right, because a test that only checks the fix passes equally
  well if someone later reverts to the shortcut on a corpus with no rotated pages -- which is
  exactly the situation that hid the defect for the life of the project.

* **Characterisation tests for PyMuPDF behaviour we depend on.** The cropbox normalisation is
  undocumented. We rely on it. If a future release changes it, these fail loudly instead of
  evidence boxes quietly drifting into the margin.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from errata_bundle.fixtures import GEOMETRIES, write_all
from errata_bundle.geometry import project_page
from errata_bundle.probe import probe_page


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory) -> dict[str, Path]:
    return write_all(tmp_path_factory.mktemp("geometry"))


def _words(page):
    class W:
        __slots__ = ("bbox", "text")

        def __init__(self, entry):
            self.bbox = (entry[0], entry[1], entry[2], entry[3])
            self.text = entry[4]

    return [W(e) for e in page.get_text("words")]


@pytest.mark.parametrize("spec", GEOMETRIES, ids=lambda s: s.name)
def test_projection_registers_on_the_ink(fixtures, spec):
    """Every fixture geometry: the projected boxes land on the rendered glyphs.

    Measured by registration, not by eye -- the modal offset over every word on the page must be
    exactly (0, 0), and most words must agree with it. See probe.py for why this metric and not
    a bounding-box comparison.
    """
    document = pymupdf.open(str(fixtures[spec.name]))
    try:
        probe = probe_page(document[0], _words(document[0]), zoom=2.0)
    finally:
        document.close()

    assert probe.measurable, f"{spec.name}: no measurable words -- the probe cannot see this page"
    assert probe.modal_offset == (0, 0), (
        f"{spec.name} ({spec.why}): projected boxes are displaced by {probe.modal_offset} px. "
        f"Agreement {probe.agreement:.0%}, mean displacement {probe.mean_displacement:.2f}px."
    )
    assert probe.agreement >= 0.6
    assert probe.clean


def test_rotation_is_actually_applied(fixtures):
    """G-1 regression: the naive `x * zoom` transform must FAIL on a rotated page.

    `page.get_text("words")` returns UNROTATED user-space coordinates while `page.rect` and the
    rendered pixmap are in ROTATED space. On the 90-degree fixture the two disagree by most of the
    page, and this test asserts that disagreement so the shortcut cannot be reintroduced silently.

    If this test ever fails because the naive box now matches, PyMuPDF has changed which space
    `get_text` reports in, and `project_page` must be re-derived rather than trusted.
    """
    document = pymupdf.open(str(fixtures["rotated_90"]))
    try:
        page = document[0]
        projection, _ = project_page(page, zoom=2.0)
        words = _words(page)
        union = (
            min(w.bbox[0] for w in words),
            min(w.bbox[1] for w in words),
            max(w.bbox[2] for w in words),
            max(w.bbox[3] for w in words),
        )
        correct = projection.to_pixels(union)
        naive = tuple(v * 2.0 for v in union)
    finally:
        document.close()

    # The rotation must be visible in the stored transform at all.
    assert projection.rotation == 90
    assert projection.matrix[0] == pytest.approx(0.0, abs=1e-9), (
        "a 90-degree rotation must give a matrix whose 'a' term is zero; "
        f"got {projection.matrix}"
    )

    # And the two answers must be far apart. 'Far' is not a tuned threshold: half the page.
    page_width = projection.pixel_width
    assert abs(correct[0] - naive[0]) > page_width * 0.25, (
        "the naive transform agrees with the rotation-aware one on a rotated page, which means "
        "either the fixture is not rotated or PyMuPDF changed coordinate spaces. Investigate "
        "before trusting any evidence box."
    )


def test_cropbox_offset_is_normalised_by_pymupdf(fixtures):
    """Characterisation: we depend on undocumented behaviour, so we pin it.

    A cropbox inset from the mediabox does NOT shift `page.rect` off the origin -- PyMuPDF
    normalises it and reports word coordinates in the same normalised space. That is why the
    cropbox turned out not to be a source of drift. If a release changes this, the assertion below
    fails and the projection needs an origin term again.
    """
    document = pymupdf.open(str(fixtures["cropped"]))
    try:
        page = document[0]
        assert page.cropbox != page.mediabox, "the fixture is meant to have an inset cropbox"
        assert page.rect.x0 == 0 and page.rect.y0 == 0, (
            "page.rect no longer starts at the origin for a cropped page. PyMuPDF has changed its "
            "normalisation; every stored projection predates the change."
        )
        projection, _ = project_page(page, zoom=2.0)
        assert (projection.origin_x, projection.origin_y) == (0.0, 0.0)
    finally:
        document.close()


def test_fraction_round_trip_is_scale_free(fixtures):
    """A box stored as a fraction reproduces the same pixels at any rendered size.

    This is the property the console relies on: it multiplies stored fractions by whatever width
    the page happens to be on screen. If fractions were not scale-free, every zoom would drift.
    """
    document = pymupdf.open(str(fixtures["upright"]))
    try:
        page = document[0]
        projection, _ = project_page(page, zoom=2.0)
        box = _words(page)[0].bbox
        fraction = projection.to_fraction(box)
    finally:
        document.close()

    for width in (400, 900, 1600):
        height = width * projection.pixel_height / projection.pixel_width
        left = fraction[0] * width
        top = fraction[1] * height
        # Same fractional position at every width, by construction.
        assert left / width == pytest.approx(fraction[0])
        assert top / height == pytest.approx(fraction[1])
        assert 0.0 <= fraction[0] <= 1.0 and 0.0 <= fraction[1] <= 1.0


def test_projection_survives_a_json_round_trip(fixtures):
    """A stored projection must replay years later from its dict alone."""
    document = pymupdf.open(str(fixtures["rotated_270"]))
    try:
        page = document[0]
        projection, _ = project_page(page, zoom=2.0)
        box = _words(page)[3].bbox
    finally:
        document.close()

    from errata_bundle.geometry import PageProjection

    revived = PageProjection.from_dict(projection.as_dict())
    assert revived.to_pixels(box) == pytest.approx(projection.to_pixels(box))
    assert revived.matrix == projection.matrix
