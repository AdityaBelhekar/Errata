# FRONTEND — ACCESSIBILITY BASELINE

**First axe run:** 21 August 2026. **Tool:** `@axe-core/playwright`, WCAG 2.0/2.1/2.2 A + AA tags.
**Scope:** every surface in `web/app/e2e/surfaces.ts`, both themes, Chromium.

§15.2 made axe-clean on every route in both themes a **required gate**. It had never been run. This
file records what the first run found, verbatim, before anything was fixed — because the delta
between the first run and the gate is the only honest measure of what was wrong, and a baseline
written after the fixes is a baseline that proves nothing.

---

## 1. What the first run found

Six distinct defects across four surfaces. All are now fixed; each is listed with what it actually
was, because "axe violation" is a category, not a finding.

| # | Rule | Impact | Where | What it really was |
|---|---|---|---|---|
| 1 | `aria-required-children` | **critical** | `#queue-list` (console) | A `role="listbox"` containing no options. The console starts empty, and the empty state appended a plain `<div>` into a listbox. |
| 2 | *(same element)* | — | `#queue-list` | The same element carried `tabindex="0"`, so it was **a focus stop containing nothing** — a keyboard user tabbed into a box that announced itself as a listbox and had no contents. |
| 3 | `aria-allowed-attr` | **critical** | `.theme-toggle > button` (states gallery) | The gallery's specimens carried `aria-checked` on bare `<button>`s. `theme.js` adds `role="radio"` at runtime, so the specimens showed a component **that the real one is not** — inaccessible *and* misleading as documentation. |
| 4 | `color-contrast` | serious | `.table-empty` (states gallery) | 4.19:1 against a 4.5 requirement. See §2 — this one is the interesting one. |
| 5 | `target-size` | serious | `.wordmark`, `.toc a`, `.nav-links a` | 11px micro type as a link target, below the WCAG 2.2 AA 24×24 minimum. |
| 6 | *(consequence of 5)* | serious | `.nav-links a` on `/web/landing/` | See §3 — the landing page's navigation had **no styling at all**. |

**Result after fixes: 0 serious or critical violations on any surface, in either theme.**

---

## 2. The contrast finding, and why two gates are not one gate too many

`contrast.py` reports **all 20 pairs meet target** and has done throughout. axe found a real failure
anyway. Both are correct, and the reason matters more than the defect.

The failing element was `.table-empty` inside `.queue`. `.queue` paints `--edge-hair` as its own
background and lets it show through the grid gap to draw the 1px rules between rows, so every child
must supply its own surface. `.queue-row` does. `.table-empty` did not — so its text rendered
directly on the translucent hairline, which the browser composited over the page to `#e1dbd3`,
giving **4.19:1**. On `--surface-1` the same text measures **5.31:1**.

**`contrast.py` could not have caught this.** It compares *token pairs*, and `#e1dbd3` is not a
token — it is two layers composited by the browser, one of them an alpha the tool drops when it
resolves a colour. The gate's own table calls `--surface-3` the "worst ground", and that assumption
was simply false: a translucent hairline over the page background is darker than `--surface-3`.

Two consequences, both recorded rather than fixed by widening the tool:

1. **The static gate's "worst ground" claim is unverified.** It is an assumption in a comment, not a
   measurement. It happens to be wrong. It has not been re-derived — doing so needs a pass over
   rendered pixels, which is what axe already does.
2. **The two gates are complementary, not redundant.** The token gate catches decisions; the
   rendered gate catches compositions. Dropping either would lose a class of defect the other
   cannot see. This case is the evidence for keeping both.

---

## 3. The finding axe reached by accident

`target-size` failed on `.nav-links a` on the landing page. The fix for the other surfaces did not
help, which is what made it worth chasing: `.site-nav` and `.nav-links` are defined **only** in
`web/site/shell.css`, and `web/app/src/app.css` imported the four DATUM stylesheets and not that one.

**The landing page's primary navigation had been rendering completely unstyled** — a row of
default-coloured inline links — for as long as that markup has existed. Nobody noticed because
looking at the page was how it was checked, and the nav sits above a scene the eye is drawn past.

That is the register's whole thesis in one defect: it was invisible to inspection and obvious to a
gate, and the gate that found it was looking for something else entirely.

---

## 4. What this file does NOT claim

**axe-clean is not accessible.** Automated rules catch a minority of WCAG failures. Still open after
this baseline:

- **No screen reader has ever been used on any surface.** Reading order, announcement order and
  whether an `aria-live` region says something a person can act on are all unverified.
- **Keyboard coverage is partial.** The suite tabs through 25 stops per surface and asserts each is
  visible. It does not test focus *return* after a dialog closes, `Esc` from nested states, or the
  roving-tabindex behaviour nine components document in comments and do not implement (H-2).
- **One browser.** Chromium. The axe run is not yet part of the Firefox and WebKit projects.
- **Zoom to 200%, Windows High Contrast, and the `role="document"` evidence layer's actual reading
  experience** are untested.
- **Contrast in dark theme composites** has not been re-derived after the finding in §2. The same
  class of defect could exist there and no measurement rules it out.

---

## 5. Rules for keeping this honest

1. **No rule is disabled to make the gate pass.** There is no `disableRules` list. If one is ever
   added, every entry needs a written reason reviewed like code — a suppression list that grows
   quietly is a suite that measures nothing.
2. **A new surface joins the gate by being added to `surfaces.ts`.** One edit, and it is smoke-,
   axe- and keyboard-tested. There is no way to add a page and forget the gate.
3. **This file is updated when the gate finds something new**, not when it goes green.
