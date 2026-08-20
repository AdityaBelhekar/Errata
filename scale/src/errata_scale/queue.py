"""The drainable ranked queue -- R2's exit criterion, and the only surface a reviewer touches.

    PRD SS4, R2: "full audit of a 10k+ SKU public catalog subset **with a drainable ranked queue**".

*Drainable* is a stronger word than it looks and it is worth being precise about what this module
has to guarantee, because three plausible implementations fail it:

* **Every entry can be decided.** A queue containing rows that cannot be actioned -- no evidence,
  no adjudicable proposal, a safety-class row nobody is authorised to sign -- does not drain, it
  stalls. Safety-class rows are decidable here, with two named signatures (FR-8.9); the queue
  refuses the decision rather than the row.
* **A decision persists and is not re-offered.** This is why redline ids are content-addressed
  (R1 finding N14). Re-running the audit over the same feed produces the same ids, so a queue
  rebuilt tomorrow shows yesterday's decisions as decided rather than starting again -- which is
  what makes draining a 6,000-row queue across a week possible at all.
* **Progress is monotone and countable.** ``progress()`` reads the ledger, not memory. If the
  process dies mid-review, the count is still right.

Nothing here mutates. A decision is an append: an ``adjudication``, the human claim it asserts, and
a ``scale_decision`` event tying both to the batch so FR-8.8's reversal can find them as a query.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from errata_audit import Ledger
from errata_spec import Adjudication, Claim, Decision, Redline, is_safety_class

from .triage import QueueEntry, TriageResult

__all__ = [
    "DrainReport",
    "ReviewQueue",
    "SecondAdjudicatorRequired",
]


class SecondAdjudicatorRequired(ValueError):
    """FR-8.9 -- a safety-class acceptance was attempted with one signature.

    Raised before anything is written. The schema would refuse the redline anyway; failing here
    means the ledger never receives a half-formed decision, and the reviewer gets a sentence rather
    than a validation error.
    """


@dataclass(frozen=True, slots=True)
class DrainReport:
    """What one drain pass did."""

    decided: int
    accepted: int
    kept_catalog: int
    escalated: int
    skipped: int
    remaining: int

    def text(self) -> str:
        return (
            f"decided {self.decided:,} - accepted {self.accepted:,}, kept catalog "
            f"{self.kept_catalog:,}, escalated {self.escalated:,}, skipped {self.skipped:,}; "
            f"{self.remaining:,} remaining"
        )


class ReviewQueue:
    """A ranked queue over one batch, backed by an append-only ledger."""

    def __init__(self, triage: TriageResult, *, ledger: Ledger, batch_id: str) -> None:
        self.triage = triage
        self.ledger = ledger
        self.batch_id = str(batch_id)
        self._by_id = {entry.redline_id: entry for entry in triage.entries}

    # -- reading -----------------------------------------------------------------------------

    def decided_ids(self) -> frozenset[str]:
        """Redline ids already decided in this batch, read from the ledger every time.

        Not cached: the point of reading it fresh is that two reviewers on one ledger, or a rerun
        after a crash, see the same answer.
        """
        return frozenset(
            str(event.payload.get("redline_id"))
            for event in self.ledger.of_kind("scale_decision")
            if str(event.payload.get("batch_id")) == self.batch_id
        )

    @property
    def total(self) -> int:
        return len(self.triage.entries)

    def open_entries(self) -> tuple[QueueEntry, ...]:
        decided = self.decided_ids()
        return tuple(entry for entry in self.triage.entries if entry.redline_id not in decided)

    def progress(self) -> tuple[int, int]:
        """``(decided, total)``. Monotone across restarts, because it is a ledger query."""
        return (self.total - len(self.open_entries()), self.total)

    def entry(self, redline_id: str) -> QueueEntry | None:
        return self._by_id.get(str(redline_id))

    # -- writing -----------------------------------------------------------------------------

    def decide(
        self,
        entry: QueueEntry | str,
        *,
        decision: Decision,
        decided_by: str,
        second_adjudicator: str = "",
        note: str = "",
        seconds_to_decision: float | None = None,
        evidence_accepted: bool | None = None,
    ) -> tuple[Adjudication, Claim]:
        """Record one decision. Three appends, no updates.

        The safety-class check runs *before* the ledger is touched. ``Redline`` enforces the same
        rule, so this is belt and braces on purpose: FR-8.9 says single-signature acceptance must be
        impossible, and "impossible" should not rest on a single validator.
        """
        resolved = entry if isinstance(entry, QueueEntry) else self.entry(entry)
        if resolved is None:
            raise KeyError(
                f"redline {entry!r} is not in this batch. A decision addressed to a finding the "
                "queue does not contain would be unattributable."
            )
        redline: Redline = resolved.redline

        if redline.requires_two_signatures and not second_adjudicator:
            raise SecondAdjudicatorRequired(
                f"{redline.attribute_uri} on {redline.sku_id} is a safety-class attribute. "
                "Acceptance needs a second named adjudicator (FR-8.9, ADR-001): pass "
                "second_adjudicator. This is not a threshold that can be raised under deadline "
                "pressure -- the attribute list is the whole rule."
            )

        adjudication, claim = self.ledger.adjudicate(
            redline,
            decision=decision,
            decided_by=decided_by,
            note=note,
            seconds_to_decision=seconds_to_decision,
            evidence_accepted=evidence_accepted,
            second_adjudicator=second_adjudicator,
            raw_score=redline.probability_catalog_wrong,
        )
        self.ledger.append(
            "scale_decision",
            {
                "batch_id": self.batch_id,
                "redline_id": str(redline.redline_id),
                "sku_id": redline.sku_id,
                "attribute_uri": redline.attribute_uri,
                "decision": decision.value,
                "decided_by": decided_by,
                "second_adjudicator": second_adjudicator,
                "claim_id": str(claim.claim_id),
                "superseded_claim_id": str(claim.supersedes) if claim.supersedes else "",
                "catalog_value": redline.catalog_value,
                "decided_value": claim.value_raw,
                "seconds_to_decision": seconds_to_decision,
                "evidence_accepted": evidence_accepted,
                "tier": resolved.tier,
                "signature_id": resolved.signature_id,
                "expected_review_value": round(resolved.expected_review_value, 6),
            },
        )
        return adjudication, claim

    def drain(
        self,
        decider: Callable[[QueueEntry], tuple[Decision, str, str] | None],
        *,
        limit: int = 0,
        seconds_to_decision: float | None = None,
    ) -> DrainReport:
        """Walk the open queue in rank order, offering each entry to ``decider``.

        ``decider`` returns ``(decision, decided_by, second_adjudicator)`` or ``None`` to leave the
        entry open. Returning ``None`` is a first-class outcome: a reviewer who stops after twenty
        rows has drained twenty rows, and the queue must say so rather than treating the rest as
        rejected.
        """
        accepted = kept = escalated = skipped = 0
        decided = 0
        for entry in self.open_entries():
            if limit and decided >= limit:
                break
            answer = decider(entry)
            if answer is None:
                skipped += 1
                continue
            decision, decided_by, second = answer
            self.decide(
                entry,
                decision=decision,
                decided_by=decided_by,
                second_adjudicator=second,
                seconds_to_decision=seconds_to_decision,
            )
            decided += 1
            if decision is Decision.ACCEPT_REDLINE:
                accepted += 1
            elif decision is Decision.KEEP_CATALOG:
                kept += 1
            else:
                escalated += 1

        return DrainReport(
            decided=decided,
            accepted=accepted,
            kept_catalog=kept,
            escalated=escalated,
            skipped=skipped,
            remaining=len(self.open_entries()),
        )

    def record_batch(self, manifest: dict[str, object]) -> None:
        """Write the batch manifest and one queue event per finding.

        The per-entry events are what make FR-8.8's reversal a *query*: without them, "everything
        this batch touched" would have to be recomputed by re-running the audit, and a reversal
        that depends on re-deriving the thing being reversed is not a reversal.

        Idempotent, and that is a consequence of the batch id being content-addressed rather than
        a nicety: re-running the same audit over the same feed *is* the same batch, so recording it
        twice would double every queue row and make "how big was this batch" unanswerable. Nothing
        is overwritten to achieve it -- the second call simply writes nothing.
        """
        if self.is_recorded():
            return
        self.ledger.append("scale_batch", {"batch_id": self.batch_id, **manifest})
        for entry in self.triage.entries:
            redline = entry.redline
            self.ledger.append(
                "scale_queue",
                {
                    "batch_id": self.batch_id,
                    "redline_id": entry.redline_id,
                    "sku_id": redline.sku_id,
                    "attribute_uri": redline.attribute_uri,
                    "tier": entry.tier,
                    "severity": int(redline.severity),
                    "disagreement_class": redline.disagreement_class.value,
                    "signature_id": entry.signature_id,
                    "cluster_size": entry.cluster_size,
                    "expected_review_value": round(entry.expected_review_value, 6),
                    "requires_two_signatures": redline.requires_two_signatures,
                },
            )

    def is_recorded(self) -> bool:
        """Whether this batch's manifest is already in the ledger."""
        return any(
            str(event.payload.get("batch_id")) == self.batch_id
            for event in self.ledger.of_kind("scale_batch")
        )

    def safety_entries(self) -> tuple[QueueEntry, ...]:
        return tuple(
            entry
            for entry in self.triage.entries
            if is_safety_class(entry.redline.attribute_uri)
            or is_safety_class(entry.redline.attribute_label)
        )


def entries_of(triage: TriageResult, ids: Iterable[str]) -> tuple[QueueEntry, ...]:
    wanted = {str(value) for value in ids}
    return tuple(entry for entry in triage.entries if entry.redline_id in wanted)
