"""FR-8.8 -- batch reversal, as a query.

    "Any audit batch's accepted redlines revert from the ledger as a query. Demonstrated on a
    1,000-record batch."

This is the commitment that makes an audit safe to accept in bulk, and SS4.3 states it plainly: a
customer who applies 1,000 of our corrections and then discovers our class resolution was wrong for
a family must be able to undo it *as a selection over stored facts*, not as a recovery project.

That requirement is what forces the ledger's shape. Because nothing was ever overwritten, the
values before the batch are still there; because every decision recorded its ``claim_id`` and its
``batch_id``, "everything this batch changed" is a filter rather than a re-derivation. A reversal
that had to re-run the audit to find out what it did would be re-deriving the thing it is meant to
undo, and would fail exactly when the audit itself was the problem.

**A reversal is an append, like everything else.** It writes a new claim, asserted by the human who
ordered the reversal, superseding the accepted one and restoring the catalog's original value. The
accepted claim stays readable forever: someone accepted it on evidence that was accurate at the
time, and deleting it would turn a defensible decision into an inexplicable gap.

**Reversal is idempotent.** Running it twice reverses nothing the second time, because the query
excludes claims a reversal already supersedes. That matters more than it sounds: the operator
reaching for this function is having a bad day, and a second attempt must not double-write.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from errata_audit import Ledger
from errata_spec import AsserterKind, Claim, Decision

__all__ = [
    "ReversalReport",
    "accepted_in_batch",
    "reverse_batch",
]


@dataclass(frozen=True, slots=True)
class AcceptedDecision:
    """One accepted redline, as the ledger recorded it."""

    batch_id: str
    redline_id: str
    sku_id: str
    attribute_uri: str
    claim_id: str
    catalog_value: str
    decided_value: str
    decided_by: str


@dataclass(frozen=True, slots=True)
class ReversalReport:
    """What a reversal did, and what it deliberately did not do."""

    batch_id: str
    accepted: int
    reversed_now: int
    already_reversed: int
    skus: int
    attributes: tuple[str, ...]
    reversed_by: str

    @property
    def is_complete(self) -> bool:
        return self.reversed_now + self.already_reversed == self.accepted

    def text(self) -> str:
        return (
            f"batch {self.batch_id}\n"
            f"  accepted redlines in batch   {self.accepted:,}\n"
            f"  reversed by this call        {self.reversed_now:,}\n"
            f"  already reversed             {self.already_reversed:,}\n"
            f"  distinct SKUs restored       {self.skus:,}\n"
            f"  attributes touched           {', '.join(self.attributes) or '(none)'}\n"
            f"  ordered by                   {self.reversed_by}"
        )


def accepted_in_batch(ledger: Ledger, batch_id: str) -> tuple[AcceptedDecision, ...]:
    """Every accepted redline of one batch. The query FR-8.8 is about."""
    batch = str(batch_id)
    out: list[AcceptedDecision] = []
    for event in ledger.of_kind("scale_decision"):
        payload = event.payload
        if str(payload.get("batch_id")) != batch:
            continue
        if payload.get("decision") != Decision.ACCEPT_REDLINE.value:
            continue
        out.append(
            AcceptedDecision(
                batch_id=batch,
                redline_id=str(payload.get("redline_id", "")),
                sku_id=str(payload.get("sku_id", "")),
                attribute_uri=str(payload.get("attribute_uri", "")),
                claim_id=str(payload.get("claim_id", "")),
                catalog_value=str(payload.get("catalog_value", "")),
                decided_value=str(payload.get("decided_value", "")),
                decided_by=str(payload.get("decided_by", "")),
            )
        )
    return tuple(out)


def _already_reversed(ledger: Ledger, batch_id: str) -> set[str]:
    return {
        str(event.payload.get("reversed_claim_id"))
        for event in ledger.of_kind("scale_reversal")
        if str(event.payload.get("batch_id")) == str(batch_id)
    }


def reverse_batch(
    ledger: Ledger,
    batch_id: str,
    *,
    reversed_by: str,
    reason: str = "",
    only: Sequence[str] | None = None,
) -> ReversalReport:
    """Reverse every accepted redline of a batch, by appending superseding claims.

    ``only`` narrows the reversal to specific redline ids -- the realistic case is one bad error
    signature rather than a whole run, and reversing more than was asked for would be its own
    incident.
    """
    accepted = accepted_in_batch(ledger, batch_id)
    if only is not None:
        wanted = {str(value) for value in only}
        accepted = tuple(item for item in accepted if item.redline_id in wanted)

    done = _already_reversed(ledger, batch_id)
    reversed_now = 0
    skus: set[str] = set()
    attributes: set[str] = set()

    for decision in accepted:
        if decision.claim_id in done:
            continue
        claim = Claim(
            sku_id=decision.sku_id,
            attribute_uri=decision.attribute_uri,
            value_raw=decision.catalog_value,
            asserter_kind=AsserterKind.HUMAN,
            supersedes=_as_uuid(decision.claim_id),
            # No evidence, deliberately. A reversal is not a claim that the catalog value is right;
            # it is a withdrawal of our assertion that it is wrong, and attaching the original
            # evidence would misdescribe it as a positive finding for the catalog.
            evidence=(),
        )
        ledger.append_claim(claim)
        ledger.append(
            "scale_reversal",
            {
                "batch_id": str(batch_id),
                "redline_id": decision.redline_id,
                "sku_id": decision.sku_id,
                "attribute_uri": decision.attribute_uri,
                "reversed_claim_id": decision.claim_id,
                "reversal_claim_id": str(claim.claim_id),
                "restored_value": decision.catalog_value,
                "withdrawn_value": decision.decided_value,
                "reversed_by": reversed_by,
                "reason": reason,
            },
        )
        reversed_now += 1
        skus.add(decision.sku_id)
        attributes.add(decision.attribute_uri)

    return ReversalReport(
        batch_id=str(batch_id),
        accepted=len(accepted),
        reversed_now=reversed_now,
        already_reversed=len(accepted) - reversed_now,
        skus=len(skus),
        attributes=tuple(sorted(attributes)),
        reversed_by=reversed_by,
    )


def _as_uuid(value: str):
    import uuid

    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None
