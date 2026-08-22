# ADR-006 — The data voice specifies a cut the foundry does not publish

**Status:** Proposed — **needs a decision that is not engineering's to make**
**Date:** 22 August 2026
**Blocks:** closing FE-1 O-1 completely; the last entry in the smoke suite's known-missing list.

## Context

Blueprint §5.2 specifies the data voice as **Sligoil**, cuts **"Regular, Micro"**. `type.css`
declares both, and `tokens.css` builds two stacks on them:

```css
--f-data:       'Sligoil', 'Geist Mono', ui-monospace, 'SF Mono', Menlo, monospace;
--f-data-micro: 'Sligoil Micro', 'Sligoil', 'Geist Mono', ui-monospace, monospace;
```

The fonts were fetched on 22 August 2026 from Velvetyne's own repository
(`gitlab.com/velvetyne/sligoil`, archive digest in `web/datum/fonts/README.md`). **The release
contains only Micro cuts:**

| Present | Absent |
|---|---|
| `Sligoil-Micro` · `Sligoil-MicroMedium` · `Sligoil-MicroBold` | anything named `Sligoil-Regular` |

There is also a variable font, `SligoilVF`, whose axis has not been examined for a non-Micro
instance. That is the one avenue not yet closed off — see *Option D*.

This was not discovered by reading the blueprint. It was discovered by the build:
`vite build` prints
`../fonts/sligoil/Sligoil-Regular.woff2 ... didn't resolve at build time`, and the smoke suite's
known-missing list is now exactly one file long.

## Why this is not simply "use Micro"

`web/datum/fonts/README.md` states the rule this ADR exists to honour:

> **Do not substitute silently.** If a face turns out to be unavailable, that is a change to §5.2
> and needs the same written argument any other blueprint change needs — not a quiet swap in
> `tokens.css`.

Micro is **not Sligoil at a smaller size**. It is a separate design drawn for small optical sizes —
larger apertures, shorter extenders, looser fit. Using it for body-sized data would look like a
different typeface being used badly, which is precisely the outcome the design system's whole
premise is meant to prevent. The two stacks above already treat them as distinct families, which is
the design acknowledging the distinction before anyone checked whether both files existed.

## Options

| | Option | What it costs |
|---|---|---|
| **A** | **Ship as is.** `--f-data` falls through to `ui-monospace`; `--f-data-micro` gets real Sligoil Micro. | The data voice — *"a machine is speaking, and you can check it"* — is carried by the system monospace at body size and by Sligoil only in micro type. Half the voice is unrealised. Costs nothing and is honest, because the gap is visible in the build output and the test allow-list. |
| **B** | **Amend §5.2 to name Sligoil Micro as the data voice at all sizes.** | A written blueprint change. Micro at body size is a real design compromise and needs someone to look at it set that way before it is ratified — which cannot happen until FE-3's plates are re-cut. |
| **C** | **Choose a different family for the non-Micro data cut.** | The largest change: a new family is a new licence, a new acquisition, new metric overrides, and a re-judgement of §5.2's three-voice argument. |
| **D** | **Check `SligoilVF` for a non-Micro instance.** | Cheapest to investigate and not yet done. If the variable font carries an optical-size or width axis reaching a text design, A becomes unnecessary. **This should be tried before B or C are argued.** |

## Decision

**None yet — deliberately.** Engineering's part is finished: the face is not substituted, the gap is
visible in three places that fail loudly rather than quietly (the build warning, the test
allow-list, the `@font-face` comment), and nothing downstream silently assumes a font that is not
there.

What remains is a **design judgement**, and FE-1 O-1's original point applies with more force now
than when it was written: *nobody has seen the degradation axis rendered.* They can now — Redaction
landed — and the person who looks at it is also the person who should decide what carries the data
voice at body size.

**Interim state, in force until this is decided:** Option A. `--f-data` resolves through
`ui-monospace`. It is recorded here rather than left to be inferred from a stack.

## Consequences

- The smoke suite's `KNOWN_MISSING` list holds exactly one entry. **When this ADR is decided that
  list goes to empty**, and a missing font becomes an unconditional test failure.
- `font-metrics.py` measures ten faces and names the eleventh as absent rather than skipping it
  quietly.
- No CLS claim is affected: the face that is missing never loads, so it never swaps.

## What would make this decision wrong to defer

If a surface starts *depending* on the data voice being Sligoil at body size — a spec sheet, an
evidence pane, the Groundable Fraction Report — then Option A stops being a neutral interim and
becomes a design that shipped by default. That is the same failure mode as Q1 (ADR-005), which was
decided in code and never ratified. Naming it here is the guard.
