---
title: Errata Reviewer Console
emoji: 📐
colorFrom: gray
colorTo: red
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Catalog verification grounded to the datasheet page it came from
---

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
| 2. Operating point | FR-0.3 | **MEASURED — asymmetry NOT confirmed.** 46.34% word-level grounding F1 against ExtractBench's 46.4%: a dead heat. Risk is 0.00% out to 20% coverage. **Read the note below on whose extractor that is** |
| 3. Calibration coverage | FR-0.4 | **not measured** — harness built; needs SKU counts per ETIM class, which three independent hunts found are not publicly published |

### Whose extractor is 46.34%?

Not the one this repository ships, and that is worth a paragraph rather than a footnote.

46.34% belongs to a **table-blind baseline**: it reads a flat sequence of words and takes the
nearest token that looks like the value. `errata_audit.derive` — the extractor that actually runs —
had never been scored on the grounding metric at all. It now can be:

```bash
errata-r3 corpus score --extractor tableblind      # 46.34%, the published number
errata-r3 corpus score --extractor r1              # 100.00%  <- a tautology, not a result
errata-r3 corpus score --extractor r1-textwindow   # R1's real, comparable number
```

**R1 scores 100% and the report refuses to let you quote it.** Gold is the cell under a named
column in the row whose identity is the type designation; `derive` prefers exactly that cell. The
two are the same act performed twice. Withhold the table structure and R1 falls back to reading by
proximity — the same job the baseline does, on the same documents, with the same eight-word window
— and the comparison is this:

| | coverage | grounding F1 (whole corpus) | grounding F1 (records it answered) |
|---|---|---|---|
| table-blind baseline | 93.4% | **46.34%** | 47.97% |
| R1, table structure withheld | **9.5%** | 2.05% | 11.76% |

The gap is not a defect. It is finding N12: where the window offers competing values, the baseline
takes the nearest one and R1 **declines**, because a value picked by tie-break becomes a confident
accusation two steps later. R1 abstains on 1,196 of 1,426 records for that reason.

So the honest statement of gate 2 is not "we tie ExtractBench". It is:

> 46.34% is the score of a system that guesses when the evidence is ambiguous. The system this
> repository ships declines those records instead, and publishes the coverage it gave up to do it.

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

Built and tested (**1,307 tests**): the value-semantics library, the claim schema, the
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

### The non-functional requirements, and which of them are now checked by the build

| | Requirement | State |
|---|---|---|
| NFR-1 | Byte-identical re-runs | **tested** — a full audit run twice and diffed field by field, and once more in a second interpreter under a different `PYTHONHASHSEED` |
| NFR-2 | Extractor fingerprinting | **enforced** — the three hashes are legitimately empty for a rule-based extractor, and `ExtractorFingerprint` now *rejects* a `model_id` without them, so the day a model is wired in the omission fails the build |
| NFR-3 | Evidence durability | built (ADR-002) |
| NFR-4 | Calibration drift alarm | **built** — `errata-audit drift`. Fires on the drift fixture; **stays silent when accuracy collapses to a coin flip and every promise stays true**, which is the clause the requirement spends half its words on. Nothing real to watch until a calibration set exists (FR-7.6) |
| NFR-5 | Cost observability | **measured** — seconds are real, money is modelled from a sourced rate card. 18.9s and 0.0259¢ over 10,001 records. See the caveat below |
| NFR-6 | Data residency | **built** — `errata-scale run --residency tenant_local`. Record-level artifacts cannot leave the tenant root; an egress payload carrying a record identifier is *refused*, not filtered |
| NFR-7 | Licence hygiene | **checked on every build** — and it found one. See *Licensing* |
| NFR-8 | Value layer determinism | tested |

> **On NFR-5's numbers.** Errata's modelled cost per page processed is roughly three orders of
> magnitude below ExtractBench's 8.1¢. That is not an efficiency claim and the report refuses to
> print it as one: Errata **calls no model**, and it is not doing the same job — born-digital
> tables only, no OCR, and a fallback path that abstains rather than guessing. Both facts are
> caveats on every priced report, next to the number.

Run the whole build the way CI does:

```bash
bash scripts/ci.sh
```

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

```bash
errata-r3 licences        # NFR-7's "CI licence check on every build". It is now a build step.
```

> **⚠️ One open licence risk, and it is not small.** PyMuPDF — the library that produces the word
> list every stored `char_span` is an offset into — is **AGPL-3.0-or-later OR Artifex Commercial**.
> `errata-audit serve` is a network service, so AGPL §13 applies squarely to a product every
> `pyproject.toml` here declares as Apache-2.0. Nothing has been distributed and no service has
> been offered to a third party, so the exposure is real and not yet realised; the decision is
> recorded in [`data/licences/third-party-decisions.yaml`](data/licences/third-party-decisions.yaml)
> with the three options, printed in full on every build, and **owned by nobody yet**. It flips to
> blocking the day a wheel is published. Found by writing the check, on its first run.

Apache-2.0 for all code in this repository. ETIM class and attribute references are used under the
Open Data Commons Attribution Licence; see [NOTICE](NOTICE). No ECLASS content ships in this repo,
its container images, or its benchmark sets — the adapter reads the customer's own licensed
dictionary at runtime (ADR-003). No manufacturer datasheet PDFs are redistributed; the gold set
ships as URLs, content hashes and annotation layers only (FR-9.5).
