# ADR-001 — Audit-only output vs. write-back enrichment

**Status:** Accepted · **Date:** 17 August 2026 · **Supersedes:** none

## Context

The system re-derives values with evidence. It would be trivially easy — and commercially
tempting — to write them into the customer's PIM. Phase 1 is categorical that catalog operations
refuses batch auto-publishing, having been burned by overnight scripts turning 4,000 SKUs into
unsearchable sludge, and demands a human gate on *every single write. Not a sample. Not a
confidence threshold. Every. Single. Write.* Meanwhile the buyer's stated desire is fewer manual
steps.

## Options considered

| Option | Complexity | Cost | Scalability | Maintenance | Trust posture |
|---|---|---|---|---|---|
| **A.** Full enrichment suite with auto-publish | High — becomes a PIM | High | Blocked by review, not compute | Owns every downstream break | Fails Phase 1's hard requirement outright |
| **B.** Audit-only; emit redlines; never write | Low | Low | Scales with disagreements, not SKUs | Small blast radius | Strongest — you cannot corrupt what you cannot write |
| **C.** Audit + gated per-attribute write-back behind explicit approval | Medium | Medium | Good | Connector matrix per PIM | Strong if the gate is architectural, weak if configurable |

## Decision

**B for R1–R2, C for R4** — with write-back permanently excluded for any attribute in the
safety-class list, at any confidence, with no configuration override.

## How this is enforced in code

Architecture is the only place the promise can be kept credibly; a policy setting can be changed
by a sales engineer under pressure.

- `errata_spec.redline.Redline` is the only output type. There is no writer.
- `Redline` **refuses construction** for any disagreement class that raises no finding, so
  semantic equivalence cannot reach a queue even by accident
  (`test_non_findings_cannot_be_materialised_as_redlines`).
- `errata_spec.taxonomy.SAFETY_CLASS_ATTRIBUTES` is a frozenset, and
  `ResolutionPolicy` **rejects at load time** any customer policy document that removes the
  attribute-scoped escalation rule (`test_a_policy_that_deletes_the_safety_rule_is_rejected_at_load`).
- Accepting a safety-class redline without a second named adjudicator raises a validation error
  (FR-8.9).

## Consequences

**Easier.** The pilot conversation, because you cannot break their catalog. Liability, because you
never assert into production. The demo, because a redline is more legible than a diff.

**Harder.** Proving ROI, since the customer must still spend reviewer-seconds — which is exactly
why reviewer-seconds is the headline metric (FR-9.3). And resisting the sales pressure that will
arrive in month four asking for auto-apply on "high-confidence" fields.

**Who owns a wrong redline that a human accepted.** Audit-only does not remove liability, it
distributes it. If the system says a rated current is wrong, a reviewer accepts on the strength of
the evidence shown, and the system was wrong, then a live catalog has been broken *by a finding*,
and the customer will not care that they clicked the button. Three product commitments follow:

1. Every accepted redline is reversible from the ledger — the superseded claim is never destroyed,
   so a full rollback of any audit batch is a query, not a recovery project (FR-8.8).
2. Safety-class attributes are never auto-applied and never single-signature, and the second
   reviewer sees the counter-evidence panel first.
3. The evidence shown is the evidence of record: that box, that document revision hash and that
   policy version are retained immutably, so "what was this person actually looking at" has one
   answer forever.

**Revisit when:** a customer has run six months of adjudications and *their own* accept-rate data
justifies a narrow, non-safety, per-attribute auto-apply. Their number, not ours.
