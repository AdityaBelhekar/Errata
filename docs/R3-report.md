# R3 report — the benchmark and the ecosystem

**Written:** 20 August 2026, at the end of the R3 (PHASES P6) build session.
**Reproduce everything here with:** `bash scripts/setup.sh`, then `errata-r3 reproduce`.

> **Read this first.** R3's exit criterion (PRD §4) is *"a **third party** reproduces our published
> scores from the repo."* The reproduction package is built, it runs, and on this machine it
> returns **REPRODUCED, 24 of 24 checks**. Nobody outside this repository has run it. A package
> that certifies itself has reproduced nothing, so the criterion is recorded as **half met** —
> exactly the shape R2 used for the *public* half of its own exit criterion, and for the same
> reason. `errata_ecosystem.reproduce.THIRD_PARTY_ATTESTATIONS` is an empty tuple, a test asserts
> that it is empty, and every receipt prints the sentence saying so.

---

## 1. What R3 is

R0 asked whether the product could work. R1 audited one SKU, R2 a catalog. R3 asks the question
that decides whether any of those numbers mean anything outside this repository, and ships one new
distribution, `errata-ecosystem`, with one new command:

```bash
errata-r3 reproduce --full
```

Nine requirements, seven met with numbers, two reported as `NOT MEASURED` because they are
measurements of people and no person has been measured.

| | Requirement | Status |
|---|---|---|
| FR-9.1 | ExtractBench's grounding metric, verbatim | ✅ **46.34%** word-level F1 @ IoU 0.5, n=1,426 |
| FR-9.2 | five unscored axes, each independently runnable | ✅ all five measured, all five caveated |
| FR-9.3 | reviewer-seconds per verified attribute | ⛔ **NOT MEASURED** — protocol ships, nobody timed |
| FR-9.4 | evidence-acceptance rate | ⛔ **NOT MEASURED** — same reason, stated alongside grounding F1 |
| FR-9.5 | gold set as URLs + hashes + annotations | ✅ 1,426 annotations, **1,426 re-derived from the documents** |
| FR-9.6 | frozen hard-tail split, CI fails if tuning touches it | ✅ 275 records, hashed, guard fires (with a negative control) |
| FR-9.7 | ETIM ↔ UNSPSC attribute bridge | ✅ published Apache-2.0, ODC-By attributed, 7 rows of which **3 are refusals** |
| FR-9.8 | ECLASS read from the customer's licence at runtime | ✅ adapter + scanner over the tree **and** over built distributions |
| FR-9.9 | leaderboard including our own losing scores | ✅ generated; we are **2nd of 8** on grounding and lose value F1 by **28.45pp** |

**Tests:** the suite is **1,199 green**, up from 1,078. `ruff check .` clean.

---

## 2. The headline numbers, and what each one is worth

Every number below is produced by `errata-r3 score`, pinned in `errata_ecosystem.reproduce.PUBLISHED`,
and re-checked by `errata-r3 reproduce`. The pins are exact string comparisons, not tolerances:
NFR-1 requires identical inputs to produce identical claims, so a tolerance would exist only to
absorb a real change quietly.

| Axis | Number | What it is worth |
|---|---|---|
| **grounding** (FR-9.1) | word-level F1 **46.34%**, conservative **43.72%**, page **67.15%**, value **67.15%** | The metric is ExtractBench's, computed by `errata_bench.operating_point.grounding_f1` — *called*, not re-implemented. Against the published **46.4%** the margin is **−0.06pp**: a dead heat on a different corpus |
| **class_assignment** (FR-9.2) | top-1 **47.06%**, top-5 **100.00%**, must-abstain **7/7** | 17 labelled queries against a four-class allow-list, single-labelled by the implementer. The abstentions are the interesting rows; a 47% top-1 on a four-way choice is not a good number and is printed as it is |
| **compound_values** (FR-9.2) | **14/20** correct, 95% CI [48.10%, 85.45%], 2 false positives, 4 unexpected abstentions | n = 20. Twenty cases decide nothing; the interval is printed next to the rate for that reason |
| **crosswalk** (FR-9.2 / 9.7) | 2 codes given attribute layers (27 and 29 ETIM features), **3/3** unmapped in-scope codes correctly yield nothing, 3 recorded refusals | Scores delivery on mapped codes and *silence* on unmapped ones. Scoring the bridge against itself would measure nothing |
| **supersession** (FR-9.2) | **5/5** — forked and cyclic histories raise rather than resolve | Constructed ledger fixtures. What they test is a property of the code, which is what a constructed fixture can honestly test |
| **abstention** (FR-9.2) | **AURC 0.3370**, risk at 20% coverage **0.00%**, selective accuracy 100.00% @20%, 53.77% @40%, 52.80% @60% | The confidence being ranked is a raw evidence-quality score, not a calibrated probability — FR-6.1's calibration set still does not exist |

**The corpus caveat travels with every one of these**, in the axis output, on the leaderboard and in
the HTML: ExtractBench's figures are over 370 documents, 4,869 pages, 8 business domains; ours are
over 1,426 fields from two low-voltage circuit-protection datasheets. *Same metric and threshold,
different population.* No row of the leaderboard should be read as one system beating another on
the other's data.

---

## 3. FR-9.5 — the gold set is URLs, hashes and annotations, and it is verified

The requirement is easy to satisfy meaninglessly: ship a file of numbers, call it an annotation
layer, never check that the numbers describe the document. So verification runs at three levels and
the report names the one it reached.

```
$ errata-r3 gold verify
gold set verification: GROUNDED
  annotations checked   1426
  documents verified    2
  records re-derived    1426
```

**GROUNDED** means: every annotation's boxes are word boxes that exist on that page of that
document, and the words inside them spell the value the annotation claims — **1,426 of 1,426**.
The re-derivation deliberately uses R1's production layout module, not the spike that wrote the
annotations. Verifying an extraction with its own extractor checks nothing, which is what finding
N16 was made of.

Two tampering tests are the proof that the check does work: moving one box by three points, and
changing one value, each drop the report to `FAILED` with the offending record named.

**What is committed:** `data/gold/manifest.json` (URLs, sha256, page counts, licence text),
`data/gold/annotations/*.jsonl` (1,426 records), `data/gold/splits/hard-tail.json`.
**What is not:** any document. A repository-wide test walks every file that is not gitignored and
fails on a `.pdf` suffix or a `%PDF-` magic number.

**The gold set's own gaps, printed rather than inferred:**

- It is **document-derived, not expert-labelled** — the value is the cell text and the evidence is
  its word boxes, read mechanically from table structure. Same weakness gate 1 has: the author of
  the labeller wrote the thing being measured.
- **One of the two registered documents contributes zero annotations.** The S200M UC datasheet's
  ordering tables are **transposed** — each product is a column, and the header row collapses into
  a single cell — so a builder that reads "a value in a cell under a named column, in a row
  identified by its type designation" finds nothing to read. The document is fetched and hashed;
  it contributes nothing, and `gold_set_gaps` in the split file says why.

---

## 4. FR-9.6 — the frozen split, and the honest half

```
frozen split 'hard-tail' -- 275 of 1426 records (19.28%), frozen 2026-08-20
  criterion: gold record sourced from a merged cell
  sha256:    99216acbd108dc72cecce4c9b470fc4356fb0d9980aeb58c2b9f1dd1cf893cd8
  NOT REPRESENTED in this corpus, and named rather than implied:
      degraded scans, fold-outs, cross-page tables, superseded revisions
```

**What is in it:** the 275 records whose value comes from a merged source cell — the ordering
tables state a pole count once for a block of twenty rows, so the value is not printed on the row
it belongs to. Resolving those needs cell geometry; an extractor reading the row as printed gets
them wrong or abstains.

**What is not in it, and this is the half that matters.** The PRD names four hard-tail categories.
**None of the four occurs in this corpus**, which is two born-digital PDFs from one manufacturer,
and freezing an empty split per category would be theatre. Each is listed as unrepresented with a
measured reason — the fold-out entry, for instance, records that every page of the first document
is 595×842 pt and every page of the second is 612×792 pt, because "there are no fold-outs" is a
claim and page sizes are how you check it. The machinery takes a real hard-tail document the day
one arrives: a split is a list of record ids and a hash, with no code path per category.

**The guard.** Anything that tunes declares the records it read; `assert_untouched` fails the build
if a declaration intersects the split, and `record_tuning_run` checks *before* it writes so that a
violating run cannot leave a record saying it happened and continue. Both the firing and the
non-firing case are tested.

**The obvious objection is right and is written into the module.** A declaration is only as honest
as the code that writes it; nothing here stops someone reading the hard tail in a notebook. What
the mechanism buys is that the repository's own tuning paths cannot touch the split without a
visible edit to a file whose whole subject is honesty. Same bargain as an append-only ledger, worth
the same amount.

---

## 5. FR-9.7 — the bridge, including the rows that refuse

UNSPSC gives a product an eight-digit code across four levels and **no attribute layer** — verified
by inspection of all 71,502 commodity rows, not taken from the PRD. ETIM has the attribute layer.
The bridge is the join, published Apache-2.0 with ODC-By attribution.

```
39121603 'Miniature circuit breakers'   --skos:exactMatch-->  EC000042 'Miniature circuit breaker (MCB)'
39121603 'Miniature circuit breakers'   --skos:narrowMatch--> EC000271 'MCB plug model'
39121601 'Circuit breakers'             --skos:narrowMatch--> EC000042 'Miniature circuit breaker (MCB)'
39121616 'Molded case circuit breakers' --skos:closeMatch-->  EC001047 'Selective main line circuit breaker'
39121614 'Earth leakage circuit breakers' --declined-->       (no ETIM class)
(no UNSPSC code)                        --no_match-->         EC000003 'RCCB'
(no UNSPSC code)                        --no_match-->         EC001047 'Selective main line circuit breaker'
```

Three of seven rows are refusals, and they carry most of the file's value:

- **39121614 is declined.** ETIM's earth-leakage class is EC000905, and this repository has ruled on
  that term twice already — `errata_valuesem` leaves "ELCB" unregistered because three live
  readings exist and none can be picked from the surface form, and `r1-classes.yaml` excludes
  EC000905 for the same reason. Mapping it here would re-introduce, inside a *published artifact*,
  an ambiguity two other components refuse to resolve, somewhere a downstream consumer could not
  see the refusal.
- **EC000003 (RCCB) has no UNSPSC code at all.** No commodity title in the codeset contains
  "residual current"; the nearest is the declined 39121614. An entire device category with its own
  IEC standard and 31 ETIM features has no code that names it. That is a finding about UNSPSC,
  recorded so the next person does not repeat the search.
- **39121616 ↔ EC001047 is a `closeMatch`, and delivers no attributes.** The two descriptors turn on
  different properties — selectivity behaviour versus enclosure construction — so the loader
  refuses to carry a schema across it. A loader that did would be contradicting the file it read.

**Three refusals in the machinery, each tested with the corrected control next to it:** a code that
does not exist does not load; a code whose *title* has changed does not load (UNSPSC is revised
roughly annually and our snapshot is dated); a mapping without a rationale does not load.

**The attribute layer is not in the bridge file.** Not one feature id appears in the YAML — a test
asserts that — and the layer is derived from the ETIM release at load time, so it cannot drift.
`39121603` currently resolves to **29 ETIM features** with units and closed value lists.

**What the bridge is not:** measured. Every mapping is a single judgement by its author, and
`errata-r3 bridge status` prints that sentence next to every count. Validation proves the codes and
titles exist; it does not prove the judgement is right, and no second domain judge has read them.

---

## 6. FR-9.8 — ECLASS stays outside, and the check is on the artifact

The adapter loads the customer's own licensed export at runtime, from a path or from
`ERRATA_ECLASS_DICTIONARY`, holds it in memory, and **refuses a path inside this repository** —
because loading from there is how content gets committed by accident. It refuses a file with no
IRDI column rather than reporting an empty dictionary: "wrong export" and "empty dictionary" are
different problems and only one is the customer's.

The scanner matches the **IRDI form** (`0173-1#NN-XXXNNN#NNN`), not the word "ECLASS". ADR-003 and
four phase documents discuss ECLASS at length; a scanner that fired on the word would either be
switched off or would push the discussion out of the documents. What it flags is the thing the
licence covers.

It runs over the working tree (238 files, **0 findings**) and over **built distributions**, because
"the repository is clean" and "the wheel is clean" are different claims and FR-9.8 makes the second
one. Package-data globs are exactly how a file nobody meant to ship gets shipped.

The tests that prove this scanner works needed content that trips it — while the scanner runs over
the test file. The fixtures are therefore **assembled at runtime from fragments**, so no
ECLASS-shaped literal exists anywhere in the repository and the invariant keeps its strong form:
not "no ECLASS content except where we allowed it", which is the loophole every such scanner
eventually acquires, but none at all.

---

## 7. FR-9.9 — the leaderboard prints our losses

```
system                        origin          word F1     page F1    value F1
LE Agentic Plus               published         46.40       84.90       95.60
Errata (R3 harness)           measured          46.34       67.15       67.15
LE Agentic                    published         44.10       66.10  not scored
Reducto Deep                  published         43.30       71.70  not scored
LE Cost-Eff.                  published         40.40  not scored  not scored
Extend Max                    published         25.10  not scored  not scored
Datalab A+B                   published          2.00  not scored  not scored
all other evaluated systems   published          0.00  not scored  not scored

WHERE WE LOSE
  word-level grounding F1 @ IoU 0.5: LE Agentic Plus 46.40 beats Errata 46.34 by 0.06pp
  page-level grounding F1:           LE Agentic Plus 84.90 beats Errata 67.15 by 17.75pp
  value F1:                          LE Agentic Plus 95.60 beats Errata 67.15 by 28.45pp
  evidence-acceptance rate (FR-9.4) and reviewer-seconds (FR-9.3): NOT MEASURED
  rank on word-level grounding F1: 2 of 8
```

Two things the table is careful not to do:

- **It does not print 0.0 for a metric a system never reported.** ExtractBench *does* record 0.0
  word-level grounding for the eight systems that return no boxes — a measured zero, printed as
  one. But nobody else reports compound-value normalization or calibrated abstention at all, and
  rendering that as 0.0 would manufacture a win on five axes at once. Those cells read `not scored`.
- **It does not hide the big loss behind the near-tie.** The 0.06pp gap on grounding is the
  flattering number; 28.45pp on value F1 is the real one, and the tests assert that both appear.

There is no curation function in `leaderboard.py`. Rows are built from axis results; `losses()`
re-reads the same rows. Dropping a losing row would mean removing a metric from the harness.

---

## 8. FR-9.3 / FR-9.4 — the two numbers that do not exist

```
FR-9.3 reviewer-seconds per verified attribute -- NOT MEASURED
FR-9.4 evidence-acceptance rate                -- NOT MEASURED
  no reviewer sessions exist. These two numbers are measurements of people, and nobody has
  been timed.
```

The protocol ships (`errata-r3 reviewer --protocol`, and `docs/reviewer-protocol.md`): who counts
as a domain reviewer, what they see, the one extra question asked after every decision — *does the
highlighted evidence support the proposed value?* — the clock rules, the gold requirement, the
30-decision floor, and what invalidates a session.

**Three unconditional refusals, each pinned by a test, each with a control showing the arithmetic
does work when the conditions are met:**

1. **Synthetic sessions never produce a number**, at any n. Ground rule 5, carried out of R0's
   gates and into R3's benchmark.
2. **Untimed decisions never produce seconds.**
3. **Decisions by anyone but a domain reviewer produce neither rate.** This repository's own ledger
   contains adjudications — made by the person building the console. `errata-r3 reviewer --ledger`
   reads them, and still reports `NOT MEASURED`, naming the role it found.

That third refusal is the one that costs us a number we could have printed today. Printing it would
have been the author grading the author's own evidence boxes.

---

## 9. Findings raised during P6

- **N15 · Two vocabularies for one attribute. FIXED, with no id churn, measured rather than
  assumed.** R2 raised it and deferred it because "fixing it properly changes every existing
  redline id and invalidates recorded adjudications". That turned out not to be true of the fix
  that was actually needed. `AttributeSpec` now carries `uri`, `build_redline` writes
  `attribute_uri`, and R2's structural findings write the same. **Redline ids did not move** —
  both id functions already hashed the URI — and the test that proves it re-derives the id
  `025b25e5-6233-561d-a509-482ecfb6aa65` recorded in the R1 ledger on 20 August, so a decision
  recorded before the fix still names the finding the current build produces. Error-signature
  fingerprints *do* move, because a fingerprint contains the attribute's name; nothing adjudicates
  a fingerprint, so that costs a recomputation. Ledger rows written before the fix carry the bare
  key, and `canonical_uri` resolves those too.
- **N19 · Every `--json` payload in the repository had English on top of it. FIXED.** PyMuPDF
  advertises its layout add-on with a bare `print` to **stdout** on every `find_tables()` call.
  Both call sites wrapped it in `warnings.catch_warnings()` with `simplefilter("ignore")`, which
  never silenced it — it is not a warning. So `errata-audit catalog --json | jq` failed for anyone
  who tried it, and no test saw it because the tests call the API rather than the process. The
  message is now redirected to stderr rather than discarded: a library telling us something is not
  noise, it is on the wrong stream. Regression test runs the actual executable and parses stdout.
- **N20 · The UNSPSC codeset is cp1252, and utf-8 raises 5,779 bytes in.** 93 non-ASCII bytes: an
  acute e in a phalaenopsis cultivar, a non-breaking space inside "Optical transmitter", an acute e
  in "cliche". `errors="replace"` would have corrupted three commodity titles — and titles are what
  the bridge validates against, so a corrupted one becomes a mapping that stops loading for no
  visible reason. Recorded in the manifest's `loader_notes` next to ETIM's utf-16-le trap.
- **N21 · One of the two gold documents is unreadable by the gold builder, and it is not a bug.**
  The S200M UC datasheet lays its ordering tables out transposed. Recorded as a gold-set gap rather
  than quietly leaving the corpus at one document.

---

## 10. What R3 deliberately does NOT claim

| The exit criterion | **Half met.** `errata-r3 reproduce` returns REPRODUCED on 24 of 24 checks here; no third party has run it, `THIRD_PARTY_ATTESTATIONS` is empty, and a test asserts it stays empty |
| FR-9.3 / FR-9.4 | **NOT MEASURED.** No reviewer has been timed and no domain reviewer has judged an evidence box |
| The gold set | Document-derived, not expert-labelled. Two documents, one manufacturer, one product family. 1,426 fields is a decent n for a metric and a thin base for a claim about the world |
| The hard tail | Contains merged-source cells. Contains **none** of the four categories the PRD names, because the corpus contains none of them |
| The bridge | Seven single-judged mappings over one UNSPSC class. Validated, not verified |
| class_assignment, compound_values | 17 and 20 cases. Regression signals with intervals, not published rates |
| supersession | Constructed fixtures — a property of the code, not a measurement of any customer's history |
| Cost per axis (NFR-5) | Not measured in R3. R2 measured cost by tier; nothing in the benchmark meters itself |

---

## 11. How a third party reproduces this

```bash
git clone <repo> && cd errata
bash scripts/setup.sh                     # venv, pinned deps, seven distributions, full suite
bash scripts/fetch_reference_data.sh      # ETIM, UNSPSC, UCUM, Rec 20/21, ISO 261, H28, the ABB PDFs
.venv/Scripts/errata-r3 gold verify       # expect: GROUNDED, 1426 / 1426
.venv/Scripts/errata-r3 reproduce         # expect: REPRODUCED, 24 of 24
.venv/Scripts/errata-r3 leaderboard --html var/r3/leaderboard.html
```

The receipt prints the sha256 of every input the numbers depend on — corpus, annotations, split,
bridge, UNSPSC codeset, reference manifest — plus the Python version, the platform and the version
of all seven distributions. **If your receipt says DIVERGED, the failing checks are named with the
expected and actual value, and we would like to see it.** A divergence is the most useful thing a
third party can send back, and it is the only way the second half of the exit criterion closes.

---

## 12. Where the numbers live in the code

| Number | Produced by | Pinned by |
|---|---|---|
| word-level grounding F1 | `errata_bench.operating_point.grounding_f1` (called, not re-implemented) | `reproduce.PUBLISHED["grounding"]` |
| top-1 / top-5 / must-abstain | `errata_audit.resolve_class` over `demo/class-labels.yaml` | `reproduce.PUBLISHED["class_assignment"]` |
| compound-value accuracy | `errata_bench.equivalence.run_suite`, filtered to compound parsed kinds | `reproduce.PUBLISHED["compound_values"]` |
| crosswalk delivery and silence | `errata_ecosystem.bridge` over ETIM 10.0 and the UNSPSC codeset | `reproduce.PUBLISHED["crosswalk"]` |
| supersession outcomes | `errata_scale.chains.claim_chains` over ledger fixtures | `reproduce.PUBLISHED["supersession"]` |
| AURC and selective accuracy | `errata_bench.operating_point` risk–coverage machinery | `reproduce.PUBLISHED["abstention"]` |
| gold set shape and verification level | `errata_ecosystem.goldset.verify` | `reproduce.PUBLISHED_GOLD` |
| hard-tail split size and hash | `errata_ecosystem.splits.load_split` | `reproduce.PUBLISHED_GOLD` + `data/gold/manifest.json` |
