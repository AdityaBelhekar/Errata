"""The disagreement taxonomy (§3.3) and the declined-bucket reasons (FR-6.2).

The taxonomy is the intellectual contribution of this project and it is deliberately open source.
Its job is not "are these two strings different" -- that question produces a false-positive
avalanche that ends the pilot in week one. Its job is to classify *how* they differ, so that a
reviewer is shown a defect where there is one and nothing where there is not.

The classes are exhaustive and mutually exclusive (FR-5.2): every compared pair lands in exactly
one, including the ones that raise no finding at all.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

__all__ = [
    "CLASS_PROFILE",
    "SAFETY_CLASS_ATTRIBUTES",
    "ClassProfile",
    "DeclinedReason",
    "DisagreementClass",
    "Severity",
    "is_safety_class",
]


class Severity(enum.IntEnum):
    """Ordered so a queue can sort on it. SEV1 is the poisoned record."""

    SEV1 = 1
    SEV2 = 2
    SEV3 = 3
    NONE = 9
    """Not a finding. Carried explicitly so "we looked and it was fine" is a recorded outcome."""


class DisagreementClass(str, enum.Enum):
    """How a catalog value and an independently re-derived value differ."""

    CONTRADICTION = "contradiction"
    """Catalog ``63 A``; datasheet table cell ``6 A``. The poisoned record."""

    UNSUPPORTED_VALUE = "unsupported_value"
    """Catalog ``IP67``; no evidence anywhere in the corpus. The value may be right, but it cannot
    be defended to an angry customer or a regulatory auditor."""

    CATALOG_NULL_EVIDENCE_PRESENT = "catalog_null_evidence_present"
    """Catalog blank; datasheet states ``10 kA``. The fill-rate finding."""

    UNIT_FRAME_MISMATCH = "unit_frame_mismatch"
    """Catalog ``0.5 in``; datasheet ``12.7 mm``. Same fact, different frame. Resolved silently."""

    PRECISION_MISMATCH = "precision_mismatch"
    """Catalog ``10 mm``; datasheet ``10 +/-0.2 mm``. The tolerance was dropped -- which matters
    for fit and not for search, hence low severity."""

    SEMANTIC_EQUIVALENCE = "semantic_equivalence"
    """Catalog ``316 SS``; datasheet ``A4``; ERP ``1.4401``. **Never flagged.**

    This is the row that decides the company. An auditor that flags 316 SS against A4 is not a weak
    product, it is an actively harmful one: it burns the reviewer's trust in the first session and
    there is no second session."""

    GRANULARITY_MISMATCH = "granularity_mismatch"
    """Catalog ``Threaded``; datasheet ``NPT 1/2-14``. Under-specified, not wrong."""

    PACKAGING_FRAME_ERROR = "packaging_frame_error"
    """Catalog ``Each``; datasheet ``Box of 10``. Maximum severity, always."""

    AGREEMENT = "agreement"
    """The catalog value is supported by the evidence. Not a finding, and recorded as such."""

    UNDETERMINED = "undetermined"
    """The comparison could not be made. Routes to the Declined bucket with a reason, never to the
    queue. Distinct from AGREEMENT: "we checked and it is fine" and "we could not check" are
    different statements and the product refuses to blur them."""


@dataclass(frozen=True, slots=True)
class ClassProfile:
    """What a disagreement class means for the queue."""

    raises_finding: bool
    default_severity: Severity
    reviewer_verb: str
    """The sentence stem shown in the queue. §5.1: a queue row reads as a sentence, not a score."""


CLASS_PROFILE: dict[DisagreementClass, ClassProfile] = {
    DisagreementClass.PACKAGING_FRAME_ERROR: ClassProfile(
        True, Severity.SEV1, "the packaging frame disagrees"
    ),
    DisagreementClass.CONTRADICTION: ClassProfile(
        True, Severity.SEV1, "the catalog contradicts the manufacturer's document"
    ),
    DisagreementClass.CATALOG_NULL_EVIDENCE_PRESENT: ClassProfile(
        True, Severity.SEV2, "the catalog is blank where the document states a value"
    ),
    DisagreementClass.UNSUPPORTED_VALUE: ClassProfile(
        True, Severity.SEV2, "no evidence in the corpus supports the catalog value"
    ),
    DisagreementClass.GRANULARITY_MISMATCH: ClassProfile(
        True, Severity.SEV3, "the catalog is less specific than the document"
    ),
    DisagreementClass.PRECISION_MISMATCH: ClassProfile(
        True, Severity.SEV3, "a stated tolerance was dropped"
    ),
    DisagreementClass.UNIT_FRAME_MISMATCH: ClassProfile(
        False, Severity.NONE, "same value, different unit frame"
    ),
    DisagreementClass.SEMANTIC_EQUIVALENCE: ClassProfile(
        False, Severity.NONE, "same value, different vocabulary"
    ),
    DisagreementClass.AGREEMENT: ClassProfile(False, Severity.NONE, "the evidence supports the catalog"),
    DisagreementClass.UNDETERMINED: ClassProfile(False, Severity.NONE, "not audited"),
}


class DeclinedReason(str, enum.Enum):
    """Why a record was not audited (FR-6.2).

    Every declined record carries exactly one of these and appears in the UI. There are no silent
    skips anywhere in the pipeline, because a system that quietly skips what it cannot handle is
    indistinguishable from one that handled it.
    """

    NO_SOURCE_DOCUMENT = "no_source_document"
    """Nothing to ground against. Feeds the §2.3 document-recovery queue."""

    LAYOUT_UNREADABLE = "layout_unreadable"
    """Fold-out page, rotated table, cross-page table split."""

    OCR_TEXT_NOT_EVIDENCE = "ocr_text_not_evidence"
    """The document is a scan carrying an OCR layer (ADR-004).

    Deliberately NOT ``LAYOUT_UNREADABLE``: the layout is not what defeated us. The text is
    perfectly legible -- that is the problem. It is a model's reading of pixels rather than the
    document's own character stream, so grounding a claim in it cites something the document does
    not say, and the evidence box has nothing true to project onto.

    A reason that misdescribes what happened is worse than no reason, which is why this is its own
    member rather than a comment on an existing one.
    """

    AMBIGUOUS_MULTI_PRODUCT_PAGE = "ambiguous_multi_product_page"
    """Cannot determine which of several products on the page the value belongs to."""

    VALUE_OUTSIDE_KNOWN_GRAMMAR = "value_outside_known_grammar"
    """The value-semantics library refused to parse. Deliberately surfaced, never guessed."""

    EQUAL_RANK_SOURCE_CONFLICT = "equal_rank_source_conflict"
    """Two sources of identical evidentiary rank disagree; policy declines to arbitrate."""

    CALIBRATION_OUT_OF_DISTRIBUTION = "calibration_out_of_distribution"
    """Too few labels in this class for the confidence estimate to be honest.

    The one no competitor will ship: the system declaring that it does not yet know how much to
    trust itself in this region. It is also, per §8.3, the reason most likely to eat the product's
    coverage -- which is why R0 measures how often it fires before anything is built on top."""

    INCOMPARABLE_KINDS = "incomparable_kinds"
    """The two values belong to different semantic families or incommensurable dimensions. Almost
    always a schema mismatch upstream, and never reported as a product defect."""

    NO_SPAN = "no_span_available"
    """A value was re-derived but could not be grounded to a span, so it never became a claim."""

    CLASS_UNRESOLVED = "class_unresolved"
    """Class resolution could not separate its top candidates, so no schema was chosen (FR-2.3).

    Added in R1, alongside ``INCOMPARABLE_KINDS`` and ``NO_SPAN``, because FR-6.2's six reasons do
    not cover it and the alternatives all lie: ``calibration_out_of_distribution`` claims we know
    where our calibration ends, and ``ambiguous_multi_product_page`` blames the document for a
    decision the resolver declined to make. FR-2.3 requires this abstention to reach the Declined
    bucket **with a reason** rather than as a silent default class, and a reason that misdescribes
    what happened is a silent default class with better manners.
    """


#: Attributes where a wrong value creates physical or legal exposure.
#:
#: Policy rule ``safety_class_override`` (§4.2): never auto-resolved, at any confidence, with no
#: configuration override. Write-back is permanently excluded for these (ADR-001) and acceptance
#: requires a second named adjudicator (FR-8.9).
SAFETY_CLASS_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "breaking_capacity",
        "rated_current",
        "rated_voltage",
        "tripping_characteristic",
        "short_circuit_capacity",
        "residual_current_rating",
        "material_grade",
        "temperature_rating",
        "pressure_rating",
        "torque_rating",
        "load_rating",
        "packaging_uom",
        "hazard_classification",
        "compliance_declaration",
    }
)


def is_safety_class(attribute_key: str) -> bool:
    """True when an attribute is on the safety list.

    Matches on the trailing segment of an attribute URI as well as a bare key, so
    ``etim:EF000094`` mapped to ``tripping_characteristic`` and the bare name behave identically.
    """
    if not attribute_key:
        return False
    key = attribute_key.strip().lower().replace("-", "_").replace(" ", "_")
    if key in SAFETY_CLASS_ATTRIBUTES:
        return True
    tail = key.rsplit(":", 1)[-1].rsplit("/", 1)[-1]
    return tail in SAFETY_CLASS_ATTRIBUTES
