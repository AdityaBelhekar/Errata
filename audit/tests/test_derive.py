"""FR-3.1 - FR-3.4 -- blind, span-required, schema-constrained re-derivation.

**The first test in this file is the one that matters.** FR-3.4 says the extractor must not see the
catalog's value, and the PRD calls it the requirement most likely to be quietly broken during
optimisation, because passing the value in as a hint measurably improves grounding and makes every
subsequent agreement meaningless. It is guarded by inspecting the function's signature rather than
by reading the source, so a keyword argument added in six months fails the build rather than the
review.

The rest follow the same principle: each one is a shortcut that would make the numbers better and
the product worthless.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from conftest import etim_archive, requires_etim

from errata_audit.attributes import load_attributes
from errata_audit.classify import load_scope
from errata_audit.derive import derive
from errata_audit.etim import load_etim
from errata_audit.layout import extract_layer
from errata_audit.tables import extract_tables
from errata_spec import Abstention, Claim, DeclinedReason

ATTRIBUTES = load_attributes()
CURRENT = ATTRIBUTES.get("rated_current")
POLES = ATTRIBUTES.get("poles")
PACKAGING = ATTRIBUTES.get("packaging_uom")


# ------------------------------------------------------------------------------------------------
# FR-3.4 -- blind
# ------------------------------------------------------------------------------------------------


def test_no_parameter_can_carry_the_catalog_value() -> None:
    """The independence guarantee, enforced by the signature.

    Anything named like a catalog value, a hint, an expectation or a prior would be a channel
    through which the answer could reach the extractor. There is none, and if one is added this
    test fails before anybody has to notice it in a diff.
    """
    parameters = set(inspect.signature(derive).parameters)
    forbidden = {
        "catalog_value",
        "catalog",
        "expected",
        "expected_value",
        "hint",
        "prior",
        "current_value",
        "record",
        "context",
        "candidates",
    }
    assert not (parameters & forbidden), (
        f"derive() gained {sorted(parameters & forbidden)}. FR-3.4: the extractor must not see the "
        "catalog's value. Passing it in improves grounding and makes every agreement meaningless."
    )
    assert parameters == {
        "layer",
        "tables",
        "mpn",
        "attribute",
        "klass",
        "sku_id",
        "doc_id",
        "revision_sha256",
        "class_uri",
    }, (
        "the exact parameter list is pinned, not just the forbidden names: a channel for the "
        "catalog value could be opened under any name at all, and a diff that changes this "
        "signature deserves to be looked at."
    )


def test_knowing_which_product_is_audited_is_not_a_leak(ordering_table_pdf: Path) -> None:
    """The MPN comes from the catalog record's identity. An auditor that did not know which row to
    read would be solving a different problem; one that knew the answer would be solving none."""
    layer = extract_layer(ordering_table_pdf)
    tables = extract_tables(ordering_table_pdf)
    ten = derive(
        layer, tables, mpn="AX-10", attribute=CURRENT, klass=None, sku_id="AX-10",
        doc_id="d", revision_sha256="a" * 64,
    )
    sixteen = derive(
        layer, tables, mpn="AX-16", attribute=CURRENT, klass=None, sku_id="AX-16",
        doc_id="d", revision_sha256="a" * 64,
    )
    assert ten.value == "10 A"
    assert sixteen.value == "16 A"


# ------------------------------------------------------------------------------------------------
# FR-3.2 / FR-3.3 -- span required, or abstain
# ------------------------------------------------------------------------------------------------


def test_a_derived_value_carries_a_full_evidence_record(ordering_table_pdf: Path) -> None:
    layer = extract_layer(ordering_table_pdf)
    result = derive(
        layer,
        extract_tables(ordering_table_pdf),
        mpn="AX-16",
        attribute=CURRENT,
        klass=None,
        sku_id="AX-16",
        doc_id="acme-ds",
        revision_sha256="b" * 64,
    )
    assert isinstance(result.claim, Claim)
    evidence = result.claim.evidence[0]
    assert evidence.doc_id == "acme-ds"
    assert evidence.doc_revision_sha256 == "b" * 64
    assert evidence.page == 1
    assert evidence.char_span[1] > evidence.char_span[0]
    assert evidence.bbox is not None
    assert evidence.snippet
    assert evidence.extraction_layer_version


def test_the_box_lands_on_the_value_not_on_the_cell(ordering_table_pdf: Path) -> None:
    """ExtractBench grounds at word level, and Appendix B.4 p.23 says a word box tightly encloses
    the cited word rather than the surrounding cell. A cell rectangle is several times the area and
    would make IoU >= 0.5 trivial to satisfy."""
    layer = extract_layer(ordering_table_pdf)
    tables = extract_tables(ordering_table_pdf)
    cell = tables[0].cell(2, "Rated current I n A")
    result = derive(
        layer, tables, mpn="AX-16", attribute=CURRENT, klass=None, sku_id="AX-16",
        doc_id="d", revision_sha256="a" * 64,
    )
    box = result.claim.evidence[0].bbox
    cell_area = (cell.bbox[2] - cell.bbox[0]) * (cell.bbox[3] - cell.bbox[1])
    assert box.area < cell_area / 2


def test_the_column_header_is_carried_as_evidence_in_its_own_right(
    ordering_table_pdf: Path,
) -> None:
    """FR-7.3: a number in a table is never shown without the header that gives it meaning, so the
    header is stored as evidence rather than reconstructed by the console."""
    layer = extract_layer(ordering_table_pdf)
    result = derive(
        layer,
        extract_tables(ordering_table_pdf),
        mpn="AX-16",
        attribute=CURRENT,
        klass=None,
        sku_id="AX-16",
        doc_id="d",
        revision_sha256="a" * 64,
    )
    assert len(result.claim.evidence) == 2
    assert result.claim.evidence[1].column_header == "Rated current I n A"


def test_the_unit_comes_from_the_header_and_the_header_is_shown(
    ordering_table_pdf: Path,
) -> None:
    """The cell says ``16``. Sixteen what is printed in the column header, and composing the two is
    the mechanism FR-4.3 describes -- not an assumption about amperes."""
    layer = extract_layer(ordering_table_pdf)
    result = derive(
        layer, extract_tables(ordering_table_pdf), mpn="AX-16", attribute=CURRENT, klass=None,
        sku_id="AX-16", doc_id="d", revision_sha256="a" * 64,
    )
    assert result.value == "16 A"
    assert result.claim.evidence[0].table_cell == "16"


def test_a_product_not_in_the_document_abstains(ordering_table_pdf: Path) -> None:
    result = derive(
        extract_layer(ordering_table_pdf),
        extract_tables(ordering_table_pdf),
        mpn="AX-63",
        attribute=CURRENT,
        klass=None,
        sku_id="AX-63",
        doc_id="d",
        revision_sha256="a" * 64,
    )
    assert result.claim is None
    assert isinstance(result.abstention, Abstention)
    assert result.abstention.reason is DeclinedReason.NO_SOURCE_DOCUMENT


def test_a_scan_is_declined_not_guessed(scanned_pdf: Path) -> None:
    result = derive(
        extract_layer(scanned_pdf),
        (),
        mpn="AX-16",
        attribute=CURRENT,
        klass=None,
        sku_id="AX-16",
        doc_id="scan",
        revision_sha256="a" * 64,
    )
    assert result.abstention.reason is DeclinedReason.LAYOUT_UNREADABLE


def test_an_abstention_has_no_value_to_misread(scanned_pdf: Path) -> None:
    """FR-3.3: abstentions and claims are distinct types. The abstention has no ``value_raw``
    field, so downstream code cannot read a non-answer as an empty answer."""
    result = derive(
        extract_layer(scanned_pdf), (), mpn="AX-16", attribute=CURRENT, klass=None,
        sku_id="AX-16", doc_id="scan", revision_sha256="a" * 64,
    )
    assert not hasattr(result.abstention, "value_raw")
    assert result.value is None


# ------------------------------------------------------------------------------------------------
# The fallback path, and the accusation it must not make
# ------------------------------------------------------------------------------------------------


def test_the_fallback_reads_running_text_when_there_is_no_table(two_column_pdf: Path) -> None:
    result = derive(
        extract_layer(two_column_pdf),
        (),
        mpn="AX-10",
        attribute=CURRENT,
        klass=None,
        sku_id="AX-10",
        doc_id="d",
        revision_sha256="a" * 64,
    )
    assert result.value == "10"
    assert result.method == "text_window"
    # Weaker evidence, and the score says so rather than the pipeline pretending otherwise.
    assert result.raw_score < 0.6


def test_the_fallback_never_crosses_a_column_boundary(two_column_pdf: Path) -> None:
    """FR-1.6. ``63`` belongs to the product in the next column; reading it for AX-10 would be a
    confident, evidenced accusation about the wrong product."""
    result = derive(
        extract_layer(two_column_pdf), (), mpn="AX-10", attribute=CURRENT, klass=None,
        sku_id="AX-10", doc_id="d", revision_sha256="a" * 64,
    )
    assert result.value != "63"


def test_competing_values_in_the_window_decline_rather_than_pick(tmp_path: Path) -> None:
    """Found on the ABB S200 M UC datasheet, whose ordering tables do not resolve into columns: the
    running text reads "0.2 A 0.3 A 0.5 A ..." and an earlier version of this code happily returned
    0.3 for a 0.2 A device (finding N12). Nearest-in-reading-order is a tie-break, not evidence.
    """
    import pymupdf

    document = pymupdf.open()
    page = document.new_page(width=400, height=200)
    page.insert_text((40, 80), "AX-10 6 10 13 16 20 25", fontsize=10)
    path = tmp_path / "list.pdf"
    document.save(path)

    result = derive(
        extract_layer(path), (), mpn="AX-10", attribute=CURRENT, klass=None, sku_id="AX-10",
        doc_id="d", revision_sha256="a" * 64,
    )
    assert result.claim is None
    assert result.abstention.reason is DeclinedReason.LAYOUT_UNREADABLE
    assert "competing values" in result.abstention.detail


# ------------------------------------------------------------------------------------------------
# FR-3.1 -- constrained to the class's schema
# ------------------------------------------------------------------------------------------------


@requires_etim
def test_a_value_outside_the_classs_declared_list_never_becomes_a_claim(tmp_path: Path) -> None:
    """ETIM declares a closed value list for the release characteristic. A cell reading ``Q`` is
    not a characteristic; rejecting it here means it cannot reach the comparator, the queue or a
    reviewer's screen."""
    import pymupdf

    model = load_etim(etim_archive(), release="10.0", class_ids=load_scope().as_set)
    mcb = model.get("EC000042")

    trip = type(CURRENT)(
        key="tripping_characteristic",
        label="Release characteristic",
        etim_feature="EF000889",
        classes=("EC000042",),
        kinds=(),
        column_headers=(__import__("re").compile("(?i)characteristic"),),
        value_pattern=__import__("re").compile(r"^[A-Z]$"),
        specificity=0.5,
    )

    document = pymupdf.open()
    page = document.new_page(width=400, height=200)
    cols, rows = [30, 160, 320], [40, 72, 104]
    for x in cols:
        page.draw_line((x, rows[0]), (x, rows[-1]))
    for y in rows:
        page.draw_line((cols[0], y), (cols[-1], y))
    page.insert_text((cols[0] + 4, rows[0] + 18), "Type", fontsize=8)
    page.insert_text((cols[1] + 4, rows[0] + 18), "Characteristic", fontsize=8)
    page.insert_text((cols[0] + 4, rows[1] + 18), "AX-10", fontsize=8)
    page.insert_text((cols[1] + 4, rows[1] + 18), "Q", fontsize=8)
    path = tmp_path / "bad-value.pdf"
    document.save(path)

    result = derive(
        extract_layer(path),
        extract_tables(path),
        mpn="AX-10",
        attribute=trip,
        klass=mcb,
        sku_id="AX-10",
        doc_id="d",
        revision_sha256="a" * 64,
    )
    assert result.claim is None
    assert result.abstention.reason is DeclinedReason.VALUE_OUTSIDE_KNOWN_GRAMMAR
    assert "value list ETIM declares" in result.abstention.detail


@requires_etim
def test_a_permitted_value_passes_the_same_check(tmp_path: Path) -> None:
    """The negative control. A constraint that rejects everything is not a constraint, it is an
    outage."""
    import re as _re

    import pymupdf

    model = load_etim(etim_archive(), release="10.0", class_ids=load_scope().as_set)
    trip = type(CURRENT)(
        key="tripping_characteristic",
        label="Release characteristic",
        etim_feature="EF000889",
        classes=("EC000042",),
        kinds=(),
        column_headers=(_re.compile("(?i)characteristic"),),
        value_pattern=_re.compile(r"^[A-Z]$"),
        specificity=0.5,
    )
    document = pymupdf.open()
    page = document.new_page(width=400, height=200)
    cols, rows = [30, 160, 320], [40, 72, 104]
    for x in cols:
        page.draw_line((x, rows[0]), (x, rows[-1]))
    for y in rows:
        page.draw_line((cols[0], y), (cols[-1], y))
    page.insert_text((cols[0] + 4, rows[0] + 18), "Type", fontsize=8)
    page.insert_text((cols[1] + 4, rows[0] + 18), "Characteristic", fontsize=8)
    page.insert_text((cols[0] + 4, rows[1] + 18), "AX-10", fontsize=8)
    page.insert_text((cols[1] + 4, rows[1] + 18), "C", fontsize=8)
    path = tmp_path / "good-value.pdf"
    document.save(path)

    result = derive(
        extract_layer(path), extract_tables(path), mpn="AX-10", attribute=trip,
        klass=model.get("EC000042"), sku_id="AX-10", doc_id="d", revision_sha256="a" * 64,
    )
    assert result.value == "C"


def test_a_numeric_feature_is_not_constrained_by_an_invented_range(
    ordering_table_pdf: Path,
) -> None:
    """ETIM's numeric features carry a unit and no enumeration. Making one up -- "a breaker is
    between 0.5 and 125 A" -- would be the audit asserting a constraint the standard does not."""
    result = derive(
        extract_layer(ordering_table_pdf), extract_tables(ordering_table_pdf), mpn="AX-16",
        attribute=CURRENT, klass=None, sku_id="AX-16", doc_id="d", revision_sha256="a" * 64,
    )
    assert result.value == "16 A"


# ------------------------------------------------------------------------------------------------
# Merged cells
# ------------------------------------------------------------------------------------------------


def test_a_merged_pole_cell_is_read_for_every_row_it_spans(merged_cell_pdf: Path) -> None:
    layer = extract_layer(merged_cell_pdf)
    tables = extract_tables(merged_cell_pdf)
    values = [
        derive(
            layer, tables, mpn=mpn, attribute=POLES, klass=None, sku_id=mpn, doc_id="d",
            revision_sha256="a" * 64,
        ).value
        for mpn in ("AX-10", "AX-16")
    ]
    assert values == ["1", "1"]


def test_the_fingerprint_records_how_the_value_was_found(ordering_table_pdf: Path) -> None:
    """NFR-2: a claim that cannot say how it was produced cannot be reproduced."""
    result = derive(
        extract_layer(ordering_table_pdf), extract_tables(ordering_table_pdf), mpn="AX-16",
        attribute=CURRENT, klass=None, sku_id="AX-16", doc_id="d", revision_sha256="a" * 64,
    )
    fingerprint = result.claim.extractor
    assert fingerprint.name == "errata-audit.derive"
    assert fingerprint.method == "table_cell"
    assert fingerprint.model_id == "", (
        "no model produced this claim, and NFR-2 keys the reconstructibility check on model_id"
    )
    assert fingerprint.grammar_version


def test_the_raw_score_is_never_presented_as_a_probability(ordering_table_pdf: Path) -> None:
    result = derive(
        extract_layer(ordering_table_pdf), extract_tables(ordering_table_pdf), mpn="AX-16",
        attribute=CURRENT, klass=None, sku_id="AX-16", doc_id="d", revision_sha256="a" * 64,
    )
    assert result.claim.confidence.calibrated_p is None
    assert result.claim.confidence.method == "none"
    assert 0.0 <= result.claim.confidence.raw_score <= 1.0


def test_deriving_twice_gives_the_same_answer(ordering_table_pdf: Path) -> None:
    layer = extract_layer(ordering_table_pdf)
    tables = extract_tables(ordering_table_pdf)
    kwargs = dict(
        mpn="AX-16", attribute=CURRENT, klass=None, sku_id="AX-16", doc_id="d",
        revision_sha256="a" * 64,
    )
    first = derive(layer, tables, **kwargs)
    second = derive(layer, tables, **kwargs)
    assert first.value == second.value
    assert first.claim.evidence == second.claim.evidence
