# ADR-004 — An OCR layer over a scan is not evidence

**Status:** Accepted · **Date:** 21 August 2026
**Closes:** FE-2.5 defect G-2 / FE-TEST-REGISTER B-5.

## Context

`errata_audit.layout`'s own scope statement says the pipeline handles born-digital PDFs, and that a
document needing OCR is declined rather than guessed at:

> "A scanned page produces a layer with no words, and `TextLayer.is_born_digital` says so at the
> point of extraction… There is no OCR here, and a document that needs one is declined with
> `LAYOUT_UNREADABLE` rather than guessed at."

That sentence describes a scan **without** an OCR layer. It is silent on the case that actually
occurs in this corpus: a scan **with** one. `H28-1957-Part-I.pdf` is 100% image area, carries an
OCR text layer, and reports **161,731 words**. `is_born_digital` returns `True`, nothing declines
it, and the pipeline proceeds to ground claims against it.

Two things are wrong with proceeding, and only the second is obvious:

1. **The text is a guess.** OCR output is a model's reading of pixels, not the document's own
   character stream. Grounding a claim in it produces a citation to something the document does
   not say — which is the *fabricated finding* the repository's ground rules place above all other
   failures.
2. **The boxes cannot land.** An OCR word box is where the OCR engine thinks the word is. It is not
   derived from the same text stream `Evidence.char_span` indexes into, so the projection that
   FE-2.5 spent its whole budget getting right has nothing true to project.

This is the same class of defect as G-1 — correct on the corpus we happen to have, wrong on the
corpus FR-9.6 commits us to — and it was found the same way, by asking what the code does on a
document nobody had run it against.

## What was measured

Image-area ratio per page: the summed area of image blocks (`get_text("dict")` blocks of type 1)
over the page area, clamped to 1.0.

| Document | Pages | Max page ratio | Mean ratio | Words/page |
|---|---:|---:|---:|---:|
| `abb-s200-2CDC002142D0207.pdf` | 16 | **0.191** | 0.035 | 263 |
| `abb-s200muc-1SXP403008B0202.pdf` | 9 | **0.182** | 0.064 | 262 |
| Manufactured OCR-over-scan fixture | 1 | **1.000** | 1.000 | 13 |

The separation is not marginal. Real born-digital datasheets — including their photographs, wiring
diagrams and dimension drawings — top out at **0.191**. A scanned page is **1.0**. Any threshold in
that gap classifies both correctly, so the choice of threshold is not a tuning decision and must
not become one.

**Limitation, stated rather than buried:** only 2 of the corpus documents are present on the
machine where this was measured; `var/` is gitignored under FR-9.5 and `H28-1957-Part-I.pdf` was
not available. The born-digital end of the table is therefore 2 documents and 25 pages, not the
corpus. The scanned end is a manufactured fixture, not the real document. **This measurement must
be re-run over the full corpus** (`bash scripts/fetch_reference_data.sh`, then the measurement in
`audit/tests/test_layout_ocr.py`) and this table replaced with the real distribution before any
coverage number derived from it is published externally. The decision below does not change under a
wider sample unless a born-digital page above 0.60 exists, which would itself be the finding.

## Options considered

| Option | What it does | Why not |
|---|---|---|
| **A.** Leave it | OCR text is grounded as if it were the document | Fabricated findings. Rejected on the ground rules, not on cost. |
| **B.** Tighten `is_born_digital` to require words **and** low image area | One predicate | Conflates two different failures. `is_born_digital` currently distinguishes *unreadable* (no words) from *thin* (few words), and its docstring records that this distinction took a revision to get right and that a reason which misdescribes what happened is worse than no reason. Folding a third case into it destroys that. |
| **C.** Separate page-level image-area signal + its own declined reason | Two orthogonal predicates, two distinct reasons | Preserves B's careful distinction and names the new failure accurately. |
| **D.** OCR it properly | Actually read the scan | Out of scope for R1 and a different product decision. Not foreclosed by this ADR. |

## Decision

**C.**

1. `Page` gains `image_area_ratio: float`, measured at extraction from the renderer's own block
   list — not estimated, and not configurable.
2. `IMAGE_DOMINATED_RATIO = 0.60`. Chosen as roughly the midpoint of a gap running from 0.191 to
   1.0, which puts it **3.1x above the highest born-digital page observed** and 0.4 below a scan.
   It is set from the separation, not fitted to a coverage target.
3. `TextLayer.is_ocr_over_scan` is true when the layer has words **and** every page carrying words
   is image-dominated. Every page, not most: a document with one scanned insert among 15 typeset
   pages is not an OCR-over-scan document, and declining it whole would lose 15 good pages.
4. A new `DeclinedReason.OCR_TEXT_NOT_EVIDENCE`, distinct from `LAYOUT_UNREADABLE`. The layout is
   not what defeated us — the text is legible, and that is exactly the problem.
5. `is_born_digital` is **unchanged**.

## Consequences

**Measured coverage will fall**, by however much of the corpus is OCR-over-scan. On the two
documents available here the delta is zero, because neither is a scan; on the full corpus it will
not be, and `H28-1957-Part-I.pdf`'s 161,731 words are 161,731 words that were previously available
to ground against and now are not.

That number going down is the point. It was never grounding; it was grounding-shaped. The old
number was higher and wrong, and the honest one is the one worth publishing.

**This is the ADR's load-bearing clause:** if `IMAGE_DOMINATED_RATIO` is later moved in the
direction that recovers coverage, that requires a **new ADR** with the full-corpus distribution
attached and a reviewer who is not the person whose coverage number it restores. It does not
require an edit to this file. The precedent this guards against is real and in this repository —
`MIN_CONTRAST` moved from 1.5 to 1.25 after it rejected 80% of good words, which was the right
change for the right reason and is also precisely the shape of the wrong one.

**Reproduction receipts change.** `errata-r3 reproduce` must be re-run and the new numbers published
beside the old, with this ADR as the explanation, rather than the old ones being quietly replaced.

## How this is enforced in code

- `audit/tests/test_layout_ocr.py` asserts a manufactured OCR-over-scan fixture is declined, that
  both real born-digital documents are **not**, and that the threshold sits clear of both ends by a
  stated margin — so a future edit that narrows the margin fails a test rather than passing quietly.
- The decline carries `OCR_TEXT_NOT_EVIDENCE` and a sentence naming the image ratio that triggered
  it, so a reviewer reads what happened rather than inferring it.
