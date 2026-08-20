"""T0 -- the document-free tier (FR-8.7's first stage).

The tests are grouped by the thing that would end a pilot if it broke:

1. **Equivalence must never flag, at any tier.** FR-5.3 is the single highest-consequence
   requirement in the PRD, and T0 is a new place for it to break because it compares a feed against
   itself with no document to appeal to. ``125 g`` against ``0.125 kg`` and ``1P`` against ``1``
   are the two traps the R1 corpus already carries; they are re-run here.
2. **A minority is not wrong for being a minority.** With no majority the policy abstains and
   surfaces every value, rather than letting whichever row was exported first become the truth.
3. **Every finding cites a span in a real artifact.** The feed is hash-registered and the span
   resolves back to the bytes -- so a customer disputing a finding can be shown the line of the
   file they sent.
4. **The order of the rows does not change the answer.** A finding that moves when a customer
   re-sorts their spreadsheet is not reproducible (NFR-1).
"""

from __future__ import annotations

from scalefixtures import catalog_of, row  # noqa: F401

from errata_audit import Outcome, load_catalog
from errata_scale import index_feed, run_structural
from errata_scale.structural import StructuralCheck
from errata_spec import DeclinedReason, DisagreementClass, Severity


def _run(catalog):
    records = load_catalog(catalog)
    return records, run_structural(records, index_feed(catalog))


# ------------------------------------------------------------------------------------------------
# 1. equivalence never flags
# ------------------------------------------------------------------------------------------------


def test_the_same_weight_in_grams_and_kilograms_is_not_a_finding(catalog_of):
    catalog = catalog_of(
        [
            row("A-1", mpn="MPN-1", weight_kg="0.125 kg"),
            row("A-2", mpn="MPN-1", weight_kg="125 g"),
        ]
    )
    _records, result = _run(catalog)
    assert [o.attribute.key for o in result.findings] == []
    weights = [o for o in result.outcomes if o.attribute.key == "weight_kg"]
    assert all(o.outcome == Outcome.RESOLVED for o in weights)


def test_one_pole_written_two_ways_is_not_a_finding(catalog_of):
    catalog = catalog_of(
        [row("B-1", mpn="MPN-2", poles="1"), row("B-2", mpn="MPN-2", poles="1P")]
    )
    _records, result = _run(catalog)
    assert result.findings == ()


def test_an_equivalence_trap_is_not_declined_as_an_equal_rank_conflict(catalog_of):
    """The subtle failure: a 1-1 split *is* a tie, but there is nothing to arbitrate when the two
    rows say the same thing. Declining here would put a non-disagreement in the Declined bucket and
    quietly cost coverage."""
    catalog = catalog_of(
        [
            row("C-1", mpn="MPN-3", weight_kg="0.125 kg"),
            row("C-2", mpn="MPN-3", weight_kg="125 g"),
        ]
    )
    _records, result = _run(catalog)
    assert result.declined == ()


# ------------------------------------------------------------------------------------------------
# 2. contradictions, gaps, and the equal-rank abstention
# ------------------------------------------------------------------------------------------------


def test_a_minority_row_contradicting_its_siblings_is_a_finding(catalog_of):
    catalog = catalog_of(
        [
            row("D-1", mpn="MPN-4", rated_current="16 A"),
            row("D-2", mpn="MPN-4", rated_current="16 A"),
            row("D-3", mpn="MPN-4", rated_current="61 A"),
        ]
    )
    _records, result = _run(catalog)
    findings = [o for o in result.findings if o.attribute.key == "rated_current"]
    assert len(findings) == 1
    finding = findings[0]
    assert finding.sku_id == "D-3"
    assert finding.proposed_value == "16 A"
    assert finding.check is StructuralCheck.SIBLING_CONTRADICTION
    assert finding.redline is not None
    assert finding.redline.disagreement_class is DisagreementClass.CONTRADICTION
    assert finding.redline.severity is Severity.SEV1
    assert finding.redline.requires_two_signatures  # rated_current is safety class (FR-8.9)


def test_a_blank_cell_beside_stated_siblings_is_a_fill_rate_finding(catalog_of):
    catalog = catalog_of(
        [
            row("E-1", mpn="MPN-5", packaging_uom="10 pcs"),
            row("E-2", mpn="MPN-5", packaging_uom="10 pcs"),
            row("E-3", mpn="MPN-5", packaging_uom=""),
        ]
    )
    _records, result = _run(catalog)
    gaps = [o for o in result.findings if o.check is StructuralCheck.SIBLING_FILL_GAP]
    assert [o.sku_id for o in gaps] == ["E-3"]
    assert gaps[0].redline is not None
    assert (
        gaps[0].redline.disagreement_class is DisagreementClass.CATALOG_NULL_EVIDENCE_PRESENT
    )
    assert gaps[0].proposed_value == "10 pcs"


def test_a_tie_abstains_and_surfaces_every_value(catalog_of):
    catalog = catalog_of(
        [
            row("F-1", mpn="MPN-6", weight_kg="0.125 kg"),
            row("F-2", mpn="MPN-6", weight_kg="0.250 kg"),
        ]
    )
    _records, result = _run(catalog)
    declined = [o for o in result.declined if o.attribute.key == "weight_kg"]
    assert {o.sku_id for o in declined} == {"F-1", "F-2"}
    assert all(o.declined_reason is DeclinedReason.EQUAL_RANK_SOURCE_CONFLICT for o in declined)
    assert not [o for o in result.findings if o.attribute.key == "weight_kg"]


def test_a_current_stated_as_a_mass_is_wrong_without_any_document(catalog_of):
    catalog = catalog_of([row("G-1", rated_current="0.125 kg")])
    _records, result = _run(catalog)
    findings = [o for o in result.findings if o.check is StructuralCheck.UNIT_DIMENSION]
    assert [o.sku_id for o in findings] == ["G-1"]
    assert findings[0].redline is not None
    assert findings[0].redline.disagreement_class is DisagreementClass.UNSUPPORTED_VALUE
    assert findings[0].redline.proposed_value == ""


def test_a_correct_current_is_not_a_dimension_finding(catalog_of):
    catalog = catalog_of([row("G-2", rated_current="16 A")])
    _records, result = _run(catalog)
    assert not [o for o in result.findings if o.check is StructuralCheck.UNIT_DIMENSION]


def test_records_with_no_sibling_produce_no_sibling_outcomes(catalog_of):
    catalog = catalog_of([row("H-1"), row("H-2")])
    _records, result = _run(catalog)
    assert result.findings == ()
    assert result.declined == ()


def test_two_manufacturers_sharing_a_part_number_are_not_compared(catalog_of):
    """Different makers may use the same number. A cross-manufacturer contradiction would be
    invented."""
    catalog = catalog_of(
        [
            row("I-1", mpn="SHARED", manufacturer="SYN-MFR-01", rated_current="16 A"),
            row("I-2", mpn="SHARED", manufacturer="SYN-MFR-02", rated_current="61 A"),
        ]
    )
    _records, result = _run(catalog)
    assert result.findings == ()


# ------------------------------------------------------------------------------------------------
# 3. evidence
# ------------------------------------------------------------------------------------------------


def test_every_structural_finding_cites_a_span_that_resolves_in_the_feed(catalog_of):
    catalog = catalog_of(
        [
            row("J-1", mpn="MPN-7", rated_current="16 A"),
            row("J-2", mpn="MPN-7", rated_current="16 A"),
            row("J-3", mpn="MPN-7", rated_current="61 A"),
        ]
    )
    records = load_catalog(catalog)
    index = index_feed(catalog)
    result = run_structural(records, index)

    assert result.findings
    for outcome in result.findings:
        assert outcome.redline is not None
        assert outcome.redline.evidence, "a finding with no evidence is an assertion"
        for evidence in outcome.redline.evidence:
            assert evidence.doc_revision_sha256 == index.sha256
            start, end = evidence.char_span
            assert end > start
            # the span is not decoration: it resolves back to the bytes of the file
            assert index.text[start:end] == evidence.snippet
            assert evidence.snippet == "16 A"
            assert evidence.bbox is None  # a CSV has no geometry, and none is invented


def test_the_feed_index_addresses_cells_by_row_and_column(catalog_of):
    catalog = catalog_of([row("K-1", rated_current="16 A"), row("K-2", rated_current="25 A")])
    index = index_feed(catalog)
    assert index.snippet(index.cell_span(1, "rated_current")) == "16 A"
    assert index.snippet(index.cell_span(2, "rated_current")) == "25 A"
    assert index.snippet(index.cell_span(1, "sku")) == "K-1"
    assert index.columns[0] == "sku"


# ------------------------------------------------------------------------------------------------
# 4. reproducibility
# ------------------------------------------------------------------------------------------------


def test_the_answer_does_not_depend_on_the_order_of_the_rows(catalog_of):
    rows = [
        row("L-1", mpn="MPN-8", rated_current="16 A"),
        row("L-2", mpn="MPN-8", rated_current="16 A"),
        row("L-3", mpn="MPN-8", rated_current="61 A"),
    ]
    forward = catalog_of(rows, "forward.csv")
    backward = catalog_of(list(reversed(rows)), "backward.csv")

    _r1, first = _run(forward)
    _r2, second = _run(backward)

    assert {(o.sku_id, o.proposed_value) for o in first.findings} == {
        (o.sku_id, o.proposed_value) for o in second.findings
    }


def test_redline_ids_are_stable_across_runs(catalog_of):
    catalog = catalog_of(
        [
            row("M-1", mpn="MPN-9", rated_current="16 A"),
            row("M-2", mpn="MPN-9", rated_current="16 A"),
            row("M-3", mpn="MPN-9", rated_current="61 A"),
        ]
    )
    _r1, first = _run(catalog)
    _r2, second = _run(catalog)
    assert [str(o.redline.redline_id) for o in first.findings] == [
        str(o.redline.redline_id) for o in second.findings
    ]


def test_no_outcome_is_ever_silent(catalog_of):
    """FR-6.2: no silent skips. Every stated cell of a record with siblings gets an outcome."""
    catalog = catalog_of(
        [row("N-1", mpn="MPN-10"), row("N-2", mpn="MPN-10", rated_current="61 A")]
    )
    records, result = _run(catalog)
    audited = {o.attribute.key for o in result.outcomes}
    for record in records:
        for key in audited:
            value = record.value(key)
            if value is None or not value.strip():
                continue
            assert any(
                o.sku_id == record.sku_id and o.attribute.key == key for o in result.outcomes
            ), f"{record.sku_id}/{key} vanished from the run"
