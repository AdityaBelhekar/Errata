# FE-2 · DESIGN DEVELOPMENT — gate report

**Phase deliverable (§18):** the datum grid, 20 core components, both themes, all
states.
**Gate:** *nothing enters DD without a token.*
**State: 🟢 GATE CRITERION MET — three items open, named in §6.**

---

## 1. The gate, discharged literally

The gate is a single sentence and it is machine-checkable, so it was checked by
machine rather than asserted:

```
python web/datum/tools/lint-tokens.py
```

| Check | Law | Result |
|---|---|---|
| Colour literals outside `tokens.css` | §17 | **pass** |
| Every `var()` resolves to a defined token | §6.1 | **pass** — 138 defined, 122 referenced, 0 dangling |
| Spacing outside the closed set | §8.5 | **pass** |
| Durations and curves outside the scale | §10.1–10.2 | **pass** |
| `outline:none` · scroll authority · frame-rate independence | §15 / §10.5 / §10.6 | **pass** |

`components.css` contains no colour, no off-scale space, no off-scale duration
and no third curve. Nothing entered DD without a token — including three things
that needed a token invented for them (§4).

---

## 2. What was built

| File | What it is |
|---|---|
| [`web/datum/styles/components.css`](../../web/datum/styles/components.css) | Twenty components |
| [`web/datum/states.html`](../../web/datum/states.html) | **The gate.** Every component × every state × both themes, on one page (§13.5) |
| [`web/datum/grid.html`](../../web/datum/grid.html) | The datum, the 16-column overlay, the 9/7, poché, the closed spacing set, the full type specimen, the live semantic layer |
| [`web/datum/index.html`](../../web/datum/index.html) | Entry point and the phase ledger, set in the system's own type |

### The states gallery is built so the two themes cannot drift

Twenty-one sections, **76 state cells**, cloned into two themes — **152 rendered
states** on one page.

Each component is defined **once**, in a `<template>`, and cloned into a light
pane and a dark pane. Duplicated markup would let one theme's markup diverge from
the other's — which is precisely the failure the page exists to catch. The panes
are theme *islands*, which works because `tokens.css` declares the semantic layer
on `[data-theme]` as well as on `:root` (FE-1 §1).

---

## 3. The twenty

| # | Component | The decision inside it |
|---:|---|---|
| 01 | `Button` | **Never signal-filled.** Signal means dispute, not "click me". Destructive is an edge and a word, never a fill — a filled crimson button would claim the button *is* the dispute |
| 02 | `IconButton` | 32px visual box, 44px hit area via a pseudo-element, so SC 2.5.8 is met without the box growing |
| 03 | `Input` | Value set in Sligoil with tabular figures: on this product an input usually holds a machine fact |
| 04 | `Select` | Native element, our skin. The ARIA combobox lands at FE-7 where it has real data — a fake one now is a component without a job |
| 05 | `Checkbox` | Indeterminate is a real state: a class is partly selected when some of its records are |
| 06 | `Radio` | The one legitimate circle in a system where radius is 0 or 3px |
| 07 | `Toggle` | Binary settings only, never filters. Square-ended, because 999px never |
| 08 | `Tabs` | Underline is `--text-1`, not signal — a selected tab is not a dispute |
| 09 | `Tooltip` | 400ms delay in CSS, so it survives without JS. Never carries the only copy of a fact |
| 10 | `Toast` | `role="status"`; the error variant takes `role="alert"` and the 2px reveal |
| 11 | `Modal` | Scrim, trap, `Esc`, focus returned |
| 12 | `Drawer` | Slides at `--m-slow`; under reduced motion it cross-fades — a designed alternative, not a disabled one |
| 13 | `Menu` | Shares its renderer with the `⌘K` palette. One list, two entry points |
| 14 | `DataTable` | Hover is **background only**: a row that jumps under the cursor makes a reader lose the line they were checking. Disputed rows get a *plane* of signal with a 2px edge on the datum side |
| 15 | `Confidence` | Five segments, **achromatic on purpose**. A green/amber/red bar would be the product telling you how to feel about a number it just asked you to check |
| 16 | `ProvenanceTag` | Its empty state is not blank — it prints "provenance missing" in signal. §7.4 is a LAW, and this component is where the LAW bites |
| 17 | `DiffPair` | The signature component: catalog value in Redaction 50 above evidence value in Redaction 0 |
| 18 | `DocumentView` + `SpanHighlight` | Paper in **both** themes. Real DOM, selectable spans, never an image-only render (L-6) |
| 19 | `SectionOpener` | Number in poché, hairline above, one `lead` per section and never a second |
| 20 | `ThemeToggle` | Three-state `radiogroup`, not a switch — a switch with three positions is a lie about its own affordance |
| 21 | `QueueRow` | **Added after the system review.** The row is a *sentence*, because FR-7.5 says so. Carries FR-8.4's four blast-radius factors separately and FR-8.5's computed cluster size. Abstention is a row state, not an empty state |

`Datum`, `Poche`, `ClaimEvidence`, `SkipLink`, `Header`, `Footer` and `HudFrame`
are in `base.css` and counted as **layout**, not components: they carry no state
of their own beyond what the page gives them.

### The state matrix, and where it is honestly incomplete

§13.5 is a LAW: default / hover / focus-visible / active / disabled / loading /
error / empty, both themes, plus a reduced-motion variant.

**Nine of the twenty do not have eight meaningful states**, and the gallery says
so in words on the page rather than leaving a hole or inventing a state to fill
one. A checkbox has no empty. A confidence readout has no hover — it is not a
control. A `SectionOpener` has no interaction to have states about.

| Component | States that are N/A, and why |
|---|---|
| `Button` | *empty* — a button with no label is a defect |
| `IconButton` | *empty*, *error* |
| `Select` | *loading*, *active* — native control |
| `Checkbox`, `Radio` | *loading*, *empty* (and *error* for Radio) |
| `Toggle` | *loading*, *error*, *empty* |
| `Tabs` | *error* — an errored panel is the panel's state, not the tab's |
| `Tooltip` | *loading*, *error*, *disabled*, *empty* |
| `Confidence`, `ProvenanceTag`, `DiffPair` | all interactive states — these are readouts |
| `SectionOpener` | everything but default |

Writing "N/A, because" is the whole discipline here. The alternative — a
disabled-state swatch for a component that cannot be disabled — is how a states
gallery becomes decoration.

---

## 4. Three tokens the components needed and the blueprint did not have

Each one is a case of the gate working: something wanted a raw value, and rather
than write one, it got named.

**`--signal-text`.** Carried over from FE-1 erratum E-1. Components that set
signal as *type* (error text, `.btn--destructive`, `u-signal`) reference this;
components that set signal as a *mark* (row wash, the 2px reveal) reference
`--signal`. Two jobs, two contrast targets, two tokens.

**`--d-tip` / `--d-toast`.** §13.1 specifies a 400ms tooltip delay and a 6s toast
dismissal. Neither is in §10.1's closed duration set, and neither should be: the
set governs **how long a thing takes to move**, and a delay is not a movement.
Naming them keeps the closed set closed while letting the components be built.

**`--m-collapse`.** The 120ms that §10.4 and the blueprint's own token file in
§20 both use for the reduced-motion collapse. It was a magic number in two
places; now it is one token in one.

---

## 5. D-FE-2 — built without the specified stack

§17 specifies Next.js 15 + Tailwind v4 + Radix + Storybook. **FE-1 and FE-2 were
built as framework-free HTML and CSS.** That is a deviation and it needs an
argument rather than a shrug.

**The argument.** FE-1's gate is *judge the direction before a shader exists*
and FE-2's is *nothing enters DD without a token*. Neither is a claim about a
framework. What both gates need is a token file, a type file and surfaces a
person can open — and a Next scaffold in front of those adds an install, a build
step and a bundler between a reviewer and the thing being reviewed, in exchange
for nothing either gate asks for.

**Why the deviation is cheap to reverse.** Tailwind v4's `@theme` consumes CSS
custom properties directly, so `tokens.css` ports verbatim — it is already the
shape Tailwind wants. `type.css` is `@font-face` and utility classes and ports
verbatim. `components.css` is plain CSS with no preprocessor syntax. Radix
supplies behaviour, and these components are skins, which is exactly the split
§17 describes.

**What is genuinely deferred, and it is not nothing:**

- **Storybook.** `states.html` is an equivalent, not a replacement. It has no
  controls, no args table and no interaction tests. It *is* a valid screenshot-
  diff target, which is the gate's stated use of it (§13.5).
- **Radix behaviour.** The keyboard behaviour of `Select`, `Menu`, `Modal`,
  `Drawer` and `Tabs` is **specified and styled but not implemented**. Focus
  traps, roving tabindex and type-ahead are FE-7 work.
- **Axe on the route.** §15.2 requires it in CI. Not wired.

**Recommendation:** stand the Next/Tailwind/Storybook scaffold up at the start of
**FE-6**, where the landing build genuinely needs RSC, routing and a bundler, and
port these three files into it rather than rewriting them.

---

## 5b. Defect C-2 — found after the gate, fixed

The FE-2 gate passed, and then reading `prd-errata.md` against what I had built
turned up a component that is not merely incomplete but **forbidden**.

> **FR-7.5 (P0).** *"Queue rows render as a sentence — values, source location,
> shared-pattern count, downstream propagation — **never a bare confidence
> percentage**. No UI surface displays a raw confidence score as the primary
> signal."*

Component 14's queue example ranked records in a `DataTable` with a
right-aligned `Conf.` column reading `0.86`, `0.91`, `0.97`. Blueprint §13.2
specified exactly that shape and I built it faithfully. **§13.2 is wrong, and the
PRD wins.**

**Fixed:** component 21, `QueueRow`. `DataTable` keeps its shape for the record
detail, the benchmark and the coverage report — it is a good component in the
wrong job. The queue is now prose, which also discharges two requirements that
had no design at all:

- **FR-8.4** — the four blast-radius factors render **separately**. "Each factor
  must be independently inspectable in the UI", because a reviewer shown one
  opaque score has been given a number, not a reason.
- **FR-8.5** — the cluster size ("1,240 SKUs share this signature") is presented
  as *computed*, never asserted.

Two further states came with it, and neither is in the blueprint: **declined**
(an `Abstention` is a distinct type in the schema, and R1 declines on the
majority of records — so it must not read as an empty state) and **awaiting a
second adjudicator** (FR-8.9's dual control, which needs an identity model the
project does not have — see `FE-SYSTEM-REVIEW.md` §4 Q4).

**The process failure this represents is more useful than the fix.** Twenty
components were built against blueprint sections, and blueprint sections cite no
requirements. **No component may merge without the requirement id it
discharges** — that one rule would have caught this before it was written.

---

## 6. Open items

### O-4 · The datum is at column 5; the split is 9/7. They are not the same line — **needs a decision**

§8.1 puts the datum at **column 5 of 16**. §8.3 splits every section **9 claim /
7 evidence**, which puts the split at **column 10**. Both are stated as governing
the same layouts, and they are two different vertical lines.

Built as specified: the datum is fixed at column 5 and `.claim-evidence` splits
9/7 at column 10. It reads coherently — the datum behaves as a *reading spine*
that content hangs off, and the 9/7 is a *content* proportion — but this is an
interpretation, not something either section says.

Three ways out, in order of preference:

1. **Keep both, and say so in the blueprint.** The datum is a spine, not a
   column boundary. Costs one paragraph in §8.1.
2. **Move the datum to column 10.** Makes the two lines one line. Costs the
   4/16 proportion, which is what makes the datum feel like a margin rule rather
   than a centre line.
3. **Change the split to 5/11.** Rejected: it inverts the hierarchy — evidence
   would dominate claim.

**Recommendation: (1).** Wants a brand call, not a frontend one.

### O-5 · Nine components are styled but not behaviourally implemented

Listed in §5. Every one of them has its keyboard contract written down in
`components.css` and in the gallery's spec notes; none is wired. `ThemeToggle` is
the exception — it is fully implemented in `theme.js`, arrow keys included,
because it is the one control both FE-1 and FE-2 actually need to work.

**This means the §19 line "keyboard path verified for every interaction" is NOT
yet true**, and FE-7's gate — a keyboard-only run-through — is the phase that
makes it true. Recording it here so nobody reads "20 components, all states" as
"20 components, all working".

### O-6 · The Redaction axis is still invisible

Carried from FE-1 O-1, and it lands hardest on `DiffPair` — component 17, the
one §13.2 calls the signature. Its entire argument is a degraded cut above a
clean one. With the fonts absent it renders as one face struck through, which is
a *weaker* component than the one specified, and it should be re-judged when the
files land rather than assumed to work.

---

## 7. What FE-2 hands to FE-3

- Twenty components with no colour, spacing, duration or curve outside their
  closed sets, both themes, on one screenshot-diffable page.
- A grid page that draws its own overlay from the same token the layout reads, so
  the two cannot disagree.
- Three new tokens, each named because something needed it.
- One blueprint contradiction (O-4) that needs a person.
- An honest count: **20 styled, 1 behaviourally complete**.
