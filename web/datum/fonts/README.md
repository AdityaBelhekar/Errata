# DATUM — the type: what was fetched, from where, and what is measured from it

**Status: LANDED, 22 August 2026 — ten of eleven declared faces.**

The one exception is `Sligoil-Regular`, which the foundry does not publish. It has
**not** been substituted; see [ADR-006](../../../docs/adr/ADR-006-sligoil-regular-does-not-exist.md).

The original text of this file follows the acquisition log, unedited, because it
is the record of what was promised and it is worth being able to check the
promise against the delivery.

---

## Acquisition log

Fetched 22 August 2026. All three from **first-party sources** — the project's own
site or the foundry's own repository. No third-party font mirror was used: a
binary from an unverified mirror is not the same artefact even when it has the
same name.

| Family | Source | Archive SHA-256 |
|---|---|---|
| Redaction | `https://www.redaction.us/static/redaction.zip` | `3bc97cfd8e6a9611…` |
| Apfel Grotezk | `https://github.com/collletttivo/apfel-grotezk` (`main`) | `1192845fe5fdc552…` |
| Sligoil | `https://gitlab.com/velvetyne/sligoil` (`main`) | `322059c1b0cfe437…` |

### Installed files

| File | Size | SHA-256 |
|---|---:|---|
| `redaction/Redaction_0-Regular.woff2` | 28,392 B | `13b7352c2729e67c…` |
| `redaction/Redaction_100-Regular.woff2` | 19,504 B | `18f6df94d9d9949b…` |
| `redaction/Redaction_20-Italic.woff2` | 78,536 B | `7a18cff5d7223a92…` |
| `redaction/Redaction_20-Regular.woff2` | 68,996 B | `7faedff3b274a922…` |
| `redaction/Redaction_50-Regular.woff2` | 32,972 B | `7dcdd9b0f9b0675f…` |
| `apfel/ApfelGrotezk-Brukt.woff2` | 35,484 B | `661ae837ad5701bf…` |
| `apfel/ApfelGrotezk-Fett.woff2` | 20,128 B | `5f799ce6e8fec2b6…` |
| `apfel/ApfelGrotezk-Mittel.woff2` | 20,564 B | `869899ef1bdd5b13…` |
| `apfel/ApfelGrotezk-Regular.woff2` | 19,852 B | `5fd817f20d9fac6b…` |
| `sligoil/Sligoil-Micro.woff2` | 42,420 B | `c4381c326f79b05a…` |

### Departures from the spec, both recorded rather than smoothed over

1. **`Redaction_0-Regular.woff2` does not exist under that name.** The release ships the
   undegraded face as `Redaction-Regular.woff2` — grade 0 is the base design, and the number is
   omitted rather than written as zero. It is the same face; the file was renamed on install and
   this line is the record of that.

2. **`Sligoil-Regular.woff2` does not exist at all.** Not renamed, not moved — the current release
   contains only Micro cuts. Not substituted. ADR-006.

### What was done, against the five steps below

1. **Fetch** — done, logged above.
2. **Subset and convert** — **NOT done, deliberately.** The upstream releases already ship
   `.woff2`, so no conversion was needed. Subsetting was declined: a subset is a derivative, which
   raises reserved-name and attribution questions under the OFL, to save ~40 KB on a page that
   already loads 183 KB of WebGL engine. Recorded in `NOTICE`.
3. **Measure the fallback metrics** — **done.** `web/datum/tools/font-metrics.py` produced every
   `size-adjust` / `ascent-override` / `descent-override` in `type.css` from the real files. No
   value is approximated and no `<MEASURE>` placeholder remains.
4. **Do not quote a CLS number until step 2** — the measured basis now exists. What it does and
   does not license is in `docs/frontend/PERF-BASELINE.md` §3; the overrides were measured against
   the fallbacks *as installed on one machine*, which is right for the common case and approximate
   elsewhere.
5. **Ship the OFL** — **done.** `OFL.txt` verbatim in each family directory, all three named in
   `NOTICE`.

### Still open

- **Step 5 of the original list below: re-review the FE-1 Room I comp and the FE-2 specimen.**
  The degradation axis can now be seen for the first time. Nobody has looked at it. That is a
  design judgement, and it is the reason ADR-006 is Proposed rather than Accepted.
- **42 screenshot baselines were captured in fallback faces** and have been regenerated with the
  real type. They were renamed `-fallback` → `-specified` in the same commit, because the images
  changed regardless and splitting it would have produced two unreviewable diffs instead of one.

---

## Original text, as written when the fonts were absent

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
