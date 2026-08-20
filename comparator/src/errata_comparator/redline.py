"""Turning a comparison into a reviewable redline.

The counter-evidence panel is assembled here rather than in the console, so that a redline is never
constructible without one. FR-7.4 says it is never empty and never absent; making it a required
constructor argument is how that becomes true rather than aspirational.
"""

from __future__ import annotations

from errata_spec import (
    BlastRadius,
    CounterEvidence,
    Evidence,
    Redline,
    is_safety_class,
)

from .compare import Comparison

__all__ = ["SAFETY_MULTIPLIER", "build_redline"]

#: How much more a safety-class attribute is worth in the queue. Not tuned -- chosen so that a
#: safety finding outranks an equally probable cosmetic one, and documented as an assumption rather
#: than presented as a measurement.
SAFETY_MULTIPLIER = 25.0


def build_redline(
    comparison: Comparison,
    *,
    evidence: tuple[Evidence, ...] = (),
    counter_evidence: CounterEvidence | None = None,
    revenue_weight: float = 1.0,
    propagation_count: int = 0,
    record_multiplicity: int = 1,
    probability_catalog_wrong: float | None = None,
) -> Redline | None:
    """Materialise a redline, or ``None`` when the comparison raises no finding.

    Returning ``None`` for agreement, semantic equivalence and unit-frame mismatch is not a
    convenience -- ``Redline`` refuses to be constructed for those classes, because a queue
    containing "316 SS versus A4" is the specific failure that ends a pilot.
    """
    if not comparison.raises_finding:
        return None

    safety = is_safety_class(comparison.attribute.key) or is_safety_class(
        comparison.attribute.label
    )

    return Redline(
        sku_id="",
        attribute_uri=comparison.attribute.attribute_uri,
        attribute_label=comparison.attribute.label,
        catalog_value=comparison.catalog_raw,
        proposed_value=comparison.evidence_raw,
        disagreement_class=comparison.disagreement_class,
        severity=comparison.severity,
        evidence=evidence,
        counter_evidence=counter_evidence
        or CounterEvidence.none_found(comparison.catalog_raw),
        blast_radius=BlastRadius(
            revenue_weight=revenue_weight,
            safety_class_multiplier=SAFETY_MULTIPLIER if safety else 1.0,
            propagation_count=propagation_count,
            record_multiplicity=record_multiplicity,
        ),
        probability_catalog_wrong=probability_catalog_wrong,
        rationale=comparison.rationale,
    )
