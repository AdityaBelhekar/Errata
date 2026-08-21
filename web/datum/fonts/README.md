# DATUM — the type, and why it is not in this directory

**Status: the three specified families are NOT in this repository.** Every page
under `web/datum/` currently renders in its fallback stack. This file records
what must be fetched, from where, under which licence, and what must be measured
once it lands.

This is written down rather than quietly left as a broken `@font-face` because of
ground rule 1 (`HANDOFF.md` §8): the honest statement of a missing thing is the
missing thing, named. A comp reviewed in Georgia is not a comp reviewed in
Redaction, and a reviewer is entitled to know which one they are looking at.

---

## What is specified (blueprint §5.2)

| Voice | Family | Designer / foundry | Licence | Cuts needed |
|---|---|---|---|---|
| **Display** | **Redaction** | Forest Young & Jeremy Mickel | SIL OFL 1.1 | `0`, `20`, `20 Italic`, `50`, `100` — all Regular |
| **Text** | **Apfel Grotezk** | Collletttivo | SIL OFL 1.1 | Regular, Mittel, Fett, **Brukt** |
| **Data** | **Sligoil** | Ariel Martín Pérez · Velvetyne | SIL OFL 1.1 | Regular, Micro |

All three are libre. There is no licence cost and no licence blocker; there is a
fetch step, and it has not been done.

**Do not substitute silently.** If a face turns out to be unavailable, that is a
change to §5.2 and needs the same written argument any other blueprint change
needs — not a quiet swap in `tokens.css`.

## Where they come from

- **Redaction** — <https://www.redaction.us/> (the project's own site) and the
  designers' foundries. Drawn for *The Redaction*, a project about the criminal
  justice system: type as a record decaying through reproduction.
- **Apfel Grotezk** — Collletttivo, <https://www.collletttivo.it/>
- **Sligoil** — Velvetyne Type Foundry, <https://velvetyne.fr/fonts/sligoil/>

<sub>URLs recorded as the addresses named in blueprint §5.2. They have not been
fetched or verified from this machine. Anyone doing the acquisition should treat
them as a starting point and record what they actually downloaded, below.</sub>

## Target layout

```
web/datum/fonts/
  redaction/  Redaction_0-Regular.woff2   Redaction_20-Regular.woff2
              Redaction_20-Italic.woff2   Redaction_50-Regular.woff2
              Redaction_100-Regular.woff2
  apfel/      ApfelGrotezk-Regular.woff2  ApfelGrotezk-Mittel.woff2
              ApfelGrotezk-Fett.woff2     ApfelGrotezk-Brukt.woff2
  sligoil/    Sligoil-Regular.woff2       Sligoil-Micro.woff2
  OFL.txt     × 3, one per family, kept verbatim
```

`styles/type.css` already declares every one of these `@font-face` rules against
exactly these paths. Dropping the files in is the whole integration.

---

## What must be done when they land — not optional

1. **Subset and convert.** Latin + Latin-1 Supplement + the punctuation the site
   actually uses. `pyftsubset` from `fonttools`. Keep the full-range originals
   out of `/public`.
2. **Measure the fallback metrics.** §5.3 is a LAW: every `@font-face` carries
   `size-adjust`, `ascent-override` and `descent-override` tuned to its fallback
   so the swap causes **zero layout shift**. Those three properties are
   currently marked `<MEASURE>` in `type.css` and are **absent**, not
   approximated. Produce them from the real files.
3. **Do not quote a CLS number until step 2 is done.** The blueprint's 0.00 CLS
   budget is a target, not a measurement. Publishing it as though it were
   measured is the failure FR-9.1 exists to prevent.
4. **Ship the OFL.** SIL OFL 1.1 requires the licence to travel with the fonts.
   Add each family's `OFL.txt` verbatim and list all three in the repository's
   `NOTICE`.
5. **Re-review the FE-1 Room I comp and the FE-2 specimen.** The degradation
   axis (§5.2) is the single most distinctive decision in this design system and
   **nobody has seen it yet**. Until Redaction is present, the difference
   between a verified value and an unverified one is carried entirely by colour
   and strike-through — which is a weaker system than the one that was
   specified, and it should be re-judged, not assumed to work.

## What is affected right now

| Surface | What is real | What is a stand-in |
|---|---|---|
| `room-i.html` | Composition, the lie in the reflection, both themes, the lamp | Every letterform; the hero's Redaction 50 degradation |
| `grid.html` | Sizes, leadings, tracking curve, measure, the four-cut axis *as structure* | The four cuts render identically |
| `states.html` | All twenty components, all states, both themes | `DiffPair` — its whole argument is the axis |
| `styles/type.css` | The scale, the curve, the family stacks | `size-adjust` / ascent / descent overrides |
