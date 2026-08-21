# FE-2.5 · THE CONTRACT — gate report

**Phase deliverable:** the wire format between the audit pipeline and the frontend — the
coordinate system, the Evidence Bundle, and a console that renders one.
**Gate:** *a round-trip — `errata-audit` → bundle → the box lands on the right words, **measured in
pixels**, not eyeballed.*
**State: 🟢 GATE MET.** Two defects found on the way, one of them latent in shipped code. Three
items open, named in §6.

---

## 1. The gate, discharged

```
python -m errata_bundle probe
```

Registers every projected evidence box against the ink actually rendered, and reports the
displacement that best covers it. **(0, 0) is the correct answer.**

| Corpus | Pages | Modal offset | Verdict |
|---|---:|---|---|
| Synthetic fixtures — upright, `/Rotate 90`, `/Rotate 270`, inset cropbox | 4 | `(0, 0)` on all four, agreement 83–100% | **CLEAN** |
| `abb-s200-2CDC002142D0207.pdf` (born-digital) | 2 | `(0, 0)`, agreement 80% / 82% | **CLEAN** |
| `abb-s200muc-1SXP403008B0202.pdf` p1 (born-digital) | 1 | `(0, 0)`, agreement 79% | **CLEAN** |
| `abb-s200muc-1SXP403008B0202.pdf` p2 (born-digital) | 1 | `(0, 0)`, agreement **54%** | **fails the agreement threshold** — §6 O-8 |
| `extractbench-2607.29677.pdf` (born-digital) | 2 | `(0, 0)`, agreement 67% / 64% | **CLEAN** |
| `H28-1957`, `FedStd-H28-1969` — 100% image area, OCR text layer | 4 | scattered | **FAIL — finding G-2** |
| `ISO-261-1998-preview.pdf` — 38 words, sparse | 2 | `(0, -10)`, `(0, -5)` | **FAIL — low sample, §6 O-9** |

**The end-to-end round trip**, measured in the browser on a real audit of `S201M-B16UC`:

| Check | Result |
|---|---|
| The value mark covers | the word **`16`** — the derived value |
| The header mark covers | **`Rated`, `current`, `In`, `A`** — the column header, FR-7.3 |
| DOM text span vs stored fraction | p50 **0.23 px**, p95 **0.58 px** |
| Word width after fitting | p50 **0 px**, p95 **0 px** |
| Element under the value mark | `SPAN:16` — real, selectable DOM (L-6) |
| Bundle verification, in-browser | **4/4 files**, recomputed with WebCrypto |

The audit behind it is real: 8 records, 2 findings, 30 resolved, 8 declined, coverage 0.80. The
catalog claims `61 A`; page 8, column *Rated current I n A*, row `S201M-B16UC` says `16 A`. Nothing
in the console was invented.

---

## 2. G-1 · page rotation put every evidence box in the wrong place

**Severity: latent defect in shipped code. Cannot fire on the current corpus. Certain to fire in
production.**

`errata_audit.console.PageImage.place` computes `x * zoom`. Every PDF in `var/` shares one geometry
signature — `rect = (0, 0, 595.3, 841.9)`, `mediabox == cropbox`, `rotation = 0` — so on that
corpus it is correct, and no test in the repository can distinguish *correct by construction* from
*correct by coincidence*.

So the missing counterexamples were manufactured, and measured:

```
page.get_text("words")  ->  UNROTATED user space
page.rect + the pixmap  ->  ROTATED space
```

On a `/Rotate 90` page the union of all word boxes projects naively to `(144, 216, 803, 1047)`
while the ink is at `(640, 144, 1458, 802)`. **Not a drift of a few pixels — a different part of
the page.** Applying `page.rotation_matrix` first gives `(637, 144, 1468, 803)`, which is the ink.

**Why this matters more than it looks.** Rotated pages are how datasheets carry fold-out tables and
landscape dimension drawings — and **FR-9.6 names fold-outs as part of the frozen hard-tail
split.** The first hard-tail document with `/Rotate 90` would have put every evidence box in the
wrong place, which is the failure the PRD's own risk register calls *"product self-discredits on
screen."*

**Fixed** by carrying the complete affine the renderer used — `page.rotation_matrix * Matrix(z, z)`
— in the projection, rather than recomposing it from `zoom` at each call site. Pinned by
`test_rotation_is_actually_applied`, which asserts that **the naive transform is wrong** as well as
that ours is right, so the shortcut cannot be reintroduced silently on a corpus that would not
notice.

**Not fixed in `errata_audit.console`.** That module is R1's shipped console and changing it is a
change to a measured surface. Raised here; the fix is to delegate to
`errata_bundle.geometry.project_page`, and it belongs in a PR of its own.

Two other candidate faults were measured and found **not** to be faults:

- **Cropbox offset.** PyMuPDF normalises `page.rect` to the origin and reports words in the same
  space, so the offset never reaches us. This is undocumented behaviour we now depend on, so
  `test_cropbox_offset_is_normalised_by_pymupdf` pins it.
- **Sub-pixel zoom rounding.** Not a problem, provided the divisor is the pixmap's own width rather
  than `rect.x1 * zoom`. It is, here and in `place`.

---

## 3. G-2 · a scan with an OCR layer is never declined

`TextLayer.is_born_digital` is deliberately the weakest possible test — *any* extracted word — and
`layout.py` argues for that well: a sparse but readable page should decline with
`no_span_available`, not with `LAYOUT_UNREADABLE`.

But it also means a **scan** with an OCR layer passes:

| Document | Image area | Words reported | `is_born_digital` |
|---|---:|---:|---|
| `H28-1957-Part-I.pdf` | **100.6%** | **161,731** | ✅ true |
| `FedStd-H28-1969.pdf` | **100.0%** | 101 on p1 | ✅ true |
| `abb-s200-2CDC002142D0207.pdf` | 13.9% | 4,210 | ✅ true |

So the pipeline will happily derive values from an OCR layer, ground them to spans, and hand the
console boxes that **cannot** land on the ink — because the OCR boxes are an approximation of ink
the renderer draws from an image. The registration probe detects this. Nothing else in the
repository does.

`layout.py`'s own scope statement says *"born-digital PDFs… a document that needs [OCR] is declined
with `LAYOUT_UNREADABLE` rather than guessed at."* **That intent is correct and the test does not
implement it.**

**Recommended fix**, and it is not a threshold on word count: compute the page's image-area
fraction at extraction time and treat a page that is ≥ 95% image *with* a text layer as an OCR
layer — a distinct `DeclinedReason`, not the same one as a genuine scan. That is a change to
`errata_audit.layout`, it changes what R1 declines, and it therefore changes measured coverage.
**It needs its own decision record, not a quiet patch**, which is why this report raises it rather
than fixing it.

---

## 4. The float that broke cross-language verification

The first bundle format stored `bundle_digest` over a *canonical JSON* re-serialisation of the
manifest, and the console recomputed it in JavaScript. It failed on the first real bundle:

```
Python  json.dumps(2.0)    ->  "2.0"
JS      JSON.stringify(2)  ->  "2"
```

Every projection carries floats — `zoom`, the affine, the page rect — so the two languages produced
different bytes for the same object and every digest mismatched. RFC 8785 (JSON Canonicalization
Scheme) exists exactly for this and implementing it would have worked.

It would also have made the correctness of stored evidence depend on two independent
implementations of a number-formatting specification agreeing forever, in every language that ever
reads a bundle.

**Resolved by removing the requirement instead of meeting it.** The manifest's digest now lives in
a sibling `bundle.sha256`, and verification hashes the bytes on disk. Confirmed interoperable with
tools that know nothing about the format:

```
$ sha256sum manifest.json | cut -d' ' -f1
e0a905a2a5d8b1c6ee62b2edb79a246e0d2b32d29ac314abbe5d96baf9c3de5e
$ cat bundle.sha256
e0a905a2a5d8b1c6ee62b2edb79a246e0d2b32d29ac314abbe5d96baf9c3de5e
```

Canonical JSON is still used to *write* files, so output stays deterministic — but nothing
load-bearing depends on reproducing it.

---

## 5. Three instrument artefacts, recorded because they each looked like a bug

The probe reported a confident wrong answer three times before it was trustworthy. All three
produced the identical figure — `9.0px`, which is the search margin plus one, the signature of
*"ink fills the window"* rather than of any displacement:

1. A flat search margin caught the **next word along the line**.
2. Clipping along the line only caught the **line above and below**.
3. Clipping against a *sampled* word list clipped nothing, because the real neighbours had been
   sampled away.

And after all three were fixed, real documents still showed ~8.6px on 39% of words, for a reason no
clipping addresses: **a datasheet is full of ink that is not a glyph** — table rules, cell borders,
logos — and a bounding-box method attributes it to the nearest word. The synthetic fixtures were
clean throughout, because they are text on white, which is exactly how a bad instrument passes its
own tests.

The metric was replaced with **registration**: of all small displacements of this box, which covers
the most ink? Table rules raise the noise floor without moving the peak.

This is recorded at length because the sequence is the point. **An instrument that has never been
wrong has not been shown to work**, and a coordinate gate that reports 9px of drift on a
pixel-perfect page would have sent someone hunting a transform bug that did not exist.

---

## 6. Open items

### O-7 · `errata_audit.console` still carries the G-1 transform

The shipped console's `PageImage.place` is unfixed. It is a measured surface and the fix — delegate
to `project_page` — belongs in its own PR with its own review.

### O-8 · One born-digital page fails the agreement threshold

`abb-s200muc-1SXP403008B0202.pdf` p2: **modal offset `(0, 0)`** — no systematic displacement — but
only 54% of measurable words agree with it, against a threshold of 60%. It is a dense
ordering-data table of short numeric tokens, which is the hardest case for registration: a
two-character word has few distinct ink pixels and its peak is shallow.

**This is not resolved and the threshold was not lowered to make it pass.** Two candidate answers,
and the honest position is that neither has been tested: weight agreement by ink mass so that short
tokens count less, or accept that per-word registration is noisy on dense numeric tables and gate
on the mode alone. Deciding by looking at which one makes this page pass would be fitting the
instrument to the answer.

### O-9 · `ISO-261-1998-preview.pdf` registers at the search boundary

Modal offsets `(0, -10)` and `(0, -5)`, with only 10 measurable words on p1. `(0, -10)` is the edge
of the search window, which means the true peak may be outside it. A 38-word "preview" document is
a thin sample and it is not a datasheet. **Unexplained**, and flagged rather than dismissed: it
should be re-probed with a wider search before anyone concludes it is fine.

---

## 7. What FE-2.5 hands to FE-7

- A coordinate system that is correct by construction, with the counterexamples the corpus lacks.
- A gate that runs in one command and has been shown to fail when it should.
- A wire format verifiable by `sha256sum`, by WebCrypto, and by anything that can read a file.
- A working three-pane console rendering real audits — §8 of `FE-7a` below.
- Two product defects found by building the frontend, which is the argument for building it.

---

## 8. What the console actually implements

`web/console/` — built on DATUM, no framework, served by any static file server.

| Requirement | State |
|---|---|
| **FR-7.1** three-pane: queue · evidence · claim | ✅ |
| **FR-7.2** word-level box at the stored span's projection | ✅ measured, §1 |
| **FR-7.3** headers shown with the value | ✅ — and it resolves contradiction C-1, see below |
| **FR-7.4** counter-evidence, never empty, never absent | ✅ |
| **FR-7.5** queue rows as sentences, no confidence percentage | ✅ |
| **FR-7.6** Accept / Keep catalog / Escalate | ⚠️ **rendered, not persisted** — needs the ledger endpoint and a signed actor (FR-8.9) |
| **FR-7.8** evidence reconstructible, not regenerated | ✅ structurally — the console has no extractor |
| **FR-8.4** four blast-radius factors, independently inspectable | ✅ |
| **FR-9.3** reviewer-seconds, timed, pauses on blur | ✅ measured, not persisted |
| **FR-9.4** evidence-acceptance asked separately | ✅ measured, not persisted |
| **L-2** paper in both themes | ✅ verified in both |
| **L-6** spans selectable at device resolution | ✅ verified — `SPAN:16` under the mark |

**The adjudication buttons deliberately do not fake success.** They print the payload and show a
toast saying it was not recorded. A console that appears to record a decision it did not record is
worse than one that plainly cannot.

### C-1, resolved — the three-colour problem

FR-7.3 wants the value's cell **plus its row and column headers in a second colour**; FR-7.4 adds
counter-evidence. Four adjacent marks. L-1 permits **one** chromatic event.

The implemented answer stops encoding the distinction in hue:

- **The value** — a signal plane with the 2px reveal. The only chroma on the page.
- **Its headers** — hairline **brackets with a leader rule** back to the value: the notation an
  engineering drawing uses to dimension a feature. Achromatic, and it survives greyscale printing,
  which a second hue does not.
- **Counter-evidence** — a **dotted** reveal. Anastylosis reversed: the fabric arguing back.

Both laws intact. **This is a proposal with an implementation, not a settled answer** — it needs
judging against FR-7.3's own criterion by a domain reviewer, not a designer.

### One more type-substitution note

The console renders in fallback faces, like every other DATUM surface, because Redaction, Apfel
Grotezk and Sligoil are still not in the repository (FE-1 O-1). The `DiffPair` at the top of the
claim pane — `61 A` struck through above `16 A` — is the component whose entire argument is the
degradation axis, and it is currently making that argument with a strike-through alone.
