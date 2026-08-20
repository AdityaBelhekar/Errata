# Phase 1 — Differentiated Multi-Model Research

**Project brief:** AI-Powered Product Intelligence for Industrial Commerce
**Operating constraints:** No hackathon scoping. Series A infrastructure quality. Open-source repo that becomes a startup. No invented numbers — cite or mark [UNVERIFIED].
**Date of run:** 16 August 2026

---

## 0. Execution status and instruction-following audit

3 of 3 assigned models responded in full, plus the optional fourth (Perplexity). Nothing was blocked, gated behind login, or rate-limited. Four caveats materially affect how much weight each response carries:

- **Gemini ignored the "cite sources for every factual claim" instruction entirely.** Zero citations, zero URLs, zero uncertainty flags — and it produced confident dollar figures anyway. Every number from Gemini below is marked **[UNVERIFIED]**. This is precisely the failure mode the no-invented-numbers constraint was written to catch, and it fired on the first model.
- **Kimi explicitly chose not to search.** Its visible reasoning trace states: "I should answer this directly without tools… well-established in my training data." So it is pure prior with no evidence. Its two specific figures (<0.1% error threshold, 500+ verified examples) are **asserted, not sourced**. Its session banner also indicated a mid-generation downgrade to a faster non-thinking tier due to demand.
- **ChatGPT named papers and repos but gave no URLs** and did not appear to browse. Names are checkable in Phase 2; its production-vs-research verdicts are judgment, not measurement.
- **Perplexity did browse (101 sources) with dates and URLs, but leaned heavily on low-quality SEO aggregators** (puhulab, DEMG.ai, martini.ai, thecompanycheck, passportcraft, dppgrid) and contradicted itself inside a single table row. Flagged item-by-item below.

Nothing was truncated on the model side. No prompt-injection or instruction-like content was encountered in any page.

---

## 1A — Gemini: The Market and the Standards Layer

### Vendor landscape

Gemini segmented the market four ways: enterprise MDM / parametric (inRiver, Syndigo), syndication and digital shelf (Salsify), developer / open-source core (Akeneo, Pimcore), mid-market feed engine (Productsup, Plytix).

| Vendor | What it actually is | Pricing model claimed | Complaint claimed |
|---|---|---|---|
| inRiver | Graph-based PIM, deep parametric modelling for replacement parts and parent-child variants | SaaS by SKU-volume tier, users, endpoints — **$25,000–$90,000+/yr [UNVERIFIED]** | High total implementation cost; steep learning curve for non-technical data-entry teams |
| Akeneo | Open-source core moving to cloud PXM; strong manual-enrichment UI | Community free; Growth/Enterprise by active SKUs and channels | **Changing attribute schemas after initial setup is painful**; DAM is a repository, not a CDN |
| Salsify | Commerce/experience management, channel-requirement syndication, digital shelf analytics | Tiered by SKU volume + connected destinations + modules | Cost scales with channel count; **not natively strong on ETIM/eCl@ss mapping without third-party tools** |
| Syndigo | MDM + GDSN syndication, vendor onboarding, regulatory compliance | Enterprise custom quote incl. GDSN pool access | Legacy UI friction from mergers; variable integration-support responsiveness |
| Pimcore | Open-source MDM/PIM/DAM framework, highly extensible | Free core; enterprise per instance/cluster + support | Needs real developer resources; **no business-user-ready UI out of the box** |
| Productsup | Feed management, high-volume ETL and channel transformation | By data rows processed, export frequency, channels | **Overage fees on large datasets**; throughput degrades on massive batch runs |
| Plytix | SMB PIM, lightweight catalogs, CSV/e-comm exports | Flat/tiered monthly, unlimited seats on higher tiers | **No native support for ETIM/eCl@ss trees, multi-level parent-child, or custom API connections** |

**The load-bearing observation is not the pricing — it is that schema change is the expensive operation across every single vendor.** Akeneo is "cumbersome to modify attribute schemas after setup." Plytix cannot represent industrial taxonomy trees at all. Salsify needs third parties for ETIM/eCl@ss. That is a structural gap, not a UX complaint.

### Standards layer

Gemini split classification from exchange, which is the correct cut.

**Classification.** ETIM is a *flat, non-hierarchical* class model — a product gets a class, and the class carries predefined technical parameters with value lists and units. Dominant in European electrical, HVAC, plumbing, building materials. eCl@ss is a *4-level hierarchy*, ISO/IEC-aligned, covering both commercial and deep engineering attributes; Gemini claims it is a core input to the EU Digital Product Passport and to Industry 4.0 Asset Administration Shells. UNSPSC is a 4-level hierarchy maintained by GS1 US, dominant in North American e-procurement (Ariba, Coupa) and government spend analysis — and critically, **it classifies product type but defines no technical attributes at all.** GS1/GDSN handles global identity (GTIN) and logistics/physical accuracy via GPC. ISO 13584 (PLIB) and IEC CDD are the formal, computer-interpretable dictionary standards feeding CAD/PLM.

**Exchange.** BMEcat is the XML container (from the German BME) that actually transports ETIM or eCl@ss payloads supplier-to-distributor. cXML is Ariba's open transactional standard (POs, invoices, punchout) dominant in North America. OCI is SAP's proprietary HTTP GET/POST interface for pulling an external vendor catalog into an SAP requisition. Punchout is the workflow: the buyer browses the distributor's live catalog from inside their own ERP, builds a cart, and line items return as a requisition.

**Where the standards conflict — the most useful passage Gemini produced:**

1. **Structural mismatch.** ETIM's flat classes and eCl@ss's rigid 4-level hierarchy do not map cleanly onto each other.
2. **Version breakage.** eCl@ss version updates can *change class IDs*, breaking downstream ERP mappings. This is a live, recurring, dated failure — not a theoretical one.
3. **The UNSPSC hole.** UNSPSC gives an 8-digit code and no attributes. Any buyer wanting parametric filtering must cross-map UNSPSC to ETIM/eCl@ss attribute tables themselves. Nobody ships that mapping.
4. **Unit conflict.** DIN metric specs versus imperial thread pitch collide when European eCl@ss data is loaded into North American ERPs.

### Distributors and marketplaces

**Grainger** demands exhaustive structured attributes for faceted search (exact thread dimensions, material grades, duty ratings) and chokes on vendors supplying PDFs and unformatted spreadsheets. **McMaster-Carr runs a strict proprietary taxonomy — suppliers must convert standard PIM output into McMaster's custom schema.** **RS Group, Würth, Fastenal** need live ETIM-to-UNSPSC alignment across regions; Fastenal additionally needs exact inner-pack and master-case metrics plus GTINs because of its vending and inventory-managed locations.

India: **IndiaMART** is free-text long-tail listings with low attribute density, so discoverability is the pain. **Moglix** must map multi-vendor catalogs into *buyer-specific* taxonomies and gets blocked by mismatched GST categories, inconsistent UoM (metres versus rolls), and missing datasheets delaying enterprise RFQs. **Zetwerk** is custom manufacturing — catalog metadata must link to CAD, tolerances, and material test certificates. **Udaan and TradeIndia** are non-digitised SMB suppliers with high attribute error rates.

### Enrichment cost — every figure [UNVERIFIED], no source given

| Activity | Claimed cost |
|---|---|
| Basic dedup / formatting | $0.50 – $1.50 per SKU |
| Full parametric + ETIM/eCl@ss mapping | $3.00 – $12.00+ per SKU |
| CAD / blueprint interpretation | $15 – $40+ per SKU |
| Offshore catalog analyst | $12 – $25 per hour |
| Domain-expert catalog lead | $30 – $50 per hour |
| LMM + OCR draft compute | $0.05 – $0.20 per document page |
| Blended human-in-the-loop saving vs fully manual | 40% – 65% |

**Treat every one of these as fiction until verified.** They are suspiciously round, internally consistent in a way real market data is not, and came from a model that was explicitly told to cite and chose not to. Three of them are decision-critical for the business model, which is why they go into the Phase 2 verification pass.

### Regulatory pressure

**ESPR / DPP** requires a machine-readable record covering material provenance, environmental impact, recycled content, durability and disassembly. Gemini's claim: PIM systems will have to hold structural links to eCl@ss or Asset Administration Shell schemas to serve it. **REACH / RoHS** requires SVHC declarations tracked at component level, and **a missing compliance flag blocks downstream B2B catalog syndication outright.** **SCIP** requires direct submission to ECHA for SVHCs above 0.1% w/w, forcing PIM platforms to maintain ECHA-shaped XML exports or APIs. **GS1 data-quality frameworks** mean non-compliant vendor feeds are auto-rejected at distributor portals, creating immediate revenue delay for the manufacturer.

---

## 1B — ChatGPT: The Technical State of the Art

Opening framing, which is the right one: this is not invoice OCR. It requires **jointly** solving document understanding, information extraction, ontology alignment, entity resolution, normalization, and uncertainty estimation. Its claim about how real systems are built: *"Most commercial systems (Amazon, Grainger, RS Components, DigiKey, McMaster, Siemens, Schneider, etc.) combine classical IR, rule systems, and increasingly LLMs rather than relying on a single foundation model."*

Reference pipeline it laid out:

    Sources (supplier PDFs, CAD drawings, product pages, ERP exports, Excel catalogs, legacy scans)
      -> Document AI (layout + OCR + tables)
      -> Semantic parsing (attributes + tables + dimensions)
      -> Ontology mapping (schema induction)
      -> Normalization (units / materials / thread specs)
      -> Entity resolution (MPN matching, variants)
      -> Verification (retrieval + attribution)
      -> Human review (only uncertain cases)

### 1. Document AI for datasheets — "the most mature part of the pipeline"

**LayoutLM v1/v2/v3** (token embedding + 2D bounding boxes + image embedding, instead of text only): strong on forms, invoices, manuals, structured technical PDFs; **weak on large engineering tables, nested tables, rotated diagrams, CAD drawings.** **DocFormer** fuses text/vision/layout through shared attention, more robust on noisy scans, still fails on dimension drawings and exploded diagrams. **DiT** is a document-image-only pretrained backbone, good for page understanding and segmentation, often used as a backbone. **Donut** is OCR-free (PDF image -> transformer -> JSON), elegant and avoids OCR error, but **large engineering PDFs exceed its context** and it is poor on 100-page catalogs and tiny engineering fonts. **Nougat** targets scientific PDFs and formulas, largely irrelevant here. **MinerU** is the recent open-source parser gaining adoption on complex, multilingual documents.

OCR: **PaddleOCR** is called the production favourite (multilingual, engineering fonts, tables). **TrOCR** beats Tesseract. **EasyOCR** is less accurate. **Tesseract** needs preprocessing and is not SOTA.

Tables: **Table Transformer / TATR** (DETR-based row, column, cell detection) is the "excellent baseline." **PubTables-1M** (Smock et al.) was the step change in data. **TableFormer** competitive. **CascadeTabNet** good on scans. **DeepDeSRT** older but still cited. **ChatGPT's verdict: table extraction "is still surprisingly difficult" — a flat table is fine, nested headers break most systems.**

Explicit remaining failure modes: multi-column catalog pages (the model merges the left and right product into one record), floating callouts that must be associated with a drawing, **dimension drawings needing OCR plus geometry plus association, where "Vision LLMs help but reliability remains mediocre,"** engineering symbols (persistent OCR errors), rotated tables, and fold-out pages ("almost impossible automatically").

Production verdict as stated: OCR yes, layout yes, basic tables yes — "mostly solved." Still failing: dimension diagrams, nested engineering tables, callout linking, exploded mechanical drawings.

### 2. Attribute extraction and schema induction — "arguably the hardest ML problem"

Canonical example: Supplier A says *Rated Voltage*, B says *Operating Voltage*, C says *Nominal Supply Voltage*; the target schema wants one *Voltage*. Now scale that to **~15,000 attributes across ~300 categories.** Its conclusion: "impossible to solve with rules."

Pipeline: stage 1 NER-style span extraction, stage 2 ontology mapping, stage 3 schema completion. Sequence labelling with BERT / RoBERTa / DeBERTa is "still strong." LLM span extraction is "very common today." Few-shot taxonomy mapping with modern LLMs is "surprisingly good" on individual mappings — **but degrades into hallucination and nearest-neighbour error once the taxonomy exceeds ~10,000 nodes.**

**The single most important sentence in the whole response, and the one that should shape the architecture: "Almost nobody uses pure LLMs. Instead: candidate retrieval -> reranker -> LLM. This dramatically reduces errors."**

Schema induction (discovering that *Ingress Protection* and *IP Rating* are the same concept) via embedding clustering, contrastive learning, or LLM clustering is called **"research frontier… still immature."** Ontology-aware embeddings with GNNs: "still mostly research."

### 3. Entity resolution — "very mature research area"

Canonical case: Bosch **0 281 002 401** vs **0281002401** vs a distributor SKU. Pipeline: blocking to cut comparisons (same manufacturer, voltage, family) -> embedding retrieval (SBERT, BGE, GTE) -> cross-encoder verification -> graph clustering into same-product components. Variants need parent SKU plus variant attributes. **Supersessions (old MPN -> new MPN) need a temporal knowledge graph and are "still difficult."** Production systems combine fuzzy matching, manufacturer-specific rules, embeddings and cross-encoders — explicitly "not LLM-only."

### 4. Unit and value normalization — "one of the most underestimated engineering challenges"

**M8 × 1.25** is diameter × pitch, **not multiplication.** **3/8-16 UNC** encodes diameter, thread count and standard. **10 ±0.2 mm** needs value and tolerance as separate fields. **IP67** is non-numeric and needs a controlled vocabulary. **6061-T6** is a material grade needing an ontology. The correct pipeline is regex -> grammar parser -> ontology lookup -> unit converter, and the blunt verdict: **"LLMs alone are unreliable."** Existing libraries (Pint, Quantulum3) "need substantial extension for industrial engineering." **That gap is a product opportunity.**

### 5. Grounding and hallucination control — "the biggest production concern"

Its rule, stated as an imperative: every extracted value carries page, bounding box, token span. **"No provenance -> reject."** Constrained decoding to JSON schema plus enums plus regex plus units reduces formatting errors but does not guarantee factual correctness. Retrieval verification (extract -> retrieve supporting text -> verify -> accept) is "very effective." Self-consistency voting is useful but expensive. Calibration via temperature scaling, Platt scaling, conformal prediction. Selective prediction — emitting *Unknown* rather than guessing — is "critical for production," with the key economic insight: **"often increases end-to-end precision far more than squeezing out another point of recall."**

### 6. Evaluation — and this is where the gap is

Existing: **MAVE** (Amazon) for attribute-value extraction. **WDC Product Data Corpus** for entity and schema matching. **AE-110K** for attribute extraction ("less diverse"). **WDC Product Matching Benchmark** for entity resolution. Adjacent: FUNSD (forms), CORD (receipts, "not industrial"), DocVQA, InfographicVQA, PubTables-1M, ChartQA.

**Read that list against the brief. Every single one is consumer-retail or generic-document.** There is nothing for industrial parametric data, nothing for ETIM/eCl@ss mapping, nothing for unit normalization, nothing for supersession, nothing that scores abstention or provenance. ChatGPT names "benchmarking multilingual product catalogs" as a gap where "public resources remain limited," and in its own production-versus-research table, these rows have **no production-proven entry at all**: dimension-drawing understanding, callout-to-geometry linking, ontology induction, supersession prediction, end-to-end autonomous enrichment.

Its production-versus-research table, verbatim in substance:

| Area | Status |
|---|---|
| OCR | Production proven |
| Layout analysis | Production proven |
| Table detection | Production proven |
| Simple table extraction | Production proven |
| Multi-page reasoning | Partial |
| Dimension drawing understanding | Research only |
| Callout-to-geometry linking | Research only |
| Ontology induction | Research only |
| 10k+ attribute mapping | Partial |
| Entity matching | Production proven |
| Variant reasoning | Partial |
| Supersession prediction | Research only |
| Unit normalization | Mostly production |
| Hallucination control | Emerging |
| Confidence calibration | Partial |
| End-to-end autonomous enrichment | Research only |

Its forward call: the winner is not one giant multimodal model, it is a **modular neuro-symbolic pipeline** — document foundation model, retriever narrowing thousands of ontology nodes to dozens, LLM extractor under constrained schema with span provenance, symbolic normalization for units and grades, graph-based entity resolution over MPNs, variants and supersessions, and a verifier checking every value against retrieved evidence with calibrated confidence.

---

## 1C — Kimi: The Adversarial Teardown

Kimi delivered. It also leaked its full reasoning trace, which is itself informative: it decided the answer needed no evidence, and planned to "avoid naming specific companies where possible" — then named them anyway.

### 1. Failure modes

**The 95% accuracy death spiral.** 95% sounds like a win in a deck. On 2M SKUs it is 100,000 poisoned records. A single wrong unit-of-measure — selling a case as an each — does not merely annoy a customer: it corrupts margin analytics, breaks punchout cXML feeds into customer ERPs, and triggers phantom inventory allocations. *"You don't have a 95% solution. You have a 100,000-incident queue."*

**Schema hallucination.** The model extracts into a statistically probable approximation of a taxonomy, not yours. Your schema has *Thread Standard: NPT* and *Pressure Class: 150 PSI*; the model emits *Connection Type: Threaded* and *Max Pressure: 150* because that is what the open internet looks like. Faceted search breaks, procurement rules misfire, governance spends six months hunting the drift.

**Confident-wrong on safety-critical fields.** Material certifications, temperature ratings, voltage tolerances. Models are trained on marketing copy, not engineering datasheets. A wrong circuit-breaker spec is a fire, a lawsuit, a terminated contract — *"and the model will tell you it is 98% confident while doing it."*

**Cascade failure from integration fragility.** A supplier reformats a PDF, a site adds a cookie banner, a table spans a page break and becomes an image — the pipeline does not fail gracefully, it emits plausible garbage that propagates to ERP, marketplace listings and customer-facing search before anyone notices.

**Temporal drift without provenance.** A supplier updates a spec; your record is stale with no audit trail of when extraction happened or from which document revision. *"Catalog operations lives on provenance. Without it, they cannot defend a spec to an angry customer or a regulatory auditor. You have built a liability engine."*

### 2. Why it is not solved

*"The hard part was never extraction. The hard part is normalization at the edge of long-tail entropy."*

Its example is better than anything the other two produced: **316 SS**, **A4 Stainless** and **1.4401** are the same material, and must normalize to *your* preferred term because your ERP's material master was configured in 2003 by a consultant who is now dead.

It then directly contradicts Gemini: **"UNSPSC, eCl@ss, and ETIM are all garbage-in-garbage-out standards that nobody actually uses consistently in the field. There is no universal schema."** It argues an LLM cannot bridge two bespoke taxonomies without months of per-customer supervised fine-tuning, at which point unit economics look identical to an offshore data-entry team.

**Cost asymmetry — the sharpest point in the entire phase.** Automating the easy 80% delivers almost no value, because those are high-volume items that already have clean data. The value is in the bottom 20%: obscure maintenance parts, obsolete SKUs, single-source vendor items — scanned PDFs, handwritten amendments, non-standard units. And **the cost to automate that tail exceeds manual entry, because the exception-handling infrastructure (review queues, confidence scoring, fallback workflows) is more expensive than the labour it replaces.**

### 3. What catalog ops will refuse

A human gate on **every single write.** "Not a sample. Not a confidence threshold. Every. Single. Write."

Refused outright:
- **Batch auto-publishing.** They have been burned by overnight scripts turning 4,000 SKUs into unsearchable sludge.
- **Black-box confidence scores.** *"They know that '92% confident' is a meaningless number when the 8% error rate clusters on the most expensive, most safety-critical SKUs."*
- **Schema overrides.** If you cannot map to their existing attribute dictionary — the one powering faceted search, punchout catalogs and customer-specific pricing matrices — **"they would rather hire temps than re-platform their taxonomy."**
- **Anything that does not understand UoM and pricing context.** Enrich "Box of 10" as "Each" and *"they will catch this once, and you will never get another meeting."*

Trust threshold **[ASSERTED, unsourced]**: 500+ manually verified extractions **on their own SKUs**, <0.1% error on critical attributes (price, UoM, material, safety rating), before they let it touch even non-critical attributes — then a shadow catalog running in parallel for six months. *"Most AI vendors don't survive that trial."*

### 4. The ten obvious hackathon projects to avoid

1. Chat-with-your-catalog RAG bot — works on three curated SKUs, fails on real industrial part numbers.
2. Auto-generate product descriptions — marketing fluff; industrial buyers search by attribute, not narrative.
3. Visual search for spare parts — confuses a 3/4-inch hex bolt with a 5/8-inch hex bolt because training data was consumer products.
4. PDF spec-sheet extractor — dies on scans, multi-page tables, engineering drawings.
5. Duplicate SKU detector — finds exact string matches, misses the same product under three supplier part numbers with incompatible units.
6. Auto-attribute tagger — emits *Material: Rubber* when the spec requires Viton fluoroelastomer.
7. Competitive price scraper — scrapes list prices unrelated to the negotiated contract prices driving ~90% of industrial volume.
8. B2B recommendation engine — uses co-occurrence when industrial procurement is driven by BOM compatibility.
9. Natural-language procurement assistant — "I need a valve" when procurement needs 12 precise parameters; *"a conversational interface adds friction, not removes it."*
10. Universal schema mapper — maps the common top 20% and **dumps the rest into a catch-all text field, creating more technical debt than it solves.**

**This list overlaps almost perfectly with the pre-declared banned list.** Independent convergence: the instinct was right, and it also proves the obvious ideas are *very* obvious.

### 5. The no-moat case

- **Commoditized extraction.** *"If your entire product is 'we use LLMs to extract data,' you are a feature, not a company."* OpenAI ships a structured-extraction endpoint and vaporizes the core value proposition.
- **No data network effects.** Customer A's hydraulic-fitting taxonomy is useless for Customer B's electrical connectors. *"You are not building a proprietary dataset; you are building a services business with recurring re-training costs."* **This is a direct frontal attack on hypothesis H3.**
- **Incumbents.** inRiver, Salsify, Akeneo and the ERP giants have distribution, integrations and trust. They bolt on LLM modules at $5/seat/month. You cannot out-sell or out-integrate them.
- **The dirty-data moat works against you.** Decades of idiosyncratic data is not a problem you solve for them, it is a barrier protecting their existing workflows. Their data is so bespoke your generalist tool needs massive customization, which destroys margin.
- **Asymmetric switching costs.** A customer swaps your enrichment tool for a competitor's in a weekend. They cannot swap their catalog taxonomy without a multi-year ERP migration. *"You are fighting a battle on their turf with no leverage."*

Closing: *"You are building a services company that uses LLMs as labor arbitrage. The moment the arbitrage window closes — when API costs rise or when offshore data entry costs fall — you are dead."*

---

## 1D — Perplexity: Recency Sweep (Aug 2025 – Aug 2026)

This is the phase that most changes the picture, and also the one with the weakest sourcing. **Everything here post-dates my own knowledge and none of it has yet been independently confirmed.** Items flagged for the Phase 2 verification pass.

### (a) Consolidation — the incumbent landscape Gemini described may no longer exist

| Event | Date claimed | Sourcing quality / status |
|---|---|---|
| **Adobe acquires Akeneo** | Definitive agreement 23 Jun 2026; close reported 1 Aug 2026 | **CONTRADICTS ITSELF.** Deal value cited as ~$340M in June reporting and ~$620M in August. Explicitly "not confirmed by Adobe IR." Sourced to puhulab and DEMG.ai — both low quality. Claim: Akeneo capabilities embedded into Adobe Commerce by Q1 2027; FTC clearance reported, EU DMA review expected by Oct 2026. **MUST VERIFY AGAINST ADOBE IR / PRESS.** |
| **Cinven acquires Salsify** | Announced 22 Jul 2026, terms undisclosed | Partly sourced to Goodwin Law (deal counsel) — a reasonable signal. Expected to close "in the coming weeks," subject to regulatory approval. |
| **Syndigo acquires 1WorldSync** | Announced 3 Sep 2025 | **Best-sourced item here:** Syndigo newsroom plus Cooley, Kirkland & Ellis, Summit Partners. Claimed >$3.5B combined entity. Syndigo backed by Summit Partners, TJC, Battery Ventures. |
| inRiver | No 2025–26 deal found | Most recent ownership change remains THL majority investment, May 2022 |
| Productsup | No new equity round found | Still Nordwind Capital and Bregal Milestone; partnership with Syndigo Feb 2025 |
| Plytix | No new round found | Last disclosed: Series A, $8.7M, Sep 2022 |
| Pimcore | No deal found | Partner ecosystem activity continues |

Perplexity's own flag: *any analysis relying on pre-2025 ownership or valuation for Akeneo or Salsify is now outdated; pre-Sep-2025 analysis of Syndigo predates the 1WorldSync combination.*

**If the Adobe/Akeneo item holds, it is the single most strategically important fact in this entire phase.** The leading open-source PIM would now be Adobe-owned. That directly conditions the open-source strategy: it either vacates the open-source-PIM position entirely, or means competing against an Adobe-funded one.

### (b) AI-native entrants — and the pattern that matters more than the list

| Startup | Focus | Round / date |
|---|---|---|
| Catalog (SF) | Making merchant catalogs "AI-agent ready" — normalization, enrichment, distribution to AI shopping agents | $3M pre-seed, 3 Apr 2026, led by Acrew Capital |
| Naratix (Bucharest) | AI automation for e-commerce product data enrichment and catalog management | €1M seed, 10 Jun 2026, Early Game Ventures |
| Nudge (NYC / Bengaluru) | Agentic commerce; enriches catalogs and metadata so AI assistants can discover SKUs | $1.1M pre-seed, Jul 2026, led by s16vc |
| ReFiBuy | "Commerce Intelligence Engine" — ingest, enrich, distribute, monitor catalogs | $2M seed, Mar 2025 |
| Cernel (Denmark) | AI-native e-commerce data management, catalog enrichment for agentic commerce | $4.7M seed, 25 Feb 2026, led by Seed Capital |
| ShopAgentic | Product data readiness for AI agents | €1.9M pre-seed, Jun 2026, May Ventures + Greenfield |
| CommerceClarity | Composable AI OS for e-commerce, automates catalogs and enrichment | €2.7M, 13 Nov 2025 |

Incumbent feature launches in the same window: **Productsup "AI Enrich" (21 May 2026)**, **Mirakl "Agentic Activation" (29 Apr 2026)**.

**The pattern: every funded entrant is positioning around "agentic commerce" and consumer/merchant e-commerce, not industrial parametric data.** Seven companies, all pre-seed to seed, all chasing legibility of catalogs to AI shopping agents. Nobody in this list is doing ETIM/eCl@ss, engineering datasheets, or verification. That is either a wide-open lane, or evidence that the industrial lane does not fund. Phase 2 has to decide which.

### (c) Benchmarks — hypothesis H2 needs immediate revision

| Benchmark | Date | What it does |
|---|---|---|
| **ExtractBench** (arXiv) | v1 31 Jul 2026, v2 5 Aug 2026 | 4,869 pages, 370 enterprise documents, 8 domains, 67 document types. **Scores value accuracy, record completeness, grounding, and cost.** Reports LlamaExtract Agentic Plus leading on all three. |
| **LongExtractionBench** (micro1) | Jun 2026 | Long, table-heavy document extraction to JSON-like schemas; precision, recall, leaf accuracy across systems |
| **OmniDocBench** (updated leaderboards) | Apr 2026, Jul 2026 | Text extraction, table parsing, formula recognition, layout understanding over 1,100+ real documents. GLM-OCR leads at 94.62 (Apr 2026); Kimi K3 reported 91.1% (Jul 2026) |
| **RD-TableBench** (Reducto) | 2026 | Complex table parsing; Reducto reports 90.2% average table similarity |

**This is the most important correction in Phase 1.** H2 assumed "there may be no serious open benchmark for industrial product-data enrichment." That is now only half true. Generic **schema-guided enterprise document extraction with grounding as a scored axis already exists** (ExtractBench), and it is three weeks old. The naive version of H2 — "ship the first extraction benchmark" — is dead on arrival.

What still does not exist, and this is where H2 survives in narrowed form: none of these four benchmarks touch **industrial parametric semantics** — no ETIM/eCl@ss class assignment, no unit and compound-value normalization (M8 × 1.25, 3/8-16 UNC, 6061-T6, 316 SS = A4 = 1.4401), no supersession or variant reasoning, no cross-standard mapping correctness, and critically **no scoring of abstention** — ExtractBench scores grounding and completeness, but not whether a system correctly refused to answer. Phase 2 must verify the ExtractBench paper directly to confirm this reading before H2 is rewritten.

### (d) Standards changes — all live, all in the last 12 months

**ETIM**
- **ETIM 11.0 release planning approved, 12 Jan 2026.** Change-request deadline 30 Jun 2026; **final release planned 1 Dec 2026.** (ETIM International)
- **ETIM xChange v2.0 released, 27 Nov 2025** — **adds environmental LCA/EPD fields, packaging material data, and MDX media type codes.** (ETIM International)
- **ETIM MC Guidelines v2.0, 9 Dec 2025** — restructured rules aligned to a future bi-annual ETIM MC cycle; ETIM MC expected early 2027 alongside ETIM 11.

**eCl@ss**
- **eCl@ss Release 16.0, 27 Nov 2025** — official release across languages and formats.

**GS1 / GDSN**
- GS1 General Specifications v26, Jan 2026.
- GDSN 3.1.32 live 24 Aug 2025.
- GDSN 3.1.35 live 16 May 2026 (documentation published 19 Mar 2026).
- GS1 Benelux FMCG and Foodservice data model 3.1.36 go-live 22 Aug 2026 (published 15 Jun 2026).

**EU DPP / ESPR**
- ESPR, Regulation (EU) 2024/1781, entered into force 18 Jul 2024.
- First ESPR and Energy Labelling Working Plan adopted 16 Apr 2025 — sets priority product groups for delegated acts.
- Earliest delegated-act effect date 19 Jul 2025.
- **DPP Registry operational milestone 20 Jul 2026; framework act July 2026.** (single-market-economy.ec.europa.eu — the one genuinely primary source in this section)
- **Iron and steel delegated act expected Q4 2026 adoption; DPP compliance approximately 18 months after adoption.**
- **Batteries DPP: 18 Feb 2027 (firm)**, under the separate Battery Regulation — the first mandatory DPP.

**Two things follow.** First, the ETIM xChange v2.0 addition of LCA/EPD and packaging-material fields on 27 Nov 2025 is the standards layer visibly bending to meet DPP. That is a concrete, dated convergence of the regulatory driver and the taxonomy driver, and it is a much stronger "why now" than anything Gemini offered. Second, **ETIM 11.0 landing 1 Dec 2026 and eCl@ss 16.0 having landed 27 Nov 2025 means the version-migration breakage Gemini described is not hypothetical — it is scheduled.** Every distributor mapped to ETIM 10 has a migration ahead of them.

---

## Phase 1 closing notes

**What failed or needs flagging:**
- Gemini: no citations at all, contrary to explicit instruction. All cost and pricing figures unverified.
- Kimi: refused to search; all figures asserted from prior. Downgraded to a faster model tier mid-generation.
- ChatGPT: no URLs; paper and repo names only. No evidence of browsing.
- Perplexity: browsed 101 sources but many are SEO aggregators; self-contradicted on Akeneo deal value; the (d) section rendered progressively and required direct DOM reads to capture in full.
- No content was truncated on the model side. No prompt-injection or embedded-instruction content was encountered on any page.

**The three most decision-critical claims, queued for the Phase 2 verification pass:**
1. **Adobe acquired Akeneo** — verify against Adobe investor relations or Akeneo's own press release. Determines whether the open-source-PIM position is vacant or Adobe-occupied.
2. **ExtractBench (arXiv, Jul–Aug 2026) scope** — verify whether it scores abstention and whether any industrial/parametric domain is included. Determines whether H2 lives, narrows, or dies.
3. **Per-SKU enrichment cost** — find a published price from an actual catalog-ops vendor or BPO. Gemini's $3–$12 per SKU for parametric mapping is currently the entire basis of the cost argument, and it is uncited.

**Preliminary read on the three hypotheses, to be attacked in Phase 3:**
- **H1 (trust, not extraction) — strongly corroborated, independently, by all three models.** ChatGPT: "no provenance -> reject," abstention beats recall. Kimi: human gate on every write, provenance is what catalog ops lives on, "92% confident is a meaningless number." Gemini: compliance flags gate syndication. This is the load-bearing consensus of Phase 1.
- **H2 (own the benchmark) — wounded.** ExtractBench already occupies generic schema-guided extraction with grounding. Survives only if narrowed hard to industrial parametric semantics plus abstention scoring. Verify before committing.
- **H3 (taxonomy graph is the moat) — directly and specifically attacked by Kimi** ("no data network effects… Customer A's hydraulic-fitting taxonomy is useless for Customer B's electrical connectors"). But Kimi's attack assumes the asset is *customer-specific schemas*. It does not address a *cross-standard* mapping asset (ETIM ↔ eCl@ss ↔ UNSPSC ↔ IEC CDD), which is shared, not bespoke — and which the standards bodies themselves demonstrably do not ship, per Gemini's UNSPSC-hole point. That is the crack in the no-moat argument and the place Phase 2 should push hardest.

*End of Phase 1. Awaiting "continue" for Phase 2 — cross-model synthesis, contradiction matrix, blind-spot list, and the three-claim verification pass.*
