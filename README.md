# Errata

**Your product catalog is already wrong, and we can prove it — record by record, with the datasheet page open beside it.**

Errata is a verification layer for industrial product data. It ingests a product catalog **and** the
source documents behind it, independently re-derives every attribute, grounds each value to a
word-level span, calibrates its own confidence, and emits a ranked list of records where the catalog
and the evidence disagree — with the evidence attached.

**It grades data. It does not create data.**

---

## Why this exists

From ExtractBench (arXiv 2607.29677), measured on the same system — LlamaExtract Agentic Plus:

| Metric | Score |
|---|---|
| Value F1 — does it get the answer right? | **95.6%** |
| Word-level grounding F1 @ IoU 0.5 — can it point at the words? | **46.4** |
| Systems returning no evidence at all | **8 of 14** |

Extraction is solved. **Evidence is not.** Errata lives in the 49-point gap.

<sub>Read out of Table 3, p.9 of the paper on 20 August 2026. The paper prints one decimal place;
an earlier draft of this README carried `46.43`, which is a precision the source does not contain.
Corrected here for the same reason FR-9.1 exists — a figure quoted to a digit nobody published is
the beginning of a number nobody can check.</sub>

---

## Status

**R0 is measured except for gate 3; R1, R2 and R3 are built.** The R0 kill tests come first by
design — two of the three can end the project — and R1 was entered with gate 3 still unmeasured, on
a waiver that is written down (decision **D-3**, `PHASES.md` §10) rather than drifted into. R2 meets
all nine of its requirements and **does not meet the "public catalog" half of its exit criterion**;
that is recorded as decision **D-4** rather than relabelled. R3 ships the benchmark, the gold set,
the frozen split, the ETIM↔UNSPSC bridge, the ECLASS adapter and a leaderboard that prints our own
losing scores — and **no third party has reproduced our numbers yet**, so that half of R3's exit
criterion is open too (decision **D-5**).

| R0 gate | Requirement | State |
|---|---|---|
| 1. Equivalence suite | FR-0.1 / FR-0.2 | **PASS** — 1.30% false positives [0.44%, 3.76%] on 230 flagged records, 624 cases |
| 2. Operating point | FR-0.3 | **MEASURED — asymmetry NOT confirmed.** 46.34% word-level grounding F1 against ExtractBench's 46.4%: a dead heat. Risk is 0.00% out to 20% coverage |
| 3. Calibration coverage | FR-0.4 | **not measured** — harness built; needs SKU counts per ETIM class, which three independent hunts found are not publicly published |

Full numbers and their caveats: [docs/R0-report.md](docs/R0-report.md).

Run the gate:

```bash
errata-r0 equivalence --show failures
```

It prints a false-positive rate with a Wilson interval and exits non-zero if the project should
stop — `0` pass, `1` hold, `2` **stop**, `3` inconclusive. `< 2%` passes. `> 5%` stops the project.
That exit code is the point.

Every run also prints what the number does *not* establish: the suite has 348 of FR-0.1's 500
equivalence pairs, 13 cases are dual-labelled, and **every case was labelled by the author of the
comparator** — FR-0.1 requires independent dual-labelling before the number is quotable outside
this repository.

Read the rate next to the **coverage**, always. A comparator can flatter its false-positive rate by
refusing to commit: 20.5% of the suite is declined, and the honest miss rate once declined defects
are counted is 17.36%, not 4.91%.

### What exists

| Release | Contains | State |
|---|---|---|
| **R0** | Equivalence suite + FP harness (`errata-r0`) | gates 1 and 2 measured; gate 3 deferred |
| **R1** | Single-SKU audit, three-pane console, `errata-audit sku` | **built** — [docs/R1-report.md](docs/R1-report.md) |
| **R2** | Catalog-scale audit, groundable fraction, triage router, batch reversal (`errata-scale run`) | **built** — [docs/R2-report.md](docs/R2-report.md) |
| **R3** | Public benchmark, gold set, frozen hard tail, ETIM↔UNSPSC bridge, ECLASS BYO adapter, leaderboard (`errata-r3 reproduce`) | **built** — [docs/R3-report.md](docs/R3-report.md) |

Built and tested (**1,199 tests**): the value-semantics library, the claim schema, the
resolution-policy DSL, the disagreement taxonomy, the comparator, the R0 harness, and the R1 audit —
ingest, document register, layout with word boxes, table structure, three-stage ETIM class
resolution, blind re-derivation, the declined bucket, the ledger and the reviewer console — and the R2
catalog-scale run: the groundable fraction, the document-free structural tier, error-signature
clustering, the ranked queue and batch reversal — and the R3 benchmark: six axes, a gold set
distributed as URLs and hashes, a frozen hard-tail split with a tuning guard, the published bridge,
the ECLASS content scanner and the leaderboard.

**What R1 deliberately does not ship, and says so on every run:** the embedding retriever and
cross-encoder of FR-2.2 (interfaces only), an LLM selector (an interface, capped at five candidates
by construction), a calibration set (none exists — calibration needs reviewer decisions and nobody
has made any), and OCR (born-digital documents only).

---

## Layout

Mirrors `phase4-full-spec.md` §9.3.

```
spec/            claim schema, disagreement taxonomy, resolution-policy DSL   built
valuesem/        the value-semantics library — grammars, ontologies, units    built
comparator/      disagreement classification, equivalence resolution          built
bench/           R0 harness + equivalence suite; gold set manifests later     R0 built
docs/            ADRs, the metrology of it all                                built
audit/           R1 — the end-to-end audit and the reviewer console           built
scale/           R2 — the catalog-scale audit, ledger, triage, reversal       built
ecosystem/       R3 — the benchmark, gold set, bridge, ECLASS adapter, board  built
data/gold/       FR-9.5 — URLs, content hashes and annotation layers. No PDFs  built
```

The bridge and the ECLASS adapter live inside `ecosystem/` rather than in directories of their own:
both are a few hundred lines that share the benchmark's validation and its scanner, and splitting
them would have produced two packages whose only content was an import of the third.

## The three decisions worth reading first

- [ADR-001](docs/adr/ADR-001-audit-only-output.md) — audit-only output. We emit redlines and never
  write to a customer catalog. Enforced by types, not policy: a `Redline` cannot be constructed for
  a non-finding, and a resolution policy that deletes the safety-class escalation rule is rejected
  at load time.
- [ADR-002](docs/adr/ADR-002-grounding-representation.md) — evidence is a char span on the
  canonical text layer, with the bounding box as a regenerable projection. Upgrading OCR recomputes
  coordinates without invalidating a single claim.
- [ADR-003](docs/adr/ADR-003-cross-standard-licensing.md) — ETIM ships open under ODC-By, ECLASS
  ships as an adapter that reads the customer's own licensed dictionary, and no manufacturer
  datasheet is ever redistributed.

## Install (development)

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -e ./valuesem -e ./spec -e ./comparator -e ./bench -e ./audit -e ./scale
pytest
```

Or `bash scripts/setup.sh`, which does the whole thing and verifies it.

## Seeing it work

Numbers are the honest way to judge this, but they are not the fast way to understand it:

```bash
errata-demo
```

```bash
errata-demo --html report.html
```

Runs the real comparator over a demonstration catalog and prints a ranked reviewer queue — what it
flagged, what it deliberately stayed silent on, and what it refused to judge. Every value pair is
loaded by case id from the equivalence suite together with its citation, and the loader fails on an
unknown id, so the demo cannot drift from the data the gate measures. It covers the **comparator
only** and says so: evidence grounding is not built.

Then the R1 audit itself — one SKU, one datasheet, evidence boxed on the page:

```bash
errata-audit sku --random --html console.html
```

It picks a SKU at runtime, resolves its ETIM class in three inspectable stages, re-derives every
attribute **without ever seeing the catalog's value**, and prints a ranked redline with the word
span, the page, the box and the column header that gives the number meaning — or an honest
abstention with a machine-readable reason. The exit code is the decision: `0` supported, `1`
findings, `2` could not audit.

And the reviewer console, where a person actually works:

```bash
errata-audit serve --open
```

A local web app — ranked queue, evidence boxed on the page image with its column headers, and
Accept / Keep catalog / Escalate buttons that write to an append-only ledger. Safety-class
attributes refuse a single signature. Nothing is ever written to a catalog (ADR-001); accepting a
redline records a claim that a human accepted it.

Then the whole catalog at once:

```bash
errata-scale run --html report.html
```

10,001 records, tier by tier. **It prints the groundable fraction first** — 2.77% of that catalog has
a retrievable source document — because a defect count over a catalog where 97% of records have no
document is unreadable without it. Then the tier costs (T2 did 67 counter-evidence searches over
10,001 records, which is the whole commercial argument for auditing rather than extracting), the
error signatures with the fingerprint that grouped them, and the ranked queue with **every factor of
the ranking shown separately**, including the ones nobody supplied.

A queue can then be drained and, if it turns out to have been wrong, reversed in bulk — as a query
over an append-only ledger, with nothing deleted:

```bash
errata-scale reverse --batch <id> --by "<name>"
```

Signatures key to documents and data, **never to a company**: there is no schema field for a
supplier name and a test asserts its absence (FR-8.6). A defect count keyed to a named company,
produced by a system with a non-zero false-positive rate, is defamation with a dashboard.

> The demonstration catalog is **constructed** — no public feed for these products is available, so
> defects were injected on purpose. The datasheet is the manufacturer's own and hash-registered, and
> the spans and boxes are read from it. Both facts are printed by the CLI and rendered on the face
> of the HTML report. The same is true of the 10,001-record R2 corpus, which is generated rather
> than committed: `errata-scale corpus` rebuilds it, deterministically, at any size.

Then the benchmark, which is what makes any of the above quotable:

```bash
errata-r3 reproduce          # 24 checks against the published numbers; expect REPRODUCED
errata-r3 leaderboard        # the table, including every metric we lose on
errata-r3 gold verify        # 1,426 annotations re-derived from the documents themselves
errata-r3 bridge show --code 39121603
```

R3 reuses ExtractBench's grounding metric **verbatim** — it calls R0's implementation rather than
writing a second one — and scores five axes no published benchmark scores. The gold set ships as
URLs, content hashes and annotation layers with **no source PDF in the repository**; the hard tail
is frozen and hashed, and a declared tuning run that touches it fails the build. Two requirements
report `NOT MEASURED` and will keep doing so until a domain reviewer has been timed: reviewer-seconds
per verified attribute (FR-9.3) and the evidence-acceptance rate (FR-9.4).

> **The R3 exit criterion is "a third party reproduces our published scores from the repo."** The
> package does that on this machine, 24 of 24. Nobody outside has run it, `THIRD_PARTY_ATTESTATIONS`
> is empty, and a test asserts it stays empty. If you run it and get `DIVERGED`, that receipt is the
> most useful thing anyone could send us.

`valuesem` is installable on its own and depends on nothing else in this repo (FR-4.6).

## Licensing

Apache-2.0 for all code in this repository. ETIM class and attribute references are used under the
Open Data Commons Attribution Licence; see [NOTICE](NOTICE). No ECLASS content ships in this repo,
its container images, or its benchmark sets — the adapter reads the customer's own licensed
dictionary at runtime (ADR-003). No manufacturer datasheet PDFs are redistributed; the gold set
ships as URLs, content hashes and annotation layers only (FR-9.5).
