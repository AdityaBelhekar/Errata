# FE-4 / FE-5 / FE-6 · THE PROCESSION — gate report

**Phase deliverable (§18):** the camera path, the TSL/shader materials, and Rooms I–V wired.
**Gate:** *the page works with `?nogl=1`.*
**State: 🟢 GATE MET.** Five acts built, five defects found and fixed, four items open in §6.

---

## 0. Why this exists, stated plainly

FE-1 and FE-2 shipped Room I as CSS and deferred the entire WebGL procession to "FE-4/FE-5, which
have their own gates". That was defensible as process and wrong as a result: §11 and §12 describe
five rooms, one continuous camera and a shader-driven reflection, and what was on screen was a
static plate and a headline. The gates were being used as a reason not to build the thing the gates
were for.

This phase builds it. Same design system, same tokens, same laws — the stack the blueprint asked
for.

---

## 1. What runs

```bash
cd web/app && npm install && npm run build     # → web/landing/
python -m errata_bundle serve                  # → http://127.0.0.1:8099/web/landing/
```

**Stack, as specified in §17:** React 19 · @react-three/fiber 9 · three 0.185 · Lenis · Vite 8 ·
TypeScript. Built to `web/landing/` and served by the same Python process as the console and the
design system — one origin, one server, no second runtime.

| Room | Scroll | What it is | Where |
|---|---|---|---|
| **I · Approach** | 0–16% | Black water, one plate, and a **real planar reflection of a second scene** | `Scene.tsx` |
| **II · Compression** | 14–32% | 1,800 instanced documents, FOV 52→32, fog 0.028→0.055 | `Scene.tsx` |
| **III · Blacklight** | 30–58% | **DOM, not WebGL** — the lens over two stacked documents | `Overlay.tsx` |
| **IV · The archive** | 56–86% | 150k points, **analytic** fall in the vertex shader | `Scene.tsx` |
| **V · The queue** | 84–100% | The same buffer morphs to ranked rows; verified records recede | `Scene.tsx` |

**Room III is deliberately not in the scene file.** §11.5 makes it a LAW that the blacklight room is
DOM, because that surface is made of type and rendering type into a texture is F-04. It is real
DOM at device resolution, the canvas drops to 30%, and the paper owns the frame.

---

## 2. The gate: `?nogl=1`

| Check | Result |
|---|---|
| `data-gl="off"`, tier `off` | ✅ |
| Canvas elements in the document | **0** |
| **three.js network requests** | **0 — the engine is never downloaded** |
| Acts present and readable | 5 of 5, static, ordinary scrolling document |
| Headings in the DOM | all present |

L-7 says WebGL is enhancement and never structure. This does better than work without the canvas:
it does not *pay* for it. `Scene.tsx` is a lazy import behind the tier check, so a visitor on
`?nogl=1` — or on hardware that cannot run the procession — downloads none of it.

**Measured payload:**

| Chunk | Raw | Gzipped | |
|---|---:|---:|---|
| CSS | 40.6 KB | 8.5 KB | |
| app | 31.8 KB | 10.0 KB | |
| react | 188.2 KB | 58.7 KB | |
| **initial total** | | **77.6 KB** | what `?nogl=1` costs |
| Scene | 163.0 KB | 52.4 KB | lazy |
| three | 709.3 KB | 178.9 KB | lazy |

---

## 3. The laws, discharged in code

**F-01 · one scroll authority (§10.5).** Lenis owns the scrollbar. `lib.ts` exposes a single
`ScrollAuthority`; the scene and the overlay both subscribe to it, and nothing reads `window.scrollY`
— the token lint fails the build on it.

**F-02 · frame-rate independence (§10.6).** Every interpolation goes through
`damp(a, b, k, dt) = a + (b − a)(1 − (1 − k)^dt)`. A fixed `a += (b − a) * 0.07` is a merge blocker.

**F-03 · the camera is damped, never assigned (§10.7).** Scroll sets a target on a six-waypoint
path; the camera chases it. This is the difference between a directed shot and a scroll stutter
transmitted 1:1 into the image.

**F-04 / L-6 · type is not a texture.** One texture in the whole procession carries lettering: the
rating plate, which §11.3 specifies as a baked map. That is not a loophole — the datasheet in Room
III is a *document* and stays DOM, while the plate is a *manufactured object* whose lettering is
stamped into metal, has to reflect in water, and has to catch a raking key. DOM can do none of
those. It is baked at 4× with a two-pass engraving cut, not at screen resolution.

**L-5 · light must be motivated.** One raking key, out of frame upper-left, and one hemispheric
fill. Plus a procedural `RoomEnvironment` so the metal has something to be — see §5, D-3.

**§11.7 · the light-theme inversion.** THE LIGHT TABLE is a *different room*, not a brighter one:
the ground becomes milk glass, the key becomes a soft top-down diffuse, the fill goes from a cold
12% to a warm bounce, fog drops from 0.028 to 0.010, and the records blend **multiplicatively** so
they read as ink rather than as light. The scene reads the theme at init and on change.

**§10.4 · reduced motion is a designed alternative.** Lenis is not started, native scroll is
restored, and the canvas renders **on demand** — one frame per scroll change rather than a loop.
The procession still moves when the reader moves; it never moves by itself.

---

## 4. The number on screen is the claim

41,206 of 1.2M is **3.43%**. That is the exact proportion of points given `aBad = 1`, so the hot
points in the fall are the finding, not a density chosen because it looked right. It cost nothing
to do properly and it is the sort of thing this product cannot afford to fake.

---

## 5. Five defects, found by building it

### D-1 · The planar reflection was an approximation, and it showed nothing

Mirroring the camera position, flipping `up` and calling `lookAt` on the mirrored target is *not* a
planar reflection. Sampling that render by the fragment's own screen UV only works if the virtual
camera shares the main camera's projection, which a hand-built one does not.

Symptom, in order as it was chased: the reflection appeared 150px below where the plate met the
water; then, after the camera was reframed, it vanished entirely. Every matrix in it was
individually correct.

**Fixed** with the texture matrix three's own `Reflector` uses — reflect the position *and* the
look direction about the plane, reuse the main camera's projection unchanged, and build
`bias · projection · viewInverse` to map a water vertex to the right texel. And then **include the
model matrix**: the water plane is rotated −90° about X, so feeding the texture matrix a local
position sampled somewhere off the plane entirely.

### D-2 · The composition made the reflection physically impossible to see

With the plate at eye height and a level 46° camera, the mirrored plate lands ~29° below the view
axis and a 46° FOV reaches 23°. The scene rendered perfectly and showed nothing — the most
expensive kind of correct.

**Fixed** by putting the object low and close to the surface and tilting the camera down: the
composition every still-water photograph has used for a century, for exactly this reason.

### D-3 · A metal with no environment renders black

`metalness: 0.62` and no `envMap` gives a material with almost no diffuse term and nothing to
reflect, so the anodized plate came out as a featureless dark slab on the light table.
**Fixed** with `RoomEnvironment` — procedural, ships inside three, so it costs no network request
and no HDR file, which matters because §5.3's no-CDN law is about the critical path and an
environment map is on it. At full intensity it then flattened the scene into a grey gradient; it is
now tuned per palette.

### D-4 · The first and last acts were invisible

The cross-fade formula gave an act opacity zero at both ends of its own span. Act I begins at
scroll 0 and had no room to fade in; Act V ends at scroll 1 and had no room to fade out. **The
first thing a visitor saw was an empty room, and the last thing they saw — after scrolling to the
product panel — was another one.** Found separately, at opposite ends, which is the argument for
fixing the rule rather than the symptom.

### D-5 · Smaller ones, worth naming

- A **backtick inside a GLSL template literal** (`flip \`up\``) terminated the shader string and
  failed the build with a parse error 60 lines away.
- `manualChunks` as an object fails on Vite 8 / Rolldown; it takes the function form only.
- The browser restores scroll on reload, and Lenis then treats the restored offset as truth and
  glides to it — dropping a returning visitor into Act IV with no idea what Act I said.
- `overflow: hidden` is right for a pinned act and wrong for a flowing one: it clipped Act II's own
  heading mid-sentence in `?nogl=1`.
- Room II's corridor was plainly visible behind the plate in Act I. A room you can see before you
  reach it is a set, not a passage.

---

## 6. Open items

### O-14 · WebGLRenderer, not WebGPU + TSL

§11.1 specifies `WebGPURenderer` and TSL node materials. This ships the standard `WebGLRenderer`
with GLSL `ShaderMaterial`, and that is a deviation with a reason: TSL's own argument is that it
compiles to *both* backends, so the port is a materials-layer change rather than a rewrite, and
taking a WebGPU dependency before the perf budget in §11.9 has ever been measured would be
optimising a frame time nobody has recorded. **The perf budget is still unmeasured** — that is
FE-5's actual gate and it is not met.

### O-15 · No post-processing

§11.7 specifies bloom (0.28 dark / 0.10 light) and grain (2.6% / 1.8%). Neither is implemented. Both
are cheap to add and both cost frame time, so they belong after O-14's measurement, not before it.

### O-16 · Theatre.js is not used, and should not be

§17 lists it for camera authoring. It has had no meaningful release in a long time, and putting the
camera path of the entire landing on a stalled dependency is a risk with no upside here — the path
is six waypoints in a typed array in `Scene.tsx`, which is readable, diffable and has no
maintainer but us. Recorded as **D-FE-9** rather than left as a silent omission.

### O-17 · The typefaces are still absent

Redaction, Apfel Grotezk and Sligoil remain unfetched (FE-1 O-1), so the hero's degradation axis —
the reason `reflection` is set in a decayed cut — still carries no visual difference. Every surface
in this project now renders in fallback, and this is the fifth report to say so.

---

## 7. Gates

| Gate | Result |
|---|---|
| `?nogl=1` — the phase gate | **pass**, 0 canvases, 0 engine bytes |
| Token lint — 17 files across site, console, app and design system | **pass** |
| Contrast — 20 pairs, worst ground, both themes | **pass** |
| FE-2.5 projection probe | **pass** |
| ruff · mypy | **clean** |
| Repository suite | see the run recorded in `FE-7-CONSOLE.md` §6 |

The lint now also covers `web/app/src`. It caught the lens's glass colours and the preloader's
duration in this phase — both are now tokens (`--glass-rim`, `--glass-inner`, `--glass-shadow`,
`--d-preload`) rather than exemptions, because unlike the WebGL scene values they are ordinary DOM
and there was no reason for them to live outside `tokens.css`.
