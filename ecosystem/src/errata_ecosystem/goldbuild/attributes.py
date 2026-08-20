"""The attributes the spike audits, and the surface patterns a value of each can take.

Shared by the gold builder and the predictor, and that sharing is deliberate and bounded: both
must be talking about the *same attribute*, or the corpus is incoherent. What they must NOT share
is any means of finding the value, which is why this module contains a column name and a regex and
nothing else. The gold side uses the column name; the predictor may not see it.

The regexes are chosen to give a realistic spread of difficulty rather than a flattering one:

* ``order_code`` and ``weight`` have distinctive shapes -- ``2CDS…`` and ``0.125`` -- and should
  ground easily.
* ``rated_current``, ``poles`` and ``packing_unit`` are all bare small integers, mutually
  ambiguous, and sitting in adjacent columns. A table-blind extractor will confuse them, which is
  exactly the failure ExtractBench's word-level grounding metric exists to expose. If every
  attribute here were distinctive the measurement would say nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Attribute:
    key: str
    column_header: str
    """The ordering-table column the GOLD builder reads. The predictor never sees this."""

    pattern: re.Pattern[str]
    """What a value of this attribute looks like as a bare token. All the predictor gets."""

    specificity: float
    """How distinctive the pattern is, in [0, 1]. Feeds the predictor's confidence.

    Set from the shape of the regex alone -- how many unrelated tokens in a datasheet could match
    it -- and NOT from how often the predictor turns out to be right, which would be fitting the
    confidence to the answer and would make the risk-coverage curve meaningless.
    """


ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="rated_current",
        column_header="Rated current I n A",
        pattern=re.compile(r"^\d{1,2}(?:\.\d)?$"),
        specificity=0.35,
    ),
    Attribute(
        key="poles",
        column_header="Number of poles",
        pattern=re.compile(r"^[1-4]$"),
        specificity=0.25,
    ),
    Attribute(
        key="order_code",
        column_header="Order code",
        pattern=re.compile(r"^2CDS\w{10,}$"),
        specificity=0.95,
    ),
    Attribute(
        key="packing_unit",
        column_header="Packing unit PCS",
        pattern=re.compile(r"^\d{1,3}$"),
        specificity=0.30,
    ),
    Attribute(
        key="weight_kg",
        column_header="Weight 1 PC kg",
        pattern=re.compile(r"^\d\.\d{3}$"),
        specificity=0.90,
    ),
)

BY_KEY = {a.key: a for a in ATTRIBUTES}

#: The column holding the SKU's type designation. The audit is told WHICH product it is auditing
#: -- that comes from the catalog record's MPN and is not a leak -- but never what the answer is.
TYPE_COLUMN = "Type"
