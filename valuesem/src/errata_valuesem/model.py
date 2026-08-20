"""Typed normalized values, refusals, and comparison verdicts.

Every value that enters the comparator is one of exactly two things:

  * a :class:`NormalizedValue` -- parsed into a typed structure whose semantics are known, or
  * a :class:`Refusal` -- the grammar declined, with a reason that can be routed.

There is no third option and there is no "best guess". FR-4.2: the grammar either parses or
refuses; refusal is a routable signal, never a silent fallback to string comparison.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

__all__ = [
    "IngressSpec",
    "Interval",
    "Kind",
    "MaterialSpec",
    "NormalizedValue",
    "PackagingSpec",
    "ParseResult",
    "Quantity",
    "Refusal",
    "RefusalReason",
    "Relation",
    "TermSpec",
    "ThreadSpec",
    "Tolerance",
    "Verdict",
]


class Kind(str, enum.Enum):
    """The semantic families the library can reason about."""

    QUANTITY = "quantity"
    """A magnitude with a unit, optionally toleranced. ``63 A``, ``10 +/-0.2 mm``."""

    QUANTITY_SET = "quantity_set"
    """An unordered set of alternative magnitudes. ``230/400 V`` -- not a range."""

    RANGE = "range"
    """A closed interval of magnitudes. ``-25...+70 degC``."""

    THREAD = "thread"
    """A screw thread designation. ``M8 x 1.25``, ``3/8-16 UNC-2A``, ``NPT 1/2-14``."""

    INGRESS = "ingress_protection"
    """An IEC 60529 ingress code. ``IP67``, ``IPX4``, ``IP6X``."""

    MATERIAL = "material"
    """A material identity resolved to an equivalence class. ``316`` = ``A4`` = ``1.4401``."""

    TERM = "term"
    """A controlled-vocabulary term resolved to a canonical id. ``Type C`` -> ``trip_curve/C``."""

    PACKAGING = "packaging"
    """A packaging frame: unit of measure plus quantity per pack. ``Box of 10``."""

    BOOLEAN = "boolean"
    """``Yes`` / ``No`` / ``true`` / ``-``."""

    COUNT = "count"
    """A dimensionless integer count. ``2``, ``4 pcs`` where the unit is a mere counter."""


class RefusalReason(str, enum.Enum):
    """Why the normalizer declined. Each maps onto a Declined-bucket reason (FR-6.2)."""

    NO_GRAMMAR_MATCH = "value_outside_known_grammar"
    """No registered parser recognised the surface form."""

    EMPTY = "empty_value"
    """The input was blank, or a null-ish placeholder (``-``, ``n/a``, ``TBD``)."""

    AMBIGUOUS_PARSE = "ambiguous_parse"
    """More than one parser claimed the value with incompatible readings."""

    UNKNOWN_UNIT = "unknown_unit"
    """The shape parsed but the unit is not in the registry. Extending the registry fixes this."""

    UNKNOWN_TERM = "unknown_vocabulary_term"
    """Looks like a controlled term but is absent from the ontology."""

    MALFORMED = "malformed_for_kind"
    """Matched a family's prefilter but failed that family's grammar. ``IP6``, ``M8x``."""


class Relation(str, enum.Enum):
    """How two normalized values stand to one another.

    The comparator maps these onto the §3.3 disagreement taxonomy. Keeping the two vocabularies
    separate matters: this library knows about *values*, and knows nothing about which side is the
    catalog and which is the evidence.
    """

    EQUIVALENT = "equivalent"
    """Same fact, same frame, same vocabulary."""

    EQUIVALENT_UNIT_FRAME = "equivalent_unit_frame"
    """Same fact, different unit system. ``0.5 in`` / ``12.7 mm``."""

    EQUIVALENT_VOCABULARY = "equivalent_vocabulary"
    """Same fact, different vocabulary. ``316 SS`` / ``A4`` / ``1.4401``."""

    A_MORE_SPECIFIC = "a_more_specific"
    """``a`` refines ``b``. ``NPT 1/2-14`` against ``Threaded``. Not a disagreement."""

    B_MORE_SPECIFIC = "b_more_specific"
    """``b`` refines ``a``. The under-specified case."""

    A_PRECISION_LOSS = "a_precision_loss"
    """``a`` dropped a tolerance that ``b`` carries. ``10 mm`` against ``10 +/-0.2 mm``."""

    B_PRECISION_LOSS = "b_precision_loss"
    """``b`` dropped a tolerance that ``a`` carries."""

    CONTRADICTION = "contradiction"
    """The two cannot both be true of the same product."""

    INCOMPARABLE = "incomparable"
    """Different semantic families, or incommensurable dimensions. Abstain -- never flag."""


EQUIVALENT_RELATIONS: frozenset[Relation] = frozenset(
    {
        Relation.EQUIVALENT,
        Relation.EQUIVALENT_UNIT_FRAME,
        Relation.EQUIVALENT_VOCABULARY,
    }
)


# --------------------------------------------------------------------------------------------
# Value payloads
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Interval:
    """A closed numeric interval in a single unit, used for precision reasoning."""

    lo: Decimal
    hi: Decimal
    unit: str

    def contains(self, point: Decimal) -> bool:
        return self.lo <= point <= self.hi

    def overlaps(self, other: Interval) -> bool:
        if self.unit != other.unit:
            raise ValueError(f"cannot overlap intervals in different units: {self.unit} vs {other.unit}")
        return self.lo <= other.hi and other.lo <= self.hi

    @property
    def width(self) -> Decimal:
        return self.hi - self.lo


@dataclass(frozen=True, slots=True)
class Tolerance:
    """An explicitly stated manufacturing tolerance.

    Distinct from the precision implied by significant figures. A dropped *explicit* tolerance is a
    finding (§3.3 precision mismatch); a rounded significant figure is not.
    """

    plus: Decimal
    minus: Decimal
    relative: bool = False
    """True when stated as a percentage: ``10 mm +/-2%``."""

    def absolute_bounds(self, nominal: Decimal) -> tuple[Decimal, Decimal]:
        if self.relative:
            return (
                nominal - (nominal.copy_abs() * self.minus / Decimal(100)),
                nominal + (nominal.copy_abs() * self.plus / Decimal(100)),
            )
        return (nominal - self.minus, nominal + self.plus)


@dataclass(frozen=True, slots=True)
class Quantity:
    """A magnitude with a unit.

    ``magnitude`` keeps the source's exact decimal, including trailing zeros, because the number of
    significant figures is load-bearing for precision comparison. ``Decimal("10.0")`` and
    ``Decimal("10")`` are different values to this library, deliberately.
    """

    magnitude: Decimal
    unit: str
    """Canonical Pint unit string. ``""`` for dimensionless."""

    tolerance: Tolerance | None = None

    qualifier: str = ""
    """A trailing modifier the unit registry cannot hold: ``AC``, ``DC``, ``rms``, ``max``.

    Frame-defining qualifiers change the fact -- ``230 V AC`` and ``230 V DC`` are different
    products. Advisory ones (``max``, ``typ``, ``nom``) do not, and must not be allowed to
    manufacture a disagreement.
    """

    exact: bool = False
    """True for values whose written form is exact by construction -- imperial fractions such as
    ``1/2 in``, and integer counts. Exact values get a point interval, not a half-ulp band."""

    @property
    def has_explicit_tolerance(self) -> bool:
        return self.tolerance is not None


@dataclass(frozen=True, slots=True)
class ThreadSpec:
    """A screw thread, completed from the standard pitch tables where the source omitted a pitch.

    ``M8`` and ``M8x1.25`` are the same thread: ISO 261 fixes the coarse pitch for M8 at 1.25 mm, so
    a bare ``M8`` is not less specific, it is fully specified by reference to the standard. ``M8x1``
    is a *different* thread and must contradict ``M8``.
    """

    system: str
    """``metric`` | ``unified`` | ``pipe_npt`` | ``pipe_bspp`` | ``pipe_bspt``."""

    nominal_mm: Decimal | None = None
    nominal_designation: str = ""
    """Source-side nominal as written: ``8``, ``3/8``, ``#10``, ``1/2``."""

    pitch_mm: Decimal | None = None
    tpi: Decimal | None = None
    series: str = ""
    """``UNC`` | ``UNF`` | ``UNEF`` | ``coarse`` | ``fine`` | ``NPT`` | ``G`` | ``R`` | ``Rp``."""

    tolerance_class: str = ""
    """``6g``, ``2A``, ``2B`` -- a refinement, not a different thread."""

    left_hand: bool = False
    pitch_inferred: bool = False
    """True when the pitch came from the standard table rather than the source string."""

    @property
    def designation(self) -> str:
        if self.system == "metric":
            base = f"M{_plain(self.nominal_mm)}"
            if self.pitch_mm is not None:
                base += f"x{_plain(self.pitch_mm)}"
            if self.tolerance_class:
                base += f"-{self.tolerance_class}"
            return base + (" LH" if self.left_hand else "")
        if self.system == "unified":
            base = f"{self.nominal_designation}-{_plain(self.tpi)}"
            if self.series:
                base += f" {self.series}"
            if self.tolerance_class:
                base += f"-{self.tolerance_class}"
            return base
        return f"{self.series} {self.nominal_designation}" + (
            f"-{_plain(self.tpi)}" if self.tpi is not None else ""
        )


@dataclass(frozen=True, slots=True)
class IngressSpec:
    """IEC 60529 ingress protection. ``None`` for a digit means ``X`` -- unspecified, not zero."""

    solids: int | None
    liquids: int | None
    suffix: str = ""
    """``K`` for IP69K, or letters like ``H``/``M``/``S``/``W``."""

    @property
    def designation(self) -> str:
        s = "X" if self.solids is None else str(self.solids)
        liq = "X" if self.liquids is None else str(self.liquids)
        return f"IP{s}{liq}{self.suffix}"


@dataclass(frozen=True, slots=True)
class MaterialSpec:
    """A material resolved into an equivalence class from the ontology."""

    group_id: str
    """Stable id: ``steel/stainless/316``."""

    canonical: str
    matched_alias: str
    caveat: str = ""
    """Set when the equivalence is real but conditional -- e.g. ``A4`` covers the 316 family, not
    only 316 itself. Surfaced in reviewer copy rather than silently dropped."""

    broader: tuple[str, ...] = ()
    """Group ids this material is a member of, for granularity comparison."""


@dataclass(frozen=True, slots=True)
class TermSpec:
    """A controlled-vocabulary term resolved to a canonical id."""

    vocabulary: str
    term_id: str
    canonical: str
    matched_alias: str
    subsumes_kinds: tuple[str, ...] = ()
    """Non-empty for generic terms like ``Threaded``, which subsume any THREAD value."""

    subsumes_groups: tuple[str, ...] = ()
    """Ontology group prefixes this term subsumes: ``Stainless steel`` -> ``steel/stainless``."""

    subsumes_terms: tuple[str, ...] = ()
    """Controlled-vocabulary term ids this generic covers: ``Circuit breaker`` -> the four
    ``device_type/*`` ids. Listing ids rather than a vocabulary name is deliberate -- it keeps the
    generic honest about scope, so a term added to the vocabulary later is NOT silently swept under
    an existing generic without someone deciding it belongs there."""

    restrict_thread_system: str = ""
    """Narrows what a generic term subsumes. ``NPT`` subsumes pipe_npt threads and *contradicts*
    a metric one -- without this it would swallow every thread as merely under-specified."""


@dataclass(frozen=True, slots=True)
class PackagingSpec:
    """A packaging frame. Getting this wrong corrupts price-per-unit, so it is its own kind."""

    uom_code: str
    """Rec 20 unit-of-measure code (``EA``, ``CEN``, ``DZN``, ``MTR``) or Rec 21 package-type code
    (``BX``, ``PK``, ``CT``, ``RO``). Both are used; see the provenance header in
    ``ontology/packaging.yaml``. Rec 20 lists the container nouns only to redirect them to Rec 21,
    so calling them all "Rec 20 codes" is wrong."""

    uom_canonical: str
    quantity: Decimal | None
    """Base units per package. ``Each`` -> 1, ``Box of 10`` -> 10, bare ``Box`` -> None.

    ``None`` means the container is named but its contents count is not. That is under-specified,
    not wrong, and it must compare as such."""

    is_bulk_container: bool = False


Payload = (
    Quantity
    | tuple  # QUANTITY_SET / RANGE hold tuples of Quantity
    | ThreadSpec
    | IngressSpec
    | MaterialSpec
    | TermSpec
    | PackagingSpec
    | bool
    | Decimal
)


@dataclass(frozen=True, slots=True)
class NormalizedValue:
    """A parsed value. Immutable, and always carries the raw string it came from."""

    kind: Kind
    payload: Any
    raw: str
    """The source string, verbatim. FR-1.1: original strings are preserved without mutation."""

    canonical_text: str = ""
    """A stable, comparable rendering. Two values with the same canonical_text are the same value,
    but the converse does not hold -- ``0.5 in`` and ``12.7 mm`` differ here and are equivalent."""

    grammar_version: str = ""
    """FR-4.5. Recorded on every normalized value so a grammar change is visible in the ledger."""

    parser: str = ""
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.raw:
            raise ValueError("NormalizedValue.raw must retain the source string")
        if not self.grammar_version:
            raise ValueError(
                f"NormalizedValue for {self.raw!r} must record grammar_version (FR-4.5)"
            )


@dataclass(frozen=True, slots=True)
class Refusal:
    """The normalizer declined. This is a first-class outcome, not an error path.

    A ``Refusal`` on either side of a comparison forces abstention. That is the single most
    important false-positive suppressant in the system: the library never guesses in order to have
    something to compare.
    """

    reason: RefusalReason
    raw: str
    detail: str = ""
    attempted: tuple[str, ...] = ()
    """Parser names that were tried and declined -- the debugging surface for a contributor."""

    def __bool__(self) -> bool:
        # Guards against `if normalize(x):` reading as success.
        return False


ParseResult = NormalizedValue | Refusal


@dataclass(frozen=True, slots=True)
class Verdict:
    """The result of comparing two normalized values."""

    relation: Relation
    rationale: str
    """Deterministic, human-readable, and safe to show a reviewer verbatim."""

    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def is_equivalent(self) -> bool:
        return self.relation in EQUIVALENT_RELATIONS


def _plain(d: Decimal | None) -> str:
    """Render a Decimal without exponent notation or gratuitous trailing zeros."""
    if d is None:
        return ""
    s = format(d.normalize(), "f")
    return s
