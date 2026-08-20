# Phase 2 — Cross-Model Synthesis, Contradiction Matrix, Verification Pass

**Run date:** 16 August 2026
**Input:** `phase1-differentiated-research.md` (Gemini / ChatGPT / Kimi / Perplexity)
**Method:** analysis of Phase 1 plus live browsing for the verification pass. Everything below is either sourced to a page actually opened, or marked.

---

## 0. Headline

Four things changed the picture. In order of how much they should alter the plan:

1. **The Adobe/Akeneo acquisition is false.** Perplexity laundered SEO noise into a confident claim. Akeneo is independent and expanding.
2. **Grounding is measurably terrible in the wild.** The best system on the newest extraction benchmark scores **46.43 word-level grounding F1**, and 8 of 14 systems score exactly 0.00 because they return no evidence boxes at all. H1 stops being a hypothesis and becomes a number.
3. **ETIM and ECLASS have opposite licensing.** ETIM is free and open; ECLASS is licensed. No model mentioned this and it directly constrains the open-source strategy.
4. **The Gemini-vs-Kimi standards fight resolves — and both were right about different things.** That resolution is the whole product thesis.

---

## 1. Verification pass

### V1 — "Adobe acquired Akeneo" → **FALSE**

Perplexity claimed a definitive agreement 23 Jun 2026, close 1 Aug 2026, at ~$340M or ~$620M depending on which of its own sentences you read. It sourced this to puhulab and DEMG.ai.

What the record actually shows:

- Akeneo announced its **own acquisition of PricingHUB on 11 June 2026** via PR Newswire, described as extending its Product Cloud into pricing. A company being acquired by Adobe twelve days later does not issue that release.
- Akeneo shipped a **Summer Release 2026** in July, branded "Agentic Product Cloud," as an independent company.
- Adobe's 2026 acquisition is **Topaz Labs**, announced June 2026, image and video enhancement for Firefly and Creative Cloud. Acquisition trackers list one Adobe acquisition completed this calendar year, and it is Topaz.

**Verdict: fabricated.** Not "unconfirmed" — contradicted by the acquiring party's own newsroom.

**Consequences:**
- The open-source PIM position is **not vacant**. Akeneo is alive, independent, cash-deploying, and explicitly repositioning around agents. Any open-source play must beat a live Akeneo, not fill a hole Adobe left.
- Perplexity's entire section (a) drops to "unreliable until individually verified." **The rule that falls out: Perplexity's well-sourced items held, its badly-sourced item was fiction. Sourcing quality predicted truth exactly.** Apply that filter to the rest of its output.

### V1b — "Cinven acquires Salsify" → **TRUE**

Confirmed against primary sources: Salsify's own press release and Cinven's newsroom, both dated **22 July 2026**, terms undisclosed, subject to regulatory approval. Goodwin confirms it acted as Salsify's counsel. Salsify's own figures: 2,000+ customers, ~750 million products across 2,600 commerce destinations, 70,000+ active users.

Note the framing in the deal coverage: Cinven positions Salsify as **the data layer for agentic commerce**. Both the funded startups and the PE money are betting the same direction.

### V2 — ExtractBench → **REAL, and the gap is sharper than Phase 1 guessed**

Confirmed: arXiv 2607.29677, LlamaIndex, Apache 2.0, public HuggingFace dataset, open eval harness. 370 documents, 4,869 pages, 8 domains, 67 document types.

**Its domain breakdown, which is the decisive detail:**

| Domain | Docs |
|---|---|
| Finance | 145 |
| Energy | 98 |
| Government | 49 |
| Automotive | 27 |
| Supply chain | 20 |
| Healthcare | 15 |
| Legal | 10 |
| Real estate | 6 |

Its documents come from SEC and regulatory filings, government procurement and customs forms, court exhibits, tax forms (W-2, 1040, K-1, 1099-B), and Texas Railroad Commission energy filings.

**There is not one manufacturer datasheet, catalog page, or engineering drawing in it.** "Automotive" is vehicle valuation, not parts. "Supply chain" is logistics paperwork, not product specs.

**What it scores, precisely:**
- Unified value F1, deterministic matching, no LLM judge.
- Word-level grounding F1 (predicted box overlaps accepted evidence box at IoU 0.5) and page-level grounding F1.
- Measured cost per page.
- Null-correctness: a correct `null` on a genuinely blank field is credited; inventing a value for a blank field is penalized. Task challenge T3 explicitly targets over-extraction.

**What it does not score, and this is where H2 survives:**
- Any notion of **confidence or calibration**. Null-on-blank is not abstention — abstention is declining to answer a field whose value *is* present but ambiguous. There is no risk-coverage curve, no selective prediction axis.
- **Ontology selection.** The schema is handed to the system. The industrial problem is choosing the right class out of thousands and then filling its attributes — a retrieval problem ExtractBench never poses.
- **Compound-value semantics.** No M8 × 1.25, no 3/8-16 UNC, no 6061-T6, no 316 SS = A4 = 1.4401. Normalization is date canonicalization and whitespace collapsing.
- **Supersession, variants, cross-standard mapping.** Absent entirely.

**The number that matters most in this whole phase:** best-in-class word-level grounding F1 is **46.43** (LlamaExtract Agentic Plus). Second is 44.14. Reducto 43.30. And **eight of fourteen systems score 0.00 on both grounding metrics** because they return no boxes at all. Page-level tops out at 84.92 for the leader; most of the field is far below.

Read that against the PS's demand for "explainable outputs." The state of the art can tell you *which page* about 85% of the time at best, and *which words* less than half the time. That is the gap, quantified, three weeks old.

### V3 — Per-SKU enrichment cost → **PARTIALLY CORROBORATED, Gemini's labour rates inflated**

Published rate data I could actually open:

- Complex/technical SKUs (detailed specs, multiple images, multi-language): roughly **$0.80–$11.67 per SKU**, offshore at the low end, US onshore at the high end. Standard SKUs $0.33–$4.38. Simple $0.20–$2.33.
- 2026 labour rates: **offshore data-entry specialists $4–$6/hour**, nearshore LatAm/Caribbean $12–$18/hour, US or specialized BPO $20–$35/hour fully loaded.
- One vendor puts manual enrichment for a mid-sized distributor at **£250k–£400k/year in staff time**, and frames a 50,000-SKU catalog at 30–40 attributes as over 1.5 million data points.

**Gemini's $3–$12/SKU for full parametric mapping sits inside the published complex-SKU band, so that figure survives.** Its offshore analyst rate of $12–$25/hour does not — published offshore rates are $4–$6/hour, which is 2–4× lower. Any cost model built on Gemini's labour number overstates the savings by a wide margin.

**Caveat you must carry:** every one of these sources is a vendor marketing or SEO page, not a primary rate card or an audited study. They are better than model output and worse than evidence. Treat the band as directional.

**One free finding from that search, from a buyer's-guide page — third-party corroboration of H1 from the purchasing side:** the advice to distributors evaluating enrichment vendors is to ask *whoever can show provenance per attribute*, and to demand it **in the pilot, not the contract**. Same page argues the metric that predicts revenue is not catalog-wide completeness but **fill rate on required attributes in revenue-weighted categories** — noting a distributor can sit at 71% overall while being at 34% on the twelve attributes buyers actually filter by in its three best-selling categories.

That last sentence is a demo, a metric, and a sales pitch in one line. Keep it.

---

## 2. Consensus — claims two or more models reached independently

| Claim | Who | Weight |
|---|---|---|
| Provenance is mandatory; a value without a traceable source is rejected | ChatGPT ("no provenance → reject"), Kimi ("catalog operations lives on provenance… you have built a liability engine"), Gemini (compliance flags gate syndication) | **Load-bearing.** Three lenses, one conclusion. Now quantified by ExtractBench. |
| Pure LLM extraction is the wrong architecture | ChatGPT ("almost nobody uses pure LLMs… retrieval → reranker → LLM"), Kimi (models emit statistically probable schemas, not yours) | High |
| Abstention beats recall | ChatGPT (selective prediction "critical for production"), Kimi (a wrong safety-critical value is a lawsuit) | High |
| Schema change is the expensive operation | Gemini (Akeneo painful post-setup, Plytix can't represent the trees, Salsify needs third parties for ETIM/eCl@ss), Kimi ("they would rather hire temps than re-platform their taxonomy") | **High — and these two are saying the same thing from opposite ends of the transaction.** The vendor can't change the schema cheaply; the customer won't. |
| Units and compound values are underestimated and under-tooled | ChatGPT (Pint/Quantulum3 "need substantial extension"), Kimi (316 SS / A4 / 1.4401), Gemini (DIN metric vs imperial thread pitch colliding in NA ERPs) | High |
| The obvious hackathon ideas are obvious | Kimi's ten-item list overlaps the pre-declared banned list almost exactly | Confirms the filter; also confirms the room will be full of them |

---

## 3. Contradiction matrix

### C1 — Are ETIM/ECLASS real infrastructure or garbage nobody uses? **The one that decides the moat.**

**Gemini:** they are the load-bearing classification and exchange layer of industrial commerce.
**Kimi:** "UNSPSC, eCl@ss, and ETIM are all garbage-in-garbage-out standards that nobody actually uses consistently in the field. There is no universal schema."

**Resolution: Gemini is right about adoption, Kimi is right about population, and the collision of those two facts is the market.**

Evidence for adoption, from ETIM's own North American body and industry press:

- ETIM is used across **20+ countries in 17+ languages**. ETIM 10.0 (December 2024) defines **more than 5,600 product classes** across electrical, HVAC/plumbing, building materials, tools and marine.
- Distributors named as adopters: **Sonepar, Graybar, WESCO, Rexel, McNaughton-McKay.** Manufacturers named: **Schneider Electric, ABB, Siemens, Legrand, Prysmian, Rockwell, Eaton.**
- **IDEA** — jointly owned by NEMA and NAED — serves **80 of the top 100 US distributors** through IDEA Connector, and is deepening a collaboration with ETIM NA on syndicating ETIM-classified data.
- ECLASS 16.0 (28 November 2025) carries roughly **50,000 classes, 23,000 properties, 140,000 keywords, 31 languages**, and processed **over 155,000 change requests** for that release alone. Siemens Teamcenter supports it natively.

Standards nobody uses do not get 155,000 change requests, or eleven named multinationals, or NEMA's data body building syndication rails for them.

**But Kimi's deeper point stands and is more useful than his stated one.** ETIM North America's own marketing page describes the problem it exists to solve like this: every manufacturer sends data in a different format, with different attribute names, different structures, different completeness — and the distributor's team is the human translation layer in between. **The standard is universal; conformance to it is not.** That is exactly the gap a product lives in. Kimi mistook "the data in the field is inconsistent" for "the schema doesn't exist." Those are opposite conclusions from the same observation, and his is the wrong one.

**What this does to H3:** the mapping asset is real, because the target schemas are real, shared, versioned and mandated by trading partners. Kimi's no-network-effects attack assumed the asset was per-customer bespoke schemas. It isn't — or at least, it doesn't have to be.

### C2 — Can an LLM bridge two taxonomies?

**Kimi:** no, not without months of per-customer supervised fine-tuning, at which point your unit economics equal an offshore data-entry team.
**ChatGPT:** you never ask it to. Candidate retrieval → reranker → LLM, which "dramatically reduces errors." Few-shot mapping degrades past ~10,000 nodes *when used naively*.

**ChatGPT wins.** Kimi is attacking an architecture nobody competent would build. Retrieving 20 candidate classes out of 5,600 (ETIM) or 50,000 (ECLASS) is standard IR, not fine-tuning. The taxonomies are published, structured dictionaries with defined properties and value lists — ideal retrieval corpora.

**But Kimi's economics point survives in modified form:** retrieval solves *class selection*. It does not solve mapping a customer's dead-consultant 2003 material master onto anything. Those are two different problems and only one of them is cheap.

### C3 — Is unit normalization solved?

**ChatGPT:** "mostly production."
**Kimi:** "the hard part is normalization at the edge of long-tail entropy" — the single hardest thing.

**Both right, different referents.** Converting 10 mm to inches is production. Parsing `M8 × 1.25` as diameter-and-pitch rather than a multiplication, or knowing 316 SS = A4 = 1.4401 = your customer's internal code, is an ontology problem wearing a units costume. ChatGPT itself concedes this by calling out Pint and Quantulum3 as needing substantial extension and labelling that gap a product opportunity.

**This is the sharpest unclaimed technical wedge in the document.** Nobody ships an industrial value-semantics library.

### C4 — Where is the value, the head or the tail?

**Kimi's cost asymmetry, which nobody else addressed at all:** automating the easy 80% delivers almost nothing because those SKUs already have clean data. The value is in the bottom 20% — obsolete parts, single-source vendors, scanned PDFs, handwritten amendments. And the exception-handling infrastructure needed for that tail (review queues, confidence scoring, fallback workflows) may cost more than the labour it replaces.

**Uncontested by any other model, and it is the strongest argument against the entire category.** Nothing in Phase 1 refutes it.

**But notice what it actually implies.** If the tail is where value is, and the tail is where models are least reliable, then the product's core competence must be *knowing which items are in the tail and routing them correctly* — which is confidence, calibration and triage. That is H1 again, arriving from the economics side instead of the trust side. Kimi's best attack on the category is simultaneously the best argument for the specific thing H1 proposes.

Any Phase 3 idea that cannot answer C4 head-on should be cut.

---

## 4. Blind spots — what all four missed

**B1 — ETIM is free; ECLASS is not.** ETIM is an open, free-to-use international standard, published to the buildingSMART Data Dictionary. ECLASS is licensed: single-release licences, a multi-year concordance licence, membership tiers, REST API access. One German reference source states flatly that ECLASS is not free and openly available.

Not one model mentioned this, and it materially constrains the open-source play. An open cross-standard mapping asset can be built freely on the ETIM side; the ECLASS side has a licensing gate. **This would have detonated somewhere in Phase 4 if it had gone unnoticed.** It also suggests where the open contribution has the clearest legal room.

**B1b — a partial ETIM↔ECLASS mapping already exists** for electrical engineering products, with stated intent to expand it. So "nobody ships that mapping" is too strong. The unfilled hole is narrower and more specific: **UNSPSC gives a code and no attributes at all**, so anyone wanting parametric filtering from a UNSPSC-classified catalog must build the bridge themselves.

**B2 — nobody priced the reviewer.** All four analyzed extraction cost. None costed the human review loop — seconds per attribute decision, queue depth, escalation rate. If the product is a trust layer, **reviewer-seconds-saved-per-verified-attribute is the unit of value**, and it is unmeasured by every model and every benchmark. That is a metric you could define.

**B3 — everyone assumed the distributor is the customer.** The manufacturer sending non-conformant data is the party causing the problem *and* the party whose revenue is blocked when a distributor portal auto-rejects the feed. Gemini even noted that rejection creates immediate revenue delay for the manufacturer — then kept framing distributors as buyers. The supplier side may be the more motivated payer and is a completely unexamined wedge.

**B4 — nobody looked at India's mandatory taxonomy.** Gemini flagged Moglix being blocked by mismatched GST categories and then dropped it. **HSN classification is government-defined, nationally mandatory, and legally consequential** — misclassification is a tax exposure, not a search-relevance problem. None of the seven funded AI-native entrants in Perplexity's list is anywhere near it. Given where you are, this is the least contested wedge in the document.

**B5 — the funded-startup pattern is a signal nobody interpreted correctly.** Seven entrants, all seed or pre-seed, all positioning on "agentic commerce" and consumer/merchant catalogs. Perplexity called it "either a wide-open lane or evidence the industrial lane doesn't fund" and moved on. The Cinven/Salsify framing resolves it: PE is buying the consumer PXM layer at scale *because* agentic commerce is the thesis. The industrial lane isn't unfunded because it's bad — it's unfunded because it requires domain knowledge that generalist commerce founders don't have. That's a barrier, and barriers are the only thing that keeps a lane open long enough to matter.

---

## 5. Hypothesis status going into Phase 3

**H1 — the bottleneck is trust, not extraction. → PROMOTED from hypothesis to established finding.**
Three independent models, plus a buyer-side guide telling distributors to demand per-attribute provenance in the pilot, plus a hard number: 46.43 best-in-class word-level grounding, 8/14 systems at zero. Stop debating this and start building on it. It is now the floor, not the idea.

**H2 — own the benchmark. → NARROWED, ALIVE.**
Dead: "ship the first extraction benchmark." ExtractBench owns generic schema-guided extraction with grounding and cost. Alive, and now precisely specified — no existing benchmark scores industrial class assignment, compound-value semantics, cross-standard mapping correctness, supersession, or calibrated abstention with a risk-coverage curve. ExtractBench is Apache 2.0 with a public dataset and open harness, so it is a template and a citation, not just a competitor.

**H3 — the taxonomy graph is the moat. → SURVIVES, with one new constraint and one narrowed target.**
Kimi's attack fails because it aimed at per-customer schemas while the real asset is cross-standard. The standards are demonstrably real, adopted and mandated. New constraint: ECLASS licensing (B1). Narrowed target: the UNSPSC attribute hole and version-migration breakage, not a general ETIM↔ECLASS map that partly exists already.

**Still unverified, carry the flag:** Kimi's trust threshold (500+ verified extractions, <0.1% error on critical attributes, six-month shadow catalog) remains asserted from prior with no source. I could not corroborate it. It is directionally plausible and quantitatively unsupported — do not put those numbers in a pitch deck.

**Not checked this phase:** Syndigo/1WorldSync, the seven startup funding rounds, ETIM 11.0's 1 Dec 2026 date, the DPP registry milestones. Given V1, assume the poorly-sourced ones are suspect until opened.

---

## 6. Amendments to Phase 3

**Add to the banned list:**
- Anything demoed on the clean 80% of a catalog. If the demo SKUs have usable source data, the demo proves nothing (C4).
- Anything that requires the customer to change their taxonomy. Both Gemini and Kimi independently established that this is the one thing they will not do.

**Add a scoring criterion, weight ×3:**
- **Survives C4** — does this create value specifically on the long tail, where data is worst and models are least reliable, without an exception-handling cost that exceeds the labour it replaces? Any concept that only works on clean inputs scores zero here regardless of how it scores elsewhere.

**Three things to design toward, now evidence-backed rather than speculative:**
1. Word-level grounding as a first-class output, because the field's best is 46 and most of it is zero.
2. Calibrated abstention with a risk-coverage curve, because it is the one axis no benchmark scores and the one thing C4 says the economics depend on.
3. Reviewer-seconds-saved as the headline metric, because nobody measures it and it is what the buyer actually pays for.
