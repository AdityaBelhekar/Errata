"""T0 -- the structural tier: everything that can be checked without a source document.

FR-8.7 tiers the run T0 -> T1 -> T2 -> T3 so that cost scales with *error* count rather than SKU
count. That only works if T0 is genuinely cheap and genuinely useful, and the interesting question
is what an auditor can honestly say about a record whose datasheet nobody has.

The answer is: quite a lot, as long as it never pretends to have read a document.

**Check 1 -- the feed against its own declared units.** The attribute map records the unit ETIM
declares for each feature. A ``rated_current`` cell holding ``0.125 kg`` is wrong without anyone
opening a PDF, because amperes and kilograms are not the same dimension. This fires rarely and it
is never a false positive.

**Check 2 -- the feed against itself.** Real catalogs list the same manufacturer part number more
than once: a regional SKU, a kitted SKU, a re-listed SKU. When two rows carrying the same MPN
disagree about a technical attribute, at least one of them is wrong and no external evidence is
needed to know it. This is the single most productive document-free check there is, and it is run
through :func:`errata_comparator.compare_attribute` rather than string equality -- so ``125 g`` and
``0.125 kg`` under one MPN resolve silently, which is FR-5.3 holding at T0 exactly as it holds at
T1.

**Check 3 -- blank against stated.** Same MPN, one row blank and the others filled: the fill-rate
finding, with the sibling row as the evidence.

Three rules keep this tier honest:

* **A minority does not lose by being a minority.** Where sibling values disagree with no majority,
  the policy's ``equal_rank_conflict`` rule applies -- two sources of identical rank, so the audit
  abstains and surfaces both (``equal_rank_source_conflict``) instead of picking the first one.
* **Every T0 finding cites a span.** Not of a datasheet -- of the feed, which is itself a
  hash-registered artifact (see :mod:`errata_scale.feedindex`). Nothing here relaxes the evidence
  rule to get a finding out of the door.
* **No T0 finding carries a probability.** There is no calibration set (FR-6.1 remains unmet), and
  a structural check's certainty is a different quantity from a calibrated P(catalog wrong)
  anyway. The triage router ranks these on blast radius, and the report says so.
"""

from __future__ import annotations

import enum
import functools
from collections.abc import Sequence
from dataclasses import dataclass

from errata_audit import AttributeMap, AuditAttribute, CatalogRecord, Outcome, load_attributes
from errata_comparator import Comparison, compare_attribute
from errata_spec import (
    CounterEvidence,
    DeclinedReason,
    DisagreementClass,
    Evidence,
    Redline,
    Severity,
)
from errata_valuesem import Kind, NormalizedValue, normalize
from errata_valuesem.unitreg import parse_unit, same_dimension

from .feedindex import FeedIndex

__all__ = [
    "STRUCTURAL_VERSION",
    "StructuralCheck",
    "StructuralOutcome",
    "StructuralResult",
    "run_structural",
]

STRUCTURAL_VERSION = "errata-structural/1.0.0"

#: A catalog of 10,000 rows holds far fewer distinct *values* than cells, and the comparator and
#: the normalizer are both pure functions of their inputs. Memoising them turns the tier from
#: linear in cells into linear in distinct value pairs, which is the difference between a run a
#: reviewer waits for and one they schedule. Both caches are keyed on the attribute as well as the
#: values, because an attribute's declared kinds change what a string means -- ``2`` is a pole
#: count here and a bare number there.
_CACHE_LIMIT = 200_000


@functools.lru_cache(maxsize=_CACHE_LIMIT)
def _compare_cached(spec: object, catalog: str, other: str) -> Comparison:
    return compare_attribute(spec, catalog, other)  # type: ignore[arg-type]


def _compare(attribute: AuditAttribute, catalog: str, other: str) -> Comparison:
    return _compare_cached(attribute.to_spec(), catalog, other)


class StructuralCheck(str, enum.Enum):
    """Which document-free check produced an outcome. Printed and stored."""

    UNIT_DIMENSION = "unit_dimension"
    SIBLING_AGREEMENT = "sibling_agreement"
    SIBLING_CONTRADICTION = "sibling_contradiction"
    SIBLING_FILL_GAP = "sibling_fill_gap"
    SIBLING_EQUAL_RANK = "sibling_equal_rank"
    NO_SIBLING = "no_sibling"

    @property
    def sentence(self) -> str:
        return {
            StructuralCheck.UNIT_DIMENSION: (
                "the value's dimension is not the dimension the class declares for this attribute"
            ),
            StructuralCheck.SIBLING_AGREEMENT: (
                "every row carrying this manufacturer part number states the same value"
            ),
            StructuralCheck.SIBLING_CONTRADICTION: (
                "rows carrying the same manufacturer part number state different values"
            ),
            StructuralCheck.SIBLING_FILL_GAP: (
                "this row is blank where other rows with the same part number state a value"
            ),
            StructuralCheck.SIBLING_EQUAL_RANK: (
                "sibling rows disagree with no majority; the policy declines to arbitrate"
            ),
            StructuralCheck.NO_SIBLING: (
                "nothing in the feed corroborates or contradicts this value"
            ),
        }[self]


@dataclass(frozen=True, slots=True)
class StructuralOutcome:
    """One attribute of one record, judged without a source document."""

    sku_id: str
    mpn: str
    row_number: int | None
    attribute: AuditAttribute
    check: StructuralCheck
    outcome: str
    catalog_value: str | None
    proposed_value: str = ""
    redline: Redline | None = None
    comparison: Comparison | None = None
    declined_reason: DeclinedReason | None = None
    detail: str = ""
    sibling_rows: tuple[int, ...] = ()

    @property
    def severity(self) -> Severity:
        return self.redline.severity if self.redline else Severity.NONE


@dataclass(frozen=True, slots=True)
class StructuralResult:
    """Everything T0 concluded, over the whole feed."""

    outcomes: tuple[StructuralOutcome, ...]
    records_examined: int
    attributes_examined: int
    feed_sha256: str = ""
    version: str = STRUCTURAL_VERSION

    @property
    def findings(self) -> tuple[StructuralOutcome, ...]:
        return tuple(o for o in self.outcomes if o.outcome == Outcome.FINDING and o.redline)

    @property
    def declined(self) -> tuple[StructuralOutcome, ...]:
        return tuple(o for o in self.outcomes if o.outcome == Outcome.DECLINED)

    @property
    def resolved(self) -> tuple[StructuralOutcome, ...]:
        return tuple(o for o in self.outcomes if o.outcome == Outcome.RESOLVED)

    def by_check(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for outcome in self.outcomes:
            counts[outcome.check.value] = counts.get(outcome.check.value, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def declined_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for outcome in self.declined:
            key = outcome.declined_reason.value if outcome.declined_reason else "unspecified"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def run_structural(
    records: Sequence[CatalogRecord],
    index: FeedIndex,
    *,
    attributes: AttributeMap | None = None,
) -> StructuralResult:
    """Run every document-free check over the whole feed.

    One pass to group by manufacturer part number, one pass per attribute per group. Linear in
    records x audited attributes: T0 is the only tier that touches every record, so it is the only
    tier whose cost is allowed to scale with catalog size.
    """
    attributes = attributes or load_attributes()
    audited = tuple(
        attribute
        for attribute in attributes
        # Every record, not a sample of the first few. A CSV has uniform columns and a sample would
        # be right for it; a JSON or YAML feed does not, and an attribute that first appears at row
        # 4,000 would then be dropped from the whole run -- a silent skip, which FR-6.2 forbids
        # outright. `any` short-circuits on the first record that carries the column, so the full
        # scan only costs anything for an attribute that is absent everywhere.
        if any(attribute.key in record.attributes for record in records)
    )

    outcomes: list[StructuralOutcome] = []

    for record in records:
        for attribute in audited:
            value = record.value(attribute.key)
            if value is None or not value.strip():
                continue
            mismatch = _unit_dimension_mismatch(attribute, value)
            if mismatch is None:
                continue
            outcomes.append(
                _dimension_finding(record, attribute, value, mismatch, index)
            )

    groups = _group_by_mpn(records)
    for (_manufacturer, _mpn), members in groups.items():
        for attribute in audited:
            outcomes.extend(_judge_group(members, attribute, index))

    return StructuralResult(
        outcomes=tuple(outcomes),
        records_examined=len(records),
        attributes_examined=len(audited),
        feed_sha256=index.sha256,
    )


# ------------------------------------------------------------------------------------------------
# check 1 -- declared unit versus stated dimension
# ------------------------------------------------------------------------------------------------


@functools.lru_cache(maxsize=_CACHE_LIMIT)
def _unit_dimension_mismatch(attribute: AuditAttribute, value: str) -> str | None:
    """Return the offending unit when the value's dimension is not the declared one.

    Silent (``None``) whenever anything is uncertain: no declared unit, a unit the registry cannot
    parse, a value that is not a quantity, or a dimensionless magnitude -- ``16`` under a column
    that never stated amperes is a grounding problem, not a dimensional one.
    """
    declared = (attribute.unit_from_header or "").strip()
    if not declared or Kind.QUANTITY not in (attribute.kinds or ()):
        return None
    try:
        declared_unit = parse_unit(declared)
    except Exception:
        return None
    if not declared_unit:
        return None

    parsed = normalize(value, expect=Kind.QUANTITY)
    if not isinstance(parsed, NormalizedValue) or parsed.kind is not Kind.QUANTITY:
        return None
    quantity = parsed.payload
    unit = getattr(quantity, "unit", "")
    if not unit:
        return None
    try:
        if same_dimension(unit, declared_unit):
            return None
    except Exception:
        return None
    return unit


def _dimension_finding(
    record: CatalogRecord,
    attribute: AuditAttribute,
    value: str,
    offending_unit: str,
    index: FeedIndex,
) -> StructuralOutcome:
    evidence = (
        index.evidence(
            row_number=record.row_number,
            column=attribute.key,
            row_header=record.sku_id,
        ),
    )
    redline = _redline(
        sku_id=record.sku_id,
        mpn=record.mpn,
        attribute=attribute,
        catalog_value=value,
        proposed_value="",
        disagreement_class=DisagreementClass.UNSUPPORTED_VALUE,
        severity=Severity.SEV2,
        evidence=evidence,
        counter_summary=(
            f"The feed states {value!r} for an attribute the class declares in "
            f"{attribute.unit_from_header!r}. Nothing in the feed supports it."
        ),
        rationale=(
            f"{attribute.label} is declared in {attribute.unit_from_header} and this row states "
            f"{value!r}, which is a {offending_unit} quantity. The two are not the same dimension, "
            "so the value cannot be a measurement of this attribute regardless of what any "
            "document says. No source document was read to reach this conclusion."
        ),
    )
    return StructuralOutcome(
        sku_id=record.sku_id,
        mpn=record.mpn,
        row_number=record.row_number,
        attribute=attribute,
        check=StructuralCheck.UNIT_DIMENSION,
        outcome=Outcome.FINDING,
        catalog_value=value,
        redline=redline,
        detail=StructuralCheck.UNIT_DIMENSION.sentence,
    )


# ------------------------------------------------------------------------------------------------
# checks 2 and 3 -- the feed against itself
# ------------------------------------------------------------------------------------------------


def _group_by_mpn(
    records: Sequence[CatalogRecord],
) -> dict[tuple[str, str], tuple[CatalogRecord, ...]]:
    """Records sharing a manufacturer part number, in feed order.

    Keyed on ``(manufacturer, mpn)`` and never on the manufacturer alone: two makers may use the
    same part number, and a cross-manufacturer "contradiction" would be an invented one. Records
    with no MPN form no group -- there is nothing to compare them to.
    """
    buckets: dict[tuple[str, str], list[CatalogRecord]] = {}
    for record in records:
        mpn = record.mpn.strip().lower()
        if not mpn:
            continue
        key = (record.manufacturer.strip().lower(), mpn)
        buckets.setdefault(key, []).append(record)
    return {key: tuple(value) for key, value in buckets.items() if len(value) > 1}


def _judge_group(
    members: Sequence[CatalogRecord],
    attribute: AuditAttribute,
    index: FeedIndex,
) -> list[StructuralOutcome]:
    stated = [(record, record.value(attribute.key)) for record in members]
    filled = [(record, value) for record, value in stated if value is not None and value.strip()]
    blank = [record for record, value in stated if value is not None and not value.strip()]
    if not filled:
        return []

    counts: dict[str, int] = {}
    for _record, value in filled:
        counts[value] = counts.get(value, 0) + 1

    modal_value, modal_count = max(counts.items(), key=lambda kv: (kv[1], _stability_key(kv[0])))
    runner_up = max(
        (count for value, count in counts.items() if value != modal_value), default=0
    )
    modal_record = next(record for record, value in filled if value == modal_value)
    rows = tuple(
        sorted({record.row_number for record, value in filled if value == modal_value and record.row_number})
    )

    outcomes: list[StructuralOutcome] = []

    for record in blank:
        outcomes.append(
            _fill_gap(record, modal_record, modal_value, modal_count, attribute, index, rows)
        )

    if len(counts) > 1 and modal_count <= runner_up and _any_real_disagreement(
        filled, modal_value, attribute
    ):
        # equal_rank_conflict (SS4.2): statements of identical evidentiary standing, and no
        # majority. The policy abstains and surfaces *both*, so every member of the group is
        # recorded -- surfacing only the minority would be picking a winner by omission.
        detail = (
            "sibling rows state "
            + ", ".join(f"{value!r} x{count}" for value, count in sorted(counts.items()))
            + ". All are rows of the same feed, so none outranks another; policy rule "
            "equal_rank_conflict declines to arbitrate and surfaces every value."
        )
        return outcomes + [
            _declined(
                record,
                attribute,
                value,
                StructuralCheck.SIBLING_EQUAL_RANK,
                DeclinedReason.EQUAL_RANK_SOURCE_CONFLICT,
                detail,
                rows,
            )
            for record, value in filled
        ]

    if len(counts) == 1:
        for record, value in filled:
            outcomes.append(
                StructuralOutcome(
                    sku_id=record.sku_id,
                    mpn=record.mpn,
                    row_number=record.row_number,
                    attribute=attribute,
                    check=StructuralCheck.SIBLING_AGREEMENT,
                    outcome=Outcome.RESOLVED,
                    catalog_value=value,
                    detail=(
                        f"{modal_count} row(s) under this part number state {value!r} and none "
                        "state anything else."
                    ),
                    sibling_rows=rows,
                )
            )
        return outcomes

    for record, value in filled:
        if value == modal_value:
            continue
        comparison = _compare(attribute, value, modal_value)
        if comparison.is_declined:
            outcomes.append(
                _declined(
                    record,
                    attribute,
                    value,
                    StructuralCheck.SIBLING_CONTRADICTION,
                    comparison.declined_reason or DeclinedReason.VALUE_OUTSIDE_KNOWN_GRAMMAR,
                    comparison.rationale,
                    rows,
                    comparison,
                )
            )
            continue
        if not comparison.raises_finding:
            outcomes.append(
                StructuralOutcome(
                    sku_id=record.sku_id,
                    mpn=record.mpn,
                    row_number=record.row_number,
                    attribute=attribute,
                    check=StructuralCheck.SIBLING_AGREEMENT,
                    outcome=Outcome.RESOLVED,
                    catalog_value=value,
                    comparison=comparison,
                    detail=(
                        f"{value!r} and the sibling rows' {modal_value!r} are the same value: "
                        f"{comparison.rationale}"
                    ),
                    sibling_rows=rows,
                )
            )
            continue

        evidence = (
            index.evidence(
                row_number=modal_record.row_number,
                column=attribute.key,
                row_header=modal_record.sku_id,
            ),
        )
        redline = _redline(
            sku_id=record.sku_id,
            mpn=record.mpn,
            attribute=attribute,
            catalog_value=value,
            proposed_value=modal_value,
            disagreement_class=comparison.disagreement_class,
            severity=comparison.severity,
            evidence=evidence,
            counter_summary=(
                f"{counts[value]} row(s) in this feed state {value!r}; no source document was "
                "read, so nothing outside the feed supports either value."
            ),
            rationale=(
                f"{modal_count} row(s) carrying part number {record.mpn!r} state {modal_value!r} "
                f"for {attribute.label}, and this row states {value!r}. "
                f"{comparison.rationale.strip().rstrip('.')}. The disagreement is inside the feed "
                "itself; no source document was consulted, and the proposed value is what the "
                "other rows say rather than what any manufacturer document says."
            ),
            record_multiplicity=1,
        )
        outcomes.append(
            StructuralOutcome(
                sku_id=record.sku_id,
                mpn=record.mpn,
                row_number=record.row_number,
                attribute=attribute,
                check=StructuralCheck.SIBLING_CONTRADICTION,
                outcome=Outcome.FINDING,
                catalog_value=value,
                proposed_value=modal_value,
                redline=redline,
                comparison=comparison,
                detail=StructuralCheck.SIBLING_CONTRADICTION.sentence,
                sibling_rows=rows,
            )
        )

    return outcomes


def _any_real_disagreement(
    filled: Sequence[tuple[CatalogRecord, str]],
    modal_value: str,
    attribute: AuditAttribute,
) -> bool:
    """True when at least one sibling genuinely contradicts the modal value.

    Without this, a group holding ``0.125 kg`` and ``125 g`` once each would be declined as an
    equal-rank conflict -- the tie is real, but there is nothing to arbitrate, because the two
    rows say the same thing. FR-5.3 again: equivalence is not disagreement, at any tier.
    """
    for _record, value in filled:
        if value == modal_value:
            continue
        comparison = _compare(attribute, value, modal_value)
        if comparison.raises_finding:
            return True
    return False


def _fill_gap(
    record: CatalogRecord,
    modal_record: CatalogRecord,
    modal_value: str,
    modal_count: int,
    attribute: AuditAttribute,
    index: FeedIndex,
    rows: tuple[int, ...],
) -> StructuralOutcome:
    evidence = (
        index.evidence(
            row_number=modal_record.row_number,
            column=attribute.key,
            row_header=modal_record.sku_id,
        ),
    )
    redline = _redline(
        sku_id=record.sku_id,
        mpn=record.mpn,
        attribute=attribute,
        catalog_value="",
        proposed_value=modal_value,
        disagreement_class=DisagreementClass.CATALOG_NULL_EVIDENCE_PRESENT,
        severity=Severity.SEV2,
        evidence=evidence,
        counter_summary=(
            "The row is blank; nothing supports a blank, and nothing outside the feed was read."
        ),
        rationale=(
            f"This row leaves {attribute.label} blank while {modal_count} row(s) carrying the same "
            f"part number state {modal_value!r}. A blank cell in a feed that carries the column is "
            "a fill-rate defect, not a schema gap."
        ),
    )
    return StructuralOutcome(
        sku_id=record.sku_id,
        mpn=record.mpn,
        row_number=record.row_number,
        attribute=attribute,
        check=StructuralCheck.SIBLING_FILL_GAP,
        outcome=Outcome.FINDING,
        catalog_value="",
        proposed_value=modal_value,
        redline=redline,
        detail=StructuralCheck.SIBLING_FILL_GAP.sentence,
        sibling_rows=rows,
    )


def _declined(
    record: CatalogRecord,
    attribute: AuditAttribute,
    value: str,
    check: StructuralCheck,
    reason: DeclinedReason,
    detail: str,
    rows: tuple[int, ...],
    comparison: Comparison | None = None,
) -> StructuralOutcome:
    return StructuralOutcome(
        sku_id=record.sku_id,
        mpn=record.mpn,
        row_number=record.row_number,
        attribute=attribute,
        check=check,
        outcome=Outcome.DECLINED,
        catalog_value=value,
        comparison=comparison,
        declined_reason=reason,
        detail=detail,
        sibling_rows=rows,
    )


def _redline(
    *,
    sku_id: str,
    mpn: str,
    attribute: AuditAttribute,
    catalog_value: str,
    proposed_value: str,
    disagreement_class: DisagreementClass,
    severity: Severity,
    evidence: tuple[Evidence, ...],
    counter_summary: str,
    rationale: str,
    record_multiplicity: int = 1,
) -> Redline:
    """Materialise a T0 redline through the same constructor R1 uses.

    :func:`errata_comparator.build_redline` is not used here because it derives its class and
    severity from a :class:`~errata_comparator.Comparison`, and two of the three T0 checks have no
    comparison to derive them from. The safety multiplier is applied identically, and ``Redline``
    itself still refuses any class that raises no finding -- so the rule that keeps semantic
    equivalence out of the queue is enforced on this path too.
    """
    from errata_comparator.redline import SAFETY_MULTIPLIER
    from errata_spec import BlastRadius, is_safety_class

    from .ids import structural_redline_id

    safety = is_safety_class(attribute.key) or is_safety_class(attribute.label)
    return Redline(
        redline_id=structural_redline_id(
            feed_sha256=evidence[0].doc_revision_sha256 if evidence else "",
            sku_id=sku_id,
            attribute_uri=attribute.uri,
            catalog_value=catalog_value,
            proposed_value=proposed_value,
        ),
        sku_id=sku_id,
        mpn=mpn,
        # **The canonical uri, and now so does R1** -- this line is half of finding N15's fix.
        # It used to read `attribute.key`, matching `errata_comparator.build_redline`, which had
        # no ETIM id to set the field from. Both now write `AttributeSpec.attribute_uri`, so a
        # structural finding and a grounded finding about the same attribute land in one cluster
        # instead of two. What this moves and what it does not is measured in docs/R3-report.md:
        # redline ids are unchanged (both id functions already hashed the uri), signature
        # fingerprints do move, and no adjudication keys on a fingerprint.
        attribute_uri=attribute.uri,
        attribute_label=attribute.label,
        catalog_value=catalog_value,
        proposed_value=proposed_value,
        disagreement_class=disagreement_class,
        severity=severity,
        evidence=evidence,
        counter_evidence=CounterEvidence(
            supporting=(),
            independent=False,
            summary=counter_summary,
        ),
        blast_radius=BlastRadius(
            revenue_weight=1.0,
            safety_class_multiplier=SAFETY_MULTIPLIER if safety else 1.0,
            propagation_count=0,
            record_multiplicity=record_multiplicity,
        ),
        probability_catalog_wrong=None,
        rationale=rationale,
    )


def _stability_key(value: str) -> tuple[int, str]:
    """Tie-break for the modal value: the shortest string, then the lexicographically last.

    Any deterministic rule would do; what matters is that it is not "whichever row came first",
    because feed order is an accident of export and a finding that changes when a customer
    re-sorts their spreadsheet is not reproducible (NFR-1).
    """
    return (-len(value), value)
