# ERRATA — FRONTEND BLUEPRINT
### Design system **DATUM** · art direction **THE STILL WATER** · v1.0

> **Status:** design authority document. Nothing ships that contradicts this file.
> **Owner:** design + frontend. **Reviewers:** brand, product, accessibility, performance.
> **Written:** 21 August 2026.

---

## 0. HOW TO READ THIS DOCUMENT

This is not a moodboard and not a style guide. It is a **construction document** — the frontend
equivalent of what an architecture practice hands a contractor. Every number in it is a decision
someone had to defend, and every decision is traceable to either (a) the product's own ethic,
(b) a perceptual constraint, or (c) a performance budget.

Read it in this order:

| If you are… | Read |
|---|---|
| Deciding whether to approve the direction | §1 Post-mortem, §2 Thesis, §4 Principles, §12 Pages |
| Building the design system | §5 Type, §6 Colour, §8 Grid, §9 Surfaces, §13 Components, §20 Tokens |
| Building the landing experience | §7 Art, §10 Motion, §11 WebGL, §12.1 |
| Building the product UI | §6.6 Light Table, §12.9–12.13, §13 |
| Reviewing before merge | §15 A11y, §16 Perf, §19 Definition of done |

**Rules of the document.** Anything written as a **LAW** is non-negotiable and blocks merge.
Anything written as *guidance* is a default you may argue out of, in writing, in the PR.

---

## 1. POST-MORTEM — WHERE THE PROTOTYPE LACKED

Before proposing anything, the honest audit of the three prototype iterations. This section exists
because the same mistakes will recur if they are not named.

### 1.1 The twelve findings

**F-01 · Scroll was fought, not owned.**
`window.scrollY` was smoothed with a lerp while native scroll continued to run. Two motion systems
on one axis produce beat frequencies — the judder the reviewer felt. **Fix:** a single scroll
authority (Lenis) that owns the scrollbar; nothing else reads `scrollY`.

**F-02 · Frame-rate-dependent damping.**
`p += (target - p) * 0.072` runs 2.4× faster on a 144Hz panel than on 60Hz. The site literally felt
different on different machines. **Fix:** `k' = 1 - (1-k)^(dt/16.67)` everywhere. **LAW.**

**F-03 · The camera was assigned, not driven.**
Camera position was computed directly from scroll progress. Real camera work is *damped* — position
chases a target with inertia. Without it, every scroll stutter is transmitted 1:1 into the image.

**F-04 · Type was rendered into a texture.**
The datasheet and the spec plate were drawn into `<canvas>` and sampled as textures. Result: no
hinting, no subpixel positioning, no real metrics, mip-blur. **This is the single largest source of
the "AI-generated" read.** Machine-drawn type at texture resolution never looks designed.
**LAW: any surface whose primary content is text is DOM, not a texture.**

**F-05 · Two accents fighting.**
Oxide orange + ochre yellow at chroma 0.13–0.15 on a blue-tinted graphite. Two warm high-chroma
hues against a cool ground is the exact recipe for "cheap dashboard". **Fix:** monochrome + exactly
one chromatic event.

**F-06 · Default-tier typefaces.**
Inter, Geist, Archivo, JetBrains Mono, Newsreader — the free tier that ships on every AI-generated
landing page. Correct, legible, and completely anonymous. Character was missing because character
was never specified.

**F-07 · No art. Anywhere.**
Three iterations and not one drawn, photographed or engraved asset. Pure CSS/WebGL with no imagery
is the visual signature of generated work. Award sites are *art-directed* — they have pictures,
and the pictures were chosen by a person.

**F-08 · Every page was the landing page.**
There was no sitemap, no second template, no product surface, no docs, no pricing. A frontend is a
*system of pages*, and a system was never designed.

**F-09 · One theme only.**
Dark-only. No light mode, no theming architecture, no token indirection — colours were literal
values scattered through CSS. Retrofitting a second theme onto that costs more than building both.

**F-10 · Motion had no grammar.**
Durations were picked per-element (`.3s`, `1.05s`, `.45s`) with three different curves. Award-level
motion has a *scale* — a small closed set of durations and one or two curves, used consistently.

**F-11 · No loading, error, empty or reduced-motion design.**
The states a real product spends most of its life in were never drawn.

**F-12 · Accessibility was an afterthought.**
`cursor: none` with a custom cursor and no keyboard path. Scroll-jacking with no escape. Contrast
never measured. Motion preference honoured in one place out of six.

### 1.2 The meta-finding

Every one of the twelve is the same mistake: **producing surface before deciding structure.**
The remainder of this document decides structure first.

---

## 2. THESIS — WHAT THIS PRODUCT IS, VISUALLY

### 2.1 The product, in the product's own words

> Errata is a verification layer for industrial product data. It ingests a catalog **and** the source
> documents behind it, independently re-derives every attribute, grounds each value to a word-level
> span, calibrates its own confidence, and emits a ranked list of records where the catalog and the
> evidence disagree — with the evidence attached.
>
> **It grades data. It does not create data.**

### 2.2 What that means for design

Three consequences, and they generate everything downstream:

1. **The product's authority comes from restraint.** It does not generate, guess, or embellish. A
   visual language full of gradients, glows and generated flourish would contradict the pitch on
   arrival. **The design must look like it is holding something back.**

2. **The product's subject is paper.** Datasheets, PDFs, scans, tables, spans. Paper is warm,
   square-cornered, and lit from outside. Any design that renders evidence as a glowing dark card is
   lying about what evidence is.

3. **The product's emotional beat is being caught.** Not "wow, impressive" — *"oh. that's been wrong
   the whole time."* Awe is the wrong target. **Unease, then relief** is the right one.

### 2.3 The parti

> **A dark mass, one raking light, warm paper, and a repair you are never allowed to stop seeing.**

Three elements only. Every surface in the system answers *which one am I?*

| Element | Meaning | Material |
|---|---|---|
| **MASS** | The unlit archive. What you have not checked. | Graphite, matte, cold |
| **FABRIC** | Surviving evidence. The source document. | Bone paper, warm, lit |
| **INTERVENTION** | What Errata added. The correction. | Signal crimson, always visibly *other* |

The governing principle is **anastylosis** — the archaeological law that reconstructed material must
remain visibly distinguishable from original fabric. You never fake continuity. Chipperfield's Neues
Museum is the built reference; Errata's own README is the written one:

> *"a figure quoted to a digit nobody published is the beginning of a number nobody can check."*

### 2.4 The sentence the site exists to earn

> **Your catalog is a reflection. We checked it against the thing it claims to reflect.**

---

## 3. REFERENCE BOARD — WHAT TO STEAL, PRECISELY

Vague inspiration produces vague work. Each reference below is paired with **the one specific thing
to take** and **the thing to leave**.

### 3.1 MNC / enterprise

| Reference | Take | Leave |
|---|---|---|
| **Stripe** | Density done elegantly: a lot of information per screen with no crowding. Their WebGL mesh hero is a *background*, never the subject | The gradient. It's been copied to death |
| **Palantir** | Institutional gravity. Monospace as a primary voice. Screens that look like instruments | The opacity — we must be *legible* about what we do |
| **Linear** | Motion discipline: a tiny set of durations, one curve, zero bounce | Dark-only. Their subject isn't paper |
| **Vercel** | Token architecture and theme switching done properly at scale | The geometric-sans neutrality — we need character |
| **Bloomberg Terminal** | Tabular numerals, condensed column heads, information density as a *feature* | The chrome. It's 1990s |
| **Siemens / ABB** | The credibility of engineering documentation: part numbers, revisions, standards references shown openly | The corporate stock photography |

### 3.2 Awards circuit

Sites recognised on Awwwards / FWA / CSSDA in 2025–26 and the exact technique worth taking:

| Reference | Take |
|---|---|
| **Hubtown** (Unseen Studio) — Awwwards SOTD, June 2026 | The **cursor-reveal**: the pointer uncovers detail in geometry and lighting. This is Act II's mechanic, and it is proven |
| **Iventions** — CSSDA Website of the Month, Awwwards SOTD + Developer | Treating each item as a **spotlit installation**. One light, one subject, black around it |
| **Shader.se** (Codrops case study) | **Scroll-driven WebGPU with seamless scene transitions** — no cuts between acts, which is exactly our four-room procession |
| **Trionn** (Codrops case study) | The **architecture**: GSAP as the single timeline authority, Lenis synced to GSAP's ticker, Web Audio layered on top. Copy the coordination pattern verbatim |
| **IVRESS** | **WebGPU renderer with a WebGL fallback** shipped in production — the exact degradation ladder we need |
| **Mat Voyce** | Type as a physical object with mass and motion — not text that fades in |

### 3.3 Art & institutional

| Reference | Take |
|---|---|
| **Neues Museum** (Chipperfield) | Anastylosis: new material visibly distinct from old. The entire parti |
| **Castelvecchio** (Carlo Scarpa) | **The expressed joint.** Where two materials meet, celebrate the seam with a reveal, never a blend |
| **Louis Kahn** | One motivated light source. *"The sun never knew how great it was until it struck the side of a building"* |
| **Peter Zumthor, _Atmospheres_** | Material temperature as a design instrument; "levels of intimacy" as a spatial hierarchy |
| **Frank Lloyd Wright** | **Compression and release** — squeeze the visitor through a dark passage so the next room detonates. This is our scroll choreography |
| **Luis Barragán** | Colour as *mass*, never as paint. Accent arrives as a plane or not at all |
| **Bauhaus / Jan Tschichold** | Asymmetric typographic layout; the hanging margin; rules as structure |
| **Library of Congress HAER drawings** | Drafted line-work as visual culture: measured, annotated, beautiful, and public domain |

**Sources:** [Utsubo — Best Three.js Websites 2026](https://www.utsubo.com/blog/best-threejs-websites-2026) ·
[Codrops — Trionn architecture](https://tympanus.net/codrops/2026/07/15/the-architecture-behind-trionn-coordinating-gsap-three-js-lenis-and-web-audio/) ·
[Codrops — Shader.se WebGPU pipeline](https://tympanus.net/codrops/2026/05/19/80s-business-tech-seamless-scene-transitions-inside-shader-ses-scroll-driven-webgpu-pipeline/) ·
[Hon Tran — Award-winning websites 2026, judged](https://www.hontran.dev/blog/best-award-winning-websites-2026)

---

## 4. PRINCIPLES — THE SEVEN LAWS

**L-1 · Colour only where meaning is.**
The interface is achromatic except where a value is in dispute. Global chroma ceiling **0.16 OKLCH**.
If a colour does not encode state, it is not a colour, it is decoration — remove it.

**L-2 · Paper is paper.**
Evidence surfaces are warm, near-white, square-cornered, and identical in both themes. **The evidence
pane does not have a dark mode.** Reading a scanned datasheet inverted is a lie about the artefact.

**L-3 · The joint is expressed.**
Where system meets evidence, there is a visible 2px reveal. Never a gradient, never a fade. This is
anastylosis at component scale and it is the most recognisable detail in the system.

**L-4 · Never render a precision the source does not contain.**
`46.4`, not `46.43`. No silent rounding, no `~`, no cosmetic decimals, no fabricated placeholder
data in production surfaces. Taken directly from the product's own ethic. **LAW.**

**L-5 · Light must be motivated.**
Every glow has a source you could point at. No ambient prettiness, no rim light without a lamp.
Test: *could a photographer stand in this room and take this picture?* If no, delete the light.

**L-6 · Type is never a texture.**
Any surface whose primary content is text is rendered as DOM/SVG at device resolution. **LAW.**

**L-7 · The page works with the canvas deleted.**
All copy is real DOM. All navigation is keyboard-reachable. WebGL is enhancement, never structure.
**LAW.**

---

## 5. TYPOGRAPHY

### 5.1 The problem with the previous stack

Inter / Geist / Archivo / Newsreader / JetBrains Mono are *correct* and *anonymous*. They are the
default output of every generated landing page in 2026. The pendulum has swung back toward
expression precisely because homogeneity kills identity — when every product uses the same neutral
grotesk, typography stops contributing to the brand at all.

We need faces with **character that means something**, not character for its own sake.

### 5.2 The system — three voices, one concept

#### VOICE 1 — DISPLAY: **Redaction** (Forest Young & Jeremy Mickel · SIL OFL · free)

The decision that makes this system unique. Redaction ships as a **graded family** — Redaction 0,
10, 20, 35, 50, 70, 100 — each step a coarser halftone, the letterform progressively degrading as if
photocopied, faxed, and re-scanned. It was drawn for a project about the criminal justice system:
type as a record decaying through reproduction.

For a product whose subject is **data that has degraded through copying between systems**, this is
not decoration. It is the argument, set in type.

**Semantic use of the degradation axis — this is the novel move:**

| Cut | Meaning in Errata | Where |
|---|---|---|
| **Redaction 0** | Ground truth. The source. Clean. | Evidence values, verified figures, the datasheet |
| **Redaction 20** | Derived, calibrated, high confidence | Section openers, editorial headlines |
| **Redaction 50** | Degraded — a claim we have not verified | Hero word "reflection"; unverified catalog claims |
| **Redaction 100** | Fully corrupted. Unreadable as record. | The "before" state; error/void illustrations |

A visitor scrolling from hero to evidence literally watches the type *sharpen* as the claim becomes
grounded. Nobody else on the web is doing this because it requires a product with something to say.

*Fallback:* `Redaction` → `Redaction 20` → `Spectral` → `Georgia`.

#### VOICE 2 — TEXT: **Apfel Grotezk** (Collletttivo · OFL · free)

A grotesque with warmth and slight optical irregularity — a face with a hand in it. Reads
institutional without reading corporate-neutral. Weights: Regular, Medium, Semibold, plus **Apfel
Grotezk Brukt** (a deliberately damaged cut) reserved for the void/error states.

*Alternates if licensing budget appears:* **Söhne** (Klim) or **ABC Diatype** (Dinamo) — the paid
tier this is standing in for.
*Fallback:* `Apfel Grotezk` → `Switzer` → `system-ui`.

#### VOICE 3 — DATA: **Sligoil** (Ariel Martín Pérez · Velvetyne · OFL · free)

A monospace drawn for film subtitling — humane, slightly narrow, with real personality at small
sizes where most monos go dead. This is the machine's voice: every attribute value, SKU, span
offset, confidence figure, coordinate and label.

*Fallback:* `Sligoil` → `Geist Mono` → `ui-monospace`.

**Why libre foundries:** Velvetyne (Paris, founded 2010, the first Francophone open-source foundry)
and Collletttivo are where design studios actually source expressive free type. These are not
"budget fonts" — they are curated, opinionated, and unavailable to anyone using defaults.

**Sources:** [Velvetyne Type Foundry](https://velvetyne.fr/about/) · [Collletttivo](https://www.collletttivo.it/) ·
[UNCUT free typeface catalogue](https://uncut.wtf/)

### 5.3 Self-hosting — LAW

All three families are **self-hosted as `.woff2`** in `/public/fonts`. No CDN, no FOIT, no third-party
request on the critical path.

```
/public/fonts/
  redaction/     Redaction_0-Regular.woff2  Redaction_20-Regular.woff2
                 Redaction_50-Regular.woff2 Redaction_100-Regular.woff2
                 Redaction_20-Italic.woff2
  apfel/         ApfelGrotezk-Regular.woff2  -Mittel.woff2  -Fett.woff2  -Brukt.woff2
  sligoil/       Sligoil-Regular.woff2  Sligoil-Micro.woff2
```

```css
@font-face{
  font-family:'Redaction 20'; src:url('/fonts/redaction/Redaction_20-Regular.woff2') format('woff2');
  font-weight:400; font-style:normal; font-display:swap;
  size-adjust:100%; ascent-override:92%; descent-override:24%;   /* metric-matched to Spectral */
}
```

**LAW:** every `@font-face` carries `size-adjust` / `ascent-override` / `descent-override` tuned to
its fallback, so the swap causes **zero layout shift**. Measured with `Fallback Font Generator`, CLS
budget **0.00** on the type swap.

### 5.4 The proportional system

Two scales, two ratios, because editorial and interface have different jobs.

- **Editorial** — Perfect Fourth (**1.333**), anchored at 18px
- **Interface** — Minor Third (**1.200**), anchored at 15px

**Optical tracking law.** Tracking tightens as size grows, on a curve, never by eye:

```
tracking(em) = −0.0165 + (0.29 / size_px)
```

| Size | Tracking |
|---|---|
| 11px | +0.0099em |
| 15px | +0.0028em |
| 24px | −0.0044em |
| 48px | −0.0105em |
| 96px | −0.0135em |
| 168px | −0.0148em |

### 5.5 The full scale

| Token | Face / cut | Size / leading | Tracking | Use |
|---|---|---|---|---|
| `d-1` | Redaction 50 | 168 / 152 | −.015em | Landing hero. **One per site** |
| `d-2` | Redaction 20 | 112 / 104 | −.014em | Page heroes |
| `d-3` | Redaction 20 | 76 / 76 | −.012em | Section openers |
| `d-4` | Redaction 20 Italic | 54 / 60 | −.010em | Pull quotes, the single italic accent |
| `h-1` | Apfel Grotezk Fett | 40 / 44 | −.009em | Page title |
| `h-2` | Apfel Grotezk Mittel | 28 / 34 | −.006em | Section heading |
| `h-3` | Apfel Grotezk Mittel | 20 / 27 | −.003em | Panel / card title |
| `h-4` | Apfel Grotezk Mittel | 16 / 22 | −.001em | Sub-head, table group |
| `lead` | Redaction 0 | 22 / 34 | −.003em | Opening paragraph. **Once per section** |
| `body` | Apfel Grotezk | 15 / 24 | −.002em | UI prose |
| `body-s` | Apfel Grotezk | 13 / 20 | 0 | Dense prose, help text |
| `data` | Sligoil | 14 / 20 | 0 | **Every value** |
| `data-s` | Sligoil | 12 / 17 | +.004em | Table cells, dense data |
| `col` | Sligoil Micro | 11 / 14 | +.10em uc | Table column heads |
| `meta` | Sligoil Micro | 10 / 14 | +.14em uc | Eyebrows, HUD, captions |
| `micro` | Sligoil Micro | 9 / 12 | +.16em uc | Span offsets, legal |

### 5.6 Typographic laws

- **LAW:** tabular lining numerals + slashed zero in every data context.
  `font-variant-numeric: tabular-nums slashed-zero;`
- **LAW:** measure locked — **62–72 characters** for sans prose, **44–52** for the Redaction lead.
- **LAW:** mono and prose never mix inside a sentence *except* to mark a machine fact:
  "Rated current — `16 A`". That contrast is the product's grammar.
- Hyphenation off in display, on in body (`hyphens:auto` + `lang` set).
- `text-wrap: balance` on all `d-*` and `h-1`; `text-wrap: pretty` on body.
- No text over 3 sizes in one viewport. If you need a fourth, the layout is wrong.
- Italic is Redaction 20 Italic only, one word or one line, never a paragraph.

### 5.7 The voice mapping — how a reader knows what they're looking at

| What the reader sees | What it means |
|---|---|
| Redaction, degraded (50/100) | An unverified claim |
| Redaction, clean (0/20) | Grounded, evidenced |
| Apfel Grotezk | A human is speaking |
| Sligoil | A machine is speaking, and you can check it |

---

## 6. COLOUR — DUAL THEME

### 6.1 The architecture

Three layers of indirection. **LAW: components never reference a palette value directly.**

```
PALETTE  →  SEMANTIC  →  COMPONENT
--p-graphite-900       --surface-1          --panel-bg
```

Palette values change never. Semantic values change per theme. Component values change per
component. A new theme touches only the semantic layer.

### 6.2 Two themes, and why

| Theme | Name | Where | Ground |
|---|---|---|---|
| **Dark** | **THE VAULT** | Marketing, landing, docs at night | Graphite `#07080A` |
| **Light** | **THE LIGHT TABLE** | **Product default**, docs, benchmark | Bone `#F4F1EB` |

**The Light Table is the product's default, and this is a considered decision.** Users read paper —
datasheets, scanned PDFs, tables — for hours. A dark chrome with a white PDF pane forces the iris
across a ~100:1 luminance step on every glance. That is measurable fatigue on a triage task that
runs three hours. Dark mode is offered and fully supported; **the evidence pane stays paper in both.**

### 6.3 Palette — OKLCH first

OKLCH because its lightness is perceptually uniform: a ladder built on it does not go muddy in the
mid-tones the way hex-picked ramps always do.

#### Graphite (the mass)

| Token | OKLCH | Hex |
|---|---|---|
| `p-graphite-950` | `oklch(.145 .008 250)` | `#07080A` |
| `p-graphite-900` | `oklch(.195 .010 250)` | `#0E1013` |
| `p-graphite-850` | `oklch(.235 .011 250)` | `#15181C` |
| `p-graphite-800` | `oklch(.275 .012 250)` | `#1D2126` |
| `p-graphite-700` | `oklch(.345 .012 250)` | `#2B3037` |
| `p-graphite-600` | `oklch(.425 .012 250)` | `#3C424A` |
| `p-graphite-500` | `oklch(.520 .011 250)` | `#525963` |
| `p-graphite-400` | `oklch(.620 .010 250)` | `#6B727C` |
| `p-graphite-300` | `oklch(.720 .009 250)` | `#8B929B` |
| `p-graphite-200` | `oklch(.820 .007 250)` | `#ADB3BB` |
| `p-graphite-100` | `oklch(.900 .005 250)` | `#CDD1D6` |

#### Bone (the fabric — warm, hue 78)

| Token | OKLCH | Hex |
|---|---|---|
| `p-bone-50` | `oklch(.972 .010 78)` | `#F7F4EE` |
| `p-bone-100` | `oklch(.952 .012 78)` | `#F1EDE5` |
| `p-bone-200` | `oklch(.918 .015 78)` | `#E8E2D7` |
| `p-bone-300` | `oklch(.868 .018 78)` | `#DAD2C4` |
| `p-bone-400` | `oklch(.780 .020 74)` | `#C0B7A7` |
| `p-bone-700` | `oklch(.470 .018 70)` | `#6B6459` |
| `p-bone-900` | `oklch(.250 .014 70)` | `#2A2620` |
| `p-bone-950` | `oklch(.190 .012 70)` | `#1D1A16` |

#### Signal (the intervention — the only chroma in the building)

| Token | OKLCH | Hex | Note |
|---|---|---|---|
| `p-signal-700` | `oklch(.420 .155 20)` | `#8E1F2A` | Text on light |
| `p-signal-600` | `oklch(.505 .175 20)` | `#B02330` | Default on light |
| `p-signal-500` | `oklch(.560 .180 20)` | `#C42B38` | Default on dark |
| `p-signal-400` | `oklch(.660 .150 20)` | `#DE5B62` | Hover on dark |
| `p-signal-100` | `oklch(.920 .040 22)` | `#F7DFDD` | Row wash on light |
| `p-signal-050` | `oklch(.960 .020 22)` | `#FCF0EF` | Faintest wash |

Hue **20**, not 38. The previous oxide sat at hue 38 — that is orange, and orange against a blue
ground is the clash the reviewer correctly rejected. Hue 20 is unambiguously crimson.

#### Verdigris (settled / reconciled) — used at most twice per screen

| Token | OKLCH | Hex |
|---|---|---|
| `p-verdigris-600` | `oklch(.560 .060 178)` | `#41847D` |
| `p-verdigris-300` | `oklch(.820 .035 178)` | `#B4CFCB` |

#### Ice (light on paper — a highlight, never a colour)

| Token | OKLCH | Hex |
|---|---|---|
| `p-ice-200` | `oklch(.920 .030 230)` | `#DCE9F2` |
| `p-ice-400` | `oklch(.800 .045 230)` | `#B0C9DC` |

**LAW:** the total palette is graphite + bone + signal + verdigris + ice. Adding a hue requires a
written argument in the PR and a reviewer from brand.

### 6.4 Semantic layer — dark (THE VAULT)

| Semantic | Value |
|---|---|
| `--bg-void` | `p-graphite-950` |
| `--surface-1` | `p-graphite-900` |
| `--surface-2` | `p-graphite-850` |
| `--surface-3` | `p-graphite-800` |
| `--edge-hair` | `rgba(255,255,255,.055)` |
| `--edge-strong` | `rgba(255,255,255,.115)` |
| `--edge-lift` | `rgba(255,255,255,.075)` (1px top highlight) |
| `--text-1` | `p-bone-50` |
| `--text-2` | `p-graphite-300` |
| `--text-3` | `p-graphite-400` |
| `--text-disabled` | `p-graphite-500` |
| `--signal` | `p-signal-500` |
| `--signal-hover` | `p-signal-400` |
| `--settled` | `p-verdigris-300` |
| `--evidence-bg` | `p-bone-100` ← **paper stays paper** |
| `--evidence-text` | `p-bone-950` |
| `--focus-ring` | `p-ice-200` |

### 6.5 Semantic layer — light (THE LIGHT TABLE)

| Semantic | Value |
|---|---|
| `--bg-void` | `p-bone-100` |
| `--surface-1` | `p-bone-50` |
| `--surface-2` | `#FFFFFF` |
| `--surface-3` | `p-bone-200` |
| `--edge-hair` | `rgba(20,18,14,.085)` |
| `--edge-strong` | `rgba(20,18,14,.170)` |
| `--edge-lift` | `rgba(255,255,255,.9)` |
| `--text-1` | `p-bone-950` |
| `--text-2` | `p-bone-700` |
| `--text-3` | `oklch(.560 .014 70)` |
| `--signal` | `p-signal-600` |
| `--settled` | `p-verdigris-600` |
| `--evidence-bg` | `p-bone-50` ← identical intent in both themes |
| `--evidence-text` | `p-bone-950` |
| `--focus-ring` | `p-signal-600` |

### 6.6 Theming mechanics — LAW

Three states, and all three must be handled:

```css
:root { /* complete LIGHT palette defined here, on bare :root */ }

@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]) { /* dark overrides */ }
}

:root[data-theme="dark"] { /* same dark overrides — explicit choice wins */ }
```

- Never define a colour *only* inside a media query or `[data-theme]` block.
- `<body>` always has an explicit token background. A transparent body borrows the host's ground.
- Theme is stored in `localStorage.errata-theme`, applied by a **blocking inline script in `<head>`**
  before first paint. No flash. **LAW.**
- Toggle is three-state: `system / light / dark`, mono label, top-right of the header.
- `<meta name="theme-color">` updated on switch.
- WebGL scenes read theme tokens at init and on change — the void inverts to a **pale studio**
  in light mode (see §11.7).

### 6.7 Contrast — measured, not assumed

| Pair | Theme | Ratio | Target |
|---|---|---|---|
| `--text-1` on `--bg-void` | dark | 16.9:1 | ≥ 7 (AAA) |
| `--text-2` on `--bg-void` | dark | 7.4:1 | ≥ 4.5 |
| `--text-3` on `--surface-1` | dark | 4.9:1 | ≥ 4.5 |
| `--signal` on `--surface-1` | dark | 5.1:1 | ≥ 4.5 |
| `--text-1` on `--bg-void` | light | 14.6:1 | ≥ 7 |
| `--text-2` on `--bg-void` | light | 6.8:1 | ≥ 4.5 |
| `--signal` on `--bg-void` | light | 5.6:1 | ≥ 4.5 |
| `--settled` on `--surface-1` | light | 4.6:1 | ≥ 4.5 |

**LAW:** contrast is asserted in CI. A token change that drops any pair below target fails the build.

### 6.8 Colour usage laws

- **Signal appears on at most 4 elements per viewport.** Counted in review.
- Signal never appears as a 1px border or a small dot. It arrives as a **plane** — a full row wash
  with a 2px edge on the datum side — or not at all. *(Barragán: colour is mass.)*
- Verdigris is used at most twice per screen and never adjacent to signal.
- Ice is a highlight on paper only. It never appears on graphite.
- **No gradients as decoration.** Gradients are permitted only for: fog/depth in WebGL, mask
  feathering, and the studio environment map.

---

## 7. ART DIRECTION — REAL PICTURES, PUBLIC DOMAIN

### 7.1 The gap this closes

Finding F-07: three prototype iterations contained **zero drawn or photographed assets**. Pure
CSS/WebGL with no imagery reads as generated because it *is* generated. Award sites are
art-directed: someone chose pictures.

### 7.2 The visual culture we are borrowing

Not stock photography. Not 3D renders of abstract shapes. **Measured technical draughtsmanship** —
patent plates, engineering elevations, exploded assemblies, calibration charts. This is beautiful,
free, and thematically exact: it *is* source documentation, which is the product's subject.

### 7.3 Sources — all public domain or CC0

| Source | What to take | Licence | Access |
|---|---|---|---|
| **Library of Congress — HAER / HABS** | Measured engineering & architectural drawings of industrial plant. The crown jewels | Public domain | `loc.gov/pictures/` JSON API |
| **Smithsonian Open Access** | 5.1M items across 21 museums; instruments, apparatus, machinery | **CC0** | `api.si.edu` (api.data.gov key) |
| **The Met Open Access** | Public-domain works + full object metadata | **CC0** | `collectionapi.metmuseum.org` |
| **Rijksmuseum** | High-res plates, exceptional scan quality | Public domain | `rijksmuseum.nl/api` |
| **Art Institute of Chicago** | Clean IIIF endpoints, excellent API ergonomics | **CC0** | `api.artic.edu` |
| **Cleveland Museum of Art** | CC0 with open API | **CC0** | `openaccess-api.clevelandart.org` |
| **USPTO / Espacenet** | Patent drawings — line art of mechanisms, annotated with reference numerals | Public domain | Bulk data |
| **Internet Archive / BHL** | Trade catalogs, engineering handbooks, plate books | Varies — verify | `archive.org` API |
| **NYPL Digital Collections** | Prints, plates, ephemera | Public domain subset | `api.repo.nypl.org` |

**Sources:** [Smithsonian Open Access](https://www.si.edu/openaccess) ·
[The Met Open Access](https://www.metmuseum.org/hubs/open-access) ·
[Museum APIs overview — Nordic APIs](https://nordicapis.com/how-museums-are-using-apis-to-inspire-art-lovers-worldwide/)

### 7.4 LAW — provenance

**Every image asset carries a provenance record.** This is a verification product; using an image
we cannot source would be self-refuting.

```yaml
# /content/assets/plate-0114.yml
id: plate-0114
title: "Circuit breaker, sectional elevation"
institution: "Library of Congress, HAER"
identifier: "HAER PA,51-PITBU,1--12"
rights: "Public domain"
retrieved: "2026-08-21"
url: "https://www.loc.gov/pictures/item/pa1234/"
treatment: "duotone graphite→bone, 8% grain, 2px signal reveal on datum edge"
```

Every plate on the site shows its identifier in `micro` type in the hanging margin. That is both
honest and — because it looks like a museum wall label — a large part of why it will look expensive.

### 7.5 Treatment — how art enters the system

Raw plates are sepia, foxed, and inconsistent. Every asset passes through one pipeline:

1. **Desaturate** to luminance.
2. **Duotone map** — shadows → `p-graphite-900`, highlights → `p-bone-100`. In light theme the map
   inverts to shadows → `p-bone-950`, highlights → `#FFF`.
3. **Levels** — clamp to 4–96% so nothing hits pure black or white.
4. **Grain** — 6–8% monochrome, matched to the WebGL grain pass so plates and canvas share a skin.
5. **Reveal** — a 2px `--signal` rule on the plate's datum edge. The expressed joint (L-3).
6. **Export** — AVIF primary, WebP fallback, at 1×/2×; `<picture>` with explicit dimensions.

**LAW:** no asset ships untreated. A raw sepia scan among duotone plates destroys the system.

### 7.6 Where art appears

| Surface | Asset | Role |
|---|---|---|
| Landing Act I | — | Restraint. The void carries it |
| Landing Act IV → footer | HAER sectional elevation, full-bleed, 12% opacity | Ground under the queue |
| Method page | Patent plate with numerals, annotated with our own callouts | The main illustration |
| Benchmark page | Calibration chart engraving as section divider | Rhythm |
| Docs index | Small plate per section, 64px, duotone | Wayfinding |
| Manifesto | Neues-Museum-style repaired-surface photograph | The parti, stated |
| 404 / error | Redaction 100 + a plate at 4% | The void state |
| Blog / Errata log | One plate per entry, chosen per topic | Editorial |

### 7.7 Illustration system (where no plate exists)

Draw in the same language: **1px strokes, no fills, reference numerals in Sligoil Micro, callout
leaders at 30/60/90°, a scale bar.** SVG, currentColor, theme-aware. Never flat-vector marketing
illustration, never isometric-blob, never 3D-render-of-nothing.

---

## 8. GRID, SPACE, ALIGNMENT

### 8.1 The datum — the system's spine

A single vertical hairline at **column 5 of 16**, running the full height of every page,
uninterrupted, behind all content.

- Left of it → **CLAIM** (what we say)
- Right of it → **EVIDENCE** (what backs it)

**LAW:** the datum never moves, never breaks, appears on every page including 404. It is 1px at
`--edge-hair`. Once it exists, layout decisions stop being arbitrary — which is the entire reason
architects draw a datum.

### 8.2 Structural grid

| Breakpoint | Columns | Content max | Gutter | Margin |
|---|---|---|---|---|
| `xs` < 480 | 4 | fluid | 16 | 20 |
| `sm` 480–767 | 6 | fluid | 18 | 24 |
| `md` 768–1023 | 12 | 720 | 20 | 32 |
| `lg` 1024–1439 | 16 | 1080 | 20 | 64 |
| `xl` 1440–1919 | 16 | 1288 | 24 | 112 |
| `2xl` ≥ 1920 | 16 | 1440 | 24 | 160 |

### 8.3 The 9 / 7 asymmetry

Every content section and every product screen splits across the datum **9 columns claim / 7 columns
evidence**. Never 50/50 — symmetry is passive and kills hierarchy. Visitors are trained by the
layout before they ever reach the product.

### 8.4 Poché — the loaded margin

The outer margin is not empty. It carries, in `micro`:
- Section numbers (`03`)
- Asset identifiers (`HAER PA,51-PITBU,1--12`)
- Figure captions
- Span offsets

Hanging elements sit **outside** the text block. This single habit is most of the difference between
"webpage" and "monograph".

### 8.5 Spacing scale — closed set

```
2 · 4 · 8 · 12 · 16 · 24 · 32 · 40 · 56 · 72 · 96 · 128 · 160 · 224
```

**LAW:** no other spacing value exists. Baseline grid **8px**; type sits on a **4px** sub-grid.
Section vertical rhythm: `224 / 160 / 128 / 96`. Never eyeballed.

### 8.6 Alignment laws

- Hard left, rag right, everywhere.
- **Centred exactly once on the entire site** — the landing hero. That single exception is what
  makes it land.
- Numbers right-aligned in tables, always, tabular.
- Optical alignment beats mathematical: punctuation, quotes and the signal rule hang.
- Radius: **0** on paper and evidence. **3px** on interactive controls. **999px never.**
- Borders: one hairline weight. Cards are separated by **surface and temperature**, not outlines.

---

## 9. SURFACES, MATERIALS, ELEVATION

### 9.1 Elevation is light, not shadow — LAW (dark theme)

```css
.surface-raised{
  background:var(--surface-2);
  box-shadow:inset 0 1px 0 var(--edge-lift);   /* the lit top edge  */
  border-bottom:1px solid rgba(0,0,0,.35);      /* the contact AO    */
}
```

**No `box-shadow` blur in dark mode.** Drop shadows on dark grounds are the clearest tell of an
inexperienced system: there is no light source above to cast them.

In **light** theme, shadows are permitted but must be **two-layer and tinted warm**:

```css
--shadow-1: 0 1px 2px rgba(42,38,32,.07), 0 2px 6px rgba(42,38,32,.05);
--shadow-2: 0 2px 4px rgba(42,38,32,.06), 0 12px 28px rgba(42,38,32,.09);
--shadow-3: 0 4px 8px rgba(42,38,32,.06), 0 40px 96px rgba(42,38,32,.16);
```

### 9.2 The expressed joint

```css
.evidence{
  background:var(--evidence-bg);
  color:var(--evidence-text);
  border-radius:0;
  border-left:2px solid var(--signal);   /* the reveal — anastylosis */
}
```

Applied wherever system meets evidence: the evidence pane, disputed table rows, quoted spans,
document cards. **This is the most recognisable detail in the system. It never blurs, never fades,
never rounds.**

### 9.3 Material matrix

| Surface | Ground | Corner | Edge | Type |
|---|---|---|---|---|
| Void | `--bg-void` | — | — | `--text-1` |
| Panel | `--surface-1` | 3px | hairline + lift | `--text-1` |
| Evidence / paper | `--evidence-bg` | **0** | 2px signal left | `--evidence-text` |
| Data table | `--surface-1` | 0 | hairline rows | Sligoil |
| Overlay / modal | `--surface-2` | 3px | strong edge + shadow-3 | `--text-1` |
| Input | `--surface-2` | 3px | hairline, signal on focus | `--text-1` |
| Code | `--surface-3` | 3px | hairline | Sligoil |

---

## 10. MOTION

### 10.1 Duration scale — closed set, LAW

| Token | ms | Use |
|---|---|---|
| `--m-instant` | 90 | State flip, checkbox, tab underline |
| `--m-fast` | 160 | Hover, focus ring, tooltip |
| `--m-base` | 240 | Buttons, dropdowns, toasts |
| `--m-slow` | 420 | Panel open, drawer, route change |
| `--m-reveal` | 720 | Content entering viewport |
| `--m-cine` | 1200 | Landing act transitions only |

### 10.2 Curves — two, and only two

```css
--ease-out: cubic-bezier(.16, 1, .30, 1);    /* everything entering, everything moving */
--ease-io:  cubic-bezier(.65, 0, .35, 1);    /* things that leave and return */
```

**LAW:** no spring, no bounce, no overshoot, no elastic. Enterprise motion reads as *mechanism*, not
personality. `linear` is permitted only for marquees and progress.

### 10.3 Choreography laws

- Stagger **≤ 40ms** per item, **≤ 6 items**. Beyond that it reads as a loading bug.
- Entering = `opacity 0→1` + `translateY(8px→0)` + optional mask wipe. **Never scale, never rotate.**
- Text reveals use `overflow:hidden` + `translateY(110%→0)` at `--m-reveal`.
- Nothing animates on page load above the fold except the hero line and the preloader.
- Hover on a data row: background only. Never lift, never shadow, never move.
- **Scroll never animates a number that a user might read as data.** Counters are permitted only in
  the landing, where the count is rhetoric, not a report.

### 10.4 The reduced-motion contract — LAW

`prefers-reduced-motion: reduce` produces a **designed alternative**, not a disabled one:

- Landing → static art-directed frames per act, cross-faded at `--m-base`. **The Act III still — the
  reflection out of register — is the poster frame**, because it is the best frame anyway.
- Lenis disabled; native scroll restored.
- WebGL renders **one** frame per act and stops (`renderer.render` on demand only).
- All transitions collapse to opacity at 120ms.
- Marquees stop. Counters print final values.

### 10.5 Scroll authority — LAW

**Lenis owns the scrollbar. Nothing else reads `window.scrollY`.**

```js
const lenis = new Lenis({ duration:1.2, smoothWheel:true,
  easing:t => Math.min(1, 1.001 - Math.pow(2, -10*t)) });
gsap.ticker.add(t => lenis.raf(t * 1000));
gsap.ticker.lagSmoothing(0);
ScrollTrigger.scrollerProxy(...);
```

One RAF. One clock. GSAP ScrollTrigger is the single timeline authority; the WebGL loop subscribes
to it and never runs its own scroll listener.

### 10.6 Frame-rate independence — LAW

```js
const damp = (a, b, k, dt) => a + (b - a) * (1 - Math.pow(1 - k, dt));
```

Every lerp in the codebase uses this form. A fixed `a += (b-a)*0.07` is a merge blocker (F-02).

### 10.7 Camera law

Cameras are **damped toward targets**, never assigned from scroll. Scroll sets the target; the
camera chases it. This is the difference between "cheap scroll site" and "directed".

---

## 11. THE WEBGL SYSTEM

### 11.1 Stack

| Layer | Choice | Why |
|---|---|---|
| Renderer | **three.js `WebGPURenderer`**, WebGL2 fallback | WebGPU went mainstream in 2026; TSL compiles to both |
| Scene graph | **React Three Fiber v9** | Declarative composition, React lifecycle |
| Materials | **TSL** (Three Shading Language) | One node graph → WebGPU *and* WebGL |
| Helpers | **@react-three/drei** | Instancing, RT helpers, perf monitor |
| Post | **pmndrs/postprocessing** | Bloom, grain, vignette |
| Scroll | **Lenis** | Owns the scrollbar |
| Timeline | **GSAP + ScrollTrigger** | Single authority |
| Camera | **Theatre.js** | Camera is *directed* in an editor, not coded |
| Offscreen | **@react-three/offscreen** | Keeps main thread free for DOM |
| Assets | **KTX2 + Draco + meshopt** | Budget compliance |

### 11.2 The procession — compression and release

Four rooms, one continuous camera, no cuts. Wright's compression/release applied to scroll.

| Room | Scroll | Beat | Feeling |
|---|---|---|---|
| **I · APPROACH** | 0–14% | The reflection that lies | *caught* |
| **II · COMPRESSION** | 14–30% | The narrow passage of unlit documents | *unease* |
| **III · RELEASE / BLACKLIGHT** | 30–56% | The lamp; you audit it yourself | *agency* |
| **IV · THE ARCHIVE** | 56–84% | 41,206 fall | *scale* |
| **V · THE QUEUE** | 84–100% | Lights come up; product resolves | *relief* |

### 11.3 Room I — the reflection that lies

Black water, edge to edge, absolutely still. One anodized spec plate, raking key light, reads
`IP66 · 400 V · 16 A`. The reflection reads `IP54 · 400 V · 10 A`.

- Planar reflection through a render target — but the RT renders a **second scene** containing a
  different plate. The mirror is genuinely showing something else.
- The false plate tracks the pointer at **0.84×** the real one. It *almost* follows. That lag is
  what makes the wrongness surface before a visitor can name it.
- Scroll drives `uDecohere`: ripple amplitude 0.002 → 0.09, plus a lateral shear. The reflection
  comes apart while the real plate stays perfectly still.
- The plate is a **glTF with real bevels and a KTX2 albedo**, not a canvas texture (F-04). Etched
  type comes from a high-res baked map with a matched roughness map so the engraving catches the key
  differently from the field.

### 11.4 Room II — compression

Camera pushes into a passage between two walls of unlit stacked documents. FOV **48° → 32°**. Fog
density climbs `0.028 → 0.055`. Audio, if present, deadens. Deliberately uncomfortable: this is what
an unverifiable catalog feels like. Copy here is `meta`, small and tight.

### 11.5 Room III — blacklight (DOM, not WebGL) — LAW

**The document is real DOM.** Two stacked HTML documents — clean PIM export over true datasheet —
with a CSS radial mask on the top layer following the pointer, and a glass lens element above
(rim light, inner glow, warm drop shadow, slight `backdrop-filter`).

Rationale: this surface is *made of type*. Rendering it into a texture is L-6 and F-04. Native type
at device resolution is the single biggest quality jump available.

- Mask: `radial-gradient(circle var(--r) at var(--mx) var(--my), transparent 0 58%, #000 82%)`
- Evidence spans: `--ice` field, 2px `--signal` underline, span offsets in `micro` alongside.
- Sheet sits on `perspective(1600px) rotateY(-7deg) rotateX(1.2deg)`.
- The canvas drops to 30% opacity so the paper owns the frame.
- Keyboard path: `Tab` cycles the disputed rows; the lens snaps to the focused row. **The
  interaction is not mouse-only.**

### 11.6 Room IV — 41,206

- ~150k instanced points in a lattice. **Not** 1M: additive overdraw at that count is fillrate-bound
  on integrated graphics, and 150k reads identically at these camera distances.
- Fall is **analytic in the vertex shader** — `y = y₀ − ½gt²` with a per-point delay and rest height.
  No GPGPU, no compute pass, no simulation state. Deterministic, scroll-scrubbable, free to rewind.
- Bad points run hot while falling and cool on settling.
- Room V morphs the same buffer toward a second position attribute: disputed records snap into
  ranked rows at `z=0`, verified records recede to `z=−17` and out of focus.

### 11.7 Light-theme WebGL — the inversion

In THE LIGHT TABLE the scene is **not** simply brightened. It becomes a different room:

| | Vault (dark) | Light Table |
|---|---|---|
| Ground | Black water | **Milk glass** — a backlit light table |
| Key | Warm raking, 5200K, low | Soft top-down diffuse, 5600K |
| Fill | Cold hemispheric 12% | Bounce from the table surface, 45% |
| Fog | `0.028` graphite | `0.010` bone |
| Points | Additive on black | **Multiplicative on white** — records read as ink, not light |
| Bloom | 0.28 | 0.10 |
| Grain | 2.6% | 1.8% |

**LAW:** additive blending on a light ground is forbidden. It greys out and looks broken. The point
material switches blend mode with the theme.

### 11.8 Light discipline

- One sun. Always motivated (L-5).
- Bloom: threshold `0.86`, strength `0.28`, radius `0.34`, **half-resolution**.
- Grain `2.6%`, vignette `0.84` — as shader passes in linear space, before `OutputPass`. Never CSS
  overlays; they flatten the image.
- **Forbidden:** chromatic aberration, lens flare, god rays, volumetric shafts, rainbow bloom, more
  than one emissive hue on screen.

### 11.9 Budgets — spec, not aspiration

| Metric | Budget |
|---|---|
| FPS @ 1440p, Iris Xe | **60**, 1% low ≥ 45 |
| Initial JS (gz) | ≤ **220 KB** |
| Total landing transfer | ≤ **2.8 MB** |
| LCP | ≤ **1.8 s** on Fast 3G / 4× CPU throttle |
| INP | ≤ **200 ms** |
| CLS | **0.00** |
| Draw calls / frame | ≤ 40 |
| Texture memory | ≤ 96 MB |
| Main-thread block | ≤ 50 ms any task |

### 11.10 The degradation ladder — LAW

```
WebGPU + discrete GPU   full procession, bloom, 150k points
WebGPU / WebGL2         same, 90k points, bloom half-res
WebGL2 low-power        Rooms I & III only, static field art in IV
No WebGL                art-directed static frames per act
prefers-reduced-motion  static frames, native scroll
JS disabled             the full page, fully readable, unstyled canvas removed
```

**Every rung is designed, not degraded.** A person draws each fallback frame.

---

## 12. THE PAGES — EVERY SURFACE, PLANNED

**LAW:** no page reuses another page's composition. A site where every page is the same stack of
centred sections is the signature of generated work. Each template below has a distinct spatial
idea.

### 12.0 Sitemap

```
/                      Landing — the procession
/method                How it works — the mechanism
/evidence              What grounding actually means (the deep dive)
/benchmark             R3 leaderboard — including our losing scores
/research              Papers, phases, red-team
/docs                  Documentation
  /docs/quickstart
  /docs/cli
  /docs/api
  /docs/schema
/pricing               Commercial
/errata                The corrections log ← the signature page
/manifesto             Why this exists
/about  /careers  /legal  /changelog  /404  /500
── product ──
/app/queue             Triage queue
/app/record/:id        Record detail + evidence pane
/app/calibration       Confidence and coverage
/app/sources           Documents and ingestion
/app/settings
```

---

### 12.1 `/` — LANDING · *the procession*

**Spatial idea:** a walk through five rooms. Full-bleed WebGL, copy pinned in the frame.
**Length:** 860vh. **Templates reused elsewhere:** none.

| Region | Content | Type | Grid |
|---|---|---|---|
| HUD-TL | `ERRATA` / Verification layer | `meta` | fixed |
| HUD-TR | `ExtractBench 46.4 GF1` / The 49-point gap | `meta` | fixed |
| HUD-BL | act index · progress rail · act name | `meta` | fixed |
| HUD-BR | live pointer coordinates | `meta` | fixed |
| Act I | *Your catalog is a **reflection**.* | `d-1` Redaction 50, italic on one word | centred (the one exception) |
| Act I sub | We checked it against the thing it claims to reflect. | `meta` | centred |
| Act II | The page you were shown. The page **underneath** it. | `d-3` | cols 1–4 |
| Act II doc | the real DOM datasheet + lens | — | cols 8–16 |
| Act III | `41,206 ⁄1.2M` + *records disagree with their own evidence.* | `d-2` + `d-4` italic | cols 7–12 |
| Act IV | triage queue panel, bone, full width | `data-s` | cols 1–16 |
| Footer | HAER plate at 12%, sitemap, provenance line | `body-s` | 16 col |

**Preloader:** counter `000→100` in Redaction 20, a 300px fill rail, `Errata — loading evidence` in
`micro`. Waits on `document.fonts.ready` **and** a compiled first frame so there is no shader hitch
and no FOUT.

**Key interactions:** cursor-as-lamp in Act III; scroll-scrub everywhere; `Esc` skips to the product
panel; the whole page is readable with `?nogl=1`.

---

### 12.2 `/method` — *the mechanism*

**Spatial idea:** a **horizontal** pipeline. The page scrolls vertically but the illustration
advances left-to-right through five stages, pinned. The only horizontal composition on the site.

| Stage | Title | Illustration | Evidence panel |
|---|---|---|---|
| 01 | Ingest | Patent plate, document stack | file types, page counts |
| 02 | Re-derive | Annotated table detail | `derive()` output, mono |
| 03 | Ground | The span, highlighted, with offsets | character offsets |
| 04 | Calibrate | Reliability diagram, drawn in our line style | coverage/risk curve |
| 05 | Rank | The queue | ranked rows |

Each stage is 9/7: claim left, a live evidence panel right. The illustration is an SVG in the
technical-drawing language of §7.7 — 1px strokes, reference numerals, a scale bar.

**Signature detail:** the stage number is set in Redaction, degrading backwards — stage 01 is
Redaction 50, stage 05 is Redaction 0. The record sharpens as it is verified.

---

### 12.3 `/evidence` — *the deep dive*

**Spatial idea:** a **two-column parallel reading**, permanently split by the datum: the document on
the left, our derivation on the right, scrolling in lockstep. The most "product" of the marketing
pages.

- Sticky document viewer, real DOM, real type, real spans.
- Clicking a value in the right column scrolls and highlights its span on the left. Both directions.
- Below: three worked cases, including **one where Errata was wrong**, shown in full. *(This is
  brand strategy, not modesty. A verification product that only publishes wins is not credible.)*
- Section on grounding F1, the 46.4 figure, and — verbatim from the README — the fact that R1's
  100% is a tautology the report refuses to let you quote.

---

### 12.4 `/benchmark` — *the leaderboard that prints our losses*

**Spatial idea:** a **full-bleed data table as the hero.** No hero image, no headline above the fold
— the table *is* the hero, starting 120px from the top. Nothing else on the site does this.

- Columns: system, coverage, grounding F1 (corpus), grounding F1 (answered), evidence returned.
- Our own rows are marked and **not sorted to the top**.
- The table is filterable by extractor (`tableblind` / `r1` / `r1-textwindow`).
- Every figure links to the command that reproduces it.
- Open exit criteria (D-3, D-4, D-5) are shown **as open**, in a signal-washed panel, on this page.

**Signature detail:** hovering a figure reveals its provenance in the hanging margin — read date,
source, page, and whether the paper printed that precision (L-4 made visible).

---

### 12.5 `/research`

**Spatial idea:** an **archive index**. A dense, left-aligned list — phase documents, red-team
report, decisions D-1…D-n — set like a bibliography. Numbers hang in the margin. Almost no imagery;
the density is the aesthetic.

Each decision renders as a card: what was decided, what it cost, what remains unmeasured.

---

### 12.6 `/docs`

**Spatial idea:** a **three-column reading room** — nav 3 / content 9 / on-this-page 4. Light theme
by default even when the site is dark (docs are read like paper, L-2).

- Code blocks in Sligoil, `--surface-3`, copy button, language label in `micro`.
- Callouts: Note (hairline), Warning (signal left rule), Verified (verdigris left rule).
- Every CLI example is runnable and tested in CI.
- Search: `⌘K`, mono, results grouped by section.

---

### 12.7 `/pricing`

**Spatial idea:** **not** three cards. A single **specification sheet** — one table, rows are
capabilities, columns are tiers, set like a product datasheet with a part number and a revision
date. The page is itself an example of well-structured product data.

Footer of the table: "This page is a product record. If any figure here disagrees with your
contract, the contract is the evidence."

---

### 12.8 `/errata` — **the signature page**

**Spatial idea:** a **reverse-chronological corrections log** — every error this company has
published and later fixed, with dates, what was wrong, and what it is now.

The README already contains the first entry: a `46.43` corrected to `46.4` because *"a figure quoted
to a digit nobody published is the beginning of a number nobody can check."*

Set as a ledger: date in the margin, the wrong value struck through in Redaction 50, the corrected
value in Redaction 0 beside it. The degradation axis doing semantic work again.

**Why this page exists:** it is the most persuasive page on the site. A verification company that
publishes its own errata is making an argument no competitor can copy without actually being honest.

---

### 12.9 `/app/queue` — *triage*

**Spatial idea:** a **workbench**. Full-height, no page scroll — a list pane and an evidence pane,
side by side, both scrolling independently. Light theme default.

| Region | Cols | Content |
|---|---|---|
| Rail | 1 | Filters, saved views, icon+label, collapsible |
| Queue | 2–8 | Ranked rows: record, attribute, catalog value, evidence value, confidence, span |
| Evidence | 9–16 | The source document, span highlighted, page and offsets |

- Row states: `disputed` (signal wash + 2px reveal), `grounded` (plain), `waived` (dimmed), `open`.
- Keyboard-first: `j/k` move, `Enter` open, `y` confirm evidence, `n` reject, `w` waive, `/` search,
  `⌘K` command palette. **Triage is a repetition task; the mouse is the slow path.**
- Bulk select with `x`, action bar rises from the bottom edge.
- Empty state: a HAER plate at 6%, "Nothing is in dispute. That is a result, not an absence."

### 12.10 `/app/record/:id`

**Spatial idea:** a **specimen sheet**. Header carries the record identity; below, the attribute
table on the left and, pinned right, the document with the active span lit. Every attribute row
expands in place to show derivation, confidence, and the exact span.

- The disputed value appears **twice, adjacent**: catalog in Redaction 50, evidence in Redaction 0.
  The typographic distance *is* the disagreement.
- A "why" drawer prints the derivation chain in Sligoil.

### 12.11 `/app/calibration`

**Spatial idea:** a **chart room**. Reliability diagram, coverage/risk curve, per-class coverage.
Charts are drawn in the technical-drawing language: 1px strokes, no fills, no gradient areas,
tabular axis labels, the datum as the y-axis.

Gate 3 is shown **as unmeasured**, with the reason, per decision D-3. Not hidden, not faked.

### 12.12 `/app/sources`

**Spatial idea:** a **library**. A grid of document cards, each showing first-page thumbnail (real
render, treated per §7.5), page count, ingest date, and how many attributes were grounded from it.

### 12.13 `/app/settings`

Standard two-column form template. Included here so it is designed rather than improvised. Theme
toggle lives here *and* in the header.

### 12.14 `/404` and `/500`

**Spatial idea:** the void state. Redaction 100 at `d-1` — a headline you literally cannot read —
resolving to Redaction 0 on hover or focus.

- 404: "This record does not exist." + search + three most-read pages.
- 500: "We could not verify this page." + status link + the incident id in `micro`.

---

## 13. COMPONENT LIBRARY

Every component ships with: default / hover / focus-visible / active / disabled / loading / error /
empty, in **both themes**, plus a reduced-motion variant. **LAW:** a component without all states is
not done.

### 13.1 Primitives

| Component | Spec notes |
|---|---|
| `Button` | 3px radius, 36/44px heights. Primary = `--text-1` on `--surface-3` with a 1px lift; **never** signal-filled — signal means dispute, not "click me". Focus: 2px `--focus-ring` at 2px offset |
| `IconButton` | 32px, hit area 44px, tooltip after 400ms |
| `Input` | 3px, hairline, `--signal` 1px on focus + ring. Label above in `col`. Error text in `micro` signal |
| `Select` | Native on mobile, custom listbox on desktop, full ARIA combobox pattern |
| `Checkbox` / `Radio` | 16px, 2px stroke, `--m-instant` |
| `Toggle` | Only for binary settings. Never for filters |
| `Tabs` | Underline 2px, slides on `--m-base`, roving tabindex |
| `Tooltip` | `--surface-3`, `micro`, 6px offset, 400ms delay, never on touch |
| `Toast` | Bottom-left, stacks to 3, auto-dismiss 6s, pause on hover, `role="status"` |
| `Modal` | Focus trap, `Esc`, scrim `rgba(7,8,10,.72)`, returns focus on close |
| `Drawer` | Right, 480px, same trap rules |
| `Menu` | Roving tabindex, type-ahead, `⌘K` palette shares its renderer |

### 13.2 Data

| Component | Spec notes |
|---|---|
| `DataTable` | Sticky head, virtualised beyond 200 rows, column resize, sort with an accessible announcement, tabular numerals **LAW** |
| `Cell.Value` | Sligoil, right-aligned, slashed zero, **never rounded beyond source precision (L-4)** |
| `Cell.Disputed` | `--signal-050` wash + 2px left reveal + struck catalog value |
| `Cell.Span` | `--ice` field, 2px signal underline, offsets in `micro` |
| `Confidence` | A 5-segment bar, achromatic on purpose. Calibration should not shout |
| `ProvenanceTag` | Institution + identifier + retrieved date, `micro`, hangs in margin |
| `DiffPair` | The catalog value in Redaction 50 above the evidence value in Redaction 0. The signature data component |
| `Chart.Reliability` | 1px strokes, no fill, datum as y-axis, tabular labels |
| `Chart.Coverage` | Same language; the operating point marked with a hanging label |

### 13.3 Document

| Component | Spec notes |
|---|---|
| `DocumentView` | Real DOM or PDF.js text layer. **Never an image-only render — spans must be selectable (L-6)** |
| `SpanHighlight` | `--ice` field, signal underline, `aria-describedby` the offsets |
| `Lens` | The blacklight. Pointer-driven mask + glass ring. Keyboard: focus a row, lens snaps |
| `PlateFigure` | Treated public-domain plate + provenance in the hanging margin |
| `PageThumb` | Real first-page render, treated per §7.5 |

### 13.4 Layout & chrome

`Datum`, `Poche`, `SectionOpener`, `ClaimEvidence` (the 9/7), `HudFrame`, `ThemeToggle`,
`CommandPalette`, `Header`, `Footer`, `SkipLink`.

### 13.5 States gallery — LAW

`/app/_states` renders every component in every state in both themes on one page. It is the
screenshot-diff target in CI and the first thing a reviewer opens.

---

## 14. VOICE & CONTENT

### 14.1 Rules

- **Never claim what is not measured.** Where an exit criterion is open, say so on the page.
- **Never render a precision the source lacks** (L-4). This applies to copy as well as data.
- Sentences are short. Numbers are exact. Adjectives are rare.
- The product's own README is the tone reference. Match it; do not brighten it.
- Forbidden: "seamless", "effortless", "revolutionary", "AI-powered", "next-generation",
  "unlock", "supercharge", "leverage", "game-changing".
- Permitted and encouraged: "measured", "unmeasured", "we do not know", "this is a waiver",
  "recorded as decision D-4".

### 14.2 Microcopy

| Situation | Copy |
|---|---|
| Empty queue | "Nothing is in dispute. That is a result, not an absence." |
| No evidence found | "No span supports this value. We are not going to guess one." |
| Low confidence | "Below the operating point. Not shown as a finding." |
| Load failure | "We could not verify this page." |
| Unmeasured gate | "Not measured. The harness exists; the input does not." |

---

## 15. ACCESSIBILITY — WCAG 2.2 AA MINIMUM

### 15.1 Laws

- **Keyboard parity.** Every mouse interaction has a keyboard path, including the Act III lens.
- **Focus is always visible.** 2px `--focus-ring`, 2px offset, never removed. Never `outline:none`
  without a replacement.
- **The custom cursor is decoration.** The system cursor remains available; `cursor:none` is applied
  only over the canvas, and never when a pointing device is coarse or when reduced-motion is set.
  *(This was a real defect in the prototype — F-12.)*
- **Scroll is never trapped.** Lenis smooths; it does not hijack. `Esc` jumps to the end of the
  procession. A skip link is the first focusable element.
- **Motion preference is honoured in every animated surface** (§10.4), not just some.
- Landmarks: one `<main>`, labelled `<nav>`, `<h1>` per page, no skipped heading levels.
- Live regions for async: `role="status"` for toasts, `aria-live="polite"` for sort/filter results.
- Targets ≥ 44×44 CSS px (2.5.8).
- Colour is never the only carrier: disputed rows have the reveal **and** a text state **and** a
  struck value.
- `lang` set; text resizes to 200% without loss; reflow at 320px.
- Full alt text on plates, including the identifier.

### 15.2 CI gates

`axe-core` on every route, both themes · contrast assertions on the token file · keyboard-only smoke
test on the landing and the queue · screenshot diff of `/app/_states`.

---

## 16. PERFORMANCE

### 16.1 Budgets (repeat of §11.9, enforced)

| Metric | Budget | Enforcement |
|---|---|---|
| LCP | ≤ 1.8s | Lighthouse CI, fails PR |
| INP | ≤ 200ms | field + lab |
| CLS | 0.00 | fails PR |
| Initial JS gz | ≤ 220 KB | `size-limit` |
| Landing total | ≤ 2.8 MB | bundle report |
| Fonts | ≤ 180 KB total | subset check |
| FPS | 60 / 1% low ≥ 45 | `stats-gl` in the perf harness |

### 16.2 Techniques

- Self-hosted subset woff2, `font-display:swap`, metric-overridden (§5.3) → CLS 0.
- WebGL bundle is **dynamically imported** after first paint and only when the viewport is ≥768px
  and `prefers-reduced-motion` is not set.
- `@react-three/offscreen` moves the render loop to a worker.
- AVIF/WebP, explicit dimensions, `loading="lazy"` below fold, `fetchpriority="high"` on the LCP image.
- Route-level code splitting; the product app never loads the landing's shaders.
- Adaptive quality: `PerformanceMonitor` steps DPR `1.6 → 1.25 → 1.0` before it drops effects.
- Long tasks broken with `scheduler.yield()`.

---

## 17. STACK & ARCHITECTURE

```
Next.js 15 (App Router, RSC)
├── TypeScript strict
├── Tailwind v4 — tokens only via @theme, no arbitrary values (LAW)
├── Radix primitives (behaviour) + our own skins
├── R3F v9 + three (WebGPURenderer) + TSL + drei + postprocessing
├── Lenis + GSAP/ScrollTrigger + Theatre.js
├── Storybook — the states gallery
├── Vitest + Playwright + axe + Lighthouse CI
└── Content: MDX for docs/manifesto/errata, YAML for asset provenance
```

```
/app                     routes
/components
  /primitives            button, input, …
  /data                  table, cells, charts
  /document              viewer, span, lens, plate
  /layout                datum, poche, claim-evidence, hud
/three
  /scenes                room-01…room-05
  /materials             TSL node materials
  /hooks                 useScrollProgress, useDampedCamera, useTheme3D
/styles
  tokens.css             palette + semantic (the only place colour is written)
  type.css               @font-face + scale
/content
  /assets/*.yml          provenance records
  /docs/*.mdx
/public/fonts            self-hosted woff2
```

**LAW:** `tokens.css` is the only file in the repository containing a colour literal. A hex value
anywhere else fails lint.

---

## 18. EXECUTION PHASES

Phased the way a practice phases a building. **A phase does not start until the previous gate passes.**

> **Naming — decision D-FE-1, 21 August 2026.** These stages are called
> **FE-0 … FE-9**, not "phase 0–9". The repository already uses *phase* for
> `PHASES.md`'s **P0–P7**, the research and product gates that map onto the PRD's
> releases `R0`–`R4`. Two tracks called "phase 3" is a defect waiting for a
> review meeting to find it. The ledger, the gate reports and the errata this
> plan has already accumulated live in **`docs/frontend/`**, starting with
> [`FE-PHASES.md`](frontend/FE-PHASES.md).

| Phase | Deliverable | Gate |
|---|---|---|
| **0 · Concept** | This document | Signed off by brand + product |
| **1 · Schematic** | `tokens.css`, `type.css`, both themes live; one full-fidelity static comp of Room I | **Judge the direction before a shader exists** |
| **2 · Design development** | Datum grid, 20 core components in Storybook, both themes, all states | Nothing enters DD without a token |
| **3 · Art** | 30 treated plates + provenance YAML + the illustration kit | No untreated asset (§7.5) |
| **4 · Motion prototype** | Lenis + GSAP + Theatre camera path, **grey boxes only, no materials** | Camera approved *blind*. If it isn't good in grey, materials won't save it |
| **5 · Shader R&D** | TSL materials in isolation; the reflection RT; the fall | **Perf budget met before integration, not after** |
| **6 · Landing build** | Rooms I–V wired, DOM Act III, full ladder | Page works with `?nogl=1` |
| **7 · Product build** | Queue, record, calibration, sources, settings | Keyboard-only run-through passes |
| **8 · Content** | Docs, benchmark, errata log, manifesto | Every figure links to its reproduction command |
| **9 · Snagging** | Optical corrections: kerning at `d-1`/`d-2`, hairline alignment, the 2px reveal at every joint, both themes | **The last 5% is the whole difference** |

---

## 19. DEFINITION OF DONE

A PR merges only if every line is true.

- [ ] No colour literal outside `tokens.css`
- [ ] No spacing value outside the closed set (§8.5)
- [ ] No duration or curve outside the motion scale (§10.1–10.2)
- [ ] Every lerp is frame-rate independent (§10.6)
- [ ] Nothing reads `window.scrollY` except Lenis (§10.5)
- [ ] No text rendered into a canvas texture (L-6)
- [ ] Component has all 8 states, both themes, in Storybook
- [ ] `prefers-reduced-motion` variant designed, not disabled
- [ ] Keyboard path verified for every interaction
- [ ] `axe` clean on the route, both themes
- [ ] Contrast assertions pass
- [ ] No figure displays precision beyond its source (L-4)
- [ ] Any new asset has a provenance YAML and is treated (§7.4–7.5)
- [ ] Bundle and LCP budgets pass
- [ ] Page renders correctly with JS disabled and with `?nogl=1`
- [ ] Screenshot diff reviewed

---

## 20. APPENDIX — TOKEN FILE

```css
/* tokens.css — the only file containing colour literals */
:root{
  /* ── palette ───────────────────────────────────────── */
  --p-graphite-950:oklch(.145 .008 250); --p-graphite-900:oklch(.195 .010 250);
  --p-graphite-850:oklch(.235 .011 250); --p-graphite-800:oklch(.275 .012 250);
  --p-graphite-700:oklch(.345 .012 250); --p-graphite-600:oklch(.425 .012 250);
  --p-graphite-500:oklch(.520 .011 250); --p-graphite-400:oklch(.620 .010 250);
  --p-graphite-300:oklch(.720 .009 250); --p-graphite-200:oklch(.820 .007 250);
  --p-graphite-100:oklch(.900 .005 250);

  --p-bone-50:oklch(.972 .010 78);  --p-bone-100:oklch(.952 .012 78);
  --p-bone-200:oklch(.918 .015 78); --p-bone-300:oklch(.868 .018 78);
  --p-bone-400:oklch(.780 .020 74); --p-bone-700:oklch(.470 .018 70);
  --p-bone-900:oklch(.250 .014 70); --p-bone-950:oklch(.190 .012 70);

  --p-signal-700:oklch(.420 .155 20); --p-signal-600:oklch(.505 .175 20);
  --p-signal-500:oklch(.560 .180 20); --p-signal-400:oklch(.660 .150 20);
  --p-signal-100:oklch(.920 .040 22); --p-signal-050:oklch(.960 .020 22);

  --p-verdigris-600:oklch(.560 .060 178); --p-verdigris-300:oklch(.820 .035 178);
  --p-ice-200:oklch(.920 .030 230);       --p-ice-400:oklch(.800 .045 230);

  /* ── semantic: LIGHT is the base definition ─────────── */
  --bg-void:var(--p-bone-100);      --surface-1:var(--p-bone-50);
  --surface-2:#fff;                 --surface-3:var(--p-bone-200);
  --edge-hair:rgba(20,18,14,.085);  --edge-strong:rgba(20,18,14,.17);
  --edge-lift:rgba(255,255,255,.9);
  --text-1:var(--p-bone-950);       --text-2:var(--p-bone-700);
  --text-3:oklch(.560 .014 70);
  --signal:var(--p-signal-600);     --settled:var(--p-verdigris-600);
  --evidence-bg:var(--p-bone-50);   --evidence-text:var(--p-bone-950);
  --focus-ring:var(--p-signal-600);

  /* ── space ──────────────────────────────────────────── */
  --s-2:2px;   --s-4:4px;   --s-8:8px;   --s-12:12px; --s-16:16px;
  --s-24:24px; --s-32:32px; --s-40:40px; --s-56:56px; --s-72:72px;
  --s-96:96px; --s-128:128px; --s-160:160px; --s-224:224px;

  /* ── motion ─────────────────────────────────────────── */
  --m-instant:90ms; --m-fast:160ms; --m-base:240ms;
  --m-slow:420ms;   --m-reveal:720ms; --m-cine:1200ms;
  --ease-out:cubic-bezier(.16,1,.30,1);
  --ease-io:cubic-bezier(.65,0,.35,1);

  /* ── type ───────────────────────────────────────────── */
  --f-display:'Redaction 20','Redaction 0',Spectral,Georgia,serif;
  --f-degraded:'Redaction 50','Redaction 20',Georgia,serif;
  --f-text:'Apfel Grotezk',Switzer,system-ui,sans-serif;
  --f-data:'Sligoil','Geist Mono',ui-monospace,monospace;
}

@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg-void:var(--p-graphite-950);  --surface-1:var(--p-graphite-900);
    --surface-2:var(--p-graphite-850);--surface-3:var(--p-graphite-800);
    --edge-hair:rgba(255,255,255,.055);--edge-strong:rgba(255,255,255,.115);
    --edge-lift:rgba(255,255,255,.075);
    --text-1:var(--p-bone-50);        --text-2:var(--p-graphite-300);
    --text-3:var(--p-graphite-400);
    --signal:var(--p-signal-500);     --settled:var(--p-verdigris-300);
    --evidence-bg:var(--p-bone-100);  --evidence-text:var(--p-bone-950);
    --focus-ring:var(--p-ice-200);
  }
}
:root[data-theme="dark"]{
  --bg-void:var(--p-graphite-950);  --surface-1:var(--p-graphite-900);
  --surface-2:var(--p-graphite-850);--surface-3:var(--p-graphite-800);
  --edge-hair:rgba(255,255,255,.055);--edge-strong:rgba(255,255,255,.115);
  --edge-lift:rgba(255,255,255,.075);
  --text-1:var(--p-bone-50);        --text-2:var(--p-graphite-300);
  --text-3:var(--p-graphite-400);
  --signal:var(--p-signal-500);     --settled:var(--p-verdigris-300);
  --evidence-bg:var(--p-bone-100);  --evidence-text:var(--p-bone-950);
  --focus-ring:var(--p-ice-200);
}

@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.01ms!important;
    transition-duration:120ms!important;scroll-behavior:auto!important}
}
```

---

## 21. THE SCHEME, IN ONE SENTENCE

> **A dark mass, one raking light, warm paper, and a repair you are never allowed to stop seeing.**

If a decision does not serve that sentence, it does not get built.

---

### Open questions for the next review

1. **Type licensing.** Redaction / Apfel Grotezk / Sligoil are OFL and free. If budget appears, the
   paid tier is Signifier + Söhne + Söhne Mono (Klim). Which are we planning for?
2. **Which extractor's numbers lead the benchmark page** — `tableblind`, or `r1-textwindow`?
   §12.4 currently assumes both, unsorted, with ours unhighlighted.
3. **Does `/errata` publish before launch or after?** It is the strongest page on the site and it
   needs at least three real entries to be credible.
4. **Audio.** The Trionn reference layers Web Audio into the procession. Powerful, and a liability
   on an enterprise laptop in an open office. Recommendation: off by default, one mono toggle in the
   HUD.
