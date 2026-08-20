# ADR-002 — How grounding is represented

**Status:** Accepted · **Date:** 17 August 2026

## Context

Word-level evidence is the product. The representation choice determines whether evidence survives
a parser upgrade, whether it is comparable to published benchmarks, and whether a reviewer can act
on it.

The field's numbers, verified: the best system scores **84.92 page-level** and **46.43 word-level**
grounding F1, and 8 of 14 evaluated systems return no evidence at all.

## Options considered

| Option | Complexity | Cost | Scalability | Maintenance | Reviewer utility |
|---|---|---|---|---|---|
| **A.** Page-level citation only | Low | Low | High | Trivial | Poor — page-level tops out at 84.92 against 46.43 word-level, so page-only hides the actual difficulty |
| **B.** Word-level bbox only | Medium | Medium | Good | **Brittle** — every OCR/layout upgrade invalidates stored coordinates | Excellent, until the parser changes |
| **C.** Char span on canonical text only | Medium | Low | Good | Stable | Poor for scans — no visual anchor to point at |
| **D.** Dual anchor: char span primary + derived bbox projection | High | Medium | Good | Bbox is regenerable from the span | Excellent and durable |

## Decision

**D.** The char span on the canonical text layer is the primary, stored anchor. Bounding boxes are
a *projection* of that span through the versioned layout map, regenerated when the extraction layer
is upgraded.

## How this is enforced in code

- `errata_spec.claim.Evidence.char_span` is required; `bbox` is `BBox | None` and documented as
  derived, never the source of truth.
- Every `Evidence` records `extraction_layer_version`, so a projection can be recomputed against
  the map that produced it.
- `BBox.iou` implements ExtractBench's metric verbatim — a field is grounded-correct only when its
  value is accepted **and** its predicted box overlaps an accepted evidence box at **IoU 0.5**
  (FR-9.1). Reusing the metric rather than inventing one is a strategic choice: it makes our
  results directly comparable to a published leaderboard, and you do not want a metric of your own
  that nobody can check you against.
- `Evidence.row_header` and `Evidence.column_header` are first-class fields. A number in an
  engineering table means nothing without its headers, and a system that boxes `6` without boxing
  `Rated current (A)` has not explained anything (FR-7.3).

## Consequences

**Easier.** Upgrading OCR without invalidating history — coordinates are recomputed, claims are
not. Diffing evidence across document revisions. Reporting an IoU-0.5 word-level score comparable
to the published 46.43.

**Harder.** The canonical text layer becomes critical infrastructure needing its own versioning and
reproducibility guarantees. Born-digital PDFs and scans need separate projection paths. A
span-to-bbox projection failure is a new error class to handle — it routes to
`DeclinedReason.NO_SPAN` rather than to a claim without evidence.

**Revisit when:** a customer needs evidence rendered inside a viewer that only accepts static
coordinates, or a document type appears where char spans are meaningless — a pure dimension drawing
with no text layer at all.
