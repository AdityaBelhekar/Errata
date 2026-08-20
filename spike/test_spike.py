"""Tests for the grounding spike.

The spike is throwaway (see `spike/README.md`), but the corpus it produces carries R0 gate 2, so
the properties that make that corpus *mean* something are tested as carefully as production code.
Three of them matter:

1. **FR-3.4 — the predictor cannot see the answer.** Asserted on the function signature, not on
   behaviour, because behaviour can be correct today and wrong after one helpful refactor.
2. **Gold and prediction are produced by different mechanisms.** If that ever stops being true the
   grounding number becomes a tautology, and it would stop being true silently.
3. **Determinism.** The corpus must be reproducible, or a change in the gate's number cannot be
   attributed to a change in the code.

These run only when the ABB datasheets are present under `var/spike/datasheets/` -- they are
fetched by `scripts/fetch_reference_data.sh` and gitignored (FR-9.5), so a clean clone has the
URLs and hashes but not the payload. Where a test can assert something without the PDFs, it does,
so a clean clone still checks the parts that matter most.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from spike import predict as predict_module
from spike.attributes import ATTRIBUTES, BY_KEY
from spike.catalog import build_catalog
from spike.gold import build_gold
from spike.layout import extract_layer
from spike.predict import predict
from spike.tables import extract_tables, value_for_row

DATASHEETS = sorted(Path("var/spike/datasheets").glob("*.pdf"))
needs_pdfs = pytest.mark.skipif(not DATASHEETS, reason="datasheets not fetched")


# -- FR-3.4: no path exists through which the answer could reach the predictor ----------------


def test_predict_cannot_receive_a_catalog_or_gold_value() -> None:
    """The PRD calls FR-3.4 "the requirement most likely to be quietly broken during
    optimisation", because passing the catalog value in as a hint measurably improves grounding
    and makes every subsequent agreement meaningless.

    So it is asserted structurally. `predict` takes a text layer, a SKU and an attribute. If a
    parameter is ever added that could carry a value -- even optional, even defaulted, even
    called something innocuous -- this fails before anyone has to notice the score improved.
    """
    parameters = list(inspect.signature(predict).parameters)
    assert parameters == ["layer", "sku", "attribute"], (
        f"predict() signature changed to {parameters}. FR-3.4 requires that the re-derivation "
        "cannot see the catalog's value; a new parameter is how that stops being true."
    )


def test_the_predictor_module_never_imports_gold_or_catalog() -> None:
    """The second door into the same room. A signature stays clean while a module-level import
    quietly gives the predictor access to the answer key."""
    source = inspect.getsource(predict_module)
    for forbidden in ("from spike.gold", "from spike.catalog", "import spike.gold"):
        assert forbidden not in source, f"predict.py imports the answer: {forbidden}"


def test_gold_and_prediction_use_different_mechanisms() -> None:
    """The property the whole measurement rests on.

    Gold reads table structure; the predictor reads the flat layer. If the predictor ever gained
    table access the two would agree by construction, grounding F1 would approach 100%, and the
    number would say nothing about grounding at all -- while looking like an enormous improvement.
    """
    predictor = inspect.getsource(predict_module)
    assert "spike.tables" not in predictor
    assert "extract_tables" not in predictor
    assert "column_header" not in predictor

    from spike import gold as gold_module

    assert "spike.tables" in inspect.getsource(gold_module), "gold must be table-aware"


# -- layout (FR-1.4) ---------------------------------------------------------------------------


@needs_pdfs
def test_the_text_layer_is_deterministic_for_identical_bytes() -> None:
    """FR-1.4's actual acceptance criterion. `Evidence.char_span` is an offset into this layer,
    so a layer that shifts between runs invalidates every stored span while every other test
    still passes."""
    first, second = extract_layer(DATASHEETS[0]), extract_layer(DATASHEETS[0])
    assert first.sha256 == second.sha256
    assert [w.bbox for w in first.words] == [w.bbox for w in second.words]


@needs_pdfs
def test_the_layer_is_version_stamped() -> None:
    assert extract_layer(DATASHEETS[0]).layout_version.startswith("spike-layout/")


@needs_pdfs
def test_word_spans_index_back_into_the_canonical_text() -> None:
    """The map has to be a map. If a word's span does not select that word, a stored char_span
    resolves to the wrong words and the evidence box lands somewhere unrelated."""
    layer = extract_layer(DATASHEETS[0])
    for word in layer.words[:200]:
        assert layer.text[word.start : word.end] == word.text


@needs_pdfs
def test_born_digital_detection_agrees_with_reality() -> None:
    """Both ABB datasheets carry real text layers, which is why OCR is off the spike's critical
    path. If a future document does not, the pipeline must say so rather than silently produce
    an empty extraction."""
    assert extract_layer(DATASHEETS[0]).is_born_digital


# -- tables (FR-1.5) ---------------------------------------------------------------------------


@needs_pdfs
def test_a_cell_can_resolve_its_column_header() -> None:
    """FR-1.5 verbatim. FR-7.3's reason: `10` is not a fact; `10` under *Rated current In A* is."""
    tables = extract_tables(DATASHEETS[0])
    ordering = [t for t in tables if "Type" in t.column_headers and "Order code" in t.column_headers]
    assert ordering, "no ordering tables found -- the document layout changed"
    for cell in ordering[0].cells[:50]:
        assert cell.column_header or cell.column == 0


@needs_pdfs
def test_merged_cells_resolve_by_geometry_not_by_carrying_forward() -> None:
    """The ABB ordering tables state *Number of poles* once and leave the next twenty rows blank.

    Read naively, twenty SKUs have no pole count. This is the case that made the difference
    between 275 gold pole records and 7, and it is resolved by asking which merged cell's box
    contains the row -- observation -- rather than by carrying the last value forward, which
    would be a guess wearing a lookup's clothes.
    """
    ordering = [
        t
        for t in extract_tables(DATASHEETS[0])
        if "Number of poles" in t.column_headers and "Type" in t.column_headers
    ]
    assert ordering
    table = ordering[0]
    rows = sorted({c.row for c in table.cells})[1:9]
    resolved = [value_for_row(table, r, "Number of poles") for r in rows]
    assert all(c is not None for c in resolved), "merged pole cell did not resolve for every row"
    assert any(c.is_merged_source for c in resolved if c)


# -- the corpus --------------------------------------------------------------------------------


@needs_pdfs
def test_gold_is_read_from_the_document_and_carries_word_boxes() -> None:
    gold, _layer = build_gold(DATASHEETS[0])
    assert gold, "no gold records"
    for record in gold[:50]:
        assert record.boxes, "gold with no evidence boxes cannot be grounded against"
        assert record.page >= 1
        assert record.value == record.value.strip()
        # Gold evidence must be word boxes, not the cell rectangle -- the paper's §B.4 is explicit
        # that "a word-level box tightly encloses the cited word ... rather than the surrounding
        # table cell", and a cell-sized box would make IoU >= 0.5 trivial to satisfy.
        cell_area = (record.cell_bbox[2] - record.cell_bbox[0]) * (
            record.cell_bbox[3] - record.cell_bbox[1]
        )
        box_area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in record.boxes)
        assert box_area <= cell_area


@needs_pdfs
def test_the_predictor_gets_easy_attributes_right_and_hard_ones_wrong() -> None:
    """A sanity check on the difficulty spread, not on the score.

    If every attribute grounded perfectly the corpus would be measuring nothing; if none did, the
    extractor would be broken rather than limited. Order codes are distinctive and should land;
    the three mutually-ambiguous bare integers should not always.
    """
    gold, layer = build_gold(DATASHEETS[0])
    by_attribute: dict[str, list[bool]] = {}
    for record in gold:
        prediction = predict(layer, record.sku, BY_KEY[record.attribute])
        by_attribute.setdefault(record.attribute, []).append(
            prediction is not None and prediction.value == record.value
        )

    order = by_attribute["order_code"]
    assert sum(order) / len(order) > 0.95, "the distinctive pattern should be easy"

    ambiguous = by_attribute["packing_unit"]
    assert sum(ambiguous) / len(ambiguous) < 0.9, (
        "a table-blind extractor should NOT reliably tell packing unit from the bare integers "
        "in the adjacent columns -- if it does, it has gained table access"
    )


@needs_pdfs
def test_the_catalog_is_reproducible_and_contains_all_three_kinds() -> None:
    gold, _ = build_gold(DATASHEETS[0])
    first = build_catalog(gold)
    second = build_catalog(gold)
    assert {k: v.value for k, v in first.items()} == {k: v.value for k, v in second.items()}

    kinds = {entry.kind for entry in first.values()}
    assert kinds == {"correct", "defect", "equivalent_variant"}


@needs_pdfs
def test_equivalent_variants_are_not_counted_as_genuine_disagreements() -> None:
    """FR-5.3's trap, made explicit in the corpus.

    A catalog saying `6.0` where the datasheet says `6` is the same value in a different shape.
    Counting it as a genuine disagreement would reward the comparator for flagging it, and
    semantic equivalence not flagging is the single highest-consequence requirement in the PRD.
    """
    gold, _ = build_gold(DATASHEETS[0])
    catalog = build_catalog(gold)
    variants = [e for e in catalog.values() if e.kind == "equivalent_variant"]
    assert variants
    assert not any(e.is_genuine_disagreement for e in variants)


def test_every_attribute_has_a_pattern_and_a_stated_specificity() -> None:
    for attribute in ATTRIBUTES:
        assert attribute.pattern.pattern
        assert 0.0 < attribute.specificity <= 1.0
        assert attribute.column_header
