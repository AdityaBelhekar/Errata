# R2 report — the catalog-scale audit

**Written:** 20 August 2026, at the end of the R2 (PHASES P5) build session.
**Reproduce everything here with:** `bash scripts/setup.sh` then `errata-scale run`.

> **Read this first.** R2's exit criterion (PRD §4) is *"full audit of a 10k+ SKU **public** catalog
> subset with a drainable ranked queue."* Two of those three things are done and demonstrated. The
> word **public** is not. No public industrial catalog of that size carrying technical attributes
> and pointing at retrievable source documents was reachable; §7 records the hunt and what it
> closed on. The corpus this report runs over is **constructed**, its provenance file says so, and
> every report the tool prints says so on its face. **The phase is complete on nine of nine
> requirements and open on half of one exit criterion, and this document does not blur the two.**

---

## 1. What R2 is

R1 proved one SKU could be audited against one document. R2 answers the question a buyer actually
asks: *what does this tell me about my whole catalog, and can two people act on it?*

The release is one new distribution, `errata-scale`, and one new command:

```bash
errata-scale run --html var/scale/report.html
```

It adds four things R1 did not have, and each is a requirement rather than a preference:

| | |
|---|---|
| **A forecast before the audit** | The groundable fraction is computed over the whole feed *before* a value is re-derived (FR-8.1). A defect count without it is unreadable. |
| **A tier that needs no document** | T0 checks the feed against its own declared units and against itself. On a catalog where 97% of records have no datasheet, this is the difference between a report and an apology. |
| **A queue that can be drained** | Ranked by expected review value with every factor shown separately (FR-8.4), decisions persisted append-only (FR-8.2), and reversible in bulk as a query (FR-8.8). |
| **Patterns, counted** | Error signatures clustered from the findings (FR-8.5), keyed to artifacts and **never to a company** (FR-8.6). |

**What R2 still does not claim.** There is no calibration set — FR-6.1 remains unmet, because
calibration needs reviewer decisions and no reviewer has made one. Structural findings therefore
carry **no probability at all** and are ranked on blast radius alone; every queue row says so in
words. Revenue weight and propagation count are customer configuration and are unset, and the queue
marks them as stated defaults rather than showing a 1.0 that reads like a measurement.

---

## 2. The run

```
10,001 records · 2 documents · policy electrical-conservative@v3 · ETIM 10.0
```

### 2.1 Groundable fraction (FR-8.1) — the number that makes the rest readable

| bucket | records | share |
|---|---:|---:|
| `groundable` | 277 | 2.77% |
| `document_named_not_supplied` | 1 | 0.01% |
| `document_unreadable` | 0 | 0.00% |
| `no_document_named` | 9,723 | 97.22% |

**2.77% of this catalog can be audited against a manufacturer document.** That is the honest
headline and it is printed above the findings, not below them. The remaining 97% is not a defect
and is not dropped: it is a document-recovery queue, and the report ranks it by how many records
each missing document would unlock.

The buckets are exhaustive, mutually exclusive, and summed on exact rationals rather than floats —
`percentages_sum()` is asserted by test, including on populations (three records) where float
percentages provably cannot total 100%. Every bucket enumerates to record level:

```bash
errata-scale groundable --bucket no_document_named
```

### 2.2 Tiered execution (FR-8.7) — measured, not estimated

| tier | what it does | records entered | work | scales with |
|---|---|---:|---:|---|
| T0 | structural checks, no document required | 10,001 | 50,005 cell checks | catalog size |
| T1 | re-derivation against a source document | 277 | 1,385 re-derivations | groundable fraction |
| T2 | counter-evidence and calibration | 1,495 | 67 counter-evidence searches | error count |
| T3 | a reviewer | 1,495 | 1,495 queue rows | error count |

Every number is a count of operations that happened. The acceptance criterion — *"T2/T3 volume
scaling with error count, not SKU count"* — is not asserted from this table: a test runs the same
catalog twice, once padded with 200 clean records, and demands T0 grows while **T2 and T3 do not
move at all**. A scaling claim measured at one size is not a measurement.

The tier boundary is a code path rather than a diagram: `errata_audit.audit._judge` calls
`find_counter_evidence` only after a comparison raises a finding, which is why T2 did 67 searches
over 10,001 records.

### 2.3 Findings

| | |
|---|---:|
| queue rows | **1,495** |
| from T0 — the feed's own structure | 1,428 |
| from T1 — a source document | 67 |
| error signatures | 9 |
| coverage, over the 277 groundable records | 79.4% |
| coverage, whole catalog | 89.2% |

**Read the coverage next to the groundable fraction, always.** 79.4% describes the population where
evidence existed. The tool never prints it without 2.77% beside it, and neither should anyone else.

### 2.4 Declined — one machine-readable reason each (FR-6.2)

| reason | records |
|---|---:|
| `no_source_document` | 9,729 |
| `equal_rank_source_conflict` | 986 |
| `value_outside_known_grammar` | 276 |
| `layout_unreadable` | 2 |
| `no_span_available` | 2 |

`equal_rank_source_conflict` is new at this scale and it is the resolution policy doing its job:
493 families hold two rows that disagree with **no majority**, so the policy declines to arbitrate
and surfaces both rather than letting whichever row was exported first become the truth. The
`value_outside_known_grammar` count is the order-code column, which the value layer refuses by
design — R1 put it in the attribute map precisely so the refusal would be visible.

### 2.5 Error signatures (FR-8.5) — computed, not asserted

Nine signatures over 1,495 findings. The four largest:

| records | pattern | tier |
|---:|---|---|
| 473 | blank cell on `packaging_uom` (`catalog_null_evidence_present`) | T0 |
| 360 | digit transposition on `rated_current` (`contradiction`) | T0 |
| 360 | order of magnitude on `rated_current` (`contradiction`) | T0 |
| 235 | no proposal on `rated_current` (`unsupported_value`) | T0 |

`size` is `len(members)` of an enumerable member list, the fingerprint that grouped them is printed
next to the count, and every member is addressable by redline id. *"473 records share this pattern"*
is the sentence that turns a list of defects into a decision, and it is also the easiest number in
this product to fake, which is why it is computed and inspectable.

T0 and T1 signatures never merge, and that is correct rather than a limitation: a defect found
against the feed's own rows and one found against a manufacturer's datasheet rest on different
evidence, and merging them would let the weaker inherit the stronger one's cluster size.

### 2.6 Detection, against what the corpus says is there

The corpus states, family by family, what a competent reviewer should conclude. The audit is then
run and the two are compared by test — if they ever disagree, the build fails.

| | expected | found |
|---|---:|---:|
| T0 findings | 1,428 | **1,428** |
| T0 declines (equal-rank abstentions) | 986 | **986** |
| **false positives on 654 equivalence-trap families** | 0 | **0** |
| false positives on 1,918 consistent / clean families | 0 | **0** |

The traps are the point. 447 families state the same weight in kilograms and in grams; 207 write
one pole count as `1` and `1P`. **FR-5.3 — "semantic equivalence must not flag" — holds at T0**,
which is a new place for it to break, because T0 compares a feed against itself with no document to
appeal to. It holds because T0 runs every comparison through `errata_comparator.compare_attribute`
rather than through string equality.

One subtler trap is worth naming: a 1-1 split between `0.125 kg` and `125 g` *is* a tie, and a naive
equal-rank rule would put it in the Declined bucket. That would be a non-disagreement quietly eating
coverage, so the tie branch first asks whether any sibling genuinely contradicts the modal value.

**T1's numbers are R1's, unchanged**: 67 findings over the 277 grounded records, 79.4% coverage —
the same 56 injected defects and 11 gaps `docs/R1-report.md` reports, reproduced by the R2 pipeline
without touching `audit_sku`. R2 adds scale, not a second opinion about how one SKU is audited.

That is **asserted, not observed**. `scale/tests/test_r1_parity.py` re-runs the T1 tier over R1's
own catalog and pins 67 findings and 79.4% coverage, because the most dangerous thing a scale
release can do is quietly improve or quietly degrade the audit it wraps — and `run_catalog` does
change *how* R1 is invoked, extracting each document's layer and tables once per document rather
than once per record. Performance changes are exactly the kind that alter results by accident. The
same test pins that T0 raises **nothing** on that catalog: one row per part number means T0 has
nothing to compare, so a structural finding there would be an invented one.

### 2.7 Batch reversal (FR-8.8) — demonstrated on 1,000 records

```bash
errata-scale drain --by "A. Reviewer" --second "B. Reviewer" --count 1000
errata-scale reverse --batch <id> --by "C. Operator"
```

```
accepted redlines in batch   1,000
reversed by this call        1,000
already reversed                 0
distinct SKUs restored       1,000
```

Run it again and it reverses nothing: `already reversed 1,000`, and the ledger does not grow. That
matters more than it sounds — the operator reaching for this function is having a bad day, and a
second attempt must not double-write.

**Nothing is deleted.** Each reversal is a new claim superseding the accepted one, so the accepted
claim stays readable forever: somebody accepted it on evidence that was accurate at the time, and
erasing it would turn a defensible decision into an inexplicable gap. A reversal carries **no
evidence**, deliberately — it withdraws our accusation rather than asserting that the catalog value
is right, and attaching the original evidence would misdescribe it as a positive finding.

The batch id is content-addressed (feed sha256 + policy + attribute map + code versions), so two
identical runs are **one** batch. Recording it twice writes nothing the second time.

---

## 3. The four requirements that needed a real decision

### 3.1 FR-8.1 — the single-document convenience overstates the forecast, and stays anyway

`errata_audit.cli` treats one supplied document as covering a record that names none. R2's inventory
does the same, which means a 10,000-row feed with one PDF would forecast 10,000 groundable records
and then decline most of them at T1.

Kept, and the cost is written into the test that pins it. The alternative is worse: a forecast that
used a different rule from the audit would give two numbers that cannot be checked against each
other, and the whole point of computing the fraction before the run is that it can be.

### 3.2 FR-8.2 — "no UPDATE or DELETE in any code path" is a claim about source, so it is checked as one

A test that appends events and observes that nothing was overwritten proves only that the paths it
exercised behaved. `errata_scale.scan_for_mutation` parses **every module of every distribution**
and reports any operation that could overwrite a ledger — a truncating `open`, an `unlink`, a
`rename` over one. The repository is asserted to produce an empty list, and two further tests write
modules that *do* mutate and assert the scanner catches them, because a check that cannot fire is
decoration.

```bash
errata-scale integrity
```

### 3.3 FR-8.6 — the prohibition is structural, not editorial

The natural next feature after clustering is *"which supplier sends us the worst data"*, and it is a
product that gets its author sued: a defect count keyed to a named company, produced by a system
with a non-zero false-positive rate, published inside a customer's organisation, is defamation with
a dashboard.

So there is no field to put the name in. `ErrorSignature` is inspected against a banned lexicon at
import time, a test asserts a schema that *does* grow `supplier_id` is rejected, and a behavioural
test asserts that the same defect under two different manufacturers lands in **one** cluster — so
even a renamed field could not reintroduce it.

### 3.4 FR-8.4 — a factor nobody supplied is shown as a factor nobody supplied

Every term of expected review value is carried separately with the sentence that says where it came
from and a `measured` flag. `revenue weight = 1 (not supplied — stated default)` reads differently
from `revenue weight = 1`, and that difference is the whole of FR-8.4's "independently inspectable".

`record_multiplicity` is the one term R1 could not compute, because it is not knowable one record at
a time. R2 clusters first and ranks second, so it is a counted number with a fingerprint attached.

---

## 4. The findings R2 produced

Numbered continuing from R1's N11–N14.

- **N15 · Redlines and claims speak two vocabularies for one attribute. NOT FIXED; contained.**
  `errata_comparator.build_redline` sets `attribute_uri` from `AttributeSpec.key` (`rated_current`)
  because it has no ETIM id to set it from, while `errata_audit.audit.stable_redline_id` derives the
  redline's **identity** from `attribute.uri` (`etim:EF000227`). R1 is therefore internally
  inconsistent: the id says one thing and the field says another. R2 found it by clustering across
  tiers — signatures split in two because the two tiers disagreed about what the attribute was
  called. **Contained rather than fixed**: R2's structural redlines follow the comparator's
  convention, so the clusters merge. Fixing it properly means teaching `build_redline` the ETIM id,
  which changes every existing redline id and invalidates recorded adjudications; that is an R3
  change, alongside FR-9.7's ETIM↔UNSPSC bridge, and it is logged here rather than done quietly.

- **N16 · The feed index cited the wrong two characters of every row. FIXED.**
  `index_feed` computed a line's span as the *count of its trailing newline characters* rather than
  the length of its content, so every structural finding's evidence pointed at the first two bytes
  of the row. It passed the obvious test — the snippet was sliced from the same span, so it was
  self-consistently wrong — and was caught by a test that asserted the snippet equalled the literal
  `"16 A"`. **A grounding test that only checks internal consistency checks nothing**, which is a
  lesson this repository has now learned twice.

- **N17 · `--limit` meant two different things in one command. FIXED.**
  `errata-scale drain --limit 1000` was read by the shared run loader as *"audit the first 1,000
  records"* and by the drain as *"decide 1,000 rows"*, so a drain silently audited 3% of the catalog
  and then reported a drained queue. The option is now `--count`, and the reason is a comment at the
  definition rather than in a changelog.

- **N18 · Two `conftest.py` files shadowed each other across distributions. FIXED.**
  `audit/tests` and `scale/tests` are both on `sys.path` with no `__init__.py`, so
  `audit/tests/test_audit.py`'s `from conftest import ...` began resolving to R2's module and seven
  R1 test files failed to collect. It passed when either suite was run alone and when they were run
  in the other order, which is exactly the kind of failure that gets "fixed" by reordering something
  until it goes away. The R2 fixtures now live in a uniquely named module and R2 ships **no**
  `conftest.py`; R1's tests were not touched.

All four carry regression tests. N16's asserts a literal snippet rather than a self-consistent one;
N15's is a comment at the site that would otherwise look like a mistake.

---

## 5. Requirement coverage

| | Requirement | State |
|---|---|---|
| FR-8.1 | Groundable Fraction Report | ✅ Computed before any audit, exhaustive buckets, exact-rational sum, enumerable to record level |
| FR-8.2 | Append-only claim ledger with `supersedes` chains | ✅ Chains reconstructed and validated (fork, cycle and orphan all raise); no UPDATE or DELETE anywhere, asserted by a source scan |
| FR-8.3 | Versioned resolution policy, executed | ✅ Engine applies rank / recency / specificity / tolerance / safety / equal-rank abstention; **every** resolution records `policy_version`, including the ones that resolve nothing |
| FR-8.4 | Triage router, factors independently inspectable | ✅ Five factors, each with provenance and a `measured` flag; ranking reproducible through ties |
| FR-8.5 | Error-signature clustering | ✅ 9 clusters, `size == len(members)`, members enumerable |
| FR-8.6 | No named-organisation signatures | ✅ No schema field; import-time check; a rejection test and a two-manufacturer behavioural test |
| FR-8.7 | Tiered execution T0→T3 with a cost report | ✅ Measured operation counts; the scaling claim tested at two catalog sizes |
| FR-8.8 | Batch reversal as a query | ✅ 1,000 records, idempotent, nothing deleted, narrowable to one signature |
| FR-8.9 | Two adjudicators for safety-class attributes | ✅ Refused before the ledger is touched, and refused again by `Redline` itself |

**Exit criterion:** *full audit of a 10k+ SKU **public** catalog subset with a drainable ranked
queue.*

| | |
|---|---|
| 10k+ SKU | ✅ 10,001 records, audited end to end |
| drainable ranked queue | ✅ Drains to zero; decisions persist across a rebuilt queue; safety rows are decidable with two signatures |
| **public catalog** | ❌ **Not met.** See §7 |

**Tests: 1,078 passing** (933 + 145 for R2). `ruff check .` clean.

---

## 6. What R2 does not answer

- **FR-6.1 is still unmet and now costs more.** With 1,495 findings and no calibration set, the
  queue's top rows are ordered by blast radius alone. The ordering is defensible and it is not the
  ordering the PRD describes; the missing term is a probability, and a probability needs reviewer
  decisions.
- **T0's precision is measured against injected defects.** 1,428 of 1,428 found and 0 false
  positives on 654 traps describes a population we created. The traps are the same shapes R0's
  equivalence suite uses, so it is not a circular test — but it is not a field measurement either.
- **The reviewer-seconds in this repository are still scripted.** `errata-scale drain` prints a
  banner saying so on every run. FR-9.3 becomes a claim at a few hundred human decisions, which
  needs reviewers rather than code.
- **T1 ran on 277 records.** Everything R1 could not do — OCR, embedding retrieval, the LLM class
  selector — it still cannot do, and at 2.77% groundable those gaps bound the whole result.

---

## 7. The exit criterion's missing half: no public catalog was reachable

**Searched 20 August 2026.** The requirement is a public catalog subset of 10,000+ SKUs carrying
technical attributes *and* pointing at retrievable source documents. What was checked, and what it
closed on:

- **Manufacturer feeds.** ABB, Schneider and their peers publish datasheets freely and catalogs
  through partner APIs that require credentials. `audit/tools/build_demo_catalog.py` already
  recorded this for R1: *"no public ABB catalog feed is available to us."*
- **Distributor APIs** (Digi-Key, Mouser, RS, Farnell): keys and terms that forbid redistribution.
- **Product data pools.** Open Icecat requires registration; ETIM publishes the **taxonomy** and no
  articles — the same negative result D-1 recorded when hunting a per-class SKU distribution.
- **Open government and open-data sets.** Large public product registers exist (energy-efficiency
  certification databases, for example) but are out of the ETIM classes R1 and R2 are scoped to, and
  carry no per-SKU source document. Auditing them would mean building a second attribute map and a
  second class scope to measure a different product.

That is three independent angles closing on the same answer, which is the pattern D-1 established
and the reason it is recorded rather than worked around. **The corpus is therefore constructed, and
labelled:**

| | Real | Constructed |
|---|---|---|
| the ABB S200 datasheets | hash-registered, ABB's own | |
| the values Errata re-derives from them, and their spans | ✅ empirical | |
| the S1 rows (278) | derived from those datasheets by R1's generator | |
| the value pool S2 draws from (IEC preferred series, the datasheet's weights and packing units) | ✅ | |
| **the S2 rows (9,723) and the defects in them** | | **generated** |

Mutation is by `sha256(family key) % 100` — reproducible from the SKU list alone, in any Python, in
any iteration order, forever. Every synthetic manufacturer is `SYN-MFR-nn`: a plausible-sounding
name in a defect corpus is one copy-paste away from a defamatory claim about a real company, which
is FR-8.6's reasoning applied to the fixtures.

**What would close this.** The corpus generator takes any CSV; `errata-scale run --catalog <file>`
runs over a customer's own feed with no code change, and the groundable-fraction report is designed
to be the first thing such a customer sees. The open half of the criterion needs a catalog, not an
engineering change — and `docs/data-request-etim-distribution.md` is the template for asking.

---

## 8. Reproducing this report

```bash
bash scripts/setup.sh
```

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

The corpus is generated rather than committed — ten thousand rows of constructed catalog is not
source — and `scripts/setup.sh` builds it. To rebuild it alone, at any size:

```bash
./.venv/Scripts/errata-scale.exe corpus --total 25000
```
