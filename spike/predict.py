"""The audit half: an independent re-derivation from the flat text layer.

**This module is table-blind by construction.** It receives a `TextLayer` -- a linear sequence of
words with boxes -- and nothing else. It cannot see cells, columns, row boundaries or headers. It
finds the SKU's type designation in the text and looks for a value-shaped token near it.

That is not a simplification for convenience; it is what makes the measurement worth taking. If
the predictor read the same table structure the gold builder reads, the two would agree by
construction, grounding F1 would be ~100%, and the number would say nothing about anything. A
table-blind extractor makes the mistakes real extraction systems make -- latching onto an adjacent
column, picking up the wrong row's value, tripping over a merged cell -- which is precisely what
ExtractBench's word-level grounding metric was designed to expose.

**FR-3.4 is enforced structurally, not by discipline.** The PRD says this is the requirement most
likely to be quietly broken during optimisation, because passing the catalog value in as a hint
measurably improves grounding and makes every subsequent agreement meaningless. So:

    def predict(layer, sku, attribute) -> Prediction | None

There is no parameter through which a catalog value or a gold value could reach this code. Not a
defaulted one, not an optional one. A test asserts the signature.
"""

from __future__ import annotations

from dataclasses import dataclass

from spike.attributes import Attribute
from spike.layout import TextLayer, Word

PREDICT_VERSION = "spike-predict/1.0.0"

#: How many words either side of the anchor to search. Wide enough to cross a table row in reading
#: order, narrow enough that it does not wander into the next SKU. Chosen from the document's own
#: row width (7 columns), not tuned against the score -- tuning a window until the grounding number
#: improves is fitting the extractor to the answer key.
WINDOW = 8


@dataclass(frozen=True, slots=True)
class Prediction:
    value: str
    page: int
    box: tuple[float, float, float, float]
    confidence: float
    distance: int
    """Words between the anchor and the value. Kept for diagnosis, and it is the honest reason a
    prediction is uncertain rather than a number invented to look like one."""


def _anchors(layer: TextLayer, sku: str) -> list[int]:
    """Indices of words equal to the SKU's type designation.

    Knowing WHICH product is being audited is not a leak -- it comes from the catalog record's
    MPN, and an auditor who did not know which row to look at would be solving a different
    problem. Knowing what the value IS would be a leak, and nothing here supplies one.
    """
    return [i for i, w in enumerate(layer.words) if w.text == sku]


def predict(layer: TextLayer, sku: str, attribute: Attribute) -> Prediction | None:
    """Re-derive one attribute for one SKU, or abstain.

    Returns ``None`` for an abstention -- FR-3.3's distinction between "no value" and "the empty
    value" matters here, and the corpus format carries it as ``predicted_value: None``.

    The search is nearest-first outward from the anchor, taking the first token whose shape
    matches the attribute. Nearest-first is the only defensible ordering without table structure:
    with no columns to reason about, proximity in reading order is all the evidence there is.
    """
    matches: list[tuple[int, int, Word]] = []

    for anchor in _anchors(layer, sku):
        lo = max(0, anchor - WINDOW)
        hi = min(len(layer.words), anchor + WINDOW + 1)
        for index in range(lo, hi):
            if index == anchor:
                continue
            word = layer.words[index]
            if attribute.pattern.match(word.text):
                matches.append((abs(index - anchor), index, word))

    if not matches:
        return None

    distance, _, word = min(matches, key=lambda m: (m[0], m[1]))

    return Prediction(
        value=word.text,
        page=word.page,
        box=word.bbox,
        confidence=_confidence(attribute, distance, len(matches)),
        distance=distance,
    )


def _confidence(attribute: Attribute, distance: int, candidates: int) -> float:
    """A calibrated-in-spirit confidence, from things the predictor can actually observe.

    Three signals, all available without knowing the answer:

    * **pattern specificity** -- ``2CDS271061R0065`` can only be an order code; ``6`` could be
      four different attributes.
    * **distance** from the anchor -- a token further away in reading order is more likely to
      belong to a different row.
    * **competition** -- when several tokens in the window match the pattern, the extractor is
      choosing, and a choice is less certain than a find.

    Deliberately NOT fitted to the outcome. A confidence tuned until the risk-coverage curve
    looked good would be reporting how well it was tuned, and the curve is the whole instrument
    for FR-6.3.
    """
    proximity = 1.0 / (1.0 + 0.25 * distance)
    contention = 1.0 / candidates**0.5
    raw = attribute.specificity * proximity * contention
    return round(min(1.0, max(0.0, raw)), 4)
