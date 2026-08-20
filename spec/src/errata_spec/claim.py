"""The Claim -- the atomic unit of the system (§4.1).

Nothing in Errata stores "the value of attribute X for SKU Y". It stores immutable, append-only
*claims about* that value, each carrying who asserted it, from what, and how sure they were.

**The hard invariant:** a claim asserted by an extractor with an empty evidence array cannot be
constructed. Phase 1's imperative -- *no provenance, reject* -- is not a validation rule that gets
relaxed under deadline pressure. If the extractor cannot produce a span it emits an
:class:`Abstention`, which is a different type, and the type system refuses to let one be read as
the other.

Evidence is stored as a char span on the canonical text layer with a *derived* bbox projection
(ADR-002). Upgrading OCR recomputes coordinates without invalidating a single claim.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .taxonomy import DeclinedReason

__all__ = [
    "Abstention",
    "AsserterKind",
    "BBox",
    "Claim",
    "ClaimOrAbstention",
    "ClaimStatus",
    "Confidence",
    "EmptyEvidenceError",
    "Evidence",
    "ExtractorFingerprint",
    "emit_abstention",
    "emit_extracted_claim",
]


class EmptyEvidenceError(ValueError):
    """Raised when something tries to construct a machine claim with no evidence.

    This is the exception that keeps the product honest. It should never be caught and downgraded;
    the correct handling is to emit an :class:`Abstention` instead.
    """


class AsserterKind(str, enum.Enum):
    SOURCE_FEED = "source_feed"
    """The catalog itself. Carries no evidence by construction -- it *is* the thing under audit."""

    EXTRACTOR = "extractor"
    """A machine re-derivation. Evidence is mandatory."""

    HUMAN = "human"
    """A reviewer's adjudication. Evidence optional: "keep catalog" with no supporting evidence is
    the highest-signal event in the system (§5.4) and must be recordable."""

    POLICY = "policy"
    """A value selected by the resolution policy from competing claims."""


class ClaimStatus(str, enum.Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"
    DISPUTED = "disputed"


class BBox(BaseModel):
    """A bounding box in PDF user-space points, origin top-left.

    Derived, not stored as truth: a projection of :attr:`Evidence.char_span` through the versioned
    layout map (ADR-002). Regenerated when the extraction layer is upgraded.
    """

    model_config = ConfigDict(frozen=True)

    x0: float
    y0: float
    x1: float
    y1: float

    def iou(self, other: BBox) -> float:
        """Intersection over union -- ExtractBench scores word-level grounding at IoU 0.5 (FR-9.1),
        and we reuse its metric verbatim so our numbers are comparable to the published 46.43."""
        ix0, iy0 = max(self.x0, other.x0), max(self.y0, other.y0)
        ix1, iy1 = min(self.x1, other.x1), min(self.y1, other.y1)
        if ix1 <= ix0 or iy1 <= iy0:
            return 0.0
        intersection = (ix1 - ix0) * (iy1 - iy0)
        union = self.area + other.area - intersection
        return intersection / union if union > 0 else 0.0

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)


class Evidence(BaseModel):
    """One span of a source document that supports a value."""

    model_config = ConfigDict(frozen=True)

    doc_id: str
    doc_revision_sha256: str = Field(min_length=64, max_length=64)
    """The hash of the exact bytes. A supplier reposting a PDF at the same URL creates a new
    revision, and every claim anchored to the prior hash becomes historical rather than wrong."""

    page: int = Field(ge=1)

    char_span: tuple[int, int]
    """Primary anchor: offsets into the canonical text layer (ADR-002 option D)."""

    bbox: BBox | None = None
    """Projection of the char span. Regenerable; never the source of truth."""

    snippet: str = ""
    extraction_layer_version: str = ""

    table_cell: str = ""
    """Cell reference when the value came from a table."""

    row_header: str = ""
    column_header: str = ""
    """FR-7.3. A number in an engineering table means nothing without its headers, and a system
    that boxes ``6`` without boxing ``Rated current (A)`` has not explained anything."""

    @model_validator(mode="after")
    def _span_is_ordered(self) -> Evidence:
        start, end = self.char_span
        if start < 0 or end < start:
            raise ValueError(f"char_span {self.char_span} is not a valid forward span")
        return self


class ExtractorFingerprint(BaseModel):
    """Everything needed to reproduce a machine claim byte for byte (NFR-1, NFR-2)."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    model_id: str = ""
    prompt_sha256: str = ""
    params_sha256: str = ""
    decode_constraints_sha256: str = ""
    grammar_version: str = ""
    """The value-semantics grammar version that normalized the value (FR-4.5)."""


class Confidence(BaseModel):
    """How sure, honestly.

    ``calibrated_p`` is the product. If 0.9 does not mean nine in ten, the triage router mis-ranks,
    the abstention curve is decoration, and the reviewer is back to a meaningless 92%.
    """

    model_config = ConfigDict(frozen=True)

    raw_score: float | None = None
    calibrated_p: float | None = Field(default=None, ge=0.0, le=1.0)
    calibration_set_id: str = ""
    method: Literal["conformal", "platt", "temperature", "none"] = "none"
    abstained: bool = False
    abstain_reason: DeclinedReason | None = None

    @model_validator(mode="after")
    def _calibration_is_attributable(self) -> Confidence:
        if self.calibrated_p is not None and self.method == "none":
            raise ValueError(
                "a calibrated probability must name the method that produced it; an uncalibrated "
                "score belongs in raw_score"
            )
        if self.calibrated_p is not None and not self.calibration_set_id:
            raise ValueError(
                "a calibrated probability must name its calibration set, or it cannot be audited "
                "when the set drifts"
            )
        return self


def _now() -> datetime:
    return datetime.now(UTC)


class Claim(BaseModel):
    """An immutable assertion about one attribute's value.

    Never mutated and never deleted (FR-8.2). A correction is a new claim whose ``supersedes``
    points at the old one, which is what makes batch reversal a query rather than a recovery
    project (§4.3 commitment 1).
    """

    model_config = ConfigDict(frozen=True)

    claim_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    sku_id: str
    mpn: str = ""
    attribute_uri: str
    """``etim:EF000094`` | ``eclass:0173-1#02-AAO662`` | ``customer:MAT_GRADE``."""

    class_uri: str = ""
    """``etim:EC000042 @ 10.0`` -- the release is part of the identity."""

    value_raw: str
    """Exactly as it appeared. FR-1.1: original strings are preserved without mutation."""

    value_normalized: dict[str, Any] = Field(default_factory=dict)
    """The typed structure from errata-valuesem, serialised."""

    evidence: tuple[Evidence, ...] = ()

    asserter_kind: AsserterKind
    extractor: ExtractorFingerprint | None = None
    confidence: Confidence = Field(default_factory=Confidence)

    asserted_at: datetime = Field(default_factory=_now)
    supersedes: uuid.UUID | None = None
    status: ClaimStatus = ClaimStatus.ACTIVE

    source_rank_key: str = ""
    """Which bucket of the resolution policy's ``source_rank`` this claim came from."""

    @model_validator(mode="after")
    def _machine_claims_carry_evidence(self) -> Claim:
        if self.asserter_kind is AsserterKind.EXTRACTOR and not self.evidence:
            raise EmptyEvidenceError(
                f"extractor claim for {self.sku_id}/{self.attribute_uri} has no evidence. "
                "An extractor that cannot produce a span emits an Abstention, not a value. "
                "See errata_spec.claim.emit_abstention."
            )
        if self.asserter_kind is AsserterKind.EXTRACTOR and self.extractor is None:
            raise ValueError(
                "an extractor claim must carry its fingerprint (NFR-2) or its provenance cannot "
                "be reconstructed"
            )
        return self

    @property
    def is_grounded(self) -> bool:
        return any(e.bbox is not None or e.char_span[1] > e.char_span[0] for e in self.evidence)


class Abstention(BaseModel):
    """A declared non-answer. A different type from a Claim, deliberately (FR-3.3).

    An abstention can never be read as a value downstream, because it has no ``value_raw`` field to
    read. That is the whole point: null-on-blank is not abstention, and a system that returns an
    empty string for "I could not tell" has quietly converted an unknown into a fact.
    """

    model_config = ConfigDict(frozen=True)

    abstention_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    sku_id: str
    mpn: str = ""
    attribute_uri: str
    class_uri: str = ""

    reason: DeclinedReason
    detail: str = ""
    """Human-readable, shown in the Declined bucket. Not a stack trace."""

    asserter_kind: AsserterKind = AsserterKind.EXTRACTOR
    extractor: ExtractorFingerprint | None = None
    considered_evidence: tuple[Evidence, ...] = ()
    """What was looked at before declining. Makes "we tried" auditable (NFR-9)."""

    asserted_at: datetime = Field(default_factory=_now)


ClaimOrAbstention = Annotated[Claim | Abstention, Field(discriminator=None)]


# ------------------------------------------------------------------------------------------------
# The only sanctioned way for a machine to emit
# ------------------------------------------------------------------------------------------------


def emit_extracted_claim(
    *,
    sku_id: str,
    attribute_uri: str,
    value_raw: str,
    evidence: tuple[Evidence, ...],
    extractor: ExtractorFingerprint,
    **kwargs: Any,
) -> Claim:
    """Construct an extractor claim. Raises if evidence is empty.

    Extractors call this rather than :class:`Claim` directly, so that the "no provenance, reject"
    rule is on the shortest path rather than in a code review comment.
    """
    if not evidence:
        raise EmptyEvidenceError(
            f"refusing to emit a claim for {sku_id}/{attribute_uri} with no evidence; "
            "call emit_abstention with DeclinedReason.NO_SPAN instead"
        )
    return Claim(
        sku_id=sku_id,
        attribute_uri=attribute_uri,
        value_raw=value_raw,
        evidence=evidence,
        asserter_kind=AsserterKind.EXTRACTOR,
        extractor=extractor,
        **kwargs,
    )


def emit_abstention(
    *,
    sku_id: str,
    attribute_uri: str,
    reason: DeclinedReason,
    detail: str = "",
    **kwargs: Any,
) -> Abstention:
    """Construct an abstention. Always available, never a failure path."""
    return Abstention(
        sku_id=sku_id,
        attribute_uri=attribute_uri,
        reason=reason,
        detail=detail,
        **kwargs,
    )
