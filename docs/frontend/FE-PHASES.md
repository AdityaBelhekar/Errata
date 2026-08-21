# FE-PHASES — the frontend execution track

**Written:** 21 August 2026.
**Governs:** everything under `web/datum/`.
**Authority:** `docs/FRONTEND-BLUEPRINT.md` §18. This file is the ledger, not the plan.

---

## 0. The naming decision — D-FE-1

The repository already uses the word *phase* for something else. `PHASES.md`
tracks **P0–P7**, the research and product gates that map onto the PRD's
releases `R0`–`R4`. The blueprint's §18 also numbers its stages 0–9.

Two tracks called "phase 3" is a defect waiting for a review meeting to find it.

> **Decision D-FE-1.** The frontend stages are renumbered **FE-0 … FE-9**
> everywhere: in this directory, in `web/datum/`, in commit messages and in
> review. `PHASES.md`'s P0–P7 keep their names and are never called FE-anything.
> Where a document needs both, it says which track it means in the same sentence.

The two tracks are otherwise independent. FE-2 does not wait on P5; P6 does not
wait on FE-4. The only real coupling is content: **FE-8 cannot publish a figure
the research track has not measured**, which is a constraint on FE-8, not on the
research.

---

## 1. The ladder

A phase does not start until the previous gate passes. A gate passes when its
deliverable exists and someone has looked at it — not when it is asserted.

| | Phase | Deliverable | Gate | State |
|---|---|---|---|---|
| **FE-0** | Concept | The blueprint | Signed off by brand + product | 🟡 **prepared, unsigned** — see [FE-0-CONCEPT.md](FE-0-CONCEPT.md) |
| **FE-1** | Schematic | `tokens.css`, `type.css`, both themes live, one Room I comp | *Judge the direction before a shader exists* | 🟢 **met**, 3 items open — see [FE-1-SCHEMATIC.md](FE-1-SCHEMATIC.md) |
| **FE-2** | Design development | Datum grid, 21 components, all states, both themes | Nothing enters DD without a token | 🟢 **met**, 3 items open, 1 defect fixed — see [FE-2-DESIGN-DEVELOPMENT.md](FE-2-DESIGN-DEVELOPMENT.md) |
| **FE-2.5** | **The contract** | `errata-bundle`: the coordinate system, the Evidence Bundle, the projection gate | A round-trip: `errata-audit` → bundle → box lands on the right words, **measured in px** | 🟢 **met** — value mark covers the word `16`, span offsets p95 **0.58 px**. Two product defects found. See [FE-2.5-CONTRACT.md](FE-2.5-CONTRACT.md) |
| **FE-3** | Art | 30 treated plates + provenance YAML + illustration kit | No untreated asset (§7.5) | ⬜ not started |
| **FE-4** | Motion prototype | Lenis, the damped six-waypoint camera path, frame-rate-independent damping | Camera approved *blind* | 🟢 **built** — not judged in grey boxes, see D-FE-10 |
| **FE-5** | Shader R&D | Planar-reflection RT, the analytic fall, the light-table inversion | Perf budget met *before* integration | 🟡 **materials built, budget NOT measured** — §11.9 remains unrecorded (O-14) |
| **FE-6** | Landing build | `web/app/` → `web/landing/`: **Rooms I–V**, React 19 + R3F + three. `web/site/` keeps the no-canvas argument page | Works with `?nogl=1` | 🟢 **met** — 0 canvases and **0 engine bytes** with `?nogl=1`; 5 defects found. See [FE-6-PROCESSION.md](FE-6-PROCESSION.md) |
| **FE-7** | Product build | `web/console/` + `errata_bundle serve`: three panes, adjudication wired to the real ledger, keyboard-first | Keyboard-only run-through; a real FR-9.3 number | 🟢 **met** — decisions persist with `supersedes`; 3 defects found. See [FE-7-CONSOLE.md](FE-7-CONSOLE.md) |
| **FE-8** | Content | Docs, benchmark, errata log, manifesto | Every figure links to its reproduction command | ⬜ not started |
| **FE-9** | Snagging | Optical corrections, both themes | *The last 5% is the whole difference* | ⬜ not started |

🟡 = the deliverable exists and the gate needs a person.
🟢 = the gate's own criterion is met and the report names what is still open.

---

## 2. Ground rules, inherited

The frontend track runs under the same rules as the rest of the repository
(`HANDOFF.md` §8). Two of them bind particularly hard here, because a design
system is unusually good at producing confident-looking numbers:

> **Ground rule 1 — never invent a number or a citation.** Cite a source
> actually opened, or write `[UNVERIFIED — needs checking]`.

Applied: every contrast ratio in `FE-1-SCHEMATIC.md` was computed from the token
file that ships, by a tool in this repository, and it prints its disagreements
with the blueprint rather than adopting the blueprint's figures. No CLS number
is quoted, because the fonts that would produce one are not here yet.

> **L-4 — never render a precision the source does not contain.**

Applied: `46.4`, not `46.43` — including in comps and in placeholder data.

---

## 3. What is built, and how to look at it

```bash
python -m errata_bundle serve
```

One command: it serves the site, the console and the design system, and it is the only thing that
can record a decision. `/` is the site; `/console` and `/datum` redirect. Loopback by default —
binding elsewhere prints a warning, because this console shows a customer's catalog beside a
manufacturer's copyrighted document and has no authentication.

Rebuild the procession after changing `web/app/`:

```bash
cd web/app && npm install && npm run build
```

Build bundles first:

```bash
python -m errata_bundle build --catalog var/scale/catalog.csv --datasheet var/spike/datasheets/abb-s200-2CDC002142D0207.pdf
```

| Page | Phase | What it is for |
|---|---|---|
| `index.html` | — | Entry point and this ledger, in the system's own type |
| `room-i.html` | FE-1 | The full-fidelity Room I comp. **The FE-1 gate is this page.** |
| `grid.html` | FE-2 | The datum, the grid, the spacing scale, the type specimen. Press `G` for the column overlay |
| `states.html` | FE-2 | Twenty-one components × every state × both themes. **The FE-2 gate is this page.** |
| `web/landing/` | FE-4/5/6 | **The procession.** Rooms I–V, one continuous camera. Built from `web/app/` |
| `web/site/` | FE-6 | The argument page — the gap, the method, our own errata. No canvas at all |
| `web/console/` | FE-7 | The reviewer console. Decisions persist to the real ledger |

**Read before planning anything:**
[**FE-TEST-REGISTER.md**](FE-TEST-REGISTER.md) — every open item, defect, unanswered question and
untested category in one place, ranked. Its headline: 1,335 tests cover the domain and **zero**
cover the frontend, and CI does not run either design gate.

**Read before planning FE-3 or later:**
[**FE-SYSTEM-REVIEW.md**](FE-SYSTEM-REVIEW.md) — fifteen P0/P1 requirements with no
design, four contradictions between the design LAWs and the PRD, six undecided
architectural questions, and the system design that resolves them. It concludes
that the blueprint was written without reading the product it is for, and shows
the mechanical evidence.

The two CI gates, which run on every change:

```bash
python web/datum/tools/contrast.py      # 20 pairs, worst-ground, both themes
python web/datum/tools/lint-tokens.py   # colour / spacing / motion / var() / a11y laws
python -m errata_bundle probe           # FE-2.5: evidence boxes vs rendered ink, in pixels
```

Both exit non-zero on violation. `lint-tokens.py --list` prints what it does
**not** check, which is as much of its job as what it does.

---

## 4. Decision log

| | Date | Decision | Cost | What would reverse it |
|---|---|---|---|---|
| **D-FE-1** | 2026-08-21 | Frontend stages renumbered FE-0…FE-9, separate from `PHASES.md` P0–P7 | A rename pass across the blueprint's §18 | Nothing — the collision is real |
| **D-FE-2** | 2026-08-21 | FE-1 and FE-2 built as framework-free HTML/CSS, not Next.js + Storybook as §17 specifies | The Next/Tailwind/Storybook scaffold is deferred to FE-6 | Nothing yet. See FE-2 §5 for the argument and the migration path |
| **D-FE-3** | 2026-08-21 | Six errata raised against the blueprint's own numbers (§5.5, §6.3, §6.7) and the built values differ from the printed ones | The blueprint needs a v1.1 | The measurements, if anyone re-derives them differently |
| **D-FE-4** | 2026-08-21 | FE-2 entered with FE-0 unsigned | A direction nobody has formally approved has 21 components built on it | A signature, or a rejection that costs two days of token work |
| **D-FE-5** | 2026-08-21 | Where the blueprint and `prd-errata.md` conflict, **the PRD wins** | The blueprint needs a v1.1 that resolves four contradictions, not just six errata | A written argument per conflict, reviewed by product |
| **D-FE-6** | 2026-08-21 | FE-2.5 inserted before FE-3, ahead of art and motion | Art and motion slip by the length of the contract work | Nothing — FE-7 is unbuildable without it, and building it found two product defects |
| **D-FE-7** | 2026-08-21 | Bundle verification hashes **bytes**, not canonical JSON (RFC 8785 declined) | A bundle's identity is the manifest's byte digest, so the manifest cannot carry it | A reader that needs structural equality rather than byte equality |
| **D-FE-9** | 2026-08-21 | **Theatre.js dropped.** The camera path is six waypoints in a typed array in `Scene.tsx` | No visual timeline editor for the camera | A maintained release of Theatre, or a path complex enough to need scrubbing |
| **D-FE-10** | 2026-08-21 | FE-4's camera was **not** approved blind in grey boxes — it was built with materials already present | The gate's whole point was to catch a camera that only works because the materials flatter it | Nothing; it is a waiver. Judging the path in grey is still possible and still worth doing |
| **D-FE-8** | 2026-08-21 | The console stays framework-free and uses platform APIs — `<dialog>`, View Transitions, container queries, WebCrypto, scroll-driven animations | No virtual list, so the queue does not yet scale past a few hundred rows | **FE-7b.** A 1.2M-row queue and the as-of time model are a real argument for a framework; that argument gets had with the problem in front of us |

**D-FE-5 was forced by defect C-2**: blueprint §13.2 specifies a queue ranked by a
confidence column, and FR-7.5 forbids exactly that. Three more conflicts of the
same kind are catalogued in [FE-SYSTEM-REVIEW.md](FE-SYSTEM-REVIEW.md) §2. The
rule that prevents the next one: **no component merges without the requirement id
it discharges.**

**D-FE-4 is a waiver of an entry criterion, not a criterion met.** It is recorded
here in the same form `PHASES.md` §10 records D-3, and for the same reason: a
waiver that is written down can be argued with, and one that is drifted into
cannot.
