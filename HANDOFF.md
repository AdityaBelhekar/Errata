# HANDOFF — Errata

**Written:** 19 August 2026, end of the R0 build session.
**Updated:** 20 August 2026 — R1 (PHASES P4) and R2 (PHASES P5) are built. See §12 and §13.
**For:** a fresh session, or a person who has never seen this repo.
**Read this, then `PROGRESS.md` for the task board. You should not need anything else to start.**

---

## 1. What this is, in sixty seconds

A hackathon problem statement asked for *"AI-Powered Product Intelligence for Industrial Commerce — data enrichment, validation, and explainable outputs."*

Five phases of research (`phase1`–`phase5`, then `prd-errata.md`) concluded that the obvious build — PDF in, LLM out, pretty dashboard — is a commodity feature, and that the real, verified gap is **evidence**:

> On ExtractBench (arXiv 2607.29677), the best commercial extraction system scores **95.6% value F1**
> and **46.43 word-level grounding F1**. Eight of fourteen systems score **0.00** on grounding.
> The field can get the answer right and cannot show where it came from.

So **Errata** does not extract product data. It **audits product data somebody else already produced**: ingest a catalog *and* its source documents, independently re-derive every attribute, ground each value to a word-level span, calibrate confidence, and emit a ranked list of disagreements with the evidence attached.

**It grades. It does not create.** That is the whole product — it means better extraction models improve Errata's *input* rather than making it redundant.

---

## 2. Current state — one table

| | Status |
|---|---|
| **Research + spec + PRD** | ✅ Complete (`phase1`–`phase5`, `prd-errata.md` with 62 numbered requirements) |
| **R0 gate 1** — equivalence suite | ✅ **PASS at 1.30%** (3/230), 624 hand-labelled cases |
| **R0 gate 2** — operating point | ✅ **MEASURED** — **ASYMMETRY NOT CONFIRMED**. 46.34% word-level grounding F1 against ExtractBench's 46.4%: a dead heat. See `docs/R0-report.md` |
| **R0 gate 3** — calibration coverage | 🔵 Built, **NOT MEASURED** — needs one real ETIM class distribution. Searched 2026-08-19: **not publicly reachable**, see §9 |
| **R1** | ✅ **BUILT** — `errata-audit`, end to end on a real datasheet. Entered on **waiver D-3**, not on a met entry criterion (gate 3 is still unmeasured). See §12 and `docs/R1-report.md` |
| **R2** | ✅ **BUILT** — `errata-scale`, 10,001 records audited T0→T3. All nine FR-8.x requirements met; the exit criterion's **"public catalog" half is NOT met** and is recorded as decision **D-4**. See §13 and `docs/R2-report.md` |
| **R3** | ✅ **BUILT** — `errata-r3`, the benchmark and the ecosystem. Seven of nine FR-9.x requirements measured; FR-9.3 and FR-9.4 are **NOT MEASURED** because they are measurements of people; the exit criterion's **third-party half is NOT met** and is recorded as decision **D-5**. See §14 and `docs/R3-report.md` |
| **R4** | ⬜ Not started — out of PRD scope |
| **Tests** | ✅ **1,199 passing** (1,078 + 121 for R3) |

```bash
./.venv/Scripts/errata-r0.exe status
```

**R0 is not finished.** One of three gates has a real number, one has a measured but unfavourable
one, and gate 3 is deferred by decision. **R1 was built anyway, on an explicit recorded waiver** —
the reasoning, the cost and the reversal condition are in `PHASES.md` §10 under D-3, and
`errata-audit status` prints it so nobody discovers it from a document.

---

## 3. How to run it

Windows, Git Bash (the scripts detect POSIX shells too). **One command sets everything up** —
it creates `.venv/`, installs the pinned dependency set from `requirements-lock.txt`, installs all
five packages editable, then verifies by running the suite and the gates. Idempotent:

```bash
bash scripts/setup.sh
```

```bash
./.venv/Scripts/python.exe -m pytest -q
```

Reference data (the ETIM 10.0 model) is fetched separately, hash-verified against
`data/reference/manifest.json`:

```bash
bash scripts/fetch_reference_data.sh
```

The `errata-r0` CLI is the R0 driver. **Exit code is the decision, not a diagnostic** — 0 pass, 1 hold, 2 stop, 3 inconclusive/not-measured.

```bash
./.venv/Scripts/errata-r0.exe status
```

```bash
./.venv/Scripts/errata-r0.exe equivalence --show failures
```

```bash
./.venv/Scripts/errata-r0.exe equivalence --family threads --show failures
```

```bash
./.venv/Scripts/errata-r0.exe equivalence --json
```

Gates 2 and 3 run on a synthetic stand-in by default and are pinned to `NOT_MEASURED` unconditionally in that mode. Real data makes them live with no code change:

```bash
./.venv/Scripts/errata-r0.exe operating-point --corpus <file.yaml>
```

```bash
./.venv/Scripts/errata-r0.exe coverage --distribution <file.csv>
```

### The catalog-scale audit (R2)

`errata-scale` audits a whole feed, tier by tier. **It prints the groundable fraction above the
findings, not below them** — a defect count over a catalog where 97% of records have no retrievable
document is unreadable without it.

```bash
./.venv/Scripts/errata-scale.exe run --html var/scale/report.html
```

```bash
./.venv/Scripts/errata-scale.exe groundable
```

```bash
./.venv/Scripts/errata-scale.exe clusters --top 12
```

```bash
./.venv/Scripts/errata-scale.exe integrity
```

```bash
./.venv/Scripts/errata-scale.exe status
```

The 10,001-row demonstration corpus is **generated rather than committed** (`scripts/setup.sh`
builds it; `errata-scale corpus` rebuilds it at any size). Ten thousand rows of constructed catalog
is not source, and a repository that commits fixtures at that size teaches everyone to stop reading
diffs.

### The demo

`errata-demo` runs the real comparator over a small demonstration catalog and prints a reviewer
queue. Text to stdout, or `--html` for a shareable report.

```bash
./.venv/Scripts/errata-demo.exe
```

```bash
./.venv/Scripts/errata-demo.exe --html report.html
```

It exists because R0 produced no artefact a person could look at, and a judge or a customer asks
to see the thing work before they ask what its false-positive rate is.

**It is deliberately fenced so it cannot become a lie.** Every value pair is loaded *by case id*
from the equivalence suite, with its citation, and `run_demo` raises if an id does not resolve --
so the demo cannot drift from the data the gate measures, and nobody can quietly hand-tune a value
to make the output look better. The SKU identifiers are illustrative and the report says so.
It shows the **comparator only**; the report states on its face that evidence grounding is not
built and that gate 2 is still `NOT MEASURED`. Pinned by `bench/tests/test_demo.py`.

---

## 4. Repo map

```
Research & spec — read-only history, do not edit
  product-intelligence-research-prompt.md   the original five-phase mega-prompt
  phase1-differentiated-research.md         3-model research + recency sweep
  phase2-synthesis-and-verification.md      contradiction matrix + live verification
  phase3-concepts-and-scoring.md            15 concepts scored; C8/C12 fusion won
  phase4-full-spec.md                       THE SPEC — 13 sections, ADRs, post-red-team revisions
  phase5-red-team.md                        hostile judge/investor pass + kill criteria
  prd-errata.md                             62 requirements, R0–R4, with acceptance criteria

Code — seven editable packages
  spec/       errata_spec        Claim, Redline, DisagreementClass taxonomy, resolution policy
  valuesem/   errata_valuesem    deterministic normalizer — NO model/network calls, ever
                parsers/         thread, dimension, ingress, material, term, packaging
                grammars/        thread.lark, dimension.lark
                ontology/        materials.yaml, packaging.yaml, terms.yaml
                units/           industrial.txt (Pint extensions)
  comparator/ errata_comparator  disagreement classification (8-class taxonomy)
  audit/      errata_audit       R1 — the end-to-end single-SKU audit + errata-audit CLI
                ingest / documents / layout / tables    FR-1.x
                etim / classify                          FR-2.x  three-stage class resolution
                derive                                   FR-3.x  blind, span-required
                confidence / counterevidence             FR-6.x / FR-7.4
                audit / ledger / console / cli           the run, the ledger, the three panes
  scale/      errata_scale       R2 — the catalog-scale audit + errata-scale CLI
                groundable                               FR-8.1  the inventory, before any audit
                feedindex / structural                   T0 -- the feed as a citable artifact
                signatures                               FR-8.5 / FR-8.6  computed, never org-keyed
                triage / queue                           FR-8.4 / the drainable queue
                chains / reversal                        FR-8.2 / FR-8.8
                resolution                               FR-8.3  the policy, executed
                tiers / run / report / cli               the run and its three surfaces
                corpus                                   the demonstration catalog generator
  bench/      errata_bench       R0 harness + errata-r0 CLI
                equivalence.py      gate 1
                operating_point.py  gate 2 — ExtractBench-compatible metrics
                coverage.py         gate 3 — calibration-coverage arithmetic
                stats.py            Wilson intervals
                suites/equivalence/ the 624-case gold suite
  ecosystem/  errata_ecosystem   R3 — the benchmark and the ecosystem + errata-r3 CLI
                axes.py                                  FR-9.1 / FR-9.2  six axes, each alone
                goldset.py                               FR-9.5  annotations, verified GROUNDED
                splits.py                                FR-9.6  the frozen hard tail + its guard
                bridge.py + data/etim-unspsc-bridge.yaml FR-9.7  published, ODC-By attributed
                eclass.py                                FR-9.8  BYO licence + content scanner
                leaderboard.py                           FR-9.9  generated, prints our losses
                reviewer.py                              FR-9.3 / FR-9.4  the protocol, and refusals
                reproduce.py                             the exit criterion, as far as it can run
                vocabulary.py                            finding N15's fix and its regression guard

Data — committed, and deliberately payload-free
  data/reference/manifest.json   URLs + sha256 for ETIM, UNSPSC, UCUM, Rec 20/21, ISO 261, H28,
                                 the ExtractBench paper and the two ABB datasheets. No payload.
  data/gold/                     FR-9.5 — the gold set: manifest, annotation layers, frozen split

Tests — 1,199 passing
```

### The equivalence suite — 624 cases

`<family>.yaml` is the original seed; `<family>_hard.yaml` is the adversarial pass.

| family | seed | hard | note |
|---|---|---|---|
| ingress | 15 | 45 | IP codes; IP67-vs-IP65 non-ordering handled correctly |
| materials | 42 | 70 | |
| packaging | 19 | 64 | zero misses on "Each vs Box of N" — the highest-severity case |
| terms | 30 | 89 | MCB/RCBO/RCCB, trip curves, pole counts |
| threads | 30 | 114 | largest family; **never citation-audited** (see §7) |
| units | 39 | 67 | found the unit-conversion bug |

Each case has `a`, `b`, `expect`, and a `source:` citation. Seven labels: `equivalent`, `contradiction`, `granularity`, `precision`, `agreement_specific`, `undetermined`, `null_gap`.

---

## 5. How gate 1 got to 1.38% — read this before trusting the number

The number moved a long way and the reasons matter more than the value.

| Suite state | FP rate | Gate | What it meant |
|---|---|---|---|
| Seed, 175 cases | 0.00% | PASS | **Meaningless** — the suite was written alongside the code it grades and never challenged it. All 175 still pass. |
| +5 adversarial suites, 510 | 1.57% | PASS | First real signal; caught a silent unit-conversion bug. |
| +threads suite, 624 | 7.50% | STOP | 15 new false positives, four concrete root causes. |
| after fixing the thread parser | 1.33% | PASS | All 15 cleared — but this was the *narrow* reading. |
| after fixing the gate's accounting | 6.22% | **STOP** | The honest number: the metric had been routing around its own instruments. |
| **after fixing the over-resolutions** | **1.38%** | **PASS** | Both readings now agree. |

**The key event was the accounting fix.** The gate metric's own docstring claimed to be "the number a reviewer experiences," and it was not: findings raised on `undetermined` pairs were dropped from its numerator by branch order **while staying in its denominator**, so one bad redline improved the rate at both ends. Three related leaks:

1. `over_resolved` drained the numerator — 11 findings, 8 at SEV-1. **Fixed:** the gate now judges on `fp_reviewer_experienced` = every redline that should not have been raised.
2. Declined contradictions were booked as coverage loss, not misses — understating by ~3.4×. **Fixed:** `miss_rate_including_declines` reports both.
3. `CaseResult.accusatory` fired **zero times** across the whole suite — the one instrument built to capture "a reviewer sees a false accusation" was dead code. **Fixed.**

Then the underlying over-resolutions were fixed — packaging hierarchies, material facet commensurability, an `IP6/7` misparse, and a missing `null_gap` suite label — and both readings converged at 1.38% with `over_resolved_findings` empty.

### What the number still does not establish

- **All 624 cases were labelled by the same author who wrote the comparator.** FR-0.1 requires independent dual-labelling before this is quotable outside the repo. The harness says so in its own caveats — keep it that way.
- The suite has **348 of FR-0.1's 500** equivalence pairs.
- **Coverage is 76.9%** — 144 of 624 cases are declined. A comparator can flatter its FP rate by refusing to commit, so always read the rate next to the coverage.
- **The honest miss rate is 21.51%** (57/265) once declined defects are counted, against 6.42% answered-wrong.

---

## 6. Open work queue

Full detail with file paths is in `PROGRESS.md`. Ranked:

**P1 — ✅ ALL FOUR CLOSED (19 Aug 2026, session 2).** Findings 9, 10, 13 and 15 are fixed, each
with regression tests carrying negative controls. Detail and the two label changes they required
are in `PROGRESS.md`. Gate 1 moved 1.38% → **1.30%** with coverage 76.9% → **79.49%** and misses
21.51% → **17.36%**; the FP *count* never changed, only the denominator, which is the honest way.

Four **new** findings were raised in the process (N1–N4 in `PROGRESS.md`). Two want your ruling:

- **N2** — ~~HANDOFF §7 below overstates one of its four fabrication exhibits.~~ **RESOLVED
  2026-08-21.** IEC 60947-1 does have an Annex A, and it is *about utilization categories*, so the
  exhibit did not merely overstate — it convicted a plausibly correct citation on a false charge.
  The exhibit is withdrawn and the verified text is quoted in §7, from a primary source that was
  actually opened.
- **N1** — the Rec 20 mis-citation is systemic. Several suite `source:` fields still say "Rec 20"
  for what are Rec 21 package-type codes.

**P2 — suite quality**
- **16** · Citation-audit `threads_hard.yaml` (114 cases, never audited — see §7).
- **17** · `expect_alternatives` laundering — `pkg-h026/h031/h035` and `pkg-010` attach a second label so a known SEV-1 defect scores PASS (`Dozen` vs `Box of 12` — twelve against twelve).
- **19** · Six reported label findings; sharpest is `mat-h063`: `"18-8"` vs `"S30400"` labelled `equivalent`, but 18-8 is a *family* covering 302/303/304/305 — generic ≡ specific is a silent false negative.
- **20** · Independent dual-labelling.

**Deliberately left failing:** `KNOWN_FALSE_POSITIVES = {unt-h011, unt-h014, unt-h031}` in `bench/tests/test_r0_gate.py` — three cases judged real code findings and pinned so a *new* false positive breaks the build. Shrinking this set is progress; growing it silently is how a gate stops meaning anything.

---

## 7. The citation problem — internalise this

The project's governing rule: **never invent numbers — cite a source you actually opened, or write `[UNVERIFIED — needs checking]`.**

An audit of the adversarial suites found that **three of five authoring agents fabricated standards citations** — and every one had self-reported "0 UNVERIFIED citations":

| Fabrication | Reality |
|---|---|
| "IEC 60529 **5.2**: X means not tested" — cited 15× | The X rule is clause **4.1** |
| "IEC 60947-1 **Annex A**" — cited 4× | ⚠️ **This exhibit was itself wrong. Withdrawn 2026-08-21 — see below.** |
| "ISO 898-1 **Table 3** = chemical composition" | Table 3 is *mechanical properties* — the opposite |
| 13 cases citing IEC 60947-1 for **SP/DP/TP** | Trade conventions the standard never defines |

**Exhibit 2 is withdrawn, and the correction is the point (finding N2).**

The row above used to read "**No such annex.** AC-1/AC-3 are IEC 60947-4-1 Table 1". IEC 60947-1
**does** have an Annex A. Verified 21 August 2026 against the full text of IS/IEC 60947-1:2007 —
the Indian Standard adoption, a verbatim reproduction, freely readable at
`archive.org/stream/gov.in.is.iec.60947.1.2007` — which prints:

> Annex A (informative) — Examples of utilization categories for low-voltage switchgear and
> controlgear

and defines *utilization category* generally at 2.1.18, with clause 4.4 titled "Utilization
category".

So the finding is worse than "overstated". The annex exists, it is *about utilization categories*,
and an agent citing it for AC-1/AC-3 was **plausibly right** — what is true is narrower: the
*normative* AC-1/AC-3 requirements for contactors are in IEC 60947-4-1 Table 1, and 60947-1
Annex A is an informative list across the series. Cited as "where AC-3 is defined normatively",
the original citation is wrong. Cited as "where utilization categories are listed", it is correct.
The audit convicted it on a charge — "no such annex" — that was not true.

That charge was written the same way the fabrications were: confidently, about a locator nobody
had opened. The audit that caught three agents inventing citations invented one of its own, in the
table where it announced the finding. It stayed uncorrected for a while because it was persuasive
and on-message, which is exactly the property the other three had.

The three remaining exhibits stand and were re-read on the same date. The lesson does not move; if
anything it lands harder, and it is the reason ground rule 1 says "cite a source you actually
opened" rather than "cite a source".

47 source fields were corrected; zero labels were changed. The signature: each agent was **disciplined about facts it knew were shaky and careless about locators it assumed nobody would open.** The two files that scored best were the two that *admitted* uncertainty.

**Treat any confident citation in this repo as a claim to check** — especially in `threads_hard.yaml`, the largest suite file, which has never been audited.

The same failure happened to me this session: while extending the inch-thread tables I briefly wrote UNF's 12 TPI values into the **UNEF** table, where the correct value is 18. Caught, fixed, and pinned with a test. It is easy to do.

### Verified live this session

| Claim | Result |
|---|---|
| ECLASS is licensed/paid | ✅ Confirmed — priced by company size |
| ETIM is free | ✅ Confirmed — **Open Data Commons Attribution Licence**. Not all local language versions are free |
| UNSPSC has no technical attributes | ✅ Confirmed — 4 levels, 8 digits, code + label only |
| ETIM 11.0 release | ✅ Confirmed **1 December 2026** |
| ExtractBench grounding metric | ✅ Confirmed — value accepted AND box IoU ≥ 0.5; leader 95.6% value F1 at 8.1¢/page |
| The 46.43 grounding table | ⚠️ **Carried from Phase 2, not re-verified** — the arXiv PDF is 5.9MB of compressed streams and no PDF text library was available locally |

---

## 8. Ground rules — do not reverse these silently

1. **Never invent a number or a citation.** Mark `[UNVERIFIED — needs checking]` instead.
2. **`valuesem` is deterministic** — no model call, no network call, in any code path (NFR-8, enforced by `test_determinism_boundary.py`).
3. **A grammar either parses or refuses.** Refusal is a routable signal; a silent guess is not.
4. **Leave real code failures failing.** A failing case is the finding. Never write a knowingly-wrong label to make the code look good.
5. **Gates 2/3 stay `NOT_MEASURED` on synthetic input**, unconditionally.
6. **Errata audits; it never enriches, and never writes to a customer PIM.**
7. **Every comparator fix needs negative controls.** `Each` vs `Box of 10` must still contradict; `class 8.8` vs `class 10.9` must still contradict; `316` = `A4` = `1.4401` must stay equivalent. A fix that softens a real defect is worse than the bug it removed.
8. **The gate judges on the strict metric.** If the strict and narrow readings ever diverge again, the comparator has started answering where the honest reply is "you cannot tell".

---

## 9. What to do next

**Option A — unblock gate 3. Still the cheapest path, but narrower than it looked.**
Needs one file: `class_id, sku_count`. `--distribution` is already wired; no new code required.

**Searched 2026-08-19. Result: the counts are not publicly published.** What was established:

- ✅ **The ETIM model is free and is now downloaded** — ETIM 10.0 ALL-SECTORS CSV, released
  2024-12-05, ODC-By, no login, direct link off `etim-international.com/downloads/`. 5,640 classes
  in 159 groups. This is the **taxonomy only**: `ARTCLASSID`, `ARTGROUPID`, description. There is
  **no SKU count anywhere in the release**, and that is the half gate 3 actually needs.
- ❌ ETIM publishes no per-class product statistics.
- ❌ 2BA (the Dutch datapool, 4M+ product records / 24M+ trade records) exposes class search but
  gates statistics behind membership. No public facet-count endpoint was found.
- ❌ No open dataset of ETIM-classified products with counts was found.

**Two routes remain, and both need your decision rather than more searching:**

1. **Scrape one ETIM-adopting distributor** (Sonepar, Rexel, Graybar, WESCO, Würth) and crosswalk
   to ETIM classes. The counting is easy; **the crosswalk is the whole difficulty** — most
   distributor front-ends expose their own merchandising categories, not ETIM class ids. Needs a
   per-site decision from you on ToS, and every row wants a source URL + retrieval date.
   **The trap:** if the mapping has to be *inferred*, gate 3 produces a number that looks measured
   and is not. Under ground rule 1 that is strictly worse than `NOT_MEASURED`, which is at least
   honest. Only take this route if real ETIM class ids can be attached to real counts.
2. **Ask for a datapool export.** 2BA or IDEA membership, or a friendly distributor. One email.
   Slower in wall-clock, and it is the only route that yields a defensible number.

**Calibrate the payoff before spending on this.** The synthetic finding — 5.95% of classes /
77.39% of SKUs at a 5,000-label budget — is a Zipf artefact. A real distribution will very likely
reproduce it directionally. Gate 3 is worth having as a *real* number, but expect it to confirm
rather than surprise.

**Option B — unblock gate 2. Harder, and genuinely blocked on R1 work.**
Sourcing PDFs is trivial: Schneider, ABB, Siemens, Legrand, Eaton and Rockwell all publish MCB datasheets openly; one series (Schneider Acti9 iC60, ABB S200) yields hundreds of SKUs. The cost is producing, per record: gold value, gold page, gold bounding box, predicted value, predicted box, confidence — which needs the grounding pipeline (FR-1.2–1.5) that does not exist yet.

**Option C — harden gate 1.** Findings 9, 10, 13, 15 are real bugs with evidence. Finding 16 (audit `threads_hard.yaml`) is the highest-value quality item.

**Do not start R1.** The PRD gates it on all three kill tests, and two have no number.

---

## 10. Two things worth keeping in view

The seed suite of 175 cases still scores **100% pass**, while the 449 adversarial cases decline at ~6× the rate and produced every bug found this session. That contrast is Phase 5's warning demonstrated: a suite written alongside the code it grades encodes the same blind spots twice.

And the a/b symmetry test is clean — **624 pairs swapped, zero ordering violations**, with all asymmetries landing on documented design intent. That is the one result here defensible without qualification.

---

## 11. The two things that decide this project

From `phase5-red-team.md`, both still open:

1. **The §0.3 assumption is unmeasured.** Everything rests on auditing having a materially better precision/coverage operating point than extraction at equal grounding quality. Gate 2 exists to test exactly this and has never run on real data.
2. **"Everybody wants exactly one audit."** If the product works perfectly, the customer's rational next move is to take the report to their enrichment vendor and renegotiate — once. That makes it ammunition, not a platform. Untestable before revenue, and it is the company thesis.

---

## 12. R1 — what was built on 20 August 2026, and what it does not claim

**`errata-audit` is the product working end to end**, on a real ABB S200 datasheet with real word
boxes. Full numbers: `docs/R1-report.md`. Package guide: `audit/README.md`.

```bash
./.venv/Scripts/errata-audit.exe serve --open
```

```bash
./.venv/Scripts/errata-audit.exe sku --random --html var/audit/console.html
```

```bash
./.venv/Scripts/errata-audit.exe classes
```

```bash
./.venv/Scripts/errata-audit.exe catalog --json
```

The exit code is the decision, as with `errata-r0`: **0** audited and supported, **1** findings,
**2** could not audit, **3** the run failed.

**The headline, with its caveat attached:** 56/56 injected defects raised, 11/11 fill-rate gaps
raised, **0 false positives** across 168 correct rows and 40 equivalence traps, coverage 79.4%.
**The catalog is constructed** — no public ABB feed exists — so those detection rates describe a
population we created; the datasheet, the spans and the boxes are real and hash-registered. That
sentence is printed by the CLI and rendered on every report, not filed in a document.

**Four things R1 does not have, and every run says so:**

1. FR-2.2's embedding retriever and cross-encoder — interfaces, no implementation.
2. An LLM selector — an interface, capped at five candidates by a function that raises.
3. **A calibration set (FR-6.1)** — none exists. Calibration needs reviewer decisions and nobody has
   made any; on the demo population the audit has no false positives at all, so a fit would have one
   outcome and `fit_platt` refuses it. Confidences print as raw scores with "NOT CALIBRATED".
4. OCR — born-digital documents only; a scan is declined with a reason.

**The most quotable measurement is the class-resolution split: top-1 47.1%, top-5 100%.** Retrieval
and reranking put the right class in the shortlist every time; the selector — the stage FR-2.2
specifies as an LLM and this package does not ship — commits half the time and is **never wrong**.
That gap is the missing stage's job, and it is measured rather than assumed.

`serve` is the console as a running application: ranked queue, evidence boxed on the page image,
and Accept / Keep catalog / Escalate buttons that write to the append-only ledger. It is where
FR-7.6, FR-9.3 and FR-9.4 stop being claims — the first real decision recorded 25.7 reviewer-seconds
and an evidence-acceptance answer. It binds to loopback and refuses anything else without a flag,
because it renders a customer's catalog beside a manufacturer's document and has no authentication.

**Four findings, all fixed, all with tests** (detail in `PROGRESS.md`):

- **N11** — `errata_valuesem` cited ETIM feature `EF000094`, which does not exist in ETIM 10.0. The
  MCB class declares `EF000889`. §7's signature at a new location; now pinned by a cross-package
  citation test that checks every ETIM id in the repo against the loaded release.
- **N12** — the text-window fallback returned `0.3` for a 0.2 A device out of a list of ratings: a
  confident, evidenced accusation about a value the document never stated for that product. It now
  declines when the window offers competing values.
- **N13** — the class-resolution evaluation was scoring its own tie-break and reported 88.2%. The
  honest number is 47.1%.
- **N14** — redline ids were random, so a decision could not attach to a finding twice and the
  printed `adjudicate` command expired on the next run. Ids are now derived from the finding's
  content, the same rule the document register uses for bytes.

**`spike/` is now FROZEN**, which P3 rule 5 required once gate 2 had a number. Frozen rather than
deleted: `build_corpus.py` is the only thing that can regenerate gate 2's corpus, and a measured
gate whose corpus cannot be rebuilt is a measurement nobody can check. Nothing imports it, and
`audit/tests/test_boundaries.py` fails the build if anything starts.

**What to do next.** R2's entry criterion names gate 3 and D-3 does not waive it, so the honest next
move is either the datapool export (one email, `docs/data-request-etim-distribution.md`) or the one
experiment R1 has made cheap: **wire an LLM selector behind the `Selector` protocol and re-run
`errata-audit classes`.** The labelled set, the harness and the five-candidate cap already exist,
and the gap it would close is measured at 47.1% → 100%.

---

## 13. R2 — what was built on 20 August 2026, and what it does not claim

**`errata-scale` is the product at catalog scale.** Full numbers: `docs/R2-report.md`.

```bash
./.venv/Scripts/errata-scale.exe run --html var/scale/report.html
```

**The headline, with its caveat attached, in the order they must be read:**

> **2.77% of this 10,001-record catalog can be audited against a manufacturer document.** Of the
> records that can be, coverage is 79.4%. The run produced 1,495 queue rows in 9 error signatures,
> found 1,428 of 1,428 injected T0 defects, and raised **0 false positives across 654
> equivalence-trap families**. T2 did 67 counter-evidence searches over 10,001 records, which is the
> whole commercial argument for auditing rather than extracting.

**The catalog is constructed** — stratum S1 (278 rows) comes from R1's demonstration catalog and
ABB's real hash-registered datasheets; stratum S2 (9,723 rows) is generated with defects injected on
purpose. Detection numbers describe a population we created; grounding, where a document exists, is
empirical. That sentence is printed by the CLI, written into `var/scale/provenance.yaml`, rendered on
every HTML report, and pinned by a test — **a constructed corpus is acceptable exactly as long as
nobody can read a number out of it without also reading that it is constructed** (decision D-4).

**Three things R2 does not have, and every run says so:**

1. **A public corpus.** The exit criterion asks for a public 10k+ catalog. Three independent hunts
   closed on the same negative result (`docs/R2-report.md` §7). Open, not waived.
2. **A calibration set (FR-6.1).** Still none. Structural findings carry no probability at all and
   are ranked on blast radius alone; the queue says so on every row.
3. **Revenue weight and propagation count.** Customer configuration, unset, and rendered as stated
   defaults — because a `1.0` that reads like a measurement is how a ranking quietly becomes a
   fiction.

**The most useful thing R2 measured** is not a detection rate: it is that **T2 volume tracked the
error count and not the record count**, tested at two catalog sizes. That is the property that makes
the price of an audit fall as a customer's data improves, and it is the only reason the tiering
exists.

**One structural finding carried forward and then closed (N15).** Redlines stored `attribute_uri`
as the bare key while their *identity* was derived from the ETIM URI — R1 was internally
inconsistent from the day it shipped, and nothing noticed until R2 clustered across both tiers.
**R3 fixed it, and the reason it was deferred turned out not to hold:** both id functions already
hashed the URI, so no redline id moved. The R1 ledger row recorded on 20 August still names the
finding the current build produces, pinned by a test on the literal id. Error-signature
fingerprints do move; nothing adjudicates a fingerprint. See `docs/R3-report.md` §9.

---

## 14. R3 — what was built on 20 August 2026, and what it does not claim

**`errata-r3` is the benchmark, and the reason any number above is quotable.** Full numbers:
`docs/R3-report.md`.

```
./.venv/Scripts/errata-r3.exe reproduce --full   # 24 checks + the leaderboard
./.venv/Scripts/errata-r3.exe gold verify        # 1,426 annotations, re-derived from the documents
./.venv/Scripts/errata-r3.exe split show         # the frozen hard tail, and what it does not contain
./.venv/Scripts/errata-r3.exe bridge show --code 39121603
./.venv/Scripts/errata-r3.exe eclass scan --dist dist/*.whl
./.venv/Scripts/errata-r3.exe status             # what it can do, and what it declines to claim
```

**Word-level grounding F1 46.34%** at IoU 0.5 over 1,426 fields against ExtractBench's published
**46.4%** — computed by *calling* R0's implementation, not by writing a second one. Five further
axes, each runnable alone: class assignment (top-1 47.06%, must-abstain 7/7), compound values
(14/20), crosswalk (2 codes given attribute layers, 3/3 unmapped codes correctly silent),
supersession (5/5, broken histories raise), calibrated abstention (AURC 0.3370).

**Three things worth knowing before you touch it.**

1. **Two requirements report NOT MEASURED and are supposed to.** FR-9.3 and FR-9.4 are measurements
   of people. Synthetic sessions are pinned to NOT_MEASURED unconditionally; so are decisions by
   anyone who built the tool, which is every adjudication this repository holds. Do not "enable"
   these by relaxing the role check — the protocol is at `docs/reviewer-protocol.md` and what is
   missing is a reviewer, not a code path.
2. **The gold set is verified, not merely shipped.** `gold verify` re-derives every annotation from
   the document using R1's layout module — a *different* extractor from the one that wrote them,
   deliberately. If it ever drops below GROUNDED, something moved and the diff is the finding.
3. **The hard tail is frozen by hash.** Editing the record list fails the load rather than
   re-freezing. If you need to change what is in it, that is a deliberate act with a new hash in
   `data/gold/manifest.json` and a sentence in the report saying why.

**The exit criterion is half open (decision D-5):** the reproduction package returns REPRODUCED,
24 of 24, on this machine, and no third party has run it. `THIRD_PARTY_ATTESTATIONS` is empty and a
test asserts it stays empty. A receipt from outside — especially a DIVERGED one — is the single
most useful thing anyone can contribute to R3.
