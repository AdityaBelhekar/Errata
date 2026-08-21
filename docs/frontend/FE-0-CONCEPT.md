# FE-0 · CONCEPT — gate report

**Phase deliverable:** `docs/FRONTEND-BLUEPRINT.md` — design system **DATUM**,
art direction **THE STILL WATER**, v1.0.
**Gate:** *signed off by brand + product.*
**State: 🟡 PREPARED, UNSIGNED.**

---

## 1. What this phase honestly produced

The blueprint exists and is complete against its own table of contents: 21
sections, a post-mortem naming twelve specific failures of the prototype, a
thesis, a reference board, seven laws, a full type and colour system, a grid, a
motion grammar, a WebGL plan, every page in the sitemap, a component library, an
accessibility and performance budget, an execution plan and a token file.

**What FE-0 cannot produce is its own signature.** Its gate is a human decision
by two named functions, brand and product. That decision has not been taken, so
this phase is reported as prepared rather than passed — and FE-1 and FE-2 were
entered anyway, on the waiver recorded as **D-FE-4** in `FE-PHASES.md`.

That waiver is not free. Twenty components are now built on a direction nobody
has formally approved. The cost of a rejection at this point is roughly two days
of token and component work, which is small — and it will not stay small past
FE-3, when thirty treated plates start depending on the same direction.
**The signature is cheap now and expensive in a fortnight.**

---

## 2. The sign-off sheet

Reviewers named in the blueprint's own header: **brand, product, accessibility,
performance.**

| Reviewer | Question they are actually being asked | State |
|---|---|---|
| **Brand** | Is *"a dark mass, one raking light, warm paper, and a repair you are never allowed to stop seeing"* the thing we want to be? Is the degradation axis (§5.2) an argument or a gimmick? | ☐ unsigned |
| **Product** | Is **THE LIGHT TABLE** the right default for a three-hour triage task (§6.2)? Is *unease, then relief* (§2.2) the emotional beat we want, rather than awe? | ☐ unsigned |
| **Accessibility** | Are the §15 laws the right floor, and is WCAG 2.2 **AA** the right target rather than AAA? | ☐ unsigned |
| **Performance** | Are the §11.9 budgets real numbers or aspirations? | ☐ unsigned |

Two of the four have partial evidence already, produced during FE-1 and FE-2:

- **Accessibility** can review against measurements rather than promises. Twenty
  contrast pairs are asserted in CI, each against the *worst* ground its token
  may legally land on, in both themes. See `FE-1-SCHEMATIC.md` §3.
- **Brand** can review a real surface. `web/datum/room-i.html` is the Room I comp
  in both themes — with the caveat, stated on the page itself, that the three
  specified typefaces are absent and everything is rendering in fallback.

**Brand cannot fully sign until Redaction is present.** The degradation axis is
the single most distinctive decision in this system and nobody has seen it.

---

## 3. The blueprint's four open questions — recommendations

§21 closes with four questions for "the next review". This is that review.
These are recommendations with reasons, not decisions; each still needs the
owner named beside it.

### Q1 · Type licensing — *Redaction / Apfel Grotezk / Sligoil, or the paid tier?*

**Recommendation: stay on the libre tier, and treat the decision as closed.**

The paid alternative (Signifier + Söhne + Söhne Mono) is excellent and would make
this system read as a well-funded one. It would not make it read as *this*
product. Redaction is not a stylistic preference — it is a family whose entire
concept is a record degrading through reproduction, which is the subject of the
product. Söhne cannot say that. Nothing can, at any price.

The cost of staying libre is not zero: `size-adjust` and the ascent/descent
overrides must be measured by hand (§5.3 LAW), where a commercial foundry would
ship them. That is one afternoon.

**Owner: brand.** *Blocks FE-3.*

### Q2 · Which extractor's numbers lead the benchmark page?

**Recommendation: `tableblind` leads, `r1-textwindow` sits beside it, and `r1` is
printed with its own refusal attached.**

This is not a design question wearing a design hat. The repository's README
already answers it in prose — R1 scores 100% on grounding and the report refuses
to let anyone quote it, because gold is the cell under a named column and
`derive` prefers exactly that cell: the same act performed twice. A benchmark
page that leads with 100% is a benchmark page nobody outside this building will
believe, and §12.4's whole premise is a leaderboard that prints our own losses.

Design consequence, and it is a real one: the page needs a component that can
display **a number and its disqualification together**, without either burying
the number or making the disqualification look like an excuse. That component
does not exist yet and is not in FE-2's twenty. It should be specified at FE-8.

**Owner: product, with the research track.** *Blocks FE-8.*

### Q3 · Does `/errata` publish before launch or after?

**Recommendation: before, and it is a launch blocker rather than a nice-to-have.**

`/errata` is the page where the product applies its own ethic to itself. A
verification product that launches without a public record of its own
corrections is asking for a trust it has not extended. It needs three real
entries to be credible, and — usefully — **this phase has already produced six**:
the errata raised against the blueprint's own numbers in `FE-1-SCHEMATIC.md` §4.
They are small, technical and completely genuine, which is exactly the register
that page needs.

**Owner: product.** *Blocks FE-6 (the footer links to it) and FE-8.*

### Q4 · Audio in the procession?

**Recommendation: no audio in v1. Not off-by-default — absent.**

An off-by-default toggle still costs a Web Audio dependency, an autoplay-policy
path, a mute state in the HUD, a reduced-motion interaction nobody has designed,
and a decision about what happens when a user tabs away. That is real surface for
a feature whose upside is *atmosphere on a landing page* and whose downside is
*noise in an open-plan office on an enterprise laptop*.

If it returns, it returns at FE-9 as a snagging item, where it can be judged
against a finished procession rather than an imagined one.

**Owner: brand + product.** *Blocks nothing.*

---

## 4. One thing the blueprint gets wrong about itself

§18 calls the phase list "the way a practice phases a building", and it is right
about that. But it inherits an architectural assumption that does not survive
contact with this repository: **that concept is signed before schematic starts.**

In practice FE-1 changed the concept. Six of the blueprint's own numbers turned
out to be wrong when they were built and measured — three contrast pairs that
fail their stated targets, a hex column that disagrees with the OKLCH column
beside it by up to 21/255, and a tracking table that contradicts the tracking
curve on the previous page. None of those are visible from a document. All of
them are visible from a token file.

That is not an argument against gates. It is an argument that **FE-0's gate
should be signed against FE-1's evidence**, not against the document alone — and
it is why this report is written after the schematic rather than before it.

---

## 5. What FE-0 hands to FE-1

- The blueprint, unchanged, as the authority document.
- Four recommendations above, unowned.
- One erratum list, produced downstream, in `FE-1-SCHEMATIC.md` §4. The blueprint
  needs a **v1.1** to absorb it. Until it does, `tokens.css` and the blueprint
  disagree, and **`tokens.css` is the one that ships**.
