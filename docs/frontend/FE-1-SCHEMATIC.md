# FE-1 · SCHEMATIC — gate report

**Phase deliverable (§18):** `tokens.css`, `type.css`, both themes live, and one
full-fidelity static comp of Room I.
**Gate:** *judge the direction before a shader exists.*
**State: 🟢 GATE CRITERION MET — three items open, named in §6.**

---

## 1. What was built

| File | What it is |
|---|---|
| [`web/datum/styles/tokens.css`](../../web/datum/styles/tokens.css) | Palette → semantic → component. The only file in the system containing a colour literal. Both themes, plus theme *islands* |
| [`web/datum/styles/type.css`](../../web/datum/styles/type.css) | Eleven `@font-face` declarations, the tracking curve evaluated, the full scale, the degradation axis as four utilities |
| [`web/datum/styles/base.css`](../../web/datum/styles/base.css) | The datum, the grid, the 9/7, poché, surfaces, the expressed joint, the reduced-motion contract, the no-canvas contract |
| [`web/datum/room-i.html`](../../web/datum/room-i.html) | **The gate.** Room I, full fidelity, no shader, both themes |
| [`web/datum/theme.js`](../../web/datum/theme.js) | Three-state toggle, arrow-key traversal, `theme-color` sync, no-flash inline snippet |
| [`web/datum/tools/contrast.py`](../../web/datum/tools/contrast.py) | The §6.7 CI assertion, computing rather than quoting |
| [`web/datum/tools/lint-tokens.py`](../../web/datum/tools/lint-tokens.py) | Five §19 laws, plus a written list of the ones it does not check |

### Two decisions inside `tokens.css` worth naming

**Theme islands.** §6.6 declares the semantic layer on `:root`, which is correct
for a page and useless for a subtree. The token file additionally declares it on
bare `[data-theme="light"]` / `[data-theme="dark"]`, so a theme can be scoped.
Two things need that: the FE-2 states gallery, which shows both themes on one
page, and the evidence pane, which must stay paper inside the vault (**L-2**).

**Signal split in two.** §6.4 gives one `--signal`. Measurement forced two:

- `--signal` — signal as a **mark**: plane fills, the 2px reveal, rules. Held to
  the non-text target, WCAG 2.2 SC 1.4.11, ≥ 3.0.
- `--signal-text` — signal as **type**. Held to ≥ 4.5.

The blueprint's single token could not satisfy both at once; see erratum **E-1**.
The split is not a compromise — it names a distinction §6.8 already makes in
prose ("*signal arrives as a plane… or not at all*") and had no token for.

---

## 2. Room I — how the gate is meant to be judged

Open `web/datum/room-i.html` and toggle the theme in the top-right.

**What is real and judgeable:** the composition; the waterline at 0.618 rather
than centre; the plate as a manufactured object with square corners; the etched
type cut by two offset shadows from one lamp; the reflection mirrored, sheared
0.9° and *reading different values*; the hero centred exactly once; the poché
margin doing real work; and the room genuinely re-lighting between the vault and
the light table while the evidence pane does not move at all.

**The mechanism is deliberately not the shipped one.** §11.3 renders the false
plate into a second scene through a render target, so the mirror is genuinely
showing something else. This comp does the same thing with two DOM elements whose
text differs. Same lie, cheaper mechanism — and that is the point of the gate: if
the composition does not hold in CSS, a planar reflection at FE-5 will not save
it. There is **no canvas on the page**, so L-7 holds by construction rather than
by fallback.

**What cannot be judged yet:** the letterforms. See §6, O-1.

---

## 3. Contrast — measured, not assumed

§6.7 says contrast is asserted in CI. `tools/contrast.py` is that assertion. It
parses the palette out of the token file that ships, resolves the semantic layer
for both themes, converts OKLCH → Oklab → linear sRGB → sRGB, composites any
alpha in linear light, and computes WCAG 2.x ratios.

**Nothing in it is copied from the blueprint's table.** Where a computed ratio
disagrees with the blueprint's stated one, the tool prints both.

Text pairs are asserted against the **worst ground the token may legally land
on** — `--surface-3` in both themes — rather than against a convenient one.
Passing there means passing everywhere.

```
python web/datum/tools/contrast.py
```

| Pair | Theme | Fore | Ground | Measured | Target | |
|---|---|---|---|---:|---:|---|
| `--text-1` on `--bg-void` | dark | `#FAF5EE` | `#080A0D` | **18.24:1** | 7.0 | PASS <sub>§6.7 states 16.9</sub> |
| `--text-2` on `--surface-3` | dark | `#A0A5AA` | `#23282D` | **5.98:1** | 4.5 | PASS |
| `--text-3` on `--surface-3` | dark | `#90959B` | `#23282D` | **4.92:1** | 4.5 | PASS |
| `--signal-text` on `--surface-3` | dark | `#E57477` | `#23282D` | **5.01:1** | 4.5 | PASS |
| `--settled` on `--surface-3` | dark | `#ADCCC4` | `#23282D` | **8.61:1** | 4.5 | PASS |
| `--evidence-text` on `--evidence-bg` | dark | `#17130E` | `#F4EEE6` | **16.06:1** | 7.0 | PASS |
| `--focus-ring` on `--bg-void` | dark | `#D1E9F5` | `#080A0D` | **15.72:1** | 3.0 | PASS |
| `--signal` on `--surface-1` | dark | `#C83846` | `#121519` | **3.58:1** | 3.0 | PASS |
| `--signal` on `--evidence-bg` | dark | `#C83846` | `#F4EEE6` | **4.44:1** | 3.0 | PASS |
| `--edge-strong` on `--surface-1` | dark | `#616263` | `#121519` | 2.99:1 | — | reported, not gated |
| `--text-1` on `--bg-void` | light | `#17130E` | `#F4EEE6` | **16.06:1** | 7.0 | PASS <sub>§6.7 states 14.6</sub> |
| `--text-2` on `--surface-3` | light | `#625950` | `#E9E3D9` | **5.37:1** | 4.5 | PASS |
| `--text-3` on `--surface-3` | light | `#6B655E` | `#E9E3D9` | **4.52:1** | 4.5 | PASS |
| `--signal-text` on `--surface-3` | light | `#8E1427` | `#E9E3D9` | **7.20:1** | 4.5 | PASS |
| `--settled` on `--surface-3` | light | `#386D62` | `#E9E3D9` | **4.65:1** | 4.5 | PASS |
| `--evidence-text` on `--evidence-bg` | light | `#17130E` | `#FAF5EE` | **17.04:1** | 7.0 | PASS |
| `--focus-ring` on `--bg-void` | light | `#B32738` | `#F4EEE6` | **5.60:1** | 3.0 | PASS |
| `--signal` on `--surface-1` | light | `#B32738` | `#FAF5EE` | **5.94:1** | 3.0 | PASS |
| `--signal` on `--evidence-bg` | light | `#B32738` | `#FAF5EE` | **5.94:1** | 3.0 | PASS |
| `--edge-strong` on `--surface-1` | light | `#E6E2DC` | `#FAF5EE` | 1.19:1 | — | reported, not gated |

**All 20 gated pairs meet target.** The hairline rows are printed rather than
gated: a 1px hairline at 1.19:1 is a legitimate design decision under SC 1.4.11
(it is decoration, not a UI boundary carrying meaning), and pretending a lint can
tell those apart would be the kind of claim this repository audits people for.

---

## 4. Errata against the blueprint

Six. Every one was found by building the thing rather than reading about it.

### E-1 · `--signal` on dark fails its stated 4.5:1 by a wide margin

§6.7 states `--signal` on `--surface-1`, dark, is **5.1:1**. Computed from the
OKLCH the blueprint specifies, it is **3.58:1** — below AA for text.

`p-signal-500` at `oklch(.560 .180 20)` cannot reach 4.5:1 against graphite-900
at any chroma; the lightness must rise to roughly `.62`, and at `.62` the hue
starts to read as coral rather than crimson.

**Fix as built:** split the token (see §1). `--signal` keeps `p-signal-500` for
planes and reveals, held to ≥ 3.0. `--signal-text` takes `p-signal-400`, whose
palette value was moved from `oklch(.660 .150 20)` to `oklch(.690 .140 20)` so it
clears 4.5:1 on *every* dark surface including `--surface-3` (5.01:1). Chroma
dropped to .140, still under the L-1 ceiling of .16.

### E-2 · `p-graphite-400` fails as `--text-3` on `--surface-3`

§6.4 assigns dark `--text-3` = `p-graphite-400` = `oklch(.620 .010 250)`. On
`--surface-1` that is 5.03:1 and fine. On `--surface-3` — the code surface, and
the ground inside an overlay — it is **4.07:1**.

**Fix as built:** `p-graphite-400` → `oklch(.668 .010 250)`. Now 4.92:1 on the
worst ground. The ramp stays perceptually even; graphite-300 above it is
unchanged.

### E-3 · `p-verdigris-600` fails as `--settled` on light

§6.7 states `--settled` on `--surface-1`, light, is **4.6:1**. Computed: **4.16:1**,
and **3.53:1** on `--surface-3`.

**Fix as built:** `p-verdigris-600` → `oklch(.495 .060 178)`, giving 4.65:1 on the
worst light ground.

### E-4 · light `--text-3` fails on `--surface-3`

§6.5 gives `oklch(.560 .014 70)`: **4.30:1** on `--surface-1` and **3.66:1** on
`--surface-3`. **Fix as built:** `oklch(.510 .014 70)` → 4.52:1 worst-ground.

### E-5 · §5.5's tracking column contradicts §5.4's tracking curve

§5.4 gives `tracking(em) = −0.0165 + 0.29/size_px` and says tracking is set
"never by eye". §5.5's table then hand-writes values that the curve does not
produce, below 20px:

| Token | Size | §5.5 says | Curve gives |
|---|---:|---:|---:|
| `h-4` | 16px | −.001em | **+.0016em** |
| `body` | 15px | −.002em | **+.0028em** |
| `data` | 14px | 0 | **+.0042em** |
| `body-s` | 13px | 0 | **+.0058em** |

Above 20px the two agree to four places, which is the tell: the small sizes were
typed, not evaluated.

**Fix as built:** the curve wins, because §5.4 says it does. The uppercase
allowances (`col` +.10em, `meta` +.14em, `micro` +.16em) are **kept** — those are
caps letterspacing, which the curve does not govern.

### E-6 · §6.3's hex column is a different colour from its OKLCH column

§6.3 prints both, and says "OKLCH first". They do not agree. Converting each
OKLCH value to sRGB and comparing to the hex printed beside it:

| Token | OKLCH → sRGB | §6.3 hex | Max channel delta |
|---|---|---|---:|
| `p-graphite-300` | `#A0A5AA` | `#8B929B` | **21** |
| `p-graphite-500` | `#646A6F` | `#525963` | **18** |
| `p-signal-500` | `#C83846` | `#C42B38` | **14** |
| `p-ice-200` | `#D1E9F5` | `#DCE9F2` | **11** |
| `p-bone-950` | `#17130E` | `#1D1A16` | 8 |
| `p-graphite-950` | `#080A0D` | `#07080A` | 3 |

Twenty-one out of 255 on a mid-grey is not a rounding artefact; it is a visible
difference. Anyone who eyedropped the hex column would have built a different
palette from anyone who used the OKLCH column.

**Fix as built:** `tokens.css` carries **OKLCH only**. No hex fallback ladder is
shipped — every target browser has supported `oklch()` since 2023, and a hex
fallback would reintroduce exactly the two-sources-of-truth problem this erratum
describes. The blueprint's hex column should be deleted in v1.1, or regenerated
from the OKLCH and labelled as derived.

---

## 5. The other gates, discharged

```
python web/datum/tools/lint-tokens.py
```

| Check | Law | Result |
|---|---|---|
| Colour literals outside `tokens.css` | §17 | **pass**, 2 exemptions, both written down |
| Every `var()` resolves to a defined token | §6.1 | **pass** — 138 defined, 122 referenced |
| Spacing outside the closed set | §8.5 | **pass** |
| Durations and curves outside the scale | §10.1–10.2 | **pass**, 3 named carve-outs |
| `outline:none` · scroll authority · frame-rate independence | §15 / §10.5 / §10.6 | **pass** |

The lint was negative-tested: a deliberately bad rule
(`color:#ff0000; margin-top:37px; transition:opacity 333ms cubic-bezier(.3,.7,.4,1)`)
raises four violations and one undefined `var()` raises one. A gate that has
never failed has not been shown to work.

**Three carve-outs** exist in the motion check, each with a citation:
`--d-tip` 400ms (§13.1, tooltip delay), `--d-toast` 6000ms (§13.1, auto-dismiss),
`--m-collapse` 120ms (§10.4, and the blueprint's own token file in §20). The
§10.1 closed set governs **durations** — how long a thing takes to move. A delay
is not a duration, and rather than argue that in review every time, the three are
named tokens so no component ever writes a raw millisecond.

### What the lint does not check, and does not claim to

`L-4` (no precision beyond the source), `L-5` (light must be motivated), `L-6`
(type is never a texture), §6.8 (signal on at most 4 elements per viewport),
§13.5 (every state, both themes), §5.3 (zero CLS on the font swap). Run
`lint-tokens.py --list` and it prints them. A lint that claimed these would be
the same failure this repository's own audit found in its adversarial suite:
three of five authors self-reporting "0 UNVERIFIED" while fabricating citations.

---

## 6. Open items

### O-1 · The three typefaces are not in this repository — **blocks a full brand sign-off**

Redaction, Apfel Grotezk and Sligoil are all SIL OFL and free. There is no
licence blocker; there is a fetch step, and it has not been done. Every page is
rendering in fallback.

The consequence is specific rather than general: **the semantic degradation axis
does not currently exist.** §5.2's novel move — Redaction 0 for ground truth
through Redaction 100 for a corrupted record, so a visitor watches type sharpen
as a claim becomes grounded — is the most distinctive decision in this design
system, and it is presently four identical lines of Georgia.

`room-i.html` and `grid.html` both say so on the page. `web/datum/fonts/README.md`
carries the acquisition list and the five things that must happen when the files
land, including the `size-adjust` measurement that §5.3 makes a LAW.

**No CLS number is quoted anywhere in this report**, because the fonts that would
produce one are absent. The blueprint's 0.00 budget is a target.

### O-2 · `--edge-strong` at 1.19:1 in light theme

Reported above. It is a hairline, and a hairline is decoration — but the material
matrix (§9.3) also uses `--edge-strong` on the **overlay/modal** edge, where it
separates a dialog from the scrim behind it and is therefore arguably a UI
boundary under SC 1.4.11. Two readings, and the difference matters.

**Recommendation:** decide at FE-9 with a real modal on a real page, not now with
a swatch. Left open deliberately.

### O-3 · Room I carries page-scoped colour literals

`room-i.html` declares the anodized plate ramp and the key-light falloff in its
own `<style>` block, and is exempted from the §17 colour rule with that reason
written into the lint's exemption list. Those values belong in a scene token file
— **at FE-5**, when the shader owns them and there is something to name them
against. Declaring a `--scene-*` layer now would be inventing an interface for a
system that does not exist.

---

## 7. What FE-1 hands to FE-2

- A token file whose every gated contrast pair is measured and passing.
- A type system whose scale, curve and measure are real and whose faces are not.
- Two CI gates that have been shown to fail when they should.
- Six errata the blueprint needs to absorb in a v1.1.
- One comp that a person can look at and say yes or no to — which was the gate.
