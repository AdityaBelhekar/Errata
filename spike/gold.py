"""The gold half: what the datasheet says, and exactly where it says it.

Gold is read from the **table structure** -- a cell under a named column, in a row identified by
its type designation, with the word boxes that cell contains. That is the labelling act, and it is
mechanised because the mechanisation is faithful: the value is the text printed in the cell, and
the evidence is the words that make up that text. Nothing is inferred.

Two decisions worth stating, because both could reasonably have gone the other way:

**The value is the cell text exactly as printed.** ``6``, not ``6 A``. The unit lives in the
column header (*Rated current I n A*), which is FR-7.3's whole point -- a number in an engineering
table means nothing without its headers, and the right response is to carry the header, not to
quietly fold it into the value. Folding it in would also mean gold contained a string that appears
nowhere in the document, which is a strange thing for evidence to do.

**Gold evidence is the WORD boxes, not the cell rectangle.** ExtractBench grounds at word level. A
cell box is several times the area of the value inside it, so scoring IoU against the cell would
let a predicted box land anywhere in the column and still clear 0.5. That would inflate the
grounding score for no reason other than that we chose the easier rectangle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from spike.attributes import ATTRIBUTES, TYPE_COLUMN, Attribute
from spike.layout import TextLayer, Word, extract_layer
from spike.tables import Table, extract_tables, value_for_row

GOLD_VERSION = "spike-gold/1.0.0"


@dataclass(frozen=True, slots=True)
class GoldRecord:
    """One attribute of one SKU, as the datasheet states it."""

    sku: str
    attribute: str
    value: str
    page: int
    boxes: tuple[tuple[float, float, float, float], ...]
    column_header: str
    cell_bbox: tuple[float, float, float, float]
    from_merged_cell: bool

    @property
    def attribute_id(self) -> str:
        return f"{self.sku}-{self.attribute}"


def _ordering_tables(tables: tuple[Table, ...]) -> tuple[Table, ...]:
    """The per-SKU tables: those carrying both a Type column and an Order code column.

    Selected by structure rather than by page number, so a re-issued datasheet with the tables
    moved does not silently produce an empty gold set.
    """
    return tuple(
        t
        for t in tables
        if TYPE_COLUMN in t.column_headers and "Order code" in t.column_headers
    )


def build_gold(pdf_path: Path | str) -> tuple[list[GoldRecord], TextLayer]:
    """Every (SKU, attribute) the ordering tables state, with word-level evidence."""
    path = Path(pdf_path)
    layer = extract_layer(path)
    records: list[GoldRecord] = []
    seen: set[str] = set()

    for table in _ordering_tables(extract_tables(path)):
        rows = sorted({c.row for c in table.cells})
        for row in rows:
            type_cell = value_for_row(table, row, TYPE_COLUMN)
            if type_cell is None or not type_cell.text.startswith("S2"):
                continue
            sku = type_cell.text
            if sku in seen:
                # A type designation repeated across tables would give one SKU two gold values.
                # Skip rather than overwrite: a duplicate is a document-structure finding, not
                # something to resolve silently by taking the last one seen.
                continue
            seen.add(sku)

            for attribute in ATTRIBUTES:
                record = _gold_for(table, row, attribute, sku, layer)
                if record is not None:
                    records.append(record)

    return records, layer


def _gold_for(
    table: Table, row: int, attribute: Attribute, sku: str, layer: TextLayer
) -> GoldRecord | None:
    cell = value_for_row(table, row, attribute.column_header)
    if cell is None:
        return None

    words: tuple[Word, ...] = layer.words_in_box(cell.page, cell.bbox)
    if not words:
        # A cell whose text the layer cannot locate is not usable as gold: there would be
        # nothing for a predicted box to overlap, and the record would score as ungroundable
        # for a reason that has nothing to do with the predictor.
        return None

    return GoldRecord(
        sku=sku,
        attribute=attribute.key,
        value=cell.text,
        page=cell.page,
        boxes=tuple(w.bbox for w in words),
        column_header=cell.column_header,
        cell_bbox=cell.bbox,
        from_merged_cell=cell.is_merged_source,
    )
