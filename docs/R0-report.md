# R0 — kill test report

**Generated from:** `errata-r0 equivalence` · **Suite:** `equivalence/0.1.0` · **Date:** 19 August 2026

R0 gates everything. Per PRD §4 and spec §13, two of these three tests can end the project, and no
R1 work starts until all three report numbers. **One of three has a number.**

---

## Gate 1 — Equivalence suite (FR-0.1, FR-0.2) · MEASURED · **PASS**

624 hand-labelled pairs across materials, threads, unit frames, tolerances, ingress codes,
packaging frames and controlled vocabularies. Every case cites the standard that makes its label
true; a test fails the build if any case lacks a source.

| Metric | Result | Threshold |
|---|---|---|
| **False positives, measured on flagged records** | **1.30%  [0.44%, 3.76%]  (3/230)** | < 2% pass · > 5% stop |
| The same rate under the narrow §6.1 reading | 1.30%  [0.44%, 3.76%]  (3/230) | — |
| **The same rate with the dual-labelled cases resolved against us** | **4.78%  [2.69%, 8.36%]  (11/230)** | see below |
| False positives over no-defect pairs | 0.86%  [0.29%, 2.51%]  (3/347) | — |
| Missed defects (answered wrong) | 5.26%  [3.16%, 8.64%]  (14/266) | — |
| Missed defects (including declined) | 17.67%  [13.56%, 22.70%]  (47/266) | — |
| Accusations on non-defects | 0.87% (2/230) | — |
| Coverage (not declined) | 79.49%  [76.14%, 82.47%]  (496/624) | — |
| Exact-label agreement | 87.34%  [84.50%, 89.72%]  (545/624) | — |

Intervals are Wilson score, 95%. Regenerated from the harness on 19 August 2026 (P1).

### The PASS is real, and it is conditional

Read the third row. 8 of the findings above sit on cases carrying a
second label that says the finding should not have been raised. `Case.accepted` unions the classes
of both labels, so those cases score PASS whichever way the comparator answers.
Resolved against the comparator, the rate is **4.78%** — above the
2% pass threshold, with an upper bound past the 5% stop threshold.

The four sharpest are a quantity word against a container noun **at the same quantity**
(`Dozen` vs `Box of 12`, `Pair` vs `Box of 2`, `Hundred` vs `Box of 100`), resolved as a SEV-1
packaging-frame error — a class whose own stated harm is that the line gets priced wrong, which
cannot happen when twelve equals twelve.

The gate verdict still comes from the strict metric (ground rule 8). But the condition attached to
it is a set of judgment calls made by **the same author who wrote the comparator**, which is
exactly what FR-0.1's independent dual-labelling exists to settle. Quote the headline with this
band attached, or do not quote it.

### Denominators

347 no-defect + 266 defect +
11 straddling = 624. The straddling cases carry labels
spanning defect and no-defect, so they appear in neither supporting rate.

**Read the false-positive rate next to the coverage, always.** A comparator can flatter its FP rate
by refusing to commit. 20.5% of this suite is declined, and 33 of the declines are real defects the
customer would never have seen — which is why the honest miss rate is 17.36% and not 4.91%.

### Why the strict and narrow readings agreeing is the point

Both columns read 1.30%. They have not always agreed, and the history is the most important thing
on this page:

| Suite state | FP rate | Gate | What it meant |
|---|---|---|---|
| Seed, 175 cases | 0.00% | PASS | **Meaningless.** The suite was written alongside the code it grades and never challenged it. |
| +5 adversarial suites, 510 | 1.57% | PASS | First real signal; caught a silent unit-conversion bug. |
| +threads suite, 624 | 7.50% | **STOP** | 15 new false positives, four concrete root causes. |
| after fixing the thread parser | 1.33% | PASS | The *narrow* reading only. |
| after fixing the gate's accounting | **6.22%** | **STOP** | The honest number. The metric had been routing around its own instruments. |
| after fixing the over-resolutions | 1.38% | PASS | Both readings agreed for the first time. |
| **after the P1 comparator fixes** | **1.30%** | **PASS** | Current. Denominator grew with *correct* findings. |

The decisive event was the **accounting fix**, not any parser fix. Findings raised on `undetermined`
pairs were being dropped from the metric's numerator by branch order while staying in its
denominator, so one bad redline improved the rate at both ends. `CaseResult.accusatory` — the one
instrument built to detect "a reviewer sees a false accusation" — fired **zero times across 624
cases** and was dead code. A gate that cannot fail is not a gate.

### What this number does not establish

Printed with every run, and reproduced here because a gate result quoted without them is exactly
the kind of confident-but-unqualified figure this product exists to find in other people's data.

- FR-0.1 asks for **500 equivalence pairs**; the suite has **348**. It asks for **500 genuine
  contradictions**; the suite has **216**. The interval width above is the honest size of that
  shortfall.
- **13 cases are dual-labelled** — a second reading was accepted as defensible — which makes the
  gate marginally easier to pass than a single-label suite would.
- **Every case was labelled by the author of the comparator.** FR-0.1 requires independent
  dual-labelling before this number is quotable outside this repository.
- Three cases are pinned as `KNOWN_FALSE_POSITIVES` (units: identical-interval ×2,
  temperature-delta ×1). They are the entire numerator. Shrinking that set is progress; growing it
  silently is how a gate stops meaning anything.

### The seed-vs-adversarial contrast

The 175-case seed suite still scores **100% pass**. The 449 adversarial cases decline at roughly six
times the rate and produced **every bug found so far**. That contrast is Phase 5's warning
demonstrated: a suite written alongside the code it grades encodes the same blind spots twice.

The a/b symmetry result is the one figure here defensible without qualification: **624 pairs
swapped, zero ordering violations**, with all asymmetries landing on documented design intent.

### Defects the suite has found

**First honest run — ten bugs, all fixed:**

| # | Defect | Consequence had it shipped |
|---|---|---|
| 1 | Unit dimensionality compared as a **rendered string**. Pint prints `N·m` and `Nm` with different dimension orderings. | Every torque value incommensurable with every other torque value. |
| 2 | `IP-67` failed the ingress prefilter | A common spelling routed to the Declined bucket. |
| 3 | `IP69K` vs `IP69` read as equivalent | An over-claimed ISO 20653 rating passing as agreement. |
| 4–7 | Constrained parser chains excluded the generic-term parser, so `Threaded` was unparseable **in a thread field** | The most common granularity mismatch became an abstention instead of a finding. |
| 8 | `3/8 in` vs `230/400 V` reported as a **contradiction** | A fabricated finding from comparing inches against volts. |
| 9–10 | Two suite labels contradicted the documented direction convention | Fixed by testing **both directions** rather than relabelling to suit the code. |

**Adversarial expansion — the order-of-magnitude one:**

`m2 = meter ** 2` made the alias prefixable, so `um2` parsed as micro×(m²) = 1e-6 m² instead of
1e-12 — **wrong by 10⁶ on conductor cross-section**, the most standard mm² field in electrical data.
`km2` was wrong by 10³. The regression test pins the *factors*, because the next missing spelling
will not be `um2`.

**P1 pass (19 Aug 2026) — four fixed:**

| # | Defect | Class |
|---|---|---|
| 9 | Hot-dip galvanised ≡ zinc-plated, one ontology group with a caveat that never reached the verdict | Silent **false negative** on a corrosion-performance attribute |
| 10 | `1.4404` ≡ `1.4435`, two aliases of one group with non-nesting Mo bands | Silent **false negative** |
| 13 | `MCB`/`RCBO`/`RCCB` had no vocabulary at all — 9 declined cases | Coverage gap on the device class gate 2's own corpus is named for |
| 15 | `CQ`→Hundred, `RL`→Roll, `DZ`→Dozen all wrong, and all eight container codes are **Rec 21**, not Rec 20 | Citation defect in the highest-severity attribute family |

### Citation integrity

An audit of the adversarial suites found that **three of five authoring agents fabricated standards
citations**, and every one had self-reported "0 UNVERIFIED citations". 47 source fields were
corrected; zero labels were changed. The signature: each agent was disciplined about facts it knew
were shaky and careless about locators it assumed nobody would open.

**Treat any confident citation in this repository as a claim to check.** `threads_hard.yaml` — the
largest suite file, 114 cases — has never been citation-audited.

---

## Gate 2 — Operating point (FR-0.3) · MEASURED · **ASYMMETRY NOT CONFIRMED**

Measures the one assumption everything downstream of spec §1 rests on: that auditing has a
materially better precision/coverage operating point than extraction does at the same grounding
quality. **It has now been measured, and on this corpus it does not hold.**

**Corpus:** 1,426 records from two ABB S200 published datasheets, hash-registered in
`data/reference/manifest.json`. Gold values and evidence boxes read from the documents' own
ordering tables; predictions produced by a deliberately table-blind extractor; disagreements
decided by the real `errata_comparator`.

### The comparison FR-0.3 asks for — at full coverage

| Metric | Errata | ExtractBench best | |
|---|---|---|---|
| **Word-level grounding F1** | **46.34%** (conservative 43.72%) | **46.4%** | dead heat |
| Value F1 | 67.15% | 95.6% | well behind |
| Page-level grounding F1 | 67.15% | 84.9% | behind |

**Verdict: ASYMMETRY NOT CONFIRMED.** The margin is -2.68pp on the
Wilson lower bound. Per §13 this is a stop-or-narrow signal, and per ground rule 4 it is reported
as found.

### The selective operating point — where §0.3's mechanism 1 survives

| coverage | n | word F1 | disagreement precision | selective accuracy |
|---|---|---|---|---|
| 20% | 286 | 100.00% | n/a | 100.00% |
| 40% | 571 | 53.77% | 96.49% | 53.77% |
| 60% | 856 | 52.80% | 46.83% | 52.80% |

Risk–coverage AURC **0.3370** (lower is better), curve emitted to
`var/spike/risk-coverage.csv`. **Risk is 0.00% out to 20% coverage** and climbs to 55.19% at full
coverage: the confidence signal genuinely separates the fields the audit knows from the ones it
does not. That is §0.3's mechanism 1 — an audit needs only one workable low-coverage operating
point to be useful — and it is the strongest thing in this result.

**It is not, however, a win over the baseline.** ExtractBench's 46.4% is a full-coverage figure,
so only the full-coverage row can be set against it. Comparing the selective row to it was a real
defect in this harness (finding N9): the gate first reported "clearing the baseline by 52.24pp,
Proceed", from a 20% slice that is almost entirely order codes.

### Per-attribute — where the grounding actually fails

| attribute | n | word F1 | value F1 | abstained |
|---|---|---|---|---|
| `order_code` | 292 | 100.00% | 100.00% | 0 |
| `packing_unit` | 292 | 12.33% | 16.44% | 0 |
| `poles` | 275 | 3.51% | 10.09% | 94 |
| `rated_current` | 292 | 98.63% | 98.63% | 0 |
| `weight_kg` | 275 | 5.45% | 100.00% | 0 |

**`weight_kg` is the finding.** Value F1 100%, word-level grounding F1 5.45%: it gets the answer
right every time and cites the wrong instance of it, because `0.125` appears in hundreds of rows
and a table-blind extractor picks the nearest one. That is ExtractBench's central claim reproduced
independently on different documents with a different system — *the field can get the answer right
and cannot show where it came from.*

### What this does not establish

- **The catalog is constructed.** No real ABB catalog was available; catalog values were built
  from gold with an 18% injected-defect rate and a 12% cosmetic-but-equivalent rate. Disagreement
  precision measures the comparator against defects we chose. The **grounding** half is fully
  empirical.
- **Gold is document-derived, not expert-labelled.** FR-0.3 asks for 200 *hand*-labelled records.
  These are read mechanically from table structure — faithful, but not a domain expert's judgment,
  and it shares gate 1's weakness: one author wrote both the labeller and the thing measured.
- **One manufacturer, two documents, born-digital.** No scans, no fold-outs, no cross-page tables.
- **The extractor is deliberately unsophisticated.** "Errata does not beat published extraction"
  is a statement about *this spike*, not a proof that auditing cannot. A stronger extractor is the
  obvious next experiment, and the corpus is now in place to score it.

---

## Gate 3 — Calibration coverage (FR-0.4) · **NOT MEASURED**

Arithmetic only, no new code required, and §8.3 expects it to hurt. Needs one file:
`class_id, sku_count`. `--distribution` is already wired.

**Data availability was investigated on 19 August 2026. The counts are not publicly reachable.**

- ✅ The **ETIM model is free and downloadable** — ETIM 10.0 ALL-SECTORS, released 2024-12-05, ODC-By,
  no login, direct from `etim-international.com/downloads/`. 5,640 classes in 159 groups. This is
  the **taxonomy only**: class id, group id, description. There is no SKU count anywhere in it.
- ❌ ETIM publishes no per-class product statistics.
- ❌ 2BA (the Dutch datapool, 4M+ product records) gates statistics behind membership.
- ❌ No open dataset of ETIM-classified products with counts was found.

Two routes remain: scrape an ETIM-adopting distributor and crosswalk to class ids (the counting is
easy, the crosswalk is the difficulty — and **an inferred crosswalk produces a number that looks
measured and is not**, which is strictly worse than `NOT_MEASURED`), or obtain a datapool export.

Structural finding on synthetic data, pending real numbers: greedy allocation calibrates **5.95% of
classes / 77.39% of SKUs** at a realistic 5,000-label budget. Volume is calibratable; the taxonomy
is not. This is a Zipf artefact and a real distribution will likely reproduce it directionally —
expect gate 3 to *confirm* rather than surprise.

**Kill condition:** single-digit percentage coverage → re-scope from a catalog-wide audit to a
narrow set of named high-volume classes, and reprice accordingly.

---

## Reproducing

```bash
errata-r0 status
```

```bash
errata-r0 equivalence --show failures
```

```bash
errata-r0 equivalence --family threads --show failures
```

Exit code is the decision, not a diagnostic: `0` pass · `1` hold · `2` **stop** · `3` inconclusive.

To see the comparator working on a sample catalog rather than reading numbers about it:

```bash
errata-demo --html report.html
```

The demo covers the **comparator only**. It says so on its own face, and it loads every value by
case id from this suite so it cannot drift from what is measured here.
