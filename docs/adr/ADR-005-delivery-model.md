# ADR-005 — Delivery model: one Python process serves everything

**Status:** Accepted · **Date:** 21 August 2026
**Closes:** open question Q1, recorded in the test register as blocker B-3.

## Context

Q1 — local tool, hosted SaaS, or a split — has been listed as *the* blocking open question in five
consecutive reports. Everything downstream hangs on it: authentication, tenancy, data residency,
telemetry consent, and the copyright posture of holding a customer's catalog beside a
manufacturer's PDF, which is a legal question rather than an architectural one.

**The decision was in fact already made, in code, and never written down.** `web/app/vite.config.ts`
builds to `web/landing/` with this comment:

> "Builds to `web/landing/`, which the Python console server already serves as static files. One
> server, one origin, no second runtime — the delivery model stays 'a Python process serves
> everything' (FE-SYSTEM-REVIEW §4, Q1 → C)."

So the situation was worse than "undecided". It was **decided, implemented, depended upon, and
unratified** — which is the state in which a decision gets reversed by accident, because nobody can
point at the thing that says it was a decision.

This ADR does not choose the delivery model. It records the one the code has been built on and
states what follows from it.

## Options considered

| | Option | Consequence |
|---|---|---|
| **A** | Hosted SaaS | We hold the customer's catalog and the manufacturers' PDFs on our infrastructure. That is a copyright and data-residency position requiring legal review that has not happened, and it makes the product unusable by exactly the customers whose data is most sensitive. |
| **B** | Split: local extraction, hosted queue | Two runtimes, two deployment stories, two threat models, and a synchronisation problem between them. The most work, and it forecloses nothing that C forecloses. |
| **C** | **Local: one Python process serves everything** | The customer's data never leaves their machine. No auth, no tenancy, no residency question — not because they are solved but because they do not arise. Costs: no telemetry without a consent surface built for it, no central benchmark, and updates are a package install. |

## Decision

**C.** A single Python process serves the console, the static site and the built landing page from
one origin. There is no second runtime and no network dependency at run time.

This is what the code already does. What this ADR adds is the *consequences*, which were being
inherited without being examined:

1. **No authentication, by design and now on the record.** The console binds to localhost and
   serves one operator. It is not multi-user and must not grow a user model without a new ADR — a
   half-built auth system on a tool that assumed none is worse than either end state.
2. **The frontend build output is committed** (`web/landing/`). A Python-only install has no Node
   and cannot build it, so the thing that ships must be the thing in the tree. Committed build
   output drifts; `scripts/ci.sh` gates on a rebuild producing no diff, which converts the drift
   into a failing build. That gate exists *because* of this decision.
3. **Every asset is same-origin.** The CSP is `default-src 'none'` and there is nothing off-origin
   to talk to. Any future feature that needs a third-party origin contradicts this ADR and needs
   its own.
4. **FR-9.3's telemetry has no home yet.** Instrumenting a reviewer is privacy-sensitive by nature,
   and on a local tool there is no channel to send it down and no consent surface to ask through.
   Whatever is built must be opt-in and local-first, and it is blocked on a design that does not
   exist. Recorded here rather than left as an assumption that telemetry "will be added later".
5. **No central benchmark and no shared calibration.** A local tool cannot pool adjudications
   across customers. This is a real product cost of C and it is accepted: the alternative is
   holding other people's catalogs to improve our numbers, which is the thing the product exists to
   argue against.

## Consequences for the open questions this unblocks

- **Q4 (reviewer identity, cryptographically)** is now scoped to a single-operator machine. That is
  a much smaller problem than a hosted one, and it is no longer blocked.
- **Q5 (offline for 3-hour sessions)** is largely answered: a local tool is offline by
  construction. What remains is document fetching, which is already content-addressed and cached.
- **Q3 (the time model)** is **not** answered by this and remains the expensive one.

## Reversal

If this is ever revisited, the reversal is not a deployment change. It is auth, tenancy, residency,
a threat model for holding third-party copyrighted documents, and a consent surface — none of which
exist. That cost belongs in the argument for reversing, which is why it is written here rather than
discovered afterwards.
