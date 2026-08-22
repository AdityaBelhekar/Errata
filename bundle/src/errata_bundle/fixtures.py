"""Adversarial page geometries, manufactured because the corpus does not contain any.

Every PDF in ``var/`` shares one geometry signature -- origin (0,0), cropbox == mediabox,
rotation 0. Under that signature the naive transform ``x * zoom`` is correct, so a coordinate
system built and tested only against it is **correct by coincidence**, and nothing in the test
suite would notice the difference between that and correct by construction.

A corpus with no counterexamples is not evidence that none exist. It is evidence that nobody has
looked, and the honest response is to manufacture the cases the corpus is missing rather than to
report a pass over the easy ones. This is the same move ``FR-9.6`` makes with the frozen hard-tail
split, applied to page geometry instead of to scans.

Four fixtures, each isolating one thing that breaks the shortcut:

``upright``       the benign case. If this fails, the probe is broken, not the transform.
``rotated_90``   ``/Rotate 90``. Renders landscape from a portrait user space.
``rotated_270``   the other direction, because a sign error passes one and fails the other.
``cropped``       a cropbox inset from the mediabox, so ``page.rect`` starts away from the origin
                  and every naive projection drifts by exactly that offset.

The text is deliberately shaped like the thing being measured -- a rating line reading
``IP66 400 V 16 A`` -- so that a failure is legible as a failure of the product rather than as an
abstract rectangle mismatch.

These are generated, never committed: a fixture written by code that the test then re-derives is
one artefact, and a fixture checked in beside the code that made it is two that can drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

__all__ = ["GEOMETRIES", "FixtureSpec", "write_all", "write_fixture", "write_ocr_over_scan"]


@dataclass(frozen=True, slots=True)
class FixtureSpec:
    name: str
    rotation: int
    crop_inset: float
    """Points inset on every side of the cropbox, relative to the mediabox. 0 = no inset."""

    why: str


GEOMETRIES: tuple[FixtureSpec, ...] = (
    FixtureSpec("upright", 0, 0.0, "the benign case the whole corpus happens to be"),
    FixtureSpec("rotated_90", 90, 0.0, "landscape render from portrait user space"),
    FixtureSpec("rotated_270", 270, 0.0, "the other direction; a sign error passes 90 and fails this"),
    FixtureSpec("cropped", 0, 36.0, "page.rect starts off the origin; naive projection drifts by the inset"),
)

#: Lines drawn on every fixture page. Positions are in unrotated user space, chosen to sit well
#: inside a 36pt cropbox inset so the cropped fixture still contains all of them.
_LINES: tuple[tuple[float, float, str, float], ...] = (
    (72.0, 120.0, "TYPE 4C-M SERIES II", 11.0),
    (72.0, 160.0, "IP66 400 V 16 A", 18.0),
    (72.0, 200.0, "Rated current 16 A", 11.0),
    (72.0, 240.0, "Ingress protection IP66", 11.0),
    (300.0, 160.0, "Second column 10 A", 11.0),
    (72.0, 520.0, "Far down the page 6 kA", 11.0),
)


def write_fixture(spec: FixtureSpec, directory: Path) -> Path:
    """Write one fixture PDF and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"geometry-{spec.name}.pdf"

    document = pymupdf.open()
    page = document.new_page(width=595.0, height=842.0)
    for x, y, text, size in _LINES:
        # helv is a base-14 font: present in every viewer, no embedding, and identical bytes on
        # every machine -- which matters because these fixtures back a determinism claim.
        page.insert_text((x, y), text, fontname="helv", fontsize=size, color=(0, 0, 0))

    if spec.crop_inset:
        media = page.mediabox
        page.set_cropbox(
            pymupdf.Rect(
                media.x0 + spec.crop_inset,
                media.y0 + spec.crop_inset,
                media.x1 - spec.crop_inset,
                media.y1 - spec.crop_inset,
            )
        )
    if spec.rotation:
        page.set_rotation(spec.rotation)

    document.save(str(path))
    document.close()
    return path


def write_all(directory: Path) -> dict[str, Path]:
    return {spec.name: write_fixture(spec, directory) for spec in GEOMETRIES}


def write_ocr_over_scan(directory: Path, *, name: str = "ocr-over-scan") -> Path:
    """A scanned page carrying an OCR text layer -- the counterexample for ADR-004.

    ``H28-1957-Part-I.pdf`` is the real instance: 100% image area, an OCR layer, 161,731 words, and
    nothing in the pipeline declining it. It lives in ``var/``, which is gitignored under FR-9.5
    because the documents are the manufacturers' and not ours to redistribute, so a test that
    depends on it is a test that does not run on a fresh clone.

    So the counterexample is manufactured here, the same way the rotated and cropped geometries
    were: render typeset text to a raster, place the raster as the whole page, and lay the same
    words back over it in render mode 3 -- invisible. That is structurally what an OCR tool
    produces, and it reproduces both properties that matter: ``image_area_ratio == 1.0``, and a
    word list that looks entirely reasonable until you ask where it came from.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.pdf"

    typeset = pymupdf.open()
    page = typeset.new_page(width=595.0, height=842.0)
    for x, y, text, size in _LINES:
        page.insert_text((x, y), text, fontname="helv", fontsize=size, color=(0, 0, 0))
    raster = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")
    typeset.close()

    scanned = pymupdf.open()
    scan_page = scanned.new_page(width=595.0, height=842.0)
    scan_page.insert_image(scan_page.rect, stream=raster)
    for x, y, text, size in _LINES:
        # render_mode=3 is "invisible": drawn into the text layer, never onto the page. This is how
        # every OCR tool attaches its reading to a scan, and why the words extract cleanly.
        scan_page.insert_text((x, y), text, fontname="helv", fontsize=size, render_mode=3)

    scanned.save(str(path))
    scanned.close()
    return path
