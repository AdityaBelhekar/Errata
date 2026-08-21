# FE — TEST REGISTER AND OPEN-ITEM LEDGER

**Written:** 21 August 2026.
**Purpose:** everything that is not done, not verified, or verified weakly — in one place, ranked
by what it would cost to be wrong about.
**Standing rule:** a gate that has never failed has not been shown to work. Where a "pass" below
rests on a single manual observation, it is labelled **SMOKE**, not PASS.

---

## 0. The headline numbers

| | Measured | Comment |
|---|---:|---|
| Python tests | **1,335 passing** | Real coverage of the domain |
| **Frontend automated tests** | **0** | No Playwright, no Vitest, no axe run, no visual diff |
| **CI steps touching the frontend** | **0** | `scripts/ci.sh` has no reference to `web/`, npm, or either design gate |
| PRD requirements (FR-*) | **59** | |
| …referenced by a built surface | **14** | |
| …**with no surface at all** | **45** | §3 lists them |
| Browsers tested | **1** | One Chromium pane, one viewport family |
| Frontend perf measurements | **0** | §11.9's budget has never been recorded |

**The single most important line in this table is the second one.** Every frontend claim in every
gate report — including the ones I wrote — rests on manual observation in one browser, on one
machine, on one day. That is a demo, not a test suite.

---

## 1. BLOCKERS — things that make a release impossible

### B-1 · No frontend test suite exists
**Severity: critical. Owner: engineering.**

Zero automated tests across `web/datum`, `web/console`, `web/site`, `web/app`. Everything asserted
in FE-1, FE-2, FE-2.5, FE-6 and FE-7 was verified by me looking at it once.

Minimum to close:
- **Playwright** smoke per surface: loads, no console errors, no failed requests (excluding the
  known-missing fonts), key elements present.
- **Screenshot diff on `states.html`** — 21 components × 2 themes × 3 viewports. §13.5 explicitly
  designates this page as the CI diff target and nothing has ever diffed it.
- **`axe-core`** on every route, both themes. §15.2 makes this a required gate; it has never run.
- **Vitest** on `lib.ts` — `damp`, `span`, `ease`, `actOpacity`, `tier`. `actOpacity` shipped with
  the same off-by-one at *both ends* (D-4 in FE-6) and a three-line unit test would have caught it
  before it reached a screenshot.

### B-2 · CI does not build or check the frontend
**Severity: critical. Owner: engineering.**

`scripts/ci.sh` runs the Python suite, the licence scan and the reproduction receipt. It does not:
run `lint-tokens.py`, run `contrast.py`, run `errata_bundle probe`, `npm ci && npm run build`, or
serve anything. **Both design gates I built can be broken by any commit and nothing will notice.**

The repo's own rule applies here — *"a pipeline that only exists as YAML is a second definition of
correct"* — so these belong in `ci.sh`, invoked from the workflow.

### B-3 · Delivery model still undecided (Q1)
**Severity: critical. Owner: product + founder.**

Local tool vs hosted SaaS vs split. Everything downstream — auth, tenancy, data residency, the
copyright posture of holding customers' catalogs beside manufacturers' PDFs — hangs on it. It has
been made by default, by nobody, every day since the blueprint was written.

### B-4 · `errata_audit.console` still carries the G-1 rotation bug
**Severity: critical (latent). Owner: engineering.**

`PageImage.place` computes `x * zoom`. On a `/Rotate 90` page every evidence box lands on a
different part of the page. Cannot fire on the current corpus; **FR-9.6 names fold-outs as part of
the frozen hard-tail split**, so it will fire. Fixed in `errata_bundle.geometry`, **not** in the
shipped console. (FE-2.5 O-7.)

### B-5 · OCR-over-scan documents are never declined
**Severity: critical (latent). Owner: engineering + research.**

`TextLayer.is_born_digital` is true for any extracted word. `H28-1957-Part-I.pdf` is 100% image
area with an OCR layer and reports **161,731 words** — nothing declines it, and its evidence boxes
cannot land. `layout.py`'s own scope statement says such documents *should* be declined. Changing
this changes measured coverage, so it needs a decision record. (FE-2.5 G-2.)

---

## 2. HIGH — verified weakly, or verified once

### H-1 · "Keyboard-only run-through passes" is SMOKE, not PASS
FE-7's gate. I drove it once with synthetic `KeyboardEvent`s from the console. Never tested:
real tab order across all three panes, focus return after dialog close, focus visibility at every
stop, screen-reader announcement order, `Esc` from nested states, or the roving-tabindex behaviour
the components document but do not implement (FE-2 O-5).

### H-2 · Nine components are styled but not behaviourally implemented
`Select`, `Menu`, `Modal`, `Drawer`, `Tabs` and others have their keyboard contracts written in
comments and not in code. `ThemeToggle` is the only fully implemented one. (FE-2 O-5.)

### H-3 · The client-side bundle verifier is untested
`errata_bundle.verify` has Python tests including tamper detection. The **JavaScript** verifier in
`console.js` has none — and it is the one a customer would rely on. The byte-digest interop is
tested in one direction only (Python writes, `sha256sum` agrees); nothing asserts the browser
computes the same value.

### H-4 · No cross-browser or device testing
Everything ran in one Chromium build. Untested and at genuine risk:
- **Safari**: `container-type: size` + `cqh` (the evidence text layer), `mask-image` on the
  blacklight, `backdrop-filter` on the lens, View Transitions.
- **Firefox**: View Transitions API support, `@property` on `--decohere`.
- **Touch**: the blacklight lens is `pointermove`-driven with no touch path; the console has no
  touch target audit.
- **Mobile**: the console degrades to a stacked layout that has never been opened on a phone.

### H-5 · `?nogl=1` is verified; the *capability* ladder is not
The explicit switch works (0 canvases, 0 engine bytes). The `lite` tier — triggered by
`deviceMemory <= 4` or `hardwareConcurrency <= 4` — has **never been exercised**. Neither has the
`webgl2 === null` path. Both are code that only runs on hardware nobody has tested on.

### H-6 · Reduced motion is implemented and never verified end-to-end
`prefers-reduced-motion` changes: Lenis off, `frameloop="demand"`, act cross-fades, the mark pulse,
skeleton animation, toast entrance, View Transitions. Verified: none of it, under the actual media
query.

### H-7 · Probe thresholds have weak provenance
`MIN_COVERAGE = 0.02`, `MIN_CONTRAST = 1.25`, `MAX_OFFSET_PX = 10`, `DARK_THRESHOLD = 160`, and
`clean` requiring `agreement >= 0.6`. Each is documented with a rationale, but `MIN_CONTRAST` was
**changed from 1.5 to 1.25 after it rejected 80% of good words** — that is a threshold moved to
make a measurement pass, which is exactly the failure mode the file warns about elsewhere. It
happened to be the right change for the right reason; it still needs an independent look.

### H-8 · One born-digital page fails the projection gate and the threshold was *not* moved
`abb-s200muc` p2: modal offset `(0,0)`, agreement 54% against a 60% bar. Unresolved by design —
two candidate fixes named in FE-2.5 O-8, neither tested. Right call, still an open failure.

### H-9 · `ISO-261` registers at the search boundary
Modal offsets `(0,-10)` and `(0,-5)` — `-10` is the edge of the search window, so the true peak may
lie outside it. Never re-probed with a wider window. **Unexplained.** (FE-2.5 O-9.)

---

## 3. REQUIREMENTS WITH NO SURFACE — 45 of 59

Referenced by a built surface: FR-7.1–7.6, 7.8, 7.9, 8.4, 8.5, 8.9, 9.1, 9.3, 9.4.

**Never built, by requirement family:**

| Family | Missing | What it is |
|---|---|---|
| **FR-0.x** (4) | 0.1–0.4 | The R0 kill-gate results — no surface publishes them |
| **FR-1.x** (6) | 1.1–1.6 | Ingest, fetch, document register, text layer, column bands |
| **FR-2.x** (4) | 2.1–2.4 | ETIM class resolution, top-1/top-5 accuracy, class allow-list |
| **FR-3.x** (4) | 3.1–3.4 | Value semantics, units, tolerances, compound values |
| **FR-4.x** (6) | 4.1–4.6 | The open-source value-semantics library and its packaging |
| **FR-5.x** (5) | 5.1–5.5 | Disagreement taxonomy, severity, blast radius model |
| **FR-6.x** (3) | 6.1–6.3 | **Calibration** — no calibration page exists at all |
| **FR-7.7** | 1 | OCR-layer toggle, raw-page jump, **document revision history** |
| **FR-8.1** | 1 | **Groundable Fraction Report** — arguably the most important screen |
| **FR-8.2** | 1 | Claim-ledger browser with `supersedes` chains |
| **FR-8.3** | 1 | Resolution policy as a versioned document |
| **FR-8.6** | 1 | Named-organisation signature prohibition |
| **FR-8.7** | 1 | Tiered execution T0→T3 + **cost report** — the commercial argument |
| **FR-8.8** | 1 | **Batch reversal as a query**, demonstrated on 1,000 records |
| **FR-9.2** | 1 | The five unscored axes |
| **FR-9.5–9.9** | 5 | Gold set, frozen split, ETIM↔UNSPSC bridge, ECLASS adapter, **leaderboard** |

Blueprint pages specified in §12 and **not built**: `/method`, `/evidence`, `/benchmark`,
`/research`, `/docs`, `/pricing`, `/errata`, `/500`, `/app/calibration`, `/app/sources`,
`/app/settings`, `/app/record/:id` (as a route), `/app/_states` (exists as `states.html`, not routed).

---

## 4. NON-FUNCTIONAL — untested categories

### 4.1 Performance — **nothing measured**
§11.9 states budgets as "spec, not aspiration". Not one has been recorded:
- Frame time on the procession · shader **compile** time · LCP, CLS, INP
- Bundle budget compliance (initial is 77.6 KB gzipped; no stated ceiling to compare against)
- 150k-point fill rate on integrated graphics
- Console responsiveness with the 1.2M-row queue that does not exist yet (FE-7 O-12)
- Memory: three's render target, PMREM environment and 150k-point buffers are never profiled

**FE-5's actual gate — "perf budget met *before* integration" — is not met.** Materials were
integrated first. (FE-6 O-14, and D-FE-10 waives FE-4's blind-grey approval.)

### 4.2 Accessibility — specified, never audited
§15 requires WCAG 2.2 AA and axe-clean on every route in both themes.
- axe: **never run** · Screen reader: **never used** · Keyboard: one scripted pass
- Contrast: **measured and passing** — the one a11y claim with real evidence
- Untested: focus order, `aria-live` politeness in practice, reduced-motion, zoom to 200%,
  Windows High Contrast, the `role="document"` text layer's actual reading experience,
  touch target sizes (44px is coded, never measured)

### 4.3 Security — no headers, no audit
The console server sets **no** `Content-Security-Policy`, `X-Content-Type-Options`,
`X-Frame-Options` or `Referrer-Policy`. Path traversal *is* checked. No auth by design (stated), but:
- **132 npm packages installed, never audited** (`npm audit` has not been run)
- No Subresource Integrity, no dependency pinning beyond the lockfile
- No threat model exists for a console that displays a customer's catalog beside a
  manufacturer's copyrighted PDF

### 4.4 Internationalisation — absent
No message catalogue, no `lang` strategy beyond `lang="en"`, no RTL, no pseudo-locale.
**Q6 is unresolved and it is a correctness issue, not a polish one:** ETIM is multilingual and the
customers are European. If the source says `16,0 A` and the UI renders `16.0 A` that is a
transformation of evidence; if it renders `16 A` that is a lost significant figure. The proposed
rule — evidence rendered byte-exact and never localised, derived values localised — is written down
and **not implemented or tested**.

### 4.5 Privacy and data handling
No telemetry plan. FR-9.3 requires instrumenting a human, which is privacy-sensitive by nature and
has no consent surface. No data-retention policy for bundles under `var/`.

### 4.6 Print
No print stylesheet anywhere. An Evidence Bundle is meant to be the artifact you send a supplier in
a dispute; nobody has looked at what it does on paper.

---

## 5. OPEN DEFECTS — logged, not fixed

| id | Where | What | Severity |
|---|---|---|---|
| **O-7** | `errata_audit.console` | G-1 rotation bug unfixed in shipped code | **critical, latent** |
| **G-2** | `errata_audit.layout` | OCR-over-scan never declined | **critical, latent** |
| **O-8** | probe | One born-digital page at 54% agreement vs 60% bar | high |
| **O-9** | probe | `ISO-261` peak may be outside the search window | high |
| **O-11** | `errata_spec.redline` | `keep_catalog` refused on safety-class, and the message says *"acceptance"* — it names a decision the reviewer did not make | medium |
| **O-4** | blueprint §8.1 vs §8.3 | Datum at column 5, split at column 10 — two different lines, both stated as governing | medium |
| **O-2** | tokens | `--edge-strong` at 1.19:1 in light; decoration or UI boundary is undecided | medium |
| **O-3** | `site.css` | Room I scene values exempted from the colour law | low, tracked |
| **C-1** | console | Three-mark legend resolves L-1 vs FR-7.3 — **implemented, never judged by a domain reviewer** | medium |
| **E-1…E-6** | blueprint | Six errata against §5.5, §6.3, §6.7 — `tokens.css` and the blueprint still disagree; **no v1.1 issued** | medium |

---

## 6. OPEN QUESTIONS — blocking, unanswered

| | Question | Blocks | Owner |
|---|---|---|---|
| **Q1** | Delivery model: local / hosted / split | everything | product + founder |
| **Q2** | Where ranking runs; frozen ranking snapshot | FE-7b queue at scale | engineering |
| **Q3** | The time model — every view is as-of a revision, policy and fingerprint | FE-7b; **expensive to retrofit** | engineering |
| **Q4** | Reviewer identity, cryptographically | FR-8.9 in any real deployment | product + eng |
| **Q5** | Offline for 3-hour sessions | FE-7b | engineering |
| **Q6** | Locale vs L-4 | correctness | product |
| **FE-0 Q1** | Type licensing — confirm libre tier | FE-3 | brand |
| **FE-0 Q2** | Which extractor leads the benchmark | FE-8 | product + research |
| **FE-0 Q3** | Does `/errata` publish before launch | FE-6, FE-8 | product |
| **FE-0 Q4** | Audio | nothing | brand |

---

## 7. DEPENDENCIES ON THE RESEARCH TRACK

These are not frontend items but they gate what the frontend may honestly display.

- **R0 gate 3 (FR-0.4) — NOT MEASURED.** Deferred (D-1); needs SKU counts per ETIM class that three
  hunts could not find. **FE-6's calibration page cannot be built without it.** The proposal to
  unblock it via the queue's own adjudications (FE-SYSTEM-REVIEW §7.1) is untested and carries a
  real statistical risk (non-i.i.d. sampling).
- **R0 gate 2 — MEASURED, ASYMMETRY NOT CONFIRMED.** 46.34% vs ExtractBench's 46.4% is a dead heat,
  and the 46.34% belongs to a **table-blind baseline, not the shipped extractor**. Any marketing
  surface that implies otherwise is a claim the repo's own README refuses to make.
- **R2 exit criterion half open (D-4)** — the corpus is not public.
- **R3 exit criterion half open (D-5)** — no third party has reproduced the numbers.
- **P1 item 1.2** needs a person; **1.12** blocked on standards access.

---

## 8. PROCESS AND HOUSEKEEPING

- **FE-0 is unsigned.** Everything since was built on a direction nobody formally approved
  (waiver D-FE-4). The cost of a rejection rises sharply once FE-3's thirty plates depend on it.
- **No design↔requirement traceability enforcement.** The rule *"no component merges without the
  requirement id it discharges"* was written after defect C-2 and is not mechanised.
- **No ADRs for any frontend decision.** `docs/adr/` holds three, all backend. Q1, the determinism
  boundary, the bundle format and the coordinate system are all ADR-shaped and none exists.
- **`web/still-water/index.html` is dead code** — 34KB of superseded prototype still served.
- **`web/landing/` build output is committed to the working tree** and is not gitignored; it will
  drift from `web/app/` the first time someone edits one without rebuilding.
- **No release/versioning story** for the frontend relative to the Python wheels.
- **Fonts** (FE-1 O-1) — Redaction, Apfel Grotezk, Sligoil still absent. Consequences: the semantic
  degradation axis has **never been seen by anyone**; `DiffPair`'s entire argument is unrendered;
  §5.3's `size-adjust` metrics are unmeasured so **no CLS number may be quoted**; and this is now
  the oldest open item in the project, cited in five consecutive reports.

---

## 9. WHAT I WOULD GATE A RELEASE ON

In order. Nothing below the line ships without the things above it.

1. **B-1 + B-2** — a frontend test suite, running in `ci.sh`. Until then every claim decays.
2. **B-4 + B-5** — the two latent critical defects in shipped Python.
3. **B-3 (Q1)** — the delivery model, in an ADR.
4. **4.2** — axe clean, both themes, every route; one real screen-reader pass.
5. **4.1** — record the §11.9 budgets. Even bad numbers beat none.
6. **O-1** — get the fonts. It is a download, and it has blocked a design judgement for five reports.
7. **H-4** — Safari and Firefox, at minimum, plus one real phone.
8. **FR-8.1** — the Groundable Fraction Report. The product's honest opening screen does not exist.

---

## 10. Honest summary

What is built is real: measured contrast, a measured coordinate system, a working adjudication loop
against the real ledger, a five-room procession that costs nothing when disabled, and four gates
that have each been shown to fail when they should.

What is missing is **the entire verification layer around it** — which is an uncomfortable thing to
report on a product whose pitch is that unverified data is the problem. 1,335 tests cover the
domain; zero cover the thing a user touches. That asymmetry is the finding of this register.
