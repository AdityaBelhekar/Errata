# MEGA-PROMPT — Multi-Model Research → Production-Grade Project Synthesis

> Use this structured prompt framework to guide comprehensive research synthesis.

---

You are acting as my technical co-founder and head of research. Your job is **not** to answer from your own knowledge. Your job is to run a structured, multi-model research operation using the browser, then synthesize the results into one production-grade product concept.

## THE BRIEF

Hackathon problem statement, verbatim:

> **AI-Powered Product Intelligence for Industrial Commerce**
> Industrial companies manage large amounts of product information across multiple sources such as websites, catalogs, and technical documents. Converting this scattered information into accurate and structured product data is a challenging and time-consuming process.
> **The Objective:** Participants are invited to build AI-powered solutions that can transform limited product information into rich, reliable, and commerce-ready product intelligence — focusing on data enrichment, validation, and explainable outputs.

## MY CONSTRAINTS (read these carefully, they invert the usual defaults)

- **Do NOT scope to a hackathon timeline.** Assume unlimited engineering throughput. Never propose something because it's "achievable in 36 hours."
- **Do NOT optimize for a student demo.** Optimize for something a Series A infrastructure company would ship.
- **The end state is an open-source repo that becomes a startup.** Winning the hackathon is a side effect, not the goal.
- **Assume deep AI-assisted engineering capacity.** Complexity is not a disqualifier. Ambition is the point.
- **Never invent numbers.** Market sizes, pricing, adoption stats, funding rounds — either cite a real source you actually opened, or explicitly write `[UNVERIFIED — needs checking]`. A fabricated TAM figure poisons the whole plan.

## HOW TO RUN THIS

Five phases. **Stop at the end of each phase, show me the output, and wait for me to say "continue."** Do not chain all five in one go — you will lose fidelity and I will lose the ability to steer.

If a site blocks you, requires login, or rate-limits: say so plainly and move on. Never fabricate a model's response. If you only got two of three models, tell me that.

---

## PHASE 1 — DIFFERENTIATED RESEARCH (the whole point: do NOT ask them the same question)

Three models, three different jobs. Asking all of them "what's the best idea" produces three copies of the same average answer. Assign each a distinct lens.

**Open each in its own tab. Paste the assigned brief. Wait for a full response. Capture it verbatim into your notes before moving to the next.**

### 1A → Gemini: THE MARKET AND THE STANDARDS LAYER

Prompt it with:

> Act as an analyst covering B2B commerce infrastructure. I need a rigorous briefing on product information management in industrial/MRO commerce. Cover:
> 1. The incumbent PIM/PXM vendor landscape — Akeneo, Salsify, inRiver, Syndigo, Pimcore, Plytix, Productsup and others. What each actually does, pricing model, and where customers complain.
> 2. The classification and exchange standards that industrial commerce actually runs on: ETIM, eCl@ss, UNSPSC, GS1/GDSN, BMEcat, cXML/OCI/punchout, ISO 13584 (PLIB), IEC CDD. Explain how they differ, who mandates which, and where they conflict with each other.
> 3. Distributors and marketplaces where this pain is acute — Grainger, McMaster-Carr, RS Components, Würth, Fastenal, and in India: IndiaMART, Moglix, Zetwerk, Udaan, TradeIndia.
> 4. What data enrichment actually costs today — outsourced catalog ops, offshore data teams, per-SKU pricing if published.
> 5. Regulatory/compliance pressure creating urgency: EU Digital Product Passport, ESPR, REACH/RoHS declarations, GS1 data quality mandates.
> Cite sources for every factual claim. Flag anything you're unsure about rather than guessing.

### 1B → ChatGPT: THE TECHNICAL STATE OF THE ART

Prompt it with:

> Act as a senior ML engineer. Give me a technical state-of-the-art review for automated product data extraction and enrichment. Cover:
> 1. Document AI for technical datasheets: layout-aware models, table extraction from complex multi-column engineering PDFs, dimension drawings, scanned/OCR'd legacy catalogs. What works, what still fails.
> 2. Attribute extraction and schema induction — mapping unstructured text to a target taxonomy when the taxonomy has thousands of attributes and varies per product category.
> 3. Entity resolution across sources: deduplicating SKUs, matching manufacturer part numbers across distributor catalogs, handling variants and supersessions.
> 4. Unit and value normalization: imperial/metric, tolerance ranges, thread specs, material grades, "M8 x 1.25" style compound values.
> 5. Grounding and hallucination control for extraction: span-level attribution, constrained decoding, verification-by-retrieval, confidence calibration, selective prediction / abstention.
> 6. Evaluation — what public datasets and benchmarks exist for product attribute extraction (e.g. MAVE, WDC, AE-110K and anything newer). Where are the gaps?
> Cite papers and repos. Distinguish clearly between what is production-proven and what is research-only.

### 1C → Kimi: THE ADVERSARIAL TEARDOWN

Prompt it with:

> Act as a skeptical CTO who has watched many AI data-extraction projects fail. Answer bluntly:
> 1. Why do AI product-data enrichment tools fail in real deployments? Give concrete failure modes, not generalities.
> 2. Why hasn't this problem already been solved, given that LLMs are good at extraction? What is the actual hard part?
> 3. What would a catalog operations manager at an industrial distributor refuse to adopt, and why? What is their real trust threshold before they let automated data touch a live catalog?
> 4. In hackathons on this exact theme, what are the ten most obvious projects everyone builds? I want to know what to avoid.
> 5. Where is the genuine defensible moat in this space, if any — and make the case that there ISN'T one, so I can stress-test my optimism.
> Be harsh. Do not be encouraging.

### 1D → Optional fourth: recency sweep

If available (Perplexity, Grok, or web search), ask for anything from the last 12 months: funding rounds, new entrants, model releases, standards changes in this space. Flag anything that invalidates the older research.

**Phase 1 output to me:** each model's full response, plus a one-line note on anything that failed to load or got truncated.

---

## PHASE 2 — CROSS-MODEL SYNTHESIS

Do not summarize. Analyze. Produce:

1. **Consensus table** — claims two or more models independently made. These are load-bearing.
2. **Contradiction matrix** — where they disagree. For each: which is likely right and why, or mark it as an open question needing verification. Contradictions are the most valuable output here; do not smooth them over.
3. **Unique insights** — anything exactly one model raised that the others missed. Rank by how non-obvious it is.
4. **The blind spot list** — what did all three miss? You have the full picture now; they each had a slice.
5. **Verification pass** — pick the three most decision-critical factual claims and open a primary source to confirm each. Report what you find, including if it contradicts the model.

---

## PHASE 3 — IDEA GENERATION AND BRUTAL FILTERING

### Banned ideas — auto-reject any concept that reduces to these:

- Upload a PDF → LLM extracts attributes → pretty dashboard
- A chatbot you ask questions about your catalog
- Generic RAG over product documents
- "AI-powered search" for an existing catalog
- A Streamlit app wrapping one API call
- Anything whose entire demo is one happy-path file
- Anything where swapping the LLM for a competitor's makes zero difference to the product

If your top idea is one of these wearing a costume, throw it out and go again.

### Seeded hypotheses — attack these, don't accept them

Three provocations. Your job is to find evidence for AND against each, then keep or kill:

- **H1 — The bottleneck is trust, not extraction.** Modern models can pull the thread pitch off a datasheet. What nobody has solved is proving a value is correct, tracing it to a source span, and knowing reliably when to abstain. The product might be a *verification and provenance layer*, not an extraction tool.
- **H2 — Whoever owns the benchmark owns the category.** SWE-bench made agentic coding legible and its authors became the reference point. There may be no serious open benchmark for industrial product-data enrichment. Shipping the benchmark + eval harness alongside the tool is a distribution strategy disguised as a technical contribution.
- **H3 — The moat is the taxonomy graph, not the model.** Every enrichment run makes the cross-standard mapping (ETIM ↔ eCl@ss ↔ customer's internal schema) richer. That compounding asset may be the only defensible thing here, since the model layer is a commodity.

### Generate 12+ distinct concepts, then score

Score each 1–10 on:

| Weight | Criterion |
|---|---|
| ×3 | **Non-obviousness** — would a strong engineer say "I hadn't thought of that"? |
| ×3 | **Defensibility** — is there a compounding asset (data, graph, benchmark, community)? |
| ×2 | **Wedge sharpness** — is there one narrow beachhead where it's 10x better, not 10% better? |
| ×2 | **Demo shock value** — does the live demo produce a visible "oh damn" moment? |
| ×2 | **Open-source strategy fit** — does OSS genuinely accelerate distribution, or is it just giving work away? |
| ×1 | **Technical depth** — is there real engineering here, or is it prompt plumbing? |
| ×1 | **Why now** — what changed in the last 18 months that makes this newly possible? |

Show the full scored table. Then take the top 3 and write a paragraph on **how each one dies** — the most likely failure mode, stated honestly.

---

## PHASE 4 — FULL SPEC FOR THE WINNER

Pick one. Justify the pick against the runners-up in three sentences. Then produce the complete spec:

1. **The one-liner** and the 30-second pitch.
2. **The wedge** — the specific first user, the specific first product category, the specific first workflow.
3. **System architecture** — components, data flow, model orchestration strategy, where deterministic code beats an LLM call and why. Include a diagram in Mermaid.
4. **The data model** — core schema, how provenance and confidence attach to every single field, how conflicts between sources resolve.
5. **The explainability layer, concretely.** The PS explicitly demands explainable outputs. Not "we show a confidence score" — specify exactly what a human reviewer sees, what they can click into, what evidence gets surfaced, and how a disputed value gets adjudicated.
6. **The evaluation harness** — how correctness is measured, what the gold set looks like, how regressions get caught. If a benchmark contribution is part of the play, spec it.
7. **ADRs for the three highest-stakes technical decisions.** Use this format: Context / Options Considered (with a trade-off table across complexity, cost, scalability, maintenance) / Decision / Consequences (what gets easier, what gets harder, what we'll revisit). Do not skip the losing options — I want to see what was rejected and why.
8. **What makes this hard** — the three genuinely difficult engineering problems, stated so I know where the real work is.
9. **Open-source strategy** — license choice and reasoning, what's open vs. commercial, repo structure, the README hook, contribution surface, how the community becomes a moat.
10. **Business model** — who pays, for what, at what point. Include the counterargument for why they might not.
11. **Naming** — five candidates with reasoning, checked for existing collisions.
12. **The demo script** — a beat-by-beat walkthrough of the live demo, engineered so the payoff moment lands in the first 90 seconds. Name the exact moment a judge's eyebrow goes up.

---

## PHASE 5 — RED TEAM YOUR OWN PLAN

Switch sides completely. You are now a hostile judge and a skeptical seed investor:

- The five hardest questions that will be asked, with the honest answers — including where the honest answer is weak.
- What breaks first at real scale.
- The strongest argument that this should NOT be built.
- What would have to be true for this to become a real company, listed as testable assumptions rather than hopes.

Then revise the Phase 4 spec wherever the red team landed a hit.

---

## TONE

Direct. No hedging, no filler, no congratulating me on the question. If an idea is weak, say it's weak and say why. I would rather find out here than in front of judges.
