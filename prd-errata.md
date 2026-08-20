# PRD — Errata

**A verification layer for industrial product data.**

| | |
|---|---|
| **Status** | Draft for build |
| **Date** | 17 August 2026 |
| **Product name** | Errata *(provisional — registry, domain and trademark checks incomplete; see `phase4-full-spec.md` §11)* |
| **Upstream documents** | `phase4-full-spec.md` (architecture, ADRs, strategy) · `phase5-red-team.md` (risks, kill criteria) · `phase1-3` (research) |
| **This document's job** | Turn the spec into buildable, testable requirements. It does **not** restate strategy — where a decision was already made and justified upstream, this PRD cites the section and moves on |
| **Hackathon PS** | AI-Powered Product Intelligence for Industrial Commerce — data enrichment, validation, **explainable outputs** |

---

## 1. Problem

Industrial distributors hold millions of SKUs whose technical attributes were populated by offshore teams, BPOs, or an incumbent PIM's AI module. At 95% accuracy, a two-million-SKU catalog contains a hundred thousand wrong records, **and nobody knows which hundred thousand.** A wrong unit-of-measure corrupts margin analytics, breaks punchout feeds into customer ERPs, and triggers phantom inventory allocations. A wrong circuit-breaker rating is a safety exposure.

The market cannot currently solve this because it cannot show its work. Verified, three weeks old, from ExtractBench (arXiv 2607.29677):

| Metric, same system (LlamaExtract Agentic Plus) | Score |
|---|---|
| Value F1 — does it get the answer right? | **95.6%** |
| Word-level grounding F1 @ IoU 0.5 — can it point at the words? | **46.43** |
| Page-level grounding F1 (best in field) | 84.92 |
| Systems returning no evidence at all | **8 of 14** |

Extraction is solved. **Evidence is not.** The problem statement asks for explainable outputs; the state of the art can name the right page ~85% of the time and the right words less than half the time.

---

## 2. Product summary

Errata ingests a product catalog **and** the source documents behind it, independently re-derives every attribute, grounds each value to a word-level span, calibrates its own confidence, and emits a ranked list of records where the catalog and the evidence disagree — with the evidence attached.

**It grades data. It does not create data.**

### 2.1 What Errata is not — binding non-goals

These are requirements, not preferences. A build that violates one has failed, not compromised.

| Non-goal | Why |
|---|---|
| **Not an enrichment tool.** It never fills a blank field as a product feature | The moment it produces values, it competes with a commodity endpoint and inherits every liability it exists to detect |
| **Not a PIM, DAM or MDM** | Sits beside the customer's system of record, never replaces it |
| **Never writes to a customer catalog in R1–R2** | ADR-001. Output is a redline addressed to a human |
| **Never auto-resolves a safety-class attribute**, at any confidence, with no configuration override | §4.2 safety-class override |
| **No chatbot, no "ask your catalog", no generic RAG** | Master prompt banned list; Phase 1 §1C-4 |
| **No demo or benchmark run on clean, current, well-documented records only** | Phase 2 §6 amended ban — value lives in the tail |
| **Never requires the customer to change their taxonomy** | Phase 2 §6 amended ban — "they would rather hire temps than re-platform their taxonomy" |
| **No named-organisation error signatures** | §9.2 — defamation and channel-conflict surface |

---

## 3. Users

| # | Persona | Job to be done | Priority |
|---|---|---|---|
| **U1** | **Compliance owner** under a dated obligation (ESPR/DPP, REACH/RoHS SVHC) | "Prove our published technical data is defensible for the fields my regulation names" | **Primary** |
| **U2** | **Post-acquisition integration lead** | "Quantify the state of the catalog I just inherited, before it becomes mine" | Primary |
| **U3** | **Catalog operations reviewer** — the person in the queue all day | "Show me only what's worth my next 30 seconds, and show me why" | **Primary user, not primary buyer** |
| **U4** | **Head of digital / e-commerce**, first 180 days | "Establish the baseline I'll be measured against" | Secondary |
| **U5** | **Distributor onboarding an untrusted supplier** | "Check this feed before it touches my catalog" | Secondary |
| **U6** | **Open-source contributor / data engineer** | "Parse industrial compound values correctly without writing my own grammar" | Ecosystem |

U3 is the user whose experience determines whether the product survives contact. U1/U2 sign; U3 decides whether it renews.

---

## 4. Release plan

Sequenced by dependency, not duration. **R0 gates everything** — per `phase5-red-team.md` §4, two of its three tests can end the project, so no R1 work starts until R0 reports numbers.

| Release | Name | Contains | Exit criteria |
|---|---|---|---|
| **R0** | **Kill tests** | Equivalence suite, operating-point measurement, calibration-coverage arithmetic. No UI, no pipeline, no repo polish | FP rate < 2% on equivalence suite; measurable audit-vs-extraction asymmetry; calibration coverage arithmetic understood |
| **R1** | **Single-SKU audit + console** | End-to-end audit of one SKU against one datasheet, evidence-boxed redline, three-pane console, abstention bucket, CLI. **The demo target** | The §12 demo script runs on public data, unrehearsed, on a SKU chosen at runtime |
| **R2** | **Catalog-scale audit** | Groundable Fraction Report, batch audit, triage router with blast radius, claim ledger, resolution policies, error-signature clustering | Full audit of a 10k+ SKU public catalog subset with a drainable ranked queue |
| **R3** | **Benchmark + ecosystem** | Public gold set, harness, leaderboard, ETIM↔UNSPSC bridge, ECLASS BYO-licence adapter | Third party reproduces our published scores from the repo |
| **R4** | **Commercial** | Monitoring, connectors, calibration service, gated write-back | Out of scope for this PRD |

---

## 5. Functional requirements

Priorities are **within** their release. P0 = release cannot ship without it.

### 5.1 R0 — Kill tests

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-0.1 | **Equivalence suite.** 500 hand-labelled equivalence pairs and 500 genuine contradictions from public datasheets, spanning materials, threads, tolerances, ingress codes, packaging frames, unit frames | P0 | Dataset published as fixtures; every pair carries a source URL and a rationale; dual-labelled where judgment is involved |
| FR-0.2 | **FP-rate measurement** of the comparator against FR-0.1 | P0 | Reported as a single number with a confidence interval. **< 2% passes; > 5% stops the project** |
| FR-0.3 | **Operating-point measurement.** 200 hand-labelled MCB records; disagreement-detection precision and word-level grounding F1 @ IoU 0.5, at 20/40/60% coverage | P0 | Risk–coverage curve plotted; compared explicitly against ExtractBench's 46.43 word-level / 95.6 value F1 at full coverage |
| FR-0.4 | **Calibration-coverage arithmetic.** Given a real catalog's ETIM class distribution, compute how many classes clear a minimum label floor under a stated labelling budget | P1 | A table of coverage vs budget. If coverage is single-digit %, R2 scope narrows to named high-volume classes |

### 5.2 R1 — Ingest and document handling

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-1.1 | Ingest a catalog record from a URL, CSV row, or JSON object: SKU, MPN, manufacturer, existing attribute values | P0 | Round-trips without value mutation; original strings preserved verbatim |
| FR-1.2 | Ingest a source document by URL or local path (PDF, born-digital or scanned) | P0 | Stored in a content-addressed blob store |
| FR-1.3 | **Document Register.** Every document stored with `sha256` of bytes, fetch timestamp, source URL, and a revision label where the document declares one | P0 | Re-fetching identical bytes does not create a second record; changed bytes create a new revision linked to the prior |
| FR-1.4 | **Layout + OCR** producing a canonical, char-indexed text layer with a bbox map per token | P0 | Deterministic for identical input bytes and identical extractor version; cached; version-stamped |
| FR-1.5 | Table structure detection with cell, row-header and column-header roles | P0 | A value in a table cell can resolve its row and column headers (required by FR-4.3) |
| FR-1.6 | Handle multi-column catalog pages without merging adjacent products | P1 | On a labelled multi-column fixture set, no cross-product attribute bleed; where ambiguous, abstain per FR-6.2 |

### 5.3 R1 — Class resolution

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-2.1 | Load the **ETIM** dictionary (classes, attributes, value lists, units) from the ODC-By distribution, with attribution recorded | P0 | ETIM 10.0 loads; loader is release-parameterised so 11.0 (1 Dec 2026) loads without code change |
| FR-2.2 | **Retrieve → rerank → select** class resolution: lexical + embedding retrieval to top-50, cross-encoder to top-5, LLM selects with class definitions in context | P0 | Architecture is literally three stages; an LLM is never given more than 5 candidates. Top-1 and top-5 accuracy reported on a labelled set |
| FR-2.3 | Emit class-resolution confidence and abstain when top candidates are not separable | P1 | Abstention appears in the Declined bucket with reason, not as a silent default class |
| FR-2.4 | R1 scope limited to **low-voltage circuit protection** ETIM classes | P0 | Class allow-list is configuration, not hardcoded logic |

### 5.4 R1 — Re-derivation

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-3.1 | Extract attribute values constrained to the resolved class's schema — its attributes, its enums, its units | P0 | Output outside the class's declared value list is rejected before it becomes a claim |
| FR-3.2 | **Span-required extraction.** Every value carries `doc_id`, `revision_sha256`, `page`, `char_span`, `bbox`, `snippet` | P0 | **A claim with an empty evidence array cannot be constructed.** Enforced at the type/constructor level, not by validation that can be relaxed |
| FR-3.3 | When no span can be produced, emit an **abstention object** with a reason — never a value | P0 | Abstentions and claims are distinct types; an abstention can never be read as a value downstream |
| FR-3.4 | Re-derivation must not see the catalog's existing value when producing its own | P0 | Verified by test: the extractor's input payload contains no catalog value. Prevents anchoring, which would silently destroy the product's independence |

> **FR-3.4 is the requirement most likely to be quietly broken during optimisation.** Passing the catalog value in as a hint measurably improves grounding — and makes every subsequent agreement meaningless. Guard it with a test, not a comment.

### 5.5 R1 — Value semantics (the C1 library)

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-4.1 | **Deterministic normalizer. No model in the hot path.** Pipeline: regex → grammar → ontology lookup → unit conversion | P0 | No network call, no model invocation, in any code path of this module. Enforced by test |
| FR-4.2 | Parse compound values into typed structures: `M8 × 1.25`, `3/8-16 UNC`, `10 ±0.2 mm`, `IP67`, `6061-T6`, ranges, tolerances | P0 | Grammar **either parses or refuses**. Refusal is a routable signal (FR-6.2), never a best guess |
| FR-4.3 | Resolve material and vocabulary equivalence classes: `316 SS` ≡ `A4` ≡ `1.4401` | P0 | FR-0.1 equivalence suite passes at < 2% FP |
| FR-4.4 | Unit conversion across metric/imperial with tolerance preservation | P0 | `0.5 in` ≡ `12.7 mm`; `10 mm` vs `10 ±0.2 mm` classified as precision loss, not contradiction |
| FR-4.5 | Grammars are versioned; every normalized value records `grammar_version` | P1 | A grammar change is detectable in the ledger and re-runnable |
| FR-4.6 | Ships as a standalone Apache-2.0 package, usable with no other component | P1 | `pip install` and parse, no Errata pipeline required |

### 5.6 R1 — Comparator

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-5.1 | Compare catalog value against re-derived value **only after both are normalized** into the same semantic space | P0 | No raw string comparison anywhere in the decision path |
| FR-5.2 | Classify every difference into the taxonomy: contradiction · unsupported value · catalog-null/evidence-present · unit-frame mismatch · precision mismatch · **semantic equivalence** · granularity mismatch · packaging-frame error | P0 | Every flagged record carries exactly one class; classes are exhaustive and mutually exclusive |
| FR-5.3 | **Semantic equivalence must not flag** | P0 | FR-0.2 gate. This is the single highest-consequence requirement in the document |
| FR-5.4 | Packaging-frame errors (`Each` vs `Box of 10`) flagged at maximum severity | P0 | Present in R1 demo fixtures |
| FR-5.5 | Granularity mismatch (`Threaded` vs `NPT 1/2-14`) flagged as under-specified, never as wrong | P1 | Distinct severity and distinct reviewer copy from contradiction |

### 5.7 R1 — Confidence and abstention

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-6.1 | Calibrated probability per disagreement, method recorded (`conformal` \| `platt`), with the calibration set identified | P0 | Reliability diagram published; `calibrated_p = 0.9` means ≈9-in-10 on held-out data |
| FR-6.2 | **Declined bucket** with a machine-readable reason per record: `no_source_document`, `layout_unreadable`, `ambiguous_multi_product_page`, `value_outside_known_grammar`, `equal_rank_source_conflict`, `calibration_out_of_distribution` | P0 | Every declined record has exactly one reason and is visible in the UI. **No silent skips anywhere in the pipeline** |
| FR-6.3 | Risk–coverage curve and AURC computed for any audit run | P1 | Rendered in the console and emitted in the run report |

### 5.8 R1 — Explainability and console

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-7.1 | Three-pane console: queue · evidence · claim history | P0 | Reviewer can adjudicate without leaving the screen |
| FR-7.2 | **Word-level evidence box** rendered on the source page at the stored span's projection | P0 | Box lands on the value's words, not the paragraph or page |
| FR-7.3 | **Header highlighting.** The containing cell outlined, plus its row and column headers in a second colour | P0 | A number in a table is never shown without the headers that give it meaning |
| FR-7.4 | **Counter-evidence panel.** Best evidence *for* the catalog's value, or an explicit "no supporting evidence found" | P0 | Never empty and never absent. A disagreement with no counter-evidence section fails review |
| FR-7.5 | Queue rows render as a sentence — values, source location, shared-pattern count, downstream propagation — **never a bare confidence percentage** | P0 | No UI surface displays a raw confidence score as the primary signal |
| FR-7.6 | Adjudication: Accept redline · Keep catalog · Escalate. Each writes a human-asserted claim | P0 | Decision, actor, timestamp and note persisted immutably |
| FR-7.7 | OCR-layer toggle, raw-page jump, document revision history | P1 | Reviewer can see what the machine actually read |
| FR-7.8 | Evidence shown is reconstructible from stored state, not regenerated at view time | P1 | "What was this reviewer looking at" has one permanent answer (§4.3) |
| FR-7.9 | **CLI:** `audit sku --catalog-url <url> --datasheet <url>` prints a redline with evidence, or an honest abstention | P0 | Runs from a clean clone with no signup. This is the README hook |

### 5.9 R2 — Scale

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-8.1 | **Groundable Fraction Report** — catalog inventoried against retrievable evidence before any audit, broken down by source type and reason | P0 | Percentages sum; every bucket is enumerable to record level |
| FR-8.2 | **Claim ledger** — append-only, immutable, with `supersedes` chains | P0 | No UPDATE or DELETE on claims in any code path. Full history reconstructible |
| FR-8.3 | **Resolution policy** as a versioned declarative document (source rank, recency, specificity, tolerance-never-dropped, safety-class escalation, equal-rank abstention) | P0 | Every resolved value records the policy version that resolved it |
| FR-8.4 | **Triage router** ranking by expected review value = P(catalog wrong) × blast radius (revenue weight × safety multiplier × propagation count × record multiplicity) | P0 | Ranking is reproducible and each factor is independently inspectable in the UI |
| FR-8.5 | **Error-signature clustering** — group records sharing a systematic pattern, report cluster size | P1 | The "1,240 SKUs share this pattern" claim is computed, not asserted |
| FR-8.6 | Signatures key to document/data artifacts only. **Named-organisation signatures are prohibited** | P0 | Schema has no field for it; test asserts absence |
| FR-8.7 | Tiered execution: T0 structural (all records) → T1 grounded (documented records) → T2 deep (disagreements only) → T3 human | P0 | Cost report shows T2/T3 volume scaling with error count, not SKU count |
| FR-8.8 | Batch reversal — any audit batch's accepted redlines revert from the ledger as a query | P0 | Demonstrated on a 1,000-record batch |
| FR-8.9 | Safety-class attributes require a second named adjudicator | P0 | Single-signature acceptance impossible for allow-listed attributes |

### 5.10 R3 — Benchmark and ecosystem

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-9.1 | Grounding scored with **ExtractBench's metric verbatim** — value accepted AND predicted box overlaps an accepted box at IoU 0.5 | P0 | Our scores are directly comparable to the published 46.43 |
| FR-9.2 | Score the five unscored axes: ETIM class assignment · compound-value normalization · cross-standard mapping · supersession · **calibrated abstention with risk–coverage, AURC, selective accuracy at fixed coverage** | P0 | Each axis independently runnable |
| FR-9.3 | **Reviewer-seconds-per-verified-attribute** via a timed human protocol | P0 | Protocol documented reproducibly; results include decision accuracy, not just speed |
| FR-9.4 | **Evidence-acceptance rate** — fraction of redlines whose box a domain reviewer accepts as supporting the claim | P0 | Reported alongside grounding F1. Distinct metric, distinct number |
| FR-9.5 | Gold set distributed as **URLs + content hashes + annotation layers only. No source PDFs redistributed** | P0 | Fetch script reconstructs the corpus locally; no copyrighted document in the repo |
| FR-9.6 | Frozen hard-tail split (degraded scans, fold-outs, cross-page tables, superseded revisions) never used for tuning | P0 | Split hash recorded; CI fails if tuning touches it |
| FR-9.7 | **ETIM ↔ UNSPSC attribute bridge**, published Apache-2.0 with ODC-By attribution | P1 | Bridges UNSPSC's eight-digit code to ETIM attributes — the documented hole |
| FR-9.8 | **ECLASS adapter reads the customer's own licensed dictionary at runtime.** No ECLASS content in repo, image or benchmark | P0 | ADR-003. Verified by inspection of build artifacts |
| FR-9.9 | Published leaderboard includes our own losing scores | P1 | Leaderboard is generated from the harness, not hand-edited |

---

## 6. Non-functional requirements

| ID | Requirement | Acceptance criteria |
|---|---|---|
| NFR-1 | **Reproducibility.** Identical inputs + identical component versions → identical claims | Re-run produces byte-identical claim payloads excluding timestamps and ids |
| NFR-2 | **Extractor fingerprinting.** Every claim records model id, prompt sha256, params sha256, decode-constraint sha256 | Any claim's provenance is fully reconstructible |
| NFR-3 | **Evidence durability.** Bboxes are a projection of stored char spans, regenerable after an OCR upgrade (ADR-002) | Upgrading the layout engine recomputes coordinates without invalidating claims |
| NFR-4 | **Calibration drift alarm.** Fires on calibration degradation, not just accuracy degradation | Alarm triggers on a synthetic drift fixture |
| NFR-5 | **Cost observability.** Per-run cost by tier, per page and per record | Run report includes measured cost; ExtractBench's 8.1¢/page is the T1 reference point |
| NFR-6 | **Data residency.** Record-level findings storable in the customer's own tenant | Deployment mode where no record-level finding leaves customer infrastructure |
| NFR-7 | **Licence hygiene.** Apache-2.0 for open components; ODC-By attribution for ETIM; no licensed dictionary content committed | CI licence check on every build |
| NFR-8 | **Determinism boundary.** The value-semantics module contains no model call or network call | Static check in CI |
| NFR-9 | **Auditability of the auditor.** Every pipeline decision, including abstentions, is logged with its reason | An auditor can reconstruct why any record was or was not flagged |

---

## 7. Key user flows

### UF-1 — Single-SKU audit (R1, the demo)
1. U3 supplies a catalog URL and a datasheet URL.
2. System registers the document, hashes it, builds the canonical text layer.
3. Resolves the ETIM class; abstains if unseparable.
4. Re-derives attributes **blind to the catalog's values** (FR-3.4).
5. Normalizes both sides; comparator classifies each difference.
6. Emits redlines with word-level evidence + counter-evidence, or abstentions with reasons.
**Acceptance:** on a SKU chosen at runtime, output is either an evidence-boxed redline or an honest abstention. Never a bare value, never a silent skip.

### UF-2 — Reviewer adjudication (R1)
1. U3 opens the top queue row — reads it as a sentence, not a score.
2. Evidence pane shows the boxed value with its row/column headers.
3. Counter-evidence pane shows the best case for the catalog, or states none exists.
4. U3 accepts, keeps, or escalates. Decision becomes a claim and a calibration label.
**Acceptance:** a domain reviewer decides without leaving the screen; a "keep catalog" with no counter-evidence is captured as a false-positive signal and a document-recovery lead.

### UF-3 — Groundable Fraction Report (R2)
1. U1/U2 supplies a catalog export.
2. System inventories retrievable evidence per record.
3. Report states auditable %, undefendable %, and reasons per bucket.
**Acceptance:** the undefendable set is enumerable to record level and exportable as a compliance finding and a recovery work queue.

---

## 8. Success metrics

| Metric | Why it exists | Target |
|---|---|---|
| **FP rate on equivalence suite** | The one number that decides the product | **< 2%.** > 5% = stop |
| **Evidence-acceptance rate** | Whether reviewers believe the box. Nobody measures this | Establish baseline in R1; it becomes the headline |
| **Word-level grounding F1 @ IoU 0.5** | Comparability to the published field | Beat 46.43 on our domain, at stated coverage |
| **Disagreement-detection precision at coverage** | Tests the §0.3 asymmetry the whole thesis rests on | Materially above extraction's operating point, or stop |
| **Reviewer-seconds-per-verified-attribute** | What the buyer actually pays for (Phase 2 §B2) | Establish the first published number in the category |
| **AURC / selective accuracy at fixed coverage** | The axis no benchmark scores | Reported for every release |
| **Groundable fraction** | Honest scope of the product | Measure on 3 public catalogs; < 50% forces re-scope |
| **Cost per audited record by tier** | Proves cost tracks disagreements, not SKUs | T2+T3 spend correlates with error count, not catalog size |

---

## 9. Dependencies and assumptions

| Type | Item | Status |
|---|---|---|
| Data | **ETIM** dictionary under Open Data Commons Attribution Licence | ✅ Verified. Attribution required. Free tier excludes some local language versions |
| Data | **ECLASS** | ⚠️ Licensed — single-release, concordance, pay-per-IRDI or membership; priced by company size. BYO-licence adapter only (ADR-003) |
| Data | **UNSPSC** — eight-digit code, four levels, **no attribute layer** | ✅ Verified. This is the hole FR-9.7 fills |
| Data | Manufacturer datasheets (Schneider, ABB, Siemens, Legrand, Eaton, Rockwell) | Publicly downloadable. **Copyrighted — never redistributed** (FR-9.5) |
| Schedule | **ETIM 11.0 releases 1 Dec 2026** (CRs closed 30 Jun; processed by 15 Oct; one-month beta) | ✅ Verified. FR-2.1 must be release-parameterised |
| Benchmark | ExtractBench — Apache 2.0, public dataset, open harness | ✅ Verified. Metric reused verbatim (FR-9.1) |
| Assumption | Auditing beats extraction at equal grounding quality | ❌ **Unproven.** FR-0.3 tests it. See spec §0.3 |
| Assumption | A one-time diagnostic converts to continuous monitoring | ❌ **Untestable pre-revenue.** The company thesis (§10.3) |
| Assumption | Error signatures generalise across customers | ❌ Unproven. Phase 5 A5 |

---

## 10. Risks

| Risk | Impact | Response |
|---|---|---|
| **False positives on semantic equivalence** | Reviewer trust gone in session one; no session two | FR-0.1/0.2 as a gate before any other work |
| **Evidence boxes wrong more often than right** at field-standard grounding | Product self-discredits on screen | FR-9.4 metric; a wrong box is at least self-revealing, unlike a silent wrong value |
| **Calibration coverage collapse** — `calibration_out_of_distribution` fires on most of the catalog | Product's honesty caps its coverage | FR-0.4 arithmetic first; hierarchical pooling up the ETIM tree; sell coverage per class |
| **Source documents missing on the valuable tail** | Product declines where the money is | Groundable Fraction Report as the *first* deliverable, not a caveat |
| **Anchoring:** catalog value leaks into re-derivation | Independence destroyed silently; every agreement becomes meaningless | FR-3.4 enforced by test |
| **"Everybody wants exactly one audit"** — report used as vendor-renegotiation ammunition | No recurring revenue | Price the diagnostic to stand alone; instrument drift so report #2 writes itself |
| **Incumbent ships "Data Quality Score"** | Distribution beats correctness | Stay vendor-neutral — grading work of unknown provenance is the position they can't occupy |
| **Wrong redline accepted by a human** | Customer's live catalog broken by a finding | Batch-reversible ledger, two-signature safety class, evidence-of-record retention (§4.3) |
| **Named-org signatures in the pattern corpus** | Defamation / channel conflict | FR-8.6 — no schema field for it |
| **Demo names a real distributor's errors** | Reputational and legal exposure | Frame as manufacturer-datasheet-vs-catalog discrepancy; anonymise; cached offline fallback |

---

## 11. Open questions

| # | Question | Blocks | Owner action |
|---|---|---|---|
| Q1 | Does the compliance buyer hold signable budget this quarter? | Go-to-market, R2 priorities | 15 structured conversations (Phase 5 A6). Run in parallel with R0 |
| Q2 | Is `Errata` actually available — PyPI, npm, GitHub org, domain, trademark class? | Naming commitment | Complete the registry checks §11 could not finish. Fallback: `Holdpoint` |
| Q3 | What is the minimum label floor per ETIM class for honest conformal coverage? | R2 scope | FR-0.4 |
| Q4 | Does a customer accept a redline queue they cannot drain, or does it need finding-retirement? | Triage router design | Observe in first R2 pilot |
| Q5 | Which eleven-ish fields does the ESPR/DPP obligation actually name for circuit protection? | U1 wedge scope | Read the delegated act text directly — do not infer it from research notes |

---

## 12. Glossary

| Term | Meaning |
|---|---|
| **Attribute** | One technical property of a product — rated current, thread pitch, IP rating |
| **Claim** | An immutable assertion about one attribute's value, carrying evidence, extractor fingerprint and calibrated confidence. The atomic unit of the system |
| **Redline** | A proposed correction addressed to a human: catalog value, evidence-supported value, evidence, counter-evidence. The system's only output |
| **Grounding** | Pointing at the exact words in a source document that support a value. Word-level grounding means a bounding box, not a page number |
| **Abstention** | Declining to answer a field whose value is present but ambiguous. Distinct from a correct `null` on a genuinely blank field |
| **Calibration** | Making a stated confidence mean what it says — `0.9` occurring ≈9 times in 10 |
| **Blast radius** | How much damage one wrong value causes: revenue weight × safety class × downstream systems touched × records sharing the pattern |
| **ETIM** | Industrial classification standard, ~5,600 classes, strong in electrical/HVAC/plumbing. Free under ODC-By |
| **ECLASS** | Deeper classification standard, ~50,000 classes / 23,000 properties. **Licensed** |
| **UNSPSC** | Eight-digit procurement classification. Four levels, no technical attributes |
| **MPN** | Manufacturer Part Number |
| **BMEcat** | XML container that transports ETIM or ECLASS payloads supplier-to-distributor |
| **Punchout** | Workflow where a buyer browses a distributor's catalog from inside their own ERP; line items return as a requisition |
| **PIM** | Product Information Management system — the customer's system of record |
| **Supersession** | An old part number being replaced by a new one over time |
| **Safety class** | Attributes where a wrong value creates physical or legal exposure. Never auto-resolved |

---

*Requirements trace to `phase4-full-spec.md`; risks and kill criteria trace to `phase5-red-team.md`. R0 gates all downstream work.*
