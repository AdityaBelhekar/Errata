# errata-bundle

**The Evidence Bundle**, the coordinate system it depends on, and the gate that proves the
coordinate system works.

This is FE-2.5 — the contract between the audit pipeline and the frontend. It exists because
`docs/frontend/FE-SYSTEM-REVIEW.md` identified it as the thing blocking every later frontend phase:
the console cannot be built against a backend that has no wire format, and the highest-consequence,
lowest-glamour piece of the whole product is the transform that puts an evidence box on a word.

---

## What is here

| Module | What it is |
|---|---|
| `geometry.py` | The **only** place a PDF box becomes something a browser can draw. Carries the full affine the renderer used, not a reconstruction of it |
| `probe.py` | The gate. Registers projected boxes against rendered ink and reports the displacement **in pixels** |
| `fixtures.py` | Adversarial page geometries — rotated, cropped — manufactured because the corpus contains none |
| `bundle.py` | The bundle writer and its verifier |
| `build.py` | Drives a real `audit_sku` run into bundles. The only module that imports the pipeline |

## Run it

```bash
python -m errata_bundle probe
```

```bash
python -m errata_bundle build --catalog var/scale/catalog.csv --datasheet var/spike/datasheets/abb-s200-2CDC002142D0207.pdf
```

Then serve the repository root and open `web/console/`:

```bash
python -m http.server 8099
```

## Two defects this found

**G-1 · page rotation put every evidence box in the wrong place.** `page.get_text("words")` returns
*unrotated* user-space coordinates; `page.rect` and the rendered pixmap are in *rotated* space. On
a `/Rotate 90` page the naive `x * zoom` transform — which the shipped console uses — puts the
union of all word boxes at `(144, 216, 803, 1047)` while the ink is at `(640, 144, 1458, 802)`.
Not a drift: a different part of the page. It cannot fire on the current corpus, and FR-9.6 names
fold-outs as part of the frozen hard-tail split, so it would have fired in production.

**G-2 · a scan with an OCR layer is not declined.** `TextLayer.is_born_digital` is true for *any*
extracted word. `H28-1957-Part-I.pdf` is 100% image area with an OCR text layer and reports
**161,731 words**, so nothing declines it — but its word boxes are approximations of ink drawn from
an image, and its evidence boxes will be visibly wrong. The probe detects this and nothing else in
the repository does.

Both are written up in `docs/frontend/FE-2.5-CONTRACT.md`.

## What this package does not depend on

**Not `errata-audit`.** The bundle is a wire format; coupling it to the pipeline's in-process class
layout would make every refactor there a breaking change for stored evidence that has to stay
readable for years. `build.py` imports the pipeline lazily, inside the function, so `geometry`,
`probe` and `bundle` are importable on their own.

**Not numpy.** The probe reads pixmap bytes directly and builds its own summed-area table. A gate
is not worth a compiled dependency in a project whose README hook is that it runs from a clean
clone with no signup (FR-7.9).

## What a bundle never contains

The source PDF. FR-9.5 forbids redistributing it; a bundle carries its SHA-256 so a holder can
verify they have the same document without being given a copy.

Whether the *rendered page raster* of a copyrighted datasheet may be redistributed is a legal
question and it is **unanswered**. Until it is, bundles built from third-party documents stay
local: they are written under `var/`, which is gitignored, and nothing here uploads or packages
them.
