# The timed reviewer protocol (FR-9.3, FR-9.4)

**Written:** 20 August 2026, with the R3 build.
**Canonical source:** `errata_ecosystem.reviewer.PROTOCOL`. This file is a copy for reading; the
harness prints the one in the code, with `errata-r3 reviewer --protocol`.

These are the two numbers in the PRD that no amount of engineering produces. They are measurements
of people, and until a person has been measured under the conditions below the harness reports
`NOT MEASURED` and names what is missing. Three refusals are unconditional and each is pinned by a
test: synthetic sessions never produce a number, untimed decisions never produce seconds, and
decisions made by anyone who built the tool produce neither rate.

Run the arithmetic over a session file with:

```bash
errata-r3 reviewer --sessions var/r3/reviewer-sessions.jsonl
```

---

```
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
```
