"""The comparator (§3.3).

Everything upstream of this component exists in some form on the market. This does not, and it is
where the product is won or lost.

Its job is not "are these two strings different" -- that question produces a false-positive
avalanche that ends the pilot in week one. Its job is to classify *how* they differ, and in
particular to recognise the cases that look like disagreements and are not:

    316 SS  /  A4  /  1.4401        one material, three vocabularies
    0.5 in  /  12.7 mm              one length, two frames
    M8      /  M8x1.25              one thread, one of them completed from ISO 261
    Threaded /  NPT 1/2-14          under-specified, not wrong
    10 mm   /  10 +/-0.2 mm         a dropped tolerance, not a contradiction

Two structural rules make the false-positive rate controllable, and both cost recall on purpose:

**Compare only in normalized space (FR-5.1).** No raw string comparison appears anywhere in the
decision path. If a value did not parse, it is not compared.

**A refusal abstains (FR-6.2).** The comparator would rather report "could not check" than invent a
finding out of a string it did not understand. Coverage is a number we publish; a fabricated
accusation is a customer we lose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from errata_spec import DeclinedReason, DisagreementClass, Severity
from errata_spec.taxonomy import CLASS_PROFILE
from errata_valuesem import (
    Kind,
    NormalizedValue,
    Refusal,
    RefusalReason,
    Relation,
    Verdict,
    normalize,
)
from errata_valuesem import compare as compare_values

__all__ = [
    "GRAMMAR_VERSION",
    "RELATION_TO_CLASS",
    "AttributeSpec",
    "Comparison",
    "classify",
    "compare_attribute",
]

GRAMMAR_VERSION = "comparator/1.0.0"


#: The mapping that turns a statement about two values into a statement about a catalog.
#:
#: ``a`` is always the catalog side and ``b`` always the evidence side, which is why the table is
#: asymmetric: ``A_MORE_SPECIFIC`` means the catalog is *more* precise than the datasheet, and that
#: is not a defect in the catalog.
RELATION_TO_CLASS: dict[Relation, DisagreementClass] = {
    Relation.EQUIVALENT: DisagreementClass.AGREEMENT,
    Relation.EQUIVALENT_UNIT_FRAME: DisagreementClass.UNIT_FRAME_MISMATCH,
    Relation.EQUIVALENT_VOCABULARY: DisagreementClass.SEMANTIC_EQUIVALENCE,
    Relation.A_MORE_SPECIFIC: DisagreementClass.AGREEMENT,
    Relation.B_MORE_SPECIFIC: DisagreementClass.GRANULARITY_MISMATCH,
    Relation.A_PRECISION_LOSS: DisagreementClass.PRECISION_MISMATCH,
    Relation.B_PRECISION_LOSS: DisagreementClass.AGREEMENT,
    Relation.CONTRADICTION: DisagreementClass.CONTRADICTION,
    Relation.INCOMPARABLE: DisagreementClass.UNDETERMINED,
}

#: Refusal reasons map straight onto Declined-bucket reasons. No refusal is dropped on the floor.
_REFUSAL_TO_DECLINED: dict[RefusalReason, DeclinedReason] = {
    RefusalReason.NO_GRAMMAR_MATCH: DeclinedReason.VALUE_OUTSIDE_KNOWN_GRAMMAR,
    RefusalReason.MALFORMED: DeclinedReason.VALUE_OUTSIDE_KNOWN_GRAMMAR,
    RefusalReason.UNKNOWN_UNIT: DeclinedReason.VALUE_OUTSIDE_KNOWN_GRAMMAR,
    RefusalReason.UNKNOWN_TERM: DeclinedReason.VALUE_OUTSIDE_KNOWN_GRAMMAR,
    RefusalReason.AMBIGUOUS_PARSE: DeclinedReason.VALUE_OUTSIDE_KNOWN_GRAMMAR,
    RefusalReason.EMPTY: DeclinedReason.VALUE_OUTSIDE_KNOWN_GRAMMAR,
}


@dataclass(frozen=True, slots=True)
class AttributeSpec:
    """What the resolved ETIM class says this attribute is.

    Supplying it is what lets ``316`` mean AISI 316 rather than the number three hundred and
    sixteen, and ``2`` mean two poles rather than the number two. Constrained decoding, not
    judgment (§3.4).
    """

    key: str
    """Stable attribute key or URI: ``rated_current``, ``etim:EF000094``."""

    label: str = ""
    kinds: tuple[Kind, ...] = ()
    """Kinds the class schema allows. Empty means "unconstrained", which is honest but weaker."""

    vocabulary: str = ""
    """Named value list for a TERM attribute."""

    uri: str = ""
    """The attribute's identity in the interoperable vocabulary: ``etim:EF000227``.

    **Finding N15, raised in R2 and fixed here in R3.** Before this field existed, a redline
    carried ``rated_current`` in ``attribute_uri`` while the id that named it was derived from
    ``etim:EF000227`` -- one attribute, two vocabularies, and nothing noticed until R2 started
    clustering across both. Empty means the caller supplied no interoperable id, and
    :meth:`attribute_uri` falls back to ``customer:<key>``: a local attribute says so rather than
    borrowing an ETIM id it does not have.
    """

    decimal_separator: str | None = None
    """Set per feed when the locale is known, so ``1,000`` resolves instead of refusing."""

    @property
    def expect(self) -> tuple[Kind, ...] | None:
        return self.kinds or None

    @property
    def attribute_uri(self) -> str:
        """The one string a redline, a claim and a cluster all key on (N15).

        Never the bare key. ``customer:`` is a real prefix with a real meaning -- this attribute
        is not in any published dictionary -- and a consumer that sees it knows the value is not
        comparable across catalogs.
        """
        if self.uri:
            return self.uri
        return f"customer:{self.key}"


@dataclass(frozen=True, slots=True)
class Comparison:
    """The comparator's output for one attribute of one SKU."""

    attribute: AttributeSpec
    catalog_raw: str
    evidence_raw: str

    disagreement_class: DisagreementClass
    severity: Severity
    rationale: str

    relation: Relation | None = None
    declined_reason: DeclinedReason | None = None
    catalog_value: NormalizedValue | None = None
    evidence_value: NormalizedValue | None = None
    catalog_refusal: Refusal | None = None
    evidence_refusal: Refusal | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    @property
    def raises_finding(self) -> bool:
        """True only for classes that belong in a reviewer's queue.

        Semantic equivalence and unit-frame mismatch resolve silently, agreement is not a finding,
        and undetermined goes to the Declined bucket. FR-5.3 is enforced here and asserted by test.
        """
        return CLASS_PROFILE[self.disagreement_class].raises_finding

    @property
    def is_declined(self) -> bool:
        return self.disagreement_class is DisagreementClass.UNDETERMINED


def compare_attribute(
    attribute: AttributeSpec,
    catalog_raw: str | None,
    evidence_raw: str | None,
) -> Comparison:
    """Compare one catalog value against one independently re-derived value.

    The re-derived value must have been produced without sight of the catalog value (FR-3.4). This
    function cannot enforce that -- it happens upstream -- but every agreement it reports is
    meaningless if that rule was broken, which is why the pipeline guards it with a test rather
    than a comment.
    """
    catalog_present = _is_present(catalog_raw)
    evidence_present = _is_present(evidence_raw)

    if not catalog_present and not evidence_present:
        return _declined(
            attribute,
            catalog_raw,
            evidence_raw,
            DeclinedReason.NO_SOURCE_DOCUMENT,
            "neither the catalog nor the evidence states a value for this attribute",
        )

    if not evidence_present:
        # A populated catalog field with nothing in the corpus behind it. The value may well be
        # right; the point is that it cannot be defended to an angry customer or a regulator.
        return Comparison(
            attribute=attribute,
            catalog_raw=catalog_raw or "",
            evidence_raw="",
            disagreement_class=DisagreementClass.UNSUPPORTED_VALUE,
            severity=CLASS_PROFILE[DisagreementClass.UNSUPPORTED_VALUE].default_severity,
            rationale=(
                f"the catalog states {catalog_raw!r} and no evidence in the corpus supports or "
                "refutes it; this record is undefendable rather than wrong"
            ),
        )

    if not catalog_present:
        return Comparison(
            attribute=attribute,
            catalog_raw="",
            evidence_raw=evidence_raw or "",
            disagreement_class=DisagreementClass.CATALOG_NULL_EVIDENCE_PRESENT,
            severity=CLASS_PROFILE[
                DisagreementClass.CATALOG_NULL_EVIDENCE_PRESENT
            ].default_severity,
            rationale=(
                f"the catalog field is blank and the source document states {evidence_raw!r}; "
                "this is a recoverable gap, not a contradiction"
            ),
        )

    catalog = normalize(
        catalog_raw or "",
        expect=attribute.expect,
        vocabulary=attribute.vocabulary or None,
        decimal_separator=attribute.decimal_separator,
    )
    evidence = normalize(
        evidence_raw or "",
        expect=attribute.expect,
        vocabulary=attribute.vocabulary or None,
        decimal_separator=attribute.decimal_separator,
    )

    if isinstance(catalog, Refusal) or isinstance(evidence, Refusal):
        refusal = catalog if isinstance(catalog, Refusal) else evidence
        assert isinstance(refusal, Refusal)
        return _declined(
            attribute,
            catalog_raw,
            evidence_raw,
            _REFUSAL_TO_DECLINED.get(
                refusal.reason, DeclinedReason.VALUE_OUTSIDE_KNOWN_GRAMMAR
            ),
            (
                "not audited: "
                + ("the catalog value " if isinstance(catalog, Refusal) else "the evidence value ")
                + f"{refusal.raw!r} did not parse ({refusal.reason.value}). {refusal.detail}"
            ),
            catalog_refusal=catalog if isinstance(catalog, Refusal) else None,
            evidence_refusal=evidence if isinstance(evidence, Refusal) else None,
        )

    verdict = compare_values(catalog, evidence)
    return classify(attribute, catalog, evidence, verdict)


def classify(
    attribute: AttributeSpec,
    catalog: NormalizedValue,
    evidence: NormalizedValue,
    verdict: Verdict,
) -> Comparison:
    """Turn a value-level verdict into a catalog-level disagreement class."""
    disagreement = RELATION_TO_CLASS[verdict.relation]

    # Packaging outranks every other reading of the same relation. A quantity mismatch in a
    # packaging frame is not "a contradiction" generically -- it is the specific error that prices
    # a line at a tenth of cost, and it is always SEV-1.
    if (
        disagreement is DisagreementClass.CONTRADICTION
        and catalog.kind is Kind.PACKAGING
        and evidence.kind is Kind.PACKAGING
    ):
        disagreement = DisagreementClass.PACKAGING_FRAME_ERROR

    severity = CLASS_PROFILE[disagreement].default_severity
    declined = (
        DeclinedReason.INCOMPARABLE_KINDS
        if disagreement is DisagreementClass.UNDETERMINED
        else None
    )

    return Comparison(
        attribute=attribute,
        catalog_raw=catalog.raw,
        evidence_raw=evidence.raw,
        disagreement_class=disagreement,
        severity=severity,
        rationale=verdict.rationale,
        relation=verdict.relation,
        declined_reason=declined,
        catalog_value=catalog,
        evidence_value=evidence,
        detail=dict(verdict.detail),
        notes=tuple(dict.fromkeys((*catalog.notes, *evidence.notes))),
    )


def _declined(
    attribute: AttributeSpec,
    catalog_raw: str | None,
    evidence_raw: str | None,
    reason: DeclinedReason,
    rationale: str,
    *,
    catalog_refusal: Refusal | None = None,
    evidence_refusal: Refusal | None = None,
) -> Comparison:
    return Comparison(
        attribute=attribute,
        catalog_raw=catalog_raw or "",
        evidence_raw=evidence_raw or "",
        disagreement_class=DisagreementClass.UNDETERMINED,
        severity=Severity.NONE,
        rationale=rationale,
        declined_reason=reason,
        catalog_refusal=catalog_refusal,
        evidence_refusal=evidence_refusal,
    )


def _is_present(value: str | None) -> bool:
    """Whether a field carries a value at all.

    Deliberately narrow: only whitespace and the null placeholders the canonicalizer already knows
    about count as absent. A field containing ``0`` is present, and treating it as blank would turn
    a stated zero into a missing value.
    """
    if value is None:
        return False
    from errata_valuesem.canonical import NULLISH

    return value.strip().lower() not in NULLISH
