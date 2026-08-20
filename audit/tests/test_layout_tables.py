"""FR-1.4 / FR-1.5 / FR-1.6 -- the text layer, the table structure, and the column bands.

FR-1.4's acceptance criterion names three properties and the first one carries the product:
*deterministic for identical input bytes*. ``Evidence.char_span`` is an offset into this layer, so
a layer that shifts between runs silently invalidates every stored claim while every other test
still passes. It is tested here by extracting twice and comparing the offsets, not by trusting the
library.

FR-1.5's criterion -- "a value in a table cell can resolve its row and column headers" -- is tested
through the merged-cell case, because that is where the obvious implementation (carry the last
non-empty value forward) and the right one (read the cell's box) disagree, and where the wrong
answer is *plausible*: twenty products silently inheriting a neighbour's pole count.
"""

from __future__ import annotations

from pathlib import Path

from errata_audit.layout import LAYOUT_VERSION, extract_layer, layer_cache_key
from errata_audit.tables import CellRole, extract_tables

# ------------------------------------------------------------------------------------------------
# FR-1.4 -- the canonical layer
# ------------------------------------------------------------------------------------------------


def test_extraction_is_deterministic_for_identical_bytes(ordering_table_pdf: Path) -> None:
    first = extract_layer(ordering_table_pdf, use_cache=False)
    second = extract_layer(ordering_table_pdf, use_cache=False)
    assert first.text == second.text
    assert first.sha256 == second.sha256
    assert [w.span for w in first.words] == [w.span for w in second.words]


def test_the_layer_is_version_stamped(ordering_table_pdf: Path) -> None:
    assert extract_layer(ordering_table_pdf).layout_version == LAYOUT_VERSION


def test_the_cache_key_is_content_plus_version_never_the_path() -> None:
    """A supplier reposting a revised PDF under the same filename must not hit the cache -- that
    is the exact case the document register exists to catch."""
    key = layer_cache_key("a" * 64)
    assert key == f"{'a' * 64}@{LAYOUT_VERSION}"
    assert "ordering.pdf" not in key and ".pdf" not in key


def test_a_span_maps_back_to_the_words_it_covers(ordering_table_pdf: Path) -> None:
    layer = extract_layer(ordering_table_pdf)
    word = next(w for w in layer.words if w.text == "AX-16")
    assert [w.text for w in layer.words_in_span(*word.span)] == ["AX-16"]
    assert layer.text[word.start : word.end] == "AX-16"


def test_a_page_with_no_text_layer_says_so(scanned_pdf: Path) -> None:
    layer = extract_layer(scanned_pdf)
    assert not layer.is_born_digital
    assert layer.words == ()


def test_a_thin_but_readable_page_is_not_called_unreadable(two_column_pdf: Path) -> None:
    """A sparse page is readable and simply does not say much. Calling it unreadable would decline
    with ``layout_unreadable`` -- "the layout defeated us" -- when the honest reason is that the
    document does not state the value. ``is_sparse`` reports the thinness without deciding on it."""
    layer = extract_layer(two_column_pdf)
    assert layer.is_born_digital
    assert layer.is_sparse


def test_column_bands_tile_every_page(two_column_pdf: Path) -> None:
    """Every word must fall in exactly one band. A word in none would be unattributable, which is
    the failure FR-1.6 is about."""
    layer = extract_layer(two_column_pdf)
    for word in layer.words:
        bands = [b for b in layer.columns if b.page == word.page and b.contains(word)]
        assert len(bands) == 1, f"{word.text!r} landed in {len(bands)} bands"


def test_two_columns_are_detected_and_separate_the_products(two_column_pdf: Path) -> None:
    layer = extract_layer(two_column_pdf)
    left = layer.column_of(next(w for w in layer.words if w.text == "AX-10"))
    right = layer.column_of(next(w for w in layer.words if w.text == "AX-63"))
    assert left is not None and right is not None
    assert left.index != right.index

    # And the neighbouring product's rating is not in the first product's band.
    sixty_three = next(w for w in layer.words if w.text == "63")
    assert not left.contains(sixty_three)


def test_a_single_column_page_yields_one_band(ordering_table_pdf: Path) -> None:
    layer = extract_layer(ordering_table_pdf)
    assert len({b.index for b in layer.columns if b.page == 1}) == 1


# ------------------------------------------------------------------------------------------------
# FR-1.5 -- table structure
# ------------------------------------------------------------------------------------------------


def test_cells_carry_their_column_and_row_headers(ordering_table_pdf: Path) -> None:
    table = extract_tables(ordering_table_pdf)[0]
    cell = table.cell(2, "Rated current I n A")
    assert cell is not None
    assert cell.text == "16"
    assert cell.column_header == "Rated current I n A"
    assert cell.row_header == "AX-16"


def test_header_cells_have_the_header_role_and_a_box(ordering_table_pdf: Path) -> None:
    """FR-7.3 renders the header, so the header has to survive as an object with a rectangle."""
    table = extract_tables(ordering_table_pdf)[0]
    header = table.header_cell("Rated current I n A")
    assert header is not None
    assert header.role is CellRole.COLUMN_HEADER
    assert header.bbox[2] > header.bbox[0]


def test_a_merged_cell_is_resolved_by_geometry_for_every_row_it_spans(
    merged_cell_pdf: Path,
) -> None:
    table = extract_tables(merged_cell_pdf)[0]
    poles = [table.cell(row, "Number of poles") for row in table.rows if row > 0]
    assert [c.text for c in poles if c] == ["1", "1"]
    assert any(c.is_merged_source for c in poles if c)


def test_a_merged_cell_is_never_taken_as_a_row_identity(merged_cell_pdf: Path) -> None:
    """It states a value for a block of rows, so it cannot identify one of them. Taking it would
    label every product in the block ``1``."""
    table = extract_tables(merged_cell_pdf)[0]
    identities = {table.cell(row, "Type").row_header for row in table.rows if row > 0}
    assert identities == {"AX-10", "AX-16"}


def test_tables_are_cached_on_content(ordering_table_pdf: Path) -> None:
    first = extract_tables(ordering_table_pdf)
    second = extract_tables(ordering_table_pdf)
    assert first is second


def test_a_missing_column_returns_none_rather_than_a_guess(ordering_table_pdf: Path) -> None:
    table = extract_tables(ordering_table_pdf)[0]
    assert table.cell(1, "Breaking capacity kA") is None
