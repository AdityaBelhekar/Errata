"""FE-2.5 / FR-7.2 -- the coordinate system, stated once so nothing downstream has to guess.

    "Word-level evidence box rendered on the source page at the stored span's projection.
     Box lands on the value's words, not the paragraph or page."

This module is the *only* place in the system that converts a PDF user-space box into something a
browser can draw. It exists because that conversion is the highest-consequence, lowest-glamour
piece of the product: an evidence box that lands two lines below the value is the failure mode the
PRD's own risk register calls "product self-discredits on screen", and it is invisible in every
test that does not look at pixels.

Why this is not just ``x * zoom`` -- measured, not assumed
---------------------------------------------------------

``errata_audit.console.PageImage.place`` computes ``x * zoom``. Every PDF in ``var/`` shares one
geometry signature -- ``rect = (0, 0, 595.3, 841.9)``, ``mediabox == cropbox``, ``rotation = 0`` --
so on that corpus it is correct, and nothing in the suite can tell the difference between correct
by construction and correct by coincidence.

So the missing counterexamples were manufactured (:mod:`errata_bundle.fixtures`) and the projection
measured against rendered ink (:mod:`errata_bundle.probe`). Three candidate failures, three
different answers, and only one of them is what anybody expected:

* **A cropbox offset from the mediabox — not a problem.** PyMuPDF normalises ``page.rect`` to the
  origin and returns ``get_text("words")`` in that same normalised space, so the offset is absorbed
  before it reaches us. Verified on the ``cropped`` fixture: cropbox ``(36, 36, 559, 806)``,
  ``page.rect`` ``(0, 0, 523, 770)``, projection clean. This is undocumented behaviour we now
  depend on, which is exactly why the fixture exists to pin it.

* **Sub-pixel zoom rounding — not a problem**, provided the divisor is the pixmap's own width and
  not ``rect.x1 * zoom``. It is, here and in ``place``.

* **Page rotation — BROKEN, and badly.** ``page.get_text("words")`` returns boxes in **unrotated**
  user space, while ``page.rect`` and the rendered pixmap are in **rotated** space. On the
  ``rotated_90`` fixture the union of all word boxes projects naively to ``(144, 216, 803, 1047)``
  while the ink is actually at ``(640, 144, 1458, 802)``. Not a drift of a few pixels -- a
  different part of the page. Applying ``page.rotation_matrix`` first gives
  ``(637, 144, 1468, 803)``, which is the ink.

  This is a latent defect in the shipped console (``FE-2.5 defect G-1``). It cannot fire on the
  current corpus and it is certain to fire in production: rotated pages are how datasheets carry
  fold-out tables and landscape dimension drawings, and **FR-9.6 names fold-outs as part of the
  frozen hard-tail split**. The first hard-tail document with ``/Rotate 90`` would have put every
  evidence box in the wrong place, which is the PRD's own "product self-discredits on screen".

The fix is not another special case. It is to stop composing the transform by hand and carry
**the full affine matrix the renderer used**, which is what :func:`project_page` now does.

The contract
------------

Everything downstream -- the bundle, the console, the SVG overlay -- consumes
:class:`PageProjection` and nothing else. It carries the transform *and* the numbers needed to
verify it, so a stored bundle can be checked years later without re-opening the PDF.

Boxes are emitted as **fractions of the rendered page**, not pixels. A fraction survives the image
being scaled to fit a screen, a print stylesheet, or a 3x display; a pixel does not, and a box that
drifts off its words when a reviewer resizes the window is the same failure as one that was wrong
to begin with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pymupdf

__all__ = [
    "GEOMETRY_VERSION",
    "Box",
    "PageProjection",
    "project_page",
]

#: Stamped into every projection and every bundle. Bump on any change that could move a rendered
#: box by a pixel. A stored projection is meaningless without the version that produced it, for the
#: same reason ``LAYOUT_VERSION`` travels with a char span.
GEOMETRY_VERSION = "errata-geometry/1.0.0"

#: (x0, y0, x1, y1). In PDF user space when it comes off a ``Word``; in page fractions once
#: projected. The type is the same and the *meaning* is not, which is why every function below says
#: which one it takes and which one it returns.
Box = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class PageProjection:
    """How one rendered page maps PDF user space onto the image a browser will show.

    Constructed by :func:`project_page` from the renderer's own output. Never by hand -- a
    hand-built projection is an assumption wearing a dataclass.
    """

    page: int
    """1-indexed, matching ``Evidence.page`` and ``Word.page``."""

    zoom: float

    rect: Box
    """``page.rect`` in PDF user space. Note ``x0``/``y0`` are not necessarily zero."""

    rotation: int
    """Degrees, as the PDF declares. Recorded for the audit trail; the arithmetic below does not
    need it, because ``page.rect`` and ``get_text("words")`` are both already in rotated display
    space. Recorded precisely *because* that is easy to forget and expensive to rediscover."""

    pixel_width: int
    pixel_height: int
    """The rendered image's true size, from the pixmap -- not ``rect * zoom`` rounded by hand."""

    origin_x: float
    origin_y: float
    """The pixmap's integer-rect origin in device space. Subtracted from every projected point."""

    matrix: tuple[float, float, float, float, float, float] = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    """The COMPLETE PDF-user-space -> device-space affine, ``(a, b, c, d, e, f)``, as the renderer
    used it: ``page.rotation_matrix * Matrix(zoom, zoom)``.

    Stored rather than recomposed from ``zoom`` and ``rotation``, because recomposing it is exactly
    the mistake that produced defect G-1. A projection that carries its own matrix can be replayed
    years later by anything that can multiply, including thirty lines of JavaScript in the console,
    with no PDF library and no knowledge of how PyMuPDF spells rotation."""

    geometry_version: str = GEOMETRY_VERSION

    metadata: dict[str, Any] = field(default_factory=dict)

    # -- the transform ---------------------------------------------------------------------

    def to_pixels(self, box: Box) -> Box:
        """PDF user-space box -> pixel box on the rendered image.

        All four corners are transformed and the bounding box taken, rather than the two opposite
        corners. Under a rotation the two are not the same: transforming only ``(x0, y0)`` and
        ``(x1, y1)`` of a 90-degree-rotated page yields a rectangle with negative width. This is
        the arithmetic half of defect G-1.
        """
        a, b, c, d, e, f = self.matrix
        x0, y0, x1, y1 = box
        xs = []
        ys = []
        for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            xs.append(a * px + c * py + e - self.origin_x)
            ys.append(b * px + d * py + f - self.origin_y)
        return (min(xs), min(ys), max(xs), max(ys))

    def to_fraction(self, box: Box) -> Box:
        """PDF user-space box -> fraction of the rendered image, 0..1.

        This is what the bundle stores and what the SVG overlay consumes. Fractions rather than
        pixels so the page can be scaled freely without the boxes drifting off the words.
        """
        px0, py0, px1, py1 = self.to_pixels(box)
        return (
            px0 / self.pixel_width,
            py0 / self.pixel_height,
            px1 / self.pixel_width,
            py1 / self.pixel_height,
        )

    def to_percent(self, box: Box) -> Box:
        """As :meth:`to_fraction`, in percent, as ``(left, top, width, height)``.

        The shape CSS wants. Kept separate from :meth:`to_fraction` because the argument order
        differs -- ``(x0, y0, x1, y1)`` against ``(left, top, w, h)`` -- and silently swapping
        between the two conventions is how boxes end up mirrored.
        """
        fx0, fy0, fx1, fy1 = self.to_fraction(box)
        return (100.0 * fx0, 100.0 * fy0, 100.0 * (fx1 - fx0), 100.0 * (fy1 - fy0))

    def union(self, boxes: list[Box] | tuple[Box, ...]) -> Box | None:
        """Smallest PDF-space box containing all of ``boxes``.

        Word-level evidence is several words; the box a reviewer sees is their union. Returns
        ``None`` for an empty input rather than a degenerate rectangle at the origin, because a
        zero-size box drawn at (0,0) looks like a bug in the corner of the page and reads as one.
        """
        if not boxes:
            return None
        return (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )

    def as_dict(self) -> dict[str, Any]:
        """The form written into an Evidence Bundle manifest."""
        return {
            "page": self.page,
            "zoom": self.zoom,
            "rect": list(self.rect),
            "rotation": self.rotation,
            "pixel_width": self.pixel_width,
            "pixel_height": self.pixel_height,
            "origin_x": self.origin_x,
            "origin_y": self.origin_y,
            "matrix": list(self.matrix),
            "geometry_version": self.geometry_version,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PageProjection:
        return cls(
            page=int(payload["page"]),
            zoom=float(payload["zoom"]),
            rect=tuple(payload["rect"]),  # type: ignore[arg-type]
            rotation=int(payload["rotation"]),
            pixel_width=int(payload["pixel_width"]),
            pixel_height=int(payload["pixel_height"]),
            origin_x=float(payload["origin_x"]),
            origin_y=float(payload["origin_y"]),
            matrix=tuple(payload["matrix"]),  # type: ignore[arg-type]
            geometry_version=str(payload.get("geometry_version", "")),
        )


def project_page(page: pymupdf.Page, *, zoom: float) -> tuple[PageProjection, pymupdf.Pixmap]:
    """Render one page and return the projection **the renderer actually used**.

    The pixmap comes back with the projection because the two must agree: a projection describing
    one render and an image from another is worse than no projection, and separating the calls is
    the easiest way to let that happen.
    """
    # The renderer applies the page's rotation before the zoom. `get_pixmap(matrix=Matrix(z, z))`
    # does that internally; `get_text("words")` does NOT, and returns unrotated coordinates. So the
    # transform we must store is the composition, and it must be composed here rather than
    # reconstructed by every consumer. See defect G-1 in the module docstring.
    matrix = page.rotation_matrix * pymupdf.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))

    # `irect` is the pixmap's position in device space. For a page whose rect starts at the
    # user-space origin this is (0, 0) and the shortcut holds; for a cropbox-offset page it is not,
    # and this subtraction is the whole difference between a box on the words and a box in the
    # margin. Read off the pixmap rather than recomputed, so it cannot disagree with the image.
    # `irect` is a plain 4-tuple in PyMuPDF 1.28, not a Rect. Read positionally rather than by
    # attribute so a version that returns either shape keeps working.
    irect = tuple(pixmap.irect)
    rect = page.rect

    projection = PageProjection(
        page=page.number + 1,
        zoom=zoom,
        rect=(rect.x0, rect.y0, rect.x1, rect.y1),
        rotation=page.rotation,
        pixel_width=pixmap.width,
        pixel_height=pixmap.height,
        origin_x=float(irect[0]),
        origin_y=float(irect[1]),
        matrix=(matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f),
    )
    return projection, pixmap
