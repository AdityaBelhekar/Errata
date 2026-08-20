"""FR-9.3 / FR-9.4 -- the path from a reviewer's click to a published number, end to end.

**Nothing here is a measurement and nothing here should ever be read as one.** Every session below
is written by this file. What is being tested is the *plumbing*: that if a domain reviewer sits
down at the console and works through a queue, the numbers FR-9.3 and FR-9.4 ask for come out the
other end without anybody writing more code.

That was not true until now, and the reason was one missing field. The console asked for a name,
timed the decision in the browser and recorded whether the evidence box was accepted -- and never
asked **what the person was**. ``sessions_from_ledger`` therefore stamped every row
``reviewer_role="implementer"``, hard-coded, so a genuine expert's session was indistinguishable
from the author's and could never have counted. Two numbers the PRD calls the ones a buyer
actually cares about were blocked on a ``<select>``.

**Where the trust boundary sits, stated plainly.** The guard is the role, and the role is typed by
a person. Nothing in software can verify that the human at the keyboard is an electrician rather
than the author, and this module does not pretend otherwise: a fabricated ledger passes these
checks exactly as a real one does. What the mechanism buys is that fabricating a measurement now
requires somebody to *assert a false role in an append-only ledger under their own name*, which is
a different act from a number quietly appearing because nobody was asked.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from errata_ecosystem.reviewer import (
    DOMAIN_ROLE,
    MIN_DECISIONS,
    SessionProvenance,
    report,
    sessions_from_ledger,
    synthetic_sessions,
)


def _ledger(path: Path, *, n: int, role: str, timed: bool = True, seconds: float = 42.0) -> Path:
    """A ledger of ``n`` adjudications in the shape the console writes.

    Written by hand rather than by driving the console, because the console needs a browser. The
    field names are the ones ``Ledger.adjudicate`` emits and a test in ``audit/`` pins that shape,
    so a rename there fails there rather than silently making this file test a format nobody uses.
    """
    start = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
    lines = []
    for i in range(n):
        presented = start + timedelta(minutes=i)
        payload = {
            "redline_id": f"redline-{i:03d}",
            "decision": "accept" if i % 3 else "keep",
            "decided_by": "R. Whitfield",
            "decided_by_role": role,
            "evidence_accepted": i % 5 != 0,
            "seconds_to_decision": seconds,
        }
        if timed:
            payload["presented_utc"] = presented.isoformat().replace("+00:00", "Z")
            payload["decided_utc"] = (
                (presented + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
            )
        lines.append(json.dumps({"kind": "adjudication", "payload": payload}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------------------------------------
# The path closes
# ------------------------------------------------------------------------------------------------


def test_a_timed_domain_reviewer_session_produces_both_numbers(tmp_path: Path) -> None:
    """The whole point. Same ledger shape the console writes, and FR-9.3/9.4 come out."""
    ledger = _ledger(tmp_path / "ledger.jsonl", n=MIN_DECISIONS + 5, role=DOMAIN_ROLE)
    result = report(sessions_from_ledger(ledger))

    assert result.measured, result.reason
    assert result.n_timed >= MIN_DECISIONS
    assert result.median_seconds == pytest.approx(42.0, abs=0.5)
    assert result.evidence_acceptance is not None, "FR-9.4 did not populate"


def test_the_role_is_read_from_the_row_not_assumed(tmp_path: Path) -> None:
    """The one-field fix, pinned.

    Before this, ``sessions_from_ledger`` hard-coded ``implementer``. A test that only checked the
    happy path would still have passed with the hard-coding in place, because the fixture would
    have been read as an implementer's and the assertion would have been about the refusal. So
    this asserts the role that came *out* equals the role that went *in*.
    """
    ledger = _ledger(tmp_path / "l.jsonl", n=3, role=DOMAIN_ROLE)
    assert {s.reviewer_role for s in sessions_from_ledger(ledger)} == {DOMAIN_ROLE}


def test_a_row_with_no_role_is_read_as_an_implementers(tmp_path: Path) -> None:
    """Not a default so much as a fact: every row written before the field existed was one."""
    ledger = _ledger(tmp_path / "l.jsonl", n=3, role="")
    assert {s.reviewer_role for s in sessions_from_ledger(ledger)} == {"implementer"}


def test_the_timestamps_are_carried_so_the_duration_can_be_checked(tmp_path: Path) -> None:
    """An elapsed number on its own cannot be audited; two endpoints can.

    ``seconds_to_decision`` is computed in the browser. Nothing about "42.0" says when it started
    or whether the tab sat open over lunch, so the console now records both endpoints and the
    session derives its own duration from them rather than trusting the browser's arithmetic.
    """
    ledger = _ledger(tmp_path / "l.jsonl", n=1, role=DOMAIN_ROLE, seconds=93.0)
    session = sessions_from_ledger(ledger)[0]
    assert session.presented_utc and session.decided_utc
    assert session.seconds == pytest.approx(93.0)


# ------------------------------------------------------------------------------------------------
# The refusals still refuse
# ------------------------------------------------------------------------------------------------


def test_an_implementers_session_still_produces_nothing(tmp_path: Path) -> None:
    """Counting these would be measuring the author's opinion of the author's boxes."""
    ledger = _ledger(tmp_path / "l.jsonl", n=MIN_DECISIONS + 5, role="implementer")
    result = report(sessions_from_ledger(ledger))

    assert not result.measured
    assert "domain reviewer" in result.reason


def test_untimed_decisions_still_produce_nothing(tmp_path: Path) -> None:
    """A decision recorded without endpoints is a decision, not a measurement."""
    ledger = _ledger(tmp_path / "l.jsonl", n=MIN_DECISIONS + 5, role=DOMAIN_ROLE, timed=False)
    result = report(sessions_from_ledger(ledger))

    assert not result.measured
    assert "timed" in result.reason


def test_too_few_decisions_still_produce_nothing(tmp_path: Path) -> None:
    """A median of nine decisions is an anecdote with a decimal point."""
    ledger = _ledger(tmp_path / "l.jsonl", n=MIN_DECISIONS - 1, role=DOMAIN_ROLE)
    result = report(sessions_from_ledger(ledger))

    assert not result.measured
    assert str(MIN_DECISIONS) in result.reason


def test_synthetic_sessions_can_never_produce_a_number() -> None:
    """Ground rule 5, carried from gates 2 and 3 into R3. Unconditional.

    Note the asymmetry with the ledger path and why it is correct: synthetic rows are refused by a
    stamp the *code* applies, while a ledger row is trusted because a *person* signed it. Software
    can be certain about the first and cannot be about the second.
    """
    rows = synthetic_sessions(MIN_DECISIONS * 2)
    assert all(s.provenance is SessionProvenance.SYNTHETIC for s in rows)
    result = report(rows)
    assert not result.measured
    assert "synthetic" in result.reason


def test_the_repositorys_own_ledger_still_measures_nothing() -> None:
    """The state of the world, asserted so a fixture cannot be mistaken for progress.

    Every adjudication this repository holds was made by somebody building it. If this test ever
    fails, either a real reviewer has been run -- in which case delete it and publish the number --
    or somebody has written a role into a ledger that was not earned.
    """
    real = Path(__file__).resolve().parents[2] / "var" / "audit" / "ledger.jsonl"
    if not real.exists():
        pytest.skip("no local ledger; nothing to assert about")
    assert not report(sessions_from_ledger(real)).measured
