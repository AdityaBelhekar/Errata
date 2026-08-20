"""The catalog under audit — constructed, with a known and stated error pattern.

**This is the one part of the corpus that is not read from a document, and it has to be, because
no real ABB catalog is available to us.** The distinction matters enough to be loud about it:

| | Real | Constructed |
|---|---|---|
| the datasheets | ✅ ABB's own, hash-registered | |
| gold values and boxes | ✅ read from their tables | |
| predicted values and boxes | ✅ produced by the blind extractor | |
| **the catalog being audited** | | ⚠️ **built here** |

So the *grounding* half of gate 2 is fully empirical, and the *disagreement-detection* half rests
on a catalog whose errors we injected. That is a normal way to measure detection -- you cannot
measure recall against errors you cannot enumerate -- but it must travel with the number, and it
is written into the corpus `notes` so it reaches anyone reading the report.

**Three kinds of catalog value are generated, and the third is the interesting one:**

1. **Correct** -- matches the datasheet. The audit should stay silent.
2. **Wrong** -- a realistic transcription defect: a transposed pair, a dropped decimal, a
   neighbouring SKU's value. The audit should raise it.
3. **Cosmetically different but equivalent** -- ``6`` written as ``6.0``. The audit must **not**
   raise it. FR-5.3 calls semantic equivalence "the single highest-consequence requirement in the
   document", and a detection measurement that contained no equivalence traps would report a
   precision that had never been tested.

Deterministic: a fixed seed, so the corpus is reproducible and a change in the numbers is a change
in the code rather than a reroll.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from spike.gold import GoldRecord

CATALOG_VERSION = "spike-catalog/1.0.0"
SEED = 20260819

#: Fraction of records given a genuine defect. Chosen to be roughly plausible for a poorly
#: maintained catalog and, more importantly, high enough that the defect count supports an
#: interval worth quoting. Stated rather than tuned.
DEFECT_RATE = 0.18

#: Fraction given a cosmetic-but-equivalent variant. These are the FR-5.3 traps.
EQUIVALENT_VARIANT_RATE = 0.12


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    sku: str
    attribute: str
    value: str
    kind: str
    """``correct`` | ``defect`` | ``equivalent_variant``."""

    note: str = ""

    @property
    def is_genuine_disagreement(self) -> bool:
        """What a competent domain reviewer would say.

        ``equivalent_variant`` is deliberately False: the catalog says the same thing in a
        different shape, and a reviewer shown that row would ask why they were shown it.
        """
        return self.kind == "defect"


def _transpose(value: str) -> str | None:
    digits = [i for i, c in enumerate(value) if c.isdigit()]
    if len(digits) < 2:
        return None
    i, j = digits[0], digits[1]
    chars = list(value)
    chars[i], chars[j] = chars[j], chars[i]
    swapped = "".join(chars)
    return swapped if swapped != value else None


def _drop_decimal(value: str) -> str | None:
    if "." not in value:
        return None
    stripped = value.replace(".", "", 1)
    return stripped if stripped != value else None


def _scale(value: str) -> str | None:
    try:
        number = float(value)
    except ValueError:
        return None
    scaled = number * 10
    text = f"{scaled:g}"
    return text if text != value else None


DEFECTS = (_transpose, _drop_decimal, _scale)


def _equivalent_variant(value: str) -> str | None:
    """Same value, different surface form. Must not be flagged."""
    try:
        number = float(value)
    except ValueError:
        return None
    if number != int(number):
        return f"{number:.3f}".rstrip("0").rstrip(".") + "0"
    return f"{int(number)}.0"


def build_catalog(gold: list[GoldRecord], *, seed: int = SEED) -> dict[str, CatalogEntry]:
    """A catalog entry per gold record, keyed by ``attribute_id``."""
    rng = random.Random(seed)
    catalog: dict[str, CatalogEntry] = {}

    for record in gold:
        roll = rng.random()
        entry: CatalogEntry | None = None

        if roll < DEFECT_RATE:
            rng.shuffle(mutators := list(DEFECTS))
            for mutate in mutators:
                broken = mutate(record.value)
                if broken is not None:
                    entry = CatalogEntry(
                        sku=record.sku,
                        attribute=record.attribute,
                        value=broken,
                        kind="defect",
                        note=f"injected {mutate.__name__.lstrip('_')} of {record.value!r}",
                    )
                    break
        elif roll < DEFECT_RATE + EQUIVALENT_VARIANT_RATE:
            variant = _equivalent_variant(record.value)
            if variant is not None:
                entry = CatalogEntry(
                    sku=record.sku,
                    attribute=record.attribute,
                    value=variant,
                    kind="equivalent_variant",
                    note=f"cosmetic variant of {record.value!r} -- must NOT be flagged (FR-5.3)",
                )

        catalog[record.attribute_id] = entry or CatalogEntry(
            sku=record.sku,
            attribute=record.attribute,
            value=record.value,
            kind="correct",
        )

    return catalog
