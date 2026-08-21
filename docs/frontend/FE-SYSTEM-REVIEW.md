# FE-SYSTEM-REVIEW — what the frontend plan is missing, and the architecture that fixes it

**Written:** 21 August 2026, after building FE-1 and FE-2.
**Scope:** everything the blueprint decides, everything it does not, and the seam between
`web/datum/` and the six Python distributions that are the actual product.
**Status:** review document. It raises questions; §9 says who owns each one.

---

## 0. The verdict, in one paragraph

`FRONTEND-BLUEPRINT.md` is an outstanding **art direction** document and a **non-existent
architecture** document. Its §17 is titled "STACK & ARCHITECTURE" and contains a dependency list
and a folder tree — no data contract, no delivery model, no identity model, no time model, no
failure taxonomy. That would be a normal gap. What is not normal is the reason for it: **the
blueprint was written without reading the product it is for.** The evidence is mechanical and it
is in §1. The fix is not more design; it is one architectural decision (§4.1) that has never been
taken, and a contract (§5.1) that has never been written.

---

## 1. The finding that reframes everything else

I grepped the blueprint for the vocabulary of the domain it is designing for. The domain model is
`errata_spec`, it is 5 modules, it is shipped, and it is good.

| Domain term | In `errata_spec` | Mentions in the 1,515-line blueprint |
|---|---|---:|
| `Adjudication` | ✅ shipped | **0** |
| `Abstention` (a distinct type, not a null) | ✅ shipped | **0** |
| `Redline` | ✅ shipped | **0** |
| `CounterEvidence` | ✅ shipped | **0** |
| `BlastRadius` | ✅ shipped | **0** |
| `supersedes` chains | ✅ shipped | **0** |
| `DeclinedReason` | ✅ shipped | **0** |
| reviewer-seconds (FR-9.3) | ✅ shipped, timed | **0** |
| ETIM / ECLASS / UNSPSC | ✅ shipped, three adapters | **0** |
| "API" | — | 10 — **all ten are museum image APIs** (§7.3) |
| "auth" | — | 7 — **all seven are "authority"** (scroll authority, design authority) |

Two of those rows are the ones that matter.

**There is no authentication anywhere in the blueprint, and FR-8.9 requires dual control.**
"Safety-class attributes require a second named adjudicator. Single-signature acceptance
impossible for allow-listed attributes." That is not a settings-page feature. It is an identity
model, a pending-second-signature state, a role, and a UI that can express *"you cannot complete
this alone."* None of it exists in the plan.

**There is no API in the blueprint, and there is no HTTP layer in the product.** I checked: no
FastAPI, no Flask, no Starlette, no uvicorn anywhere in the repository. `spec/tests/test_registry.py`
actively *bans* `socket`, `urllib`, `requests`, `httpx`, `http`, `aiohttp` and `ssl` from the core
— determinism is enforced by test. The only server that exists is
`audit/src/errata_audit/web.py`: 1,058 lines of `http.server`, bound to 127.0.0.1, no auth, by
explicit decision.

So the blueprint designs `/app/queue`, `/app/record/:id`, `/app/calibration`, `/app/sources` and
`/app/settings` in Next.js 15 with RSC — **against a backend that does not exist, over a contract
nobody has written, for a product whose current shipping form is a local tool that deliberately
refuses to be on a network.**

That is the gap. Everything in §2–§4 is a consequence of it.

---

## 2. Four places the design LAWs contradict P0 requirements

These are not tensions. They are contradictions, and each one blocks a P0.

### C-1 · The evidence legend needs three colours. The palette allows one.

**FR-7.3 (P0):** *"Header highlighting. The containing cell outlined, plus its row and column
headers in a second colour. A number in a table is never shown without the headers that give it
meaning."*
**FR-7.4 (P0):** the counter-evidence panel is *"never empty and never absent"* — and in the
shipped console it is a third box style.

The shipped console already does this, in `console.py`:

```
--value-box: #b3261e;   --header-box: #1d6fb8;   --counter-box: #2e7d32;
```

Red, blue, green. Three simultaneous, adjacent, semantically distinct overlays on one page image.

**Blueprint L-1:** *"The interface is achromatic except where a value is in dispute. Global chroma
ceiling 0.16."*
**§6.8:** *"Verdigris is used at most twice per screen and never adjacent to signal. Ice is a
highlight on paper only."*

A reviewer looking at an evidence page sees the value box, its row header, its column header and
the counter-evidence, **at the same time, touching each other.** That is four marks needing three
distinguishable identities, in the one place the system's colour law is strictest.

**This is the hardest unsolved design problem in the product and the blueprint does not know it
exists.** It is also the one that decides whether the console is usable, because FR-7.3 exists
precisely because a number in a table without its headers is how the previous generation of tools
got things wrong.

*Direction I would take:* stop solving it with hue. The three marks are not three categories of
equal weight — they are **the value**, **its coordinates**, and **the case against**. Encode them
in three different *channels*: the value gets the signal plane (the only chroma); the headers get
a **hairline bracket in `--edge-strong` plus a leader rule**, which is how an engineering drawing
dimensions a feature and needs no colour at all; counter-evidence gets the **dotted 2px reveal on
the opposite edge** — anastylosis reversed, because counter-evidence is the fabric arguing back.
That keeps L-1 intact, is stronger typographically, and is testable against FR-7.3's own
acceptance criterion. It needs a comp before anyone believes it.

### C-2 · FR-7.5 forbids the queue I built in FE-2

**FR-7.5 (P0):** *"Queue rows render as a sentence — values, source location, shared-pattern
count, downstream propagation — **never a bare confidence percentage**. No UI surface displays a
raw confidence score as the primary signal."*

`states.html` component 14 renders a queue as a `DataTable` with a right-aligned `Conf.` column of
`0.86`, `0.91`, `0.97`. I built that by following §13.2 faithfully. **§13.2 is wrong**, and I
propagated it. The `Confidence` component is well-designed and belongs on the record detail; it
must not be the queue's primary signal.

The queue row is a **sentence component** that does not exist:

> **4C-M-16-66** says rated current is `10 A`. Page 2, table 3 says `16 A`.
> **1,240 SKUs** share this signature. It feeds **3 faceted filters** and **1 compliance export**.

That is FR-7.5, FR-8.4 and FR-8.5 in one component, and it is a genuinely novel row design because
almost nobody builds a data table whose row is prose. It also happens to be far better for screen
readers than a five-column numeric grid.

### C-3 · L-6 forbids the render FR-7.2 requires

**FR-7.2 (P0):** *"Word-level evidence box rendered on the source page at the stored span's
projection. Box lands on the value's words, not the paragraph or page."*
**Blueprint L-6 / §13.3:** *"Never an image-only render — spans must be selectable."*

The shipped console rasterizes with PyMuPDF (`render_page`, `PageImage`) and draws boxes on the
image. The blueprint forbids that. Both are right about something: a scanned datasheet **is** an
image and pretending otherwise is the lie L-2 warns against, and text that cannot be selected
**is** the F-04 failure.

The reconciliation is a specific rendering architecture, not a compromise, and §5.3 specifies it.
Nobody has written it down, and it is the single largest piece of engineering in FE-7.

### C-4 · `--m-cine: 1200ms` on a triage tool

§10.1's motion scale runs to 1200ms and §12.1 spends 860vh on a five-room procession. Correct for
the landing. **The product surface has no motion budget at all** — no guidance that a reviewer
adjudicating for three hours needs `--m-instant` and nothing else, that a queue must never animate
a reorder, and that FR-9.3 is *literally timing the human*, so every millisecond of decorative
transition is being charged to the metric a buyer pays for.

**A motion system that is measured in reviewer-seconds is a different system.** The blueprint has
one motion grammar where it needs two, and the second one is mostly the word "no".

---

## 3. Requirement coverage — what has no surface at all

Every row below is a **P0 or P1 in `prd-errata.md`**. The right-hand column is what exists in the
blueprint's §12 sitemap and §13 component library.

| Req | What it demands | Blueprint provides |
|---|---|---|
| **FR-7.1** | Three-pane console: queue · evidence · **claim history** | Queue and evidence, in outline. **No claim-history pane, no component** |
| **FR-7.3** | Header highlighting, second colour | Nothing. Contradicted (C-1) |
| **FR-7.4** | Counter-evidence panel, never empty | **Nothing** |
| **FR-7.6** | Accept redline · Keep catalog · Escalate | **Nothing.** Not even a button variant |
| **FR-7.7** | OCR-layer toggle · raw-page jump · **document revision history** | **Nothing** |
| **FR-7.8** | Evidence reconstructible from stored state, *not regenerated at view time* | **Nothing** — and this is an architecture constraint, not a component (§5.2) |
| **FR-8.1** | **Groundable Fraction Report** — the catalog inventoried against retrievable evidence *before any audit* | **No page.** This is arguably the product's most important screen (§7.3) |
| **FR-8.4** | Blast radius, **four factors independently inspectable in the UI** | **Nothing.** `Confidence` is the only score component and it is deliberately opaque |
| **FR-8.5** | Cluster size — "1,240 SKUs share this pattern" | **Nothing** |
| **FR-8.7** | Tiered execution T0→T3 + **cost report** scaling with error count | **No page.** This is the commercial argument |
| **FR-8.8** | Batch reversal as a **query**, demonstrated on 1,000 records | **No surface.** Needs a selection-over-history UI |
| **FR-8.9** | **Second named adjudicator** for safety-class attributes | **Nothing.** No identity model exists |
| **FR-9.3** | Reviewer-seconds via a **timed protocol** | **Nothing.** The page must time itself and submit the number |
| **FR-9.4** | **Evidence-acceptance rate** — did the reviewer accept the *box* | **Nothing.** A second, separate control next to the decision |
| **FR-9.8** | **ECLASS content never in repo, image or benchmark** (ADR-003) | **Nothing** — and this is a *build-time constraint on the frontend bundle*. Nobody has said so |

Fifteen P0/P1 requirements with no design. For calibration: the blueprint specifies twenty
components and I built them. **Roughly nine more are required by the PRD**, and three of them
(`QueueSentence`, `EvidenceOverlay`, `AdjudicationBar`) are harder than any of the twenty.

### The one that should worry you most

**FR-9.8 is a bundle constraint.** ECLASS is licensed; the adapter reads *the customer's own*
dictionary at runtime. If a frontend developer imports a label map for nicer display names, or a
build step inlines a class dictionary for search, **the wheel and the container become
redistributable ECLASS content** and ADR-003 is broken by a webpack config. CI has a content
scanner for the Python artifacts (`supply-chain` job in `build.yml`). **There is no equivalent
scanner for the frontend bundle, and no policy saying there should be.**

---

## 4. The six questions nobody has answered

These are the "more lacking questions". They are ordered by how much downstream work they unblock.
Q1 is not the most interesting; it is the one that makes the other five answerable.

### Q1 · What is the delivery model? — **blocks everything**

Three futures, mutually exclusive, all currently implied somewhere in the repository:

| | Model | What it means | What it breaks |
|---|---|---|---|
| **A** | **Local operator tool** (today) | Ships in the wheel. 127.0.0.1. No signup — this is FR-7.9 and the README hook | Next.js RSC is the wrong stack. No hosted marketing→product funnel |
| **B** | **Hosted SaaS** | We store the customer's catalog *and* third-party copyrighted datasheets on our infrastructure | Breaks "no signup". Creates a copyright-exposure surface FR-9.5 was written to avoid. Needs tenancy, auth, DPA, SOC2 conversations |
| **C** | **Split** — hosted marketing/docs/benchmark, local console | Public site is static; the product stays on the reviewer's machine | Two build pipelines, two deploy targets. "Try it" is a `pip install`, not a signup |

**My recommendation: C, and say it out loud in an ADR.**

The reason is not technical. It is that **the product's entire pitch is that it does not touch
your data** ("It grades data. It does not create data", ADR-001 audit-only output, FR-8.6 no
named-organisation signatures). A hosted console that ingests a customer's PIM export *and*
Schneider's copyrighted PDF is a different company with a different legal posture. That is a
board-level decision wearing an architecture hat, and it has been made by default — by nobody —
every day since the blueprint was written.

**C also happens to be the cheapest and the most distinctive.** "Install it, point it at a
datasheet, no account, and the evidence never leaves your laptop" is a genuinely strong enterprise
sales position in 2026 and no PIM vendor can copy it.

### Q2 · Where does ranking run, and over how many rows?

R2 is catalog-scale. FR-8.4's expected review value = P(catalog wrong) × blast radius must be
**reproducible** and each factor **inspectable**. The blueprint says "virtualised beyond 200 rows".

At 1.2M records: ranking is not a client concern, pagination must be cursor-based over a stable
sort key, and *the sort key must be content-addressed* — otherwise a reviewer who returns after
lunch gets a different queue and cannot explain why. **A reproducible ranking implies a frozen
ranking snapshot with an id.** That is a data structure, not a UI decision, and it does not exist.

### Q3 · What is the time model?

`DocumentRevision`, `supersedes`, versioned `ResolutionPolicy`, `ExtractorFingerprint`. Every one
of those is a time axis. FR-7.8 says evidence must be *reconstructible*, and FR-7.7 wants document
revision history.

**Therefore every product view is an as-of view** — as-of a document revision, a policy version and
an extractor fingerprint. There is no as-of anywhere in the blueprint. Retrofitting time into a UI
that assumed "now" is one of the most expensive refactors in software, and it is one hundred percent
avoidable by deciding it in FE-3.

### Q4 · Who is the reviewer, cryptographically?

Three requirements need identity and none of them is a login page:

- FR-8.9 — a **second named** adjudicator
- FR-7.6 — decision, **actor**, timestamp, note, persisted immutably
- `docs/reviewer-protocol.md` — the harness **refuses to produce a number** for decisions made by
  anyone who built the tool. Insider exclusion is enforced, so actor identity is load-bearing for
  a *measurement*, not just for an audit trail.

In delivery model **C** there is no server to hold accounts. §5.5 proposes the answer.

### Q5 · What happens to a three-hour session when the network blinks?

The reviewer protocol times people. A lost decision is a lost measurement and an angry reviewer.
There is no offline model, no optimistic write, no conflict rule, no draft state. For an
append-only ledger this is unusually tractable (§5.4) and unusually damaging to skip.

### Q6 · Which locale is `16,0 A` in?

ETIM is a **multilingual** standard. The customers are European industrial distributors. German and
French industrial documents use the decimal comma. The blueprint mandates
`font-variant-numeric: tabular-nums slashed-zero` and L-4 says never render a precision the source
does not contain.

**L-4 and locale formatting are in direct conflict and nobody has noticed.** If the source says
`16,0 A` and the UI renders `16.0 A`, that is a transformation of evidence. If it renders `16 A`,
that is a *lost significant figure* — `16,0` asserts a precision `16` does not.

**Rule I would write:** evidence values are rendered **byte-exact as extracted, never localised,
ever.** Derived and aggregate values are localised. The two must be typographically distinct — and
they already are, because evidence is Redaction 0 and interface numbers are Sligoil. The type
system solves this for free and nobody has claimed the win.

There is no i18n plan at all, incidentally: no message catalogue, no `lang` strategy, no RTL
consideration, no pseudo-locale in CI.

---

## 5. The system design

This is the part that does not exist anywhere in the repository today.

### 5.1 One contract, two hosts

```
┌─────────────────────────────────────────────────────────────────┐
│  errata-spec   (pydantic, deterministic, NETWORK-FREE by test)  │  ← unchanged
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────┴───────────────────────────────────┐
│  errata-api  ── NEW. ASGI. The only place HTTP touches the core │
│  · generated OpenAPI 3.1 straight off the pydantic models       │
│  · same app object served by (a) the local wheel  (b) a host    │
└─────────────────────────────────────────────────────────────────┘
        ▲                                          ▲
┌───────┴──────────┐                    ┌──────────┴──────────────┐
│  console (SPA)   │                    │  site (static, Astro)   │
│  served BY the   │                    │  marketing · docs ·     │
│  local process   │                    │  benchmark · errata     │
└──────────────────┘                    └─────────────────────────┘
```

**The determinism boundary is preserved and must be stated as an ADR.** The banned-import test
covers `spec` and `valuesem`. `errata-api` may import `http`; the core may not. That layering is
already implicit in the test and needs to become explicit before someone "helpfully" adds a fetch
to `derive.py`.

**The contract is generated, never hand-written.** `errata_spec`'s pydantic models → OpenAPI 3.1
→ TypeScript via `openapi-typescript`. The domain model becomes the wire format becomes the client
types. A field added to `Redline` shows up as a type error in the console at build time. This is
the difference between a design system that drifts and one that cannot.

`web.py`'s existing routes are the honest starting point — `/audit`, `/status`, `/ledger`,
`POST /adjudicate` — and they are already 80% of the right shape.

### 5.2 The Evidence Bundle — the idea I would fight for

FR-7.8 says evidence must be **reconstructible from stored state, not regenerated at view time.**
Today that is an aspiration enforced by discipline. Make it structural.

An **Evidence Bundle** is a content-addressed, self-contained, offline-verifiable directory:

```
bundle-<blake3>/
  manifest.json        # digests of everything below, + the bundle's own digest
  claims.jsonl         # Claim | Abstention, verbatim errata_spec
  redline.json         # Redline + CounterEvidence + BlastRadius (4 factors, separate)
  policy.json          # the ResolutionPolicy VERSION that resolved this
  fingerprint.json     # ExtractorFingerprint — which code produced this
  document/
    revision.json      # DocumentRevision + sha256 of the source PDF (never the PDF)
    pages/2@2x.avif    # deterministic raster, PyMuPDF, fixed DPI + fixed matrix
    pages/2.chars.bin  # char-level geometry sidecar (§5.3)
```

Five things follow, and each one is a requirement that stops being aspirational:

1. **FR-7.8 becomes structurally true.** The console renders *only* from a bundle. There is no code
   path that regenerates evidence at view time, because the renderer has no extractor.
2. **The console works offline** (Q5) — a bundle is the unit of prefetch.
3. **"What was this reviewer looking at" has a permanent answer**: the bundle digest, recorded on
   the `Adjudication`.
4. **It is the commercial artifact.** When a distributor disputes a value with a manufacturer, they
   send the bundle. Self-contained, hash-verifiable, no account needed to open it. *Nobody in this
   market ships that.*
5. **Verifiable in the browser with no backend.** Canonical JSON + SHA-256 via WebCrypto — the
   console can prove a bundle is untampered, client-side, offline. `errata_spec.determinism`
   already has `canonical_payload` and `payload_digest`; port that canonicalisation to TS and the
   check is thirty lines.

**Prior art to steal rather than invent: OCFL** (Oxford Common File Layout) — a real, boring,
institutionally-adopted standard for content-addressed versioned object storage, used by
university archives. For a product whose entire pitch is provenance, adopting an archival standard
rather than a bespoke zip is both correct and unusually good positioning.

**Copyright caveat, and it is load-bearing:** FR-9.5 forbids redistributing source PDFs. A bundle
stores the *rasterized page region* and the source **hash**, not the PDF. Whether a 2× raster of one
page of a Schneider datasheet is redistributable is **a legal question I am not qualified to
answer, and it must be answered before this ships.** Flagging it rather than assuming fair use.

### 5.3 The evidence render pipeline — resolving C-3

The fight between "boxes on a page image" (FR-7.2) and "never an image-only render" (L-6) resolves
into three layers, and it is the same trick a good scan viewer has used for twenty years:

```
z=0   <img>   deterministic page raster, AVIF, 2 zoom levels, content-addressed
z=1   <span>  transparent, absolutely positioned, one per WORD, from the char sidecar
              → real selectable text at device resolution. L-6 satisfied.
z=2   <svg>   evidence boxes, header brackets, counter-evidence marks
              → vector, crisp at any zoom, themeable from tokens
```

- Geometry comes from **PyMuPDF, already a dependency**. Extract char rects once, at ingest,
  deterministically, into the bundle. Never at view time.
- **Define the coordinate system once, in the spec.** PDF user space → raster px → CSS px, with
  rotation and MediaBox/CropBox offset handled at ingest. Getting this wrong is how evidence boxes
  land on the wrong words, which is failure mode "evidence boxes wrong more often than right" —
  already on the PRD's own risk register as *"product self-discredits on screen."*
- **PDF.js is not on the critical path.** It becomes the FR-7.7 "raw-page jump" escape hatch only.
- Word spans, not char spans: 1 span per word keeps DOM nodes in the low thousands per page.

### 5.4 Offline and the ledger (Q5)

An append-only ledger with `supersedes` is the easiest possible thing to make offline-safe, because
**there are no updates to conflict.**

- Adjudications are written to a local **outbox** (IndexedDB/OPFS) with a client-generated ULID,
  then flushed. Replay is idempotent by id.
- Two reviewers adjudicating the same attribute is **not a conflict** — it is two claims, which is
  exactly what FR-8.9's dual control wants anyway.
- The reviewer-seconds timer (FR-9.3) runs client-side and is submitted with the decision. It must
  **pause on blur and record that it paused**, or the metric is a lie the first time somebody
  answers Slack.

### 5.5 Identity without accounts (Q4)

Delivery model C has no server to hold accounts, and three requirements need a named actor.

**Proposal: adjudications are cryptographically signed, not logged in.**

- Reviewer generates a keypair on first run (**WebAuthn**/passkey where available, **age** or
  **minisign** as the portable fallback — all open source, all boring).
- Every `Adjudication` carries a detached signature over its canonical payload.
- FR-8.9's dual control becomes *"this claim requires two valid signatures from distinct keys in the
  allow-list"* — verifiable by anyone, offline, forever, with no auth server.
- The reviewer protocol's insider exclusion becomes a **key-list check** instead of an honour system.

This is more work than a login form and it is the correct amount of work for a product whose output
is meant to survive a dispute. It also means the ledger a customer reads in a text editor is a
ledger a customer can *verify* in a text editor — which is the strongest possible version of the
claim `ledger.py` already makes.

### 5.6 What the queue actually is

Not a table. A **ranking snapshot** (Q2) plus a **sentence renderer** (C-2):

```
GET /queue?snapshot=<digest>&cursor=<opaque>&limit=50
```

- The snapshot digest pins P(wrong) × blast radius, the policy version and the extractor
  fingerprint. Same digest ⇒ same order, forever. Reproducible ranking, as FR-8.4 demands.
- Each row carries its **four blast-radius factors separately**, because FR-8.4 says each must be
  independently inspectable and a score is not a reason.
- Virtualisation: TanStack Virtual over cursor pages. The client never holds 1.2M rows.

---

## 6. The stack — with what I reject and why

The blueprint's stack is defensible and, for the product surface, wrong. Reasoning, not a list.

| Layer | Blueprint | Recommendation | Why |
|---|---|---|---|
| **Public site** | Next.js 15 RSC | **Astro 5** + one React island | The site is content: 9 static pages, MDX docs, a benchmark table. Astro ships ~0 JS by default, content collections fit `/docs` and `/errata` exactly, and the *one* heavy island is the procession. Next's server runtime buys nothing here and costs the LCP budget |
| **Console** | Next.js 15 RSC | **Vite + React 19 + TanStack Router/Query/Virtual**, served as static assets by the local process | RSC needs a Node server. Delivery model C has a *Python* process. A client app served from the wheel has no second runtime, works offline, and survives `pip install` |
| **API** | *(absent)* | **Litestar** (or FastAPI) over `errata_spec` | Litestar's msgspec serialization and DI are a better fit for pydantic-heavy payloads; FastAPI is the safer hire. Either way: **OpenAPI is generated, TS types are generated** |
| **Doc render** | PDF.js text layer | **PyMuPDF at ingest + AVIF tiles + word spans + SVG** (§5.3) | Deterministic, cacheable, offline, and it satisfies both FR-7.2 and L-6 instead of picking one |
| **Analytics views** | *(absent)* | **DuckDB-WASM over Parquet** | The Groundable Fraction Report, cost report and reliability curves aggregate millions of rows. DuckDB-WASM does that client-side with no backend — which is *exactly* the local-first posture, and it makes the public benchmark page interactive with zero server |
| **Tokens** | hand-written `tokens.css` | **DTCG JSON → Style Dictionary / Terrazzo** → CSS + TS + the gate | My `contrast.py` parses CSS with regex. That is a smell I introduced. Tokens should be data, with CSS as *one* output, so the gate, the TS types and any Figma sync read one source |
| **Motion** | GSAP + Lenis + Theatre.js | GSAP + Lenis; **replace Theatre.js** | GSAP is fully free now, Lenis is right. **Theatre.js has not had meaningful releases in a long time** — putting the camera authoring of the whole landing on a stalled dependency is a real risk. Author the camera as a typed keyframe module in the repo |
| **3D** | R3F v9 + TSL + WebGPU | **Keep.** Genuinely correct | TSL compiling to both WebGPU and WebGL2 is the reason this choice is right, not fashion. Budget must include *shader compile* time, not just frame time |
| **Component gallery** | Storybook | **Keep for the console**; `states.html` stays the diff target | Storybook earns its cost once components have real props and interaction tests. It does not earn it for 20 CSS skins |
| **Visual regression** | *(absent)* | Playwright screenshot diff on `states.html`, both themes, 3 viewports | The gate §13.5 already names a screenshot-diff target. Nothing runs it |
| **A11y** | axe (§15.2) | axe-core in Playwright **+ pa11y on static routes**, both themes, in `scripts/ci.sh` | §15.2 requires it. Nothing runs it. And it must live in `ci.sh`, not YAML — the repo's own rule that a pipeline existing only as YAML is a second definition of correct |

**One thing I would add that is nowhere:** a **frontend supply-chain job** mirroring the existing
`supply-chain` job — scanning the built bundle for ECLASS content (FR-9.8), for any inlined
third-party datasheet text, and for named-organisation strings (FR-8.6). The Python artifacts are
scanned. The JS artifacts are not, and they are the ones a browser will happily ship to anyone.

---

## 7. Five moves that are actually novel

Not "novel" as in unusual. Novel as in: derived from a blocker this repository actually has, and
not doable by a competitor who has not built the same domain model.

### 7.1 The queue is the calibration instrument — this unblocks gate 3

**The blocker:** `PHASES.md` P2 / gate 3 (FR-0.4, calibration coverage) is **deferred, unmeasured**,
because it needs SKU counts per ETIM class and *"three independent hunts found they are not
publicly published."* A data request is written and unsent.

**The observation, which `web.py` half-makes already:** FR-6.1 says calibration needs labels. Labels
are adjudications. **The console generates the exact data the blocked gate needs.**

**The move:** the queue does not rank purely by expected review value. It ranks by a two-objective
policy — *exploit* (highest blast radius, the reviewer's job) and *explore* (fills the class ×
attribute × confidence-bin cells calibration is missing). Then it **tells the reviewer**:

> These 18 decisions close the last gap in `EC000227` above 0.8 confidence.
> Calibration for this class becomes reportable at 41 of 60.

That converts a research gate blocked on a third party into a product loop that closes itself, and
it makes the reviewer a participant in the measurement rather than a subject of it. It is also the
single most defensible thing in this document, because the alternative is waiting for ETIM to
answer an email.

**Caveat, stated up front:** an actively-sampled label set is *not* an i.i.d. sample, and naive
calibration on it is biased. This needs inverse-propensity weighting and the sampling probabilities
must be recorded per decision. Doing this wrong produces a confidently wrong calibration curve,
which is worse than `NOT MEASURED`. **It is a research task with a product surface, not a feature.**

### 7.2 Abstention-first information architecture

R1 abstains on **1,196 of 1,426 records**. `Abstention` is a distinct type in the schema
specifically so downstream code cannot mistake it for a value. The blueprint's IA opens on a list
of findings — the same IA as every competitor.

**Open on FR-8.1 instead: the Groundable Fraction Report.** What we could not check, and why,
enumerable to record level. Findings are the *second* screen.

This is contrarian, it is a P0 with no design, and it is the honest inverse of a market where
everyone's dashboard is a wall of confident red. It is also the screen a buyer needs to size the
job before they trust a single finding — and the `DeclinedReason` taxonomy already exists to
populate it.

### 7.3 A real variable axis for the degradation system

Redaction ships as **discrete grades** — 0, 10, 20, 35, 50, 70, 100. The blueprint maps four of them
to four confidence bands by hand.

**The move:** build a variable font from the grades with `fontTools.varLib`, giving a continuous
`DGRD` axis, and drive it from the calibrated confidence. Type sharpness becomes a *continuous
readout of a real number*, which is (a) genuinely unprecedented on the web and (b) **compliant with
FR-7.5**, because a font grade is not a bare confidence percentage.

Three constraints, all real:
- **OFL Reserved Font Name.** A modified Redaction must be renamed. Non-negotiable and cheap.
- **Accessibility.** A visual-only encoding of a number fails WCAG 1.4.1. It needs a text
  equivalent — which FR-7.5 pushes you toward anyway, in the sentence.
- **It must be measured, not asserted.** Does a reviewer actually read grade as confidence? That is
  a user-research question and it belongs in FE-3, with five people and a card sort.

### 7.4 The bundle as the deliverable (§5.2)

Restated here because it is the commercial one. The industry ships *findings*. Shipping a
**portable, hash-verifiable evidence object** that a manufacturer can open with no account is a
different product category, and it falls straight out of a domain model that already has
content-addressed document revisions and canonical payload digests.

### 7.5 Signed adjudications (§5.5)

The ledger already claims to be immutable. Signatures make that claim *checkable by the customer*
rather than promised by the vendor — which is the same move the product makes about catalog data,
applied to itself. For a verification company, not doing this is close to a contradiction.

---

## 8. How a company actually runs this

The research track here has an unusually strong operating model — gates, entry/exit criteria,
written waivers (D-1…D-6), ground rules, a CI job that runs the reproduction on a machine nobody
controls. **The frontend has none of it**, and it is not because frontend is different. It is
because nobody wrote it.

### What is missing at the process level

| Missing | Why it bites here specifically |
|---|---|
| **Frontend ADRs** | `docs/adr/` has three, all backend. Q1 (delivery model), the determinism boundary, the bundle format and the coordinate system are all ADR-shaped and all undecided |
| **An API design review** | The contract in §5.1 is the highest-leverage artifact in the project and there is no forum that would review it |
| **A threat model** | The console shows Customer A's catalog beside Manufacturer B's copyrighted document. Delivery model B makes that our liability. Nobody has drawn the trust boundary |
| **A product-surface performance budget** | §11.9 budgets the landing. The console is the thing that runs for three hours and is measured in reviewer-seconds |
| **A failure taxonomy → UX map** | `DeclinedReason` is an enum in the schema. Every value needs a designed empty/declined state. That mapping is a one-day exercise nobody has scheduled |
| **A "definition of ready"** | FE-2's DoD is excellent (§19). There is no *entry* checklist — which is exactly how twenty components got built against a §13.2 that contradicts FR-7.5 |
| **Design ↔ requirement traceability** | Every component should cite the FR it discharges. Mine cite blueprint sections. The blueprint cites nothing |
| **Research cadence** | Zero user research in a 1,515-line document about a professional tool. The reviewer protocol proves the team *can* run a human study — that instrument should also be pointed at the UI |

### The operating model I would put in place

**Two-week cycles, three artifacts each, and one rule.**

1. **A decision record** — at least one ADR closed per cycle, from the Q1–Q6 stack.
2. **A measurement** — one number that did not exist before (a coordinate-projection error rate, a
   timed task, a bundle size at p95). The repo's own culture is that a gate closes on an artifact,
   not an assertion.
3. **A surface** — something a person can open.

**The rule, inherited and extended:** *a component may not merge without the requirement id it
discharges.* That single line would have caught C-2 before I wrote it.

**Roles this needs and does not name:** someone who owns the contract (§5.1) across Python and TS;
someone who owns the coordinate system, because it is the highest-consequence, lowest-glamour piece
of the product; and a domain reviewer on retainer, because FR-9.3 and FR-9.4 cannot be produced by
anyone who built the tool — the protocol says so and a test enforces it.

---

## 9. The restructured FE plan

FE-0…FE-9 as written phases *the visual system*. It cannot phase a product, because FE-7 "Product
build" is one line covering fifteen unaddressed P0s. Revised — same numbering, honest contents:

| | Was | Should be | Gate |
|---|---|---|---|
| **FE-0** | Concept | **+ Q1 answered as an ADR** | Delivery model decided in writing |
| **FE-1** | Schematic ✅ | done | ✅ met |
| **FE-2** | Design development ✅ | done, **with C-2 logged as a defect I introduced** | ✅ met, defect open |
| **FE-2.5** | — | **NEW · The contract.** OpenAPI off `errata_spec`, generated TS, bundle format v0, coordinate system spec | A round-trip: `errata-audit` → bundle → rendered box lands on the right words. Measured as projection error in px, not eyeballed |
| **FE-3** | Art | Art **+ the C-1 comp** (three marks, one chroma) **+ the five-person study for 7.3** | No untreated asset; C-1 resolved against FR-7.3's own criterion |
| **FE-4** | Motion prototype | unchanged, **+ the product motion budget (C-4)** | Camera approved blind |
| **FE-5** | Shader R&D | unchanged | Perf budget met before integration |
| **FE-6** | Landing build | Landing on Astro, **+ the frontend supply-chain scanner** | Works with `?nogl=1`; bundle scan clean |
| **FE-7** | Product build | **Split: 7a queue + adjudication + evidence overlay · 7b coverage, cost, calibration · 7c dual control + signing** | Keyboard-only run-through; **and a timed session that produces a real FR-9.3 number** |
| **FE-8** | Content | unchanged | Every figure links to its reproduction command |
| **FE-9** | Snagging | unchanged | The last 5% |

**FE-2.5 is the insertion that matters.** Everything from FE-7 onward is unbuildable without it,
and it is currently scheduled nowhere.

---

## 10. What I would do in the next ten working days

1. **Write ADR-004: the delivery model.** One page, three options, a recommendation, a decision.
   Nothing else on this list is safe to start first. *(Owner: product + founder.)*
2. **Write ADR-005: the determinism boundary.** Make the banned-import rule explicit as a layering
   law so `errata-api` can exist without eroding it. *(Owner: engineering.)*
3. **Spike the coordinate system.** PyMuPDF → raster → CSS px, one page, one attribute, and
   **measure the projection error in pixels** against the shipped console's boxes. This is the
   highest-risk unknown in the product and it is two days.
4. **Draft the Evidence Bundle v0 and generate the OpenAPI** from `errata_spec`. Do not design it —
   emit it and see what is ugly.
5. **Fix C-2.** Replace the queue table with the sentence row, in `states.html`, citing FR-7.5.
   It is my defect and it is half a day.
6. **Comp C-1.** Three marks, one chroma, on a real page image. Put it in front of a domain
   reviewer, not a designer.
7. **Wire the two CI gates that already exist but never run**: Playwright screenshot diff on
   `states.html` and axe on both themes, both into `scripts/ci.sh`.

---

### The short answer to "is it good?"

The art direction is genuinely top-tier and I would not change the thesis, the parti, the
degradation axis or the palette architecture. **The problem is not quality; it is scope.** A
document that decides typography to four decimal places and does not decide whether the product has
a server is not 80% done — it is one excellent half of a two-half problem, and the missing half is
the one with the P0s in it.

The good news is unusual: **the hard part is already built.** `errata_spec` is a better domain model
than most products ship with, the ledger design is right, abstention is a type, provenance is
content-addressed, and there is a CI job that reproduces the numbers on a machine nobody here
controls. The frontend does not need to invent any of that. **It needs to stop being designed as
though none of it exists.**
