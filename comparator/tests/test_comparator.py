"""Comparator behaviour: the taxonomy, and the rules that keep it from crying wolf.

FR-5.3 -- "semantic equivalence must not flag" -- is called out in the PRD as the single
highest-consequence requirement in the document. It gets tested three ways here: as a class
mapping, as a queue-materialisation refusal, and across the whole equivalence suite.
"""

from __future__ import annotations

import inspect

import pytest

from errata_comparator import AttributeSpec, build_redline, compare_attribute
from errata_comparator import compare as comparator_module
from errata_spec import DeclinedReason, DisagreementClass, Severity
from errata_spec.taxonomy import CLASS_PROFILE
from errata_valuesem import Kind

RATED_CURRENT = AttributeSpec(
    key="rated_current", label="Rated current", kinds=(Kind.QUANTITY,)
)
MATERIAL = AttributeSpec(key="material_grade", label="Material", kinds=(Kind.MATERIAL,))
PACKAGING = AttributeSpec(key="packaging_uom", label="Packaging", kinds=(Kind.PACKAGING,))
THREAD = AttributeSpec(key="thread_size", label="Thread", kinds=(Kind.THREAD,))
INGRESS = AttributeSpec(key="degree_of_protection", label="IP", kinds=(Kind.INGRESS,))
DEPTH = AttributeSpec(key="package_depth", label="Depth", kinds=(Kind.QUANTITY,))
TRIP = AttributeSpec(
    key="tripping_characteristic", label="Trip curve", kinds=(Kind.TERM,), vocabulary="trip_curve"
)


# ------------------------------------------------------------------------------- the taxonomy --


def test_contradiction() -> None:
    result = compare_attribute(RATED_CURRENT, "63 A", "6 A")
    assert result.disagreement_class is DisagreementClass.CONTRADICTION
    assert result.severity is Severity.SEV1
    assert result.raises_finding


def test_packaging_outranks_a_generic_contradiction() -> None:
    result = compare_attribute(PACKAGING, "Each", "Box of 10")
    assert result.disagreement_class is DisagreementClass.PACKAGING_FRAME_ERROR
    assert result.severity is Severity.SEV1
    assert "1/10" in result.rationale


def test_unsupported_value_when_the_corpus_is_silent() -> None:
    result = compare_attribute(INGRESS, "IP67", None)
    assert result.disagreement_class is DisagreementClass.UNSUPPORTED_VALUE
    assert "undefendable" in result.rationale


def test_catalog_null_with_evidence_present_is_a_recoverable_gap() -> None:
    result = compare_attribute(RATED_CURRENT, "", "10 kA")
    assert result.disagreement_class is DisagreementClass.CATALOG_NULL_EVIDENCE_PRESENT
    assert result.severity is Severity.SEV2


def test_a_stated_zero_is_a_value_not_a_blank() -> None:
    result = compare_attribute(DEPTH, "0 mm", "0 mm")
    assert result.disagreement_class is DisagreementClass.AGREEMENT


def test_unit_frame_mismatch_resolves_silently() -> None:
    result = compare_attribute(DEPTH, "0.5 in", "12.7 mm")
    assert result.disagreement_class is DisagreementClass.UNIT_FRAME_MISMATCH
    assert not result.raises_finding


def test_precision_mismatch_is_a_low_severity_finding() -> None:
    result = compare_attribute(DEPTH, "10 mm", "10 ±0.2 mm")
    assert result.disagreement_class is DisagreementClass.PRECISION_MISMATCH
    assert result.severity is Severity.SEV3
    assert result.raises_finding


def test_granularity_mismatch_is_under_specified_not_wrong() -> None:
    result = compare_attribute(THREAD, "Threaded", "NPT 1/2-14")
    assert result.disagreement_class is DisagreementClass.GRANULARITY_MISMATCH
    assert result.severity is Severity.SEV3


def test_catalog_more_specific_than_the_evidence_is_not_a_defect() -> None:
    result = compare_attribute(THREAD, "NPT 1/2-14", "Threaded")
    assert result.disagreement_class is DisagreementClass.AGREEMENT
    assert not result.raises_finding


# --------------------------------------------------------------------- FR-5.3, three ways over --


@pytest.mark.parametrize(
    "attribute,a,b",
    [
        (MATERIAL, "316 SS", "A4"),
        (MATERIAL, "316", "1.4401"),
        (MATERIAL, "Viton", "FKM"),
        (THREAD, "M8", "M8x1.25"),
        (PACKAGING, "Box of 10", "Pack of 10"),
        (TRIP, "C", "Type C"),
    ],
)
def test_semantic_equivalence_never_raises_a_finding(
    attribute: AttributeSpec, a: str, b: str
) -> None:
    result = compare_attribute(attribute, a, b)
    assert not result.raises_finding, f"{a!r} vs {b!r} -> {result.disagreement_class.value}"


def test_semantic_equivalence_cannot_be_turned_into_a_redline() -> None:
    result = compare_attribute(MATERIAL, "316 SS", "A4")
    assert build_redline(result) is None


def test_the_relation_mapping_covers_every_relation() -> None:
    from errata_valuesem import Relation

    for relation in Relation:
        assert relation in comparator_module.RELATION_TO_CLASS


def test_every_disagreement_class_has_a_profile() -> None:
    for member in DisagreementClass:
        assert member in CLASS_PROFILE


# ------------------------------------------------------------------------- abstention, not noise --


@pytest.mark.parametrize(
    "attribute,a,b",
    [
        (RATED_CURRENT, "63 A", "230 V"),
        (RATED_CURRENT, "suitable for most uses", "6 A"),
        (RATED_CURRENT, "63 A", "see table 4"),
        (RATED_CURRENT, "1,000 A", "1000 A"),
        (AttributeSpec(key="x", kinds=()), "Type B", "Type B"),
    ],
)
def test_unparseable_or_incomparable_values_decline(
    attribute: AttributeSpec, a: str, b: str
) -> None:
    result = compare_attribute(attribute, a, b)
    assert result.disagreement_class is DisagreementClass.UNDETERMINED
    assert result.is_declined
    assert not result.raises_finding


def test_every_declined_comparison_carries_exactly_one_machine_readable_reason() -> None:
    """FR-6.2: no silent skips anywhere in the pipeline."""
    for a, b in [("63 A", "230 V"), ("nonsense", "6 A"), (None, None)]:
        result = compare_attribute(RATED_CURRENT, a, b)
        if result.is_declined:
            assert isinstance(result.declined_reason, DeclinedReason)
            assert result.rationale.strip()


def test_declining_names_which_side_failed() -> None:
    result = compare_attribute(RATED_CURRENT, "63 A", "consult factory")
    assert "the evidence value" in result.rationale
    assert result.evidence_refusal is not None
    assert result.catalog_refusal is None


def test_the_locale_can_be_declared_per_feed() -> None:
    german = AttributeSpec(
        key="rated_voltage", kinds=(Kind.QUANTITY,), decimal_separator="."
    )
    result = compare_attribute(german, "1,000 V", "1000 V")
    assert result.disagreement_class is DisagreementClass.AGREEMENT


# ------------------------------------------------------------------------ structural guarantees --


def test_no_raw_string_comparison_in_the_decision_path() -> None:
    """FR-5.1: comparison happens only after both sides are normalized.

    A cheap structural check, but it catches the specific regression that matters -- somebody
    adding `if catalog_raw == evidence_raw` as a fast path, which would make every unparseable
    identical pair report agreement instead of declining.
    """
    source = inspect.getsource(comparator_module)
    for smell in ("catalog_raw ==", "== catalog_raw", "catalog_raw.lower()", "raw == evidence_raw"):
        assert smell not in source, f"raw string comparison {smell!r} found in the decision path"


def test_identical_unparseable_strings_decline_rather_than_agree() -> None:
    result = compare_attribute(RATED_CURRENT, "consult factory", "consult factory")
    assert result.disagreement_class is DisagreementClass.UNDETERMINED


def test_findings_carry_a_rationale_a_reviewer_can_read() -> None:
    result = compare_attribute(RATED_CURRENT, "63 A", "6 A")
    assert "63" in result.rationale and "6" in result.rationale
    assert "cannot both be true" in result.rationale


# ---------------------------------------------------------------------------------- redlines --


def test_redline_carries_a_counter_evidence_panel_by_default() -> None:
    result = compare_attribute(RATED_CURRENT, "63 A", "6 A")
    redline = build_redline(result)
    assert redline is not None
    assert redline.counter_evidence.summary
    assert redline.requires_two_signatures


def test_safety_attributes_get_a_larger_blast_radius() -> None:
    safety = build_redline(compare_attribute(RATED_CURRENT, "63 A", "6 A"))
    cosmetic = build_redline(compare_attribute(DEPTH, "10 mm", "60 mm"))
    assert safety is not None and cosmetic is not None
    assert safety.blast_radius.safety_class_multiplier > cosmetic.blast_radius.safety_class_multiplier
