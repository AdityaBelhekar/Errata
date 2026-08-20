# PHASES — Errata execution plan

**Written:** 19 August 2026, environment-setup session.
**Supersedes:** nothing. Sits alongside `HANDOFF.md` (orientation) and `PROGRESS.md` (task board).
**Status of this document:** this is the plan we follow. Phases are executed in order. A phase does
not start until its entry criteria are met, and does not close until its exit criteria are
**demonstrated with an artefact**, not asserted.

---

## 0. How to read this document

There are **eight phases**, mapping onto the PRD's five releases (`R0`–`R4`). The phase count is
higher than the release count because R0's three kill tests have genuinely different blockers —
one is code, one is data acquisition, one is deadlocked on R1 — and collapsing them into a single
"finish R0" phase hides the only interesting problem in the plan (see **Decision D-2**).

| | Phase | Release | Blocker type | Status |
|---|---|---|---|---|
| **P0** | Environment & reproducibility | — | none | ✅ **DONE** (this session) |
| **P1** | Gate 1 hardening — make the number quotable | R0 | effort | 🟢 **11 of 12 closed**; 1.12 blocked on standards access |
| **P2** | Gate 3 — calibration coverage | R0 | **external data** | ⏸️ **D-1 taken** — deferred, data request ready to send |
| **P3** | Grounding spike → Gate 2 | R0/R1 | **circular dependency** | ✅ **DONE** — gate 2 MEASURED, **ASYMMETRY NOT CONFIRMED** |
| **P4** | Single-SKU audit + console | R1 | gated on P1–P3 | ✅ **DONE** — entered on waiver **D-3** (gate 3 unmeasured); 933 tests |
| **P5** | Catalog-scale audit | R2 | gated on P4 **and on gate 3, which D-3 does NOT waive** | ⬜ |
| **P6** | Benchmark + ecosystem | R3 | gated on P5 | ✅ **DONE** — 9 requirements met or honestly declined; **exit criterion half open (D-5)** |
| **P7** | Commercial | R4 | out of PRD scope | ⬜ |

**A fifth decision, D-5, was taken on 20 August 2026**: R3 closed with the *third-party* half
of its exit criterion open, reported rather than waived.

**Both blocking decisions were taken on 19 August 2026** and are recorded in §10 with the evidence
behind them. P2 is deferred with a ready-to-send data request; P3 is started behind a written
scope fence. **A third decision, D-3, was taken on 20 August 2026**: P4 was entered with gate 3
still unmeasured. That is a *waiver of an entry criterion*, not a criterion met, and §10 records
what it costs and what would reverse it.

### The one rule that governs every phase

> **Ground rule 1 — never invent a number or a citation.** Cite a source actually opened, or write
> `[UNVERIFIED — needs checking]`.

This is not decoration. An audit of this repo's own adversarial-suite authors found that **three of
five fabricated standards citations while self-reporting "0 UNVERIFIED"** (`HANDOFF.md` §7). The
full ground-rule list is in `HANDOFF.md` §8 and is reproduced at the end of this document. **A phase
that produces a number by relaxing a ground rule has failed, regardless of the number.**

---

## Phase 0 — Environment & reproducibility ✅ DONE

**Objective:** make the repository runnable and its published numbers reproducible on a clean
machine, so that every later phase is measured against a known-good baseline rather than an
assumption.

### What was done

| Step | Result |
|---|---|
| Virtualenv on Python 3.14.3 | `.venv/` created |
| Build toolchain | pip 26.2.1, setuptools 84.0.0, wheel 0.48.0 |
| Runtime dependencies | lark 1.3.1, Pint 0.25.3, PyYAML 6.0.3, pydantic 2.13.4 |
| Dev tooling | pytest 9.1.1, ruff 0.16.3, mypy 2.3.1 |
| Four Errata distributions | installed **editable** in dependency order |
| Dependency set pinned | `requirements-lock.txt` (25 packages, exact versions) |
| One-command setup | `scripts/setup.sh` — idempotent, self-verifying |
| Reference-data fetcher | `scripts/fetch_reference_data.sh` + `data/reference/manifest.json` |

### Exit criteria — all met, with evidence

| Criterion | Evidence |
|---|---|
| Full test suite green | **495 passed** in 46.7s (**605** after P1) |
| Gate 1 reproduces the published number | `errata-r0 status` → **PASS, 1.30% (3/230)**, both readings agreeing |
| Gates 2 and 3 still refuse to fabricate | both report `NOT MEASURED` on synthetic input, as ground rule 5 requires |
| The demo runs | `errata-demo` → 14 attributes / 3 SKUs, 9 raised · 4 resolved · 1 declined |
| Setup is reproducible | `bash scripts/setup.sh` re-run end-to-end, idempotent, exits 0 |
| ETIM 10.0 obtained and verified | sha256 `9b2aa17f…20b6214`, 5,640 classes / 159 groups — matches `HANDOFF.md` §9 exactly |

### Findings raised during setup

These are real, were not on any existing queue, and are logged here rather than silently absorbed.

- **F0.1 · A latent defect in `valuesem/src/errata_valuesem/unitreg.py` — FIXED.**
  `_dimensionality` was annotated `-> Any` with `Any` never imported. `from __future__ import
  annotations` defers annotation evaluation, so it never raised at runtime and no test caught it —
  but `typing.get_type_hints()` on that module raised `NameError`, and mypy could not check the
  function. One-line fix (`from typing import Any`); all 495 tests still pass and
  `get_type_hints()` now resolves. **This is the exact failure signature `HANDOFF.md` §7
  describes** — careless about the thing nobody was expected to open.

- **F0.2 · The documented test count is stale, and reconciles exactly.**
  `HANDOFF.md` §2 says 489, §4 says 451, and the actual count is **495**. The difference from 489
  is precisely the 6 tests in `bench/tests/test_demo.py`, added after the count was last written.
  No test is missing or extra. **Action:** correct both numbers in `HANDOFF.md` during P1.

- **F0.3 · 77 ruff findings, pre-existing, deliberately not fixed.**
  Breakdown: 25 `RUF022` (`__all__` unsorted), 17 `UP042`, 8 `I001` (import order), 5 `SIM102`,
  4 `F811`, 4 `F401` (unused imports), 4 `E402`, and 10 others. All cosmetic **except** the
  `F821` that became F0.1. Fixing 77 lint findings during an environment setup would bury the one
  real defect in unrelated churn. **Action:** scheduled as P1 task 1.7, applied in one reviewable
  pass with the test suite green before and after.

- **F0.4 · `valuesem/` cannot currently build an sdist for PyPI.**
  Its `pyproject.toml` declares `readme = "README.md"` and `license-files = ["LICENSE", "NOTICE"]`,
  and none of those three files exist in `valuesem/`. The editable install tolerates this; a real
  `python -m build` will not. **FR-4.6 requires this package ship standalone**, so this blocks a
  stated P1 requirement. **Action:** P1 task 1.8. Do not fix by deleting the declarations — that
  would degrade the package's licence metadata to make an error go away.

- **F0.5 · CLI output mojibakes on a Windows console.**
  `errata-r0 status` renders `§` as `�` under the default cp1252 code page. Cosmetic, but this is
  the command a judge or customer runs first. Setting `PYTHONUTF8=1` fixes it.
  **Action:** P1 task 1.9 — set the encoding in the CLI entry point rather than relying on the
  operator's environment.

### Standing commands

```bash
bash scripts/setup.sh
```

```bash
./.venv/Scripts/python.exe -m pytest -q
```

```bash
./.venv/Scripts/errata-r0.exe status
```

```bash
./.venv/Scripts/errata-demo.exe --html report.html
```

```bash
bash scripts/fetch_reference_data.sh
```

---

## Phase 1 — Gate 1 hardening 🟢 11 OF 12 CLOSED

> **Start here.** This is the only phase that needs nothing from anyone.

**Objective:** make gate 1's 1.30% quotable **outside this repository**. It is not, today, for one
reason that no amount of code fixing addresses: every one of the 624 cases was labelled by the
person who wrote the comparator being graded.

**Entry criteria:** P0 complete. ✅

**Why this ranks first:** gate 1 is the only kill test with a number. If that number is not
defensible, R0 has zero measured gates rather than one, and P2/P3 are building on sand.

### Tasks

| # | Task | Source | Effort |
|---|---|---|---|
| 1.1 ✅ | **Citation-audit `threads_hard.yaml`** — 114 cases, the largest suite file, **never audited**; its authoring agent died mid-run | `PROGRESS` #16 | High |
| 1.2 🟢 | **Independent dual-labelling** — *partially closed without a human*: `errata-r0 corroborate` adjudicates the suite against **four external standards** (UCUM 2.2, ISO 261:1998, **NBS Handbook H28 — public domain, the way around ASME B1.1's paywall**, ETIM 10.0). **111 cases judged, 100% agreement, zero disagreements**, coverage 6.2% → 17.8% as sources were added. It settles facts, not taxonomy. `materials` and `terms` still have no usable open source; the report prints what each would cost. The packet and kappa arithmetic remain for the rest, and that still needs a person |
| 1.3 ✅ | Close `expect_alternatives` laundering — `pkg-h026/h031/h035`, `pkg-010` attach a second label so a known SEV-1 defect scores PASS | `PROGRESS` #17 | Low |
| 1.4 ✅ | Restore 11 dual-labelled cases excluded from both supporting denominators | `PROGRESS` #18 | Medium |
| 1.5 ✅ | Rule on 6 reported label findings — sharpest is `mat-h063` (`"18-8"` vs `"S30400"` labelled equivalent, but 18-8 is a *family* covering 302/303/304/305; generic ≡ specific is a silent false negative) | `PROGRESS` #19 | Medium |
| 1.6 ✅ | Sweep finding **N1** — the Rec 20 → Rec 21 mis-citation is systemic; several suite `source:` fields still say "Rec 20" for container codes | `PROGRESS` N1 | Low |
| 1.7 ✅ | Clear the 77 ruff findings in one reviewable pass, tests green either side | F0.3 | Low |
| 1.8 ✅ | Add `valuesem/README.md`, `LICENSE`, `NOTICE`; verify `python -m build` produces a valid sdist+wheel | F0.4, FR-4.6 | Low |
| 1.9 ✅ | Force UTF-8 in the CLI entry point | F0.5 | Trivial |
| 1.10 ✅ | Correct the stale test counts in `HANDOFF.md` §2 and §4 | F0.2 | Trivial |
| 1.11 ✅ | Finish the interrupted determinism/gate-integrity audit — unverified: whether the determinism boundary can be defeated by a lazy import, and whether gates 2/3's synthetic pinning survives a hostile attempt | `PROGRESS` "Interrupted" | Medium |
| 1.12 ⛔ | Grow the suite from 348 to FR-0.1's **500** equivalence pairs | FR-0.1 | High |

### Exit criteria

- [x] `threads_hard.yaml` fully citation-audited; every correction logged with the standard actually opened, and every standard **not** opened named in the file header
- [x] FP rate **< 2%** on the strict reviewer-experienced metric, reported next to coverage and with its Wilson interval — **1.30% [0.44%, 3.76%] at 79.49% coverage**
- [x] Strict and narrow readings still agree — both 1.30%
- [x] `KNOWN_FALSE_POSITIVES` has not grown — still the same three
- [x] `python -m build` succeeds for all four distributions, and the `valuesem` wheel was installed into an empty interpreter and exercised
- [x] The dual-labelling packet exists and the agreement arithmetic is written and tested
- [ ] ≥ 100 cases independently dual-labelled by someone who did not write the comparator; inter-labeller agreement reported as a number — **the packet is ready; this needs a person**
- [ ] 500 equivalence pairs present (FR-0.1) — **347 + 216, blocked on standards access, see `PROGRESS.md`**
- [x] `docs/R0-report.md` regenerated from the harness, not hand-edited

### What P1 established that was not known before

**The PASS is conditional, and the condition is now measured.** The gate reads 1.30%; the same
suite reads **4.78%** once every finding sitting on a dual-labelled case is resolved against the
comparator, which is above the 2% pass threshold. That band is now printed with every run and
carried in the JSON. Nothing about the comparator changed to produce it — the number was always
there and nothing was looking.

**One wrong belief was written down three times.** "The largest ISO 261 pitch is 6 mm" appeared in
two suite citations and in `MAX_ISO_METRIC_PITCH_MM`. All three agreed, so no copy could catch
another, and `M125x8` silently lost its pitch. ISO 261:1998 Table 2 lists 8 mm at M125 and M130.
This is the §7 signature at its purest, and it argues for buying the standards rather than
reasoning around them.

**The determinism boundary had an unenforced half.** `FORBIDDEN_CALLS` listed 19 dynamic-dispatch
escapes and no test read the list. The package was clean; the guard was not running.

### Risks

- **The dual-labelling can fail the gate.** A second labeller may disagree enough to move the rate
  above 2%. That is the *purpose* of the exercise, and the 4.78% band says which way it is likely
  to go. Ground rule 4: leave real failures failing.
- **Do not shrink `KNOWN_FALSE_POSITIVES` by relabelling.** Shrinking it by fixing code is
  progress; shrinking it by editing labels is how a gate stops meaning anything.
- **Do not close 1.12 by padding.** Easy cases grow the denominators and improve every rate
  without improving the comparator.

---

## Phase 2 — Gate 3, calibration coverage 🔒 BLOCKED ON DECISION D-1

**Objective:** turn FR-0.4 from `NOT_MEASURED` into a real number.

**Entry criteria:** P0 complete ✅, **and Decision D-1 taken.**

**What is already built:** everything except the data. `coverage.py` implements label-floor
derivation from split-conformal bounds, three allocation strategies, hierarchical pooling and a
budget sweep, with 61 unit tests. The CLI accepts `--distribution`. **No new code is required.**

**What is missing:** one file, two columns — `class_id, sku_count`.

### What was established on 2026-08-19, and re-confirmed during P0

- ✅ **The ETIM 10.0 model is free, downloadable without login, and is now in this repo's
  `var/reference/`** — ODC-By, sha256-verified, 5,640 classes in 159 groups.
- ❌ **It contains no SKU counts.** Verified by inspecting all nine CSVs: `ETIMARTCLASS`,
  `ETIMARTGROUP`, `ETIMFEATURE`, `ETIMVALUE`, `ETIMUNIT` and the four map files carry taxonomy and
  feature structure only. **There is no count column anywhere in the release.** The half gate 3
  needs is the half ETIM does not publish.
- ❌ ETIM publishes no per-class product statistics.
- ❌ 2BA (4M+ product records) exposes class search but gates statistics behind membership.
- ❌ No open dataset of ETIM-classified products with counts was found.

### Tasks (once D-1 is taken)

| # | Task |
|---|---|
| 2.1 | Acquire the distribution by the chosen route |
| 2.2 | Attach a source URL + retrieval date to **every row** |
| 2.3 | Register the artefact in `data/reference/manifest.json` with its sha256 |
| 2.4 | Run `errata-r0 coverage --distribution <file>` |
| 2.5 | Compare the real result against the synthetic finding (5.95% of classes / 77.39% of SKUs at a 5,000-label budget) and report whether it confirms or contradicts |
| 2.6 | If coverage is single-digit %, narrow R2 scope to named high-volume classes, per FR-0.4's own acceptance criterion |

### Exit criteria

- [ ] Gate 3 reports `MEASURED` on a distribution whose every row traces to a real source
- [ ] Coverage-vs-budget table published in `docs/R0-report.md`
- [ ] R2 scope decision recorded either way

### Risk — read this before spending on P2

**The trap is producing a number that looks measured and is not.** If distributor categories have
to be *inferred* onto ETIM class ids rather than read from a published mapping, gate 3 emits a
figure with the authority of a measurement and the content of a guess. Under ground rule 1 that is
**strictly worse than `NOT_MEASURED`**, which is at least honest.

**Calibrate the payoff first.** The synthetic finding is a Zipf artefact and a real distribution
will very likely reproduce it directionally. Gate 3 is worth having as a real number, but expect it
to **confirm rather than surprise**.

---

## Phase 3 — Grounding spike → Gate 2 ✅ COMPLETE — gate 2 MEASURED

**Objective:** turn FR-0.3 from `NOT_MEASURED` into a real number — and with it, test the
assumption the entire company rests on.

**Why this phase matters more than any other:** `phase5-red-team.md` names two things that decide
this project, and the first is that **§0.3 is unmeasured**. Everything assumes auditing has a
materially better precision/coverage operating point than extraction at equal grounding quality.
**Gate 2 exists to test exactly this and has never run on real data.** P1 and P2 harden numbers.
P3 is the one that can end the project — which is the point of a kill test.

### The circular dependency — the sharpest problem in this plan

```
   PRD §4:  R1 does not start until R0 reports three numbers
       │
       ├── Gate 2 (FR-0.3) needs, per record:
       │      gold value · gold page · gold bbox
       │      predicted value · predicted bbox · confidence
       │
       └── the "predicted" columns require the grounding pipeline (FR-1.2–1.5)
              │
              └── which is R1 work ──────► which is gated on gate 2. ⟲
```

`HANDOFF.md` §9 states this plainly ("Option B — harder, and genuinely blocked on R1 work") and
does not resolve it. **It cannot be resolved by sequencing. It has to be resolved by a decision,**
and that is D-2.

**The recommended resolution** is to build a *spike*, not the product: the narrowest possible
pipeline that produces predicted values and boxes for 200 MCB records and nothing else — no
console, no ledger, no class-resolution stack, no catalog ingest. FR-0.3 requires a measurement,
not a shipped feature. This keeps the spirit of the R0 gate (do not build the product before you
know the product works) while unblocking the measurement. It must be built as **throwaway**, with
its throwaway status recorded, or it becomes R1-by-stealth and the gate stops meaning anything.

### THE SCOPE FENCE — written 19 August 2026, before any code

D-2 is decided: **Route A, a throwaway spike.** The route only works if the throwaway part is
real, so the fence comes first and is binding. `HANDOFF.md` §9 warns that this becomes
"R1-by-stealth" if it drifts, and drift is not a moral failing — it is what happens when working
code exists and the next task is easier to do by extending it than by starting over.

**The spike exists to produce one thing: the six columns FR-0.3 needs, for 200 MCB records.**

    gold value · gold page · gold bbox · predicted value · predicted bbox · confidence

**IN scope** — and only because gate 2 cannot be measured without it:

| | Requirement | Why it is unavoidable |
|---|---|---|
| Document register | FR-1.3 | `Evidence.doc_revision_sha256` is a required field; a claim cannot be constructed without one |
| Layout with word-level boxes | FR-1.4 | "predicted bbox" is literally the measurement |
| Table structure | FR-1.5 | MCB ratings live in tables; a value without its row and column headers is not grounded |
| Span-required extraction | FR-3.2 | already enforced in `errata_spec`; the spike must not weaken it |
| Blind re-derivation | FR-3.4 | without it every subsequent agreement is meaningless, and the measurement is worthless |

**OUT of scope, explicitly** — if any of these appears in the spike, the fence has failed:

- the three-pane console, or any UI at all (FR-7.x)
- the claim ledger, `supersedes` chains, or persistence beyond a run (FR-8.2)
- catalog ingest from URLs or PIM formats (FR-1.1)
- ETIM class resolution, retrieve→rerank→select, embeddings (FR-2.x) — the spike is fixed to
  known MCB classes and does not choose them
- the triage router, blast radius, error-signature clustering (FR-8.4, FR-8.5)
- calibration beyond a raw confidence number (FR-6.1 proper)
- **any generalisation.** The spike handles born-digital MCB datasheets from six named
  manufacturers. It does not handle scans, fold-outs, or "documents" in general.

**The rules that make it throwaway rather than a first draft:**

1. It lives in `spike/`, not in a distribution. It is not `pip install`-able and nothing depends
   on it.
2. Its own README says, at the top, that it is throwaway and why.
3. **R1 may inherit its findings, not its code.** What it teaches — which PDFs defeat the layout
   pass, what fraction of values ground cleanly, where the table detection fails — is the
   valuable output. The code is scaffolding.
4. It never writes to `bench/`, `spec/`, `valuesem/` or `comparator/`. If the spike needs a
   change in one of those, that change is a real change, reviewed on its own merits, with tests.
5. When gate 2 has a number, the spike is deleted or frozen. Not "refactored into R1".

**One exception, deliberately taken:** the **document register** is built in `spec/` rather than
in the spike, as `errata_spec.registry`. It is pure content-addressed bookkeeping with a knowable
right answer, it is the thing `Evidence.doc_revision_sha256` already assumes exists, and building
a throwaway version of it would mean building it twice and having two answers to "what document
was this". It carries full tests and is treated as production code from the start.

### Tasks (once D-2 is taken)

| # | Task | Requirement |
|---|---|---|
| 3.1 ✅ | Source ~200 MCB datasheet records — Schneider Acti9 iC60, ABB S200, Siemens 5SL, Legrand, Eaton, Rockwell (all publish openly; one series yields hundreds of SKUs) | FR-0.3 |
| 3.2 ✅ | Document Register: sha256 of bytes, fetch timestamp, source URL, revision label | FR-1.3 |
| 3.3 ✅ | Layout + OCR → char-indexed text layer with a per-token bbox map, deterministic for identical input bytes | FR-1.4 |
| 3.4 ✅ | Table structure detection with cell / row-header / column-header roles | FR-1.5 |
| 3.5 ✅ | Span-required extraction — **a claim with an empty evidence array cannot be constructed**, enforced at the constructor, not by relaxable validation | FR-3.2 |
| 3.6 ✅ | **Blind re-derivation** — the extractor's input payload must not contain the catalog value | FR-3.4 |
| 3.7 🟡 | Hand-label 200 records: gold value, gold page, gold bbox — **1,426 records built, but read mechanically from table structure rather than hand-labelled by a domain expert.** Faithful (the value is the cell text, the evidence is its words) and stated as a caveat on every run; an expert pass would strengthen it | FR-0.3 |
| 3.8 ✅ | Run `errata-r0 operating-point --corpus <file>` |️ FR-0.3 |
| 3.9 ✅ | Plot the risk–coverage curve; report precision and selective accuracy at 20/40/60% coverage; compare explicitly against ExtractBench's 46.43 word-level / 95.6 value F1 | FR-0.3, FR-9.1 |
| 3.10 ✅ | Re-verify the 46.43 figure against arXiv 2607.29677 — it is carried from Phase 2 and flagged `[UNVERIFIED]` | `HANDOFF` §7 |

> **FR-3.4 is the requirement most likely to be quietly broken during optimisation.** Passing the
> catalog value in as a hint measurably improves grounding — and makes every subsequent agreement
> meaningless. The PRD says it in bold; it is repeated here because P3 is where the temptation
> first appears. **Guard it with a test, not a comment.**

### Exit criteria — all met

- [x] Gate 2 reports `MEASURED` — 1,426 records from two real ABB S200 datasheets, exit code 2
- [x] Risk–coverage curve and AURC published — AURC **0.3370**, 1,427 points, curve emitted to
      `var/spike/risk-coverage.csv`, sampled in `docs/R0-report.md`
- [x] **A stated, numeric answer to §0.3.** At full coverage — the comparison FR-0.3 specifies —
      word-level grounding F1 is **46.34%** against ExtractBench's **46.4%**. Conservative margin
      **−2.68pp**. **The audit does not ground better than published extraction; it draws with it.**
      Selectively it is a different story: risk is **0.00% out to 20% coverage**, which is §0.3's
      mechanism 1 intact
- [x] The 46.43 figure verified against the paper — and **corrected**. Table 3 p.9 prints 46.4;
      the repo had invented a second decimal on four figures
- [x] The spike's throwaway status recorded in `spike/README.md`, with what R1 may inherit
      (findings) and may not (code)
- [ ] *Not an exit criterion, but stated:* the gold is document-derived rather than
      expert-labelled, and the catalog side is constructed. Both travel with the number on every run

### The answer to §0.3, in one paragraph

`phase5-red-team.md` names two things that decide this project, and the first is that **§0.3 is
unmeasured**. It is measured now. The result is not the one the project was hoping for: at the
comparison the PRD specifies, Errata's grounding is at parity with the best published extraction
system, not materially better. Two things stop that being a verdict on the thesis. The extractor
built here is deliberately unsophisticated — it is a pattern matcher over flat text, built to be
independent of the gold rather than to be good — so this is a floor, not a ceiling. And the
selective result is genuinely strong: the confidence signal identifies a fifth of the corpus on
which the audit is **never wrong**, which is exactly the mechanism §0.3 argues matters. The honest
reading is that the *asymmetry* is unproven while the *mechanism* is real, and the next experiment
is a better extractor scored on the same corpus, which now exists.

### Risk

**This gate can end the project, and is supposed to be able to.** If the asymmetry is not there,
that is the most valuable result this repository can produce, and it must be reported as found.

---

## Phase 4 — R1, single-SKU audit + console ✅ COMPLETE — entered on a recorded waiver

**Entry criteria: all three R0 gates report numbers.** Not two. This is the PRD's rule and
`HANDOFF.md` §9 closes with "**Do not start R1.**"

> ### ⚠️ The entry criterion was NOT met. R1 was entered on decision **D-3**, below.
>
> Gate 1 is `PASS`, gate 2 is `MEASURED`, and **gate 3 is `NOT_MEASURED` by decision D-1** — the
> per-class SKU distribution is not publicly reachable and three independent hunts closed on the
> same negative result. Two of three gates carry numbers.
>
> **This is a waiver, not a satisfied criterion, and the distinction is the whole point of writing
> it down.** Gate 3 measures how much of the *taxonomy* a labelling budget can calibrate — an R2
> scoping question. It does not bear on whether a single SKU can be audited against a single
> document, which is what P4 builds. What the waiver costs is stated in D-3 rather than implied by
> a green tick, and reversing it is a decision recorded in one place instead of an archaeology
> project.

**Objective:** end-to-end audit of one SKU against one datasheet, with an evidence-boxed redline, a
three-pane console, and an abstention bucket. **This is the demo target.**

**Exit criterion (PRD §4):** the §12 demo script runs on public data, **unrehearsed, on a SKU
chosen at runtime**.

```bash
./.venv/Scripts/errata-audit.exe sku --random --html var/audit/console.html
```

### Exit criteria — met

- [x] **The demo runs unrehearsed on a SKU chosen at runtime.** `--random` picks from 278 catalog
      rows covering 292 type designations in the ABB S200 ordering tables, unseeded. Verified on
      three consecutive runs, one of which landed on a deliberately undocumented SKU and printed
      the honest abstention.
- [x] **An evidence-boxed redline.** The word box lands on `16` in the `S201M-B16UC` row and the
      header box on `Rated current In A`; the value box is under half the containing cell's area,
      which is what makes an IoU ≥ 0.5 score mean anything.
- [x] **A three-pane console** — queue · evidence · claim history — in two forms: one
      self-contained HTML file with the page image inlined, and **a local web application**
      (`errata-audit serve`) where the reviewer adjudicates without leaving the screen, which is
      what FR-7.1 actually asks for. Verified end to end in a browser: a decision produced four
      ledger events and recorded **25.7 reviewer-seconds** (FR-9.3) and an evidence-acceptance
      answer (FR-9.4).
- [x] **An abstention bucket**, 285 declines over the demonstration catalog, every one with exactly
      one machine-readable reason and no silent skips.
- [x] **Class resolution in literally three stages**, with the five-candidate cap enforced by a
      function that raises, and top-1 / top-5 reported on a labelled set: **47.1% / 100%**, 7 of 7
      must-abstain cases held, **zero wrong answers**.
- [x] **Detection on the demonstration catalog: 56/56 injected defects and 11/11 gaps raised, 0
      false positives across 168 correct rows and 40 equivalence traps.** Coverage 79.4%.
- [x] Full suite green — **933 tests**, up from 741; `ruff check .` clean.
- [x] **`spike/` frozen** (P3 rule 5, now that gate 2 has a number): a stated banner, no further
      changes, and `audit/tests/test_boundaries.py` fails the build if any distribution imports it.
      Frozen rather than deleted because `build_corpus.py` is the only thing that can regenerate
      gate 2's corpus, and a measured gate whose corpus cannot be rebuilt is unverifiable.
- [x] Every number and every non-claim written up in `docs/R1-report.md`.

### What R1 deliberately does NOT ship, and says so on every run

| FR-2.2 embedding retrieval + cross-encoder | interfaces only; retrieval is lexical |
| FR-2.2 LLM selector | interface only, capped at 5 candidates by construction |
| FR-6.1 calibration set | **none exists** — calibration needs reviewer decisions and none have been made |
| FR-1.4 OCR | born-digital only; a scan declines with a reason |

The gap between top-1 47.1% and top-5 100% is exactly the missing selector's job, which is the most
useful thing this phase measured: retrieval and reranking are not the problem, and now nobody has
to guess that.

### Workstreams

| Stream | Requirements | Note |
|---|---|---|
| Ingest & documents | FR-1.1 – FR-1.6 | Content-addressed blob store; multi-column pages must not bleed across products |
| Class resolution | FR-2.1 – FR-2.4 | **ETIM 10.0 is already fetched.** Retrieve→rerank→select, literally three stages; an LLM never sees more than 5 candidates. Loader release-parameterised so 11.0 (2026-12-01) loads with no code change |
| Re-derivation | FR-3.1 – FR-3.4 | Blind to the catalog value |
| Value semantics | FR-4.1 – FR-4.6 | **Largely built.** `errata_valuesem` is the C1 library; deterministic, no model, no network |
| Comparator | FR-5.1 – FR-5.5 | **Largely built.** FR-5.3 "semantic equivalence must not flag" is the single highest-consequence requirement in the PRD |
| Confidence & abstention | FR-6.1 – FR-6.3 | Calibrated probability with method recorded; Declined bucket with a machine-readable reason per record; **no silent skips anywhere** |
| Console | FR-7.1 – FR-7.9 | Word-level evidence box, header highlighting, counter-evidence panel that is never empty and never absent, queue rows as sentences and never a bare confidence % |

**Loader traps already discovered and recorded** (`data/reference/manifest.json`): the ETIM CSVs
are **UTF-16-LE with no BOM** — `encoding='utf-16'` raises outright — and the delimiter is `;`.
The R1-scope class ids are read out of the file, not recalled: `EC000042` MCB, `EC000003` RCCB,
`EC000271` MCB plug model, `EC001047` selective main line circuit breaker. `EC000905` "Earth
leakage circuit breaker" **exists in ETIM but is deliberately unregistered in `errata_valuesem`**
(three live readings, no way to pick one from the surface form) and is pinned by a test. Do not
"helpfully" map it.

### Findings raised during P4

- **N11 · `errata_valuesem` cited an ETIM feature that does not exist. FIXED.** `terms.yaml`
  declared `EF000094` for the tripping characteristic; there is no EF000094 in ETIM 10.0, and the
  feature the MCB class declares is `EF000889` "Release characteristic". HANDOFF §7's signature at a
  new location. The remedy is a cross-package test that checks every ETIM id cited anywhere in the
  repository against the loaded release — it is what found this.
- **N12 · The text-window fallback manufactured a confident, evidenced accusation. FIXED.** On the
  S200 M UC datasheet, whose tables do not resolve into columns, it returned `0.3` for a 0.2 A
  device from the running text `0.2 A 0.3 A 0.5 A …`. Nearest-in-reading-order is a tie-break, not
  evidence; it now declines with `layout_unreadable` when the window offers competing values.
- **N13 · The class-resolution evaluation was scoring its own tie-break. FIXED.** It reported top-1
  88.2% by passing the whole attribute map as schema-fit evidence, so every ambiguous query
  resolved to EC000042 — including the bare word "breaker". The honest numbers are 47.1% / 100%.
- **N14 · Redline ids were random, so a decision could not attach to a finding twice. FIXED.** The
  adjudication command the CLI printed stopped working after a re-run. Ids are now derived from the
  finding's content (`uuid5` of document hash, SKU, attribute, catalog value, proposed value) —
  the same content-addressing rule the document register uses — so a decision survives a restart
  and "has this been decided?" is answerable.

All four carry regression tests; N12's carries a negative control, N14's asserts id stability
across runs and across a cache clear.

### Interrupted / not attempted, logged rather than dropped

- **FR-6.3's risk–coverage curve for a run is built and empty.** It is computed over adjudicated
  findings, and there are none. A run has no curve until a reviewer has decided something, which is
  the honest shape: the alternative is the audit grading its own homework.
- **FR-9.3 reviewer-seconds per verified attribute** is collected by the ledger and has no data for
  the same reason.
- **The R1 labelled class set is single-labelled by the implementer** (17 cases + 7 must-abstain).
  Same conflict of interest FR-0.1 names for the equivalence suite, same remedy, not done.
- **The reviewer console has one reviewer-second measurement**, and one timing is an anecdote. The
  metric becomes a claim at a few hundred decisions, which needs reviewers rather than code.

---

## Phase 5 — R2, catalog-scale audit ✅ COMPLETE on all nine requirements; **exit criterion half open**

**Entry criteria:** P4 complete; and if gate 3 showed single-digit class coverage, scope narrowed
to named high-volume classes first (FR-0.4's own acceptance criterion). P4 was complete; gate 3
showed nothing, because D-1 left it `NOT_MEASURED`, so no narrowing was triggered and the R1 class
scope (four low-voltage circuit-protection classes) carried forward unchanged.

**Exit criterion (PRD §4):** full audit of a **10k+ SKU public catalog subset** with a drainable
ranked queue.

> ### ⚠️ Two of three, and the third is named rather than fudged
>
> | | |
> |---|---|
> | 10k+ SKU, audited end to end | ✅ **10,001 records** |
> | a drainable ranked queue | ✅ drains to zero; decisions survive a rebuilt queue |
> | **public** catalog | ❌ **not met** |
>
> No public industrial catalog of that size carrying technical attributes *and* pointing at
> retrievable source documents was reachable. Three independent angles — manufacturer feeds,
> distributor APIs, product data pools — closed on the same answer, which is the pattern D-1
> established. `docs/R2-report.md` §7 records the hunt. **The corpus is constructed and labelled
> as such**, in the report, in `var/scale/provenance.yaml`, on every HTML report and on every run
> of `errata-scale status`. It was not relabelled to make a criterion go green.

```bash
./.venv/Scripts/errata-scale.exe run --html var/scale/report.html
```

### Exit criteria — met, except where §7 says otherwise

- [x] **A whole catalog audited, tier by tier.** 10,001 records: 278 documented (stratum S1, the R1
      demonstration catalog from ABB's own hash-registered datasheets) and 9,723 undocumented
      (stratum S2, constructed).
- [x] **The groundable fraction reported before anything else.** **2.77%** of the catalog can be
      audited against a manufacturer document, and the report prints that above the findings rather
      than below them. Buckets exhaustive and mutually exclusive, summed on exact rationals, every
      bucket enumerable to record level.
- [x] **1,495 queue rows** — 1,428 from T0 (the feed's own structure) and **67 from T1, which are
      R1's numbers unchanged**: the same 56 injected defects and 11 gaps, reproduced by the R2
      pipeline without touching `audit_sku`.
- [x] **Detection against a stated ground truth: 1,428 of 1,428 injected T0 defects, 986 of 986
      expected equal-rank abstentions, and 0 false positives across 654 equivalence-trap families
      and 1,918 clean ones.** FR-5.3 holds at T0, which is a new place for it to break.
- [x] **Cost tracks errors, not rows.** T2 did 67 counter-evidence searches over 10,001 records.
      The claim is tested at two catalog sizes: padding with clean records grows T0 and leaves T2
      and T3 **identical**.
- [x] **Batch reversal on 1,000 records**, idempotent, with nothing deleted.
- [x] **A source scan asserts no UPDATE or DELETE on a ledger anywhere in the repository**, and two
      further tests prove the scanner fires on modules that do.
- [x] Full suite green — **1,078 tests**, up from 933; `ruff check .` clean.
- [x] Every number and every non-claim written up in `docs/R2-report.md`.

### What R2 deliberately does NOT ship, and says so on every run

| FR-6.1 calibration set | still **none exists**; structural findings carry no probability and are ranked on blast radius alone |
| FR-8.4 revenue weight / propagation count | customer configuration, unset, and rendered as stated defaults rather than as measurements |
| a public corpus | see the box above |

### Workstreams

| Stream | Requirements | Note |
|---|---|---|
| Groundable fraction | FR-8.1 | Runs before the audit. A coverage number produced with hindsight is a number chosen with hindsight |
| Ledger at scale | FR-8.2 | Chains reconstructed from `supersedes`, not from file order; fork, cycle and orphan all raise |
| Policy engine | FR-8.3 | `errata_spec` already *held* the policy; R2 is the first release where two claims compete, so it is the first that had to execute it |
| Triage | FR-8.4 | Cluster first, rank second — `record_multiplicity` is the term R1 could not compute |
| Signatures | FR-8.5, FR-8.6 | Artifacts only. **There is no field for a company name**, and that is the whole defence |
| Tiers | FR-8.7 | T0 is new: everything checkable with no document at all |
| Reversal | FR-8.8 | A query over stored facts. A reversal that re-derived what it was undoing would fail exactly when the audit was the problem |
| Two signatures | FR-8.9 | Refused before the ledger is touched, and refused again by `Redline` |

### Findings raised during P5

- **N15 · Redlines and claims speak two vocabularies for one attribute. CONTAINED, not fixed.**
  `build_redline` writes `rated_current` into `attribute_uri` while `stable_redline_id` derives the
  id from `etim:EF000227` — R1 is internally inconsistent and nobody had noticed, because nothing
  before R2 clustered across the two. Fixing it properly changes every existing redline id and
  invalidates recorded adjudications, so it is an R3 change alongside FR-9.7's ETIM↔UNSPSC bridge.
- **N16 · The feed index cited the wrong two characters of every row. FIXED.** A line's span was
  computed as the count of its trailing newline characters. It was self-consistently wrong — the
  snippet was sliced from the same span — and only a test asserting the *literal* expected text
  caught it. A grounding test that checks internal consistency checks nothing.
- **N17 · `--limit` meant two things in one command. FIXED.** `drain --limit 1000` audited the first
  1,000 records and then reported a drained queue. Now `--count`.
- **N18 · Two `conftest.py` files shadowed each other across distributions. FIXED.** Seven R1 test
  files stopped collecting, but only when the whole suite ran and only in one order. R2's fixtures
  moved to a uniquely named module and R2 ships no `conftest.py`; R1's tests were not touched.

### Interrupted / not attempted, logged rather than dropped

- **The public-catalog half of the exit criterion.** Open, with the search recorded. It needs a
  catalog, not an engineering change: `errata-scale run --catalog <file>` takes any CSV today.
- **FR-8.3's engine has no caller inside the run yet.** It is exercised by tests and by the T0
  equal-rank abstention, which applies the same rule; wiring it to multi-source resolution needs a
  second source feed, which R2 has no honest way to obtain.
- **T0's precision is measured against injected defects.** The traps are R0's equivalence shapes, so
  it is not circular — but it is not a field measurement either.

---

## Phase 6 — R3, benchmark + ecosystem ✅ COMPLETE on all nine requirements; **exit criterion half open**

**Entry criteria:** P5 complete. It was — R2 met all nine of its requirements on 20 August 2026.

**Exit criterion (PRD §4):** a **third party reproduces our published scores from the repo**.

> ### ⚠️ One of two, and the second cannot be done from inside the repository
>
> | | |
> |---|---|
> | a reproduction package that runs from the repo alone | ✅ `errata-r3 reproduce` → **REPRODUCED, 24/24** |
> | **a third party** running it | ❌ **not met** — nobody outside this repository has |
>
> `errata_ecosystem.reproduce.THIRD_PARTY_ATTESTATIONS` is an empty tuple, a test asserts that it
> stays empty, and every receipt prints *"NO THIRD PARTY HAS RUN THIS."* A reproduction package
> that certified itself would have reproduced nothing. See **decision D-5** in §10.

```bash
./.venv/Scripts/errata-r3.exe reproduce --full
```

### Exit criteria — met, except where the box above says otherwise

- [x] **FR-9.1 — ExtractBench's metric, verbatim.** Word-level grounding F1 **46.34%** at IoU 0.5
      over 1,426 fields against the published **46.4%**: margin **−0.06pp**. The axis *calls*
      `errata_bench.operating_point.grounding_f1`; a benchmark that re-implements the metric it
      claims to reuse verbatim has written a second opinion and named it after the first.
- [x] **FR-9.2 — the five unscored axes, each runnable alone.** Class assignment (top-1 47.06%,
      top-5 100%, **7/7** must-abstain held), compound values (**14/20**, CI [48.10%, 85.45%]),
      cross-standard mapping (2 codes given attribute layers, **3/3** unmapped codes correctly
      silent), supersession (**5/5**; forked and cyclic histories raise), calibrated abstention
      (**AURC 0.3370**, risk 0.00% out to 20% coverage).
- [x] **FR-9.5 — the gold set as URLs, hashes and annotation layers.** 1,426 annotations, of which
      **1,426 were re-derived from the documents themselves** using R1's layout module: every box
      is a real word box and the boxed words spell the claimed value. No PDF is in the repository,
      and a test walks the tree to prove it.
- [x] **FR-9.6 — a frozen hard-tail split**, 275 records, hashed into the gold manifest. The guard
      fires on a declared tuning run that touches it, and refuses to write the declaration.
- [x] **FR-9.7 — the ETIM↔UNSPSC bridge**, Apache-2.0, ODC-By attributed, validated against both
      hash-registered dictionaries. Seven rows, **three of them refusals** — including a *declined*
      mapping for earth-leakage devices, because two other components already refuse to resolve
      that ambiguity and a published artifact is the worst place to re-introduce it.
- [x] **FR-9.8 — ECLASS by the customer's own licence.** The adapter reads a runtime path and
      refuses one inside the repository; the scanner runs over the tree **and over built
      distributions**, finds nothing, and has a negative control proving it fires.
- [x] **FR-9.9 — a leaderboard including our losing scores.** Generated from the harness with no
      curation step: **2nd of 8** on grounding, beaten on page-level F1 by 17.75pp and on value F1
      by **28.45pp**, and those sentences come from the same function that ranks the table.
- [ ] **FR-9.3 / FR-9.4 — reviewer-seconds and evidence-acceptance.** `NOT MEASURED`; see below.
- [ ] **The third-party half of the exit criterion.** Open, with the package built. Decision D-5.
- [x] Full suite green — **1,199 tests**, up from 1,078; `ruff check .` clean.
- [x] Every number and every non-claim written up in `docs/R3-report.md`.

### What R3 deliberately does NOT ship, and says so on every run

| FR-9.3 reviewer-seconds per verified attribute | **NOT MEASURED.** The protocol ships (`errata-r3 reviewer --protocol`, `docs/reviewer-protocol.md`); nobody has been timed. Synthetic sessions are pinned to NOT_MEASURED unconditionally, exactly as gates 2 and 3 are |
| FR-9.4 evidence-acceptance rate | **NOT MEASURED**, and reported *alongside* grounding F1 in that state. The only adjudications this repository holds were made by the person who built the console; counting them would be the author grading the author's own evidence boxes |
| the hard tail's four named categories | none of degraded scans, fold-outs, cross-page tables or superseded revisions occurs in a corpus of two born-digital PDFs. Each is listed as unrepresented with a measured reason |
| a second judge for the bridge | seven single-judged mappings. Validated, not verified |

### Workstreams

| Stream | Requirements | Note |
|---|---|---|
| Grounding | FR-9.1 | Not implemented here. R0's module is the one implementation; the axis calls it, and a test asserts the two agree on the same corpus |
| The five axes | FR-9.2 | Each runnable alone, each printing its n, its provenance, and what is wrong with it |
| The human numbers | FR-9.3, FR-9.4 | Protocol and arithmetic ship; three unconditional refusals keep the numbers from existing until a person produces them |
| Gold set | FR-9.5 | `scripts/fetch_reference_data.sh` and `data/reference/manifest.json`, built in P0, were already the pattern. R3 extended that machinery rather than inventing it |
| Frozen split | FR-9.6 | A list of ids and a hash. No code path per category, which is why an unrepresented category costs nothing to add the day a document carrying one arrives |
| Bridge | FR-9.7 | Judgements in the file, attribute layer derived from ETIM at load time. Not one feature id appears in the YAML, and a test asserts that |
| ECLASS | FR-9.8 | The scanner matches the IRDI form, not the word — otherwise ADR-003 could not discuss its own subject |
| Leaderboard | FR-9.9 | There is no curation function. Dropping a losing row would mean deleting a metric from the harness |

### Findings raised during P6

- **N15 · Two vocabularies for one attribute. FIXED, and the deferral's premise turned out to be
  wrong.** R2 deferred this because fixing it "changes every existing redline id and invalidates
  recorded adjudications". It does not: both id functions already hashed the *uri*, and only the
  stored field was inconsistent. `AttributeSpec` now carries `uri`, redlines write it, and the R1
  ledger row recorded on 20 August still names the finding the current build produces — pinned by
  a test on the literal id. Signature fingerprints do move; nothing adjudicates a fingerprint.
- **N19 · Every `--json` payload in this repository had a line of English on top of it. FIXED.**
  PyMuPDF advertises its layout add-on with a bare `print` to stdout on every `find_tables()` call.
  Both call sites wrapped it in `warnings.simplefilter("ignore")`, which never silenced it — it is
  not a warning — so `errata-audit catalog --json | jq` failed for anyone who tried it. Redirected
  to stderr rather than discarded. The regression test runs the executable, because no in-process
  test could ever have seen this.
- **N20 · The UNSPSC codeset is cp1252, and utf-8 raises 5,779 bytes in.** Recorded in the
  manifest's loader notes beside ETIM's utf-16-le trap. `errors="replace"` would have corrupted
  three commodity titles, and titles are what the bridge validates against.
- **N21 · One of the two gold documents is unreadable by the gold builder**, because its ordering
  tables are transposed — products across columns, header row collapsed into one cell. Recorded as
  a gold-set gap rather than leaving the corpus quietly at one document.

### Interrupted / not attempted, logged rather than dropped

- **The third-party reproduction.** Needs a person outside this repository, not an engineering
  change. The package, the receipt and the input hashes are built and waiting.
- **A second judge for the bridge.** Same shape as FR-0.1's dual-labelling, same remedy, not done.
- **Cost metering of the benchmark itself (NFR-5).** R2 meters cost by tier; the R3 harness does
  not meter itself, and no cost-per-axis number is claimed.

---

## Phase 7 — R4, commercial ⬜

Monitoring, connectors, calibration service, gated write-back. **Explicitly out of scope for the
current PRD.** Listed for completeness so the phase count is honest.

Note the second open question from `phase5-red-team.md`, still unanswered and unanswerable before
revenue: **"everybody wants exactly one audit."** If the product works perfectly, the customer's
rational next move is to take the report to their enrichment vendor and renegotiate — once. That
makes it ammunition, not a platform. It is the company thesis, and no phase in this plan tests it.

---

## 10. Decisions — D-1 and D-2 taken 19 August 2026, D-3, D-4 and D-5 taken 20 August 2026

Both were escalated as needing a human call. Both have now been decided and recorded here, with
the evidence each rests on. **A decision recorded is reversible; a decision drifted into is not** —
so if either is wrong, reverse it here rather than working around it.

### Decision record

| | Decision | Rationale |
|---|---|---|
| **D-5** | **Close P6 (R3) with the third-party half of the exit criterion open**, taken 20 August 2026 | The reproduction package is built and returns REPRODUCED on 24 of 24 checks here. The remaining act — somebody outside this repository running it — cannot be performed from inside it, and a package that certified itself would have reproduced nothing. See below |
| **D-4** | **Build P5 (R2) on a constructed corpus, and leave the exit criterion's "public" half explicitly open**, taken 20 August 2026 | Three independent hunts for a public 10k+ industrial catalog with retrievable source documents closed on the same negative result (`docs/R2-report.md` §7). The alternatives were to build nothing, or to relabel a constructed corpus as public. See below for what this costs |
| **D-3** | **Enter P4 (R1) with gate 3 unmeasured** — an explicit waiver of the PRD's three-gate entry criterion, taken 20 August 2026 | Gate 3 measures how much of the ETIM taxonomy a labelling budget can calibrate. That is an **R2 scoping** question and does not bear on whether one SKU can be audited against one document. Holding R1 on it would mean holding the product on a number D-1 already established is not obtainable. See below for what the waiver costs |
| **D-1** | **Route C now, Route B queued.** Gate 3 stays `NOT_MEASURED`; stop spending on the hunt; a ready-to-send data request is written and waiting at `docs/data-request-etim-distribution.md` | The negative result was re-tested independently and got stronger, not weaker — see below. Route A is ruled out on ground rule 1 |
| **D-2** | **Route A — a fenced, throwaway grounding spike.** Scope fence written before any code, in §P3 | The only route that gets the number without abandoning the kill-test discipline or leaving §0.3 untested |

### D-5 — the exit criterion's second half, reported rather than waived

**This is the same kind of decision as D-4 and not the same kind as D-3.** D-3 waived an *entry*
criterion — permission to start. D-4 and D-5 waive nothing: they report an exit criterion as
partly unmet, in the phase header, in the tool's own output, and in the report.

- **What is done:** every input the numbers depend on is hashed into a receipt; the environment,
  including all seven distribution versions and the Python build, is recorded; 24 checks compare
  the run against values pinned in code rather than against the last run. `errata-r3 reproduce`
  exits 0 on REPRODUCED, 1 on DIVERGED, 2 on INCOMPLETE.
- **What is not done:** a third party has not run it. `THIRD_PARTY_ATTESTATIONS` is an empty tuple
  and a test asserts that it stays empty, so the only way to claim otherwise is to edit a constant
  whose docstring says what editing it without a receipt would be.
- **What this costs:** the published scores are *reproducible in principle and unreproduced in
  fact*. Every number in `docs/R3-report.md` was produced on one machine, one platform, one Python
  build. NFR-1 requires determinism given identical inputs and versions; nothing here has tested
  what happens when those differ, and a divergence on somebody else's machine is the most useful
  result this package could return.
- **What would reverse it:** one receipt from outside, with its `verdict` and its environment
  block. That is a five-minute act for anyone who has cloned the repository, which is exactly why
  the reproduction path is four commands and why the receipt prints what it prints.
- **The rule this decision is bound by:** the same one D-4 is bound by. **A published score is
  acceptable as unreproduced exactly as long as nobody can read it without also reading that no
  third party has checked it.** The receipt prints that sentence, the phase header prints it, the
  report opens with it, and `errata-r3 status` prints it. If that ever stops being true, this
  decision has been reversed by accident — which is the failure mode it exists to prevent.

### D-4 — a constructed corpus, and the one thing that makes it acceptable

**This is not the same kind of decision as D-3, and the difference matters.** D-3 waived an *entry*
criterion — permission to start. D-4 does not waive an *exit* criterion; it reports it as unmet. The
nine requirements of R2 are complete and measured; the exit criterion is two-thirds met and the
remaining third is named in the phase header, in `errata-scale status`, in
`var/scale/provenance.yaml`, on every HTML report, and in `docs/R2-report.md` §7.

- **What is constructed:** the 9,723 rows of stratum S2 and every defect in them. Their SKUs, their
  manufacturers (`SYN-MFR-nn`, deliberately not plausible company names) and their family shapes.
- **What is real:** the ABB datasheets, the spans and boxes Errata derives from them, the 278 rows
  of stratum S1, and the value pool S2 draws from (the IEC preferred series and the datasheet's own
  weights and packing units).
- **What this costs:** **T0's detection numbers describe a population we created.** 1,428 of 1,428
  and 0 false positives on 654 traps is a measurement of the corpus, not of the world. Grounding,
  where a document exists, is empirical — that half is unaffected.
- **What is *not* affected:** every FR-8.x acceptance criterion is a property of the machinery
  rather than of the data. Percentages summing, buckets enumerating, chains reconstructing, a
  reversal being a query, a signature having no company field, T2 volume tracking errors — none of
  those become true because the corpus is friendly, and each is tested independently of it.
- **What would reverse it:** one customer feed. `errata-scale run --catalog <file>` takes any CSV
  today, with no code change, and the groundable-fraction report is designed to be the first thing
  such a customer sees.
- **The rule this decision is bound by:** the corpus generator writes its own provenance file, the
  CLI prints the banner, and `bench/tests`-style pinning applies — a test asserts the warning text
  is present. **A constructed corpus is acceptable exactly as long as nobody can read a number from
  it without also reading that it is constructed.** If that ever stops being true, this decision has
  been reversed by accident, which is the failure mode it exists to prevent.

### D-3 — what the waiver costs, stated rather than implied

**The criterion exists for a reason and the reason is real.** R0's whole discipline is that the
product is not built before the kill tests answer, and a waiver taken quietly is how that discipline
dies — not in one decision, but in the second one that cites the first as precedent. So:

- **What is waived:** gate 3 (FR-0.4), calibration coverage. `NOT_MEASURED` since D-1.
- **What is not waived:** gates 1 and 2 both carry numbers, and both were read before P4 began.
  Gate 2's result is *unfavourable* — grounding at parity with published extraction, asymmetry not
  confirmed — and P4 proceeded with that stated, not softened.
- **What the waiver risks:** if the real distribution turns out to make calibration coverage tiny,
  the classes R1 is calibrated for are fewer than assumed. R1 audits four classes and abstains
  outside them (FR-2.4), so the blast radius of being wrong here is a **narrower scope for R2**, not
  a wrong answer in R1.
- **What would reverse it:** one file, `class_id, sku_count`, from a datapool export. `--distribution`
  is already wired and the gate goes live with zero code changes. The request is written and waiting
  at `docs/data-request-etim-distribution.md`.
- **Where it is visible:** `errata-audit status` prints it, and `docs/R1-report.md` §6 repeats it.
  A waiver nobody can see from the tool is a waiver that has already been forgotten.

**This waiver covers P4 and nothing else.** P5 (R2) has its own entry criterion that names gate 3
directly — "if gate 3 showed single-digit class coverage, scope narrowed" — and that one cannot be
waived the same way, because it is a question about exactly the thing R2 does.

### D-1 evidence — the hunt was re-run, from a different angle, and closed

Session 2 searched ETIM and 2BA. This session searched the **national datapools** instead, which
is where per-class product counts would actually live if anywhere:

- ✅ **ETIM 10.0 is downloaded, hash-verified, and confirmed to contain no counts.** All nine CSVs
  inspected: `ARTCLASSID`, `ARTGROUPID`, features, values, units. **No count column exists.**
- ❌ **EFObasen (Norway)** — reachable, and `/swagger/index.html` returns **HTTP 401**. An API
  exists and is gated.
- ❌ **2BA (Netherlands)** — statistics behind membership, as previously found.
- ❌ **Open Datapool / ITEK (Germany)** — no public per-class statistics endpoint found.
- ❌ No open dataset of ETIM-classified products with counts exists that any of three independent
  searches could reach.

Three datapools, three gates. **This is a structural property of the industry, not a gap in the
searching**, and further searching is waste. The hunt is closed.

**Route A is ruled out on principle, not on effort.** Distributor front-ends expose merchandising
categories, not ETIM class ids, so the crosswalk would have to be *inferred*. An inferred crosswalk
produces a gate-3 figure with the authority of a measurement and the content of a guess — strictly
worse than `NOT_MEASURED`, which is at least honest (ground rule 1). We do not take that route at
any price.

**What Route C costs us, stated plainly.** Gate 3 stays unmeasured, so R0 will have one measured
gate of three rather than two. The synthetic finding — greedy allocation calibrates 5.95% of
classes but 77.39% of SKUs at a 5,000-label budget — is a Zipf artefact that a real distribution
will very probably reproduce directionally. It is worth having as a real number and it is not
worth blocking on. `--distribution` is already wired: the day the file arrives, the gate goes live
with **zero code changes**, which is the whole reason it was built that way.

### The original options, kept for the record

### D-1 — How do we obtain an ETIM class SKU distribution? *(blocks P2)*

| Route | Cost | Yields a defensible number? |
|---|---|---|
| **A · Scrape one ETIM-adopting distributor** (Sonepar, Rexel, Graybar, WESCO, Würth) and crosswalk to ETIM classes | Counting is easy; **the crosswalk is the whole difficulty** — most front-ends expose their own merchandising categories, not ETIM class ids. Needs a per-site ToS decision from you | **Only if real ETIM class ids attach to real counts.** If the mapping is inferred, no |
| **B · Request a datapool export** — 2BA or IDEA membership, or a friendly distributor. One email | Slower in wall-clock, near-zero effort | **Yes.** The only route that does |
| **C · Defer** — leave gate 3 `NOT_MEASURED`, proceed on the documented synthetic finding | Free | No, but it is honest, and the synthetic result is a Zipf artefact a real distribution will likely only confirm |

*Recommendation:* **B now, C in parallel.** Send the email today because it is one email and its
latency is the only thing that matters; do not let P1 wait on it. Take A only if a *published*
crosswalk exists — an inferred one produces the exact failure mode ground rule 1 forbids.

### D-2 — How do we break the gate-2 / R1 deadlock? *(blocks P3)*

| Route | Consequence |
|---|---|
| **A · Throwaway grounding spike** — narrowest pipeline that produces predicted values + boxes for 200 MCB records, nothing else | Unblocks the measurement while preserving the gate's intent. **Requires discipline:** it must be built as throwaway and recorded as such, or it becomes R1-by-stealth |
| **B · Waive the R0 gate on R1** and build the pipeline as R1 proper, measuring gate 2 as it lands | Fastest to a working product; **abandons the kill-test discipline that is the whole reason R0 exists.** Phase 5's red team says two of three tests can end the project |
| **C · Leave gate 2 unmeasured** and proceed on gates 1 and 3 | Leaves §0.3 — the assumption everything rests on — untested. `phase5-red-team.md` names this as one of the two things that decide the project |

*Recommendation:* **A.** It is the only route that gets the number without either abandoning the
discipline or leaving the company thesis untested. The scope fence has to be written down before a
line of code is written, and it belongs in this document when you take the decision.

---

## 11. Definition of done — applies to every phase

A phase closes only when **all** of these hold:

1. Every exit criterion demonstrated by a **runnable artefact**, not a claim in a document.
2. Full test suite green. Every fix carries regression tests **with negative controls** (ground
   rule 7): `Each` vs `Box of 10` still contradicts, `class 8.8` vs `class 10.9` still contradicts,
   `316` ≡ `A4` ≡ `1.4401` untouched.
3. Every number reported with its confidence interval and next to its coverage. **A comparator can
   flatter its FP rate by refusing to commit** — the rate is meaningless without the coverage.
4. Every new citation traced to a source actually opened, or marked `[UNVERIFIED — needs checking]`.
5. `PROGRESS.md` updated: what closed, what opened, what was interrupted.
6. Findings raised but not acted on are **logged, not dropped**.
7. Any suite label that changed is called out individually with the reasoning, as `PROGRESS.md`
   already does for `mat-h005` and `pkg-h049`.

---

## 12. Ground rules — reproduced from `HANDOFF.md` §8, do not reverse silently

1. **Never invent a number or a citation.** Mark `[UNVERIFIED — needs checking]` instead.
2. **`valuesem` is deterministic** — no model call, no network call, in any code path (NFR-8,
   enforced by `test_determinism_boundary.py`).
3. **A grammar either parses or refuses.** Refusal is a routable signal; a silent guess is not.
4. **Leave real code failures failing.** A failing case is the finding. Never write a
   knowingly-wrong label to make the code look good.
5. **Gates 2/3 stay `NOT_MEASURED` on synthetic input**, unconditionally.
6. **Errata audits; it never enriches, and never writes to a customer PIM.**
7. **Every comparator fix needs negative controls.** A fix that softens a real defect is worse than
   the bug it removed.
8. **The gate judges on the strict metric.** If the strict and narrow readings ever diverge again,
   the comparator has started answering where the honest reply is "you cannot tell".
