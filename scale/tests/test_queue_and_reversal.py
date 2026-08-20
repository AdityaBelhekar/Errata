"""The drainable queue (R2's exit criterion) and FR-8.8 batch reversal.

    "Any audit batch's accepted redlines revert from the ledger as a query. Demonstrated on a
    1,000-record batch."

The 1,000-record demonstration is run here rather than described. It is slow-ish and it is worth
it: the properties that matter -- that reversal is a *selection* over stored facts, that nothing is
deleted, that running it twice does nothing the second time -- are exactly the properties that hold
trivially at n=2 and break at scale if the implementation quietly recomputes anything.

The queue tests are about the word *drainable*: a decision persists, is not re-offered, and the
count survives the process. Safety-class rows are decidable, with two signatures; the queue refuses
the decision, never the row, because a queue with undecidable rows in it does not drain.
"""

from __future__ import annotations

import pytest
from scalefixtures import ledger_path  # noqa: F401

from errata_audit import Ledger
from errata_scale import (
    ReviewQueue,
    SecondAdjudicatorRequired,
    accepted_in_batch,
    claim_chains,
    cluster_signatures,
    reverse_batch,
    route,
)
from errata_spec import (
    BlastRadius,
    CounterEvidence,
    Decision,
    DisagreementClass,
    Evidence,
    Redline,
    Severity,
)

DIGEST = "d" * 64
BATCH = "11111111-2222-3333-4444-555555555555"


def _redline(sku: str, *, attribute: str = "weight_kg", label: str = "Weight") -> Redline:
    return Redline(
        sku_id=sku,
        attribute_uri=attribute,
        attribute_label=label,
        catalog_value="0.9 kg",
        proposed_value="0.125 kg",
        disagreement_class=DisagreementClass.CONTRADICTION,
        severity=Severity.SEV1,
        evidence=(
            Evidence(
                doc_id="feed.csv",
                doc_revision_sha256=DIGEST,
                page=1,
                char_span=(0, 8),
                snippet="0.125 kg",
                column_header=attribute,
            ),
        ),
        counter_evidence=CounterEvidence.none_found("0.9 kg"),
        blast_radius=BlastRadius(),
    )


def _queue(ledger_path, redlines) -> ReviewQueue:
    triage = route(redlines, cluster_signatures(redlines))
    queue = ReviewQueue(triage, ledger=Ledger(ledger_path), batch_id=BATCH)
    queue.record_batch({"catalog": "test", "records": len(redlines)})
    return queue


# ------------------------------------------------------------------------------------------------
# drainable
# ------------------------------------------------------------------------------------------------


def test_a_queue_drains_to_empty(ledger_path):
    queue = _queue(ledger_path, [_redline(f"SKU-{n}") for n in range(20)])
    assert queue.progress() == (0, 20)
    report = queue.drain(lambda _entry: (Decision.ACCEPT_REDLINE, "A. Reviewer", ""))
    assert report.decided == 20
    assert report.remaining == 0
    assert queue.progress() == (20, 20)
    assert queue.open_entries() == ()


def test_stopping_early_leaves_the_rest_open_rather_than_rejected(ledger_path):
    queue = _queue(ledger_path, [_redline(f"SKU-{n}") for n in range(10)])
    report = queue.drain(lambda _entry: (Decision.KEEP_CATALOG, "A. Reviewer", ""), limit=3)
    assert (report.decided, report.remaining) == (3, 7)
    assert report.kept_catalog == 3
    assert len(queue.open_entries()) == 7


def test_declining_to_decide_is_a_first_class_outcome(ledger_path):
    queue = _queue(ledger_path, [_redline(f"SKU-{n}") for n in range(5)])
    report = queue.drain(lambda _entry: None)
    assert (report.decided, report.skipped, report.remaining) == (0, 5, 5)


def test_a_decision_persists_and_is_not_re_offered_by_a_rebuilt_queue(ledger_path):
    redlines = [_redline(f"SKU-{n}") for n in range(6)]
    first = _queue(ledger_path, redlines)
    first.drain(lambda _entry: (Decision.ACCEPT_REDLINE, "A. Reviewer", ""), limit=4)

    # A completely fresh queue over the same findings -- what tomorrow's run builds.
    rebuilt = ReviewQueue(
        route(redlines, cluster_signatures(redlines)),
        ledger=Ledger(ledger_path),
        batch_id=BATCH,
    )
    assert rebuilt.progress() == (4, 6)
    assert len(rebuilt.open_entries()) == 2


def test_recording_the_same_batch_twice_writes_nothing_the_second_time(ledger_path):
    redlines = [_redline(f"SKU-{n}") for n in range(3)]
    queue = _queue(ledger_path, redlines)
    before = len(list(Ledger(ledger_path).events()))
    queue.record_batch({"catalog": "test", "records": 3})
    assert len(list(Ledger(ledger_path).events())) == before


def test_a_safety_class_row_cannot_be_accepted_with_one_signature(ledger_path):
    queue = _queue(ledger_path, [_redline("SKU-1", attribute="rated_current", label="Rated current")])
    entry = queue.triage.entries[0]
    assert entry.requires_two_signatures

    with pytest.raises(SecondAdjudicatorRequired) as error:
        queue.decide(entry, decision=Decision.ACCEPT_REDLINE, decided_by="A. Reviewer")
    assert "FR-8.9" in str(error.value)
    # and nothing was written: the ledger never sees a half-formed decision
    assert queue.progress()[0] == 0

    queue.decide(
        entry,
        decision=Decision.ACCEPT_REDLINE,
        decided_by="A. Reviewer",
        second_adjudicator="B. Reviewer",
    )
    assert queue.progress()[0] == 1


def test_a_decision_addressed_to_a_finding_outside_the_batch_is_refused(ledger_path):
    queue = _queue(ledger_path, [_redline("SKU-1")])
    with pytest.raises(KeyError):
        queue.decide("not-a-redline-id", decision=Decision.KEEP_CATALOG, decided_by="A")


def test_keeping_the_catalog_records_a_claim_with_no_evidence(ledger_path):
    """SS5.4: the highest-signal event in the system. It has to be recordable in its own shape."""
    queue = _queue(ledger_path, [_redline("SKU-1")])
    _adjudication, claim = queue.decide(
        queue.triage.entries[0], decision=Decision.KEEP_CATALOG, decided_by="A. Reviewer"
    )
    assert claim.value_raw == "0.9 kg"
    assert claim.evidence == ()


# ------------------------------------------------------------------------------------------------
# FR-8.8 -- batch reversal, demonstrated on 1,000 records
# ------------------------------------------------------------------------------------------------


def test_batch_reversal_on_one_thousand_records(ledger_path):
    redlines = [_redline(f"SKU-{n:04d}") for n in range(1000)]
    queue = _queue(ledger_path, redlines)
    queue.drain(lambda _entry: (Decision.ACCEPT_REDLINE, "A. Reviewer", ""))

    assert len(accepted_in_batch(Ledger(ledger_path), BATCH)) == 1000
    lines_before = len(ledger_path.read_text("utf-8").splitlines())

    report = reverse_batch(Ledger(ledger_path), BATCH, reversed_by="C. Operator")
    assert report.accepted == 1000
    assert report.reversed_now == 1000
    assert report.skus == 1000
    assert report.is_complete

    # nothing was deleted: the file only grew, and every earlier event is still readable
    lines_after = len(ledger_path.read_text("utf-8").splitlines())
    assert lines_after > lines_before
    assert len(accepted_in_batch(Ledger(ledger_path), BATCH)) == 1000

    # and every reversal restored the catalog's own value, as a new claim superseding the accepted
    chains = claim_chains(Ledger(ledger_path))
    chain = chains[("SKU-0000", "weight_kg")]
    assert chain.values() == ("0.125 kg", "0.9 kg")
    assert chain.depth == 2


def test_reversal_is_idempotent(ledger_path):
    redlines = [_redline(f"SKU-{n}") for n in range(5)]
    queue = _queue(ledger_path, redlines)
    queue.drain(lambda _entry: (Decision.ACCEPT_REDLINE, "A. Reviewer", ""))

    first = reverse_batch(Ledger(ledger_path), BATCH, reversed_by="C. Operator")
    lines = len(ledger_path.read_text("utf-8").splitlines())
    second = reverse_batch(Ledger(ledger_path), BATCH, reversed_by="C. Operator")

    assert first.reversed_now == 5
    assert second.reversed_now == 0
    assert second.already_reversed == 5
    assert len(ledger_path.read_text("utf-8").splitlines()) == lines


def test_reversal_touches_only_accepted_redlines(ledger_path):
    redlines = [_redline(f"SKU-{n}") for n in range(6)]
    queue = _queue(ledger_path, redlines)
    order = {"n": 0}

    def decide(_entry):
        order["n"] += 1
        return (
            (Decision.ACCEPT_REDLINE if order["n"] % 2 else Decision.KEEP_CATALOG),
            "A. Reviewer",
            "",
        )

    queue.drain(decide)
    report = reverse_batch(Ledger(ledger_path), BATCH, reversed_by="C. Operator")
    assert report.accepted == 3
    assert report.reversed_now == 3


def test_reversal_can_be_narrowed_to_one_signature(ledger_path):
    """The realistic incident is one bad error signature, not a whole run. Reversing more than was
    asked for would be its own incident."""
    redlines = [_redline(f"SKU-{n}") for n in range(4)]
    queue = _queue(ledger_path, redlines)
    queue.drain(lambda _entry: (Decision.ACCEPT_REDLINE, "A. Reviewer", ""))

    target = str(redlines[0].redline_id)
    report = reverse_batch(
        Ledger(ledger_path), BATCH, reversed_by="C. Operator", only=[target]
    )
    assert report.reversed_now == 1
    assert report.accepted == 1


def test_a_reversal_carries_no_evidence(ledger_path):
    """A reversal withdraws our accusation; it is not a positive finding for the catalog value.
    Attaching the original evidence would misdescribe it as one."""
    queue = _queue(ledger_path, [_redline("SKU-1")])
    queue.drain(lambda _entry: (Decision.ACCEPT_REDLINE, "A. Reviewer", ""))
    reverse_batch(Ledger(ledger_path), BATCH, reversed_by="C. Operator")

    claims = Ledger(ledger_path).of_kind("claim")
    reversal = claims[-1].payload
    assert reversal["value_raw"] == "0.9 kg"
    assert reversal["evidence"] == []


def test_reversing_an_unknown_batch_reverses_nothing(ledger_path):
    Ledger(ledger_path).append("scale_batch", {"batch_id": BATCH})
    report = reverse_batch(Ledger(ledger_path), "no-such-batch", reversed_by="C. Operator")
    assert report.accepted == 0
    assert report.reversed_now == 0
