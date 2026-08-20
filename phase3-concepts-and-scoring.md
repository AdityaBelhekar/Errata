# Phase 3 — Concept Generation and Brutal Filtering

**Input:** Phase 1 research + Phase 2 synthesis and verification
**Rubric weights:** non-obviousness ×3, defensibility ×3, survives-C4 ×3, wedge sharpness ×2, demo shock ×2, OSS fit ×2, technical depth ×1, why-now ×1. Max 170.

**On the scores:** these are calibrated judgment, not measurement. The ranking is more trustworthy than any individual number, and the gaps under ~10 points are noise. Read the kill analysis in §4 before you trust the ordering.

---

## 1. The fifteen

**C1 — Industrial value-semantics library.** Open-source parser and ontology for compound engineering values. `M8 × 1.25` as diameter-and-pitch, `3/8-16 UNC` as three encoded facts, `10 ±0.2 mm` as value-plus-tolerance, `6061-T6` and `316 SS = A4 = 1.4401` as material identity, `IP67` as controlled vocabulary. Deterministic, exhaustively tested, no model in the hot path. Pint and Quantulum3 for industry, which ChatGPT explicitly named as an unfilled gap.

**C2 — The industrial parametric benchmark.** H2 in its narrowed form. Scores what ExtractBench doesn't: ETIM/ECLASS class assignment, compound-value normalization, cross-standard mapping correctness, supersession reasoning, and calibrated abstention with a full risk-coverage curve.

**C3 — Provenance-native attribute store.** Every attribute value is an immutable claim carrying source span, document revision, extractor version, timestamp and confidence. Conflicts between sources are resolved by explicit policy, not last-write-wins. Sits beside any PIM rather than replacing it. Git for product attributes.

**C4 — Taxonomy version-migration engine.** ETIM 11.0 lands 1 Dec 2026; ECLASS ships annually and just did 16.0. Class IDs change, mappings break, downstream ERP integrations silently rot. Diff two dictionary releases, compute the blast radius across a live catalog, generate the migration with evidence for every reclassification.

**C5 — Reviewer triage router.** The layer that decides what a human ever sees, optimized on reviewer-seconds-per-verified-attribute rather than model accuracy. Routes by expected value of review, not by confidence threshold.

**C6 — Supplier-side feed pre-flight.** The manufacturer runs their feed against each distributor's actual acceptance rules *before* submitting, and gets back a rejection-reason report with fixes. Flips the customer from the distributor to the party whose revenue is blocked by rejection.

**C7 — UNSPSC attribute bridge.** Fills the specific documented hole: UNSPSC gives you an eight-digit code and zero technical attributes, so parametric filtering is impossible without a bridge nobody ships.

**C8 — Adversarial catalog auditor.** Point it at a catalog that has *already* been enriched — by humans, by a BPO, by an incumbent's AI module — and it hunts for the poisoned records. Kimi's 100,000-incident queue, found and ranked by blast radius. Sells against work already paid for.

**C9 — HSN/GST classification with legal-grade provenance.** India-specific. A mandatory, government-defined taxonomy where misclassification is a tax exposure rather than a search-relevance problem. None of the seven funded AI-native entrants is near it.

**C10 — DPP / Asset Administration Shell compiler.** Datasheet in, machine-readable compliance record out, every field traceable. Rides the ESPR deadline schedule.

**C11 — Supersession and variant graph.** Temporal knowledge graph of manufacturer part-number lineage — supersessions, variants, equivalences. ChatGPT rated this research-only with no production-proven system.

**C12 — Vendor-neutral grounding layer.** Takes any extractor's output — LlamaExtract, Reducto, a raw VLM, an incumbent PIM's AI module — and produces word-level evidence boxes plus calibrated confidence for every field. Attacks the 46.43 number directly, from above the extraction layer.

**C13 — Revenue-weighted fill-rate analytics.** Productizes the 71%-overall / 34%-on-what-matters insight. Diagnostic, not corrective.

**C14 — Synthetic hard-case generator.** Manufactures the tail: degraded re-scans, fold-out pages, rotated tables, handwritten amendments, cross-page tables. Training and eval data for the cases that actually break systems.

**C15 — Schema archaeology.** Infers the semantics of a customer's legacy internal attribute dictionary from their existing populated data, so you map to *their* 2003 vocabulary without asking them to re-platform. Direct answer to "they would rather hire temps."

---

## 2. Scored

| # | Concept | Non-obv ×3 | Defens ×3 | C4-proof ×3 | Wedge ×2 | Demo ×2 | OSS ×2 | Depth ×1 | Why-now ×1 | **Total** |
|---|---|---|---|---|---|---|---|---|---|---|
| C8 | Adversarial catalog auditor | 10 | 7 | 9 | 9 | 10 | 7 | 8 | 8 | **146** |
| C12 | Vendor-neutral grounding layer | 9 | 7 | 8 | 9 | 10 | 8 | 9 | 10 | **145** |
| C6 | Supplier feed pre-flight | 8 | 8 | 7 | 10 | 8 | 6 | 6 | 7 | **130** |
| C15 | Schema archaeology | 9 | 8 | 7 | 8 | 8 | 5 | 9 | 6 | **129** |
| C3 | Provenance attribute store | 8 | 7 | 7 | 6 | 8 | 9 | 8 | 8 | **128** |
| C5 | Reviewer triage router | 9 | 6 | 10 | 8 | 7 | 5 | 7 | 6 | **128** |
| C4 | Version-migration engine | 9 | 7 | 6 | 9 | 7 | 7 | 6 | 10 | **128** |
| C1 | Value-semantics library | 7 | 6 | 8 | 9 | 6 | 10 | 8 | 5 | **126** |
| C2 | Industrial benchmark | 7 | 9 | 6 | 7 | 5 | 10 | 7 | 9 | **126** |
| C9 | HSN/GST India | 7 | 8 | 6 | 10 | 7 | 6 | 6 | 7 | **122** |
| C10 | DPP / AAS compiler | 6 | 7 | 5 | 8 | 7 | 7 | 7 | 10 | **115** |
| C11 | Supersession graph | 8 | 7 | 6 | 6 | 6 | 6 | 9 | 5 | **113** |
| C14 | Synthetic hard-case generator | 8 | 5 | 7 | 5 | 6 | 9 | 7 | 6 | **113** |
| C7 | UNSPSC bridge | 7 | 6 | 5 | 7 | 5 | 8 | 5 | 6 | **110** |
| C13 | Fill-rate analytics | 6 | 4 | 5 | 8 | 7 | 4 | 4 | 6 | **93** |

---

## 3. The thing the table doesn't show

**C8 and C12 are the same product seen from two ends, and that is the actual finding of this phase.**

C12 is an engine with a distribution problem — "we produce better evidence boxes than your current extractor" is a true statement that no catalog manager wakes up caring about. C8 is a wedge with an engine problem — "your catalog is already poisoned and we can prove it" gets you the meeting, but finding the poison *requires* exactly the grounding-plus-calibration machinery C12 describes.

Fused: **the product is a verification layer that audits product data it did not produce.** It ingests a catalog and its source documents, re-derives every attribute independently, grounds each value to a word-level span, calibrates its own confidence, and outputs a ranked list of records where the catalog and the evidence disagree — with the evidence attached.

That framing does several things at once:
- It sidesteps the extraction commodity trap. You are not competing with OpenAI's structured-output endpoint; you are checking its work, and every model that gets better makes your input better rather than making you redundant.
- It answers C4 head-on. You never process the clean 80%; you *find* the tail. Cost scales with the number of disagreements, not the number of SKUs.
- It makes the incumbents distribution partners rather than competitors. Akeneo, Salsify and Syndigo all now ship AI enrichment modules. None of them can credibly grade their own homework.
- It makes the benchmark (C2) a natural companion artifact rather than a separate project, and the value-semantics library (C1) a necessary internal component you can open-source without giving away the product.

C5's triage logic and C3's provenance model both fall out as components rather than competitors. C4, C6 and C9 remain genuinely separate businesses.

---

## 4. How the top three die

### C8 / C12 (fused) — the verification layer

**Most likely death: nobody wants an auditor.** You are selling a product whose core message is "the expensive thing you already bought is broken." The catalog ops manager who signed off on the current enrichment vendor is the person who must approve you, and your pitch is that their judgment produced 100,000 bad records. That is a political problem no amount of technical quality solves. The category graveyard is full of correct tools that made the buyer look bad.

The mitigation is real but unproven: sell to the party who *inherited* the mess rather than the party who created it — a new head of digital, a post-acquisition integration team, a distributor onboarding a supplier they don't trust yet.

**Second death: you can't ground what isn't there.** Auditing requires source documents. If the customer's catalog was enriched from documents they no longer have, or from supplier feeds that were themselves derived, there is nothing to point at. Your entire value proposition assumes a document trail that may not exist for the oldest, worst, highest-value records — which is precisely the tail C4 says matters.

### C6 — supplier feed pre-flight

**Most likely death: the acceptance rules are not public and not stable.** The product's whole value is knowing what Grainger, Sonepar or Moglix will reject before they reject it. Those rules are contractual, partly tacit, differ per supplier relationship, and change without notice. You would be reverse-engineering a moving target across dozens of trading partners, and every rule you get wrong produces a false pass — which is worse than no product, because the manufacturer trusted you and still got rejected.

**Second death: the buyer is too small and too many.** Distributors are few and large; suppliers are many and small. You'd be selling a low-ACV product to a long-tail market with a heavy per-customer integration cost — the exact shape Kimi described as a services business wearing SaaS clothing.

### C15 — schema archaeology

**Most likely death: it's a feature, not a company.** Inferring a customer's legacy vocabulary is a brilliant onboarding accelerant and a terrible standalone product. It runs once per customer, produces a mapping artifact, and then has nothing left to do. Recurring revenue would have to come from something else, which means the something else is the actual company and this is its first-week magic trick.

**Second death: it's unverifiable by construction.** You are inferring what a dead consultant meant in 2003. There is no ground truth, the customer cannot confirm it (that's why they hired you), and a confidently wrong inference propagates silently into every downstream mapping. It is the one concept on this list where the trust problem applies to your own output and you have no way to ground it.

---

## 5. What goes into Phase 4

The fused C8/C12 verification layer, with C1, C2, C3 and C5 as components and companion artifacts.

Open questions Phase 4 must answer rather than assume:
1. Who is the buyer who did *not* create the mess, and does that persona actually hold budget?
2. What happens to the audit when source documents are missing — is there a defensible fallback, or does the product just decline?
3. Where does the compounding asset live? Disagreement patterns across customers are shared and cross-standard; per-customer schema maps are not. The moat argument has to rest entirely on the former.
