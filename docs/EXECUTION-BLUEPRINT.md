# ERRATA — REMEDIATION AND FINAL-EXECUTION BLUEPRINT

**Version:** 1.0 · **Written:** 21 August 2026
**Supersedes:** nothing. **Amends:** `docs/frontend/FE-TEST-REGISTER.md` (§1 below).
**Scope:** every open defect, gap and unverified claim across backend and frontend, each with a
named fix, a named owner role, a verification step, and a phase.

## How to read this document

This is an *execution* document, not a survey. Every item below has four fields and none of them
is optional:

| Field | Meaning |
|---|---|
| **Evidence** | The file, line, or measurement that establishes the item is real |
| **Fix** | What to change, concretely enough to start |
| **Verify** | The automated check that proves it and keeps proving it |
| **Non-degradation** | What must NOT get worse as a side effect |

The fourth field exists because this codebase's failure mode is not sloppiness — it is *trading
one honest thing for another*. `MIN_CONTRAST` moved from 1.5 to 1.25 to make a measurement pass.
That was the right call and it is still exactly the shape of the mistake to watch for. **No item
in this plan is complete if it closes by weakening the check that caught it.**

**Standing rule, inherited from the register and reaffirmed here:** a gate that has never failed
has not been shown to work. Every gate introduced by this plan ships with a deliberately broken
fixture proving it fails.

---

## 1. CORRECTIONS TO THE TEST REGISTER

Two claims in `FE-TEST-REGISTER.md` do not match the code. Both are corrected here, and the
register should be amended rather than left to be rediscovered.

### C-A · Security headers are NOT absent — three of four are set

The register §4.3 states the console server sets *no* `Content-Security-Policy`,
`X-Content-Type-Options`, `X-Frame-Options` or `Referrer-Policy`.

**Evidence:** [web.py:888-893](audit/src/errata_audit/web.py:888) sets `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, and a restrictive CSP (`default-src 'none'`).

**The real finding is narrower and still worth fixing:**
1. `X-Content-Type-Options: nosniff` is genuinely **missing** — the one of the four that is absent.
2. The CSP carries `script-src 'unsafe-inline'` and `style-src 'unsafe-inline'`, which is the
   weakest clause in an otherwise tight policy and defeats the main thing CSP buys.

This correction *reduces* the severity of the finding. It is recorded because a register that
overstates a gap is the same defect as one that understates it.

### C-B · The entire frontend is untracked in git, not merely un-gitignored

The register §8 says `web/landing/` build output "is committed to the working tree and is not
gitignored".

**Evidence:** `git ls-files web docs/frontend bundle` returns **0 files**. `git status` shows
`web/`, `bundle/`, `docs/frontend/` and `docs/FRONTEND-BLUEPRINT.md` as untracked.

**The finding is substantially worse than reported.** ~700 KB of design system, console, procession
and the entire `errata_bundle` package exist only in one working tree, on one machine, with no
history, no review trail, and no recovery from a mistaken `git clean`. Every defect in this
document is unfixable by anyone else until this is resolved. **This is now P0 item one.**

---

## 2. PHASE PLAN

Eight phases. Each has an entry condition, an exit gate that is *mechanised*, and an explicit
statement of what it does not do. Phases P0–P2 are sequential; P3–P6 may run in parallel once P2
lands; P7 is the release gate.

| Phase | Name | Gate to exit | Blocks |
|---|---|---|---|
| **P0** | Preserve and pin | Everything committed; `ci.sh` green from clean clone | all |
| **P1** | Stop the bleeding | Two latent critical defects fixed with failing-first tests | release |
| **P2** | Build the verification layer | Frontend suite exists and runs in `ci.sh` | P3–P6 claims |
| **P3** | Decide what is undecided | Q1–Q6 answered as ADRs | FE-7b, tenancy |
| **P4** | Acquire what is missing | Fonts landed, subset, metrics measured | design judgement |
| **P5** | Measure what is unmeasured | Perf + a11y + cross-browser numbers recorded | §11.9 claims |
| **P6** | Build what is unbuilt | FR-8.1 and the calibration path | product claims |
| **P7** | Release gate | Full checklist §2.8 green | shipping |

---

## PHASE P0 — PRESERVE AND PIN

*Entry: now. Nothing else in this plan is safe to start before P0 completes.*

### P0-1 · Commit the frontend and `bundle/` — **critical**

**Evidence:** §1 C-B above. 0 tracked files across `web/`, `bundle/`, `docs/frontend/`.

**Fix:**
1. Add build output and dependency directories to `.gitignore` *first*, so the commit does not
   capture 132 packages of `node_modules` or a stale `web/landing/` build:

```
# Frontend
web/app/node_modules/
web/app/dist/
web/landing/
```

2. `web/landing/` is build output of `web/app/`. Ignore it, do not commit it — the register is
   right that a committed build artifact drifts from its source the first time someone edits one
   without rebuilding. If the deployed landing page is currently served from `web/landing/`, that
   is a deployment step, and it belongs in the build, not the tree.
3. Commit in **reviewable slices**, not one 700 KB drop: `bundle/` (a Python package with tests),
   then `web/datum/` (the design system), then `web/console/`, then `web/site/`, then `web/app/`,
   then `docs/`.
4. Delete `web/still-water/index.html` in its own commit with the message recording that it is
   superseded — 34 KB of dead prototype that is currently *served*.

**Verify:** `git status --short` is clean except for intentional work. A fresh `git clone` into a
new directory, followed by `bash scripts/setup.sh && bash scripts/ci.sh`, passes.

**Non-degradation:** do not `git add -A`. `var/`, `blobs/` and `*.pdf` are gitignored under FR-9.5
for licensing reasons — a careless `-f` flag would commit a manufacturer's copyrighted PDF into
permanent history, which is a legal problem no revert fixes.

### P0-2 · Pin the frontend toolchain

**Evidence:** `web/app/package.json` uses caret ranges throughout (`^19.2.0`, `^0.185.0`,
`vite ^8.2.0`). The lockfile pins today; a fresh `npm install` on another machine does not.

**Fix:** commit `package-lock.json` (P0-1 covers it), and make CI use `npm ci` exclusively —
never `npm install`. Record the Node version: **v24.13.0**, npm **11.6.2** in an `.nvmrc` and in
the workflow's `setup-node`.

**Verify:** CI step P2-1 runs `npm ci` and fails on a lockfile that does not match `package.json`.

### P0-3 · Run the dependency audit that has never been run

**Evidence:** register §4.3 — 132 npm packages, `npm audit` never executed.

**Fix:**

```bash
cd web/app && npm audit --omit=dev --audit-level=high
```

Record the result — including "0 vulnerabilities" — in `docs/frontend/SECURITY-BASELINE.md`.
A clean audit that nobody wrote down is indistinguishable from one nobody ran.

**Verify:** the same command becomes a gating CI step (P2-1). Advisory-only for `dev`
dependencies, gating for runtime dependencies.

**Non-degradation:** do not run `npm audit fix --force`. It resolves advisories by taking major
version bumps across a react-three-fiber/three.js stack whose versions are coupled to each other;
the procession would break in ways no current test would catch. Triage each advisory by hand.

**P0 exit gate:** clean clone → `setup.sh` → `ci.sh` → PASS, on a machine that is not this one.

---

## PHASE P1 — STOP THE BLEEDING

*Entry: P0 complete. Two latent critical defects in shipped Python. Both are latent, not dormant:
each has a named future trigger already inside the frozen split.*

### P1-1 · B-4 / O-7 — the G-1 rotation bug in shipped code — **critical**

**Evidence:** [console.py:59-70](audit/src/errata_audit/console.py:59) — `PageImage.place`
multiplies `x * zoom` against `self.width`/`self.height`. `page.get_text("words")` returns boxes in
**unrotated** user space while `page.rect` and the rendered pixmap are in **rotated** space
([geometry.py:33-43](bundle/src/errata_bundle/geometry.py:33) documents this in detail). On a
`/Rotate 90` page every evidence box lands on the wrong part of the page.

The fix already exists in `errata_bundle.geometry` and was **not** back-ported to the console.

**Fix:** do not copy the arithmetic — *delete* it. `errata_audit.console` should import the
projection from `errata_bundle.geometry` so there is exactly one implementation of the coordinate
system in the repository. Two implementations is how this defect happened; a second copy of the
correct arithmetic reproduces the cause while fixing the symptom.

Add `errata-bundle` as a dependency of the `audit` package in `pyproject.toml`.

**Verify — failing-first, in this order:**
1. Write a test that renders the `rotated_90` fixture through `errata_audit.console` and asserts a
   known word's box lands within tolerance. **Confirm it fails** against current code.
2. Make the import change. Confirm it passes.
3. Add the same fixture to the console's own test module so the gate has a permanent home.

**Non-degradation:** the current arithmetic is correct for unrotated pages, which is the entire
current corpus. The regression test must cover **both** — a rotation fix that breaks the 0° case
trades a latent defect for a live one.

### P1-2 · B-5 / G-2 — OCR-over-scan is never declined — **critical**

**Evidence:** [layout.py:145](audit/src/errata_audit/layout.py:145) — `TextLayer.is_born_digital`
returns true for any extracted word. `H28-1957-Part-I.pdf` is 100% image area carrying an OCR
layer and reports **161,731 words**. `layout.py`'s own scope statement says such documents should
be declined. Their evidence boxes cannot land.

**Fix — and this one needs a decision record before code.** Changing the predicate changes measured
coverage, and measured coverage is a published number. Sequence:

1. **Write `ADR-004-born-digital-predicate.md` first.** It must state: the current predicate, the
   proposed one, the corpus-wide delta in coverage, and the argument for why the new number is more
   honest than the old one even if it is lower.
2. Proposed predicate: born-digital requires extracted words **and** an image-area ratio below a
   threshold. The threshold is a measured value, not a guess — derive it from the corpus by finding
   the separation between known born-digital and known scanned documents, and record the
   distribution in the ADR.
3. Documents failing the predicate are **declined with a named reason**, surfaced to the user, not
   silently dropped. A declined document is a result, not an error.
4. Re-run `errata-r3 reproduce` and publish the new numbers alongside the old, with the ADR as the
   explanation.

**Verify:** a test asserting `H28-1957-Part-I.pdf` is declined; a test asserting a known
born-digital document is *not*; and `errata-r3 reproduce` regenerating the receipt.

**Non-degradation:** this is the highest-risk item in the plan for exactly one reason — a threshold
that declines too much makes coverage look worse and the temptation will be to tune it back. The
ADR is the guard. **If the threshold moves after the ADR is signed, that is a new ADR, not an
edit.** This is the `MIN_CONTRAST` lesson applied prospectively.

### P1-3 · O-11 — the redline message names a decision the reviewer did not make

**Evidence:** register §5 — `errata_spec.redline` refuses `keep_catalog` on a safety class and the
message says *"acceptance"*.

**Fix:** correct the message to name the actual refusal. Low effort, medium severity: a message
that attributes a decision to a reviewer who did not make it is an integrity defect in a product
whose entire pitch is provenance.

**Verify:** a test asserting the message text for the safety-class refusal path.

### P1-4 · `X-Content-Type-Options` and the CSP `unsafe-inline` clause

**Evidence:** §1 C-A above.

**Fix:**
1. Add `self.send_header("X-Content-Type-Options", "nosniff")` alongside the existing three at
   [web.py:888](audit/src/errata_audit/web.py:888).
2. Remove `'unsafe-inline'` from `script-src`. This requires moving inline scripts in the console
   to external files or adopting a per-response nonce. The nonce is the smaller change and keeps
   the console's single-file-serving model intact.

**Verify:** a test asserting all four headers on a representative response, and asserting the CSP
string does not contain `unsafe-inline` in `script-src`.

**Non-degradation:** the console must keep working with `default-src 'none'`. Tightening CSP until
the page silently breaks in a browser nobody tested is a real risk here — pair this with P2-3's
Playwright smoke test, which fails on console errors, so a CSP violation becomes a test failure
rather than a discovery in production.

**P1 exit gate:** all four fixes merged, each with a test that was observed to fail first.

---

## PHASE P2 — BUILD THE VERIFICATION LAYER

*Entry: P1 complete. This is the phase that makes every other claim in the project durable. Until
it lands, every frontend statement decays from the moment it is written.*

**The asymmetry to close:** 1,335 tests cover the domain; **0** cover what a user touches.

### P2-1 · Wire the frontend into `scripts/ci.sh` — **critical**

**Evidence:** `scripts/ci.sh` contains no reference to `web/`, npm, `lint-tokens.py`, or
`contrast.py`. Both design gates can be broken by any commit with nothing noticing.

The repo's own rule, from `ci.sh`'s header comment, governs the shape of this fix: *"A CI pipeline
that is a YAML file nobody can execute is a second, invisible definition of correct."* These steps
belong in `ci.sh`, invoked by the workflow — never defined in the workflow.

**Fix — add a section 4 to `scripts/ci.sh`,** following the existing `step` helper so failures
accumulate and are named at the end rather than aborting on the first:

```bash
# ---------------------------------------------------------------------------------------------
# 4. The frontend
# ---------------------------------------------------------------------------------------------

step "design -- token lint"      "$PY" web/datum/tools/lint-tokens.py
step "design -- contrast law"    "$PY" web/datum/tools/contrast.py
step "frontend -- install"       bash -c 'cd web/app && npm ci'
step "frontend -- typecheck"     bash -c 'cd web/app && npx tsc --noEmit'
step "frontend -- build"         bash -c 'cd web/app && npm run build'
step "frontend -- unit"          bash -c 'cd web/app && npm run test:unit'
step "frontend -- npm audit"     bash -c 'cd web/app && npm audit --omit=dev --audit-level=high'
step "frontend -- e2e + axe"     bash -c 'cd web/app && npm run test:e2e'
```

Guard the npm steps on `command -v npm` the same way the measured gates guard on `var/` — a Python
contributor without Node should get a skip with a named reason, not a failure.

**Verify:** break a token deliberately; confirm the build fails and names the step. Restore.
Do this for each of the eight steps. **A gate that has never failed has not been shown to work.**

### P2-2 · Vitest on `lib.ts` — the cheapest high-value tests in the project

**Evidence:** `actOpacity` ([Overlay.tsx:36](web/app/src/Overlay.tsx:36)) shipped with the same
off-by-one at *both* ends (FE-6 D-4). A three-line unit test catches it before a screenshot does.

**Fix:** add `vitest`. Cover `damp`, `span`, `ease`, `actOpacity`, `tier`.

For `actOpacity` specifically, test the **boundaries**, which is where it failed:
`t == from` → 0, `t == to` → 0, midpoint → 1, outside the range → 0, and `from == to` (degenerate).

For `tier`, test the ladder that has never executed on real hardware (H-5): `deviceMemory <= 4`,
`hardwareConcurrency <= 4`, and `webgl2 === null` all reaching `lite`. These are pure functions of
injected capability values — the fact that no available machine triggers them is precisely why
they need unit tests rather than hoping for hardware.

**Verify:** `npm run test:unit` in `ci.sh`. Coverage of `lib.ts` reported, not gated.

### P2-3 · Playwright smoke per surface

**Fix:** one spec per surface — `web/datum` (grid, room-i, states), `web/console`, `web/site`,
`web/app`. Each asserts: page loads, **zero console errors**, **zero failed network requests**
(with the known-missing fonts allow-listed *by name* until P4 closes, then the allow-list is
deleted), and key elements present.

The console-error assertion is what makes P1-4's CSP tightening safe.

**Verify:** in `ci.sh` via `test:e2e`.

### P2-4 · Screenshot diff on `states.html`

**Evidence:** §13.5 of the blueprint explicitly designates this page as the CI diff target. It has
never been diffed.

**Fix:** Playwright's `toHaveScreenshot` across 21 components × 2 themes × 3 viewports. Generate
baselines **only after P4** (fonts) — baselines captured in fallback faces will need wholesale
regeneration the moment Redaction lands, and a mass baseline update is indistinguishable from a
mass regression.

**Interim, before P4:** run the diff with fonts explicitly disabled so the baseline is stable and
intentional, and label the baseline directory `fallback/`. After P4, add a `specified/` baseline
set. Keep both — the fallback rendering is what a user with a failed font request sees, and it
should not be allowed to rot.

**Non-degradation:** a screenshot suite that is updated by reflex (`--update-snapshots` on every
red) is worse than none, because it launders regressions as intent. Require a human diff review in
the PR.

### P2-5 · axe-core on every route, both themes

**Evidence:** §15.2 makes this a required gate. Never run.

**Fix:** `@axe-core/playwright`, every route, both themes, gating on serious and critical
violations.

**Verify:** in `ci.sh`. Record the *first* run's findings verbatim in
`docs/frontend/A11Y-BASELINE.md` before fixing anything — the delta between first run and gate is
the honest measure of what was wrong.

**Non-degradation:** do not achieve axe-clean by suppressing rules. Every disabled rule needs a
written reason in the config, reviewed like code. Contrast is currently the project's one a11y
claim with real evidence — it must remain measured, not asserted.

### P2-6 · Test the JavaScript bundle verifier — **it is the one a customer relies on**

**Evidence:** H-3. `errata_bundle.verify` has Python tests including tamper detection. The
JavaScript verifier in `console.js` has **none**. Byte-digest interop is tested in one direction
only (Python writes, `sha256sum` agrees); nothing asserts the browser computes the same value.

**Fix:** port the Python tamper-detection suite to Vitest against the JS verifier, case for case.
Then add the missing interop direction: a fixture bundle written by Python, verified in a real
browser context under Playwright, asserting the *same digest string*.

This is the highest-value item in P2 after P2-1. A verifier that has never been tested is a claim,
and this product sells claims-with-evidence.

### P2-7 · Implement the nine components whose keyboard contracts are comments

**Evidence:** H-2 / FE-2 O-5. `Select`, `Menu`, `Modal`, `Drawer`, `Tabs` and others have their
keyboard contracts **written in comments and not in code**. `ThemeToggle` is the only fully
implemented one.

**Fix:** implement roving tabindex, focus trap and restore, `Esc` handling, and arrow-key
navigation per the documented contracts. Each component's contract comment becomes its test's
assertion list — the comment is already the specification, so transcribe rather than reinvent.

**Verify:** Playwright keyboard tests per component. This is what converts H-1's SMOKE to PASS:
real tab order across all three panes, focus return after dialog close, focus visibility at every
stop, and `Esc` from nested states.

**P2 exit gate:** `bash scripts/ci.sh` on a clean clone runs Python **and** frontend gates, and
each of the eight new steps has been observed to fail when deliberately broken.

---

## PHASE P3 — DECIDE WHAT IS UNDECIDED

*Entry: parallel with P2. These are not engineering tasks; they are decisions that engineering is
currently making by default, silently, every day.*

**No frontend ADRs exist.** `docs/adr/` holds three, all backend. Every item below is ADR-shaped.

### P3-1 · Q1 — delivery model — **critical, blocks everything**

Local tool vs hosted SaaS vs split. Downstream: auth, tenancy, data residency, and the copyright
posture of holding customers' catalogs beside manufacturers' PDFs — which is a legal question, not
an architectural one.

**Fix:** `ADR-005-delivery-model.md`. Owner: product + founder. This has been decided by default
since the blueprint was written; the ADR's job is to make the default explicit or replace it.

### P3-2 · Q3 — the time model — **expensive to retrofit**

Every view is as-of a revision, a policy and a fingerprint. Retrofitting temporality into a system
that assumed the present tense is among the most expensive changes in software. It costs least
today and more every week.

**Fix:** `ADR-006-time-model.md`, before FE-7b starts.

### P3-3 · Q6 — locale — **a correctness issue, not polish**

**Evidence:** register §4.4. ETIM is multilingual; the customers are European. If the source says
`16,0 A` and the UI renders `16.0 A`, that is a **transformation of evidence**. If it renders
`16 A`, that is a **lost significant figure**. Both are integrity failures in a provenance product.

The proposed rule — evidence rendered byte-exact and never localised, derived values localised — is
written down and neither implemented nor tested.

**Fix:** `ADR-007-locale-and-evidence-fidelity.md` ratifying the rule, then implement it, then test
it with a decimal-comma fixture. This is P3's only item with code attached, and it should be
treated as a correctness bug rather than an i18n feature.

**Verify:** a test asserting a `16,0 A` source value renders byte-exact in the evidence pane and
localised only in derived displays.

### P3-4 · Remaining decisions

| | Question | ADR | Owner |
|---|---|---|---|
| Q2 | Where ranking runs; frozen ranking snapshot | 008 | engineering |
| Q4 | Reviewer identity, cryptographically (FR-8.9) | 009 | product + eng |
| Q5 | Offline for 3-hour sessions | 010 | engineering |
| FE-0 Q2 | Which extractor leads the benchmark | 011 | product + research |
| FE-0 Q3 | Does `/errata` publish before launch | 012 | product |

### P3-5 · Sign FE-0, and mechanise traceability

**Evidence:** register §8. FE-0 is **unsigned** — everything since was built on a direction nobody
formally approved (waiver D-FE-4). The cost of a rejection rises sharply once FE-3's thirty plates
depend on it.

**Fix:** sign it or amend it. Separately, mechanise the rule *"no component merges without the
requirement id it discharges"* — currently written after defect C-2 and enforced by nobody. A
lint rule over component headers requiring an `FR-` or `FE-` id is sufficient and cheap.

### P3-6 · Resolve the standing contradictions

- **O-4:** blueprint §8.1 says Datum at column 5; §8.3 says the split is at column 10. Two
  different lines, both stated as governing. One must yield, in writing.
- **E-1…E-6:** six errata against §5.5, §6.3, §6.7. `tokens.css` and the blueprint still disagree
  and **no v1.1 has been issued.** Issue it. A blueprint that disagrees with the code is a document
  that has stopped being consulted.
- **O-2:** `--edge-strong` at 1.19:1 in light — decoration or UI boundary is undecided, and the
  answer determines whether it is a contrast violation or not.
- **C-1:** the three-mark legend resolving L-1 vs FR-7.3 is implemented and **never judged by a
  domain reviewer**. Get the judgement.

---

## PHASE P4 — ACQUIRE WHAT IS MISSING

*Entry: parallel with P2. The oldest open item in the project — cited in five consecutive reports.*

### P4-1 · The three type families — **it is a download**

**Evidence:** `web/datum/fonts/README.md`. All three specified families are absent. Every page under
`web/datum/` renders in fallback. Consequences: the semantic degradation axis — *the single most
distinctive decision in the design system* — **has never been seen by anyone**; `DiffPair`'s entire
argument is unrendered; §5.3's `size-adjust` metrics are unmeasured, so **no CLS number may be
quoted**.

All three are SIL OFL 1.1. **There is no licence cost and no licence blocker.**

| Family | Source | Cuts |
|---|---|---|
| **Redaction** | <https://www.redaction.us/> | `0`, `20`, `20 Italic`, `50`, `100` — all Regular |
| **Apfel Grotezk** | <https://www.collletttivo.it/> | Regular, Mittel, Fett, **Brukt** |
| **Sligoil** | <https://velvetyne.fr/fonts/sligoil/> | Regular, Micro |

Target layout is specified in the fonts README; `styles/type.css` already declares every
`@font-face` against exactly those paths. **Dropping the files in is the whole integration.**

**Fix — the five steps, none optional:**

1. **Fetch**, and record what was actually downloaded (version, date, source URL) in the README's
   acquisition log. The URLs above are the blueprint's addresses and have not been verified from a
   machine.
2. **Subset and convert** — Latin + Latin-1 Supplement + the punctuation the site uses. Install the
   tooling:

```bash
pip install fonttools brotli
```

   Then per cut:

```bash
pyftsubset Redaction_50-Regular.otf --output-file=Redaction_50-Regular.woff2 --flavor=woff2 --layout-features='*' --unicodes=U+0000-00FF,U+2000-206F,U+2190-21FF,U+2212
```

   Keep full-range originals out of the served directory.
3. **Measure the fallback metrics.** §5.3 is a **law**: every `@font-face` carries `size-adjust`,
   `ascent-override` and `descent-override` tuned to its fallback so the swap causes zero layout
   shift. These are currently marked `<MEASURE>` in `type.css` and are **absent, not approximated**.
   Produce them from the real files.
4. **Do not quote a CLS number until step 3 is done.** The 0.00 CLS budget is a target. Publishing
   it as measured is precisely the failure FR-9.1 exists to prevent.
5. **Ship the OFL.** SIL OFL 1.1 requires the licence to travel with the fonts. Add each family's
   `OFL.txt` verbatim and list all three in `NOTICE`.

**Verify:** a CI check asserting each declared `@font-face` path resolves to a file, and that no
`size-adjust` value remains `<MEASURE>`. Then P2-3's font allow-list is **deleted** — a missing
font becomes a test failure rather than a known exception.

**Non-degradation — the one that matters most in this phase:** **do not substitute silently.** If a
face turns out to be unavailable, that is a change to blueprint §5.2 and needs the same written
argument as any other blueprint change — not a quiet swap in `tokens.css`.

### P4-2 · Re-judge the design once the type is real

Not a formality. The FE-1 Room I comp and the FE-2 specimen were approved in fallback faces.
Until Redaction is present, the difference between a verified value and an unverified one is
carried entirely by **colour and strike-through** — a weaker system than the one specified.

**Fix:** re-review both, formally, and record whether the degradation axis works. It may not. That
is a finding, and finding it is the point.

---

## PHASE P5 — MEASURE WHAT IS UNMEASURED

*Entry: P2 complete — measurement without a suite to keep it honest decays immediately.*

### P5-1 · Performance — nothing is measured

**Evidence:** §11.9 states budgets as "spec, not aspiration". **Not one has been recorded.**
FE-5's actual gate — *perf budget met before integration* — **is not met**; materials were
integrated first (FE-6 O-14; D-FE-10 waives FE-4's blind-grey approval).

**Fix — record all of it, even where the number is bad:**

| Metric | How |
|---|---|
| Frame time on the procession | Playwright trace, 60s scripted scroll |
| **Shader compile time** | `performance.mark` around program link |
| LCP, CLS, INP | Lighthouse CI in `ci.sh` |
| Bundle budget | `size-limit`. Initial is 77.6 KB gzipped with **no stated ceiling** — state one |
| 150k-point fill rate | Integrated graphics, explicitly |
| Memory | Render target + PMREM environment + 150k-point buffers, profiled |

Console responsiveness at 1.2M rows (FE-7 O-12) waits on a queue that does not exist yet — record
that as deferred with its blocker named, not as absent.

**Verify:** budgets in `ci.sh` as gating steps once a first measurement establishes a defensible
ceiling. **Set the ceiling from the measurement, not from the aspiration** — a budget nobody can
meet gets switched off within a week, which is the same reasoning `ci.sh` already applies to mypy.

**Non-degradation:** a bundle ceiling must not be met by lazy-loading something the first paint
needs. Pair every budget with P2-3's smoke test.

### P5-2 · Cross-browser and device — one Chromium build is not a matrix

**Evidence:** H-4. Named at genuine risk:
- **Safari:** `container-type: size` + `cqh` (the evidence text layer), `mask-image` on the
  blacklight, `backdrop-filter` on the lens, View Transitions
- **Firefox:** View Transitions API support, `@property` on `--decohere`
- **Touch:** the blacklight lens is `pointermove`-driven with **no touch path**
- **Mobile:** the console's stacked layout has never been opened on a phone

**Fix:** Playwright projects for WebKit and Firefox in `ci.sh`. Add a `pointerdown`/`touch` path to
the lens. Then **one real device**, by hand — emulation does not surface the touch-target and
scroll-momentum problems that a phone does. Measure the 44px touch targets that are coded and
never verified.

### P5-3 · Reduced motion and the capability ladder

**Evidence:** H-6, H-5. `prefers-reduced-motion` changes Lenis, `frameloop`, act cross-fades, the
mark pulse, skeleton animation, toast entrance and View Transitions. **None verified under the
actual media query.**

**Fix:** Playwright `emulateMedia({ reducedMotion: 'reduce' })` asserting each of the seven. The
capability ladder is covered by P2-2's unit tests, plus one integration test forcing `lite`.

### P5-4 · Print — the artifact is meant to be printed

**Evidence:** §4.6. No print stylesheet anywhere. An Evidence Bundle is **the artifact you send a
supplier in a dispute**, and nobody has looked at what it does on paper.

**Fix:** a print stylesheet for the bundle and record views: evidence boxes visible, provenance
footer with digest and revision on every page, no clipped columns, no dark-theme ink flood.

**Verify:** Playwright PDF render in `ci.sh` plus a screenshot diff of page one.

### P5-5 · Probe thresholds — provenance, and two unresolved failures

- **H-7:** `MIN_COVERAGE = 0.02`, `MIN_CONTRAST = 1.25`
  ([probe.py:101](bundle/src/errata_bundle/probe.py:101)), `MAX_OFFSET_PX = 10`,
  `DARK_THRESHOLD = 160`, `agreement >= 0.6`. `MIN_CONTRAST` was **moved from 1.5 to 1.25 after it
  rejected 80% of good words**. Right change, right reason — still a threshold moved to make a
  measurement pass, which needs an independent reviewer, not the author.
  **Fix:** an independent review recorded in an ADR, with the rejected-word distribution attached.
- **H-8:** `abb-s200muc` p2 — a born-digital page at 54% agreement against a 60% bar, modal offset
  `(0,0)`. Two candidate fixes named in FE-2.5 O-8, **neither tested**. Test both. Do not move the
  bar.
- **H-9:** `ISO-261` modal offsets `(0,-10)` and `(0,-5)` — **`-10` is the edge of the search
  window**, so the true peak may lie outside it. **Unexplained.** Re-probe with a wider window;
  this is a half-day and it is currently an unknown in a measured system.

### P5-6 · Privacy — the telemetry requirement has no consent surface

**Evidence:** §4.5. FR-9.3 requires **instrumenting a human**, which is privacy-sensitive by
nature. There is no telemetry plan, no consent surface, and no data-retention policy for bundles
under `var/`.

**Fix:** this is blocked on P3-1 (delivery model) — consent and retention mean different things
for a local tool than a hosted one. Sequence it immediately after Q1 lands, and do not instrument
anyone before it exists.

---

## PHASE P6 — BUILD WHAT IS UNBUILT

*Entry: P2 complete, P3-1 decided. **45 of 59 FR requirements have no surface.** This phase does
not close that gap — it closes the part of it that changes what may honestly be claimed.*

Prioritised by what the product cannot honestly say without it:

### P6-1 · FR-8.1 — the Groundable Fraction Report

**Arguably the product's most important screen, and it does not exist.** It is the honest opening
statement: here is what fraction of this catalog can be grounded in evidence, and here is what
cannot. A provenance product whose first screen is anything else is burying its own thesis.

### P6-2 · FR-8.7 — tiered execution T0→T3 and the cost report

**The commercial argument.** Without it the pricing conversation has no artifact.

### P6-3 · FR-8.8 — batch reversal as a query, demonstrated on 1,000 records

The claim that a bad decision is reversible is currently unbacked by a demonstration.

### P6-4 · FR-6.x — calibration

**Blocked, and honestly so.** No calibration page exists because **R0 gate 3 (FR-0.4) was never
measured** — deferred (D-1), needing SKU counts per ETIM class that three hunts could not find.
The proposal to unblock via the queue's own adjudications (FE-SYSTEM-REVIEW §7.1) is untested and
carries real statistical risk: **the queue's adjudications are not an i.i.d. sample**, because the
queue is ranked. Using them as one would produce a calibration curve that is confidently wrong,
which is worse than no curve.

**Fix:** treat R0 gate 3 as a research task with a named owner, not a frontend blocker. Until it is
measured, the calibration page must not exist — a calibration surface built on a non-i.i.d. sample
is the exact failure this product was built to expose.

### P6-5 · The remaining unbuilt pages

`/method`, `/benchmark`, `/errata`, `/pricing`, `/docs`, `/app/calibration`, `/app/sources`,
`/app/settings`, `/500`, `/app/record/:id` as a route, and `/app/_states` (exists as `states.html`,
not routed).

**Sequence `/500` first** — it is the cheapest and it is the page that runs when everything else
has already gone wrong.

### P6-6 · What the marketing surfaces may NOT say

**This constrains P6-1, P6-2 and `/benchmark` directly.**

**Evidence:** register §7. **R0 gate 2 is measured but the asymmetry is not confirmed** — 46.34% vs
ExtractBench's 46.4% is a **dead heat**, and the 46.34% belongs to a **table-blind baseline, not
the shipped extractor**.

**Rule:** any surface implying the shipped extractor beat ExtractBench makes a claim **the repo's
own README refuses to make.** Encode this as a review checklist item on every marketing page, and
name it in the ADR for FE-0 Q2.

Also open: **R2's exit criterion** (the corpus is not public, D-4) and **R3's** (no third party has
reproduced the numbers, D-5). Both are half-open and both are load-bearing for the benchmark page.

---

## PHASE P7 — RELEASE GATE

Nothing ships until every line below is green. Ordered by what it costs to be wrong about — this
is the register's §9 list, expanded with the items P0 and P1 added.

**Status as of 22 August 2026.** ✅ done · ⚠️ partly done, gap named · ❌ open.

| # | Gate | Phase | Status |
|---|---|---|---|
| 1 | Everything committed; clean clone builds | P0 | ✅ 59 files tracked, `ci.sh` green |
| 2 | Frontend test suite exists and runs in `ci.sh` | P2 | ✅ 435 tests, 9 CI steps |
| 3 | G-1 rotation and OCR-decline fixed, with failing-first tests | P1 | ✅ both, observed failing first |
| 4 | Q1 answered as an ADR | P3 | ✅ ADR-005 |
| 5 | axe clean both themes every route **+ one real screen-reader pass** | P2/P5 | ⚠️ axe clean; **no screen reader has ever been used** |
| 6 | §11.9 budgets recorded — bad numbers beat none | P5 | ⚠️ 7 recorded; **shader compile still unmeasured**, CLS not quotable |
| 7 | Fonts landed, metrics measured, **design re-judged** | P4 | ⚠️ 10/11 faces, metrics measured & gated; **nobody has judged the degradation axis** |
| 8 | Safari, Firefox, **one real phone** | P5 | ⚠️ all 4 projects green in CI; **no physical device** |
| 9 | FR-8.1 (Groundable Fraction Report) built | P6 | ❌ not built |
| 10 | Every marketing claim checked against §P6-6 | P6 | ✅ `/benchmark` states the dead heat and the table-blind provenance |

**Three gates are ⚠️ for the same reason: a human has not looked.** A screen
reader, a phone, and a design judgement on type that can now be seen for the
first time. None of them is blocked on engineering, and none of them can be
closed by more automation — which is why they are listed as open rather than
quietly counted as done.

---

## 3. THE BACKEND↔FRONTEND SEAM

The seam is where this project's defects concentrate, and the pattern is consistent: **the same
concept implemented twice, diverging.** G-1 is that (`console.py` vs `geometry.py`). The bundle
verifier is that (Python tested, JavaScript not). The blueprint-vs-`tokens.css` errata are that.

Three rules, each of which would have prevented a defect already in this register:

1. **One implementation of the coordinate system.** `errata_bundle.geometry` is canonical. Nothing
   else projects a box. (Would have prevented G-1.)
2. **Every cross-language invariant is tested in both directions.** Python writes → JS reads, and
   the digest is asserted equal. One direction is not interop, it is a coincidence waiting to end.
   (Would have caught H-3.)
3. **The contract is a fixture, not a document.** FE-2.5 describes the bundle format in prose.
   Prose does not fail a build. Generate a golden fixture from the Python writer, commit it, and
   have both the Python and JavaScript verifiers assert against it.

---

## 4. NON-DEGRADATION CHARTER

Applies to every item in this plan without exception.

1. **No threshold moves to make a measurement pass.** If a gate fails, the finding is the failure.
   Moving the bar requires an ADR with the distribution attached and an independent reviewer.
   (`MIN_CONTRAST` 1.5→1.25 is the precedent, and it is the one everyone will cite as permission.)
2. **No gate lands without being observed to fail.** Break it deliberately, watch it go red,
   restore. Undemonstrated gates are comments with a test framework attached.
3. **No baseline is bulk-updated.** Screenshot and a11y baselines change one reviewed diff at a
   time.
4. **No silent substitution.** Fonts, extractors, thresholds, defaults — a substitution is a
   blueprint change with a written argument.
5. **No claim outruns its evidence.** CLS stays unquoted until measured (P4-1 step 4). Benchmark
   superiority stays unclaimed until asymmetry is confirmed (P6-6). Coverage numbers change when
   the born-digital predicate changes, and both are published (P1-2).
6. **Measured coverage may go down.** P1-2 will probably reduce it. A number that drops because
   the measurement got more honest is a success, and it must be reported as one — internally and
   externally — or the next person will quietly avoid making the measurement better.

---

## 5. WHAT THIS PLAN DOES NOT DO

Stated so nobody mistakes the omissions for oversights:

- **It does not build 45 requirements.** P6 builds four families and names why the rest wait.
- **It does not close R0 gate 3.** That is a research task needing data three hunts did not find.
- **It does not make the corpus public** (R2 D-4) or **obtain third-party reproduction**
  (R3 D-5). Both need an external party.
- **It does not resolve FE-0 Q4 (audio)** — the register itself records that it blocks nothing.
- **It does not adopt `ruff format`.** `ci.sh` already argues this correctly: 85 of 178 files would
  be rewritten and every real change would be buried. That is its own commit, on its own day.
- **It does not turn mypy gating.** Same reasoning, already recorded in `ci.sh`. Advisory is the
  right posture until someone works the backlog down deliberately.

---

## 6. HONEST SUMMARY

What is built is real: measured contrast, a measured coordinate system, a working adjudication loop
against the real ledger, a five-room procession that costs nothing when disabled, and four gates
that have each been shown to fail when they should.

What is missing is the **entire verification layer around it**, plus — newly established in §1 —
**version control around any of it**.

The register's own finding stands and is now sharper: 1,335 tests cover the domain, zero cover what
a user touches, and until P0 lands none of the frontend exists anywhere but one working tree. On a
product whose thesis is that unverified data is the problem, that asymmetry is not an engineering
detail. It is the thing the product would flag about itself.

**P0 and P2 are the whole plan. Everything else is downstream of being able to prove a claim twice.**
