# `audit/` — `errata-audit`, the R1 single-SKU audit

**This is production code, not a spike.** `spike/` is throwaway scaffolding built to unblock R0
gate 2 and is scheduled for deletion; this package inherits its *findings* — word boxes rather than
cell rectangles, merged cells resolved by geometry, PyMuPDF's word ordering being stable — and none
of its code, which is what the P3 scope fence in `PHASES.md` requires.

## What it does

```
catalog record ─► document register ─► text layer + tables ─► ETIM class (3 stages)
                                                                     │
                          blind re-derivation ◄─────────────────────┘
                                   │
                     comparator ─► redline + evidence boxes ─► console ─► ledger
```

```bash
./.venv/Scripts/errata-audit.exe sku --random --html var/audit/console.html
```

The exit code is the decision, not a diagnostic: **0** audited and supported, **1** findings a
reviewer should see, **2** could not audit, **3** the run failed.

## The reviewer console (`serve`)

```bash
./.venv/Scripts/errata-audit.exe serve --open
```

A static report is a good artefact and a bad *console*: FR-7.1 says a reviewer adjudicates "without
leaving the screen", and a file cannot accept a decision. `serve` is the same three panes with the
loop closed — a form to run an audit, a ranked queue, evidence boxed on the page, and **Accept /
Keep catalog / Escalate** buttons that write to the append-only ledger.

Closing that loop is what makes three requirements real rather than aspirational: FR-7.6 (decision,
actor, timestamp, note, persisted immutably), FR-6.1 (calibration needs labels, and labels are
adjudications — the dashboard says exactly what is still missing before a probability can honestly
be printed), and FR-9.3 (reviewer-seconds per verified attribute, timed by the page and submitted
with the decision).

Standard library only: no framework, no CDN, no build step. It binds to **127.0.0.1** and has no
authentication, so binding it anywhere else needs `--allow-remote` and a sentence explaining why.
**Accepting a redline writes a claim to Errata's ledger — never to a catalog** (ADR-001).

## The four things this package will not do

1. **It never sees the catalog's value before re-deriving one** (FR-3.4). There is no parameter on
   `derive()` through which it could, and a test pins the signature.
2. **It never emits a value without a span** (FR-3.2). `emit_extracted_claim` raises; the
   alternative is an `Abstention`, which is a different type with no value to misread.
3. **It never skips silently** (FR-6.2). Every attribute produces an outcome and every decline
   carries exactly one machine-readable reason.
4. **It never writes to a catalog** (ADR-001). The output is a redline addressed to a human, with
   the case against itself stated first.

## What it does not have, stated plainly

- the embedding retriever and cross-encoder of FR-2.2 — **interfaces, no implementation**;
- an LLM selector — an interface, capped at five candidates by a function that raises;
- a calibration set (FR-6.1) — **none exists**, because calibration needs reviewer decisions and
  none have been made. Confidences are raw evidence-quality scores and print as such;
- OCR — born-digital documents only; a scan is declined with a reason.

## Layout

```
src/errata_audit/
  ingest.py          FR-1.1  catalog records, values preserved byte for byte
  documents.py       FR-1.2  content-addressed blob store; network is opt-in
  layout.py          FR-1.4  canonical text layer, word boxes, column bands (FR-1.6)
  tables.py          FR-1.5  cells with row/column-header roles, merged cells by geometry
  etim.py            FR-2.1  ETIM release loader (UTF-16-LE, ';'), attribution carried
  classify.py        FR-2.2  retrieve -> rerank -> select, and the abstention (FR-2.3)
  derive.py          FR-3.x  blind, span-required, schema-constrained re-derivation
  counterevidence.py FR-7.4  the case *for* the catalog's value -- never empty
  confidence.py      FR-6.x  Platt calibration, reliability diagram, risk-coverage
  audit.py                   the orchestration and the outcome types
  ledger.py          FR-8.2  append-only claims, adjudications, no update or delete
  console.py         FR-7.x  three panes, boxes on the words, headers in a second colour
  cli.py             FR-7.9  errata-audit
  web.py             FR-7.1  the console as a local web app -- queue, evidence, decisions
  config/            the class allow-list and the attribute map -- configuration, not code
  demo/              the demonstration catalog and its provenance

tools/               generators and diagnostics, not shipped
tests/               192 tests; the PDFs are built at test time, never committed
```

## The demonstration catalog

`demo/catalog.csv` is **constructed**. The datasheet is ABB's own and hash-registered; the values
Errata re-derives and the boxes it draws are read from it, but no public ABB catalog feed exists, so
the thing under audit was generated by `tools/build_demo_catalog.py` with defects injected on
purpose. Every row's intent is recorded in `demo/provenance.yaml`, mutation is by `sha256(sku)` so
it is reproducible without a seed, and the caveat is printed by the CLI and rendered on the face of
every HTML report. Detection rates from it describe a population we created.

Full numbers and the four findings R1 produced: `docs/R1-report.md`.
