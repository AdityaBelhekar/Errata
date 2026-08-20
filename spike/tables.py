"""FR-1.5 — table structure with cell, row-header and column-header roles.

    "A value in a table cell can resolve its row and column headers (required by FR-4.3)."

That requirement is doing more work than it looks. FR-7.3 says a number in an engineering table is
never shown to a reviewer without the headers that give it meaning, and the reason is that `10` is
not a fact. `10` under a column headed *Rated current In A*, in a row whose type designation is
*S201M-B10UC*, is a fact. A system that boxes the `10` and not the header has explained nothing.

**The merged-cell trap, which is real in these documents.** In the ABB S200 ordering tables the
*Number of poles* column states `1` once and then leaves the next twenty rows blank -- the cell is
merged down the block. Read naively, twenty SKUs have no pole count. Read by the cell rectangle,
they all correctly have one, because the merged cell's box spans them. This module resolves it by
box geometry rather than by carrying the last non-empty value forward, because carrying forward
guesses and geometry observes.
"""

from __future__ import annotations

import contextlib
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import pymupdf

TABLES_VERSION = "spike-tables/1.0.0"


@dataclass(frozen=True, slots=True)
class Cell:
    """One table cell, with the headers that give its contents meaning."""

    text: str
    page: int
    row: int
    column: int
    bbox: tuple[float, float, float, float]
    column_header: str
    row_header: str
    """The row's leading identifying cell -- for an ordering table, the type designation."""

    is_merged_source: bool = False
    """True when this cell's box spans more rows than its own, i.e. it is the stated value for a
    block of rows rather than for one."""


@dataclass(frozen=True, slots=True)
class Table:
    page: int
    index: int
    bbox: tuple[float, float, float, float]
    column_headers: tuple[str, ...]
    cells: tuple[Cell, ...]

    def column(self, header: str) -> tuple[Cell, ...]:
        return tuple(c for c in self.cells if c.column_header == header)


def _clean(text: str | None) -> str:
    """Collapse the newlines PyMuPDF leaves inside a header cell.

    ``'Rated\\ncurrent\\nI\\nn\\nA'`` is one header, and every downstream comparison wants it as
    one line. Whitespace only -- no other normalisation, because a header is evidence.
    """
    return " ".join((text or "").split())


def extract_tables(path: Path | str, *, min_rows: int = 2) -> tuple[Table, ...]:
    """Every table in the document, with per-cell boxes and resolved headers."""
    with warnings.catch_warnings(), contextlib.redirect_stdout(sys.stderr):
        # PyMuPDF suggests its layout add-on on every find_tables() call. Noted, not needed:
        # these are ruled tables and the built-in finder resolves them correctly.
        warnings.simplefilter("ignore")
        document = pymupdf.open(Path(path))
        tables: list[Table] = []

        for page_index, page in enumerate(document, start=1):
            for table_index, found in enumerate(page.find_tables().tables):
                rows = found.extract()
                if len(rows) < min_rows:
                    continue

                headers = tuple(
                    _clean(h) for h in (found.header.names if found.header else rows[0])
                )

                # Reference height for detecting a merged cell.
                #
                # NOT the containing row's height: PyMuPDF assigns a merged cell's full height to
                # the row it starts in, so `cell_height > row_height` is False for the one cell it
                # needs to be True for. Verified on page 8 of the ABB S200 catalogue, where the
                # merged pole cell and its row both measure 110.2pt. Comparing against the table's
                # own median cell height is robust to that, and to a table whose rows are simply
                # taller than usual.
                heights = sorted(
                    bbox[3] - bbox[1]
                    for row_obj in found.rows
                    for bbox in row_obj.cells
                    if bbox is not None
                )
                median_height = heights[len(heights) // 2] if heights else 0.0

                cells: list[Cell] = []

                for row_index, (row_obj, row_text) in enumerate(zip(found.rows, rows, strict=False)):
                    # The row header is the row's first non-empty cell: for an ordering table
                    # that is the type designation once the merged pole column is skipped.
                    row_header = next((_clean(v) for v in row_text if _clean(v)), "")

                    for col_index, (bbox, value) in enumerate(
                        zip(row_obj.cells, row_text, strict=False)
                    ):
                        if bbox is None:
                            continue
                        text = _clean(value)
                        if not text:
                            continue
                        cell_height = bbox[3] - bbox[1]
                        cells.append(
                            Cell(
                                text=text,
                                page=page_index,
                                row=row_index,
                                column=col_index,
                                bbox=tuple(float(v) for v in bbox),  # type: ignore[arg-type]
                                column_header=headers[col_index] if col_index < len(headers) else "",
                                row_header=row_header,
                                is_merged_source=(
                                    median_height > 0 and cell_height > median_height * 1.5
                                ),
                            )
                        )

                tables.append(
                    Table(
                        page=page_index,
                        index=table_index,
                        bbox=tuple(float(v) for v in found.bbox),  # type: ignore[arg-type]
                        column_headers=headers,
                        cells=tuple(cells),
                    )
                )

    return tuple(tables)


def value_for_row(table: Table, row: int, header: str) -> Cell | None:
    """The cell in ``row`` under ``header``, resolving merged cells by geometry.

    Falls back to the merged cell whose box vertically contains this row. This is the difference
    between "twenty SKUs have no pole count" and "twenty SKUs are 1-pole", and it is resolved by
    observing the box rather than by carrying the last value forward, which would be a guess
    dressed as a lookup.
    """
    for cell in table.cells:
        if cell.row == row and cell.column_header == header:
            return cell

    row_cells = [c for c in table.cells if c.row == row]
    if not row_cells:
        return None
    midpoint = sum((c.bbox[1] + c.bbox[3]) / 2 for c in row_cells) / len(row_cells)

    for cell in table.cells:
        if (
            cell.column_header == header
            and cell.is_merged_source
            and cell.bbox[1] <= midpoint <= cell.bbox[3]
        ):
            return cell
    return None
