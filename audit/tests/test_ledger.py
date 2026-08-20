"""FR-7.6 / FR-8.2 -- the ledger is append-only, and that is tested as an API property.

§4.3's first commitment is that reversing a batch is a *query*, not a recovery project. That is
only true if nothing was ever overwritten, so the strongest test here is the dullest one: the class
has no update method and no delete method. It will keep passing until somebody adds one, which is
exactly when a human should be looking.

The other tests are about what gets recorded. "Keep catalog" against an empty counter-evidence
panel is the highest-signal event in the system (§5.4) -- the reviewer knows something the corpus
does not -- and a ledger that only stored accepted changes would throw that signal away.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from errata_audit.ledger import Ledger, calibration_examples
from errata_spec import (
    AsserterKind,
    BlastRadius,
    CounterEvidence,
    Decision,
    DisagreementClass,
    Evidence,
    Redline,
    Severity,
)


def _redline(*, safety: bool = False, counter: CounterEvidence | None = None) -> Redline:
    return Redline(
        sku_id="AX-16",
        mpn="AX-16",
        attribute_uri="etim:EF000227" if safety else "customer:weight_kg",
        attribute_label="Rated current" if safety else "Weight",
        catalog_value="61 A" if safety else "1.25 kg",
        proposed_value="16 A" if safety else "0.125 kg",
        disagreement_class=DisagreementClass.CONTRADICTION,
        severity=Severity.SEV1,
        blast_radius=BlastRadius(),
        counter_evidence=counter or CounterEvidence.none_found("61 A"),
        evidence=(
            Evidence(
                doc_id="d",
                doc_revision_sha256="a" * 64,
                page=1,
                char_span=(10, 12),
            ),
        ),
    )


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.jsonl")


def test_the_ledger_has_no_way_to_change_or_delete_anything() -> None:
    forbidden = {"update", "delete", "remove", "edit", "overwrite", "truncate", "clear"}
    assert not forbidden & {name for name in dir(Ledger) if not name.startswith("_")}


def test_events_round_trip(ledger: Ledger) -> None:
    redline = _redline()
    ledger.append_redline(redline)
    events = list(ledger.events())
    assert len(events) == 1
    assert events[0].kind == "redline"
    assert events[0].payload["sku_id"] == "AX-16"


def test_an_adjudication_writes_both_a_decision_and_a_claim(ledger: Ledger) -> None:
    redline = _redline()
    adjudication, claim = ledger.adjudicate(
        redline, decision=Decision.ACCEPT_REDLINE, decided_by="A. Reviewer", seconds_to_decision=31.0
    )
    kinds = [event.kind for event in ledger.events()]
    assert kinds == ["adjudication", "claim"]
    assert claim.asserter_kind is AsserterKind.HUMAN
    assert claim.value_raw == "0.125 kg"
    assert adjudication.seconds_to_decision == 31.0


def test_keep_catalog_records_the_catalog_value_and_no_evidence(ledger: Ledger) -> None:
    """§5.4: a human claim may carry no evidence, and this is the case the schema allows it for."""
    _adjudication, claim = ledger.adjudicate(
        _redline(), decision=Decision.KEEP_CATALOG, decided_by="A. Reviewer"
    )
    assert claim.value_raw == "1.25 kg"
    assert claim.evidence == ()


def test_the_empty_counter_evidence_panel_is_recorded_with_the_decision(ledger: Ledger) -> None:
    """It is what makes "keep catalog" a document-recovery lead rather than just a rejection."""
    ledger.adjudicate(_redline(), decision=Decision.KEEP_CATALOG, decided_by="A. Reviewer")
    event = ledger.of_kind("adjudication")[0]
    assert event.payload["counter_evidence_was_empty"] is True


def test_a_safety_class_redline_cannot_be_adjudicated_alone(ledger: Ledger) -> None:
    """FR-8.9, and it is enforced by ``Redline`` rather than here: attaching an adjudication with
    no second signature raises when the object is constructed, so there is no code path through
    the ledger that accepts one."""
    with pytest.raises(ValueError, match="single-signature acceptance is impossible"):
        ledger.adjudicate(
            _redline(safety=True), decision=Decision.ACCEPT_REDLINE, decided_by="A. Reviewer"
        )


def test_a_safety_class_redline_with_two_signatures_is_recorded(ledger: Ledger) -> None:
    _adjudication, claim = ledger.adjudicate(
        _redline(safety=True),
        decision=Decision.ACCEPT_REDLINE,
        decided_by="A. Reviewer",
        second_adjudicator="B. Engineer",
    )
    assert claim.value_raw == "16 A"
    assert ledger.of_kind("adjudication")[0].payload["second_adjudicator"] == "B. Engineer"


def test_history_returns_everything_about_one_sku(ledger: Ledger) -> None:
    ledger.append_redline(_redline())
    ledger.adjudicate(_redline(), decision=Decision.KEEP_CATALOG, decided_by="A")
    assert len(ledger.history("AX-16")) == 3
    assert ledger.history("AX-99") == ()


def test_calibration_labels_come_from_decisions_not_from_the_audit(ledger: Ledger) -> None:
    ledger.adjudicate(
        _redline(), decision=Decision.ACCEPT_REDLINE, decided_by="A", raw_score=0.8
    )
    ledger.adjudicate(_redline(), decision=Decision.KEEP_CATALOG, decided_by="A", raw_score=0.3)
    assert set(calibration_examples(ledger)) == {(0.8, True), (0.3, False)}


def test_an_escalation_is_not_a_calibration_label(ledger: Ledger) -> None:
    """An escalation is a reviewer declining to answer. Reading it as either label would put a
    guess into the one place a guess does the most damage."""
    ledger.adjudicate(_redline(), decision=Decision.ESCALATE, decided_by="A", raw_score=0.6)
    assert calibration_examples(ledger) == ()


def test_a_decision_with_no_score_is_skipped_rather_than_defaulted(ledger: Ledger) -> None:
    ledger.adjudicate(_redline(), decision=Decision.ACCEPT_REDLINE, decided_by="A")
    assert calibration_examples(ledger) == ()


def test_an_unknown_schema_is_refused_rather_than_skipped(tmp_path: Path) -> None:
    """A reader that skipped events it did not understand would report a history with holes, and a
    history with holes is worse than one that fails to load."""
    path = tmp_path / "l.jsonl"
    path.write_text('{"schema": "something-else/9", "kind": "claim", "payload": {}}\n', "utf-8")
    with pytest.raises(ValueError, match="understands"):
        list(Ledger(path).events())


def test_reading_a_ledger_that_does_not_exist_yet_is_empty_not_an_error(tmp_path: Path) -> None:
    assert list(Ledger(tmp_path / "nothing.jsonl").events()) == []
