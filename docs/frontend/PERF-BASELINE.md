# FRONTEND — PERFORMANCE BASELINE

**First measurement:** 22 August 2026. **Harness:** `web/app/e2e/perf.spec.ts`, headless Chromium.

§11.9 states its budgets as *"spec, not aspiration"*. **Not one had ever been recorded.** The test
register's §4.1 said so, which also means FE-5's actual gate — *perf budget met **before**
integration* — was not met: materials were integrated first, and the budget was never checked at
all, before or after.

These are the first numbers. They are a **regression tripwire, not a benchmark**.

---

## 1. What was measured

| Metric | Observed | Ceiling | Note |
|---|---:|---:|---|
| Initial transfer (uncompressed) | **274,791 B** | 450,000 B | ≈78 KB gzipped. Excludes `three-*` and `Scene-*`, which are dynamically imported |
| LCP | **~2,700 ms** | 4,000 ms | Single unthrottled run |
| CLS | **0.0000** | 0.1 | See §3 — this number **must not be quoted** |
| First observed frame | **~13 ms** | 3,000 ms | See §2 — this is *not* shader compile |
| Steady frame, median | **~58 ms** | 120 ms | See §4 |
| Steady frame, worst | **~93 ms** | — | Reported, not gated |
| `?nogl=1` engine bytes | **0** | 0 | L-7, asserted exactly |

**Ceilings are set from the measurement plus headroom, not from the aspiration.** A budget nobody
can meet gets switched off within a week — the same reasoning `scripts/ci.sh` already applies to
mypy. Every ceiling is paired with an assertion that the page still renders, because the cheapest
way to pass a bundle budget is to lazy-load something the first paint needs.

---

## 2. Shader compile is still UNMEASURED, and the first attempt mislabelled it

§11.9 names shader compile time specifically. It is **not** in the table above, and the reason is
worth recording because the wrong version of it nearly shipped as a measurement.

The first version of this test measured a 554 ms "steady frame time". That number was really the
compile: the observer attached at page load and its first sample swallowed program link and buffer
upload. Splitting the first sample out then produced **1.0 ms** labelled
`shader_compile_first_frame_ms` — also wrong, in the opposite direction. By the time the observer
attaches (after `waitForSelector('canvas')`), the scene has already drawn and paid the cost.

Both numbers are arithmetically true and neither describes its label. **Publishing 1.0 ms as a
measured shader-compile time is exactly the failure FR-9.1 exists to prevent.** The metric was
renamed to `first_observed_frame_ms`, which is what it actually is.

**To close this properly** needs `performance.mark()` around the program link inside `Scene.tsx` —
app-side instrumentation. A test outside the page cannot see a compile that happens before it
attaches. Until then §11.9's shader-compile budget is open.

---

## 3. CLS is 0.0000 and that number may not be quoted

The blueprint's 0.00 CLS is a **target**. The measurement above agrees with it and still does not
establish it, for a reason that has nothing to do with the measurement:

The three specified type families are absent (`web/datum/fonts/README.md`). Every page currently
renders in a fallback face, and §5.3's `size-adjust` / `ascent-override` / `descent-override` — the
three properties that make the eventual font swap cost nothing — are marked `<MEASURE>` and are
**absent, not approximated**. A page that never swaps its fonts trivially has no font-swap shift.

So 0.0000 is the CLS of a page nobody will ship. The assertion in the suite uses **0.1**, the Core
Web Vitals "good" threshold, as a regression floor — not as a claim of having met §11.9.

---

## 4. Steady frame time of ~58 ms is not a frame budget being met

60 fps is 16.7 ms. The observed median is roughly three and a half times that.

This is measured under the full suite's conditions: eight parallel workers, four browser projects,
sharing one GPU on a developer machine. It is not a claim about what a visitor experiences, and the
ceiling (120 ms) is set to catch a scene that has stopped rendering or fallen back to software —
not to certify smoothness.

**A real frame-rate measurement has not been taken** and needs a quiet machine, a single worker,
and a scripted scroll through all five acts. That is a different exercise from this file.

---

## 5. Never measured, still

Named in the register §4.1 and untouched by this baseline:

- **150k-point fill rate on integrated graphics.** Needs the hardware.
- **Memory profile** — three's render target, the PMREM environment, and the 150k-point buffers.
- **INP.** Requires interaction; the procession is scroll-driven and INP needs a considered
  definition of what the interaction *is* before measuring one.
- **Console responsiveness at 1.2M rows** (FE-7 O-12). Blocked on a queue that does not exist.
- **Everything on Firefox, WebKit, and a real device.** Budgets are Chromium-only by design — a
  budget that means four different things is not a budget — but that means three engines are
  unmeasured, not that they are fine.

---

## 6. Honest summary

FE-5's gate said the perf budget must be met *before* integration. It was not, and this file does
not retroactively satisfy it — integration happened first and no amount of measuring afterwards
changes the order.

What this file does change is the register's §4.1 line from *"nothing measured"* to a set of
numbers with stated methods and stated limits, running in CI where a regression trips them. Two of
the most important figures — shader compile and a real frame rate — remain open, and are open by
name rather than by omission.
