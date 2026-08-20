"""Stage 4b: what a written number actually claims.

``10 mm`` and ``10.0 mm`` are different assertions. The first claims a value between 9.5 and 10.5;
the second claims 9.95 to 10.05. Comparing them as floats loses that, and losing it is how an
auditor manufactures a disagreement out of a rounding convention.

Two separate ideas live here and must not be conflated:

* **Implied precision** -- how many digits the source bothered to write. Rounding differences at
  this level are *not* findings. Flagging them would bury the reviewer.
* **Explicit tolerance** -- ``10 +/-0.2 mm``. A dropped explicit tolerance *is* a finding
  (§3.3 precision mismatch), because it is information the manufacturer published and the catalog
  discarded.
"""

from __future__ import annotations

from decimal import Decimal

from .model import Interval, Quantity
from .unitreg import DIMENSIONLESS, convert_delta, convert_point

__all__ = ["implied_half_ulp", "interval_in", "interval_of", "intervals_overlap"]

GRAMMAR_VERSION = "precision/1.0.0"

_ZERO = Decimal(0)


def implied_half_ulp(magnitude: Decimal) -> Decimal:
    """Half the unit in the last written place.

    ``Decimal("10")`` -> ``0.5``; ``Decimal("10.0")`` -> ``0.05``; ``Decimal("0.50")`` -> ``0.005``.

    Trailing zeros carry information here, which is why magnitudes are kept as the Decimal parsed
    from the source string rather than being normalized on the way in.
    """
    exponent = magnitude.as_tuple().exponent
    if not isinstance(exponent, int):  # NaN / Infinity
        return _ZERO
    return Decimal(1).scaleb(exponent) / 2


def interval_of(quantity: Quantity) -> Interval:
    """The closed interval a quantity actually asserts, in its own unit."""
    nominal = quantity.magnitude
    if quantity.tolerance is not None:
        lo, hi = quantity.tolerance.absolute_bounds(nominal)
        return Interval(lo=min(lo, hi), hi=max(lo, hi), unit=quantity.unit)
    if quantity.exact:
        return Interval(lo=nominal, hi=nominal, unit=quantity.unit)
    half = implied_half_ulp(nominal)
    return Interval(lo=nominal - half, hi=nominal + half, unit=quantity.unit)


def interval_in(quantity: Quantity, unit: str) -> Interval:
    """The asserted interval, expressed in ``unit``.

    Endpoints are converted as points and the affine temperature units are handled by
    :func:`~errata_valuesem.unitreg.convert_point`, so ``0 +/- 5 degC`` becomes ``32 +/- 9 degF``
    and not ``32 +/- 41 degF``.
    """
    base = interval_of(quantity)
    if base.unit == unit or quantity.unit == DIMENSIONLESS == unit:
        return base
    lo = convert_point(base.lo, base.unit, unit)
    hi = convert_point(base.hi, base.unit, unit)
    return Interval(lo=min(lo, hi), hi=max(lo, hi), unit=unit)


def width_in(quantity: Quantity, unit: str) -> Decimal:
    """The width of the asserted interval in ``unit``, converted as a delta."""
    base = interval_of(quantity)
    if base.unit == unit:
        return base.width
    return abs(convert_delta(base.width, base.unit, unit))


def intervals_overlap(a: Interval, b: Interval) -> bool:
    """Overlap, not containment.

    Overlap is the permissive choice and it is deliberate: the cost of a missed error is one bad
    record, and the cost of a false accusation is the reviewer's trust in every subsequent screen
    (§8.1). When the two readings of a number cannot be told apart at the precision the sources
    chose to write, the honest answer is that they agree.
    """
    if a.unit != b.unit:
        raise ValueError(f"intervals must share a unit: {a.unit!r} vs {b.unit!r}")
    return a.lo <= b.hi and b.lo <= a.hi
