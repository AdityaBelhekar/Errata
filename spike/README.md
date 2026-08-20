# spike/ — FROZEN 20 August 2026. THROWAWAY. Read this before touching anything in here.

> ## ❄️ FROZEN
>
> **This directory takes no further changes.** P3's rule 5 says the spike is *deleted or frozen*
> once gate 2 has a number. It has one — word-level grounding F1 **46.34%** against ExtractBench's
> **46.4%**, AURC 0.3370, from the 1,426-record corpus this code produced — so the spike's job is
> finished.
>
> **Frozen rather than deleted, for one reason:** `build_corpus.py` is the only thing that can
> regenerate `var/spike/corpus.yaml`, and a measured gate whose corpus cannot be rebuilt is a
> measurement nobody can check. Deleting the code would make R0 gate 2 unreproducible, which is a
> worse outcome than keeping 900 lines nobody imports.
>
> **What "frozen" means, concretely:**
>
> - no new features, no refactors, no tidying — a change here is a change to a measurement's
>   provenance, and the correct response to wanting one is to write the R1 version instead;
> - **nothing imports it**, and `audit/tests/test_boundaries.py` fails the build if anything starts;
> - R1 (`audit/`) inherited its **findings** — word boxes rather than cell rectangles, merged cells
>   resolved by geometry, PyMuPDF's word ordering being stable — and **none of its code**, which is
>   what the P3 fence required;
> - the R1 pipeline found two things the spike's approach got wrong, both now fixed in `audit/` and
>   deliberately **not** back-ported here: the "20 words per page" born-digital rule mislabels a
>   thin page as unreadable (N-series, `layout.py`), and nearest-token fallback fabricates a value
>   when the window holds competing candidates (finding N12).

**This is not a product component. It is scaffolding, and it is scheduled for deletion.**

## Why it exists

R0 gate 2 (FR-0.3) cannot be measured without predicted values and predicted bounding boxes. Those
come from the grounding pipeline (FR-1.2–1.5), which is R1 work — and R1 is gated on gate 2
reporting a number. `HANDOFF.md` §9 states the circularity and does not resolve it.

Decision **D-2** (`PHASES.md` §10) resolved it: build the narrowest possible pipeline that produces
the six columns FR-0.3 needs for a corpus of real MCB records, and nothing else. That is this
directory.

## The rules that keep it throwaway

1. It lives here, not in a distribution. It is not `pip install`-able and **nothing depends on it**.
2. **R1 may inherit its findings, not its code.** What it teaches — which documents defeat the
   layout pass, what fraction of values ground cleanly, where table detection fails — is the
   valuable output. The code is scaffolding.
3. It never writes to `bench/`, `spec/`, `valuesem/` or `comparator/`. It imports them read-only.
   A change needed in one of those is a real change, reviewed on its own merits, with tests.
4. It handles born-digital MCB datasheets from named manufacturers. It does **not** handle scans,
   fold-outs, or "documents" in general, and it must not grow to.
5. When gate 2 has a number, this is deleted or frozen. Not "refactored into R1".

## What is deliberately NOT here

No console, no ledger, no catalog ingest, no ETIM class resolution, no triage router, no
calibration beyond a raw confidence number. If any of those appears, the fence in `PHASES.md` §P3
has failed.

## The one exception, taken deliberately

The **document register** is production code in `errata_spec.registry`, not here.
`Evidence.doc_revision_sha256` is a required field that nothing previously produced, so a
throwaway version would mean building it twice and having two answers to "what document was this".

## The independence rule — the thing that makes the measurement mean anything

Gold labels and predictions are produced by **deliberately different mechanisms**:

| | Method | Sees |
|---|---|---|
| **Gold** | table structure — cell text, cell bbox, column header | the document's tables |
| **Prediction** | flat char-indexed text layer, pattern matched near an anchor token | linear reading order only |

The predictor is **table-blind**. It cannot see cells, columns or row boundaries, so it makes the
mistakes a real extraction system makes: picking a value from an adjacent column, latching onto the
wrong row, failing where a cell is merged. If gold and prediction shared a mechanism they would
agree by construction and the grounding number would be worthless.

**FR-3.4 is enforced structurally**: `predict.py` never receives the catalog value or the gold
value. There is no parameter through which it could.

## Running it

```bash
./.venv/Scripts/python.exe -m spike.build_corpus
```

```bash
./.venv/Scripts/errata-r0.exe operating-point --corpus var/spike/corpus.yaml
```
