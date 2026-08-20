"""The systems the benchmark scores, behind one signature that cannot be handed the answer.

R0 gate 2 reports **46.34% word-level grounding F1** against ExtractBench's 46.4%. That number was
produced by ``spike/predict.py`` -- throwaway scaffolding built to break the gate-2 circularity
(decision D-2, ``PHASES.md`` §10). It is an honest number about an honest extractor, and it is
**not a number about the extractor this repository ships**. ``errata_audit.derive`` had never been
scored on the grounding metric at all. This module is what makes scoring it possible, and it does
so without letting either system near the answer key.

**Why the extractors live in ``ecosystem/`` and not next to the code they wrap.**
``audit/tests/test_boundaries.py`` asserts that ``errata_audit`` never imports ``errata_bench`` --
"a product that imported its own scorer would be a product that could be tuned against it" -- and
``bench`` does not depend on ``audit``. ``ecosystem`` depends on both, which makes it the only
place the two can meet. That is not a workaround; it is the boundary working. The benchmark
reaches into the product, never the other way round.

**The two systems, and why both are needed.**

============================  ===================================  =========================
\\                             ``tableblind``                       ``r1``
============================  ===================================  =========================
what it is                    the gate-2 baseline, frozen          ``errata_audit.derive``
sees                          a flat char-indexed word sequence    words **and** table cells
finds a value by              pattern match near the MPN           the cell under the mapped
                              in reading order                     column, falling back to the
                                                                   window when tables fail
mechanism vs. gold            **independent**                      **partly shared**
============================  ===================================  =========================

That last row is the whole reason this module has a stratification API, and it is the finding a
naive "just run derive on the corpus" would have buried.

**The circularity that a single headline number would hide.** Gold is read from *table structure*:
the cell under a named column, in the row whose identity cell is the type designation. R1's
``derive`` prefers exactly the same path. Score them against each other and the grounding F1 goes
to ~100% -- not because the extractor is good, but because the two are the same act performed
twice. ``spike/README.md`` states this ("If gold and prediction shared a mechanism they would agree
by construction and the grounding number would be worthless") and it applies with full force here.

So every prediction records **how it was found**, and :mod:`errata_ecosystem.corpusbuild` reports
the score stratified by it:

* ``text_window`` -- mechanism-independent of gold. **This is the number comparable to
  ExtractBench**, and it is comparable for the same reason the spike's was.
* ``table_cell`` -- gold and prediction both read a table cell, from two independently written
  table engines (``spike/tables.py`` and ``errata_audit.tables``). Agreement is *partly*
  structural. Reported separately, never folded into a headline.

A reader who wants one number from this module will not get one, and that is the point.

**FR-3.4 is enforced structurally here too.** :meth:`Extractor.predict` takes
``(layer, tables, mpn, attribute)``. There is no parameter through which a catalog value or a gold
value could arrive -- not a defaulted one, not an optional one, not a dictionary of "context".
:func:`assert_blind` inspects the signature of a live object rather than reading source, so a
keyword added later fails the build. The same guard that protects ``derive`` protects anything
that ever gets benchmarked beside it.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from errata_audit import (
    AuditAttribute,
    EtimClass,
    Table,
    TextLayer,
    Word,
    derive,
)
from errata_audit.derive import DERIVE_VERSION

__all__ = [
    "BASELINE_PATTERNS",
    "BASELINE_VERSION",
    "BASELINE_WINDOW",
    "EXTRACTORS",
    "FORBIDDEN_PARAMETERS",
    "Extractor",
    "Prediction",
    "R1Extractor",
    "TableBlindExtractor",
    "assert_blind",
    "get_extractor",
]

#: Frozen with the gate-2 measurement. A baseline whose parameters move is not a baseline, it is a
#: second system wearing the first one's score.
BASELINE_VERSION = "errata-bench.tableblind/1.0.0"


# ------------------------------------------------------------------------------------------------
# The result type
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Prediction:
    """One re-derived value, where it was found, and how.

    ``None`` from :meth:`Extractor.predict` is an **abstention** -- FR-3.3's distinction between
    "no value" and "the empty value" -- and the corpus format carries it as
    ``predicted_value: None`` rather than ``""``. Collapsing the two would hand the risk-coverage
    curve a confident wrong answer in place of an honest silence.
    """

    value: str
    """The value **as printed in the document** -- the cell text, or the token that was read.

    This is the common currency, and having one is the whole reason this field and
    :attr:`asserted_value` are separate. Gold records the cell text exactly as printed (``6``,
    never ``6 A``: the unit lives in the column header, which gold carries separately). A system
    that composes the two and one that does not are both right and are not comparable on ``==``,
    so the value axis is scored on what was printed and every system reports it here."""

    page: int
    box: tuple[float, float, float, float]
    confidence: float
    method: str
    """``table_cell`` or ``text_window``. The stratifier. This field is why the report can say
    which half of the score is comparable to ExtractBench and which half is partly circular."""

    distance: int = 0
    """Words between the anchor and the value. Diagnosis, and the honest reason a text-window
    prediction is uncertain rather than a number invented to look like one."""

    candidates: int = 0
    """How many tokens in the window matched. A choice is less certain than a find."""

    asserted_value: str = ""
    """What the system actually claims, which may state more than the document prints.

    R1 composes the unit its column header declares -- ``16`` under *Rated current I n A* becomes
    ``16 A`` -- because FR-4.3 says a bare number in a cell is not a fact. That composed value is
    what gets compared against the customer's catalog, so it is what the *disagreement* half of the
    corpus must use. Empty means "same as :attr:`value`", which is the honest default for a system
    that composes nothing."""

    @property
    def claim(self) -> str:
        """What this system asserts. :attr:`asserted_value` when it composed, otherwise what it
        read."""
        return self.asserted_value or self.value


# ------------------------------------------------------------------------------------------------
# The contract, and the guard that keeps it honest
# ------------------------------------------------------------------------------------------------


@runtime_checkable
class Extractor(Protocol):
    """What the benchmark is allowed to ask a system to do.

    Knowing *which* product is under audit is not a leak: ``mpn`` comes from the catalog record's
    identity, and an auditor who did not know which row to read would be solving a different
    problem. Knowing what the value *is* would be a leak, and nothing in this signature supplies
    one.
    """

    name: str
    version: str

    def predict(
        self,
        layer: TextLayer,
        tables: tuple[Table, ...],
        *,
        mpn: str,
        attribute: AuditAttribute,
    ) -> Prediction | None: ...


#: Parameter names that would mean the extractor can see the answer. Matched as substrings against
#: the lowercased parameter name, so ``gold_value``, ``catalog``, ``expected`` and ``known_value``
#: are all caught. Deliberately over-broad: a false positive here costs a rename, a false negative
#: costs the meaning of every number the benchmark prints.
FORBIDDEN_PARAMETERS = (
    "gold",
    "catalog",
    "expected",
    "answer",
    "truth",
    "label",
    "target",
    "record",
    "entry",
    "hint",
    "context",
)


def assert_blind(extractor: object) -> None:
    """FR-3.4, checked on a live object rather than trusted.

    Raises ``TypeError`` when ``predict`` carries a parameter through which the answer could
    arrive, or a ``**kwargs`` through which anything at all could. Called by the corpus builder
    before a single record is produced, so a leaky extractor cannot get as far as writing a score.
    """
    predict_fn = getattr(extractor, "predict", None)
    if predict_fn is None:
        raise TypeError(f"{extractor!r} has no predict(); it cannot be benchmarked")

    signature = inspect.signature(predict_fn)
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            raise TypeError(
                f"{extractor!r}.predict accepts arbitrary keywords via {parameter.name!r}. FR-3.4 "
                "is enforced by the signature, and a signature that accepts anything enforces "
                "nothing -- the catalog value could arrive through it and every subsequent "
                "agreement would be meaningless."
            )
        lowered = parameter.name.lower()
        hit = next((f for f in FORBIDDEN_PARAMETERS if f in lowered), None)
        if hit is not None:
            raise TypeError(
                f"{extractor!r}.predict takes {parameter.name!r}, which contains {hit!r}. "
                "FR-3.4: the extractor must not be able to see the catalog's value or the gold "
                "value. Passing one in measurably improves grounding and makes the measurement "
                "worthless."
            )


# ------------------------------------------------------------------------------------------------
# The baseline: table-blind, frozen, independent of gold's mechanism
# ------------------------------------------------------------------------------------------------

#: How many words either side of the anchor the baseline searches. Wide enough to cross a table row
#: in reading order, narrow enough that it does not wander into the next SKU. Chosen from the
#: documents' own row width (seven columns), **not** tuned against the score -- tuning a window
#: until the grounding number improves is fitting the extractor to the answer key.
BASELINE_WINDOW = 8

#: The baseline's own value patterns and specificities, carried here rather than read from R1's
#: attribute map.
#:
#: This looks like duplication and is the opposite. The map in ``audit/config/attributes.yaml`` is
#: a live product artifact: it is edited when a customer's column headers change, and every edit
#: would silently move a *baseline* score that is supposed to be a fixed point. A benchmark
#: baseline that moves when the product changes cannot be used to tell whether the product
#: improved. These are the values frozen with the gate-2 measurement on 20 August 2026 and they do
#: not change again.
#:
#: The spread of difficulty is deliberate rather than flattering: ``order_code`` and ``weight_kg``
#: have distinctive shapes and should ground easily, while ``rated_current``, ``poles`` and
#: ``packaging_uom`` are all bare small integers, mutually ambiguous, and sitting in adjacent
#: columns. A table-blind extractor confuses them -- which is exactly the failure ExtractBench's
#: word-level grounding metric exists to expose.
BASELINE_PATTERNS: dict[str, tuple[str, float]] = {
    "rated_current": (r"^\d{1,2}(?:\.\d)?$", 0.35),
    "poles": (r"^[1-4]$", 0.25),
    "order_code": (r"^2CDS\w{10,}$", 0.95),
    "packaging_uom": (r"^\d{1,3}$", 0.30),
    "weight_kg": (r"^\d\.\d{3}$", 0.90),
}


@dataclass(frozen=True, slots=True)
class _BaselineSpec:
    pattern: re.Pattern[str]
    specificity: float


_BASELINE_SPECS: dict[str, _BaselineSpec] = {
    key: _BaselineSpec(pattern=re.compile(pattern), specificity=specificity)
    for key, (pattern, specificity) in BASELINE_PATTERNS.items()
}


class TableBlindExtractor:
    """The gate-2 baseline, promoted out of the spike and frozen.

    **This is the code that produced 46.34%.** It was written as throwaway scaffolding because at
    the time it had no other job; it turns out to have one. A benchmark needs a baseline whose
    mechanism is independent of the gold builder's, and this is that baseline: it receives a
    ``TextLayer`` -- a linear sequence of words with boxes -- and nothing else. It cannot see
    cells, columns, row boundaries or headers.

    The ``tables`` argument is accepted and **deliberately ignored**, so that one signature serves
    both systems. Ignoring it in a method that receives it is a stronger statement than not
    receiving it: the structure was available and this extractor declines to look, which is what
    "table-blind by construction" has to mean when the caller has the tables in hand.

    Being table-blind is not a simplification for convenience. If the baseline read the same table
    structure the gold builder reads, the two would agree by construction, grounding F1 would be
    ~100%, and the number would say nothing about anything.
    """

    name = "tableblind"
    version = BASELINE_VERSION

    def predict(
        self,
        layer: TextLayer,
        tables: tuple[Table, ...],
        *,
        mpn: str,
        attribute: AuditAttribute,
    ) -> Prediction | None:
        """Nearest-first outward from the anchor, taking the first token whose shape matches.

        Nearest-first is the only defensible ordering without table structure: with no columns to
        reason about, proximity in reading order is all the evidence there is.
        """
        del tables  # see the class docstring: available, declined, on purpose.

        spec = _BASELINE_SPECS.get(attribute.key)
        if spec is None:
            return None

        matches: list[tuple[int, int, Word]] = []
        for anchor in (i for i, w in enumerate(layer.words) if w.text == mpn):
            lo = max(0, anchor - BASELINE_WINDOW)
            hi = min(len(layer.words), anchor + BASELINE_WINDOW + 1)
            for index in range(lo, hi):
                if index == anchor:
                    continue
                word = layer.words[index]
                if spec.pattern.match(word.text):
                    matches.append((abs(index - anchor), index, word))

        if not matches:
            return None

        distance, _, word = min(matches, key=lambda m: (m[0], m[1]))
        return Prediction(
            value=word.text,
            page=word.page,
            box=word.bbox,
            confidence=_baseline_confidence(spec, distance, len(matches)),
            method="text_window",
            distance=distance,
            candidates=len(matches),
        )


def _baseline_confidence(spec: _BaselineSpec, distance: int, candidates: int) -> float:
    """Three signals, all observable without knowing the answer.

    Pattern specificity (``2CDS271061R0065`` can only be an order code; ``6`` could be four
    different attributes), distance from the anchor (a token further away in reading order is more
    likely to belong to a different row), and contention (when several tokens match, the extractor
    is *choosing*, and a choice is less certain than a find).

    Deliberately not fitted to the outcome. A confidence tuned until the risk-coverage curve looked
    good would be reporting how well it was tuned, and that curve is the whole instrument for
    FR-6.3.
    """
    proximity = 1.0 / (1.0 + 0.25 * distance)
    contention = 1.0 / candidates**0.5
    return round(min(1.0, max(0.0, spec.specificity * proximity * contention)), 4)


# ------------------------------------------------------------------------------------------------
# The shipped extractor
# ------------------------------------------------------------------------------------------------


class R1Extractor:
    """``errata_audit.derive``, scored on the same metric as the baseline.

    Nothing about the derivation is reimplemented here. This adapter resolves an ETIM class, calls
    ``derive``, and translates a :class:`errata_audit.Derivation` into a :class:`Prediction` -- so
    the thing being measured is the thing that ships, down to the abstention reasons and the raw
    score.

    **The evidence box is the claim's own box**, taken from ``Evidence.bbox``, not recomputed.
    ADR-002 makes the bbox a projection of a stored char span; reprojecting it here would score a
    box the product never emitted.

    **The score carried into the corpus is the raw score, not a calibrated probability.**
    ``Derivation.raw_score`` and ``Confidence.probability`` are separate fields precisely so that
    an uncalibrated number can never be printed as though it were calibrated, and no calibration
    set exists (nobody has adjudicated anything yet). The risk-coverage sweep needs only a ranking,
    and the raw score is an honest one; calling it a probability would not be.
    """

    name = "r1"
    version = DERIVE_VERSION

    def __init__(
        self,
        klass: EtimClass | None = None,
        *,
        doc_id: str = "",
        revision_sha256: str = "",
        withhold_tables: bool = False,
    ) -> None:
        self.klass = klass
        self.doc_id = doc_id
        self.revision_sha256 = revision_sha256
        self.withhold_tables = withhold_tables
        if withhold_tables:
            self.name = "r1-textwindow"

    """``withhold_tables`` is how R1 gets a score that means something.

    Scored against the published gold set as it normally runs, ``derive`` reports 100.00% word
    grounding F1 -- and that is a tautology, not a result. Gold is the cell under a named column in
    the row whose identity is the type designation; ``derive`` prefers exactly that cell. The two
    are the same act performed twice, and the number says nothing about extraction.

    Withholding the tables forces ``derive`` down its text-window fallback, which finds a value by
    proximity in reading order and cannot see cells or columns. That path shares no mechanism with
    gold, so the score it produces is a real measurement -- and it is the configuration most
    comparable to ExtractBench, whose systems read documents rather than parsed table structures.

    It is a constructor argument rather than a ``predict`` parameter on purpose: it configures the
    system under test before the benchmark starts, and FR-3.4 is about what reaches the extractor
    per record. Nothing here carries a value.
    """

    def predict(
        self,
        layer: TextLayer,
        tables: tuple[Table, ...],
        *,
        mpn: str,
        attribute: AuditAttribute,
    ) -> Prediction | None:
        derivation = derive(
            layer,
            () if self.withhold_tables else tables,
            mpn=mpn,
            attribute=attribute,
            klass=self.klass,
            sku_id=mpn,
            doc_id=self.doc_id,
            revision_sha256=self.revision_sha256,
            class_uri=f"etim:{self.klass.class_id}" if self.klass is not None else "",
        )
        if derivation.claim is None or not derivation.evidence:
            return None

        evidence = derivation.evidence[0]
        box = evidence.bbox
        # `table_cell` is the cell text exactly as the document prints it; the table path fills it
        # and the text-window path leaves it empty, where `value_raw` is already uncomposed
        # (compose() with no header returns the bare token). So this is the printed value on both
        # paths, without a special case that could drift from either.
        as_printed = evidence.table_cell or derivation.claim.value_raw
        return Prediction(
            value=as_printed,
            asserted_value=derivation.claim.value_raw,
            page=evidence.page,
            box=(box.x0, box.y0, box.x1, box.y1),
            confidence=float(derivation.raw_score),
            method=derivation.method,
            distance=derivation.distance,
            candidates=derivation.candidates,
        )


EXTRACTORS: dict[str, str] = {
    "tableblind": "the frozen gate-2 baseline: table-blind, independent of gold's mechanism",
    "r1": (
        "errata_audit.derive as it ships. Scores 100% against the published gold set because both "
        "read the same cell -- a tautology, not a result. Use it to see that, not to quote it."
    ),
    "r1-textwindow": (
        "errata_audit.derive with table structure withheld, forcing its text-window fallback. "
        "Shares no mechanism with gold, so this is R1's real, ExtractBench-comparable number."
    ),
}


def get_extractor(
    name: str,
    *,
    klass: EtimClass | None = None,
    doc_id: str = "",
    revision_sha256: str = "",
) -> Extractor:
    """Build a named extractor. Unknown names raise rather than defaulting to anything."""
    if name == "tableblind":
        return TableBlindExtractor()
    if name == "r1":
        return R1Extractor(klass, doc_id=doc_id, revision_sha256=revision_sha256)
    if name == "r1-textwindow":
        return R1Extractor(
            klass,
            doc_id=doc_id,
            revision_sha256=revision_sha256,
            withhold_tables=True,
        )
    raise ValueError(f"unknown extractor {name!r}; known: {', '.join(sorted(EXTRACTORS))}")
