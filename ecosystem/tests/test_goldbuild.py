"""The benchmark's annotation engine -- the properties that make the gold set mean something.

These were ``spike/test_spike.py``. The spike is gone: :mod:`errata_ecosystem.corpusbuild` rebuilds
the gate-2 corpus from production code, byte for byte, so the one reason the directory was frozen
rather than deleted no longer holds. What was left in it was never scaffolding -- it is the code
that writes the gold set, and a benchmark needs one of those permanently. It now lives in
:mod:`errata_ecosystem.goldbuild` and these are its tests.

Three properties matter and each is load-bearing for a published number:

1. **Gold and prediction are produced by different mechanisms.** Gold reads table structure; the
   systems being scored do not have to. If that ever stops being true the grounding number becomes
   a tautology, and it would stop being true silently while looking like an enormous improvement.
2. **Determinism.** ``data/gold/manifest.json`` carries a hash of every annotation file. A layout
   that shifts between runs invalidates the published gold set while every other test passes.
3. **The version strings are the ones in the published manifest.** ``spike-layout/1.0.0`` and
   ``spike-gold/1.0.0`` look wrong in a package no longer called spike, and renaming them would
   silently invalidate a hashed artifact to make a module look tidy. A version identifies the
   algorithm that produced a hash, not the directory it sat in.

The FR-3.4 blindness tests that used to live here moved with the code they guarded: the spike's
predictor is now ``errata_ecosystem.extractors.TableBlindExtractor``, and
``test_corpus_and_extractors.py`` asserts its blindness on a live object rather than on a source
string.

These run only when the ABB datasheets are present under ``var/spike/datasheets/`` -- fetched by
``scripts/fetch_reference_data.sh`` and gitignored (FR-9.5). Where a test can assert something
without the PDFs it does, so a clean clone still checks the parts that matter most.
"""


from __future__ import annotations

from pathlib import Path

import pytest

from errata_ecosystem.corpusbuild import _build_catalog as build_catalog
from errata_ecosystem.goldbuild import (
    ATTRIBUTES,
    build_gold,
    extract_layer,
    extract_tables,
    value_for_row,
)

DATASHEET_DIR = Path(__file__).resolve().parents[2] / "var" / "spike" / "datasheets"
DATASHEETS = sorted(DATASHEET_DIR.glob("*.pdf"))
needs_pdfs = pytest.mark.skipif(not DATASHEETS, reason="datasheets not fetched")


# -- FR-3.4: no path exists through which the answer could reach the predictor ----------------


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


# The spike's `test_the_predictor_gets_easy_attributes_right_and_hard_ones_wrong` lived here. It
# asserted that a table-blind extractor grounds `order_code` easily and confuses the three bare
# small integers in adjacent columns. That claim is now measured rather than asserted:
# `errata-r3 corpus score --extractor tableblind` reports it per attribute over all 1,426 records,
# and `test_corpus_and_extractors.py` pins the headline. A spot-check on two SKUs was the right
# test when there was no corpus; keeping it beside the corpus would be a worse version of it.
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
