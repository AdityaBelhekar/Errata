"""The Redline -- the system's only output (§4.3).

Errata does not write to a customer catalog (ADR-001). It emits a proposed change addressed to a
human, with the evidence attached and *the case against itself stated first*.

That last part is the counter-evidence panel, and it is the component competitors will not build.
When the system disagrees it must argue the other side, or say plainly that it cannot. An auditor
that only shows evidence for its own conclusion is a prosecutor, and a reviewer learns to distrust
a prosecutor by the third screen. Sometimes the counter-evidence will be strong enough that the
reviewer keeps the catalog value -- that is the feature working, not failing.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .claim import Evidence
from .taxonomy import CLASS_PROFILE, DisagreementClass, Severity, is_safety_class

__all__ = [
    "Adjudication",
    "BlastRadius",
    "CounterEvidence",
    "Decision",
    "Redline",
]


class Decision(str, enum.Enum):
    ACCEPT_REDLINE = "accept_redline"
    KEEP_CATALOG = "keep_catalog"
    """Highest-signal event in the system when there is no supporting evidence (§5.4): the reviewer
    knows something the corpus does not. Each one is a document-recovery lead and a systematic
    false-positive signal."""

    ESCALATE = "escalate"


#: How each decision is named in prose addressed to the reviewer who made it. A refusal that
#: misnames the decision reads as a refusal of something else entirely, and the reviewer is left
#: correcting the record instead of reading it (register O-11).
_DECISION_NOUN: dict[Decision, str] = {
    Decision.ACCEPT_REDLINE: "acceptance",
    Decision.KEEP_CATALOG: "decision to keep the catalog value",
    Decision.ESCALATE: "escalation",
}


class BlastRadius(BaseModel):
    """How much damage one wrong value causes (§5.1, FR-8.4).

    Every factor is stored separately and rendered separately, because a reviewer who is shown a
    single opaque score has been given a number, not a reason. FR-8.4: each factor must be
    independently inspectable in the UI.
    """

    model_config = ConfigDict(frozen=True)

    revenue_weight: float = Field(default=1.0, ge=0.0)
    """SKU revenue x how often the category is filtered on."""

    safety_class_multiplier: float = Field(default=1.0, ge=1.0)
    """Fire / injury / regulatory exposure."""

    propagation_count: int = Field(default=0, ge=0)
    """Faceted filters + punchout feeds + compliance exports this attribute touches."""

    record_multiplicity: int = Field(default=1, ge=1)
    """How many SKUs share this error signature. Computed from clustering, never asserted
    (FR-8.5)."""

    @property
    def score(self) -> float:
        return (
            self.revenue_weight
            * self.safety_class_multiplier
            * max(1, self.propagation_count)
            * self.record_multiplicity
        )

    def explain(self) -> list[str]:
        """The factors as sentences, for the queue row."""
        lines = []
        if self.record_multiplicity > 1:
            lines.append(f"{self.record_multiplicity:,} SKUs share this error signature")
        if self.propagation_count:
            lines.append(f"this attribute feeds {self.propagation_count} downstream surfaces")
        if self.safety_class_multiplier > 1:
            lines.append("the attribute is on the safety-class list")
        return lines


class CounterEvidence(BaseModel):
    """The best case *for* the catalog's value (FR-7.4).

    Never absent. When nothing supports the catalog, this object still exists and says so in
    ``summary`` -- a disagreement rendered without a counter-evidence section fails review.
    """

    model_config = ConfigDict(frozen=True)

    supporting: tuple[Evidence, ...] = ()
    independent: bool = False
    """False when the only support comes from the same feed that is under audit. A distributor
    product page derived from the feed being audited is not independent corroboration, and
    presenting it as such would be circular."""

    summary: str

    @model_validator(mode="after")
    def _summary_is_stated(self) -> CounterEvidence:
        if not self.summary.strip():
            raise ValueError(
                "counter-evidence must state its finding in words, including when the finding is "
                "'no independent evidence supports the catalog value'"
            )
        return self

    @classmethod
    def none_found(cls, catalog_value: str) -> CounterEvidence:
        return cls(
            supporting=(),
            independent=False,
            summary=f"No independent evidence supports the catalog value of {catalog_value!r}.",
        )


class Adjudication(BaseModel):
    """A human decision. Becomes a claim in the ledger and a calibration label (§5.4)."""

    model_config = ConfigDict(frozen=True)

    decision: Decision
    decided_by: str
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    note: str = ""
    seconds_to_decision: float | None = None
    """Feeds reviewer-seconds-per-verified-attribute (FR-9.3) -- the metric the buyer actually
    pays for and nobody publishes."""

    evidence_accepted: bool | None = None
    """Did the reviewer accept that the box supports the claim? Feeds evidence-acceptance rate
    (FR-9.4), which is distinct from grounding F1 against a gold box and may matter more."""

    second_adjudicator: str = ""
    """Required for safety-class attributes (FR-8.9)."""


class Redline(BaseModel):
    """A proposed correction addressed to a human."""

    model_config = ConfigDict(frozen=True)

    redline_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    sku_id: str
    mpn: str = ""
    attribute_uri: str
    attribute_label: str = ""
    class_uri: str = ""

    catalog_claim_id: uuid.UUID | None = None
    proposed_claim_id: uuid.UUID | None = None

    catalog_value: str
    proposed_value: str

    disagreement_class: DisagreementClass
    severity: Severity
    blast_radius: BlastRadius = Field(default_factory=BlastRadius)
    probability_catalog_wrong: float | None = Field(default=None, ge=0.0, le=1.0)

    evidence: tuple[Evidence, ...] = ()
    counter_evidence: CounterEvidence

    rationale: str = ""
    """Deterministic prose from the comparator. Safe to show verbatim."""

    adjudication: Adjudication | None = None

    @model_validator(mode="after")
    def _only_real_findings_become_redlines(self) -> Redline:
        profile = CLASS_PROFILE[self.disagreement_class]
        if not profile.raises_finding:
            raise ValueError(
                f"{self.disagreement_class.value} does not raise a finding; it must not be "
                "materialised as a redline. Semantic equivalence in a review queue is the "
                "failure this system exists to prevent."
            )
        if (
            self.requires_two_signatures
            and self.adjudication is not None
            and not self.adjudication.second_adjudicator
        ):
            # Name the decision the reviewer ACTUALLY made. This message used to say
            # "acceptance" for every disposition, so a reviewer who chose KEEP_CATALOG -- who
            # rejected the redline and kept their own value -- was told their acceptance was
            # refused. In a product whose entire claim is provenance, telling someone they made a
            # decision they did not make is an integrity defect, not a wording nit (register O-11).
            raise ValueError(
                f"{self.attribute_uri} is a safety-class attribute; a single-signature "
                f"{_DECISION_NOUN[self.adjudication.decision]} is impossible by construction "
                "(FR-8.9)"
            )
        return self

    @property
    def requires_two_signatures(self) -> bool:
        return is_safety_class(self.attribute_uri) or is_safety_class(self.attribute_label)

    @property
    def expected_review_value(self) -> float:
        """``P(catalog is wrong | evidence) x blast_radius`` (§5.1).

        The queue is sorted on this, not on confidence. The reviewer's next thirty seconds should
        go where they are worth the most, which is not the same as where the model is surest.
        """
        probability = self.probability_catalog_wrong
        if probability is None:
            # An uncalibrated finding is not promoted above a calibrated one on the strength of a
            # number nobody can check. Rank it by blast radius alone.
            probability = 0.5
        return probability * self.blast_radius.score

    def queue_sentence(self) -> str:
        """FR-7.5: a queue row reads as a sentence, never as a bare confidence percentage."""
        profile = CLASS_PROFILE[self.disagreement_class]
        head = f"SEV-{self.severity.value} - {self.sku_id} - {self.attribute_label or self.attribute_uri}"
        body = (
            f"Catalog says {self.catalog_value!r}. The evidence says {self.proposed_value!r} "
            f"({profile.reviewer_verb})."
        )
        lines = [head, body]
        lines.extend(self.blast_radius.explain())
        if self.requires_two_signatures:
            lines.append("Safety class: acceptance needs a second named adjudicator.")
        return "\n".join(lines)


def _quantise(value: Decimal) -> str:  # pragma: no cover - display helper
    return format(value.normalize(), "f")
