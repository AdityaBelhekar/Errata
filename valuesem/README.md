# errata-valuesem

**Deterministic value semantics for industrial product data.** Compound-value grammars, material
and vocabulary equivalence, unit frames. **No model in the hot path.**

```bash
pip install errata-valuesem
```

Ships standalone under Apache-2.0. It needs nothing else from the Errata project (FR-4.6).

---

## The problem it solves

Two product records disagree:

| catalog | datasheet |
|---|---|
| `316 SS` | `1.4401` |
| `0.5 in` | `12.7 mm` |
| `Each` | `Box of 10` |

Two of those are the same value written differently. One is a packaging-frame error that prices
the line at a tenth of cost. A string comparison cannot tell them apart, and neither can an
embedding — it will rank all three as "similar".

`errata-valuesem` normalizes both sides into a typed structure first, then compares in that space.

## Usage

```python
from errata_valuesem import normalize, compare

compare(normalize("316 SS"), normalize("1.4401")).relation
# Relation.EQUIVALENT_VOCABULARY

compare(normalize("0.5 in"), normalize("12.7 mm")).relation
# Relation.EQUIVALENT_UNIT_FRAME

compare(normalize("Each"), normalize("Box of 10")).relation
# Relation.CONTRADICTION
```

Every line above is executed output, not illustration.

### Precision is not contradiction

```python
compare(normalize("10 mm"), normalize("10 ±0.2 mm")).relation
# Relation.A_PRECISION_LOSS
```

A tolerance dropped in transcription is a real defect, and it is a *different* defect from a wrong
number. Collapsing the two is how a reviewer queue becomes untrustworthy.

### It refuses rather than guessing

```python
r = normalize("some free-text blurb")
type(r).__name__       # 'Refusal'
r.reason.value         # 'value_outside_known_grammar'
```

**A grammar either parses or refuses.** A refusal is a routable signal — it sends the record to a
declined bucket with a machine-readable reason. A silent best guess is not routable, and is
indistinguishable at review time from a correct answer.

### Structure, not strings

```python
n = normalize("M8x1.25")
n.payload.system            # 'metric'
n.payload.nominal_mm        # Decimal('8')
n.payload.pitch_mm          # Decimal('1.25')
n.payload.series            # 'coarse'
n.payload.pitch_inferred    # False
n.grammar_version           # 'valuesem/1.1.0 [thread/1.1.0 ...] :: thread/1.1.0'
```

`pitch_inferred` records whether the pitch was stated or supplied from the coarse-pitch table, so
a downstream consumer can tell an asserted value from a derived one. Every normalized value carries
its `grammar_version` (FR-4.5), which makes a grammar change detectable and re-runnable rather than
a silent shift in behaviour.

## What it covers

| Kind | Examples |
|---|---|
| **Threads** | `M8 × 1.25`, `3/8-16 UNC`, `1/2 NPT`, `G1/2`, ISO 965 tolerance classes, left-hand |
| **Dimensions** | `10 ±0.2 mm`, ranges, tolerances, metric/imperial conversion |
| **Materials** | `316 SS` ≡ `A4` ≡ `1.4401`; coatings, property classes, base grades as orthogonal facets |
| **Ingress** | `IP67`, `IP6X`, `IPX7`, the `X` rule (IEC 60529 clause 4.1) |
| **Packaging** | `Each`, `Box of 10`, `Carton of 200`, package hierarchies, UN/CEFACT Rec 21 codes |
| **Terms** | MCB / RCCB / RCBO / MCCB, trip curves, pole counts |

## The determinism guarantee

**No network call and no model invocation, in any code path.** This is enforced by
`tests/test_determinism_boundary.py`, not by convention or code review.

The reason is not purity. A model that converts inches to millimetres incorrectly is wrong
*plausibly*, and plausible-wrong is unfalsifiable at review time — it looks exactly like
plausible-right. Everything in this package has a knowable right answer, so nothing here is
allowed to guess at one.

The pipeline is: **regex → grammar → ontology lookup → unit conversion** (FR-4.1). `Decimal` in,
`Decimal` out, so `0.5 in` lands on exactly `12.7 mm` and not on `12.700000000000001`.

## Measured quality

This package is the component graded by the Errata project's first kill test: 624 hand-labelled
equivalence pairs across six families, each citing the standard that makes its label true.

| Metric | Result |
|---|---|
| False positives (reviewer-experienced) | **1.30%** [0.44%, 3.76%] (3/230) |
| Coverage (not declined) | 79.49% (496/624) |
| Exact-label agreement | 87.50% (546/624) |

**Read the false-positive rate next to the coverage, always** — a comparator can flatter its FP
rate by refusing to commit.

**Caveat, stated because it matters:** all 624 cases were labelled by the same author who wrote the
comparator. Independent dual-labelling is required before these numbers are quotable outside the
project repository, and is in progress. Treat them as directional.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.

Value-list and unit references derive from the ETIM Classification Model, published by ETIM
International under ODC-By 1.0. Package-type codes are UN/CEFACT Recommendation 21. No ECLASS
content is included — ECLASS requires a licence, and none of its content appears here.
