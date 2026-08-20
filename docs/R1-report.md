# R1 report — the single-SKU audit, end to end

**Run:** 20 August 2026. **Package:** `errata-audit` 0.1.0 (`audit/`).
**Reproduce everything below with the commands in §7.**

---

## 1. What R1 is, and what it is not

R0 asked whether the idea survives contact with data. R1 asks whether it survives contact with a
reviewer. The pipeline is end to end and real:

```
catalog record ─► document register ─► text layer + tables ─► ETIM class (3 stages)
                                                                     │
                          blind re-derivation ◄─────────────────────┘
                                   │
                     comparator ─► redline + evidence boxes ─► console ─► ledger
```

**What is genuinely built:** ingest, the content-addressed store, word-level layout with a cache
and a version stamp, table structure with cell/row-header/column-header roles, ETIM 10.0 class
resolution in three inspectable stages, span-required re-derivation that is blind to the catalog,
the comparator, the Declined bucket, the append-only ledger, adjudication with the safety-class
two-signature rule, the calibration machinery, and **the reviewer console in two forms** — a
self-contained HTML report, and a local web application (`errata-audit serve`) where a reviewer
actually decides: ranked queue, evidence boxed on the page, Accept / Keep catalog / Escalate.

**What is NOT built, stated before any number below is read:**

| Requirement | Status |
|---|---|
| FR-2.2 embedding retrieval + cross-encoder | **Interfaces only.** Retrieval is lexical; every resolution reports `retrieval_method: lexical` |
| FR-2.2 LLM selector | **Interface only**, capped at 5 candidates by a function that raises |
| FR-6.1 calibrated probability | **No calibration set exists.** Confidences are raw evidence-quality scores and are printed as such |
| FR-1.4 OCR | Born-digital documents only. A scan is declined, never guessed |

---

## 2. The headline numbers

### 2.1 Detection, on the demonstration catalog (278 records, 1 document)

```
records            278        findings             67
audited            277        checked, supported 1033
coverage        79.42%        declined            285
```

| Injected kind | n | Audit raised | Audit silent |
|---|---:|---:|---:|
| **defect** (transposed current, dropped decimal, packaging frame) | 56 | **56** | 0 |
| **gap** (catalog blank, document states a value) | 11 | **11** | 0 |
| **correct** | 168 | **0** | 168 |
| **equivalent trap** (grams vs kg, `1P` vs `1`, `Each` vs a pack of 1) | 40 | **0** | 40 |
| declined by design (missing SKU, unusable tables, absent document) | 3 | 0 | 3 |

**Zero false positives and zero misses on this population**, including all 40 equivalence traps.
FR-5.3 — "semantic equivalence must not flag" — is the single highest-consequence requirement in
the PRD, and it is the row above with 40 in it.

> ⚠️ **The catalog is constructed and the datasheet is real.** No public ABB catalog feed is
> available, so the thing under audit is generated from the document with defects injected on
> purpose (`audit/tools/build_demo_catalog.py`, mutation by `sha256(sku)`, no RNG seed). **These
> detection rates describe a population we created.** The grounding half — the values, the spans,
> the boxes — is read from ABB's own hash-registered document and is empirical. The caveat is
> printed by the CLI and rendered on the face of every HTML report, not filed here.

### 2.2 The Declined bucket — where the coverage went

| Reason | n | What it means |
|---|---:|---|
| `value_outside_known_grammar` | 276 | The order code. `errata_valuesem` has no grammar for it and refuses; the attribute stays in the map so the refusal is **visible** (FR-6.2: no silent skips) rather than improving every rate by disappearing |
| `no_source_document` | 5 | One SKU's type designation is not in the datasheet, and one record names a datasheet nobody supplied |
| `layout_unreadable` | 2 | The S200 M UC datasheet's ordering tables do not resolve into columns; running text offers competing values and the audit declines rather than picking one — see finding N12 |
| `no_span_available` | 2 | The value could not be grounded to a span, so it never became a claim |

Coverage of 79.4% is dominated by one attribute the value layer cannot parse. Read the detection
numbers next to it, always.

### 2.3 Class resolution (FR-2.2), 17 labelled cases + 7 must-abstain

```
top-1      8/17   47.1%      (a committed, correct choice)
top-5     17/17  100.0%      (gold class in the shortlist the selector was handed)
abstained  9/17   52.9%
must abstain 7/7  held       (ambiguous or out-of-scope queries)
wrong        0              (it never chose a class that was not the label)
```

**This is the clearest measurement in R1 and it says something precise:** retrieval and reranking
put the right class in the top five **every time**; the selector commits to it half the time and is
never wrong. The missing stage is exactly the one FR-2.2 specifies and this package does not ship —
an LLM choosing among five candidates with the class definitions in context. The gap between 47%
and 100% is that stage's job, and it is now measurable rather than assumed.

The two rates measure different things on purpose: top-1 scores the *selector* and counts an
abstention as a miss; top-5 scores the *retriever and reranker* and does not. Folding abstentions
into top-5 would make a selection decision look like a retrieval failure.

> Labelled by the implementer, single-labelled, against a four-class allow-list. FR-0.1 identifies
> that conflict of interest for the equivalence suite and it applies here unchanged. A four-way
> choice is an easy problem; the interesting rows are the seven abstentions, not the rate.

### 2.4 The console, and the loop it closes

`errata-audit serve` is the console as a running application rather than a file, and it exists
because three requirements are otherwise untestable claims:

| | What only becomes real when a human can act |
|---|---|
| **FR-7.6** | Decision, actor, timestamp, note — persisted immutably. Verified end to end: a decision made in the browser produced four ledger events (`redline`, `score`, `adjudication`, `claim`) and nothing was overwritten |
| **FR-9.3** | Reviewer-seconds per verified attribute, the metric a buyer pays for and nobody publishes. The page times itself; the first real decision recorded **25.7 seconds** |
| **FR-9.4** | Evidence-acceptance — did the box support the claim? Asked on the form, stored with the decision |
| **FR-6.1** | The dashboard states what is still missing before a probability can honestly be printed: after one accepted redline it read *"a fit needs decisions of both kinds and there are no kept-catalog ones yet"* |

The safety-class two-signature rule (FR-8.9) is enforced **on the server**, not by the form's
`required` attribute — a request that ignores the form is still refused, and a test posts one to
prove it. The console binds to loopback and refuses a non-loopback bind without an explicit flag:
it renders a customer's catalog beside a manufacturer's document and has no authentication.

### 2.5 Grounding, on a real page

Verified visually and by test on ABB S200 page 8: the evidence box lands on the word `16` in the
`S201M-B16UC` row of the ordering table, and the header box lands on `Rated current In A`. The
value box is **less than half the area of the containing cell** (`test_the_box_lands_on_the_value_not_on_the_cell`),
which is the property that makes an IoU ≥ 0.5 score mean something — ExtractBench's Appendix B.4
p.23 says a word-level box encloses the cited word rather than the surrounding cell.

---

## 3. The four findings R1 produced

**N11 · `errata_valuesem` cited an ETIM feature that does not exist. FIXED.**
`terms.yaml` declared `EF000094` as the ETIM feature for the tripping characteristic. **There is no
EF000094 in ETIM 10.0.** The feature the MCB class actually declares is `EF000889` "Release
characteristic", read out of `ETIMFEATURE.csv` and `ETIMARTCLASSFEATUREMAP.csv`. This is HANDOFF §7's
signature at a new location — disciplined about the fact, careless about the locator nobody was
expected to open — and the remedy is not vigilance but a test: `audit/tests/test_etim.py`
cross-checks every ETIM id cited anywhere in the repository against the loaded release.

**N12 · The text-window fallback manufactured a confident, evidenced accusation. FIXED.**
On the S200 M UC datasheet, whose ordering tables do not resolve into columns, the running text
reads `0.2 A 0.3 A 0.5 A …`. The fallback took the nearest matching token and returned **0.3 for a
0.2 A device** — a SEV-1 contradiction against a value the document never stated for that product.
Nearest-in-reading-order is a tie-break, not evidence. The fallback now declines with
`layout_unreadable` when the window offers more than one distinct candidate value.

**N13 · The class-resolution evaluation was scoring its own tie-break. FIXED.**
The first run of `errata-audit classes` reported top-1 **88.2%** and resolved five of seven
must-abstain cases. The cause: the evaluation passed the *whole* attribute map as schema-fit
evidence, so every ambiguous query — including the bare word "breaker" — got the same tie-break and
resolved to EC000042. Schema fit is evidence about a **record** (which columns a feed carries), and
these cases are bare descriptions with no record behind them. Removed: the honest numbers are §2.3's
47.1% / 100% with seven of seven abstentions held.

**N14 · Redline ids were random, so a decision could not be attached to a finding twice. FIXED.**
The CLI printed an `adjudicate --redline-id …` command that stopped working the moment the audit was
re-run, because the same finding came back with a new UUID. That is a usability bug on the surface
and a correctness one underneath: a ledger accumulating one row per run per finding cannot answer
"has this been decided?", and the web console could not have worked at all. A redline's id is now
**derived from its content** — `uuid5(namespace, document sha256 | sku | attribute | catalog value |
proposed value)` — which is the same content-addressing rule the document register already uses.
Change any of those five things and it is a different finding that deserves its own decision.

All four have regression tests. N12's carries a negative control (a genuine single-candidate
fallback still resolves); N14's asserts two runs produce identical ids and that a decision survives
a cache clear.

---

## 4. Design decisions worth challenging

**Schema fit as a tie-break.** When two classes cannot be separated lexically — "miniature circuit
breaker" is the whole of EC000042's name and most of EC000271's — the resolver may break the tie on
which class can *express the attributes the record carries*. EC000271 declares no pole feature, so a
feed sending a pole count is describing an EC000042. This uses the record's attribute **keys** and
never its **values**: a resolver that read the values would choose the schema that makes those
values look correct. A record carrying neither is declined.

**The unit comes from the column header, and the header is stored as evidence.** A cell reading `16`
becomes `16 A` only because the column is headed *Rated current In A*, and that header cell travels
with the claim as a second `Evidence` record so the console can box it (FR-7.3). Composing silently
would produce a value string that appears nowhere in the document.

**An attribute with no grammar stays in the map.** The order code produces 276 of the 285 declines.
Removing it would lift coverage from 79.4% to essentially 100% and would be the cheapest possible
dishonesty: FR-6.2 says there are no silent skips, and a system that drops what it cannot parse
reports a coverage it has not earned.

**No calibration set ships.** Calibration needs labels of both kinds, and on this population the
audit has no false positives at all — a set with one outcome cannot be fitted, and `fit_platt`
refuses it explicitly. `errata-audit calibrate` fits from reviewer decisions the day there are
fifty; until then every confidence is printed as a raw score with "NOT CALIBRATED" beside it, and
an uncalibrated finding is not promoted above a calibrated one in the queue.

---

## 5. Requirement coverage

| Requirement | Where | Status |
|---|---|---|
| FR-1.1 catalog ingest, verbatim | `ingest.py` | ✅ tested byte-for-byte |
| FR-1.2 document by URL or path | `documents.py` | ✅ network is opt-in and refuses otherwise |
| FR-1.3 document register | `errata_spec.registry` + `BlobStore` | ✅ re-fetch is not a new revision; changed bytes link |
| FR-1.4 layout, char-indexed, per-word boxes | `layout.py` | ✅ deterministic, cached on content, version-stamped. **No OCR** |
| FR-1.5 table structure with header roles | `tables.py` | ✅ merged cells resolved by geometry |
| FR-1.6 multi-column without bleed | `layout.py` column bands | ✅ a gap a text block spans is not a gutter |
| FR-2.1 ETIM loader, release-parameterised | `etim.py` | ✅ UTF-16-LE / `;` traps pinned by test; ODC-By attribution carried into reports |
| FR-2.2 retrieve → rerank → select | `classify.py` | 🟡 three stages real; embedding + cross-encoder + LLM are interfaces |
| FR-2.3 abstain when not separable | `classify.py` | ✅ `class_unresolved`, never a default class |
| FR-2.4 R1 class allow-list | `config/r1-classes.yaml` | ✅ configuration with a stated reason per entry |
| FR-3.1 constrained to the class schema | `derive.py` | ✅ closed value lists rejected before a claim exists |
| FR-3.2 span-required | `errata_spec.emit_extracted_claim` | ✅ enforced at the constructor |
| FR-3.3 abstention is a different type | `derive.py` | ✅ no `value_raw` to misread |
| FR-3.4 blind re-derivation | `derive.py` | ✅ **pinned by signature inspection** |
| FR-4.x value semantics | `errata_valuesem` | ✅ from R0 |
| FR-5.x comparator | `errata_comparator` | ✅ from R0; 40 equivalence traps pass |
| FR-6.1 calibrated probability | `confidence.py` | 🟡 machinery + reliability diagram built; **no set exists** |
| FR-6.2 declined bucket, one reason each | `audit.py` | ✅ no silent skips; every reason counted |
| FR-6.3 risk–coverage and AURC | `confidence.py` | 🟡 built; empty until adjudications exist |
| FR-7.1 three panes, adjudicate without leaving the screen | `console.py`, `web.py` | ✅ static report **and** a local web console with working decision buttons |
| FR-7.2 word-level box | `console.py` | ✅ verified on ABB page 8 |
| FR-7.3 header highlighting | `console.py` | ✅ second colour, from stored evidence |
| FR-7.4 counter-evidence, never empty | `counterevidence.py` | ✅ says so in words when nothing supports the catalog |
| FR-7.5 sentences, never a bare % | `errata_spec.Redline.queue_sentence` | ✅ tested |
| FR-7.6 adjudication, immutable | `ledger.py`, `web.py` | ✅ append-only; safety class needs two signatures, enforced server-side |
| FR-7.7 OCR-layer toggle, revision history | `console.py` | ✅ shows the canonical text layer |
| FR-7.8 reconstructible from stored state | `console.py` | ✅ boxes drawn from stored spans, not re-extracted |
| FR-7.9 CLI | `cli.py` | ✅ exit code is the decision; `serve` refuses a non-loopback bind without a flag |
| FR-9.3 reviewer-seconds | `web.py`, `ledger.py` | ✅ collected — first measured decision 25.7s |
| FR-9.4 evidence acceptance | `web.py`, `ledger.py` | ✅ asked on the form, stored with the decision |
| FR-8.9 two named adjudicators | `errata_spec.Redline` | ✅ enforced at construction, including through `model_copy` |

---

## 6. What R1 does not answer

- **The §0.3 asymmetry is still unproven.** R0 gate 2 measured grounding at parity with published
  extraction (46.34% vs 46.4%). R1 does not re-open that; a better extractor scored on the same
  corpus is the next experiment.
- **Gate 3 is still `NOT_MEASURED`** (decision D-1). R1 was entered on an explicit waiver recorded
  in `PHASES.md` §10, not on a satisfied entry criterion.
- **Everything measured here was labelled by the person who wrote the code.** That is true of the
  class labels and of the demo catalog's ground truth. It is the same conflict of interest FR-0.1
  names, and it has the same remedy.
- **Reviewer-seconds per verified attribute (FR-9.3)** is now collected for real, and *n* = 1. One
  timing is an anecdote; the number becomes a claim at a few hundred, which needs reviewers rather
  than code.
- **The risk–coverage curve for a run** (FR-6.3) is computed from decisions and is therefore nearly
  empty. That is the honest shape: the alternative is the audit grading its own homework.

---

## 7. Reproducing this report

```bash
./.venv/Scripts/errata-audit.exe status
```

```bash
./.venv/Scripts/errata-audit.exe serve --open
```

```bash
./.venv/Scripts/errata-audit.exe sku --random --html var/audit/console.html
```

```bash
./.venv/Scripts/errata-audit.exe catalog --json
```

```bash
./.venv/Scripts/errata-audit.exe classes
```

```bash
./.venv/Scripts/python.exe audit/tools/demo_sweep.py
```

```bash
./.venv/Scripts/python.exe -m pytest -q
```
