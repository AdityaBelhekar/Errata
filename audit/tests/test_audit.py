"""The R1 audit end to end -- and, more importantly, the things it must never do.

Ground rule 7 says every comparator fix carries negative controls, and the same discipline applies
to the pipeline that wraps it. Half the tests here assert that nothing was raised:

* a weight stated in grams against a weight stated in kilograms -- one fact, two frames;
* a pole count written ``1P`` against a document that prints ``1``;
* ``Each`` against a document packing unit of ``1``.

Each of those would be a false accusation, and FR-5.3 calls semantic equivalence "the single
highest-consequence requirement" in the PRD. The other half assert that the real defects *are*
raised, because a system that raises nothing passes every negative control ever written.

The last group is about coverage: every attribute produces an outcome, every decline carries
exactly one reason, and nothing is skipped silently (FR-6.2).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import etim_archive, requires_etim

from errata_audit.attributes import load_attributes
from errata_audit.audit import Outcome, audit_sku
from errata_audit.classify import load_scope
from errata_audit.etim import load_etim
from errata_audit.ingest import record_from_mapping
from errata_spec import DeclinedReason, DisagreementClass, Severity

pytestmark = requires_etim

ATTRIBUTES = load_attributes()


@pytest.fixture(scope="module")
def etim():
    return load_etim(etim_archive(), release="10.0", class_ids=load_scope().as_set)


#: What the document actually states for AX-16. Tests override one field at a time, so each one
#: names the single thing under test and everything else is a control.
CORRECT = {
    "rated_current": "16 A",
    "poles": "1",
    "packaging_uom": "5 pcs",
    "weight_kg": "0.125 kg",
}


@pytest.fixture
def audit(etim, ordering_table_pdf: Path, source_of):
    document = source_of(ordering_table_pdf, doc_id="acme-ordering")
    scope = load_scope()

    def _run(_defaults: bool = True, **values):
        record = record_from_mapping(
            {
                "sku": "AX-16",
                "mpn": "AX-16",
                "manufacturer": "ACME",
                "description": "miniature circuit breaker",
                **(CORRECT if _defaults else {}),
                **values,
            }
        )
        return audit_sku(record, document, etim=etim, scope=scope, attributes=ATTRIBUTES)

    return _run


def test_a_description_alone_cannot_separate_an_mcb_from_an_mcb_plug_model(audit) -> None:
    """Worth stating as a property rather than discovering it as a flaky test.

    "miniature circuit breaker" is the whole of EC000042's name and most of EC000271's, so no
    lexical method can separate them -- and this resolver ships without the embedding and
    cross-encoder halves of FR-2.2. What separates them is the record: EC000271 declares no pole
    feature, so a feed that sends a pole count is describing an EC000042. A record with neither is
    declined, which is the conservative direction and the reason coverage is reported next to
    every rate.
    """
    assert audit(_defaults=False, rated_current="16 A").class_uri == ""
    assert audit().class_uri == "etim:EC000042 @ 10.0"


# ------------------------------------------------------------------------------------------------
# It finds the defect
# ------------------------------------------------------------------------------------------------


def test_a_contradicted_value_is_raised_with_its_evidence(audit) -> None:
    result = audit(rated_current="61 A")
    finding = result.findings[0]
    assert finding.comparison.disagreement_class is DisagreementClass.CONTRADICTION
    assert finding.redline.severity is Severity.SEV1
    assert finding.redline.evidence[0].bbox is not None
    assert finding.redline.evidence[0].page == 1


def test_a_blank_catalog_field_is_a_fill_rate_finding_not_a_contradiction(audit) -> None:
    result = audit(rated_current="")
    finding = result.findings[0]
    assert finding.comparison.disagreement_class is DisagreementClass.CATALOG_NULL_EVIDENCE_PRESENT
    assert finding.redline.severity is Severity.SEV2


def test_a_packaging_frame_error_is_always_sev1(audit) -> None:
    result = audit(packaging_uom="Each")
    finding = next(o for o in result.findings if o.attribute.key == "packaging_uom")
    assert finding.comparison.disagreement_class is DisagreementClass.PACKAGING_FRAME_ERROR
    assert finding.redline.severity is Severity.SEV1


def test_a_safety_class_finding_demands_two_signatures(audit) -> None:
    finding = audit(rated_current="61 A").findings[0]
    assert finding.redline.requires_two_signatures
    assert "second named adjudicator" in finding.redline.rationale


# ------------------------------------------------------------------------------------------------
# ...and it does not invent one. Ground rule 7: the negative controls.
# ------------------------------------------------------------------------------------------------


def test_the_same_weight_in_grams_is_not_a_finding(audit) -> None:
    """0.125 kg against 125 g. Flagging this is the false positive that ends a pilot in week one."""
    result = audit(weight_kg="125 g")
    outcome = next(o for o in result.outcomes if o.attribute.key == "weight_kg")
    assert outcome.outcome == Outcome.RESOLVED
    assert outcome.comparison.disagreement_class is DisagreementClass.UNIT_FRAME_MISMATCH


def test_a_pole_count_in_trade_notation_is_not_a_finding(audit) -> None:
    """The document prints ``5`` in the packing column and ``1``-style pole counts; a catalog
    writing ``1P`` is saying the same thing in the vocabulary its buyers use."""
    result = audit(poles="1P")
    outcome = next(o for o in result.outcomes if o.attribute.key == "poles")
    assert outcome.outcome == Outcome.RESOLVED


def test_each_against_a_packing_unit_of_one_is_not_a_finding(etim, source_of, tmp_path) -> None:
    """The trap that the demonstration catalog's first generation got wrong: "Each" is a defect
    against a pack of 10 and *correct* against a pack of 1."""
    import pymupdf

    document = pymupdf.open()
    page = document.new_page(width=460, height=300)
    cols, rows = [30, 160, 320, 440], [40, 72, 104]
    for x in cols:
        page.draw_line((x, rows[0]), (x, rows[-1]))
    for y in rows:
        page.draw_line((cols[0], y), (cols[-1], y))
    page.insert_text((cols[0] + 4, rows[0] + 18), "Type", fontsize=8)
    page.insert_text((cols[1] + 4, rows[0] + 18), "Packing unit PCS", fontsize=8)
    page.insert_text((cols[2] + 4, rows[0] + 18), "Rated current I n A", fontsize=8)
    page.insert_text((cols[0] + 4, rows[1] + 18), "AX-16", fontsize=8)
    page.insert_text((cols[1] + 4, rows[1] + 18), "1", fontsize=8)
    page.insert_text((cols[2] + 4, rows[1] + 18), "16", fontsize=8)
    path = tmp_path / "single-pack.pdf"
    document.save(path)

    record = record_from_mapping(
        {"sku": "AX-16", "mpn": "AX-16", "description": "miniature circuit breaker",
         "packaging_uom": "Each", "rated_current": "16 A", "poles": "1"}
    )
    result = audit_sku(
        record, source_of(path, doc_id="single"), etim=etim, scope=load_scope(),
        attributes=ATTRIBUTES,
    )
    packaging = next(o for o in result.outcomes if o.attribute.key == "packaging_uom")
    assert packaging.outcome == Outcome.RESOLVED


def test_a_matching_value_produces_no_finding_at_all(audit) -> None:
    result = audit(rated_current="16 A", poles="1", weight_kg="0.125 kg", packaging_uom="5 pcs")
    assert result.findings == ()
    assert len(result.resolved) == 4


def test_the_audit_never_writes_to_the_catalog_record(audit) -> None:
    """ADR-001: Errata proposes, and does not write. The record it was handed is unchanged."""
    result = audit(rated_current="61 A")
    assert result.record.value("rated_current") == "61 A"


# ------------------------------------------------------------------------------------------------
# Coverage, declines, and no silent skips (FR-6.2)
# ------------------------------------------------------------------------------------------------


def test_every_attribute_produces_an_outcome(audit) -> None:
    result = audit(rated_current="61 A")
    keys = {o.attribute.key for o in result.outcomes}
    assert keys == {a.key for a in ATTRIBUTES.for_class("EC000042")}


def test_every_decline_has_exactly_one_reason(audit) -> None:
    result = audit(rated_current="61 A", order_code="2CDS271061R0165")
    assert result.declined
    for outcome in result.declined:
        assert outcome.declined_reason is not None
        assert outcome.detail.strip()


def test_a_column_the_document_does_not_state_declines_with_no_span(audit) -> None:
    """The catalog carries an order code and this document has no such column. The reason is
    ``no_span_available`` -- "we could not ground it" -- and not the grammar refusal below, because
    the two are different failures and a reason that misdescribes what happened is worse than none.
    """
    order_code = next(
        o for o in audit(order_code="2CDS271061R0165").outcomes if o.attribute.key == "order_code"
    )
    assert order_code.outcome == Outcome.DECLINED
    assert order_code.declined_reason is DeclinedReason.NO_SPAN


def test_an_unparseable_value_is_declined_and_visible_not_dropped(
    etim, source_of, tmp_path
) -> None:
    """FR-6.2: no silent skips. An audit that quietly dropped the columns it could not parse would
    report a coverage it had not earned -- so an attribute with no grammar is still looked at, and
    its refusal appears in the Declined bucket where a reviewer can see it was considered."""
    import pymupdf

    document = pymupdf.open()
    page = document.new_page(width=460, height=300)
    cols, rows = [30, 160, 330, 450], [40, 72, 104]
    for x in cols:
        page.draw_line((x, rows[0]), (x, rows[-1]))
    for y in rows:
        page.draw_line((cols[0], y), (cols[-1], y))
    page.insert_text((cols[0] + 4, rows[0] + 18), "Type", fontsize=8)
    page.insert_text((cols[1] + 4, rows[0] + 18), "Order code", fontsize=8)
    page.insert_text((cols[2] + 4, rows[0] + 18), "Rated current I n A", fontsize=8)
    page.insert_text((cols[0] + 4, rows[1] + 18), "AX-16", fontsize=8)
    page.insert_text((cols[1] + 4, rows[1] + 18), "2CDS271061R0165", fontsize=8)
    page.insert_text((cols[2] + 4, rows[1] + 18), "16", fontsize=8)
    path = tmp_path / "with-order-code.pdf"
    document.save(path)

    record = record_from_mapping(
        {
            "sku": "AX-16",
            "mpn": "AX-16",
            "description": "miniature circuit breaker",
            "order_code": "2CDS271061R0165",
            "rated_current": "16 A",
            "poles": "1",
        }
    )
    result = audit_sku(
        record, source_of(path, doc_id="oc"), etim=etim, scope=load_scope(), attributes=ATTRIBUTES
    )
    order_code = next(o for o in result.outcomes if o.attribute.key == "order_code")
    assert order_code.outcome == Outcome.DECLINED
    assert order_code.declined_reason is DeclinedReason.VALUE_OUTSIDE_KNOWN_GRAMMAR
    # And it was genuinely read from the document first -- the decline is about the value layer,
    # not about a column nobody looked for.
    assert order_code.derived_value == "2CDS271061R0165"


def test_an_attribute_the_feed_does_not_carry_is_not_a_finding(
    etim, ordering_table_pdf, source_of
) -> None:
    """A missing column is a schema gap; a blank cell is a data defect. Collapsing them would let
    the audit manufacture SEV-2s out of a customer's decision not to send a field.

    The description resolves lexically here, so the record needs no attribute columns at all --
    which is the point: a feed that sends identity and nothing else is audited and produces four
    honest "not in feed" rows rather than four findings.
    """
    record = record_from_mapping(
        {
            "sku": "SL-63",
            "mpn": "SL-63",
            "manufacturer": "ACME",
            "description": "selective main line circuit breaker",
        }
    )
    result = audit_sku(
        record,
        source_of(ordering_table_pdf, doc_id="acme"),
        etim=etim,
        scope=load_scope(),
        attributes=ATTRIBUTES,
    )
    assert result.class_uri == "etim:EC001047 @ 10.0"
    assert result.findings == ()
    assert {o.outcome for o in result.outcomes} == {Outcome.NOT_IN_FEED}


def test_coverage_excludes_attributes_the_feed_never_carried(audit) -> None:
    result = audit(order_code="X")
    # Five attributes considered: four audited, one declined (the order code has no grammar). A
    # coverage that punished a customer for a narrow schema would be noise, so columns the feed
    # never sent are not in the denominator.
    assert result.coverage == pytest.approx(0.8)


def test_an_unresolvable_class_declines_the_whole_record(etim, ordering_table_pdf, source_of) -> None:
    """No class means no schema, and no schema means every attribute would be judged against a
    value list that may not apply. FR-2.3: a decline with a reason, never a default class."""
    record = record_from_mapping(
        {"sku": "AX-16", "mpn": "AX-16", "description": "circuit breaker", "rated_current": "61 A"}
    )
    result = audit_sku(
        record,
        source_of(ordering_table_pdf, doc_id="acme"),
        etim=etim,
        scope=load_scope(),
        attributes=ATTRIBUTES,
    )
    assert result.findings == ()
    assert result.class_uri == ""
    assert result.declined
    assert all(o.declined_reason is DeclinedReason.CLASS_UNRESOLVED for o in result.declined)


def test_a_product_missing_from_the_document_declines_rather_than_matching_a_neighbour(
    etim, ordering_table_pdf, source_of
) -> None:
    record = record_from_mapping(
        {"sku": "AX-63", "mpn": "AX-63", "description": "miniature circuit breaker",
         "rated_current": "63 A", "poles": "1"}
    )
    result = audit_sku(
        record, source_of(ordering_table_pdf, doc_id="acme"), etim=etim, scope=load_scope(),
        attributes=ATTRIBUTES,
    )
    assert result.findings == ()
    assert {o.declined_reason for o in result.declined} == {DeclinedReason.NO_SOURCE_DOCUMENT}


def test_the_class_query_never_contains_the_values_under_audit(audit) -> None:
    """A resolver that read the values would choose the schema that makes those values look right,
    and every judgment afterwards would be conditioned on the answer."""
    from errata_audit.audit import _class_query

    record = record_from_mapping(
        {"sku": "AX-16", "manufacturer": "ACME", "description": "MCB", "rated_current": "61 A"}
    )
    query = _class_query(record)
    assert "61" not in query
    assert "MCB" in query


def test_findings_are_ranked_by_expected_review_value_not_by_confidence(audit) -> None:
    result = audit(rated_current="61 A", packaging_uom="Each", weight_kg="1.25 kg")
    values = [o.redline.expected_review_value for o in result.findings]
    assert values == sorted(values, reverse=True)
    # The safety-class attributes lead -- rated current and packaging UOM are both on the list, and
    # they tie, so the order between them falls to a deterministic key rather than to chance. The
    # weight finding is equally probable and ranks last, which is the whole point: the reviewer's
    # next thirty seconds go where they are worth the most, not where the model is surest.
    assert result.findings[-1].attribute.key == "weight_kg"
    assert {o.attribute.key for o in result.findings[:2]} == {"rated_current", "packaging_uom"}
    assert all(o.redline.requires_two_signatures for o in result.findings[:2])


def test_a_finding_always_has_a_counter_evidence_panel(audit) -> None:
    """FR-7.4: never empty and never absent. When nothing supports the catalog, the panel says so
    -- that sentence is the finding."""
    for outcome in audit(rated_current="61 A", packaging_uom="Each").findings:
        assert outcome.redline.counter_evidence.summary.strip()


def test_the_run_records_which_class_and_which_document(audit) -> None:
    result = audit(rated_current="61 A")
    assert result.class_uri == "etim:EC000042 @ 10.0"
    assert result.document.sha256
    assert result.findings[0].redline.evidence[0].doc_revision_sha256 == result.document.sha256
