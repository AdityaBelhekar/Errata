"""The R1 audit itself: one SKU, one document, one honest answer per attribute.

This module is the assembly, and almost all of its judgment has already been made elsewhere -- by
``errata_valuesem`` (what a value means), by ``errata_comparator`` (how two values differ), by
``errata_spec`` (what may be asserted at all). What is decided *here* is the shape of the run, and
three shape decisions carry the product:

**Every attribute produces an outcome.** Findings, silent resolutions, declines and attributes the
feed does not carry all appear in the result. FR-6.2's "no silent skips anywhere in the pipeline"
is not satisfied by a pipeline that skips loudly in a log file: the outcome is a value in the run,
countable, with a reason attached. An audit that quietly dropped what it could not handle would
report a coverage it had not earned, and coverage is the number that makes the false-positive rate
mean anything (R0 gate 1 learned this the hard way).

**Class resolution gates everything, and abstains.** No class means no schema, and no schema means
every attribute is being judged against a value list that may not apply. That is a decline for the
whole record with a stated reason, never a default class (FR-2.3).

**An uncalibrated finding is not promoted.** When the raw score falls outside the calibration set's
support, the record moves to the Declined bucket with ``calibration_out_of_distribution`` rather
than to the queue with a probability nobody can defend (FR-6.1, FR-6.2). §8.3 warns this is the
reason most likely to eat coverage. It is still the right trade: the alternative is a confident
number about a region nobody has measured.

The order of operations is load-bearing and worth stating once: **derive first, blind; compare
second; look for counter-evidence third.** Counter-evidence is the only step permitted to look for
the catalog's own value in the document, and it runs after the derivation it can no longer
influence (FR-3.4).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from errata_comparator import Comparison, build_redline, compare_attribute
from errata_spec import (
    Abstention,
    Claim,
    Confidence,
    DeclinedReason,
    Redline,
    ResolutionPolicy,
    Severity,
    builtin_policy,
)

from .attributes import AttributeMap, AuditAttribute, load_attributes
from .classify import ClassResolution, ClassScope, resolve_class
from .confidence import (
    CalibrationModel,
    RiskCoveragePoint,
    aurc,
    calibrate,
    risk_coverage_curve,
)
from .counterevidence import find_counter_evidence
from .derive import DERIVE_VERSION, Derivation, derive
from .documents import DocumentSource
from .etim import EtimModel
from .ingest import CatalogRecord
from .layout import LAYOUT_VERSION, TextLayer, extract_layer
from .tables import TABLES_VERSION, Table, extract_tables

__all__ = [
    "AUDIT_VERSION",
    "REDLINE_NAMESPACE",
    "AttributeOutcome",
    "AuditRun",
    "Outcome",
    "SkuAudit",
    "audit_sku",
    "stable_redline_id",
]

AUDIT_VERSION = "errata-audit/1.0.0"

#: Downstream surfaces an attribute feeds, for the blast-radius factor. **Configuration a customer
#: supplies**, and zero until they do: the factor is rendered separately in the queue (FR-8.4) so a
#: reviewer can see it is unset rather than being handed a composite score with an invented term
#: inside it.
DEFAULT_PROPAGATION: dict[str, int] = {}


class Outcome:
    """What happened to one attribute. Strings, because they are printed and stored."""

    FINDING = "finding"
    """A disagreement that belongs in a reviewer's queue."""

    RESOLVED = "resolved"
    """Checked, and the catalog is supported -- including 316 SS against A4. Recorded, not shown."""

    DECLINED = "declined"
    """Not audited, with exactly one machine-readable reason (FR-6.2)."""

    NOT_IN_FEED = "not_in_feed"
    """The class declares this attribute and the catalog has no column for it.

    Deliberately not a finding and deliberately not hidden. A missing *column* is a schema gap in
    the feed; a blank *cell* is a fill-rate defect in the data. Collapsing the two would let an
    audit manufacture thousands of SEV-2 findings out of a customer's decision not to send a field.
    """


@dataclass(frozen=True, slots=True)
class AttributeOutcome:
    """One attribute of one SKU, from ingest to verdict."""

    attribute: AuditAttribute
    outcome: str
    catalog_value: str | None
    derivation: Derivation | None = None
    comparison: Comparison | None = None
    redline: Redline | None = None
    declined_reason: DeclinedReason | None = None
    detail: str = ""
    confidence: Confidence = field(default_factory=Confidence)

    @property
    def derived_value(self) -> str | None:
        return self.derivation.value if self.derivation else None

    @property
    def claim(self) -> Claim | None:
        return self.derivation.claim if self.derivation else None

    @property
    def abstention(self) -> Abstention | None:
        return self.derivation.abstention if self.derivation else None

    @property
    def severity(self) -> Severity:
        return self.redline.severity if self.redline else Severity.NONE


@dataclass(frozen=True, slots=True)
class SkuAudit:
    """The audit of one catalog record against one document."""

    record: CatalogRecord
    document: DocumentSource
    resolution: ClassResolution
    outcomes: tuple[AttributeOutcome, ...]
    class_uri: str = ""
    layout_version: str = LAYOUT_VERSION
    tables_version: str = TABLES_VERSION
    derive_version: str = DERIVE_VERSION

    @property
    def findings(self) -> tuple[AttributeOutcome, ...]:
        """The queue, ranked by expected review value -- P(wrong) x blast radius (§5.1).

        Not by confidence. The reviewer's next thirty seconds should go where they are worth the
        most, which is not the same place as where the model is surest.
        """
        found = [o for o in self.outcomes if o.outcome == Outcome.FINDING and o.redline]
        return tuple(
            sorted(
                found,
                key=lambda o: (-(o.redline.expected_review_value if o.redline else 0.0), o.attribute.key),
            )
        )

    @property
    def resolved(self) -> tuple[AttributeOutcome, ...]:
        return tuple(o for o in self.outcomes if o.outcome == Outcome.RESOLVED)

    @property
    def declined(self) -> tuple[AttributeOutcome, ...]:
        return tuple(o for o in self.outcomes if o.outcome == Outcome.DECLINED)

    @property
    def not_in_feed(self) -> tuple[AttributeOutcome, ...]:
        return tuple(o for o in self.outcomes if o.outcome == Outcome.NOT_IN_FEED)

    @property
    def audited(self) -> tuple[AttributeOutcome, ...]:
        """Attributes on which the audit committed to an answer -- the coverage denominator."""
        return tuple(
            o for o in self.outcomes if o.outcome in {Outcome.FINDING, Outcome.RESOLVED}
        )

    @property
    def coverage(self) -> float:
        considered = [o for o in self.outcomes if o.outcome != Outcome.NOT_IN_FEED]
        return len(self.audited) / len(considered) if considered else 0.0


@dataclass(frozen=True, slots=True)
class AuditRun:
    """One invocation of the audit over one or more records."""

    skus: tuple[SkuAudit, ...]
    policy_version: str
    attribute_map_version: str
    etim_release: str
    etim_attribution: str
    calibration_set_id: str = ""
    calibration_method: str = ""
    started_utc: datetime = field(default_factory=lambda: datetime.now(UTC))
    audit_version: str = AUDIT_VERSION
    notes: tuple[str, ...] = ()

    @property
    def findings(self) -> tuple[AttributeOutcome, ...]:
        found = [o for sku in self.skus for o in sku.findings]
        return tuple(
            sorted(
                found,
                key=lambda o: -(o.redline.expected_review_value if o.redline else 0.0),
            )
        )

    @property
    def declined(self) -> tuple[AttributeOutcome, ...]:
        return tuple(o for sku in self.skus for o in sku.declined)

    @property
    def resolved(self) -> tuple[AttributeOutcome, ...]:
        return tuple(o for sku in self.skus for o in sku.resolved)

    @property
    def coverage(self) -> float:
        considered = [
            o for sku in self.skus for o in sku.outcomes if o.outcome != Outcome.NOT_IN_FEED
        ]
        audited = [o for o in considered if o.outcome in {Outcome.FINDING, Outcome.RESOLVED}]
        return len(audited) / len(considered) if considered else 0.0

    def declined_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for outcome in self.declined:
            key = outcome.declined_reason.value if outcome.declined_reason else "unspecified"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def risk_coverage(self) -> tuple[RiskCoveragePoint, ...]:
        """FR-6.3, computed over this run's own findings.

        "Correct" here means a finding the reviewer accepted. Before adjudication there is nothing
        to be right or wrong about, so a run with no decisions returns an empty curve rather than
        a flattering one built from the audit grading its own homework.
        """
        scored = [
            (
                outcome.confidence.calibrated_p
                if outcome.confidence.calibrated_p is not None
                else (outcome.confidence.raw_score or 0.0),
                outcome.redline.adjudication.decision.value == "accept_redline",
            )
            for outcome in self.findings
            if outcome.redline is not None and outcome.redline.adjudication is not None
        ]
        return risk_coverage_curve(scored)

    def aurc(self) -> float | None:
        curve = self.risk_coverage()
        return aurc(curve) if curve else None


def audit_sku(
    record: CatalogRecord,
    document: DocumentSource,
    *,
    etim: EtimModel,
    scope: ClassScope,
    attributes: AttributeMap | None = None,
    calibration: CalibrationModel | None = None,
    policy: ResolutionPolicy | None = None,
    layer: TextLayer | None = None,
    tables: Sequence[Table] | None = None,
    propagation: dict[str, int] | None = None,
) -> SkuAudit:
    """Audit one catalog record against one source document."""
    attributes = attributes or load_attributes()
    policy = policy or builtin_policy()
    propagation = propagation if propagation is not None else DEFAULT_PROPAGATION

    layer = layer if layer is not None else extract_layer(document.path, document_sha256=document.sha256)
    table_set = (
        tuple(tables)
        if tables is not None
        else extract_tables(document.path, document_sha256=document.sha256)
    )

    carried = tuple(
        attribute.etim_feature
        for attribute in attributes
        if attribute.etim_feature and record.value(attribute.key) is not None
    )
    resolution = resolve_class(
        _class_query(record), etim, scope=scope, attribute_features=carried
    )
    klass = etim.get(resolution.class_id) if resolution.class_id else None
    class_uri = klass.uri(etim.release) if klass else ""

    if klass is None:
        # No schema, so no attribute can be judged. Every attribute the feed carries is declined
        # with the resolver's own reason -- visibly, one row each, rather than the record silently
        # disappearing from the run.
        outcomes = tuple(
            AttributeOutcome(
                attribute=attribute,
                outcome=Outcome.DECLINED,
                catalog_value=record.value(attribute.key),
                declined_reason=resolution.declined_reason or DeclinedReason.CLASS_UNRESOLVED,
                detail=resolution.detail,
            )
            for attribute in attributes
            if record.value(attribute.key) is not None
        )
        return SkuAudit(
            record=record,
            document=document,
            resolution=resolution,
            outcomes=outcomes,
            class_uri="",
        )

    outcomes = []
    for attribute in attributes.for_class(klass.class_id):
        catalog_value = record.value(attribute.key)
        if catalog_value is None:
            outcomes.append(
                AttributeOutcome(
                    attribute=attribute,
                    outcome=Outcome.NOT_IN_FEED,
                    catalog_value=None,
                    detail=(
                        f"{klass.description} declares this attribute and the feed has no column "
                        "for it. A missing column is a schema gap, not a data defect."
                    ),
                )
            )
            continue

        derivation = derive(
            layer,
            table_set,
            mpn=record.mpn or record.sku_id,
            attribute=attribute,
            klass=klass,
            sku_id=record.sku_id,
            doc_id=document.doc_id,
            revision_sha256=document.sha256,
            class_uri=class_uri,
        )
        outcomes.append(
            _judge(
                record=record,
                document=document,
                layer=layer,
                attribute=attribute,
                catalog_value=catalog_value,
                derivation=derivation,
                calibration=calibration,
                policy=policy,
                propagation=propagation,
            )
        )

    return SkuAudit(
        record=record,
        document=document,
        resolution=resolution,
        outcomes=tuple(outcomes),
        class_uri=class_uri,
    )


def _judge(
    *,
    record: CatalogRecord,
    document: DocumentSource,
    layer: TextLayer,
    attribute: AuditAttribute,
    catalog_value: str,
    derivation: Derivation,
    calibration: CalibrationModel | None,
    policy: ResolutionPolicy,
    propagation: dict[str, int],
) -> AttributeOutcome:
    if derivation.abstention is not None:
        return AttributeOutcome(
            attribute=attribute,
            outcome=Outcome.DECLINED,
            catalog_value=catalog_value,
            derivation=derivation,
            declined_reason=derivation.abstention.reason,
            detail=derivation.abstention.detail,
        )

    comparison = compare_attribute(attribute.to_spec(), catalog_value, derivation.value)

    if comparison.is_declined:
        return AttributeOutcome(
            attribute=attribute,
            outcome=Outcome.DECLINED,
            catalog_value=catalog_value,
            derivation=derivation,
            comparison=comparison,
            declined_reason=comparison.declined_reason
            or DeclinedReason.VALUE_OUTSIDE_KNOWN_GRAMMAR,
            detail=comparison.rationale,
        )

    confidence = calibrate(derivation.raw_score, calibration)

    if not comparison.raises_finding:
        # Agreement, unit-frame mismatch and semantic equivalence all land here, and none of them
        # reaches a reviewer. FR-5.3 -- "semantic equivalence must not flag" -- is the single
        # highest-consequence requirement in the PRD, and this is where it is honoured: not by
        # suppressing a rendered row, but by never constructing a redline at all.
        return AttributeOutcome(
            attribute=attribute,
            outcome=Outcome.RESOLVED,
            catalog_value=catalog_value,
            derivation=derivation,
            comparison=comparison,
            detail=comparison.rationale,
            confidence=confidence,
        )

    if confidence.abstained:
        return AttributeOutcome(
            attribute=attribute,
            outcome=Outcome.DECLINED,
            catalog_value=catalog_value,
            derivation=derivation,
            comparison=comparison,
            declined_reason=DeclinedReason.CALIBRATION_OUT_OF_DISTRIBUTION,
            detail=(
                f"the raw score {derivation.raw_score:.3f} falls outside the calibration set's "
                "support, so no defensible probability can be attached to this disagreement; it "
                "is held back rather than ranked on a number nobody can check"
            ),
            confidence=confidence,
        )

    counter = find_counter_evidence(
        layer,
        catalog_value=catalog_value,
        mpn=record.mpn or record.sku_id,
        doc_id=document.doc_id,
        revision_sha256=document.sha256,
    )

    redline = build_redline(
        comparison,
        evidence=derivation.evidence,
        counter_evidence=counter,
        propagation_count=propagation.get(attribute.key, 0),
        probability_catalog_wrong=confidence.calibrated_p,
    )
    assert redline is not None  # raises_finding was checked above; kept as a contract, not a guess

    # Re-validated rather than copied: `model_copy(update=...)` skips pydantic's validators, and
    # `Redline` is where the "semantic equivalence never becomes a redline" and safety-class rules
    # live. A copy that skips them is a copy that can hold a state the constructor would refuse.
    redline = _revalidate(
        redline,
        {
            "redline_id": stable_redline_id(
                document_sha256=document.sha256,
                sku_id=record.sku_id,
                attribute_uri=attribute.uri,
                catalog_value=catalog_value,
                proposed_value=derivation.value or "",
            ),
            "sku_id": record.sku_id,
            "mpn": record.mpn,
            "class_uri": derivation.claim.class_uri if derivation.claim else "",
            "proposed_claim_id": derivation.claim.claim_id if derivation.claim else None,
            "rationale": _rationale(comparison, derivation, policy),
        },
    )

    return AttributeOutcome(
        attribute=attribute,
        outcome=Outcome.FINDING,
        catalog_value=catalog_value,
        derivation=derivation,
        comparison=comparison,
        redline=redline,
        detail=comparison.rationale,
        confidence=confidence,
    )


#: Namespace for :func:`stable_redline_id`. A fixed UUID, generated once and written down, because
#: a namespace that changed would silently change every redline's identity.
REDLINE_NAMESPACE = uuid.UUID("6f3a1b2c-9d4e-5a6b-8c7d-0e1f2a3b4c5d")


def stable_redline_id(
    *,
    document_sha256: str,
    sku_id: str,
    attribute_uri: str,
    catalog_value: str,
    proposed_value: str,
) -> uuid.UUID:
    """A redline's identity, derived from its content rather than from when it was created.

    **This began as a usability bug and turned out to be a correctness one.** With a random id, the
    adjudication command the CLI prints stopped working the moment the audit was re-run, because the
    same finding came back with a new id -- and a reviewer's decision would then attach to a redline
    nobody could reproduce. Worse, a ledger accumulating one row per run per finding makes "has this
    been decided?" unanswerable.

    Content addressing is already how this repository identifies documents (``sha256`` of the
    bytes), and the same reasoning applies here: two runs over the same document, the same catalog
    value and the same re-derived value are **the same finding**, and should say so. Change any of
    those five things and it is a different finding with a different id, which is correct -- a
    supplier revising the datasheet, or the catalog being edited, genuinely does produce a new
    finding that deserves its own decision.
    """
    key = "|".join(
        (document_sha256, sku_id, attribute_uri, catalog_value, proposed_value)
    )
    return uuid.uuid5(REDLINE_NAMESPACE, key)


def _revalidate(redline: Redline, update: dict) -> Redline:
    """Apply an update and run the model's validators over the result.

    Pydantic's ``model_copy(update=...)`` deliberately skips validation, which is fine for a data
    holder and wrong for this one: ``Redline`` is where "semantic equivalence never becomes a
    redline" and the safety-class two-signature rule are enforced.
    """
    return Redline.model_validate(redline.model_copy(update=update).model_dump())


def _rationale(comparison: Comparison, derivation: Derivation, policy: ResolutionPolicy) -> str:
    """Deterministic prose, safe to show verbatim -- no model wrote this sentence.

    It names the policy that would govern the conflict and, for a safety-class attribute, says out
    loud that the policy will not resolve it automatically at any confidence (§4.2, ADR-001). A
    reviewer should never have to find that out from documentation.
    """
    parts = [comparison.rationale.strip().rstrip(".") + "."]
    if derivation.method == "table_cell":
        parts.append(
            "The value was read from the table cell whose row is this product and whose column is "
            "the mapped header; both are boxed."
        )
    elif derivation.method == "text_window":
        parts.append(
            "The value was read from running text near this product's type designation, not from "
            "a resolved table cell -- weaker evidence, and the confidence reflects it."
        )
    if policy.escalates(comparison.attribute.key):
        parts.append(
            f"Policy {policy.version_tag} never resolves this attribute automatically, at any "
            "confidence: acceptance needs a second named adjudicator (FR-8.9)."
        )
    return " ".join(parts)


def _class_query(record: CatalogRecord) -> str:
    """What class resolution is allowed to see.

    Identity and description only. The values under audit are deliberately excluded: a resolver
    that read them would be choosing the schema that makes those values look correct, and every
    subsequent judgment would be conditioned on the answer.
    """
    descriptive = " ".join(
        value
        for key, value in record.attributes.items()
        if key.strip().lower() in {"description", "product_name", "name", "short_description"}
    )
    return " ".join(part for part in (record.manufacturer, record.mpn, descriptive) if part).strip()


def find_document_for(record: CatalogRecord, documents: Sequence[DocumentSource]) -> DocumentSource | None:
    """Pick the document a record points at, or the only one available.

    Returns ``None`` rather than a default when a record names a datasheet nobody supplied: the
    correct outcome is ``no_source_document`` in the Declined bucket, and quietly auditing against
    a different manufacturer's PDF would be the worst failure this system could have.
    """
    if record.datasheet:
        wanted = Path(record.datasheet).name
        for document in documents:
            if wanted in {Path(document.source_url).name, document.doc_id, document.path.name}:
                return document
        return None
    return documents[0] if len(documents) == 1 else None
