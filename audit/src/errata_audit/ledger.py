"""FR-7.6 / FR-7.8 / FR-8.2 -- the claim ledger: append-only, and the reason anything is reversible.

    "Decision, actor, timestamp and note persisted immutably."
    "Evidence shown is reconstructible from stored state, not regenerated at view time."

The ledger is one file of JSON lines and it has no update method and no delete method. That is the
design, not a stage of it. §4.3's first commitment is that batch reversal is a *query* rather than a
recovery project: when a customer says "undo everything that run touched", the answer has to be a
selection over stored facts, and it can only be that if nothing was ever overwritten.

Three consequences, each of which someone will eventually propose removing:

* **A correction is a new claim** whose ``supersedes`` names the old one. The old claim stays
  readable forever, because a reviewer who accepted it did so on evidence that was accurate at the
  time, and rewriting history would turn a good decision into an inexplicable one.
* **A human decision is an event, not a field.** ``Accept redline`` writes an ``Adjudication`` *and*
  a human-asserted claim. Both are kept: the claim is what the catalog should say, the adjudication
  is who said so, when, in how many seconds, and whether they accepted the evidence box (FR-9.4).
* **"Keep catalog" is recorded with the same weight as "accept".** §5.4 calls it the highest-signal
  event in the system when the counter-evidence panel was empty: the reviewer knows something the
  corpus does not. A ledger that only stored accepted changes would throw that signal away.

The format is JSON Lines rather than a database because R1 must run from a clean clone with no
signup (FR-7.9), and because a ledger a customer can read in a text editor is a ledger a customer
can audit. The *interface* -- ``append``, ``events``, ``history``, ``adjudicate`` -- is the part
intended to survive a storage change.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from errata_spec import (
    Abstention,
    Adjudication,
    AsserterKind,
    Claim,
    Decision,
    Redline,
)

__all__ = [
    "LEDGER_SCHEMA",
    "Ledger",
    "LedgerEvent",
    "calibration_examples",
]

LEDGER_SCHEMA = "errata-claim-ledger/1"


class LedgerEvent(dict):
    """One line of the ledger. A dict on purpose: the file is the contract, not a Python class."""

    @property
    def kind(self) -> str:
        return str(self.get("kind", ""))

    @property
    def payload(self) -> dict[str, Any]:
        return dict(self.get("payload", {}))


class Ledger:
    """An append-only event log of claims, abstentions, redlines and human decisions."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    # -- writing ---------------------------------------------------------------------------

    def append(self, kind: str, payload: dict[str, Any]) -> LedgerEvent:
        event = LedgerEvent(
            schema=LEDGER_SCHEMA,
            kind=kind,
            event_id=str(uuid.uuid4()),
            recorded_utc=datetime.now(UTC).isoformat(),
            payload=payload,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=False, default=str) + "\n")
        return event

    def append_claim(self, claim: Claim) -> LedgerEvent:
        return self.append("claim", json.loads(claim.model_dump_json()))

    def append_abstention(self, abstention: Abstention) -> LedgerEvent:
        return self.append("abstention", json.loads(abstention.model_dump_json()))

    def append_redline(self, redline: Redline) -> LedgerEvent:
        return self.append("redline", json.loads(redline.model_dump_json()))

    def adjudicate(
        self,
        redline: Redline,
        *,
        decision: Decision,
        decided_by: str,
        note: str = "",
        seconds_to_decision: float | None = None,
        evidence_accepted: bool | None = None,
        second_adjudicator: str = "",
        raw_score: float | None = None,
    ) -> tuple[Adjudication, Claim]:
        """Record a human decision, and the claim it asserts (FR-7.6).

        Safety-class attributes need a second named adjudicator, and that is enforced by
        ``Redline`` itself rather than here -- constructing the adjudicated redline raises without
        one, so there is no path through this function that quietly accepts a single signature.
        """
        adjudication = Adjudication(
            decision=decision,
            decided_by=decided_by,
            note=note,
            seconds_to_decision=seconds_to_decision,
            evidence_accepted=evidence_accepted,
            second_adjudicator=second_adjudicator,
        )
        # `model_copy(update=...)` does NOT re-run pydantic validators, so the safety-class
        # two-signature rule in `Redline` is silently bypassed by it. That is the single most
        # important invariant in this module (FR-8.9), and it took a failing test to notice: the
        # copy is therefore re-validated, which puts the rule back on the shortest path instead of
        # relying on every caller to remember it.
        decided = Redline.model_validate(
            redline.model_copy(update={"adjudication": adjudication}).model_dump()
        )

        value = (
            decided.proposed_value
            if decision is Decision.ACCEPT_REDLINE
            else decided.catalog_value
        )
        claim = Claim(
            sku_id=decided.sku_id,
            mpn=decided.mpn,
            attribute_uri=decided.attribute_uri,
            class_uri=decided.class_uri,
            value_raw=value,
            asserter_kind=AsserterKind.HUMAN,
            supersedes=decided.proposed_claim_id
            if decision is Decision.ACCEPT_REDLINE
            else decided.catalog_claim_id,
            # A human claim may carry no evidence, and "keep catalog" with none is the
            # highest-signal event in the system (§5.4). The schema allows it precisely so this
            # case is recordable rather than being forced into a shape that hides it.
            evidence=decided.evidence if decision is Decision.ACCEPT_REDLINE else (),
        )

        self.append(
            "adjudication",
            {
                "redline_id": str(decided.redline_id),
                "sku_id": decided.sku_id,
                "attribute_uri": decided.attribute_uri,
                "decision": decision.value,
                "decided_by": decided_by,
                "decided_at": adjudication.decided_at.isoformat(),
                "note": note,
                "seconds_to_decision": seconds_to_decision,
                "evidence_accepted": evidence_accepted,
                "second_adjudicator": second_adjudicator,
                "counter_evidence_was_empty": not decided.counter_evidence.supporting,
                "probability_catalog_wrong": decided.probability_catalog_wrong,
                # The extractor's own uncalibrated score at decision time. Carried so a later
                # calibration is fitted against the signal that actually existed when the reviewer
                # decided, rather than against a probability that did not exist yet.
                "raw_score": raw_score,
                "severity": int(decided.severity),
                "disagreement_class": decided.disagreement_class.value,
            },
        )
        self.append_claim(claim)
        return adjudication, claim

    # -- reading ---------------------------------------------------------------------------

    def events(self) -> Iterator[LedgerEvent]:
        if not self.path.exists():
            return iter(())
        return self._read()

    def _read(self) -> Iterator[LedgerEvent]:
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                if raw.get("schema") != LEDGER_SCHEMA:
                    raise ValueError(
                        f"{self.path} contains an event with schema {raw.get('schema')!r}; "
                        f"this reader understands {LEDGER_SCHEMA!r} only. A ledger that silently "
                        "skipped events it did not understand would report a history with holes."
                    )
                yield LedgerEvent(raw)

    def of_kind(self, kind: str) -> tuple[LedgerEvent, ...]:
        return tuple(event for event in self.events() if event.kind == kind)

    def history(self, sku_id: str) -> tuple[LedgerEvent, ...]:
        """Everything ever recorded about one SKU, oldest first -- the console's third pane."""
        return tuple(
            event
            for event in self.events()
            if str(event.payload.get("sku_id", "")) == sku_id
        )

    def decisions_for(self, redline_id: str) -> tuple[LedgerEvent, ...]:
        return tuple(
            event
            for event in self.of_kind("adjudication")
            if str(event.payload.get("redline_id")) == redline_id
        )


def calibration_examples(ledger: Ledger) -> tuple[tuple[float, bool], ...]:
    """Turn adjudications into calibration labels (FR-6.1).

    ``(score, catalog_was_wrong)`` for every adjudicated redline that carried a score. *Accept
    redline* means the catalog was wrong; *keep catalog* means it was not. **Escalations are
    excluded** -- an escalation is a reviewer declining to answer, and reading it as either label
    would put a guess into the calibration set, which is the one place a guess does the most damage.
    """
    out: list[tuple[float, bool]] = []
    for event in ledger.of_kind("adjudication"):
        payload = event.payload
        decision = payload.get("decision")
        if decision not in {Decision.ACCEPT_REDLINE.value, Decision.KEEP_CATALOG.value}:
            continue
        score = payload.get("raw_score")
        if score is None:
            score = payload.get("probability_catalog_wrong")
        if score is None:
            continue
        out.append((float(score), decision == Decision.ACCEPT_REDLINE))
    return tuple(out)
