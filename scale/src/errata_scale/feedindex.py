"""The feed as a citable document.

R1 grounds every claim in a manufacturer's PDF. R2's T0 tier runs on records that have no PDF at
all, and the temptation there is to emit findings with no evidence -- "trust us, this row is
inconsistent". That would break the one rule the whole product rests on: **no provenance, reject.**

The way out is to notice that the feed *is* a document. It arrived as bytes, those bytes have a
sha256, and a cell inside it has a character span exactly like a cell inside a PDF does. So the
catalog file is registered in the same content-addressed register as every datasheet, and a T0
finding cites ``(row 4,182, column ``rated_current``, chars 391,204-391,210)`` of a named revision.
That is a real span in a real artifact: a reviewer can open the file and see it, and a customer
disputing a finding can be shown the line of the file they sent.

Two consequences worth stating:

* **A structural finding is evidenced, not asserted.** ``Redline.evidence`` is populated from this
  index, so nothing in R2 has to relax the schema's evidence rule to run without a datasheet.
* **The bbox is ``None``, and that is correct.** A CSV has no geometry. ADR-002 already makes the
  box a projection of the char span rather than the source of truth, so a text-only artifact
  simply has no projection -- it does not have a fabricated one.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from errata_spec import Evidence, sha256_bytes

__all__ = ["FEED_LAYER_VERSION", "FeedIndex", "index_feed"]

FEED_LAYER_VERSION = "errata-feed-index/1.0.0"


@dataclass(frozen=True, slots=True)
class FeedIndex:
    """Character spans into a delimited feed, by row number and column name.

    ``row_number`` is 1-based over data rows, matching :attr:`errata_audit.CatalogRecord.row_number`
    -- the header line is row 0 and is addressable as such, because a header that misnames a unit
    is a real defect and it needs somewhere to be cited from.
    """

    path: Path
    sha256: str
    text: str
    row_spans: dict[int, tuple[int, int]]
    cell_spans: dict[tuple[int, str], tuple[int, int]]
    columns: tuple[str, ...]

    @property
    def doc_id(self) -> str:
        return self.path.name

    def row_span(self, row_number: int | None) -> tuple[int, int]:
        if row_number is None:
            return (0, 0)
        return self.row_spans.get(row_number, (0, 0))

    def cell_span(self, row_number: int | None, column: str) -> tuple[int, int]:
        """The span of one cell, falling back to the whole row when the value is not locatable.

        Falling back rather than raising is deliberate: a quoted or escaped cell that cannot be
        located character-exactly still has a *row* a reviewer can open, and a coarser true span is
        worth more than a precise invented one.
        """
        if row_number is None:
            return (0, 0)
        span = self.cell_spans.get((row_number, column))
        return span if span is not None else self.row_span(row_number)

    def snippet(self, span: tuple[int, int]) -> str:
        start, end = span
        return self.text[start:end]

    def evidence(
        self,
        *,
        row_number: int | None,
        column: str,
        row_header: str = "",
    ) -> Evidence:
        """One cell of the feed, as evidence a redline can carry."""
        span = self.cell_span(row_number, column)
        return Evidence(
            doc_id=self.doc_id,
            doc_revision_sha256=self.sha256,
            page=1,
            char_span=span,
            bbox=None,
            snippet=self.snippet(span),
            extraction_layer_version=FEED_LAYER_VERSION,
            table_cell=f"row {row_number}, column {column}" if row_number else "",
            row_header=row_header,
            column_header=column,
        )


def index_feed(path: Path | str, *, delimiter: str | None = None) -> FeedIndex:
    """Read a delimited feed once and record where every cell physically is.

    The file is parsed twice on purpose: once by :mod:`csv` for correct field semantics, and once
    by a cursor walking the raw text to locate each parsed value inside its own line. Searching the
    raw line for the parsed value in column order is what makes quoted fields land on the right
    span -- the cursor never goes backwards, so a repeated value cannot be attributed to an earlier
    column.
    """
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    delimiter = delimiter or ("\t" if path.suffix.lower() == ".tsv" else ",")

    # Offsets must be computed against `text`, and `text` may differ from the bytes by a BOM. The
    # spans are into the decoded text layer, which is what ADR-002 makes the anchor.
    line_spans: list[tuple[int, int]] = []
    cursor = 0
    for line in text.splitlines(keepends=True):
        content = len(line.rstrip("\r\n"))
        line_spans.append((cursor, cursor + content))
        cursor += len(line)

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    columns: tuple[str, ...] = tuple(rows[0]) if rows else ()

    row_spans: dict[int, tuple[int, int]] = {}
    cell_spans: dict[tuple[int, str], tuple[int, int]] = {}

    # csv may consume more than one physical line for a quoted field. The index walks physical
    # lines and parsed rows together, which is exact for the feeds R2 ingests and degrades to a
    # row-level span rather than a wrong one when it is not.
    for index, values in enumerate(rows):
        if index >= len(line_spans):
            break
        start, end = line_spans[index]
        row_number = index  # header is 0; data rows are 1-based, as CatalogRecord records them
        row_spans[row_number] = (start, end)
        line = text[start:end]
        local = 0
        for column_index, value in enumerate(values):
            if column_index >= len(columns):
                break
            column = columns[column_index]
            if not value:
                continue
            found = line.find(value, local)
            if found < 0:
                continue
            cell_spans[(row_number, column)] = (start + found, start + found + len(value))
            local = found + len(value)

    return FeedIndex(
        path=path,
        sha256=sha256_bytes(raw),
        text=text,
        row_spans=row_spans,
        cell_spans=cell_spans,
        columns=columns,
    )


def columns_of(index: FeedIndex, names: Sequence[str]) -> tuple[str, ...]:
    """The subset of ``names`` the feed actually carries, in feed order."""
    wanted = {name.strip().lower() for name in names}
    return tuple(column for column in index.columns if column.strip().lower() in wanted)
