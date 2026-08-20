"""FR-9.3 / FR-9.4 -- the refusals; and FR-9.8 / ADR-003 -- the licence boundary.

These two live together because they are the same kind of test: each one proves a *refusal*
works, and each refusal has a control showing the machinery would produce the number if the
conditions were met. A refusal that cannot be lifted is indistinguishable from broken code.
"""

from __future__ import annotations

import json
import zipfile

import pytest

from errata_ecosystem.eclass import (
    ECLASS_IRDI,
    EclassAdapter,
    EclassContentFound,
    assert_clean,
    scan,
    scan_distribution,
)
from errata_ecosystem.reviewer import (
    MIN_DECISIONS,
    PROTOCOL,
    Decision,
    ReviewerSession,
    SessionProvenance,
    load_sessions,
    report,
    sessions_from_ledger,
    synthetic_sessions,
)

# ------------------------------------------------------------------------------------------------
# Testing a content scanner needs content that trips it, which is a problem when the scanner runs
# over this file. The identifiers below are ASSEMBLED AT RUNTIME from fragments, so no
# ECLASS-shaped literal exists anywhere in the repository and `scan()` can keep the strong form of
# its invariant: not "no ECLASS content except where we allowed it", which is the loophole every
# such scanner eventually acquires, but none at all.
#
# The codes are also deliberately impossible: ZZZ999 and ZZY000 are not code spaces ECLASS uses.
# A test fixture that happened to be a real licensed identifier would be the exact thing under
# test, committed.
# ------------------------------------------------------------------------------------------------
_PREFIX = "0173-" + "1#02-"
FAKE_IRDI = _PREFIX + "ZZZ999" + "#001"
OTHER_FAKE_IRDI = _PREFIX + "ZZY000" + "#004"

# ================================================================================================
# FR-9.3 / FR-9.4
# ================================================================================================


def _timed(n: int, *, seconds: int = 40, role: str = "domain_reviewer") -> tuple:
    return tuple(
        ReviewerSession(
            session_id="s@errata-audit-0.1.0",
            reviewer_id=f"R{i % 2}",
            reviewer_role=role,
            redline_id=f"r-{i}",
            decision=Decision.ACCEPT,
            provenance=SessionProvenance.TIMED_HUMAN,
            presented_utc="2026-09-01T09:00:00Z",
            decided_utc=f"2026-09-01T09:00:{seconds:02d}Z",
            evidence_accepted=i % 5 != 0,
            gold_decision=Decision.ACCEPT if i % 7 else Decision.KEEP,
        )
        for i in range(n)
    )


def test_no_sessions_means_no_number_and_a_list_of_what_is_missing() -> None:
    result = report(())
    assert not result.measured
    assert result.seconds_per_verified_attribute is None
    assert result.missing


def test_synthetic_sessions_never_produce_a_number_however_many_there_are() -> None:
    """Ground rule 5, carried into R3: synthetic input is pinned to NOT MEASURED."""
    result = report(synthetic_sessions(n=500))
    assert not result.measured
    assert "synthetic" in result.reason


def test_decisions_by_the_people_who_built_the_tool_do_not_count() -> None:
    result = report(_timed(MIN_DECISIONS + 5, role="implementer"))
    assert not result.measured
    assert "domain reviewer" in result.reason


def test_too_few_timed_decisions_reports_the_shortfall_rather_than_a_median() -> None:
    result = report(_timed(MIN_DECISIONS - 1))
    assert not result.measured
    assert f"{MIN_DECISIONS}" in result.reason
    assert "1 further timed decisions" in " ".join(result.missing)


def test_a_real_timed_session_does_produce_both_numbers() -> None:
    """The control. Without this, every test above could be passing because the code is broken."""
    result = report(_timed(MIN_DECISIONS, seconds=40))
    assert result.measured
    assert result.seconds_per_verified_attribute == pytest.approx(40.0)
    assert result.median_seconds == pytest.approx(40.0)
    assert result.evidence_acceptance is not None
    assert result.decision_accuracy is not None


def test_seconds_are_per_verified_attribute_not_per_screen() -> None:
    one = ReviewerSession(
        session_id="s",
        reviewer_id="R",
        reviewer_role="domain_reviewer",
        redline_id="r",
        decision=Decision.ACCEPT,
        provenance=SessionProvenance.TIMED_HUMAN,
        presented_utc="2026-09-01T09:00:00Z",
        decided_utc="2026-09-01T09:01:00Z",
        attributes_verified=4,
    )
    rows = (one,) * MIN_DECISIONS
    result = report(rows)
    assert result.measured
    assert result.seconds_per_verified_attribute == pytest.approx(15.0)


def test_the_repositorys_own_ledger_is_read_and_still_yields_nothing() -> None:
    from pathlib import Path

    ledger = Path(__file__).resolve().parents[2] / "var" / "audit" / "ledger.jsonl"
    if not ledger.exists():  # pragma: no cover - the demo ledger is gitignored
        pytest.skip("no ledger on this machine")
    sessions = sessions_from_ledger(ledger)
    result = report(sessions)
    assert not result.measured
    assert all(s.provenance is SessionProvenance.LEDGER_REPLAY for s in sessions)


def test_a_session_file_round_trips(tmp_path) -> None:
    path = tmp_path / "sessions.jsonl"
    path.write_text(
        json.dumps(
            {
                "session_id": "s1",
                "reviewer_id": "R1",
                "reviewer_role": "domain_reviewer",
                "redline_id": "r1",
                "decision": "accept",
                "presented_utc": "2026-09-01T09:00:00Z",
                "decided_utc": "2026-09-01T09:00:41Z",
                "evidence_accepted": True,
                "gold_decision": "accept",
                "provenance": "timed_human",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sessions = load_sessions(path)
    assert len(sessions) == 1
    assert sessions[0].seconds == pytest.approx(41.0)


def test_the_protocol_states_the_conditions_that_would_invalidate_a_session() -> None:
    for phrase in (
        "domain_reviewer",
        "WHAT INVALIDATES A SESSION",
        "evidence support the proposed value",
        "The clock is not paused",
    ):
        assert phrase in PROTOCOL


# ================================================================================================
# FR-9.8 / ADR-003
# ================================================================================================


def test_the_repository_contains_no_eclass_content() -> None:
    report_ = scan()
    assert report_.clean, report_.text()
    assert report_.files_scanned > 100


def test_the_scanner_fires_on_a_licensed_identifier(tmp_path) -> None:
    """The negative control. A scanner nobody has watched reject something proves nothing."""
    (tmp_path / "leak.csv").write_text(
        f"irdi,name\n{OTHER_FAKE_IRDI},Rated current\n", encoding="utf-8"
    )
    found = scan(tmp_path)
    assert not found.clean
    assert found.findings[0].sample == OTHER_FAKE_IRDI
    with pytest.raises(EclassContentFound, match="ADR-003"):
        assert_clean([found])


def test_the_scanner_does_not_fire_on_the_word_eclass(tmp_path) -> None:
    """ADR-003 discusses ECLASS at length. A scanner that flagged the word would either be
    switched off or would push the discussion out of the documents."""
    (tmp_path / "adr.md").write_text(
        "ECLASS is licensed; we ship an adapter, not content.\n", encoding="utf-8"
    )
    assert scan(tmp_path).clean


def test_a_built_distribution_is_scanned_too(tmp_path) -> None:
    """A clean working tree says nothing about what the wheel contains."""
    archive = tmp_path / "thing-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("pkg/data/dictionary.csv", f"irdi\n{FAKE_IRDI}\n")
    found = scan_distribution(archive)
    assert not found.clean
    assert "dictionary.csv" in found.findings[0].path


def test_the_irdi_pattern_matches_the_published_form_and_not_a_lookalike() -> None:
    assert ECLASS_IRDI.search(OTHER_FAKE_IRDI)
    assert not ECLASS_IRDI.search(OTHER_FAKE_IRDI.replace("0173-1", "0173-2"))
    assert not ECLASS_IRDI.search("EC000042")


def test_the_adapter_reads_the_customers_file_at_runtime(tmp_path) -> None:
    dictionary = tmp_path / "customer-eclass.csv"
    dictionary.write_text(
        "IRDI;PreferredName;Definition;Unit;DataType\n"
        f"{FAKE_IRDI};Rated current;the current;A;REAL\n",
        encoding="utf-8",
    )
    adapter = EclassAdapter.from_path(dictionary, release="16.0")
    assert len(adapter) == 1
    assert adapter.get(FAKE_IRDI).preferred_name == "Rated current"
    described = adapter.describe()
    assert "1 properties" in described
    # The description must not reproduce content -- it is the one method that could.
    assert "Rated current" not in described


def test_the_adapter_refuses_a_dictionary_inside_the_repository(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    from errata_ecosystem import eclass as module

    inside = Path(module.REPO_ROOT) / "var" / "r3tmp"
    inside.mkdir(parents=True, exist_ok=True)
    target = inside / "would-be-committed.csv"
    target.write_text(f"IRDI;PreferredName\n{FAKE_IRDI};x\n", encoding="utf-8")
    try:
        with pytest.raises(EclassContentFound, match="inside the Errata repository"):
            EclassAdapter.from_path(target)
    finally:
        target.unlink()


def test_the_adapter_refuses_a_file_that_is_not_an_eclass_export(tmp_path) -> None:
    wrong = tmp_path / "something.csv"
    wrong.write_text("sku,value\nS201,16\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no IRDI column"):
        EclassAdapter.from_path(wrong)


def test_an_absent_dictionary_is_the_normal_state_not_an_error(monkeypatch) -> None:
    monkeypatch.delenv("ERRATA_ECLASS_DICTIONARY", raising=False)
    assert EclassAdapter.from_environment() is None
