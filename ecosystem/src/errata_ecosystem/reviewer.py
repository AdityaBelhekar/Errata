"""FR-9.3 and FR-9.4 -- the two numbers only a human can produce, and the refusal to fake them.

**FR-9.3, reviewer-seconds per verified attribute.** Phase 2 identified this as what the buyer
actually pays for, and no benchmark in the category publishes it. It is a stopwatch measurement of
a person, so the deliverable here is a *protocol* plus the arithmetic that reads its output --
never a number derived from anything but a timed human session.

**FR-9.4, evidence-acceptance rate.** The fraction of redlines whose evidence box a domain
reviewer accepts as supporting the claim. Distinct from grounding F1 and from decision accuracy:
a box can enclose the right words and still not persuade the person deciding, and *that* is the
number that predicts whether a pilot survives contact with a reviewer.

**Three refusals, each unconditional, each pinned by a test:**

1. **Synthetic sessions never produce a number.** :func:`synthetic_sessions` exists so the
   arithmetic can be exercised; it stamps ``synthetic`` provenance and :func:`report` returns
   ``NOT_MEASURED`` before looking at a single duration. This is ground rule 5, carried forward
   from gates 2 and 3 into R3.
2. **Untimed decisions never produce seconds.** An adjudication recorded without a presented and
   a decided timestamp is a decision, not a measurement.
3. **Decisions by anyone other than a domain reviewer never produce either rate.** The
   repository's own ledgers contain adjudications made by the implementer while building the
   console. Counting those would be measuring the author's opinion of the author's boxes.

What this module therefore reports today is ``NOT_MEASURED`` on every input the repository has --
and the exact list of what a session file would need to change that.
"""

from __future__ import annotations

import enum
import json
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from errata_bench.stats import Proportion, wilson

__all__ = [
    "PROTOCOL",
    "Decision",
    "ReviewerReport",
    "ReviewerSession",
    "SessionProvenance",
    "load_sessions",
    "report",
    "sessions_from_ledger",
    "synthetic_sessions",
]

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SESSIONS = REPO_ROOT / "var" / "r3" / "reviewer-sessions.jsonl"

#: The role a decision must carry before its timing or its box judgement counts. A reviewer who
#: wrote the extractor is not measuring the extractor.
DOMAIN_ROLE = "domain_reviewer"

#: Minimum decisions before a median is worth printing. Chosen for the same reason
#: ``MIN_RECORDS_FOR_VERDICT`` exists in the R0 operating point: a median of nine decisions is an
#: anecdote with a decimal point. Thirty is not "enough" -- it is the floor below which the number
#: is not even arguable.
MIN_DECISIONS = 30


class Decision(str, enum.Enum):
    ACCEPT = "accept"
    KEEP = "keep"
    ESCALATE = "escalate"


class SessionProvenance(str, enum.Enum):
    TIMED_HUMAN = "timed_human"
    """A person, a stopwatch, and the protocol below. The only provenance that yields a number."""

    SYNTHETIC = "synthetic"
    """Generated to exercise the arithmetic. Pinned to NOT_MEASURED, unconditionally."""

    LEDGER_REPLAY = "ledger_replay"
    """Decisions read out of an existing ledger: real decisions, no timing, no domain role."""


@dataclass(frozen=True, slots=True)
class ReviewerSession:
    """One decision by one reviewer about one redline."""

    session_id: str
    reviewer_id: str
    reviewer_role: str
    redline_id: str
    decision: Decision
    provenance: SessionProvenance
    presented_utc: str = ""
    decided_utc: str = ""
    evidence_accepted: bool | None = None
    """FR-9.4. ``None`` means the reviewer was not asked, which is different from 'rejected'."""

    gold_decision: Decision | None = None
    """What the decision should have been, where a gold answer exists. FR-9.3 requires accuracy
    to be reported next to speed: a reviewer who is fast and wrong is not cheaper."""

    attributes_verified: int = 1
    """A reviewer usually verifies one attribute per redline; a row that verified several says so,
    because the metric is seconds *per verified attribute*, not seconds per screen."""

    @property
    def seconds(self) -> float | None:
        if not self.presented_utc or not self.decided_utc:
            return None
        start = datetime.fromisoformat(self.presented_utc.replace("Z", "+00:00"))
        end = datetime.fromisoformat(self.decided_utc.replace("Z", "+00:00"))
        delta = (end - start).total_seconds()
        return delta if delta >= 0 else None

    @property
    def is_domain_reviewer(self) -> bool:
        return self.reviewer_role == DOMAIN_ROLE


@dataclass(frozen=True, slots=True)
class ReviewerReport:
    measured: bool
    reason: str
    n_decisions: int = 0
    n_timed: int = 0
    n_domain: int = 0
    seconds_per_verified_attribute: float | None = None
    median_seconds: float | None = None
    iqr_seconds: tuple[float, float] | None = None
    decision_accuracy: Proportion | None = None
    evidence_acceptance: Proportion | None = None
    missing: tuple[str, ...] = field(default_factory=tuple)

    def text(self) -> str:
        head = "MEASURED" if self.measured else "NOT MEASURED"
        lines = [
            f"FR-9.3 reviewer-seconds per verified attribute -- {head}",
            f"FR-9.4 evidence-acceptance rate           -- {head}",
            f"  {self.reason}",
            f"  decisions seen {self.n_decisions}   timed {self.n_timed}   "
            f"by a domain reviewer {self.n_domain}",
        ]
        if self.measured:
            lines.append(
                f"  seconds per verified attribute  {self.seconds_per_verified_attribute:.1f} "
                f"(median {self.median_seconds:.1f})"
            )
            if self.iqr_seconds:
                lines.append(
                    f"  interquartile range             {self.iqr_seconds[0]:.1f} - "
                    f"{self.iqr_seconds[1]:.1f} s"
                )
            if self.decision_accuracy is not None:
                lines.append(f"  decision accuracy               {self.decision_accuracy.render()}")
            if self.evidence_acceptance is not None:
                lines.append(f"  evidence-acceptance rate        {self.evidence_acceptance.render()}")
        for item in self.missing:
            lines.append(f"  MISSING: {item}")
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {
            "measured": self.measured,
            "reason": self.reason,
            "n_decisions": self.n_decisions,
            "n_timed": self.n_timed,
            "n_domain": self.n_domain,
            "seconds_per_verified_attribute": self.seconds_per_verified_attribute,
            "median_seconds": self.median_seconds,
            "decision_accuracy": (
                self.decision_accuracy.render() if self.decision_accuracy else None
            ),
            "evidence_acceptance_rate": (
                self.evidence_acceptance.render() if self.evidence_acceptance else None
            ),
            "missing": list(self.missing),
        }


PROTOCOL = """\
FR-9.3 / FR-9.4 -- the timed reviewer protocol
==============================================

The measurement is only reproducible if the conditions are. Everything below is a condition, and
a session run under different conditions is a different measurement that must not be pooled with
these.

WHO
  A domain reviewer: someone who maintains or buys low-voltage circuit-protection product data and
  who did NOT write any part of Errata. Record `reviewer_role: domain_reviewer` only for such a
  person. Their identifier in the session file is a pseudonym; no personal data is stored.

WHAT THEY SEE
  The R1 reviewer console (`errata-audit serve`), unchanged, at its default settings: the sentence,
  the evidence pane with the boxed value and its row/column headers, and the counter-evidence pane.
  No side channel, no explanation from the person running the session.

THE TASK, per queue row
  1. Decide: accept the redline, keep the catalog value, or escalate.
  2. Answer one further question, asked identically every time and recorded as FR-9.4:
       "Does the highlighted evidence support the proposed value? yes / no."
     It is asked AFTER the decision so that it cannot steer it, and it is asked even when the
     reviewer keeps the catalog value -- a rejected redline with an accepted box and a rejected
     redline with a rejected box are different failures.

TIMING
  `presented_utc` is stamped when the row renders; `decided_utc` when the decision is submitted.
  The clock is not paused. A reviewer who stops to consult a colleague produces a long row, and a
  long row is data -- discarding it would measure only the easy decisions.

GOLD
  Where a gold decision exists, record it as `gold_decision`. Speed without accuracy is not a
  saving, and a protocol that reported only seconds would reward guessing.

SESSION SIZE
  At least 30 decisions before any median is quoted (MIN_DECISIONS), and the report states n every
  time. Fewer than 30 is reported as NOT MEASURED with the count.

WHAT INVALIDATES A SESSION
  * any decision made by someone who built the tool;
  * a console modified for the session;
  * timings reconstructed after the fact rather than stamped by the console;
  * pooling sessions run against different builds -- record the build in `session_id`.

FILE FORMAT -- one JSON object per line:

  {"session_id": "s1@errata-audit-0.1.0", "reviewer_id": "R1", "reviewer_role": "domain_reviewer",
   "redline_id": "025b25e5-...", "decision": "accept", "presented_utc": "2026-09-01T09:00:00Z",
   "decided_utc": "2026-09-01T09:00:41Z", "evidence_accepted": true, "gold_decision": "accept",
   "attributes_verified": 1, "provenance": "timed_human"}

Run it with:  errata-r3 reviewer --sessions <file>

THE SHORTEST PATH -- no session file needed
  The console now records everything above by itself. It asks the reviewer for their role, stamps
  `presented_utc` when the row renders and `decided_utc` on submit, and asks the FR-9.4 question.
  So the whole measurement is:

      errata-audit serve --open --ledger var/audit/session1.jsonl
      # the reviewer works through 30+ rows, choosing "Domain reviewer" as their role
      errata-r3 reviewer --ledger var/audit/session1.jsonl

  That is the entire remaining cost of FR-9.3 and FR-9.4: roughly half an hour of one person who
  reads datasheets for a living and did not build this. Until this session the console had no way
  to record that such a person was one -- `sessions_from_ledger` stamped every row `implementer`,
  hard-coded -- so an expert could have worked through the whole queue and produced nothing. Two
  of the numbers the PRD calls the ones a buyer actually cares about were blocked on a `<select>`.

  What software cannot do is verify the role. A person types it. Everything above is designed so
  that producing a false measurement requires somebody to assert a false role in an append-only
  ledger under their own name, rather than a number appearing because nobody was asked.
"""


def load_sessions(path: Path | str | None = None) -> tuple[ReviewerSession, ...]:
    target = Path(path) if path is not None else DEFAULT_SESSIONS
    if not target.exists():
        return ()
    sessions: list[ReviewerSession] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        sessions.append(
            ReviewerSession(
                session_id=str(row.get("session_id", "")),
                reviewer_id=str(row.get("reviewer_id", "")),
                reviewer_role=str(row.get("reviewer_role", "")),
                redline_id=str(row.get("redline_id", "")),
                decision=Decision(str(row.get("decision", "keep"))),
                provenance=SessionProvenance(str(row.get("provenance", "timed_human"))),
                presented_utc=str(row.get("presented_utc", "")),
                decided_utc=str(row.get("decided_utc", "")),
                evidence_accepted=row.get("evidence_accepted"),
                gold_decision=(
                    Decision(str(row["gold_decision"])) if row.get("gold_decision") else None
                ),
                attributes_verified=int(row.get("attributes_verified", 1) or 1),
            )
        )
    return tuple(sessions)


def sessions_from_ledger(ledger_path: Path | str) -> tuple[ReviewerSession, ...]:
    """Adjudications already in a ledger, read as sessions.

    **The role is read from the row, not assumed.** It used to be hard-coded to ``implementer``,
    which was true of every row that existed and made the console incapable of ever producing a
    measurement: a genuine domain reviewer could sit down, work through the queue, and their
    session would be filed as the implementer's because nothing asked them who they were. The
    console now requires a role and records it; this reads it back.

    ``implementer`` remains the fallback for a row with no role, and that is not a default so much
    as a fact: every adjudication written before the field existed was made by somebody building
    the tool.

    The rest of the original caveat stands. These are real decisions and they are **not** a
    measurement -- the deciders were the people building the tool, and
    :func:`report` refuses them for that reason. Reading them anyway shows exactly how far the
    existing data gets, which is further than nothing and short of a number.
    """
    path = Path(ledger_path)
    if not path.exists():
        return ()
    sessions: list[ReviewerSession] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("kind") != "adjudication":
            continue
        payload = event.get("payload", {})
        raw = str(payload.get("decision", "keep")).lower()
        decision = Decision(raw) if raw in {d.value for d in Decision} else Decision.KEEP
        sessions.append(
            ReviewerSession(
                session_id=f"ledger:{path.name}",
                reviewer_id=str(payload.get("decided_by", "unknown")),
                reviewer_role=str(payload.get("decided_by_role") or "implementer"),
                redline_id=str(payload.get("redline_id", "")),
                decision=decision,
                provenance=SessionProvenance.LEDGER_REPLAY,
                presented_utc=str(payload.get("presented_utc") or ""),
                decided_utc=str(payload.get("decided_utc") or ""),
                evidence_accepted=payload.get("evidence_accepted"),
            )
        )
    return tuple(sessions)


def synthetic_sessions(n: int = 40, *, seed: int = 20260820) -> tuple[ReviewerSession, ...]:
    """Sessions that exercise every branch of the arithmetic and can never produce a number.

    The provenance stamp is the mechanism, and :func:`report` checks it before anything else --
    so a caller cannot reach a rate by passing enough synthetic rows.
    """
    import random

    rng = random.Random(seed)
    out: list[ReviewerSession] = []
    for i in range(n):
        seconds = rng.uniform(15, 120)
        decision = rng.choice(list(Decision))
        out.append(
            ReviewerSession(
                session_id="synthetic",
                reviewer_id=f"synthetic-{i % 3}",
                reviewer_role=DOMAIN_ROLE,
                redline_id=f"synthetic-redline-{i}",
                decision=decision,
                provenance=SessionProvenance.SYNTHETIC,
                presented_utc="2026-08-20T10:00:00Z",
                decided_utc=(
                    f"2026-08-20T10:{int(seconds) // 60:02d}:{int(seconds) % 60:02d}Z"
                ),
                evidence_accepted=rng.random() < 0.8,
                gold_decision=decision if rng.random() < 0.9 else Decision.KEEP,
            )
        )
    return tuple(out)


def report(sessions: Iterable[ReviewerSession] | None = None) -> ReviewerReport:
    """FR-9.3 and FR-9.4 from a set of sessions, or the reason there is no number."""
    rows: Sequence[ReviewerSession] = tuple(sessions or ())

    if not rows:
        return ReviewerReport(
            measured=False,
            reason=(
                "no reviewer sessions exist. These two numbers are measurements of people, and "
                "nobody has been timed."
            ),
            missing=(
                "a timed session file produced under the protocol (errata-r3 reviewer --protocol)",
                f"at least {MIN_DECISIONS} decisions by a reviewer who did not build the tool",
            ),
        )

    if any(s.provenance is SessionProvenance.SYNTHETIC for s in rows):
        return ReviewerReport(
            measured=False,
            reason=(
                "the session set contains synthetic rows. Synthetic input never produces a "
                "reviewer number, unconditionally -- the same rule R0's gates 2 and 3 hold to."
            ),
            n_decisions=len(rows),
            missing=("real timed sessions",),
        )

    domain = [s for s in rows if s.is_domain_reviewer]
    timed = [s for s in domain if s.seconds is not None]

    if not domain:
        return ReviewerReport(
            measured=False,
            reason=(
                "every decision seen was made by someone other than a domain reviewer "
                f"(roles: {', '.join(sorted({s.reviewer_role or 'unstated' for s in rows}))}). "
                "Decisions made by the people who built the console measure the console's author."
            ),
            n_decisions=len(rows),
            n_timed=len([s for s in rows if s.seconds is not None]),
            missing=(f"decisions carrying reviewer_role={DOMAIN_ROLE!r}",),
        )

    if len(timed) < MIN_DECISIONS:
        return ReviewerReport(
            measured=False,
            reason=(
                f"{len(timed)} timed decisions by a domain reviewer; the protocol requires at "
                f"least {MIN_DECISIONS} before a median is quoted."
            ),
            n_decisions=len(rows),
            n_timed=len(timed),
            n_domain=len(domain),
            missing=(f"{MIN_DECISIONS - len(timed)} further timed decisions",),
        )

    per_attribute = [
        s.seconds / max(1, s.attributes_verified) for s in timed if s.seconds is not None
    ]
    quantiles = statistics.quantiles(per_attribute, n=4) if len(per_attribute) >= 4 else None

    with_gold = [s for s in domain if s.gold_decision is not None]
    accuracy = (
        wilson(sum(1 for s in with_gold if s.decision is s.gold_decision), len(with_gold))
        if with_gold
        else None
    )

    asked = [s for s in domain if s.evidence_accepted is not None]
    acceptance = (
        wilson(sum(1 for s in asked if s.evidence_accepted), len(asked)) if asked else None
    )

    missing: list[str] = []
    if accuracy is None:
        missing.append("no gold decisions recorded, so speed is reported without accuracy")
    if acceptance is None:
        missing.append("the FR-9.4 question was not asked, so there is no evidence-acceptance rate")

    return ReviewerReport(
        measured=True,
        reason=f"{len(timed)} timed decisions by {len({s.reviewer_id for s in domain})} domain reviewer(s)",
        n_decisions=len(rows),
        n_timed=len(timed),
        n_domain=len(domain),
        seconds_per_verified_attribute=statistics.fmean(per_attribute),
        median_seconds=statistics.median(per_attribute),
        iqr_seconds=(quantiles[0], quantiles[2]) if quantiles else None,
        decision_accuracy=accuracy,
        evidence_acceptance=acceptance,
        missing=tuple(missing),
    )
