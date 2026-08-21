# FE-7 · PRODUCT BUILD — gate report

**Phase deliverable (§18):** the product surfaces — queue, record, evidence, adjudication — plus
the public site that connects them.
**Gate:** *keyboard-only run-through passes; a real FR-9.3 number comes out.*
**State: 🟢 KEYBOARD RUN-THROUGH PASSES · decisions persist to the real ledger.**
Four items open, named in §7.

---

## 1. What the loop does now

Before this phase the console rendered evidence and could not adjudicate. That is not a small gap:
FR-7.1's criterion is that a reviewer *"adjudicates without leaving the screen"*, and a screen that
cannot accept a decision is a report with buttons drawn on it.

```
python -m errata_bundle serve
```

```
errata console   http://127.0.0.1:8099/web/console/
design system    http://127.0.0.1:8099/web/datum/
```

| Route | What it is |
|---|---|
| `/` → `/web/site/` | The landing. Room I, the 49-point gap, the method, our own errata |
| `/web/console/` | The three-pane reviewer console |
| `/web/datum/` | The design system, Room I comp, grid, states gallery |
| `/api/queue` | The bundle index **joined to the ledger's decisions** |
| `/api/bundle/<sku>/…` | Bundle files, path-traversal checked |
| `POST /api/adjudicate` | Rehydrates the `Redline` from the bundle and calls the real `Ledger.adjudicate` |
| `/api/session` | FR-9.3 aggregate, reported **per role and never pooled** |
| anything else | The designed 404 |

**The ledger is the real one.** Decisions go through `errata_audit.ledger.Ledger.adjudicate` — same
append-only file, same `supersedes` chains, same FR-8.9 rule enforced by `Redline` itself. A
console with its own decision store would be a second source of truth about what a human said,
which is exactly what ADR-001 and the ledger design exist to prevent.

**Verified end to end, in the browser:** blocked a single-signature accept, supplied the second
adjudicator, recorded it, saw `supersedes` come back, watched the queue advance to the next
undecided record and the progress bar move.

---

## 2. Requirement coverage

| Req | State |
|---|---|
| **FR-7.1** three panes: queue · evidence · claim | ✅ |
| **FR-7.2** word-level box at the stored projection | ✅ — measured, FE-2.5 §1 |
| **FR-7.3** headers shown with the value | ✅ — and it resolves contradiction C-1 (§4) |
| **FR-7.4** counter-evidence, never empty, never absent | ✅ |
| **FR-7.5** sentences, never a bare confidence | ✅ — no percentage appears in the queue pane |
| **FR-7.6** Accept · Keep catalog · Escalate, persisted immutably | ✅ **now writes to the ledger** |
| **FR-7.8** reconstructible, not regenerated | ✅ structurally — the console has no extractor |
| **FR-8.4** four blast factors, independently inspectable | ✅ |
| **FR-8.9** second named adjudicator | ✅ — and surfaced *before* the click (§3) |
| **FR-9.3** reviewer-seconds, timed, pauses on blur | ✅ — persisted, with both endpoint timestamps |
| **FR-9.4** evidence-acceptance, asked separately | ✅ — persisted |
| **L-2** paper in both themes | ✅ |
| **L-6** spans selectable at device resolution | ✅ |
| **L-7** works with the canvas deleted | ✅ **by construction** — there is no canvas |

---

## 3. The UX decisions, and what each one is answering

FR-9.3 measures the reviewer in **seconds**. That is not a metric to optimise afterwards — it is
the constraint the interface is designed against, and every decision below falls out of it.

**Prevent, do not validate.** `rated_current` is a safety-class attribute, so the domain model
*refuses* a single signature. Discovering that as a 422 after deciding would be a wall the reviewer
could have been shown. The console shows the requirement in the decision bar the moment the record
loads, collects the second name inline — not in a modal, which would break the flow — and blocks
the keystroke client-side with the reason.

**Land on the evidence, already legible.** An A4 page at readable zoom is four screens tall. On
load the console computes a zoom that makes the disputed value ~18px on screen and scrolls it to
0.38 of the viewport height. A reviewer who has to *find* and then *enlarge* the box pays for both,
in the metric the product is sold on.

**Three keys, always.** `j`/`k` move, `a`/`c`/`x` decide, `b` toggles the evidence answer, `f`
re-frames, `⌘K` opens the palette, `?` lists everything. Thirteen shortcuts, no mouse needed for a
full pass.

**Nothing reflows between records.** The pane tracks are fixed widths, not percentages: a longer
sentence in the queue must not resize the evidence pane, because a page that moves under the
reviewer costs a re-fixation on every single record.

**A decided row stays visible.** Dimmed, marked with who decided and how long it took, not removed.
Hiding it would make *"what did I already do"* unanswerable without changing filter.

**"Decide again", never "Undo".** The ledger is append-only. Changing your mind writes a new claim
that supersedes the old one, and calling the control *undo* would misdescribe the system it is
built on.

**The role is consequential, so the UI says so.** The identity dialog offers *domain reviewer* and
*implementer*, and states plainly that an implementer's decisions are **excluded** from the FR-9.3
rate — because `errata_ecosystem.reviewer` refuses them, and a console that recorded everyone
identically would hand that harness numbers it must throw away.

**Announced, not just shown.** A `role="status"` live region speaks every decision, navigation and
refusal. A keyboard-first tool that says nothing when it acts is only usable by people who can see
it act.

**The platform, not a dependency tree.** Native `<dialog>` for the focus trap, View Transitions for
record switching, container queries for the text layer, WebCrypto for verification, scroll-driven
CSS animations for the landing. Each replaces a library that would need auditing, bundling and
shipping inside a product whose README hook is that it runs from a clean clone with no signup.

> **Where a framework *would* earn its place** is FE-7b: the 1.2M-row virtual queue and the as-of
> time model. That is a real argument to have then, with the problem in front of us — not now, in
> advance of it. Recorded as D-FE-8 rather than left as a preference.

---

## 4. C-1, resolved in code

FR-7.3 wants the value's cell **plus its row and column headers in a second colour**; FR-7.4 adds
counter-evidence. Four adjacent marks. L-1 permits **one** chromatic event.

The implemented answer stops encoding the distinction in hue:

- **The value** — a signal plane with the 2px reveal. The only chroma on the page.
- **Its headers** — hairline **brackets with a leader rule** back to the value: the notation an
  engineering drawing uses to dimension a feature. Achromatic, and it survives greyscale printing,
  which a second hue does not.
- **Counter-evidence** — a **dotted** reveal. Anastylosis reversed: the fabric arguing back.

Both laws intact. **Still a proposal with an implementation, not a settled answer** — it needs
judging against FR-7.3's own criterion by a domain reviewer, not a designer.

---

## 5. Four defects found by wiring it up

### D-1 · Decisions were recorded and never shown — **the serious one**

The queue joined the ledger on the bundle's short attribute name (`rated_current`); the ledger
records `attribute_uri` (`etim:EF000227`). They never matched.

The failure mode is the worst kind: the decision **is** written, the queue simply never shows it,
so a reviewer re-decides work they already did and the second decision supersedes the first for no
reason. It looked like it worked — one older ledger row happened to carry the bare name, so exactly
one record showed as decided and the join looked fine.

Found by making a decision in the browser and watching the progress bar not move. Both spellings
are now indexed, with the trailing segment taken so a URI matches a bare key — the same
normalisation `errata_spec.taxonomy.is_safety_class` already does.

### D-2 · The reflection had been mirroring across the wrong edge since FE-1

`transform-origin: top center` with `scaleY(-1)` reflects across the element's **top** edge, so the
content is thrown *upward* and drawn over the real plate instead of under the waterline. It had
been doing that since the FE-1 comp and nobody saw it, because nothing clipped it and the two
plates overlapped almost exactly.

Clipping the reflection to a well made it obvious: the well sat at y=330 and the content rendered
at y=132, so the clip removed all of it and the hero's entire argument vanished. The default origin
mirrors content within its own box, which is where a reflection actually goes.

### D-3 · The join fix double-counted reviewer-seconds

Indexing one decision under several attribute spellings made `decisions()` a good lookup table and
a **bad population**: iterating its values yields the same adjudication two or three times, and
`session()` was iterating it. The result inflated the per-role reviewer-seconds — the one metric
the PRD calls the number a buyer actually pays for.

Caught by a test that asserted the per-role totals rather than merely that the endpoint returned
something. Counting now goes through `unique_decisions()`, deduplicated by event id.

Alongside it: `adjudicate` validated the `Redline` before checking that an actor was supplied, so a
missing name surfaced as a six-line pydantic dump about fields the reviewer has never heard of. The
human's inputs are checked first now. An error message is part of the interface.

### D-4 · The hero's own call to action was below the fold

At 1680×1000 the hero was 1175px tall; at 1280×800 it was 840px. Both CTAs sat under the fold —
the part of a hero it exists to offer.

Fixed by **recomposing** rather than shrinking one thing: at `max-height: 900px` the margins
tighten, the reflection well gets shallower, and the display cut steps down. A type scale that only
knows about viewport *width* is half a responsive type scale.

Also fixed on the way: an unhandled `InvalidStateError` on every overlapping View Transition
(holding `j` throws several a second), a `1400ms` skeleton pulse outside the motion scale, and
**Room I existing in two files** — `room-i.html` and the landing each carried a copy, which is two
definitions of one room and precisely the drift this project keeps finding elsewhere. One
definition now, two surfaces.

---

## 6. Gates

```
python web/datum/tools/lint-tokens.py     # 16 files — site, console and design system
python web/datum/tools/contrast.py
python -m errata_bundle probe
python -m pytest
```

| Gate | Result |
|---|---|
| Token lint — colour, spacing, motion, `var()`, a11y laws | **pass**, 16 files, 2 exemptions written down |
| Contrast — 20 pairs, worst ground, both themes | **pass** |
| FE-2.5 projection probe — born-digital | **pass**, modal offset `(0,0)`, 81.8% of words |
| Repository suite | **1335 passed** (+8 new: the D-1 and D-3 regressions) |
| HTML well-formedness, all 8 surfaces | **pass** |
| ruff · mypy | **clean** |

The lint now covers `web/site/` and `web/console/` as well as `web/datum/`. LAW §17 is repo-wide,
and a lint that only guards the design system's own files guards the place least likely to break.

---

## 7. Open items

### O-10 · Identity is a typed name, and that is not dual control

Two names typed at one keyboard are one signature wearing two hats. This is honest for a local
operator tool and **not sufficient for FR-8.9 in a real deployment**. The console says so on the
screen, next to the field. The cryptographic version — signed adjudications, WebAuthn or minisign —
is proposed in `FE-SYSTEM-REVIEW.md` §5.5 and is **not built**.

### O-11 · `keep_catalog` is refused on safety-class attributes, and the message is wrong

`Redline`'s validator requires a second signature for *any* adjudication of a safety-class
attribute, not only acceptance. That is arguably correct — overriding a finding that a safety value
is wrong is at least as consequential as accepting the correction — but **FR-8.9's wording is
"single-signature acceptance"**, and the error message says *"single-signature acceptance is
impossible"* even when the reviewer chose *keep catalog*. It names a decision they did not make.

Either the requirement's wording or the validator's message is wrong. **A product decision, not a
frontend one.**

### O-12 · The queue is not virtualised

Six bundles today; R2 is catalog-scale. Cursor pagination over a frozen ranking snapshot is
specified in `FE-SYSTEM-REVIEW.md` §5.6 and not built. This is the FE-7b work where a framework
earns its place.

### O-13 · Rooms II–V are not built

The landing is Act I only. Rooms II–V need FE-4 (camera in grey boxes, approved blind) and FE-5
(TSL materials, perf budget met before integration), and both have their own gates for good
reasons. The page is complete and coherent without them, and it satisfies L-7 **by construction**
because there is no canvas to delete.

The three typefaces are still absent (FE-1 O-1), so every surface renders in fallback and the
semantic degradation axis still carries no visual difference.
