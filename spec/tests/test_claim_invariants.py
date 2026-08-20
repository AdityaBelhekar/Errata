"""The invariants that are not allowed to be relaxed.

FR-3.2 says the empty-evidence rule is "enforced at the type/constructor level, not by validation
that can be relaxed". A rule with no test is a comment, so each one gets a test that fails loudly
if someone removes the guard under deadline pressure.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from errata_spec import (
    Abstention,
    Adjudication,
    AsserterKind,
    BBox,
    BlastRadius,
    Claim,
    Confidence,
    CounterEvidence,
    Decision,
    DeclinedReason,
    DisagreementClass,
    EmptyEvidenceError,
    Evidence,
    ExtractorFingerprint,
    Redline,
    Severity,
    builtin_policy,
    emit_abstention,
    emit_extracted_claim,
    is_safety_class,
)
from errata_spec.policy import PolicyRule, ResolutionPolicy

SHA = "a" * 64


def make_evidence(**kwargs: object) -> Evidence:
    base: dict[str, object] = {
        "doc_id": "doc-1",
        "doc_revision_sha256": SHA,
        "page": 4,
        "char_span": (1841, 1851),
        "snippet": "Rated current 6 A",
        "row_header": "Rated current (A)",
        "column_header": "iC60N",
    }
    base.update(kwargs)
    return Evidence(**base)  # type: ignore[arg-type]


FINGERPRINT = ExtractorFingerprint(name="span-required", version="0.1.0", model_id="test")


# ------------------------------------------------------------------- no provenance, no claim --


def test_extractor_claim_without_evidence_cannot_be_constructed() -> None:
    with pytest.raises((EmptyEvidenceError, ValidationError)):
        Claim(
            sku_id="MCB-63C-2P",
            attribute_uri="etim:EF000094",
            value_raw="6 A",
            evidence=(),
            asserter_kind=AsserterKind.EXTRACTOR,
            extractor=FINGERPRINT,
        )


def test_the_emit_helper_refuses_too() -> None:
    with pytest.raises(EmptyEvidenceError):
        emit_extracted_claim(
            sku_id="MCB-63C-2P",
            attribute_uri="etim:EF000094",
            value_raw="6 A",
            evidence=(),
            extractor=FINGERPRINT,
        )


def test_extractor_claim_must_carry_its_fingerprint() -> None:
    """NFR-2: without it the claim's provenance cannot be reconstructed."""
    with pytest.raises(ValidationError):
        Claim(
            sku_id="MCB-63C-2P",
            attribute_uri="etim:EF000094",
            value_raw="6 A",
            evidence=(make_evidence(),),
            asserter_kind=AsserterKind.EXTRACTOR,
        )


def test_the_catalog_itself_may_assert_without_evidence() -> None:
    """The source feed is the thing under audit; demanding evidence from it is incoherent."""
    claim = Claim(
        sku_id="MCB-63C-2P",
        attribute_uri="etim:EF000094",
        value_raw="63 A",
        asserter_kind=AsserterKind.SOURCE_FEED,
    )
    assert claim.evidence == ()


def test_a_human_may_keep_the_catalog_with_no_supporting_evidence() -> None:
    """§5.4: the highest-signal event in the system. It must be recordable."""
    claim = Claim(
        sku_id="MCB-63C-2P",
        attribute_uri="etim:EF000094",
        value_raw="63 A",
        asserter_kind=AsserterKind.HUMAN,
    )
    assert claim.asserter_kind is AsserterKind.HUMAN


def test_abstention_has_no_value_field_to_misread() -> None:
    """FR-3.3: an abstention can never be read as a value downstream."""
    abstention = emit_abstention(
        sku_id="MCB-63C-2P",
        attribute_uri="etim:EF000094",
        reason=DeclinedReason.LAYOUT_UNREADABLE,
        detail="fold-out page",
    )
    assert not hasattr(abstention, "value_raw")
    assert not hasattr(abstention, "value_normalized")
    assert isinstance(abstention, Abstention)


def test_every_declined_reason_is_reachable() -> None:
    for reason in DeclinedReason:
        assert emit_abstention(sku_id="s", attribute_uri="a", reason=reason).reason is reason


# ------------------------------------------------------------------------------- immutability --


def test_claims_are_frozen() -> None:
    claim = emit_extracted_claim(
        sku_id="MCB-63C-2P",
        attribute_uri="etim:EF000094",
        value_raw="6 A",
        evidence=(make_evidence(),),
        extractor=FINGERPRINT,
    )
    with pytest.raises(ValidationError):
        claim.value_raw = "63 A"  # type: ignore[misc]


def test_supersession_preserves_the_prior_claim() -> None:
    """FR-8.8: batch reversal is a query because nothing is destroyed."""
    original = emit_extracted_claim(
        sku_id="s",
        attribute_uri="a",
        value_raw="63 A",
        evidence=(make_evidence(),),
        extractor=FINGERPRINT,
    )
    replacement = emit_extracted_claim(
        sku_id="s",
        attribute_uri="a",
        value_raw="6 A",
        evidence=(make_evidence(),),
        extractor=FINGERPRINT,
        supersedes=original.claim_id,
    )
    assert replacement.supersedes == original.claim_id
    assert original.value_raw == "63 A"


# -------------------------------------------------------------------------------- calibration --


def test_a_calibrated_probability_must_name_its_method_and_set() -> None:
    with pytest.raises(ValidationError):
        Confidence(calibrated_p=0.9)
    with pytest.raises(ValidationError):
        Confidence(calibrated_p=0.9, method="conformal")
    assert Confidence(calibrated_p=0.9, method="conformal", calibration_set_id="mcb-v1")


def test_an_uncalibrated_score_is_allowed_but_not_dressed_up() -> None:
    confidence = Confidence(raw_score=0.87)
    assert confidence.calibrated_p is None


# ------------------------------------------------------------------------------------ evidence --


def test_bbox_iou_matches_the_extractbench_metric() -> None:
    """FR-9.1: reused verbatim so our numbers are comparable to the published 46.43."""
    box = BBox(x0=0, y0=0, x1=10, y1=10)
    assert box.iou(box) == pytest.approx(1.0)
    assert box.iou(BBox(x0=20, y0=20, x1=30, y1=30)) == 0.0
    half = box.iou(BBox(x0=5, y0=0, x1=15, y1=10))
    assert half == pytest.approx(1 / 3)


def test_evidence_rejects_a_backwards_span() -> None:
    with pytest.raises(ValidationError):
        make_evidence(char_span=(200, 100))


def test_document_revision_hash_is_required_and_sized() -> None:
    with pytest.raises(ValidationError):
        make_evidence(doc_revision_sha256="short")


# ------------------------------------------------------------------------------------ redlines --


def _redline(**kwargs: object) -> Redline:
    base: dict[str, object] = {
        "sku_id": "MCB-63C-2P",
        "attribute_uri": "rated_current",
        "attribute_label": "Rated current",
        "catalog_value": "63 A",
        "proposed_value": "6 A",
        "disagreement_class": DisagreementClass.CONTRADICTION,
        "severity": Severity.SEV1,
        "counter_evidence": CounterEvidence.none_found("63 A"),
    }
    base.update(kwargs)
    return Redline(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "quiet",
    [
        DisagreementClass.SEMANTIC_EQUIVALENCE,
        DisagreementClass.UNIT_FRAME_MISMATCH,
        DisagreementClass.AGREEMENT,
        DisagreementClass.UNDETERMINED,
    ],
)
def test_non_findings_cannot_be_materialised_as_redlines(quiet: DisagreementClass) -> None:
    """FR-5.3, enforced at the type level: `316 SS` versus `A4` must never reach a queue."""
    with pytest.raises(ValidationError):
        _redline(disagreement_class=quiet, severity=Severity.NONE)


def test_counter_evidence_cannot_be_silently_empty() -> None:
    with pytest.raises(ValidationError):
        CounterEvidence(supporting=(), independent=False, summary="   ")


def test_counter_evidence_states_its_finding_even_when_there_is_none() -> None:
    panel = CounterEvidence.none_found("63 A")
    assert "No independent evidence" in panel.summary


def test_safety_class_acceptance_needs_a_second_named_adjudicator() -> None:
    """FR-8.9. Single-signature acceptance is impossible for allow-listed attributes."""
    redline = _redline()
    assert redline.requires_two_signatures
    with pytest.raises(ValidationError):
        _redline(
            adjudication=Adjudication(decision=Decision.ACCEPT_REDLINE, decided_by="alex")
        )
    assert _redline(
        adjudication=Adjudication(
            decision=Decision.ACCEPT_REDLINE, decided_by="alex", second_adjudicator="sam"
        )
    )


def test_non_safety_attributes_accept_on_one_signature() -> None:
    redline = _redline(
        attribute_uri="package_depth",
        attribute_label="Depth",
        adjudication=Adjudication(decision=Decision.ACCEPT_REDLINE, decided_by="alex"),
    )
    assert not redline.requires_two_signatures


def test_queue_row_reads_as_a_sentence_not_a_score() -> None:
    """FR-7.5: no UI surface displays a raw confidence score as the primary signal."""
    sentence = _redline(
        probability_catalog_wrong=0.93,
        blast_radius=BlastRadius(
            revenue_weight=4.0,
            safety_class_multiplier=25.0,
            propagation_count=3,
            record_multiplicity=1240,
        ),
    ).queue_sentence()
    assert "Catalog says '63 A'" in sentence
    assert "1,240 SKUs share this error signature" in sentence
    assert "0.93" not in sentence
    assert "93%" not in sentence


def test_expected_review_value_is_probability_times_blast_radius() -> None:
    redline = _redline(
        probability_catalog_wrong=0.5,
        blast_radius=BlastRadius(revenue_weight=2.0, propagation_count=3, record_multiplicity=10),
    )
    assert redline.expected_review_value == pytest.approx(0.5 * 2.0 * 3 * 10)


def test_blast_radius_factors_stay_individually_inspectable() -> None:
    """FR-8.4: a reviewer shown one opaque score has been given a number, not a reason."""
    explanation = BlastRadius(
        safety_class_multiplier=25.0, propagation_count=3, record_multiplicity=1240
    ).explain()
    assert len(explanation) == 3


# -------------------------------------------------------------------------------------- policy --


def test_the_builtin_policy_loads_and_names_its_version() -> None:
    policy = builtin_policy()
    assert policy.version_tag == "electrical-conservative@v3"
    assert policy.rank_of("manufacturer_datasheet_current") > policy.rank_of("distributor_feed")


def test_an_unknown_source_ranks_below_everything_named() -> None:
    assert builtin_policy().rank_of("some_scraper_nobody_declared") == 0


def test_safety_attributes_always_escalate() -> None:
    policy = builtin_policy()
    for attribute in ("rated_current", "breaking_capacity", "packaging_uom", "etim:rated_voltage"):
        assert policy.escalates(attribute)


def test_a_policy_that_deletes_the_safety_rule_is_rejected_at_load() -> None:
    """A customer-editable file is exactly where this promise would quietly disappear."""
    with pytest.raises(ValueError, match="escalation rule"):
        ResolutionPolicy(
            policy_id="permissive",
            version=1,
            source_rank={"distributor_feed": 40},
            rules=(PolicyRule(name="prefer_higher_rank", action="select_higher_rank"),),
        )


def test_a_policy_cannot_invent_an_action() -> None:
    with pytest.raises(ValueError, match="unknown action"):
        PolicyRule(name="just_do_it", action="auto_apply_everything")


def test_the_safety_list_matches_bare_keys_and_uris() -> None:
    assert is_safety_class("rated_current")
    assert is_safety_class("etim:rated_current")
    assert is_safety_class("Tripping Characteristic")
    assert not is_safety_class("package_depth")
    assert not is_safety_class("")
