# Phase 5 — Red Team

**Run date:** 17 August 2026
**Target:** `phase4-full-spec.md`
**Posture:** hostile hackathon judge and skeptical seed investor. No credit given for good intentions, honest caveats, or intellectual tidiness. A spec that admits its weaknesses is still a spec with weaknesses.

---

## 0. Opening position

The Phase 4 spec has one real virtue and one real vice, and they are the same property.

Its virtue: it is unusually honest. It names its own failure modes, concedes Kimi's no-network-effects attack on per-customer schemas, flags an unverified figure rather than laundering it, and puts an abstention bucket on stage in the demo.

Its vice: **honesty has been mistaken for mitigation.** Roughly a dozen times the document identifies a problem, states it plainly, and then moves on as though naming it were solving it. The groundable-fraction report is the clearest case — "39% is undefendable" is presented as a *finding* rather than as the product failing on the majority of the records that actually matter. Section 8.2 even admits the three hardest difficulties correlate perfectly and all point at the same records, then does not follow that observation to its commercial conclusion.

Below is the conclusion it declined to draw, along with four questions the spec cannot currently answer with a number.

---

## 1. The five hardest questions

### Q1 — "You are selling a mirror. Who actually buys a mirror?"

**The attack.** Every persona in §2.1 is either politically clean and episodic, or budgeted and politically hostile. The post-acquisition integration lead has real money and disappears in nine months. The new head of digital has a discretionary budget measured in tens of thousands and will not bet their first two quarters on a report that indicts inherited systems they do not yet understand. The catalog ops manager has the recurring line item and is the one person your pitch attacks. §2.1 concedes this, calls it "unresolved," and proceeds to build five more sections on top of it.

**The honest answer.** The wedge is the compliance owner, not the four personas the spec ranks. Under a dated regulatory obligation, an audit stops being a discretionary judgment about competence and becomes a required control. That buyer is politically insulated (the pressure is external), has a defensible budget line, and recurs annually by construction. The spec ranks this persona fourth. It should be first.

**Where it stays weak.** Reordering the personas does not fix the underlying arithmetic: the compliance-driven buyer wants a *narrow* audit of the specific fields their obligation names, not the whole catalog. That is a much smaller initial contract than the spec's revenue model assumes, and the path from "audit these eleven compliance fields" to "monitor two million SKUs continuously" is exactly the expansion story every failed enterprise-tools company told its investors. Unproven.

### Q2 — "Your evidence comes from the same models that score 46.43 on grounding. Why should I believe your boxes?"

This is the question that should decide whether the project proceeds.

**The attack.** The spec's whole rhetorical structure rests on the 95.6-vs-46.43 gap. But it never confronts the direct implication: **if the state of the art points at the right words less than half the time, then more than half of your evidence boxes point at the wrong words.** A reviewer opens a redline, sees a box that does not support the claim, and concludes the tool is broken. And they are not wrong to — the box *is* wrong. You have not built a verification layer, you have built a machine that generates confident-looking accusations with mismatched citations at industrial scale, which is a more sophisticated version of the exact failure the spec claims to be fixing.

**The spec's implicit defence, made explicit and then examined.** §0.1 argues the audit task has a better operating point than extraction because the comparator only needs high-precision disagreement detection and can abstain on everything else. There are two real reasons that asymmetry might hold: an audit runs at low coverage by choice, and it starts from a candidate value rather than an open field, which turns span-finding into span-*confirmation* — a much easier retrieval problem. Both are plausible mechanisms.

**Where it is weak, and this is the sharpest weakness in the entire spec: the asymmetry is asserted, never measured.** There is no number anywhere in Phase 4 for how precisely this system detects disagreements or grounds them, at any coverage. The document builds a company on an operating-point claim it has not tested, in a spec whose governing rule was "never invent numbers." It does not invent a number here — it simply proceeds without one, which is the same sin wearing better manners.

**One partial mitigation the spec missed, in its favour:** a wrong evidence box is *self-revealing*. The reviewer sees immediately that the box does not support the claim, unlike a wrong value with no box, which propagates silently. That is a genuine architectural advantage over the alternative. But it converts a correctness failure into a trust tax, and trust taxes compound. The metric that matters — **the fraction of redlines whose evidence a reviewer accepts as supporting the claim** — does not exist in §6 and must.

### Q3 — "What stops Salsify shipping this as a checkbox?"

**The attack.** Phase 2 verified Salsify at 2,000+ customers, ~750 million products, 2,600 commerce destinations, 70,000+ active users, now Cinven-backed and explicitly positioned as the data layer for agentic commerce. Akeneo shipped an "Agentic Product Cloud" release. Syndigo combined with 1WorldSync. Any of them can ship a feature called Data Quality Score in two quarters. It will be worse than yours. It will also be in the tool the customer already owns, sold by the vendor they already trust, on a contract they already signed.

The spec's answer — "none of them can credibly grade their own homework" — is good positioning and a poor defence. It assumes buyers demand independence. Most will accept the incumbent's self-assessment because it is free, integrated, and produces a number that makes the quarterly review easier. **Distribution beats correctness in this market, and the spec never argues otherwise; it just declines to engage.**

**The honest answer.** Nothing structural stops them. What you have is a timing window and a positioning asymmetry: the incumbent will grade only its *own* output, because grading a competitor's would require ingesting a competitor's data model, and grading data enriched by an offshore BPO before the PIM existed is nobody's roadmap. A verification layer that is deliberately vendor-neutral and audits work of unknown provenance sits in a spot the incumbents cannot occupy without a strategic contradiction.

**Where it stays weak.** That spot is defensible and small. The moment your category is validated, the credible acquirer list and the credible competitor list are the same four names, and both lists are the reason a seed investor asks whether this is a feature with a five-year exit rather than a company.

### Q4 — "What is your false-positive rate?"

**The attack.** §8.1 states that false-positive suppression is the company. §6.1 makes FP rate a release gate. Neither states a number, a target, or a measurement. An investor hears: you have correctly identified the single metric that decides your survival and you have not measured it.

Then the arithmetic. A diagnostic sweep surfacing 40,000 redlines at a 15% false-positive rate wastes 6,000 reviews. At $20–$35/hour fully loaded for specialised review (Phase 2's verified band) and even 40 seconds per decision, that is thousands of dollars of the customer's money spent proving your tool is wrong — inside the pilot, in front of the person who approved it. The tolerable rate is not 15%. It is probably under 2% on flagged records, and nobody in this document has demonstrated 2% on semantic equivalence across materials, threads, tolerances, ingress codes, packaging frames and unit systems.

**The honest answer.** There is no number, and there cannot be one until the equivalence suite exists. That makes the equivalence suite the first thing to build — before the console, before the connectors, before the benchmark. If it cannot reach roughly 2%, the correct decision is to stop, and the spec should say so in those words.

**Where it stays weak.** "We will measure it first" is the right answer and a completely unproven one. The honest risk statement is that this project's viability is currently unknown, not promising.

### Q5 — "Isn't this a consulting business wearing SaaS clothing?"

**The attack.** Kimi's original charge, transposed onto the actual revenue model. Look at what §10 sells: a fixed-fee report (consulting), then a bounded per-SKU diagnostic sweep (consulting), then seats, then subscription. Stages 1 and 2 are services with a software assist. And the human-heavy work is not confined to them — document-corpus acquisition, resolution-policy configuration, calibration-set construction, and per-customer recalibration are all per-customer labour that does not amortise. §8.3 concedes that model upgrades invalidate calibration, meaning the labour recurs on your engineering cadence, not the customer's.

**The honest answer.** Stages 1 and 2 are services, deliberately, because a suspicious buyer signs a diagnostic and does not sign a platform. That is a reasonable go-to-market. The company thesis rests entirely on stage-2-to-stage-4 conversion — one-time report to continuous monitoring — and **that conversion has never been tested, cannot be tested without a customer, and is the single highest-risk assumption in the spec.**

**Where it stays weak.** Every services business that intended to become a product company said this. The distinguishing evidence would be a customer who bought monitoring after the report, and there is none.

### Three more to have ready

**"Who is liable when a reviewer accepts a wrong redline?"** The audit-only posture in ADR-001 does not remove liability, it launders it. You told them 63 A was wrong, they changed it to 6 A on your evidence, you were wrong, and now their live catalog is broken by your finding with a human signature in the middle. That signature is contractual cover, not moral cover, and the first time it happens the customer will not care about the distinction. The spec has no position on this.

**"Your demo audits a company you want to sell to."** §12 acknowledges the name-and-shame problem and mitigates it well. A judge may still ask whether the business model is publishing other companies' errors, and "we found 1,240 defects in a named distributor's live catalog" is a sentence that sounds different in a courtroom than on a stage.

**"Your pattern corpus is a cross-customer database of which vendors produce bad work."** §9.2 calls error signatures the central compounding asset and notes they contain no customer-confidential data because they describe public manufacturer documents. Partly true, and it skips the commercially explosive case: a signature like *"packaging-frame collapse appears wherever this named BPO processed the feed"* is a statement about a third party's competence, held across customers, and monetised. That is a defamation surface and a channel-conflict surface, and the spec treats it as a pure asset.

---

## 2. What breaks first at real scale

In order of how soon it breaks, not how bad it is.

**1. Calibration, and it breaks early.** §8.3 requires per-class, per-customer, per-document-family calibration. Take one customer: 5,600 ETIM classes, dozens of attributes each, several document families. The calibration-set matrix is combinatorially large and each cell needs labels. Conformal prediction with class-conditional coverage needs a floor of labels per cell to be honest, and most cells will never reach it. The realistic outcome is that `calibration_out_of_distribution` — the abstention reason the spec is proudest of — fires on the large majority of the catalog, and the product's coverage collapses to a handful of well-labelled classes. **The spec's most honest feature is also the one most likely to eat the product.**

**2. Reviewer throughput, immediately after.** The triage router optimises the order of the queue, not its length. A 400,000-SKU catalog at a plausible error rate produces a queue no team can drain. §10.3 names this objection and answers it with the router — but a better sort order on an undrainable queue is still an undrainable queue. What is missing is a mechanism for retiring findings the customer will never act on, which is a product decision the spec has not made.

**3. Corpus freshness, and it breaks silently, which is worse.** Claims are anchored to `doc_revision_sha256`. A supplier reposts a PDF at the same URL with a new revision and no announcement. Every claim anchored to the prior hash is now unverifiable — the evidence exists in your blob store but no longer corresponds to the live document. Under continuous monitoring at scale this is not an edge case, it is a constant background process, and §10's monitoring product is priced on change *detection* while the spec has no story for evidence that has quietly become historical.

**4. Policy dialect proliferation.** §4.2 makes the resolution policy customer-editable, which is a good answer to "your tool disagrees with our conventions." At fifty customers it is fifty forked policy dialects, each a support surface, each an input to calibration, each capable of making a shared benchmark score meaningless for that customer.

**5. The pattern corpus turns from asset to liability.** See Q3's third addendum. Growth makes it more valuable and more dangerous at the same rate.

---

## 3. The strongest argument that this should NOT be built

Not the political objection. Phase 3 already found that one and Phase 4 has a partial answer. There are two stronger ones, and the second is the one that should worry you most.

### 3.1 The product works best where it is least needed

Follow §8.2's own admission to its conclusion. Three difficulties correlate perfectly: the tail is where the commercial value is (Phase 2 §C4), where grounding is worst, and where source documents are missing (§2.3). The groundable-fraction report is presented as honesty. Read it as a coverage statement instead:

**The system audits the ~60% of records that have current, retrievable, machine-readable source documents — which is very close to the same population as the clean 80% that Phase 2 §6 explicitly banned demoing on — and declines on the 40% where the money is.**

Phase 2 amended the Phase 3 scoring rubric specifically to kill concepts that only work on clean inputs. The fused C8/C12 concept scored 9/10 on "survives C4" on the argument that it *finds* the tail rather than processing it. That argument is weaker than the score implies: finding the tail requires grounding the tail, and grounding the tail is precisely what fails. The abstention mechanism is intellectually correct and commercially close to fatal, because a customer who is told "we cannot help with the 40% you care most about" has been sold a partial diagnostic at full price.

The spec's best counter — that the undefendable 40% is itself a compliance finding — is real but thin. It is one report, not a product line, and it is the same report every year.

### 3.2 Everybody wants exactly one audit

This is the argument the spec does not see coming, and it is worse than "nobody wants an auditor."

Suppose it all works. The report lands: 100,000 defective records, evidenced, ranked, undeniable. What is the customer's rational next move?

Not buying monitoring. **Taking your report to their enrichment vendor and renegotiating.** Your artifact is the highest-leverage document that has ever existed in that commercial relationship — it converts a vague quality complaint into an evidenced breach claim worth six or seven figures in credits, remediation-at-vendor-cost, or a better rate. They will spend it on that, once, and then their quality problem is the vendor's contractual problem, which is a cheaper and more permanent fix than a subscription to continuously rediscovering it.

You are not a platform. You are ammunition — enormously valuable ammunition, purchased once per relationship, per negotiation cycle. That is a real business and it is a services business with lumpy revenue and no compounding contract value, which is precisely the shape Kimi described as "a services business wearing SaaS clothing" and precisely the shape a seed investor will not fund at software multiples.

The rebuttal — that the remediated data drifts again and needs continuous verification — requires the customer to believe verification is a permanent operational function rather than a periodic project. Nothing in Phases 1 through 4 provides a single piece of evidence that any industrial distributor believes that today.

---

## 4. What would have to be true — as testable assumptions

Ordered by test cost, because the cheap fatal tests come first. A1 and A2 can be run without a customer, without a repo, and inside two weeks. If either fails, nothing else matters.

| # | Assumption | Test | Cost | If it fails |
|---|---|---|---|---|
| **A1** | False-positive rate on semantic equivalence can be driven under ~2% | Build the equivalence suite first — materials, threads, tolerances, ingress codes, packaging frames, unit frames. Hand-label 500 equivalence pairs and 500 genuine contradictions from public datasheets. Measure. | ~2 weeks, no customer | **Stop.** This is the kill criterion. Above ~5% the product is unshippable at any quality of everything else |
| **A2** | Auditing has a materially better precision/coverage operating point than extraction at equal grounding quality | 200 hand-labelled MCB records from public datasheets. Measure disagreement-detection precision and word-level grounding at 20/40/60% coverage. Compare against ExtractBench's published 46.43 word-level and 95.6 value F1 at full coverage. | ~2 weeks, no customer | **Stop, or pivot to the value-semantics library as the product.** The entire thesis is this asymmetry |
| **A3** | Reviewers accept the evidence box as supporting the claim at a high rate | 5 domain reviewers, 200 redlines, measure box-acceptance rate and seconds-to-decision. This is the missing metric from Q2. | ~1 week once A2 exists | Redesign the evidence surface before anything else gets built |
| **A4** | The groundable fraction of a real industrial catalog exceeds ~50% | Run the §2.3 inventory against three public distributor catalogs in circuit protection. No permission needed; all inputs public. | ~2 weeks | If it is 25%, the addressable product is a quarter the size claimed and §3.1 above is confirmed |
| **A5** | Error signatures generalise across customers | Audit two independent catalogs carrying the same manufacturer's products. Measure signature overlap. | ~3 weeks | **The moat argument in §9.2 collapses to the grammar library alone**, and Kimi's no-network-effects attack wins after all |
| **A6** | The compliance-driven buyer holds budget and can sign | 15 structured conversations: compliance owners and post-acquisition integration leads at ETIM-adopting distributors. Ask what they have budget to sign this quarter, not whether the problem is real. | ~3 weeks, cheap, do it in parallel with A1 | Re-wedge. Possibly to C6 or C9, both of which Phase 3 kept alive as separate businesses |
| **A7** | A one-time diagnostic converts to continuous monitoring | **Not testable without a customer.** Weak proxy: ask the A6 cohort directly whether they would fund ongoing monitoring after a one-time report, and specifically whether they would instead take the report to their vendor (§3.2). | Cannot be de-risked pre-revenue | This is the company. If §3.2 is right, the honest outcome is a well-paid services business, not a venture-scale one |
| **A8** | Calibration reaches usable coverage on a real catalog's class distribution | Simulate: take the ETIM class distribution of a real catalog, compute how many classes clear a minimum label floor under a realistic labelling budget. | ~1 week, arithmetic | If coverage lands in single-digit percentages, the abstention-first design is the product's ceiling, not its integrity |

**The ordering is the recommendation.** A1, A2 and A8 are cheap, require no customer, and any one of them can end the project. Run them before writing a line of console code. A6 runs in parallel because it needs calendar time. A7 is the assumption you cannot retire, and pretending otherwise would be the exact failure this document exists to prevent.

---

## 5. Where the red team landed hits — edits forced into Phase 4

| Hit | Section | Change |
|---|---|---|
| Q2 — the audit-vs-extraction asymmetry is asserted, not measured | §0.1, new §8.0 | Promote it to the spec's named load-bearing unproven assumption, stated as such at the top |
| Q2/A3 — no metric for whether evidence is believable | §6.2 | Add **evidence-acceptance rate** as a first-class benchmark axis |
| Q4 — FP rate has no target | §6.1 | Name the gate: **<2% on the equivalence suite**, and state that above ~5% the product does not ship |
| §3.2 — everybody wants exactly one audit | §10.3 | Add as the primary counterargument, ahead of discovery-liability |
| Q1/A6 — persona ranking is wrong | §2.1 | Promote the compliance-driven buyer to first, with the narrow-scope caveat |
| Q1 addendum — liability laundering | §4.3 | Add an explicit position on who owns a wrong accepted redline |
| Q3 addendum — pattern corpus as defamation surface | §9.2 | Name the third-party-competence risk instead of treating the corpus as a pure asset |
| §2/§4 — calibration coverage may cap the product | §8.3 | State that abstention coverage collapse is the likely ceiling, not just a risk |
| All — no kill criteria anywhere | new closing section | Add A1/A2/A8 as explicit stop conditions with the ordering |

Applied in `phase4-full-spec.md` under **Revisions after Phase 5**.

---

## 6. Verdict

Build it, and do not build it in this order.

The concept survives the red team on its central insight: a verification layer occupies a position that improves as extraction models improve, and the 95.6-versus-46.43 gap is a real, verified, three-week-old hole in the market that the problem statement is explicitly asking someone to fill. That is a genuinely good reason to start.

It does not survive as a *company* on current evidence, and the reason is not the politics Phase 3 identified. It is §3.2: the most likely outcome of doing this extremely well is that you hand each customer a single devastating artifact they spend once, against their vendor, and never need again. Every path to a durable business runs through A7, and A7 cannot be tested from here.

**What the spec should have said and did not:** the correct first deliverable is not the console, the connectors, or the benchmark. It is the equivalence suite and the operating-point measurement — A1 and A2 — because they are cheap, they need no customer, and either can end the project in a fortnight. Everything in Phase 4 downstream of the comparator is well-designed work that should not be started until those two numbers exist.

Build A1 and A2. Then decide whether Phase 4 describes a company or a very good open-source library with a services attachment. On today's evidence the honest answer is that nobody knows, and the spec reads as though it does.

---

*End of Phase 5.*
