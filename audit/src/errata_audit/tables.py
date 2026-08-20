"""FR-1.5 -- table structure with cell, row-header and column-header roles.

    "A value in a table cell can resolve its row and column headers (required by FR-4.3)."

That requirement does more work than it looks. FR-7.3 says a number in an engineering table is
never shown to a reviewer without the headers that give it meaning, and the reason is that ``10``
is not a fact. ``10`` under a column headed *Rated current In A*, in a row whose type designation
is *S201M-B10UC*, is a fact. A system that boxes the ``10`` and not the header has explained
nothing, and a reviewer who accepts it has accepted a number on trust -- which is the habit this
product exists to break.

**The merged-cell trap, which is real in these documents and was found while building the
annotation engine.** In the ABB
S200 ordering tables the *Number of poles* column states ``1`` once and leaves the next twenty rows
blank: the cell is merged down the block. Read naively, twenty SKUs have no pole count. Resolved by
the cell rectangle they all correctly have one, because the merged cell's box spans them.

This module resolves merges **by box geometry, never by carrying the last non-empty value
forward.** Carrying forward guesses; geometry observes. The distinction matters because the two
agree on every well-formed table and disagree exactly where the table is malformed -- which is the
case the audit must decline rather than invent an answer for.
"""

from __future__ import annotations

import contextlib
import sys
import warnings
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pymupdf

__all__ = [
    "TABLES_VERSION",
    "Cell",
    "CellRole",
    "Table",
    "extract_tables",
]

TABLES_VERSION = "errata-tables/1.0.0"

#: A cell taller than this multiple of the table's own median cell height is read as spanning
#: several rows. Compared against the median rather than against the containing row's height,
#: because PyMuPDF assigns a merged cell's full height to the row it starts in -- so
#: ``cell_height > row_height`` is False for the one cell it needs to be True for. Verified on
#: page 8 of the ABB S200 catalogue, where the merged pole cell and its row both measure 110.2pt.
MERGE_HEIGHT_RATIO = 1.5


class CellRole(str, Enum):
    """FR-1.5's three roles, made explicit rather than implied by position.

    A role is a claim about the document's structure and it belongs in the data, not in the reader's
    head. ``COLUMN_HEADER`` and ``ROW_HEADER`` cells are evidence in their own right: FR-7.3
    renders them alongside the value, so they have to survive as first-class objects all the way to
    the console.
    """

    DATA = "data"
    COLUMN_HEADER = "column_header"
    ROW_HEADER = "row_header"


@dataclass(frozen=True, slots=True)
class Cell:
    """One table cell, with the headers that give its contents meaning."""

    text: str
    page: int
    row: int
    column: int
    bbox: tuple[float, float, float, float]
    role: CellRole
    column_header: str
    row_header: str
    """The row's leading identifying cell -- for an ordering table, the type designation."""

    is_merged_source: bool = False
    """True when this cell's box spans more rows than its own, i.e. it states the value for a block
    of rows rather than for one."""


@dataclass(frozen=True, slots=True)
class Table:
    page: int
    index: int
    bbox: tuple[float, float, float, float]
    column_headers: tuple[str, ...]
    cells: tuple[Cell, ...]
    tables_version: str = TABLES_VERSION

    @property
    def rows(self) -> tuple[int, ...]:
        return tuple(sorted({c.row for c in self.cells}))

    def column(self, header: str) -> tuple[Cell, ...]:
        return tuple(c for c in self.cells if c.column_header == header)

    def cell(self, row: int, header: str) -> Cell | None:
        """The cell in ``row`` under ``header``, resolving merged cells by geometry.

        Falls back to the merged cell whose box vertically contains this row. This is the
        difference between "twenty SKUs have no pole count" and "twenty SKUs are 1-pole", and it is
        resolved by observing the box rather than by carrying the last value forward, which would
        be a guess dressed as a lookup.
        """
        for candidate in self.cells:
            if candidate.row == row and candidate.column_header == header:
                return candidate

        row_cells = [c for c in self.cells if c.row == row]
        if not row_cells:
            return None
        midpoint = sum((c.bbox[1] + c.bbox[3]) / 2 for c in row_cells) / len(row_cells)

        for candidate in self.cells:
            if (
                candidate.column_header == header
                and candidate.is_merged_source
                and candidate.bbox[1] <= midpoint <= candidate.bbox[3]
            ):
                return candidate
        return None

    def header_cell(self, header: str) -> Cell | None:
        """The column-header cell itself, so FR-7.3 can box the header and not just print it."""
        for candidate in self.cells:
            if candidate.role is CellRole.COLUMN_HEADER and candidate.text == header:
                return candidate
        return None


def _clean(text: str | None) -> str:
    """Collapse the newlines PyMuPDF leaves inside a header cell.

    ``'Rated\\ncurrent\\nI\\nn\\nA'`` is one header and every downstream comparison wants it as one
    line. Whitespace only -- no other normalisation, because a header is evidence and rewriting
    evidence to be tidier is how a citation stops matching the page it came from.
    """
    return " ".join((text or "").split())


_CACHE: dict[tuple[str, int], tuple[Table, ...]] = {}


def extract_tables(
    path: Path | str, *, min_rows: int = 2, document_sha256: str = "", use_cache: bool = True
) -> tuple[Table, ...]:
    """Every table in the document, with per-cell boxes and resolved header roles.

    Cached on ``(content hash, min_rows)`` for the same reason the text layer is (FR-1.4): table
    detection is the expensive pass, an audit of a catalog asks for the same document hundreds of
    times, and caching on the path would serve a stale answer for a revised datasheet posted at the
    same filename. When no hash is supplied one is computed from the bytes -- reading a file is
    cheap next to detecting its tables, and guessing at identity from a path is not worth the
    seconds it saves.
    """
    key = ((document_sha256 or _digest(path)), min_rows)
    if use_cache and key in _CACHE:
        return _CACHE[key]
    tables = _extract_tables_uncached(path, min_rows=min_rows)
    if use_cache:
        _CACHE[key] = tables
    return tables


def _digest(path: Path | str) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _extract_tables_uncached(path: Path | str, *, min_rows: int = 2) -> tuple[Table, ...]:
    with warnings.catch_warnings(), contextlib.redirect_stdout(sys.stderr):
        # PyMuPDF advertises its layout add-on on every find_tables() call. Noted, not needed:
        # these are ruled tables and the built-in finder resolves them correctly.
        #
        # **Finding N19, raised and fixed in R3.** `warnings.simplefilter("ignore")` never
        # silenced it, because the advertisement is not a warning -- it is a bare `print` to
        # stdout. That put a line of English on top of every `--json` payload this repository
        # emits, so `errata-audit catalog --json | jq` failed for anyone who tried it, and the
        # tests never saw it because they call the API rather than the process. The message is
        # redirected to stderr rather than discarded: a library telling us something is not
        # noise, it is just on the wrong stream.
        warnings.simplefilter("ignore")
        document = pymupdf.open(Path(path))
        tables: list[Table] = []

        for page_index, page in enumerate(document, start=1):
            for table_index, found in enumerate(page.find_tables().tables):
                rows = found.extract()
                if len(rows) < min_rows:
                    continue

                headers = tuple(_clean(h) for h in (found.header.names if found.header else rows[0]))
                header_row = _header_row_index(found)

                heights = sorted(
                    bbox[3] - bbox[1]
                    for row_obj in found.rows
                    for bbox in row_obj.cells
                    if bbox is not None
                )
                median_height = heights[len(heights) // 2] if heights else 0.0

                cells: list[Cell] = []
                for row_index, (row_obj, row_text) in enumerate(
                    zip(found.rows, rows, strict=False)
                ):
                    # The row header is the row's first non-empty cell **that is not a merged
                    # source**. A merged cell states a value for a block of rows, so by definition
                    # it cannot identify one of them: in the ABB ordering tables the leftmost cell
                    # is a pole count stated once for twenty rows, and taking it as the row header
                    # would label twenty different products "1".
                    row_header = next(
                        (
                            _clean(value)
                            for bbox, value in zip(row_obj.cells, row_text, strict=False)
                            if bbox is not None
                            and _clean(value)
                            and not (
                                median_height > 0
                                and (bbox[3] - bbox[1]) > median_height * MERGE_HEIGHT_RATIO
                            )
                        ),
                        "",
                    )

                    for col_index, (bbox, value) in enumerate(
                        zip(row_obj.cells, row_text, strict=False)
                    ):
                        if bbox is None:
                            continue
                        text = _clean(value)
                        if not text:
                            continue
                        role = _role(row_index, col_index, header_row, text, row_header)
                        cell_height = bbox[3] - bbox[1]
                        cells.append(
                            Cell(
                                text=text,
                                page=page_index,
                                row=row_index,
                                column=col_index,
                                bbox=tuple(float(v) for v in bbox),  # type: ignore[arg-type]
                                role=role,
                                column_header=headers[col_index]
                                if col_index < len(headers)
                                else "",
                                row_header=row_header,
                                is_merged_source=(
                                    median_height > 0
                                    and cell_height > median_height * MERGE_HEIGHT_RATIO
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


def _header_row_index(found: object) -> int:
    """Which physical row carries the column headers, or -1 when they are external.

    PyMuPDF reports an external header for tables whose heading sits above the ruled box. Treating
    that case as "row 0 is the header" would demote a real data row to a header and lose a SKU.
    """
    header = getattr(found, "header", None)
    if header is None:
        return 0
    if getattr(header, "external", False):
        return -1
    return 0


def _role(row: int, column: int, header_row: int, text: str, row_header: str) -> CellRole:
    if row == header_row:
        return CellRole.COLUMN_HEADER
    if text == row_header and column == 0:
        return CellRole.ROW_HEADER
    if text == row_header:
        # The identifying cell is not always the leftmost one: an ordering table whose first
        # column is a merged pole count puts the type designation in column 1. The role follows
        # the identity, not the position.
        return CellRole.ROW_HEADER
    return CellRole.DATA
