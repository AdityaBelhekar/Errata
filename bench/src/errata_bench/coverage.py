"""R0 kill test 3 -- the calibration-coverage arithmetic (FR-0.4).

§8.3 makes the claim this module exists to test:

    Count the cells: 5,600 ETIM classes, dozens of attributes each, several document families per
    manufacturer. Conformal prediction with class-conditional coverage needs a floor of labels per
    cell to be honest, and under any realistic labelling budget most cells will never reach it.

Phase 5 §2 item 1 states the consequence: `calibration_out_of_distribution` -- the abstention
reason the spec is proudest of -- fires on the large majority of the catalog, and coverage
collapses to the well-labelled classes. **The spec's most honest feature is also the one most
likely to eat the product.**

This module answers that with arithmetic. Given a class distribution and a labelling budget, it
computes how many classes clear the label floor and what fraction of SKUs live in them, under
three allocation strategies, with and without hierarchical pooling, swept across budgets.

The finding this is built to expose is a *contrast*, not a number:

    greedy-by-SKU-count -- the strategy any commercial operator would actually run -- dominates
    every other strategy on SKU coverage and still lands in the single digits on class
    coverage, at the module's default headline budget. You can calibrate most of the catalog's
    volume and almost none of its taxonomy. (See :data:`DEFAULT_HEADLINE_BUDGET` for exactly which
    budget and why, and the test suite for the assertion that guards this claim against drift.)

WHAT THIS MODULE IS NOT
-----------------------
It is not a measurement. The real ETIM 10.0 dictionary defines 5,600+ product classes (verified,
phase2-synthesis-and-verification.md §"ETIM"), but this repository does not contain the dictionary
and does not contain any real distributor's class histogram. :func:`synthetic_distribution` builds
a Zipf-shaped stand-in so the arithmetic can be explored; every report generated from it carries
:data:`SYNTHETIC_BANNER` and the gate verdict is pinned to
:attr:`CoverageGate.NOT_MEASURED` no matter how the numbers land. A structural result is a
statement about the shape of the arithmetic. It is not evidence about anybody's catalog, and this
module will not let a caller pretend otherwise.

Load a real distribution with :func:`load_distribution` and the gate becomes live.

DETERMINISM
-----------
No model call, no network call, no RNG. Same inputs, same bytes out.
"""

from __future__ import annotations

import csv
import enum
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "DEFAULT_BUDGETS",
    "DEFAULT_HEADLINE_BUDGET",
    "GATE_EXIT_CODES",
    "RESCOPE_BELOW",
    "SYNTHETIC_BANNER",
    "AllocationResult",
    "ClassDistribution",
    "ClassEntry",
    "CoverageGate",
    "CoveragePoint",
    "CoverageReport",
    "LabelCost",
    "LabelFloor",
    "PoolingModel",
    "Provenance",
    "Strategy",
    "allocate",
    "assess",
    "coverage_report",
    "label_floor",
    "load_distribution",
    "render_report",
    "report_as_dict",
    "sweep",
    "synthetic_distribution",
]


# ================================================================================================
# The distribution
# ================================================================================================


class Provenance(str, enum.Enum):
    """Where a class distribution came from. This decides whether a verdict is allowed."""

    EMPIRICAL = "empirical"
    """A real catalog's class histogram. The gate may issue a verdict."""

    SYNTHETIC = "synthetic"
    """A generated stand-in. The gate reports NOT MEASURED regardless of the numbers."""


@dataclass(frozen=True, slots=True)
class ClassEntry:
    """One product class and how many SKUs the catalog holds in it.

    ``parent_id`` is the class's parent in the classification tree (an ETIM group, for the real
    dictionary). It is only read when hierarchical pooling is enabled; leave it empty and pooling
    has nothing to borrow from.
    """

    class_id: str
    sku_count: int
    parent_id: str = ""
    label: str = ""

    def __post_init__(self) -> None:
        if self.sku_count < 0:
            raise ValueError(f"{self.class_id}: sku_count must be >= 0, got {self.sku_count}")


@dataclass(frozen=True, slots=True)
class ClassDistribution:
    """A catalog's class histogram, plus the provenance that decides what may be claimed from it."""

    entries: tuple[ClassEntry, ...]
    name: str = "unnamed"
    provenance: Provenance = Provenance.EMPIRICAL
    source: str = ""
    """Where this came from -- a file, an export, a generator and its parameters."""

    notes: tuple[str, ...] = ()
    """Assumptions a reader must see before quoting anything computed from this distribution."""

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for entry in self.entries:
            if entry.class_id in seen:
                raise ValueError(f"duplicate class_id {entry.class_id!r}")
            seen.add(entry.class_id)

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def class_count(self) -> int:
        return len(self.entries)

    @property
    def sku_total(self) -> int:
        return sum(e.sku_count for e in self.entries)

    @property
    def is_synthetic(self) -> bool:
        return self.provenance is Provenance.SYNTHETIC

    def by_sku_count(self) -> tuple[ClassEntry, ...]:
        """Largest class first; ties broken by class_id so the order is deterministic."""
        return tuple(sorted(self.entries, key=lambda e: (-e.sku_count, e.class_id)))


# ------------------------------------------------------------------------------------------------
# Loading a real distribution
# ------------------------------------------------------------------------------------------------


_CSV_ALIASES = {
    "class_id": "class_id",
    "class": "class_id",
    "etim_class": "class_id",
    "sku_count": "sku_count",
    "skus": "sku_count",
    "count": "sku_count",
    "parent_id": "parent_id",
    "parent": "parent_id",
    "group": "parent_id",
    "label": "label",
    "description": "label",
}


def load_distribution(
    path: str | Path,
    *,
    name: str | None = None,
    provenance: Provenance | None = None,
) -> ClassDistribution:
    """Load a class distribution from CSV or YAML.

    CSV: a header row naming at least ``class_id`` and ``sku_count``; ``parent_id`` and ``label``
    are optional. A handful of obvious aliases are accepted (``class``/``skus``/``group``).

    YAML::

        name: acme-distributor-2026Q1
        provenance: empirical
        source: PIM export 2026-03-01, crosswalked to ETIM 10.0
        notes:
          - classes with zero SKUs were dropped by the exporter
        classes:
          - {class_id: EC000123, sku_count: 41822, parent_id: EG000012}

    Provenance defaults to EMPIRICAL when the file does not declare it -- an operator who points
    this at a file is asserting it is real -- but the report says out loud that the file made no
    claim, so nobody can launder a generated CSV into a verdict by omission.
    """
    path = Path(path)
    if path.suffix.lower() in {".yaml", ".yml"}:
        return _load_yaml(path, name=name, provenance=provenance)
    if path.suffix.lower() in {".csv", ".tsv"}:
        return _load_csv(path, name=name, provenance=provenance)
    raise ValueError(f"unsupported distribution file {path.name!r}: expected .csv, .yaml or .yml")


def _resolve_provenance(
    declared: str | None, override: Provenance | None
) -> tuple[Provenance, tuple[str, ...]]:
    if override is not None:
        return override, ()
    if declared:
        return Provenance(declared), ()
    return Provenance.EMPIRICAL, (
        "the distribution file did not declare a provenance; it is being read as empirical "
        "because an operator pointed the harness at it. If it was generated, say so in the file.",
    )


def _load_yaml(
    path: Path, *, name: str | None, provenance: Provenance | None
) -> ClassDistribution:
    document: dict[str, Any] = yaml.safe_load(path.read_text("utf-8")) or {}
    rows = document.get("classes") or document.get("entries") or []
    resolved, notes = _resolve_provenance(document.get("provenance"), provenance)
    entries = tuple(
        ClassEntry(
            class_id=str(row["class_id"]),
            sku_count=int(row["sku_count"]),
            parent_id=str(row.get("parent_id", "") or ""),
            label=str(row.get("label", "") or ""),
        )
        for row in rows
    )
    if not entries:
        raise ValueError(f"{path.name}: no classes found")
    return ClassDistribution(
        entries=entries,
        name=name or str(document.get("name") or path.stem),
        provenance=resolved,
        source=str(document.get("source") or f"file: {path}"),
        notes=tuple(str(n) for n in document.get("notes", ())) + notes,
    )


def _load_csv(path: Path, *, name: str | None, provenance: Provenance | None) -> ClassDistribution:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError(f"{path.name}: empty file, expected a header row")
        columns = {}
        for raw in reader.fieldnames:
            key = _CSV_ALIASES.get(raw.strip().lower())
            if key and key not in columns:
                columns[key] = raw
        missing = {"class_id", "sku_count"} - set(columns)
        if missing:
            raise ValueError(
                f"{path.name}: header is missing {sorted(missing)}; "
                f"saw {list(reader.fieldnames)}"
            )
        entries = tuple(
            ClassEntry(
                class_id=str(row[columns["class_id"]]).strip(),
                sku_count=int(str(row[columns["sku_count"]]).strip()),
                parent_id=str(row.get(columns.get("parent_id", ""), "") or "").strip(),
                label=str(row.get(columns.get("label", ""), "") or "").strip(),
            )
            for row in reader
            if any((value or "").strip() for value in row.values())
        )
    if not entries:
        raise ValueError(f"{path.name}: header parsed but no rows found")
    resolved, notes = _resolve_provenance(None, provenance)
    return ClassDistribution(
        entries=entries,
        name=name or path.stem,
        provenance=resolved,
        source=f"file: {path}",
        notes=notes,
    )


# ------------------------------------------------------------------------------------------------
# The synthetic stand-in
# ------------------------------------------------------------------------------------------------


SYNTHETIC_BANNER = """
================================================================================================
  SYNTHETIC CLASS DISTRIBUTION -- STRUCTURAL RESULT, NOT AN EMPIRICAL ONE
------------------------------------------------------------------------------------------------
  No catalog was measured. The class count is taken from ETIM 10.0's published 5,600+ product
  classes; the per-class SKU counts are a Zipf ASSUMPTION about catalog concentration, not data.
  The parent grouping is arbitrary and was chosen to FLATTER hierarchical pooling.

  These figures show the SHAPE of the arithmetic and nothing else. FR-0.4 stays NOT MEASURED
  until a real distribution is loaded with load_distribution().
================================================================================================
""".strip()

#: Working catalog size used by the default synthetic distribution. Phase 5 §2 item 2 argues the
#: throughput problem using "a 400,000-SKU catalog"; the same order of magnitude is used here so
#: the two pieces of arithmetic talk about the same imaginary customer.
SYNTHETIC_DEFAULT_SKUS = 400_000

#: ETIM 10.0 (December 2024) defines more than 5,600 product classes -- verified in
#: phase2-synthesis-and-verification.md. This is the one number in the generator that is not an
#: assumption.
ETIM_10_CLASS_COUNT = 5_600


def synthetic_distribution(
    *,
    classes: int = ETIM_10_CLASS_COUNT,
    skus: int = SYNTHETIC_DEFAULT_SKUS,
    zipf_exponent: float = 1.1,
    groups: int = 100,
    name: str = "synthetic-zipf",
) -> ClassDistribution:
    """Build an explicitly-synthetic class distribution for exploring the arithmetic.

    **This function invents a catalog. Everything derived from it is structural.**

    The shape: SKU count of the rank-*r* class is proportional to ``r ** -zipf_exponent``, one SKU
    reserved for every class first so nothing is empty, the remainder distributed by largest
    remainder so the totals are exact. Zipf/power-law concentration in product catalogs is a
    modelling convention, chosen here because it is the standard heavy-tailed assumption and
    because it is *conservative in the direction that matters*: a flatter distribution would make
    class coverage look better, and a more concentrated one would make it look worse. The exponent
    is a parameter precisely so a reader can move it and watch the conclusion move.

    ``groups`` splits the classes into parent groups round-robin **by rank**, so every group
    contains head classes as well as tail classes. That is the most favourable possible
    arrangement for hierarchical pooling -- every sparse class sits under a parent that some
    well-funded sibling has already paid to calibrate. Pooled results computed on this
    distribution are therefore an upper bound, not an estimate.

    Deterministic: no RNG, no seed, identical output for identical arguments.
    """
    if classes <= 0:
        raise ValueError("classes must be positive")
    if skus < classes:
        raise ValueError(f"need at least one SKU per class: skus={skus} < classes={classes}")
    if zipf_exponent <= 0:
        raise ValueError("zipf_exponent must be positive")
    if groups <= 0:
        raise ValueError("groups must be positive")

    weights = [(rank + 1) ** -zipf_exponent for rank in range(classes)]
    total_weight = math.fsum(weights)
    surplus = skus - classes
    shares = [surplus * w / total_weight for w in weights]
    counts = [int(share) for share in shares]
    remainder = surplus - sum(counts)
    order = sorted(range(classes), key=lambda i: (-(shares[i] - counts[i]), i))
    for i in order[:remainder]:
        counts[i] += 1

    entries = tuple(
        ClassEntry(
            class_id=f"SYN-{rank + 1:05d}",
            sku_count=counts[rank] + 1,
            parent_id=f"SYNGRP-{rank % groups:03d}",
            label=f"synthetic class at rank {rank + 1}",
        )
        for rank in range(classes)
    )
    return ClassDistribution(
        entries=entries,
        name=name,
        provenance=Provenance.SYNTHETIC,
        source=(
            f"synthetic_distribution(classes={classes}, skus={skus}, "
            f"zipf_exponent={zipf_exponent}, groups={groups})"
        ),
        notes=(
            f"class count {classes} follows ETIM 10.0's published 5,600+ classes "
            "(phase2-synthesis-and-verification.md); the SKU counts are not data.",
            f"per-class SKU counts assume a Zipf law with exponent {zipf_exponent}. "
            "This is a modelling assumption about catalog concentration, not a measurement.",
            f"the {groups} parent groups are assigned round-robin by rank, which is the most "
            "pooling-favourable arrangement possible. Pooled numbers are an upper bound.",
        ),
    )


# ================================================================================================
# The label floor
# ================================================================================================


@dataclass(frozen=True, slots=True)
class LabelFloor:
    """How many labels one class needs before its conformal predictor is honest.

    Two separate bounds, both derived below, and the larger one binds.

    **1. The feasibility floor -- exact.**

    Split (inductive) conformal prediction, in its standard form: hold out *n* calibration points,
    compute a nonconformity score for each, and set the threshold to the
    ``ceil((n + 1) * (1 - alpha))``-th smallest score. Under exchangeability of the calibration
    points with the test point, the resulting prediction set covers the truth with probability at
    least ``1 - alpha``. (Vovk/Papadopoulos inductive conformal prediction; the finite-sample
    quantile-rank form is the one restated in Lei et al. 2018 and in Angelopoulos & Bates,
    "A Gentle Introduction to Conformal Prediction".)

    That rank must be a score that actually exists, so it must be at most *n*::

        ceil((n + 1)(1 - alpha)) <= n
        =>  (n + 1)(1 - alpha)   <= n
        =>  1 - alpha(n + 1)     <= 0
        =>  n                    >= 1/alpha - 1

    Below that, the ``1 - alpha`` quantile of the calibration scores is ``+inf``: the honest
    prediction set is "everything", which is exactly the abstention the spec calls
    ``calibration_out_of_distribution``. For ``alpha = 0.1`` this is 9 labels. **It is a floor on
    arithmetic, not on statistics** -- clearing it buys the right to emit a non-trivial set, not a
    trustworthy one -- which is why quoting 9 as "the label floor" would be a lie of omission.

    **2. The tolerance floor -- the one that matters.**

    The ``1 - alpha`` guarantee is marginal over draws of the calibration set. For a *given*
    calibration set the realised coverage is random, and its distribution is known exactly::

        Coverage | calibration set  ~  Beta(n + 1 - l, l),   l = floor((n + 1) * alpha)

    (Vovk 2012, "Conditional validity of inductive conformal predictors"; restated in Angelopoulos
    & Bates §3.2.) Class-conditional coverage that is honest to a stated tolerance therefore needs
    enough labels that this Beta is tight. This floor is the smallest *n* for which

        P(Coverage < 1 - alpha - tolerance)  <=  1 - confidence

    computed exactly, via the integer-parameter identity
    ``I_x(a, b) = P(Binomial(a + b - 1, x) >= a)``. No approximation, no table, no magic constant.

    At ``alpha=0.1, tolerance=0.05, confidence=0.9`` this lands at 15 labels per class (verify with
    ``label_floor().tolerance_floor`` -- it is the binding bound here, not the feasibility floor of
    9) -- and that is *per calibration cell*. §8.3 counts cells as class x attribute x document
    family, so ``cells_per_class`` multiplies it. The default of 1 is the most charitable reading
    available
    (perfect attribute-type pooling within a class, one document family). Set it to the "dozens of
    attributes" §8.3 actually describes and the arithmetic below gets very much worse.
    """

    alpha: float
    """Target miscoverage. ``alpha = 0.1`` is a 90% target coverage."""

    tolerance: float
    """How far below ``1 - alpha`` the realised class-conditional coverage may fall."""

    confidence: float
    """Probability with which the tolerance must hold. 0.9 => allow a 10% shortfall chance."""

    cells_per_class: int
    """Calibration cells per class: attributes x document families (§8.3). 1 is charitable."""

    feasibility_floor: int
    """``ceil(1/alpha - 1)``. Below this the prediction set is trivially 'everything'."""

    tolerance_floor: int
    """Smallest n whose Beta(n+1-l, l) coverage law meets the tolerance at the stated confidence."""

    @property
    def skus_per_class(self) -> int:
        """Distinct SKUs a class must contain before it can be calibrated at all.

        One adjudicated decision per SKU per cell, so the SKU requirement is the per-cell floor;
        the same SKU serves every attribute of its class.
        """
        return max(self.feasibility_floor, self.tolerance_floor)

    @property
    def labels_per_class(self) -> int:
        """Labels a class needs in total: the per-cell floor times the number of cells."""
        return self.skus_per_class * self.cells_per_class

    @property
    def target_coverage(self) -> float:
        return 1.0 - self.alpha

    def derivation(self) -> str:
        """The argument, printed next to the number, every time."""
        return (
            f"target coverage {100 * self.target_coverage:.0f}% (alpha={self.alpha:g}), "
            f"tolerated shortfall {100 * self.tolerance:.0f}pp at "
            f"{100 * self.confidence:.0f}% confidence\n"
            f"  split-conformal feasibility  n >= ceil(1/alpha - 1) "
            f"= {self.feasibility_floor}  (below this the honest set is 'everything')\n"
            f"  coverage-tolerance bound     n >= {self.tolerance_floor}  "
            f"(smallest n with P(Beta(n+1-l, l) < {self.target_coverage - self.tolerance:.2f}) "
            f"<= {1 - self.confidence:.2f}, l = floor((n+1)*alpha))\n"
            f"  binding floor                {self.skus_per_class} labelled SKUs per class\n"
            f"  cells per class              x{self.cells_per_class} "
            f"(attributes x document families, §8.3)\n"
            f"  => {self.labels_per_class} labels per class"
        )


def _log_binom_sf(n: int, k: int, p: float) -> float:
    """P(Binomial(n, p) >= k), summed in log space so large binomials do not overflow."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    log_p, log_q = math.log(p), math.log1p(-p)
    log_n_fact = math.lgamma(n + 1)
    terms = [
        math.exp(
            log_n_fact
            - math.lgamma(j + 1)
            - math.lgamma(n - j + 1)
            + j * log_p
            + (n - j) * log_q
        )
        for j in range(k, n + 1)
    ]
    return min(1.0, math.fsum(terms))


def _coverage_shortfall_probability(n: int, alpha: float, tolerance: float) -> float:
    """P(realised coverage < 1 - alpha - tolerance) for a split-conformal predictor with n labels.

    Coverage | calibration ~ Beta(n + 1 - l, l) with l = floor((n + 1) * alpha), and for integer
    parameters the Beta CDF is a binomial tail: I_x(a, b) = P(Binomial(a + b - 1, x) >= a).
    """
    threshold = 1.0 - alpha - tolerance
    if threshold <= 0.0:
        return 0.0
    if threshold >= 1.0:
        return 1.0
    l_rank = math.floor((n + 1) * alpha)
    if l_rank < 1:
        # The (1 - alpha) quantile does not exist; the set is 'everything', coverage is 1.
        return 0.0
    a = n + 1 - l_rank
    return _log_binom_sf(n=a + l_rank - 1, k=a, p=threshold)


#: Refuse to search past this. A floor of a quarter of a million labels for a single class is not
#: a floor, it is a proof that the tolerance asked for is unbuyable, and the caller should be told
#: that rather than handed a number.
MAX_FLOOR_SEARCH = 250_000


def label_floor(
    *,
    alpha: float = 0.1,
    tolerance: float = 0.05,
    confidence: float = 0.9,
    cells_per_class: int = 1,
) -> LabelFloor:
    """Derive the per-class label floor from the split-conformal coverage guarantee.

    See :class:`LabelFloor` for the derivation. Nothing here is hardcoded: change ``alpha`` and
    both bounds move.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    if not 0.0 <= tolerance < 1.0 - alpha:
        raise ValueError(f"tolerance must be in [0, {1 - alpha}), got {tolerance}")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    if cells_per_class < 1:
        raise ValueError("cells_per_class must be >= 1")

    feasibility = max(1, math.ceil(1.0 / alpha - 1.0 - 1e-12))
    gamma = 1.0 - confidence

    def meets(n: int) -> bool:
        return _coverage_shortfall_probability(n, alpha, tolerance) <= gamma

    if tolerance == 0.0:
        # A zero-tolerance demand is met only in the limit; report the feasibility floor and let
        # the caller see that the tolerance bound was not binding rather than silently inventing.
        tolerance_floor = feasibility
    else:
        # Exponential search for a satisfying n, then binary search for the boundary. The
        # condition is monotone in n up to the floor((n+1)*alpha) step, so the boundary is swept
        # backwards over a small window to recover the true minimum.
        hi = feasibility
        while not meets(hi):
            hi *= 2
            if hi > MAX_FLOOR_SEARCH:
                raise ValueError(
                    f"no calibration-set size below {MAX_FLOOR_SEARCH} meets "
                    f"tolerance={tolerance} at confidence={confidence} for alpha={alpha}. "
                    "The tolerance being asked for cannot be bought at any plausible budget."
                )
        lo = feasibility
        while lo < hi:
            mid = (lo + hi) // 2
            if meets(mid):
                hi = mid
            else:
                lo = mid + 1
        candidate = lo
        for n in range(max(feasibility, candidate - 64), candidate):
            if meets(n):
                candidate = n
                break
        tolerance_floor = candidate

    return LabelFloor(
        alpha=alpha,
        tolerance=tolerance,
        confidence=confidence,
        cells_per_class=cells_per_class,
        feasibility_floor=feasibility,
        tolerance_floor=tolerance_floor,
    )


# ================================================================================================
# Hierarchical pooling
# ================================================================================================


@dataclass(frozen=True, slots=True)
class PoolingModel:
    """§8.3's mitigation: a sparse class borrows strength from its parent in the ETIM tree.

    Modelled here as a **reduced effective floor**, and every part of that reduction is an
    explicit parameter rather than a hidden constant, because the reduction is an assumption and
    not a result.

    The assumption, stated so it can be attacked: if a parent group has already accumulated
    ``parent_floor_multiple`` floors' worth of labels across its funded children, a sibling class
    needs only ``floor_fraction`` of its own standalone floor, because the parent's calibration
    supplies a prior for the rest.

    **What is wrong with that assumption, in the module that uses it.** Split conformal's coverage
    guarantee rests on exchangeability between the calibration points and the test point.
    Borrowing labels from a sibling class breaks exactly that exchangeability -- if sibling
    classes were exchangeable there would be no reason to calibrate them separately, and the
    class-conditional coverage §8.3 asks for would be unnecessary. So ``floor_fraction`` is not
    derived from anything here. It is a knob for asking "how strong would pooling have to be for
    the conclusion to change", and the honest answer for any real deployment is that the discount
    must be measured per taxonomy level before it is believed. Pooled numbers are never a result.
    """

    enabled: bool = False
    floor_fraction: float = 0.5
    """Fraction of the standalone floor a pooled class needs. ASSUMPTION. Default 0.5 is generous."""

    parent_floor_multiple: float = 1.0
    """How many full floors a parent must accumulate across children before pooling is available."""

    def __post_init__(self) -> None:
        if not 0.0 < self.floor_fraction <= 1.0:
            raise ValueError("floor_fraction must be in (0, 1]")
        if self.parent_floor_multiple <= 0.0:
            raise ValueError("parent_floor_multiple must be positive")

    @property
    def assumption(self) -> str:
        if not self.enabled:
            return "hierarchical pooling disabled"
        return (
            f"pooling ASSUMPTION: a class under a parent holding >= "
            f"{self.parent_floor_multiple:g} floors of labels needs only "
            f"{100 * self.floor_fraction:.0f}% of its own floor. Not derived, not measured; "
            f"pooling breaks the exchangeability the conformal guarantee rests on."
        )


# ================================================================================================
# Allocation strategies
# ================================================================================================


class Strategy(str, enum.Enum):
    """How a finite label budget is spread over classes."""

    PROPORTIONAL = "proportional"
    """Labels in proportion to SKU count. The 'fair to the catalog' baseline. Its failure mode is
    waste: the tail receives labels that can never reach a floor, and they buy nothing."""

    EQUAL = "equal"
    """Budget split evenly over every class. The 'fair to the taxonomy' baseline, and the one that
    exposes the raw arithmetic -- with 5,600 classes and a floor of 60, it clears nothing at all
    until the budget passes 336,000 labels."""

    GREEDY = "greedy"
    """Fund the largest classes to exactly their floor, biggest first, until the budget runs out.
    The strategy a commercial operator actually runs. Provably dominates PROPORTIONAL on both
    class count and SKU coverage -- and still lands in the single digits on class coverage at the
    module's headline budget, which is the finding."""


@dataclass(frozen=True, slots=True)
class AllocationResult:
    """Labels assigned per class, and the floor each class was measured against."""

    strategy: Strategy
    budget: int
    labels: tuple[int, ...]
    floor_labels: tuple[int, ...]
    capacity: tuple[int, ...]
    pooled: tuple[bool, ...]


def _floor_vector(
    distribution: ClassDistribution,
    floor: LabelFloor,
    pooling: PoolingModel,
    funded_labels: Sequence[int] | None,
) -> tuple[tuple[int, ...], tuple[bool, ...]]:
    """Per-class floor in labels, after any pooling discount."""
    base_skus = floor.skus_per_class
    base_labels = floor.labels_per_class
    size = len(distribution)
    if not pooling.enabled or funded_labels is None:
        return (base_labels,) * size, (False,) * size

    needed = pooling.parent_floor_multiple * base_labels
    accumulated: dict[str, int] = {}
    for entry, labels in zip(distribution.entries, funded_labels, strict=True):
        if entry.parent_id and labels >= base_labels:
            accumulated[entry.parent_id] = accumulated.get(entry.parent_id, 0) + labels
    active = {parent for parent, total in accumulated.items() if total >= needed}

    # Pooling can shrink the tolerance floor; it cannot repeal the feasibility floor, because
    # below ceil(1/alpha - 1) calibration points the (1-alpha) quantile does not exist at all and
    # no amount of borrowed prior conjures one.
    discounted_skus = max(floor.feasibility_floor, math.ceil(pooling.floor_fraction * base_skus))
    discounted_labels = discounted_skus * floor.cells_per_class

    floors: list[int] = []
    pooled: list[bool] = []
    for entry in distribution.entries:
        is_pooled = entry.parent_id in active and discounted_labels < base_labels
        floors.append(discounted_labels if is_pooled else base_labels)
        pooled.append(is_pooled)
    return tuple(floors), tuple(pooled)


def _allocate_greedy(
    distribution: ClassDistribution, budget: int, floors: Sequence[int], capacity: Sequence[int]
) -> list[int]:
    labels = [0] * len(distribution)
    order = sorted(
        range(len(distribution)),
        key=lambda i: (-distribution.entries[i].sku_count, distribution.entries[i].class_id),
    )
    remaining = budget
    for i in order:
        need = floors[i]
        if need <= capacity[i] and need <= remaining:
            labels[i] = need
            remaining -= need
    return labels


def _allocate_equal(
    distribution: ClassDistribution, budget: int, capacity: Sequence[int]
) -> list[int]:
    share = budget // len(distribution)
    return [min(share, capacity[i]) for i in range(len(distribution))]


def _allocate_proportional(
    distribution: ClassDistribution, budget: int, capacity: Sequence[int]
) -> list[int]:
    total = distribution.sku_total
    if total <= 0:
        return [0] * len(distribution)
    shares = [budget * e.sku_count / total for e in distribution.entries]
    labels = [int(share) for share in shares]
    remainder = budget - sum(labels)
    order = sorted(range(len(labels)), key=lambda i: (-(shares[i] - labels[i]), i))
    for i in order[:remainder]:
        labels[i] += 1
    return [min(labels[i], capacity[i]) for i in range(len(labels))]


def allocate(
    distribution: ClassDistribution,
    budget: int,
    floor: LabelFloor,
    strategy: Strategy = Strategy.GREEDY,
    pooling: PoolingModel = PoolingModel(),
) -> AllocationResult:
    """Spend ``budget`` labels over ``distribution`` under ``strategy``.

    With pooling enabled this runs twice: once at the standalone floor to find which parents get
    calibrated, then again at the discounted floors those parents unlock. Two passes, not a fixed
    point -- pooling that needs three rounds of bootstrapping to pay off is not a mitigation.
    """
    if budget < 0:
        raise ValueError("budget must be >= 0")
    if not distribution.entries:
        raise ValueError("distribution has no classes")

    capacity = tuple(e.sku_count * floor.cells_per_class for e in distribution.entries)

    def run(floors: Sequence[int]) -> list[int]:
        if strategy is Strategy.GREEDY:
            return _allocate_greedy(distribution, budget, floors, capacity)
        if strategy is Strategy.EQUAL:
            return _allocate_equal(distribution, budget, capacity)
        return _allocate_proportional(distribution, budget, capacity)

    floors, pooled = _floor_vector(distribution, floor, pooling, None)
    labels = run(floors)
    if pooling.enabled:
        floors, pooled = _floor_vector(distribution, floor, pooling, labels)
        labels = run(floors)

    return AllocationResult(
        strategy=strategy,
        budget=budget,
        labels=tuple(labels),
        floor_labels=floors,
        capacity=capacity,
        pooled=pooled,
    )


# ================================================================================================
# Assessment
# ================================================================================================


@dataclass(frozen=True, slots=True)
class CoveragePoint:
    """One (budget, strategy) cell of the sweep."""

    budget: int
    strategy: Strategy
    pooled: bool

    classes_total: int
    classes_cleared: int
    classes_unreachable: int
    """Classes holding fewer SKUs than the floor requires. No budget can ever calibrate them."""

    classes_pooled_cleared: int

    skus_total: int
    skus_cleared: int

    labels_spent: int
    labels_wasted: int
    """Labels spent on classes that did not clear their floor. Bought nothing."""

    @property
    def class_coverage(self) -> float:
        return self.classes_cleared / self.classes_total if self.classes_total else 0.0

    @property
    def sku_coverage(self) -> float:
        return self.skus_cleared / self.skus_total if self.skus_total else 0.0

    @property
    def waste_fraction(self) -> float:
        return self.labels_wasted / self.labels_spent if self.labels_spent else 0.0

    @property
    def budget_unspendable(self) -> int:
        return self.budget - self.labels_spent


def assess(distribution: ClassDistribution, allocation: AllocationResult) -> CoveragePoint:
    """Score one allocation: how many classes cleared, and how much of the catalog they hold."""
    cleared = [
        allocation.labels[i] >= allocation.floor_labels[i] and allocation.floor_labels[i] > 0
        for i in range(len(distribution))
    ]
    unreachable = sum(
        1
        for i in range(len(distribution))
        if allocation.capacity[i] < allocation.floor_labels[i]
    )
    return CoveragePoint(
        budget=allocation.budget,
        strategy=allocation.strategy,
        pooled=any(allocation.pooled),
        classes_total=len(distribution),
        classes_cleared=sum(cleared),
        classes_unreachable=unreachable,
        classes_pooled_cleared=sum(
            1 for i in range(len(distribution)) if cleared[i] and allocation.pooled[i]
        ),
        skus_total=distribution.sku_total,
        skus_cleared=sum(
            distribution.entries[i].sku_count for i in range(len(distribution)) if cleared[i]
        ),
        labels_spent=sum(allocation.labels),
        labels_wasted=sum(
            allocation.labels[i] for i in range(len(distribution)) if not cleared[i]
        ),
    )


def sweep(
    distribution: ClassDistribution,
    budgets: Iterable[int],
    floor: LabelFloor,
    strategies: Iterable[Strategy] = tuple(Strategy),
    pooling: PoolingModel = PoolingModel(),
) -> tuple[CoveragePoint, ...]:
    """Coverage against budget, for every strategy. The answer is a curve, not a number."""
    points: list[CoveragePoint] = []
    for budget in sorted(set(budgets)):
        for strategy in strategies:
            points.append(assess(distribution, allocate(distribution, budget, floor, strategy, pooling)))
    return tuple(points)


# ================================================================================================
# Cost
# ================================================================================================


@dataclass(frozen=True, slots=True)
class LabelCost:
    """What a label costs, so the budget axis means something to a person holding a chequebook."""

    seconds_per_label: float = 40.0
    rate_per_hour_low: float = 20.0
    rate_per_hour_high: float = 35.0
    source: str = (
        "phase5-red-team.md Q4, quoting Phase 2's verified $20-$35/hour fully-loaded "
        "specialised-review band and a 40-second decision. Adjudicating a calibration label is "
        "assumed to cost the same as adjudicating a redline -- an assumption, not a measurement."
    )

    def band(self, labels: int) -> tuple[float, float]:
        hours = labels * self.seconds_per_label / 3600.0
        return hours * self.rate_per_hour_low, hours * self.rate_per_hour_high

    def render(self, labels: int) -> str:
        low, high = self.band(labels)
        return f"${low:,.0f}-${high:,.0f}"


# ================================================================================================
# The gate
# ================================================================================================


class CoverageGate(str, enum.Enum):
    """The FR-0.4 decision."""

    NOT_MEASURED = "NOT MEASURED"
    """Synthetic input. The shape of the answer is reported; no empirical claim is made."""

    RESCOPE = "RESCOPE"
    """Real distribution, single-digit class coverage. §13: re-scope R2 to named high-volume
    classes and reprice. The catalog-wide audit is not a product."""

    NARROW = "NARROW"
    """Real distribution, class coverage under half. A catalog-wide claim is not supportable;
    coverage is a sold quantity, per class (§8.3)."""

    PASS = "PASS"
    """Real distribution, most classes calibratable at the stated budget."""

    INCONCLUSIVE = "INCONCLUSIVE"
    """Degenerate input, or the headline budget was not in the sweep."""


#: §13's kill condition names the single-digit trigger and nothing above it.
RESCOPE_BELOW = 0.10

#: The boundary between NARROW and PASS is this module's own reading, not the spec's. Flagged as
#: such in every report so nobody quotes it as a spec threshold.
PASS_ABOVE = 0.50

#: Mirrors errata_bench.cli.EXIT_* without importing it -- the CLI owns exit-code policy.
GATE_EXIT_CODES: dict[CoverageGate, int] = {
    CoverageGate.PASS: 0,
    CoverageGate.NARROW: 1,
    CoverageGate.RESCOPE: 2,
    CoverageGate.INCONCLUSIVE: 3,
    CoverageGate.NOT_MEASURED: 3,
}

#: A pilot-scale sweep, from a token diagnostic (1,000 labels, ~$222-$389 at the LabelCost band
#: below) up to a catalog-wide one-time program (250,000 labels, ~$55,556-$97,222). Left
#: deliberately wide: the point of a sweep is to show the whole curve, including the budgets at
#: which the headline finding below stops holding -- see the 50,000 row, where the same reference
#: distribution already clears 38% of classes, a materially better (and worse-for-the-thesis)
#: number than the headline. Collapsing the sweep down to only budgets that support the headline
#: would be exactly the kind of cherry-picking this module exists to catch in other people's data.
DEFAULT_BUDGETS: tuple[int, ...] = (
    1_000,
    2_500,
    5_000,
    10_000,
    25_000,
    50_000,
    100_000,
    250_000,
)

#: The budget the module's headline finding (module docstring, Strategy.GREEDY) is measured at.
#:
#: This was previously 50,000, chosen only for affordability -- "$11k-$19k of specialist time is a
#: budget a real pilot might actually approve" -- without checking that it reproduces the finding
#: it was supposed to headline. It does not: on synthetic_distribution()'s own defaults (5,600
#: classes, 400,000 SKUs, zipf_exponent=1.1), GREEDY at 50,000 labels clears 38.05% of classes, not
#: "the single digits" the module claims. That is a real bug -- a docstring contradicted by its own
#: module's arithmetic -- not a rounding difference; see the coverage.py module docstring and the
#: Strategy.GREEDY docstring for the claim this number has to support.
#:
#: 5,000 is the fix, for two independent reasons that both point at the same number:
#:
#: 1. It is the largest budget in DEFAULT_BUDGETS at which GREEDY still clears fewer than
#:    RESCOPE_BELOW (10%) of classes on the reference synthetic distribution -- 5.95% class
#:    coverage against 77.39% SKU coverage (verify: label_floor() then
#:    assess(synthetic_distribution(), allocate(dist, 5_000, floor, Strategy.GREEDY))). 10,000
#:    already clears 11.89%, past the module's own RESCOPE/NARROW boundary. "Single digits" is not
#:    a vibe here -- RESCOPE_BELOW is the module's own operative definition of it (see the
#:    CoverageReport.caveats note), so the headline budget should be the largest one still inside
#:    that definition on the reference distribution.
#: 2. It is still a plausible one-time calibration-labelling spend: ~$1,111-$1,944 (roughly 56
#:    hours, ~1.5 weeks of one reviewer) at the LabelCost band this module already uses
#:    (phase5-red-team.md Q4, quoting Phase 2's verified $20-$35/hour fully-loaded specialist-review
#:    band). A commercial operator sizing a first calibration pass would plausibly land here or
#:    below -- it is a modest pilot spend, not a catalog-wide program -- which is what makes the
#:    finding uncomfortable: even a realistic, easily-approved budget buys almost none of the
#:    taxonomy.
#:
#: 50,000 is not removed from the sweep -- see DEFAULT_BUDGETS above -- because the fact that a
#: 4-5x bigger budget still only reaches NARROW (not PASS) is itself part of the honest picture,
#: and burying it would trade one misleading headline for another.
DEFAULT_HEADLINE_BUDGET = 5_000


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Everything FR-0.4 asks for, and the caveats that stop it being over-read."""

    distribution: ClassDistribution
    floor: LabelFloor
    pooling: PoolingModel
    points: tuple[CoveragePoint, ...]
    budgets: tuple[int, ...]
    strategies: tuple[Strategy, ...]
    headline_budget: int
    cost: LabelCost = field(default_factory=LabelCost)

    @property
    def is_synthetic(self) -> bool:
        return self.distribution.is_synthetic

    def at(self, budget: int, strategy: Strategy) -> CoveragePoint | None:
        for point in self.points:
            if point.budget == budget and point.strategy is strategy:
                return point
        return None

    def headline(self) -> tuple[CoveragePoint, ...]:
        return tuple(p for p in self.points if p.budget == self.headline_budget)

    @property
    def best_class_coverage(self) -> float:
        headline = self.headline()
        return max((p.class_coverage for p in headline), default=0.0)

    @property
    def best_sku_coverage(self) -> float:
        headline = self.headline()
        return max((p.sku_coverage for p in headline), default=0.0)

    @property
    def gate(self) -> CoverageGate:
        """Synthetic input can never produce a verdict. That is the whole point of the flag."""
        if self.is_synthetic:
            return CoverageGate.NOT_MEASURED
        if not self.headline() or self.distribution.sku_total == 0:
            return CoverageGate.INCONCLUSIVE
        best = self.best_class_coverage
        if best < RESCOPE_BELOW:
            return CoverageGate.RESCOPE
        if best < PASS_ABOVE:
            return CoverageGate.NARROW
        return CoverageGate.PASS

    @property
    def caveats(self) -> list[str]:
        notes: list[str] = []
        if self.is_synthetic:
            notes.append(
                "the class distribution is SYNTHETIC. Every figure here is structural -- it "
                "describes the arithmetic, not a catalog. FR-0.4 is NOT MEASURED."
            )
        notes.extend(self.distribution.notes)
        if self.floor.cells_per_class == 1:
            notes.append(
                "cells_per_class = 1 assumes perfect attribute-type pooling within a class and a "
                "single document family. §8.3 counts dozens of attributes and several document "
                "families per class, so the floor used here is the most charitable one available."
            )
        if self.pooling.enabled:
            notes.append(self.pooling.assumption)
            notes.append(
                "pooled results are an upper bound: the discount is assumed, not measured, and "
                "borrowing across siblings breaks the exchangeability the guarantee rests on."
            )
        else:
            notes.append(
                "hierarchical pooling is OFF. §8.3 proposes it as the mitigation; run again with "
                "pooling enabled to see how large the assumed discount must be to matter."
            )
        notes.append(
            f"the {100 * RESCOPE_BELOW:.0f}% re-scope trigger is §13's 'single-digit percentage'. "
            f"The {100 * PASS_ABOVE:.0f}% NARROW/PASS boundary is this module's own reading and "
            "is not a threshold the spec states."
        )
        notes.append(
            "labels are counted, never simulated. Nothing here measures whether a calibrated "
            "class is actually well calibrated -- only whether it could be, at this budget."
        )
        unreachable = {p.classes_unreachable for p in self.points}
        if unreachable and max(unreachable) > 0:
            notes.append(
                f"up to {max(unreachable)} of {self.distribution.class_count} classes hold fewer "
                "SKUs than the floor requires. No budget reaches them; only pooling or a "
                "coarser taxonomy can."
            )
        return notes


def coverage_report(
    distribution: ClassDistribution | None = None,
    *,
    budgets: Iterable[int] = DEFAULT_BUDGETS,
    strategies: Iterable[Strategy] = tuple(Strategy),
    alpha: float = 0.1,
    tolerance: float = 0.05,
    confidence: float = 0.9,
    cells_per_class: int = 1,
    pooling: PoolingModel = PoolingModel(),
    headline_budget: int = DEFAULT_HEADLINE_BUDGET,
    cost: LabelCost | None = None,
) -> CoverageReport:
    """Run FR-0.4 end to end. This is the entry point a CLI should call.

    With no distribution it runs on :func:`synthetic_distribution` and the gate is pinned to
    ``NOT MEASURED`` -- which is the correct state of this kill test today.
    """
    distribution = distribution if distribution is not None else synthetic_distribution()
    floor = label_floor(
        alpha=alpha, tolerance=tolerance, confidence=confidence, cells_per_class=cells_per_class
    )
    budget_tuple = tuple(sorted({*budgets, headline_budget}))
    strategy_tuple = tuple(strategies)
    points = sweep(distribution, budget_tuple, floor, strategy_tuple, pooling)
    return CoverageReport(
        distribution=distribution,
        floor=floor,
        pooling=pooling,
        points=points,
        budgets=budget_tuple,
        strategies=strategy_tuple,
        headline_budget=headline_budget,
        cost=cost if cost is not None else LabelCost(),
    )


def compare_pooling(report: CoverageReport) -> CoverageReport:
    """The same report with pooling flipped, so the mitigation can be priced against the base case."""
    return coverage_report(
        report.distribution,
        budgets=report.budgets,
        strategies=report.strategies,
        alpha=report.floor.alpha,
        tolerance=report.floor.tolerance,
        confidence=report.floor.confidence,
        cells_per_class=report.floor.cells_per_class,
        pooling=replace(report.pooling, enabled=not report.pooling.enabled),
        headline_budget=report.headline_budget,
        cost=report.cost,
    )


# ================================================================================================
# Rendering
# ================================================================================================


_RULE = "-" * 96


def render_report(report: CoverageReport) -> str:
    """Human-readable FR-0.4 report. Prints the synthetic banner whenever it applies."""
    out: list[str] = []
    add = out.append

    add("")
    add("R0 KILL TEST 3 -- CALIBRATION COVERAGE (FR-0.4)")
    add(f"distribution: {report.distribution.name}   "
        f"{report.distribution.class_count:,} classes   "
        f"{report.distribution.sku_total:,} SKUs   [{report.distribution.provenance.value}]")
    if report.distribution.source:
        add(f"source: {report.distribution.source}")
    add(_RULE)

    if report.is_synthetic:
        add("")
        add(SYNTHETIC_BANNER)

    add("")
    add("Label floor -- where the number comes from")
    add(report.floor.derivation())
    add(f"  cost to clear ONE class        {report.cost.render(report.floor.labels_per_class)} "
        f"of specialist review ({report.floor.labels_per_class} labels -- not the per-label cost)")

    add("")
    add(report.pooling.assumption)

    add("")
    add("Coverage vs budget")
    add(f"{'budget':>9}  {'cost':>17}  {'strategy':<13}  {'classes':>16}  {'class %':>8}  "
        f"{'SKUs':>14}  {'SKU %':>7}  {'wasted':>7}")
    add(_RULE)
    for budget in report.budgets:
        for strategy in report.strategies:
            point = report.at(budget, strategy)
            if point is None:
                continue
            marker = " <" if budget == report.headline_budget else ""
            add(
                f"{budget:>9,}  {report.cost.render(budget):>17}  {strategy.value:<13}  "
                f"{point.classes_cleared:>7,}/{point.classes_total:<8,}  "
                f"{100 * point.class_coverage:>7.2f}%  "
                f"{point.skus_cleared:>14,}  {100 * point.sku_coverage:>6.2f}%  "
                f"{100 * point.waste_fraction:>6.1f}%{marker}"
            )
        add("")

    headline = report.headline()
    if headline:
        add(f"At the headline budget of {report.headline_budget:,} labels "
            f"({report.cost.render(report.headline_budget)})")
        best_class = max(headline, key=lambda p: p.class_coverage)
        best_sku = max(headline, key=lambda p: p.sku_coverage)
        add(f"  best class coverage   {100 * best_class.class_coverage:.2f}%  "
            f"({best_class.strategy.value})")
        add(f"  best SKU coverage     {100 * best_sku.sku_coverage:.2f}%  "
            f"({best_sku.strategy.value})")
        greedy = report.at(report.headline_budget, Strategy.GREEDY)
        if greedy is not None:
            add("")
            add("  The contrast that is the finding:")
            add(f"    greedy-by-SKU-count calibrates {100 * greedy.class_coverage:.2f}% of "
                f"classes and {100 * greedy.sku_coverage:.2f}% of SKUs.")
            add("    Volume is calibratable. The taxonomy is not. A catalog-wide audit priced on "
                "class coverage")
            add("    and a catalog-wide audit priced on SKU coverage are different products.")

    add("")
    add(_RULE)
    add(f"GATE: {report.gate.value}")
    add(_gate_sentence(report))

    add("")
    add("What this does not establish")
    for caveat in report.caveats:
        add(f"  - {caveat}")
    add("")
    return "\n".join(out)


def _gate_sentence(report: CoverageReport) -> str:
    gate = report.gate
    if gate is CoverageGate.NOT_MEASURED:
        return (
            "Synthetic input. This run reports the SHAPE of the answer and no empirical result.\n"
            "To make FR-0.4 live: obtain a real class histogram -- an IDEA/ETIM datapool export, "
            "or a public\ndistributor catalog crosswalked to ETIM 10.0 -- and pass it to "
            "load_distribution(). Nothing else\nabout this test is blocked."
        )
    if gate is CoverageGate.RESCOPE:
        return (
            f"Class coverage at the headline budget is "
            f"{100 * report.best_class_coverage:.2f}% -- single digits. Per §13 the "
            "abstention-first design is\nthe product's ceiling, not merely a risk: R2 narrows "
            "from a catalog-wide audit to a named set of\nhigh-volume classes, and the pricing "
            "follows the scope down."
        )
    if gate is CoverageGate.NARROW:
        return (
            f"Class coverage at the headline budget is "
            f"{100 * report.best_class_coverage:.2f}%. Not the single-digit collapse §13 "
            "names, and not a\ncatalog-wide audit either. Coverage is a sold quantity: name the "
            "classes in the contract."
        )
    if gate is CoverageGate.PASS:
        return (
            f"Class coverage at the headline budget is "
            f"{100 * report.best_class_coverage:.2f}%. The catalog-wide claim survives this "
            "arithmetic -- which is\nnot the same as surviving the calibration itself."
        )
    return (
        "Degenerate input: no classes, no SKUs, or the headline budget was not swept. No verdict."
    )


def report_as_dict(report: CoverageReport) -> dict[str, Any]:
    """Machine-readable FR-0.4 report. Carries the synthetic flag and banner, not just the numbers."""
    return {
        "gate": report.gate.value,
        "synthetic": report.is_synthetic,
        "banner": SYNTHETIC_BANNER if report.is_synthetic else "",
        "distribution": {
            "name": report.distribution.name,
            "provenance": report.distribution.provenance.value,
            "source": report.distribution.source,
            "classes": report.distribution.class_count,
            "skus": report.distribution.sku_total,
            "notes": list(report.distribution.notes),
        },
        "floor": {
            "alpha": report.floor.alpha,
            "target_coverage": report.floor.target_coverage,
            "tolerance": report.floor.tolerance,
            "confidence": report.floor.confidence,
            "cells_per_class": report.floor.cells_per_class,
            "feasibility_floor": report.floor.feasibility_floor,
            "tolerance_floor": report.floor.tolerance_floor,
            "skus_per_class": report.floor.skus_per_class,
            "labels_per_class": report.floor.labels_per_class,
            "derivation": report.floor.derivation(),
        },
        "pooling": {
            "enabled": report.pooling.enabled,
            "floor_fraction": report.pooling.floor_fraction,
            "parent_floor_multiple": report.pooling.parent_floor_multiple,
            "assumption": report.pooling.assumption,
        },
        "cost_model": {
            "seconds_per_label": report.cost.seconds_per_label,
            "rate_per_hour_low": report.cost.rate_per_hour_low,
            "rate_per_hour_high": report.cost.rate_per_hour_high,
            "source": report.cost.source,
        },
        "headline_budget": report.headline_budget,
        "sweep": [
            {
                "budget": p.budget,
                "strategy": p.strategy.value,
                "classes_total": p.classes_total,
                "classes_cleared": p.classes_cleared,
                "classes_unreachable": p.classes_unreachable,
                "classes_pooled_cleared": p.classes_pooled_cleared,
                "class_coverage": p.class_coverage,
                "skus_total": p.skus_total,
                "skus_cleared": p.skus_cleared,
                "sku_coverage": p.sku_coverage,
                "labels_spent": p.labels_spent,
                "labels_wasted": p.labels_wasted,
                "waste_fraction": p.waste_fraction,
                "budget_unspendable": p.budget_unspendable,
            }
            for p in report.points
        ],
        "caveats": report.caveats,
    }
