# PROGRESS — Errata

**Checkpoint:** 20 August 2026 (sixth session — **PHASES P6 / R3 built**)
**Context:** read `HANDOFF.md` for orientation and **`PHASES.md` for the plan of record**.
This file is the task board and the running log.

---

## Headline

```
Docs / research / spec        ████████████████████  100%   phases 1-5 + PRD complete
R0  kill tests                ███████████████████░   ~95%  gate 1 PASS, gate 2 MEASURED, gate 3 deferred
R1  single-SKU audit+console  ██████████████████░░   ~90%  BUILT — errata-audit; entered on waiver D-3
R2  catalog-scale audit       ██████████████████░░   ~90%  BUILT — errata-scale; FR-8.1–8.9 all met
R3  benchmark + ecosystem     ██████████████████░░   ~90%  BUILT — errata-r3; 7 of 9 measured, 2 honestly NOT MEASURED
R4  commercial               ░░░░░░░░░░░░░░░░░░░░     0%  out of PRD scope
```

**Tests:** all green — **1,199** (1,078 + 121 for R3). `ruff check .` clean.

**R3 is ~90%, not 100%, and the missing tenth is a person.** FR-9.3 (reviewer-seconds per verified
attribute) and FR-9.4 (evidence-acceptance rate) are measurements of people; the protocol and the
arithmetic ship, and no reviewer has been timed. The exit criterion — *a third party reproduces our
published scores from the repo* — is half met: `errata-r3 reproduce` returns **REPRODUCED, 24 of
24** here, and nobody outside this repository has run it (decision **D-5**). See
`docs/R3-report.md`.

**R2 is ~90%, not 100%, and the missing tenth is one word.** The exit criterion asks for a 10k+ SKU
**public** catalog. 10,001 records and a drainable ranked queue are done; no public industrial
catalog of that size with retrievable source documents was reachable, so the corpus is constructed
and labelled as such everywhere it is read (decision D-4). See `docs/R2-report.md` §7.

**R1 is ~90%, not 100%, and the missing tenth is named:** FR-2.2's embedding retriever,
cross-encoder and LLM selector are interfaces with no implementation, and FR-6.1 has no calibration
set because calibration needs reviewer decisions and nobody has made any. Both are stated by
`errata-audit status`, on every HTML report, and in `docs/R1-report.md` §1.

**Gate 1:** ✅ `PASS` — **1.30%** false positives (3/230), on the strict metric. Threshold: <2% pass, >5% stop.

Movement this session (findings 9, 10, 13, 15 fixed): the FP **count** never moved — it is still only
the three pinned `KNOWN_FALSE_POSITIVES`. The rate fell because the denominator grew with *correct*
findings, which is the only honest way for that number to improve.

| | before | after |
|---|---|---|
| FP rate (strict) | 1.38% (3/217) | **1.30%** (3/230) |
| cases passing | 529 | **546** |
| false negatives | 20 | **13** |
| missed defects (answered wrong) | 6.42% | **4.91%** |
| missed defects (incl. declined) | 21.51% | **17.36%** |
| coverage (not declined) | 76.9% | **79.49%** |
| exact-label agreement | 84.8% | **87.50%** |

Both readings now agree at 1.38%: the strict *reviewer-experienced* rate (every redline that should
not have been raised) and the narrow §6.1 rate. They were 6.22% vs 1.33% before the over-resolution
fixes; that gap is now closed, which is why this PASS means something the earlier 0.00% did not.

The 3 remaining are the pinned `KNOWN_FALSE_POSITIVES` (units: identical-interval ×2, temperature-delta ×1).

**Still true and worth carrying:** every case was labelled by the same author who wrote the
comparator. FR-0.1 requires independent dual-labelling before this number is quotable outside the
repo; the packet to do it now exists (`errata-r0 labelling packet`) and the labelling does not.
The suite is at **347/500** equivalence pairs and **216/500** contradictions.

⚠️ **And read this next to the PASS.** Resolved against the comparator, the dual-labelled cases
put the same suite at **4.78%** — above the 2% threshold. The PASS is real and it is conditional.
See session 3 below and `docs/R0-report.md`.

---

## R0 — the three kill tests

### Gate 1 — Equivalence suite (FR-0.1, FR-0.2)

- [x] Harness, scoring, Wilson intervals, `errata-r0 equivalence` CLI
- [x] Seed suite, 175 cases across 6 families
- [x] Adversarial suites — **449 cases added** (ingress 45, materials 70, packaging 64, terms 89, threads 114, units 67)
- [x] Citation audit of 5 of 6 hard suites (47 source fields corrected)
- [x] a/b swap-symmetry test — **0 violations across 624 pairs**
- [x] False-negative audit of the gate metric itself
- [x] **Citation-audit `threads_hard.yaml`** — done 19 Aug 2026 against ISO 261:1998 itself; 6 citations corrected, 0 labels changed
- [x] **Fixed the 4 thread-parser bug clusters** (findings 5–8) — cleared all 15 thread FPs
- [x] **Fixed the gate's own accounting** (findings 1–4) — the number is now quotable, and it stops
- [~] Independent dual-labelling — **packet and kappa arithmetic built**; the labelling itself needs a person who did not write the comparator

**Suite:** 624 cases. **Status:** ✅ PASS at **1.30%** (both readings agree); **4.78%** under the
adversarial reading of the dual-labelled cases.

### Gate 2 — Operating point (FR-0.3)

- [x] `operating_point.py` — ExtractBench-compatible grounding F1 (IoU ≥ 0.5, verbatim), risk-coverage curve, AURC, precision/selective-accuracy at 20/40/60%
- [x] Corpus format + loader (CSV/TSV/YAML/JSON) — real data drops in with zero new code
- [x] `NOT_MEASURED` pinned unconditionally on synthetic input
- [x] Wired to CLI with `--corpus` / `--json`
- [x] Bug fixed: verdict trusted a coverage row smaller than the verdict floor (a lucky 7-record window could "confirm" inside a 34-record corpus)
- [x] **Corpus built** — 1,426 records from two real ABB S200 datasheets (P3). Gold values and
  word boxes read from the documents' own ordering tables. ⚠️ document-derived, not expert-labelled
- [x] **Grounding pipeline (FR-1.2–1.5)** — built as a fenced throwaway spike, `spike/`
- [x] **N9 fixed:** the verdict compared a selective coverage row against a full-coverage baseline

**Status:** ✅ **MEASURED — ASYMMETRY NOT CONFIRMED**, exit code 2.
At full coverage, word-level grounding F1 **46.34%** (conservative 43.72%) against ExtractBench's
**46.4%**: a dead heat, margin −2.68pp. Value F1 67.15% against 95.6%. Selectively, risk is
**0.00% out to 20% coverage** — §0.3's mechanism 1 intact while the asymmetry is unproven.
AURC 0.3370. Full detail in `docs/R0-report.md`.

### Gate 3 — Calibration coverage (FR-0.4)

- [x] `coverage.py` — label-floor derivation from split-conformal bounds, 3 allocation strategies, hierarchical pooling, budget sweep
- [x] `NOT_MEASURED` pinned unconditionally on synthetic input
- [x] Wired to CLI with `--distribution` / `--json`
- [x] Bug fixed: headline budget contradicted the module's own stated finding (50k → 5k, anchored to `RESCOPE_BELOW`)
- [x] 61 unit tests
- [ ] **One real ETIM class distribution** — IDEA/ETIM datapool export, or a friendly distributor.
  **Decision D-1 taken:** hunt closed after three datapools (ETIM, 2BA, EFObasen) all gate it;
  ready-to-send request at `docs/data-request-etim-distribution.md`

**Status:** NOT MEASURED — deferred by decision, not by oversight. Structural finding on synthetic data: greedy allocation calibrates **5.95% of classes / 77.39% of SKUs** at a realistic 5,000-label budget. Volume is calibratable; the taxonomy is not.

---

## R1 — the single-SKU audit (PHASES P4) ✅ BUILT

**Package:** `audit/` → `errata-audit` 0.1.0. **Full write-up with every number:** `docs/R1-report.md`.

**Entered on decision D-3, a recorded waiver**: the PRD gates R1 on all three R0 gates and gate 3 is
`NOT_MEASURED` by D-1. What the waiver covers, costs and would take to reverse is in `PHASES.md` §10,
and `errata-audit status` prints it — a waiver nobody can see from the tool has already been
forgotten.

```bash
./.venv/Scripts/errata-audit.exe sku --random --html var/audit/console.html
```

### What was built

- [x] **FR-1.1 ingest** — values preserved byte for byte; a missing column and a blank cell stay
      different facts (schema gap vs fill-rate defect)
- [x] **FR-1.2/1.3 documents** — content-addressed blob store over `errata_spec.registry`; the
      network is **opt-in** and refuses otherwise, because "the audit used the PDF at this URL" and
      "the audit used yesterday's PDF" are different claims
- [x] **FR-1.4 layout** — canonical char-indexed layer, per-word boxes, deterministic, cached on
      content hash, version-stamped. **No OCR**: born-digital only
- [x] **FR-1.5 tables** — cell / row-header / column-header roles; merged cells resolved by box
      geometry, never by carrying the last value forward
- [x] **FR-1.6 column bands** — and the refinement that matters: a gap a text block spans is not a
      gutter, or every wide-column table splits into one "product" per column
- [x] **FR-2.1 ETIM loader** — release-parameterised, UTF-16-LE / `;` traps pinned by test, ODC-By
      attribution carried into every report rather than left in a README
- [x] **FR-2.2/2.3/2.4 class resolution** — three stages, five-candidate cap enforced by a raise,
      allow-list in configuration with a stated reason per entry, abstention with a reason
- [x] **FR-3.1–3.4 re-derivation** — schema-constrained, span-required, and **blind to the catalog,
      pinned by signature inspection** so a keyword added in six months fails the build
- [x] **FR-6.1/6.2/6.3 confidence** — Platt fit, reliability diagram, risk–coverage, AURC, and the
      Declined bucket with exactly one reason per row
- [x] **FR-7.1–7.9 console + CLI** — three panes, word box, header box in a second colour,
      counter-evidence that is never empty, queue rows as sentences, adjudication into an
      append-only ledger, and an exit code that is the decision
- [x] **`errata-audit serve` — the console as a local web app.** A static file cannot accept a
      decision, and FR-7.1 asks the reviewer to adjudicate *without leaving the screen*. Standard
      library only, binds to loopback, refuses a non-loopback bind without a flag. Verified end to
      end in a browser: one decision wrote `redline` + `score` + `adjudication` + `claim`, captured
      **25.7 reviewer-seconds** (FR-9.3) and an evidence-acceptance answer (FR-9.4), and the
      dashboard's calibration line updated to say what was still missing
- [x] **FR-8.9** — safety-class acceptance needs a second named adjudicator, enforced at
      construction *and* through `model_copy`, which skips validators and was silently bypassing it

### The numbers

| | |
|---|---|
| Demonstration catalog | 278 records, 1 real ABB datasheet |
| Injected defects raised | **56 / 56** |
| Fill-rate gaps raised | **11 / 11** |
| False positives | **0** across 168 correct rows **and 40 equivalence traps** |
| Coverage | **79.4%** — 276 of 285 declines are the order code, which has no grammar |
| Class resolution | top-1 **47.1%**, top-5 **100%**, 7/7 must-abstain held, **0 wrong** |

**Read the detection numbers next to this:** the catalog is **constructed** (no public ABB feed
exists) with defects injected by `sha256(sku)`; the datasheet, the values, the spans and the boxes
are real. The caveat is printed by the CLI and rendered on the face of every report.

**The most useful measurement in R1** is the 47.1% / 100% split: retrieval and reranking put the
right class in the shortlist every time, and the selector — the stage FR-2.2 specifies as an LLM and
this package does not ship — commits half the time and is never wrong. The gap is that stage's job,
and it is now measured rather than assumed.

### Findings raised in P4

- **N11 · `errata_valuesem` cited an ETIM feature that does not exist. FIXED.** `terms.yaml`
  declared `EF000094` for the tripping characteristic; **ETIM 10.0 has no EF000094**, and the MCB
  class declares `EF000889` "Release characteristic". HANDOFF §7's signature at a new location.
  Fixed with the locator and the evidence in the `source:` field, and pinned by a cross-package test
  that checks every ETIM id cited anywhere in this repository against the loaded release.
- **N12 · The text-window fallback manufactured a confident, evidenced accusation. FIXED.** On the
  S200 M UC datasheet it returned `0.3` for a 0.2 A device out of the running text
  `0.2 A 0.3 A 0.5 A …`. Nearest-in-reading-order is a tie-break, not evidence; the fallback now
  declines with `layout_unreadable` when the window offers competing values. Negative control: a
  genuine single-candidate fallback still resolves.
- **N13 · The class-resolution evaluation was scoring its own tie-break. FIXED.** It reported top-1
  **88.2%** and resolved five of seven must-abstain cases, because it passed the whole attribute map
  as schema-fit evidence — so the bare word "breaker" got the same tie-break a real record gets. The
  honest numbers are 47.1% / 100%.
- **N14 · Redline ids were random, so a decision could not attach to a finding twice. FIXED.** The
  `adjudicate --redline-id …` command the CLI prints stopped working the moment the audit was
  re-run. Surface: a usability bug. Underneath: a ledger accumulating one row per run per finding
  cannot answer "has this been decided?", and the web console could not have worked at all. Ids are
  now `uuid5(namespace, doc sha256 | sku | attribute | catalog value | proposed value)` — the same
  content-addressing rule the document register already uses.

### One spec change, called out individually

`errata_spec.DeclinedReason` gained **`CLASS_UNRESOLVED`**. FR-6.2 enumerates six reasons and none
of them covers "class resolution could not separate its top candidates":
`calibration_out_of_distribution` claims we know where our calibration ends, and
`ambiguous_multi_product_page` blames the document for a decision the resolver declined to make. It
joins `INCOMPARABLE_KINDS` and `NO_SPAN`, which were added for the same reason. A reason that
misdescribes what happened is a silent default with better manners.

### Left open, logged rather than dropped

- FR-6.3's per-run risk–coverage curve is **built and empty** — it scores adjudicated findings and
  there are none. A run has no curve until a reviewer decides something, which is the honest shape.
- FR-9.3 reviewer-seconds per verified attribute: collected, no data, same reason.
- The 17-case class-label set is **single-labelled by the implementer** (FR-0.1's conflict of
  interest, unchanged).
- **`spike/` is FROZEN** (P3 rule 5): banner written, no further changes, and a boundary test fails
  the build if any distribution imports it. Frozen rather than deleted because `build_corpus.py` is
  the only thing that can regenerate gate 2's corpus, and a measured gate whose corpus cannot be
  rebuilt is a measurement nobody can check.
- **One reviewer-second measurement exists (25.7s).** One timing is an anecdote; FR-9.3 becomes a
  claim at a few hundred decisions, which needs reviewers rather than code.

---

## R2 — the catalog-scale audit (PHASES P5) ✅ BUILT

**Package:** `scale/` → `errata-scale` 0.1.0. **Full write-up with every number:** `docs/R2-report.md`.

```bash
./.venv/Scripts/errata-scale.exe run --html var/scale/report.html
```

### The numbers, on 10,001 records

| | |
|---|---:|
| **groundable fraction** (FR-8.1) | **2.77%** — 277 of 10,001 records have a readable source document |
| queue rows | **1,495** — 1,428 from T0, 67 from T1 |
| error signatures (FR-8.5) | 9 |
| coverage over the 277 groundable records | 79.4% |
| coverage over the whole catalog | 89.2% |
| T0 detection vs the corpus's stated ground truth | **1,428 / 1,428** findings, **986 / 986** abstentions |
| **false positives on 654 equivalence-trap families** | **0** |
| false positives on 1,918 clean families | **0** |
| T2 work over 10,001 records | **67** counter-evidence searches |
| batch reversal | **1,000 records**, idempotent, nothing deleted |

**Read the coverage next to the groundable fraction, always.** 79.4% describes the population where
evidence existed; 2.77% is how much of the catalog that was.

**T1's 67 findings are R1's numbers unchanged** — the same 56 injected defects and 11 gaps — produced
by the R2 pipeline without touching `audit_sku`. R2 adds scale, not a second opinion.

### What was built

- [x] **FR-8.1 Groundable Fraction Report** — computed before any audit, four exhaustive buckets,
      percentages summed on **exact rationals** (a report whose own arithmetic is approximate has no
      business auditing anyone), every bucket enumerable to record level, ranked document-recovery
      leads
- [x] **FR-8.2 ledger at scale** — supersedes chains reconstructed from the links rather than from
      file order; fork, cycle and orphan each raise. **`errata-scale integrity` parses every module
      of every distribution** and asserts no ledger UPDATE or DELETE exists anywhere
- [x] **FR-8.3 policy engine** — safety escalation first, rank beats recency, tolerance never
      dropped, equal rank abstains; **every** resolution records `policy_version`, including the
      ones that resolve nothing
- [x] **FR-8.4 triage router** — five factors carried separately, each with its provenance sentence
      and a `measured` flag, so an unsupplied `revenue weight = 1` never reads as a measurement
- [x] **FR-8.5 signatures** — `size == len(members)`, fingerprint printed beside the count
- [x] **FR-8.6 no organisation field** — enforced on the schema at import, plus a test that a schema
      growing `supplier_id` is rejected, plus a behavioural test that the same defect under two
      manufacturers is **one** cluster
- [x] **FR-8.7 tiers T0→T3** — T0 is new: the feed against its own declared units, and against
      itself. The scaling claim is tested at two catalog sizes rather than asserted at one
- [x] **FR-8.8 batch reversal** — a query over stored facts, narrowable to one signature
- [x] **FR-8.9 two adjudicators** — refused before the ledger is touched, and again by `Redline`
- [x] The feed itself is hash-registered and citable, so a T0 finding cites a real span in a real
      artifact instead of relaxing the evidence rule

### Findings raised in P5

- **N15 · Redlines and claims speak two vocabularies for one attribute. CONTAINED.** `build_redline`
  writes `rated_current`; `stable_redline_id` derives the id from `etim:EF000227`. R1 was internally
  inconsistent and nothing before R2 clustered across the two. Fixing it changes every redline id
  and invalidates recorded adjudications — an R3 change, logged rather than done quietly.
- **N16 · The feed index cited the wrong two characters of every row. FIXED.** Self-consistently
  wrong: the snippet was sliced from the same bad span. **A grounding test that only checks internal
  consistency checks nothing** — this repository has now learned that twice.
- **N17 · `--limit` meant two things in one command. FIXED.** A drain audited 3% of the catalog and
  reported a drained queue. Now `--count`.
- **N18 · Two `conftest.py` files shadowed each other across distributions. FIXED.** Seven R1 test
  files stopped collecting — but only in the full suite, and only in one order.

### Left open, logged rather than dropped

- **The exit criterion's "public" half.** Open, with the hunt recorded (`docs/R2-report.md` §7) and
  decision D-4 written down. It needs a catalog, not code: `--catalog <file>` takes any CSV today.
- **FR-6.1 still has no calibration set**, and at 1,495 findings that now costs more than it did at
  67: the queue's top rows are ordered on blast radius alone, which is defensible and is not the
  ordering the PRD describes.
- **FR-8.3's engine has no caller inside the run.** Multi-source resolution needs a second source
  feed, which R2 has no honest way to obtain.
- **T0's precision is measured against injected defects.** Not circular — the traps are R0's own
  equivalence shapes — but not a field measurement either.

---

## R3 — the benchmark and the ecosystem (PHASES P6) ✅ BUILT

**Package:** `ecosystem/` → `errata-r3` 0.1.0. **Full write-up with every number:** `docs/R3-report.md`.

```bash
errata-r3 reproduce --full          # 24 checks against the published numbers, then the leaderboard
errata-r3 gold verify               # 1,426 annotations re-derived from the documents themselves
errata-r3 leaderboard --html var/r3/leaderboard.html
```

### The numbers

| Axis | Requirement | Result |
|---|---|---|
| grounding | FR-9.1 | word-level F1 **46.34%** @ IoU 0.5 (conservative 43.72%) vs ExtractBench **46.4%** — margin **−0.06pp**, n=1,426 |
| class assignment | FR-9.2 | top-1 **47.06%**, top-5 **100.00%**, must-abstain **7/7**, n=17 |
| compound values | FR-9.2 | **14/20** correct [48.10%, 85.45%], 2 FP, 4 unexpected abstentions |
| crosswalk | FR-9.2, FR-9.7 | 2 UNSPSC codes given 27 and 29 ETIM features; **3/3** unmapped in-scope codes correctly silent; 3 refusals recorded |
| supersession | FR-9.2 | **5/5**; forked and cyclic histories raise rather than resolve |
| abstention | FR-9.2 | **AURC 0.3370**; risk **0.00%** out to 20% coverage |
| gold set | FR-9.5 | 1,426 annotations, **1,426 verified GROUNDED** against the documents; no PDF in the repository |
| hard-tail split | FR-9.6 | 275 records (19.28%), hashed; guard fires on a tuning run that touches it |
| ECLASS scan | FR-9.8 | 238 files, **0 findings**; distributions scanned too; negative control fires |
| leaderboard | FR-9.9 | **2nd of 8** on grounding; loses page-level F1 by 17.75pp and value F1 by **28.45pp** |

### What R3 does not claim

- [ ] **FR-9.3 reviewer-seconds per verified attribute** — NOT MEASURED. Nobody has been timed.
      Protocol at `docs/reviewer-protocol.md` and `errata-r3 reviewer --protocol`.
- [ ] **FR-9.4 evidence-acceptance rate** — NOT MEASURED, reported alongside grounding F1 in that
      state. The repository's own adjudications were made by the implementer; `errata-r3 reviewer
      --ledger` reads them and still returns NOT MEASURED, naming the role it found.
- [ ] **A third party reproducing the scores** — the package is built; nobody outside has run it
      (decision **D-5**). `THIRD_PARTY_ATTESTATIONS` is empty and a test asserts it stays empty.
- [ ] **A second judge for the bridge** — seven single-judged mappings, validated not verified.
- [x] Everything above printed by `errata-r3 status` as well as by the report.

### Findings raised during P6

- **N15 · one attribute, two vocabularies — FIXED**, and R2's reason for deferring it was wrong:
  both id functions already hashed the uri, so **no redline id moved**. Pinned by a test against
  the literal id in the R1 ledger.
- **N19 · PyMuPDF's layout advertisement was printing to stdout on every `find_tables()`**, on top
  of every `--json` payload this repository emits. `warnings.simplefilter("ignore")` never silenced
  it because it is not a warning. Redirected to stderr; regression test runs the executable.
- **N20 · the UNSPSC codeset is cp1252**, and utf-8 raises 5,779 bytes in. In the manifest's loader
  notes now, beside ETIM's utf-16-le trap.
- **N21 · one of the two gold documents is unreadable by the gold builder** — its ordering tables
  are transposed. Recorded as a gold-set gap rather than left to be inferred from a record count.

---

## Work queue (from `HANDOFF.md` §5)

### P0 — gate accounting. Do these before quoting any number.

- [x] 1 · `over_resolved` preempts the FP check — 11 findings (8 SEV-1) excluded from numerator, kept in denominator
- [x] 2 · Declined contradictions booked as abstentions, not misses — miss rate understated ~4.9×
- [x] 3 · No coverage-adjusted FP rate — 21% of the suite vanishes from the metric
- [x] 4 · `CaseResult.accusatory` is dead code — fires 0/624

### P1 — comparator & parser bugs (failing cases already pinned)

- [x] 5 · Coarse-pitch lookup incomplete — M9, M11, M4.5, M68, M2.2, large UNC/UNF, NPT 3½, BSPP 5 *(9 FPs)*
- [x] 6 · Length suffix parsed as pitch — `M8x40`, `M6x30`, `M10x50` *(3 FPs)*
- [x] 7 · ISO 965 `6g6g`→`6g` abbreviation missing *(2 FPs)*
- [x] 8 · Decimal/fraction nominal — `0.5 NPT` vs `1/2 NPT` *(1 FP)*
- [x] 9 · Hot-dip galvanised ≡ zinc-plated — **fixed.** Split `steel/galvanised` into
  `steel/coating/hot_dip_galvanised` (ISO 1461) and `steel/coating/zinc_electroplated` (ISO 4042 /
  ASTM B633), sharing the `coating` facet so they compare and disagree. Bare "galvanised" became a
  *generic* subsuming both rather than an alias of hot-dip — the standard does not license a default
  process, and mat-h024 had flagged the earlier assumption as UNVERIFIED. Cleared mat-h019/020/021
  (3 false negatives), plus mat-h023 (alias gap) and mat-h024. **No suite labels were changed** —
  the suite already expected contradiction. Feared regressions did not materialise.
- [x] 10 · `1.4404` ≡ `1.4435` — **fixed.** Modelled as two children of the 316L family.
  ⚠️ **One suite label changed:** mat-h005 granularity → contradiction. Its label called 1.4435 "the
  narrower, tighter-spec member"; EN 10088 says Mo 2.00–2.50 vs 2.50–3.00, i.e. **shifted, not
  nested** — a bar meeting 1.4435 at Mo 2.8 fails 1.4404's ceiling. Neither subsumes the other.
  Prior reading preserved in the case's rationale. **This one wants a second pair of eyes.**
- [x] 11 · Packaging levels not modelled — `Box of 10` vs `Carton of 200` fires SEV-1 on a legitimate hierarchy
- [x] 12 · Property class vs coating treated as contradiction — orthogonal facets, 4 SEV-1 over-resolutions
- [x] 13 · `MCB`/`RCBO`/`RCCB` unparseable — **fixed.** Added a `device_type` vocabulary
  (MCB / RCCB / RCBO / MCCB) and a `Circuit breaker` generic over it, which needed a new
  `subsumes_terms` mechanism on generics. Cleared **9** cases (trm-h062–h070) plus the trip-curve
  K/Z reversed-alias gap (trm-h006/h007). The terms family went from 11 failures to **zero**.
  `ELCB` / "earth leakage circuit breaker" left deliberately **unregistered** — three live readings
  (voltage-operated, RCCB, ETIM's RCBO-shaped EC000905) and no way to pick one from the surface
  form; pinned by a test so nobody "helpfully" adds it.
- [x] 14 · `IP6/7` misparsed as a set instead of refused
- [x] 15 · `packaging.yaml` cites UN/CEFACT Rec 20 wrongly — **fixed, and it was worse than logged.**
  Verified against the machine-readable Rec 20 Rev 17 list (2136 entries). Confirmed: `CQ` is
  *cartridge*, not Hundred (that is `CEN`); `RL` is *reel*, `RO` is *roll*. **New, unlogged:** `DZ`
  is not a Rec 20 code at all (dozen is `DZN`). **Also new and structural:** every container noun in
  the file — `BX PK CT BG RL RO CS TU` — carries status `X` in Rec 20 with the description "Use
  UN/ECE Recommendation 21". They are Rec **21** codes. The file and `model.py` both cited the wrong
  recommendation for the entire container vocabulary. Provenance header added; codes pinned by test.
  ⚠️ **One suite label changed:** pkg-h049 undetermined → equivalent. That case carried an explicit
  `[UNVERIFIED - needs checking]` marker saying "if RO does turn out to be a standard code, this is
  a real coverage gap". It is. The research it asked for was done.

### P2 — suite quality

- [ ] 16 · Audit `threads_hard.yaml` (114 cases, never audited)
- [ ] 17 · `expect_alternatives` laundering — `pkg-h026/h031/h035`, `pkg-010`
- [ ] 18 · 11 dual-labelled cases excluded from both supporting denominators
- [ ] 19 · Apply/reject the 6 reported label findings (`mat-h063` is the sharpest)
- [ ] 20 · Independent dual-labelling
- [x] 21 · **N1 sweep — closed.** Suite `source:` fields corrected against both machine-readable
  UN/CEFACT lists, now fetched and hash-registered. Detail in the session-3 log below.

---

## Done this session (session 6 — 20 Aug 2026, PHASES P6 / R3)

- **Built `errata-ecosystem` (R3)** — the benchmark and the ecosystem, `errata-r3`. Six axes, a
  gold set distributed as URLs and hashes, a frozen hard-tail split with a tuning guard, the
  published ETIM↔UNSPSC bridge, the bring-your-own-licence ECLASS adapter and content scanner, a
  leaderboard generated from the harness, and a reproduction receipt. **121 tests added
  (1,078 → 1,199)**, `ruff check .` clean.
- **Obtained a real UNSPSC codeset** — 71,502 commodity rows, four levels, hash-registered in
  `data/reference/manifest.json` and fetched by `scripts/fetch_reference_data.sh` like everything
  else. Confirmed by inspection that it carries **no attribute layer of any kind**, which is the
  hole FR-9.7 exists to fill and which the repository had until now taken from the PRD's say-so.
- **Fixed N15** (one attribute, two vocabularies) with zero redline-id churn, and **N19** (a
  library's advertisement on top of every `--json` payload). Raised **N20** and **N21**.
- **Corrected `46.43` to `46.4` in the README** — the paper prints one decimal place. The rest of
  the repository had already been corrected; the front page had not.
- **Reported two requirements as NOT MEASURED and one exit criterion as half met**, rather than
  finding a reading of the available data that would have produced numbers.

---

## Done this session (session 3 — 19 Aug 2026, environment + P1 start)

Plan of record is now **`PHASES.md`** — eight phases, P0 setup through P7. This session closed
P0 and five of P1's twelve tasks.

**Tests 489 → 605. Ruff: 77 findings → 0. Gate 1 unchanged at 1.30% throughout** — every change
below was verified not to move it.

### P0 · Environment — closed

Reproducible from a clean machine: `scripts/setup.sh` (idempotent, self-verifying),
`requirements-lock.txt` (25 packages pinned), `scripts/fetch_reference_data.sh` +
`data/reference/manifest.json` for reference data. The manifest is the FR-9.5 pattern applied to
our own inputs — URLs and sha256s committed, payloads gitignored under `var/reference/`.

**Reference data now downloaded and hash-verified:**

| Artifact | Verified contents |
|---|---|
| ETIM 10.0 ALL-SECTORS CSV (ODC-By, no login) | 5,640 classes / 159 groups — matches HANDOFF §9 exactly |
| UN/CEFACT Rec 20 Rev 17, units of measure | 2,136 codes |
| UN/CEFACT Rec 21, package types | 406 codes |

Two traps recorded in the manifest for the future FR-2.1 loader: the ETIM CSVs are **UTF-16-LE
with no BOM** (`encoding='utf-16'` raises outright) and the delimiter is `;`. The R1 scope class
ids were read out of the file rather than recalled — `EC000042` MCB, `EC000003` RCCB, `EC000271`
MCB plug model, `EC001047` selective main line, and `EC000905` earth leakage circuit breaker,
which is the case `errata_valuesem` deliberately leaves unregistered.

**Gate 3 is not unblocked by any of this.** Confirmed again by inspecting all nine ETIM CSVs:
there is no SKU-count column anywhere in the release.

### P1 tasks closed

- [x] **1.6 · N1 sweep.** Six suite `source:` fields corrected in `packaging.yaml` and
  `packaging_hard.yaml`. **Zero labels changed**, gate unmoved — the same discipline as the
  earlier 47-field audit. Findings, all re-derived from the lists rather than taken on trust:
  - `CT` cited as a Rec 20 code in two places. It carries **status X** in Rec 20 Rev 17 with the
    description *"Use UN/ECE Recommendation 21"*. Rec 21 is where `CT` "Carton" lives. Confirmed
    for all eight container nouns `BX PK CT BG RL RO CS TU`.
  - **NEW, and sharper than N1 as filed: `PCE` is not a UN/CEFACT code at all** — absent from
    Rec 20 Rev 17 *and* from Rec 21. Rec 20's code for "piece" is `H87`. Two cases cited
    "Rec 20 code PCE", which reads as authoritative precisely because it is specific. The
    ontology was already right: `pce` is held there as a trade alias of `EA`, not as a standard
    code. Only the suite citations were wrong.
  - `EA` and `PR` **were correctly cited** — both are active Rec 20 units. Noted the collision
    worth knowing: `PR` is "pair" in Rec 20 but "Receptacle, plastic" in Rec 21.
  - All six of finding 15's claims independently re-verified and **all six held**: `CQ`=cartridge
    (not hundred), `CEN`=hundred, `RL`=reel, `RO`=roll, `DZN`=dozen, `DZ` absent.
  - **Turned into a permanent guard,** because the finding was that this recurs: 12 tests in
    `bench/tests/test_citation_integrity.py` fail the build if any suite file calls a Rec 21
    container noun a Rec 20 code, or cites a code that exists in neither list.
  - ⚠️ **Provenance caveat, stated in the manifest:** `unece.org` returns HTTP 403 to scripted
    clients (four URL forms tried, browser user-agent tried), so both lists came from the
    Frictionless `datasets` mirrors. Corroboration rather than blind trust: the Rec 20 file
    carries **2,136 codes, exactly the count session 2 recorded** when it verified finding 15,
    and all six of that session's specific claims re-derive from it. A citation that has to be
    defended outside this repo should still be re-checked against the UNECE original.

- [x] **1.7 · Ruff to zero**, 77 → 0, tests green either side, gate unmoved.
  Two rules were **not** accepted, with the reasoning written into `pyproject.toml` rather than
  silently suppressed. `UP042` wants `class X(str, Enum)` → `StrEnum`; verified on the
  interpreter that this changes `str(member)` from `"Class.MEMBER"` to `"member"`, and `Gate`,
  `Verdict`, `Provenance`, `Strategy`, `GroundingLevel` and `CoverageGate` are interpolated into
  the kill tests' own reports — accepting it would have silently changed what R0 prints while
  every test still passed. `E402` in test files is deliberate section structure.

- [x] **1.8 · `valuesem` now builds and ships standalone (FR-4.6).** Added the declared-but-absent
  `README.md`, `LICENSE` and `NOTICE`. All four distributions build sdist+wheel. Acceptance check
  actually performed: the wheel was installed into an **empty interpreter** with nothing else from
  this repo present, and `316 SS`≡`1.4401`, `0.5 in`≡`12.7 mm`, `Each` vs `Box of 10`, and the
  refusal path all behaved. 8 tests pin the metadata so the release path cannot rot again while
  the development path stays green — which is exactly how this defect survived.

- [x] **1.9 · CLI output encoding.** `errata-r0 status` emitted `§` as cp1252 byte 0xA7 through a
  pipe, arriving mangled anywhere expecting UTF-8. Fixed at the entry point, not in the operator's
  environment. 13 tests; negative control confirms 5 of them fail with the fix disabled.

- [x] **1.10 · Stale docs.** Test counts corrected (HANDOFF said 489 in §2 and 451 in §4).
  HANDOFF §3 hardcoded `C:/Users/Aditya Belhekar/...` from another machine and now points at
  `scripts/setup.sh`.

### P1 tasks closed (continued)

- [x] **1.1 · `threads_hard.yaml` citation-audited** — 114 cases, the file HANDOFF §7 flags as the
  largest never-audited suite. **ISO 261:1998 was opened**: the free iTeh publisher preview carries
  the complete Table 2 and clauses 1–5, and is now hash-registered in the manifest. This also
  closes the tooling gap HANDOFF §7 blamed for the unverified ExtractBench figure — there is a PDF
  text/render toolchain in the venv now, which unblocks P3 task 3.10.
  - **28 of 31 numeric coarse-pitch claims verified correct** against Table 2.
  - **3 wrong and corrected:** M11, M4,5 and M2,2 were each called "3rd-choice"; Table 2 puts all
    three in Col. 2. Their *pitches* were right, which is exactly why nothing failed and nobody
    noticed. Of the diameters this file discusses, only M9 is genuinely 3rd choice.
  - **2 wrong and corrected:** two cases argued from "no metric pitch exceeds 6 mm". Table 2 lists
    a pitch of **8 mm** at M125 and M130. 6 mm is the largest *coarse* pitch; above M68 the table
    lists no coarse pitch at all. The verdicts were right, the premise was not.
  - **1 mis-attribution:** the right-hand-default rule was sourced to ISO 261. Clause 4 of that
    standard says a thread "shall be designated according to ISO 965-1".
  - **Stated honestly in the file header:** ASME B1.1/B1.5/B1.15/B1.20.1/B1.20.3/B1.21M, BS 84,
    BS 21, ISO 7-1, ISO 228-1, ISO 965-1 and ISO 2901 are paywalled and **were not opened**. Their
    claims were checked for internal consistency only and are marked `[UNVERIFIED]`.
  - **Zero labels changed, gate unmoved.**

- [x] **1.3 + 1.4 · the dual-labelling instruments** — findings 17 and 18, which turn out to be the
  same defect seen from two sides. **This produced the most consequential result of the session.**
  - `Case.accepted` unions the classes of every label, so a case labelled `equivalent` *and*
    `contradiction` scores PASS whichever way the comparator answers. **8 findings sit on such
    cases.** New `fp_adversarial` metric resolves every one against the comparator:
    **the gate reads 1.30%; the same suite reads 4.78% under that reading** — above the 2% PASS
    threshold, with an upper bound (8.36%) past the 5% STOP line.
  - **The PASS is real but conditional**, and the condition is a set of judgment calls made by the
    same author who wrote the comparator. The report now says so on its face, the JSON carries the
    band and enumerates the contested cases, and a test pins the set so it can only shrink.
    **The gate still judges on `fp_reviewer_experienced`** (ground rule 8) — the band informs the
    verdict, it does not silently become it.
  - The sharpest four are `pkg-010`, `pkg-h026`, `pkg-h031`, `pkg-h035`: a quantity word against a
    container noun **at the same quantity** — twelve against twelve — resolved as a SEV-1 packaging
    frame error whose own stated harm (the line is priced wrong) cannot apply when the quantities
    match.
  - Finding 18: **11 cases sit in neither supporting denominator**, because their labels straddle
    defect and no-defect. The report now prints the reconciliation — 348 + 265 + 11 = 624 — so a
    reader who adds the denominators and comes up short is told why instead of left guessing.
  - The pre-existing caveat said dual-labelling made the gate "marginally" easier to pass. That
    word was doing a lot of work and is now replaced by the measured number.

- [x] **1.5 · label findings adjudicated.** The referenced "audit report" **does not exist in this
  repository** — the finding list outlived its evidence, so only the two disputes recorded in the
  suite itself were actionable.
  - `mat-h063` (`18-8` vs `S30400`) **relabelled equivalent → granularity.** 18-8 names the
    18Cr/8Ni austenitic family covering 302/303/304/305; S30400 is specifically 304, and `mat-h041`
    already labels the identical generic-vs-specific relationship as granularity. The case now
    scores **false_negative** — the comparator answers `semantic_equivalence`, so it tells a
    reviewer "same value" when the datasheet is strictly more specific. Ground rule 4: the failing
    case is the finding and it stays failing. Gate metric untouched (an unflagged case is not in
    the `flagged` denominator); miss rate rose 4.91% → 5.26%, which is the honest direction.
  - `trm-h056` (`cage clamp` vs `push in terminal`) **deliberately unchanged and escalated.** The
    evidence is manufacturer marketing rather than a standard, and acting on it means splitting an
    alias in `ontology/terms.yaml` — a comparator change dressed as a label change, affecting every
    spring-family pair. Same reasoning as ELCB in finding 13: record the ambiguity, do not resolve
    it to make a number move.

- [x] **1.11 · determinism / gate-integrity audit finished.** Both questions the interrupted audit
  left open now have answers, and one of them was a live hole.
  - **`FORBIDDEN_CALLS` and `_dotted_name` were dead code.** The audit defined a 19-entry list of
    forbidden dynamic-dispatch calls — `__import__`, `eval`, `os.popen`, `ctypes.CDLL` — and then
    never wrote the assertion, because the agent hit its session limit. **The entire
    dynamic-dispatch half of the determinism boundary was unenforced.** This is finding 4 again:
    a guard nobody runs reads exactly like a guard that passes. Now wired, with a negative control
    proving it catches hostile source. **The package itself was clean** — the hole was in the test.
  - **Lazy imports do not defeat the scan.** Established rather than assumed: `ast.walk` is a full
    recursive traversal, so an import nested in a function, class, conditional or `try` is found.
    Pinned, because the obvious "tidy-up" — iterating `tree.body` instead of walking — would
    silently check only module level, which is where a hostile import would not be.
  - **Gates 2 and 3 survive a hostile attempt.** 16 attacks: corpus sizes from 1 to 5,000, a
    corpus renamed after a real manufacturer series, class counts to 5,600, quoting the report
    without the verdict. All refused. The one attack that works — hand-writing
    `provenance: empirical` over generated data — is designed behaviour and is now pinned as
    requiring an affirmative, attributable act rather than a default someone drifts into.

- [x] **1.2 · dual-labelling packet built** (the mechanical half; the judgment half is not mine).
  `errata-r0 labelling packet --out <csv>` emits all 624 cases **stripped of label, citation and
  rationale**, with written instructions; `errata-r0 labelling score --packet <csv>` reads a
  completed one back and reports raw agreement **and Cohen's kappa**, per family, naming every
  disagreement. Kappa is there because the label distribution is lopsided enough that two labellers
  guessing the majority class would agree often and establish nothing — the report says so itself
  when agreement is high and kappa is not. Tests pin the one property that matters: the packet
  must not leak the first labeller's answers. **No real dual-labelling has been performed and no
  agreement figure should be quoted until a packet comes back from a human.**

### Decisions D-1 and D-2 — taken 19 Aug 2026

Both were escalated as needing a human call and both are now decided, recorded in `PHASES.md` §10
with the evidence behind them.

**D-1 · Gate 3 → Route C (defer), Route B queued.** The hunt was re-run from a different angle —
the *national* datapools rather than ETIM and 2BA — and closed:

| Source | Result |
|---|---|
| ETIM 10.0 (downloaded, hash-verified) | **no count column in any of the nine CSVs** |
| EFObasen (Norway) | reachable; `/swagger/index.html` returns **HTTP 401** — API exists, gated |
| 2BA (Netherlands) | statistics behind membership |
| Open Datapool / ITEK (Germany) | no public per-class statistics endpoint |

Three datapools, three gates. **This is a structural property of the industry, not a gap in the
searching**, so the hunt is closed and the spend stops. Route A (scrape + infer a crosswalk) is
ruled out on ground rule 1 at any price — an inferred mapping yields a number with the authority
of a measurement and the content of a guess. A ready-to-send data request is written at
`docs/data-request-etim-distribution.md`; sending it is an outward-facing act and belongs to a
person. `--distribution` is already wired, so the day the file lands the gate goes live with zero
code changes.

**D-2 · Gate 2 → Route A, a fenced throwaway spike.** The circular dependency (gate 2 needs
grounding; grounding is R1; R1 is gated on gate 2) cannot be sequenced away, only decided. **The
scope fence was written before any code** and is in `PHASES.md` §P3: what is in, what is out, and
the five rules that keep it throwaway rather than a first draft. One exception is taken
deliberately and stated — the document register is built as production code, because
`Evidence.doc_revision_sha256` already assumes it exists and building a throwaway version would
mean two answers to "what document was this".

### P3 started — the spike is de-risked

- [x] **FR-1.3 Document Register built** (`errata_spec.registry`, 26 tests). Content-addressed,
  append-only, with a revision chain. Both halves of the acceptance criterion are tested as
  written, because both have an obvious wrong implementation: appending a revision per call
  satisfies "changed bytes create a new revision" and quietly fails "re-fetching identical bytes
  does not create a second record", leaving a history full of a document that never changed.
  Identity is the **hash, not the URL** — manufacturers mirror datasheets across regional sites,
  and a URL-keyed register would hold four copies of one document and four answers to "what did
  the reviewer see". There is **no deletion method**, asserted by a test rather than left to
  convention (§4.3 / FR-7.8). This closes a loop that had been open since the claim schema was
  written: `Evidence` has always *required* a 64-character revision hash and nothing produced one.

- [x] **Real MCB corpus started and the spike's biggest risk removed.** Two ABB S200 datasheets
  fetched from ABB's own library, hash-registered, payload gitignored (FR-9.5). Both are
  **born-digital with real embedded text layers** — 16 pages / 4,210 word boxes and 9 pages /
  2,359 word boxes. **OCR is not on the critical path**, which was the largest engineering
  unknown in P3. The FR-1.4 shape — canonical char-indexed layer plus a per-word bbox map — comes
  straight out of the PDF and is **byte-identical across runs**, which is what FR-1.4 actually
  demands. Demonstrated end to end on a real value: the S200's rated short-circuit capacity
  `10 kA` grounds to page 2, char span 1822–1824, bbox (305.9, 325.5, 314.6, 334.4).

  That is the exact shape gate 2 measures, produced from a real manufacturer document.

### P3 COMPLETE — gate 2 is MEASURED, and the answer is not the one we wanted

**`errata-r0 operating-point --corpus var/spike/corpus.yaml` → exit 2, ASYMMETRY NOT CONFIRMED.**

The §0.3 assumption — that auditing has a materially better precision/coverage operating point
than extraction at equal grounding quality — has never been measured in this project.
`phase5-red-team.md` names it as one of the two things that decide the whole thesis. It is
measured now.

| At full coverage (the comparison FR-0.3 specifies) | Errata | ExtractBench best |
|---|---|---|
| **word-level grounding F1** | **46.34%** (conservative 43.72%) | **46.4%** |
| value F1 | 67.15% | 95.6% |
| page-level grounding F1 | 67.15% | 84.9% |

**A dead heat on grounding, behind on value. Conservative margin −2.68pp.** Per §13 that is a
stop-or-narrow signal and per ground rule 4 it is reported as found.

**But the selective result is genuinely strong, and it is §0.3's mechanism 1 intact:** risk is
**0.00% out to 20% coverage** and climbs to 55.19% at full. The confidence signal really does
separate the fields the audit knows from the ones it does not. AURC **0.3370** over 1,427 points;
curve at `var/spike/risk-coverage.csv`.

The honest reading: **the asymmetry is unproven while the mechanism is real.** The extractor built
here is deliberately unsophisticated — a pattern matcher over flat text, built to be *independent*
of the gold rather than to be good — so this is a floor, not a ceiling. The next experiment is a
better extractor scored on the same corpus, which now exists.

**The corpus.** 1,426 records from two ABB S200 datasheets fetched from ABB's own library and
hash-registered. Gold values and word boxes read from the documents' ordering tables; predictions
from a **table-blind** flat-text extractor; disagreements decided by the **real
`errata_comparator`**, so gate 2 measures the component that ships. Independence is the whole
design: if gold and prediction shared a mechanism they would agree by construction and the
grounding number would be worthless. FR-3.4 is enforced **structurally** — `predict(layer, sku,
attribute)` has no parameter through which a catalog or gold value could reach it, and a test
asserts the signature.

**Per-attribute, and this is the finding worth keeping:**

| attribute | n | word F1 | value F1 |
|---|---|---|---|
| `order_code` | 292 | 100.00% | 100.00% |
| `rated_current` | 292 | 98.63% | 98.63% |
| `packing_unit` | 292 | 12.33% | 16.44% |
| `poles` | 275 | 3.51% | 10.09% |
| **`weight_kg`** | 275 | **5.45%** | **100.00%** |

`weight_kg` gets the answer right **every time** and cites the wrong instance of it, because
`0.125` appears in hundreds of rows and a table-blind extractor picks the nearest one. **That is
ExtractBench's central claim reproduced independently**, on different documents with a different
system: *the field can get the answer right and cannot show where it came from.*

### P3 deliverables

- **`spike/`** — throwaway by design, fenced in `PHASES.md` §P3 before any code was written, with
  the fence restated at the top of `spike/README.md`. Five rules; the operative one is that **R1
  may inherit its findings, not its code**. 14 tests, wired into the main suite (removing that
  entry is part of deleting the spike).
- **`errata_spec.registry`** — FR-1.3, production code, 26 tests. The one deliberate exception to
  the fence, because `Evidence.doc_revision_sha256` already required it and a throwaway version
  would mean two answers to "what document was this".
- **FR-1.4 / FR-1.5** — canonical char-indexed layer with per-word boxes, byte-identical across
  runs and version-stamped; table structure with column and row headers. The **merged-cell** case
  is resolved by box geometry rather than by carrying the last value forward — that alone is the
  difference between 275 gold pole records and 7, and geometry observes where carry-forward guesses.
- **`var/spike/risk-coverage.csv`** — the FR-0.3 curve, 1,427 points.

### FR-0.1 — a partial answer to independent labelling, without a human

The blocker on 1.2 was that FR-0.1 wants a second labeller who did not write the comparator, and
there is nobody. **Part of that gap can be closed with published standards instead of a person.**

Many suite labels turn on a question of *fact* with a published answer. "Is 0.5 in the same length
as 12.7 mm" is settled by **UCUM**, a unit standard maintained by a committee with no connection to
this project. `errata-r0 corroborate` adjudicates every unit-quantity pair in the suite against it.

**Result: 111 of 624 cases externally judgeable (17.8%), agreement 100%, zero disagreements** —
across **four** standards and **four** families. Coverage went 6.2% → 14.6% → 17.8% as sources
were added.

| source | family | judged | agreement |
|---|---|---|---|
| UCUM 2.2 | units | 38/106 | 100% |
| ISO 261:1998 Table 2 + **NBS H28 (1957)** | threads | **58**/144 | 100% |
| ETIM 10.0 value list | ingress | 14/60 | 100% |
| UCUM 2.2 | packaging | 1/83 | 100% |

**The paywall has a way around it, and it is worth remembering.** ASME B1.1 owns the Unified inch
threads and costs money, which is why the threads family was stuck at the metric cases ISO 261
covers. **NBS Handbook H28 (1957) is a US Government publication in the public domain**, covers the
same UNC/UNF/UNEF series, and is the document ASME B1.1 descends from. Adding it took threads from
38 judged cases to 58. Where a current standard is paywalled, the national standard it grew out of
frequently is not — that generalises well beyond this project.

Read **visually from rendered page images, not from the OCR text layer**: the OCR on a 1957 scan
renders 40 as `4b` and 56 as `6`, which is precisely the plausible-wrong number ground rule 1
exists to keep out. Same method as ISO 261 Table 2.

⚠️ **`#4 UNC` and `#6 UNF` are smudged past legibility and are deliberately NOT recorded.** Both
values are well known — and "well known" is exactly how an unread number gets written down as
though it had been read. The adjudicator declines them.

Eight H28 values were spot-checked against suite claims (`1 3/4 UNC`=5, `1 1/4 UNF`=12,
`2 UNC`=4.5, `1/2 UNEF`=28, `#12 UNEF`=32, `1 1/16 UNEF`=18, `1/2 UNF`=20, `3/8 UNF`=24) — **all
eight match**. It also independently confirms HANDOFF §7's anecdote about writing UNF's 12 into the
UNEF table: from 1 inch upward UNF runs 12 and UNEF runs 18, in adjacent columns of adjacent pages.

**The H28 adjudicator declines more than it rules on, on purpose.** `1/4-20 UNJC` vs `1/4-20 UNC`,
`-2A` vs `-2B`, and `LH` vs unmarked all have **identical threads per inch** and are genuinely
different threads. A TPI table asked to rule would answer EQUAL and corroborate a number it never
looked at. Tolerance classes, root-radius profiles, hand of thread and pipe threads are all
declined — which is why coverage is 17.8% and not a flattering figure.

ISO 261 is the strongest of the three — it is the standard *itself*, read from the publisher
preview during the P1 citation audit, and it settles the question the threads family exists to
test: a bare `M20` is not "M20 with some unstated pitch", it is M20x2.5 by reference to Table 2.

Deliberately **not built on Pint**: `errata_valuesem` resolves through Pint, so a Pint-based
corroborator would be asking one library the same question twice and reporting the echo as
validation. `errata_bench.ucum` parses UCUM's own essence file and does its own arithmetic in
`Fraction` — exact, so no disagreement can be a rounding artefact. A test pins the absence of a
Pint import.

**The first run reported 8 disagreements, and every one was the corroborator's fault, not the
suite's.** That is the most useful thing this exercise produced, and all three causes are now
regression-pinned:

| Reported "disagreement" | Actual cause |
|---|---|
| `230/400 V` vs `400/230 V` | read as the fraction 230/400 = 0.575 V. It is a **dual-voltage designation**. A proper-fraction test does not catch it — 230/400 is numerically proper — so the rule is now the inch series: integer over a power of two up to 64 |
| `0.5 in` vs `13 mm`, and 5 similar | called unequal on a 0.3 mm gap. **`13 mm` is written to the nearest millimetre** and asserts nothing finer. Now: a gap inside the written precision **declines**, because whether that is `equivalent` or `precision` is a taxonomy call this module cannot make; a gap beyond it is still ruled UNEQUAL |
| `80 degC` vs `144 degF` | applied the **point-reading** formula to what unt-h031 documents at length as a temperature **rise** (80 K rise = 144 °F rise, exactly). Nothing in either string says which, so cross-scale temperature now declines |

**Check the instrument before believing what it says about the thing being measured.** 28 tests.

**Each new adjudicator also misfired first, in the same shape.** The ISO 261 one reported
`M8x40` vs `M8x1.25` as UNEQUAL, reading the 40 as a pitch. It is a forty-millimetre bolt. ISO 261
defines `M<diameter>x<pitch>` and says **nothing** about a trailing length, so it genuinely has no
opinion — it now declines. Notably, reading the length *as a length* would have been wrong for a
different reason: it would reproduce the shipped parser's own rule and turn the adjudicator into a
mirror of the code it is meant to check.

**The `X` digit is always declined**, deliberately. In IEC 60529 `X` means a digit was *not tested*,
not that it scored zero, so `IP20` vs `IP2X` is a question about missing information — and the
suite labels cases of that shape four different ways on purpose. A value list has no opinion, and
answering anyway would manufacture agreement on exactly the cases where the judgment is hardest.

**What this does NOT do, and it matters:**

- **Coverage is 14.6%, reported per family rather than averaged.** `materials` (112 cases) and
  `terms` (119) have no external source at all, and the report says "no external standard applies"
  rather than showing a bare `0/112` that reads like a failure.
- **It judges facts, not taxonomy.** `granularity` vs `precision` vs `undetermined` is the harder
  half of labelling and no external dataset encodes it.
- **Silence is never scored as agreement** — pinned by a test, because that is the one change that
  would make the whole module dishonest.

### Materials: searched, and deliberately NOT built — a negative result worth recording

`materials` is the largest uncovered family (112 cases) and the web is full of AISI/UNS/EN
cross-reference tables. **None of them is usable as an authority.**

- **Wikidata** carries the grades but not the mappings: `SAE 304 stainless steel` (Q3600978) has
  **7 claims and no UNS, no EN number, no cross-reference**. Searching `1.4401` returns nothing.
- Everything else found is a **vendor marketing page or a PDF copying another vendor marketing
  page** — unattributed, uncited, agreeing with each other for no traceable reason.
- The primary sources — EN 10088-1, ASTM A959, SAE J1086 — are paywalled.

Building a corroborator on vendor tables would be **weak evidence dressed as corroboration**: the
same failure ground rule 1 exists to prevent, and the same reasoning that ruled out an inferred
distributor crosswalk for gate 3 (D-1 Route A). The report now names what each uncovered family
would cost to unlock — `EN 10088-1 (paywalled), 112 cases` — so the gap is actionable rather than
merely admitted.

### One documented decision independently corroborated, for free

ETIM's `ETIMARTCLASSSYNONYMMAP.csv` carries **37,058 committee-curated synonyms**. Coverage of our
terms family is too thin to build a harness on (`rccb`, `elcb`, `fuse` return nothing), but one
lookup is worth recording: **`RCBO` → class EC000905 "Earth leakage circuit breaker"**.

Finding 13 left `ELCB` deliberately unregistered on the grounds that it has three live readings,
one of them "ETIM's RCBO-shaped EC000905". That was asserted from a previous session's reading.
It is now **verified from ETIM's own curated synonym data**. `circuit breaker` maps to two
different classes in ETIM as well, which supports treating it as a generic rather than a term.

### New findings this session

- **F0.1 · Latent defect in `unitreg.py`, fixed.** `_dimensionality` was annotated `-> Any` with
  `Any` never imported. `from __future__ import annotations` deferred evaluation, so nothing
  raised and no test caught it — but `typing.get_type_hints()` on the module raised `NameError`
  and mypy could not check the function. **This is the §7 signature exactly**: careless about the
  thing nobody was expected to open.
- **F0.2 · The 489 test count reconciles.** Actual was 495; the difference is precisely the 6
  `test_demo.py` tests added after the count was last written. Nothing missing.
- **N5 · `PCE` is not a UN/CEFACT code.** See 1.6 above. Filed separately from N1 because N1 was
  "the right code, the wrong recommendation" and this is "no such code".

- **N6 · The parser carried the same false 6 mm pitch premise as the suite — FIXED.**
  `MAX_ISO_METRIC_PITCH_MM` was `6`, commented "the largest pitch anywhere in the ISO 261 metric
  series is 6 mm". A second number above the ceiling is read as a fastener length, so **`M125x8`
  silently lost its pitch** — a valid, standard designation reduced to M125 with no pitch, with a
  note claiming the 8 was a length.
  .
  One wrong belief written down in three places — two suite citations and this constant — and no
  copy could catch another, because they all agreed.
  .
  Fixed **per-diameter rather than by raising the constant**, on the standard's own authority.
  ISO 261:1998 clause 5.2: *"the 'coarse' pitches are the largest metric pitches used in current
  practice"*, so where a diameter has a coarse pitch, that pitch is the ceiling; above M68, where
  Table 2 lists no coarse pitch, it falls back to the table maximum of 8 mm. Simply raising the
  constant to 8 would have broken `M6x8` — an 8 mm long M6 screw, one of the commonest fasteners
  there is — by reading its length as a pitch M6 cannot have. Negative controls cover both
  directions and the fine-pitch traps still fire.

- **N9 · Gate 2's verdict compared partial coverage against a full-coverage baseline — FIXED.**
  The first real run reported `ASYMMETRY CONFIRMED`, "clearing the 46.43% ExtractBench baseline by
  52.24pp", and printed **"Proceed"**. It was judging on `best_row` — the most favourable of the
  20/40/60% coverage points — against a baseline that is a **full-coverage** figure. On this corpus
  the winning 20% slice is almost entirely order codes, the one attribute with a distinctive
  pattern, so the gate was reporting "when the audit answers only its easiest questions it does
  well" and calling that a win over a system answering everything.
  .
  Computed the way **FR-0.3 says in as many words** — "compared explicitly against ExtractBench's
  46.43 word-level / 95.6 value F1 **at full coverage**" — the same corpus scores 46.34% against
  46.4%: a dead heat, and NOT_CONFIRMED under the Wilson lower bound.
  .
  **The report already carried a caveat naming the mismatch.** It sat below a verdict that had
  already said "Proceed". That is the shape of R0 findings 1–4 exactly: the instrument knew and
  the verdict routed around it. Fixed — the verdict now reads full coverage, the like-for-like
  comparison is rendered **above** the verdict rather than in the notes below it, and 6 tests pin
  it including a negative control that a genuinely good audit still confirms.

- **N10 · Four ExtractBench figures carried a decimal the paper does not publish — CORRECTED.**
  `HANDOFF` §7 listed the grounding table as the repo's one carried-forward claim never
  re-checked, blaming the lack of a local PDF text library. There is one now. The paper was
  fetched, hash-registered and read.
  .
  **Table 3, page 9, prints one decimal place: 46.4, 44.1, 43.3, 84.9.** The repo carried
  **46.43, 44.14, 43.30, 84.92**. Every figure was right in substance and the precision was
  invented — `46.43` is not a number that paper contains. That is the §7 signature at the second
  decimal place: disciplined about the fact, careless about the digit nobody was expected to
  check. Corrected and pinned, with the locator now inside the citation string itself.
  .
  **Verified and unchanged:** 95.6% value F1 at 8.1¢/page (§3.2 p.7); 14 systems evaluated (§1
  p.3); 8 of them scoring 0.0 on grounding (Table 3: six named rows + "All other systems"); the
  IoU 0.5 threshold (Table 3 caption). No conclusion moves — 46.34% against 46.4% is the same
  dead heat it was against 46.43%.
  .
  **One unexpected confirmation.** Appendix B.4, p.23: *"A word-level box tightly encloses the
  cited word or a short span of adjacent words, rather than the surrounding table cell."* That
  independently validates the spike's choice to use word boxes rather than cell rectangles as gold
  evidence — a cell box is several times the area of the value inside it and would have made
  IoU ≥ 0.5 trivial to satisfy, inflating our own grounding score.

- **N7 · A dangling reference: the "audit report" cited by two suite cases does not exist.**
  `mat-h063` and `trm-h056` both say "see the audit report", and there is no such file in the
  repository. HANDOFF §6 counts six reported label findings; only these two are recoverable. The
  other four exist only as a count. Both dangling references have been removed from the cases.

- **N8 · `errata-r0 status` printed mojibake, and it is the first command anyone runs.** See F0.5.
  Worth restating as a finding rather than a chore: the repo's whole proposition is that a number
  you can trust comes with evidence you can read, and the command that presents it was corrupting
  its own section marks on the default Windows code page.

### 1.12 — grow the suite to 500 pairs: NOT DONE, and deliberately not attempted

FR-0.1 asks for 500 equivalence pairs and 500 genuine contradictions. The suite has **347 and
216** — short by **153 and 284**, so **437 new cases**.

**I did not add them, and padding toward the target would have been the wrong thing to do.**

The gate's denominator is flagged records, and its supporting rates are computed over no-defect
and defect pairs. Adding easy, passing cases grows those denominators and **improves every rate
without improving the comparator** — which is precisely the move this repo has already identified
as dishonest. `PROGRESS` says it in the session-2 headline: the rate fell "because the denominator
grew with *correct findings*, which is the only honest way for that number to improve". A hundred
more `M20` vs `M20x2.5` cases would move the number and mean nothing.

What the target actually needs is 437 **adversarial** cases, each with a source someone opened.
The binding constraint is not effort, it is access: the standards that would license new thread,
material and terms cases — ASME B1.1, BS 84, ISO 965-1, ISO 228-1, ISO 7-1, EN 10088 — are
paywalled, and this session's one real citation win came from ISO 261 happening to have a free
preview carrying its whole table. Writing 437 cases against standards nobody opened would
reproduce the §7 failure at four times the scale.

**Recommendation:** treat 1.12 as blocked on standards access, not on time, and buy the handful
that matter. ISO 965-1 and ASME B1.1 alone would unblock the threads and unified families, which
are already the largest. Until then the shortfall is stated in the gate's own caveats on every
run, which is the honest position.

---

## Gate 1 cleared — what it took

| Fix | Effect |
|---|---|
| Thread parser: coarse-pitch tables, length suffix, ISO 965 abbreviation, decimal/fraction nominal | −15 false positives |
| Gate accounting: `over_resolved` folded into the FP numerator, declined defects counted as misses, `accusatory` revived | exposed the real rate (6.22%) |
| Packaging hierarchies decline instead of accusing (`Box of 10` vs `Carton of 200`) | −2 SEV-1 |
| Material facets (mechanical class / coating / base grade are orthogonal) | −4 SEV-1 |
| `IP6/7` refuses instead of manufacturing a contradiction from a delimiter | −2 SEV-1 |
| New `null_gap` suite label — the vocabulary was missing a category §3.3 defines | −3 |

Every fix carries regression tests **with negative controls**: `Each` vs `Box of 10` still
contradicts, `class 8.8` vs `class 10.9` still contradicts, `316` = `A4` = `1.4401` untouched.

## Done this session (session 2 — 19 Aug 2026)

- **Built `errata-demo`** — the first thing in this repo a person can look at. Runs the real
  comparator over a demonstration catalog (14 attributes, 3 SKUs) and emits a ranked reviewer queue
  as text or HTML. Shows all three outcomes on purpose: 9 raised, 4 resolved silently, 1 declined.
  Grounded by construction — values are pulled by case id from the equivalence suite and the loader
  raises on an unknown id, so the demo cannot drift from the measured data. States its own scope:
  comparator only, grounding not built, gate 2 still NOT MEASURED. 6 tests.

- Fixed P1 findings **9, 10, 13, 15**. Gate 1 still PASS, now 1.30% with better coverage and fewer misses.
- Added 38 tests (451 → 489), every fix with negative controls per ground rule 7.
- **Downloaded the real ETIM 10.0 model** (ALL-SECTORS CSV, released 2024-12-05, ODC-By, no login):
  5,640 classes / 159 groups. Used as primary evidence for finding 13. Does **not** unblock gate 3 —
  it is the taxonomy, and gate 3 needs SKU counts per class, which ETIM does not publish.
- **Gate 3 data hunt: negative result, documented.** Per-class SKU counts are not publicly reachable.
  ETIM's downloads are taxonomy-only; 2BA (4M+ product records) gates statistics behind membership.
  The remaining routes both need a decision from you — see HANDOFF §9.
- Two new findings raised that were not on the queue (see §"New findings" below).

## Done in session 1

- Discovered R0 was already ~half built from a prior session; verified by inspection rather than trusting reports
- Built gate 2 from scratch; fixed the small-sample verdict bug; added regression test
- Fixed gate 3's headline-budget contradiction; added 61 tests
- Wired both gates into the CLI; updated the stale stub tests
- Ran 6 adversarial suite authors + 3 audit lenses as background agents
- **Found and fixed a silent order-of-magnitude unit bug:** `m2 = meter ** 2` made the alias prefixable, so `um2` parsed as micro×(m²) = 1e-6 m² instead of 1e-12 — wrong by 10⁶ on conductor cross-section, the most standard mm² field in electrical data. `km2` was wrong by 10³. Fixed by defining every prefixed spelling explicitly; regression test pins the *factors*, since the next missing spelling won't be `um2`
- Citation audit corrected 47 fabricated/over-confident source fields
- Established that the gate's own headline number is not yet trustworthy

## New findings raised this session

- **N1 · The Rec 20 mis-citation is systemic, not three typos.** All eight container codes are Rec 21.
  Fixed in `packaging.yaml` and `model.py`, but any *other* file asserting "Rec 20" for a container
  noun is also wrong — the suite `source:` fields still say it in several places.
- **N2 · HANDOFF §7 overstates one of its four fabrication examples.** It says IEC 60947-1 has "no
  such annex" as Annex A. The 2007+A1+A2 edition **does** have an Annex A, "Harmonisation of
  utilization categories for low-voltage switchgear and controlgear". The citation was imprecise and
  edition-dependent, not invented — AC-1/AC-3 are *defined* in IEC 60947-4-1. `terms.yaml` now says
  so and carries an `[UNVERIFIED]` marker, because no standard text was actually opened. This matters
  because §7 is the repo's evidence about agent reliability; one of its four exhibits is itself
  overstated. **Not corrected in HANDOFF §7 — left for you to rule on.**
- **N3 · `poles` vocabulary was sourced to IEC 60947-1**, which does not define the SP/DP/TP trade
  abbreviations (HANDOFF §7 flagged exactly this for 13 suite cases; the ontology had the same bug).
  Re-sourced to the ETIM features actually consulted, with the trade-convention status stated.
- **N4 · `drum` is an alias of the Roll frame.** Rec 21 has a separate DR code for drum, and a drum
  of liquid is not a roll of cable. Left as-is deliberately — no failing case, and softening or
  tightening behaviour without evidence is how the suite stops meaning anything. Logged, not acted on.

## Interrupted / not finished

- `threads_hard.yaml` written (114 cases) but **never reconciled or citation-audited** — agent hit session limit
- Determinism/gate-integrity audit **incomplete** — agent hit session limit mid-run after adding tests to `test_r0_gate.py` and `test_determinism_boundary.py`. Unverified: whether the determinism boundary can be defeated by a lazy import, and whether gates 2/3's synthetic pinning survives a hostile attempt

---

## Ground rules (from the spec — don't reverse silently)

1. **Never invent a number or a citation.** Cite a source actually opened, or mark `[UNVERIFIED — needs checking]`. Three of five suite agents violated this while self-reporting "0 UNVERIFIED".
2. **`valuesem` is deterministic.** No model call, no network call, any code path.
3. **A grammar either parses or refuses.** Refusal is routable; a silent guess is not.
4. **Leave real code failures failing.** A failing case is the finding. Never write a knowingly-wrong label to make the code look good.
5. **Gates 2/3 stay `NOT_MEASURED` on synthetic input**, unconditionally.
6. **Errata audits; it never enriches, and never writes to a customer PIM.**
