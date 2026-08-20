"""Stage 4 of the pipeline: units.

A thin, deterministic layer over Pint. Everything here has a knowable right answer, which is
precisely why no model is allowed near it (§3.4): a model that converts inches to millimetres
incorrectly is wrong *plausibly*, and plausible-wrong is unfalsifiable at review time.

Decimal in, Decimal out. Pint is used for the dimensional algebra and the conversion factor; the
arithmetic is done in Decimal so that ``0.5 in`` lands on exactly ``12.7 mm`` and not on
``12.700000000000001``.
"""

from __future__ import annotations

import functools
import re
from decimal import Decimal, InvalidOperation
from importlib import resources
from typing import Any

import pint

__all__ = [
    "DIMENSIONLESS",
    "UnknownUnit",
    "comparison_unit",
    "convert_delta",
    "convert_point",
    "frame",
    "is_affine",
    "parse_unit",
    "registry",
    "same_dimension",
]

GRAMMAR_VERSION = "units/1.0.0"

DIMENSIONLESS = ""

#: Units whose conversion has an offset, so a delta cannot be converted with the same factor.
_AFFINE = {"degC", "degF", "degree_Celsius", "degree_Fahrenheit"}

_IMPERIAL_ROOTS = frozenset(
    {
        "inch", "foot", "yard", "mile", "mil", "thou",
        "pound", "ounce", "ton", "grain", "slug",
        "psi", "pound_force", "pound_force_per_square_inch", "foot_pound",
        "gallon", "quart", "pint", "fluid_ounce",
        "degree_Fahrenheit", "British_thermal_unit", "horsepower",
    }
)


class UnknownUnit(ValueError):
    """The unit string is not in the registry. Extending :mod:`units/industrial.txt` fixes it."""


@functools.cache
def registry() -> pint.UnitRegistry:
    """The single shared registry. Cached because building one costs ~100 ms."""
    ureg = pint.UnitRegistry(autoconvert_offset_to_baseunit=False)
    text = resources.files("errata_valuesem").joinpath("units/industrial.txt").read_text("utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            ureg.define(stripped)
        except Exception as exc:  # pragma: no cover - a bad definition is a build error
            raise RuntimeError(f"units/industrial.txt:{lineno}: {stripped!r}: {exc}") from exc
    return ureg


_UNIT_CLEAN = re.compile(r"\s+")


@functools.cache
def parse_unit(text: str) -> str:
    """Resolve a unit string to its canonical registry name.

    Raises:
        UnknownUnit: when the string is not a unit this registry knows.
    """
    raw = _UNIT_CLEAN.sub(" ", (text or "").strip())
    if not raw:
        return DIMENSIONLESS
    ureg = registry()
    for candidate in (raw, raw.replace(" ", "*"), raw.replace(" ", "")):
        try:
            unit = ureg.Unit(candidate)
        except Exception:
            continue
        return str(unit)
    raise UnknownUnit(f"{text!r} is not a known unit")


def is_affine(unit: str) -> bool:
    return unit in _AFFINE or str(unit) in _AFFINE


@functools.cache
def _dimensionality(unit: str) -> Any:
    """The dimensionality *container*, never its string form.

    Pint renders ``newton * meter`` as ``[mass] * [length] ** 2 / [time] ** 2`` and ``Nm`` as
    ``[length] ** 2 * [mass] / [time] ** 2`` -- the same dimension, two different strings, because
    the terms come out in construction order. Comparing the rendered text made every torque value
    incommensurable with every other torque value and sent them all to the Declined bucket. The
    container compares by content.
    """
    if unit == DIMENSIONLESS:
        return registry().Unit("").dimensionality
    return registry().Unit(unit).dimensionality


def same_dimension(a: str, b: str) -> bool:
    """True when two units measure the same physical quantity, whatever their frame."""
    try:
        return _dimensionality(a) == _dimensionality(b)
    except Exception:
        return False


@functools.cache
def _factor(from_unit: str, to_unit: str) -> Decimal:
    ureg = registry()
    value = ureg.Quantity(1, from_unit).to(to_unit).magnitude
    return Decimal(repr(value))


def convert_point(magnitude: Decimal, from_unit: str, to_unit: str) -> Decimal:
    """Convert a measured point. Handles the affine temperature units correctly."""
    if from_unit == to_unit:
        return magnitude
    if from_unit == DIMENSIONLESS or to_unit == DIMENSIONLESS:
        raise UnknownUnit(f"cannot convert between {from_unit!r} and {to_unit!r}")
    if is_affine(from_unit) or is_affine(to_unit):
        ureg = registry()
        value = ureg.Quantity(float(magnitude), from_unit).to(to_unit).magnitude
        return Decimal(repr(value))
    return _normalize_scale(magnitude * _factor(from_unit, to_unit))


def convert_delta(magnitude: Decimal, from_unit: str, to_unit: str) -> Decimal:
    """Convert a width, tolerance or interval half-span -- never a point.

    ``+/- 5 degC`` is ``+/- 9 degF``, not ``41 degF``. Getting this backwards is the classic
    temperature-tolerance bug, so the two conversions are separate functions rather than a flag.
    """
    if from_unit == to_unit:
        return magnitude
    if is_affine(from_unit) or is_affine(to_unit):
        ureg = registry()
        delta_from = f"delta_{from_unit}" if is_affine(from_unit) else from_unit
        delta_to = f"delta_{to_unit}" if is_affine(to_unit) else to_unit
        value = ureg.Quantity(float(magnitude), delta_from).to(delta_to).magnitude
        return Decimal(repr(value))
    return _normalize_scale(magnitude * _factor(from_unit, to_unit))


def _normalize_scale(value: Decimal) -> Decimal:
    """Trim the float-derived noise that a repr() round-trip can leave behind."""
    try:
        quantized = value.quantize(Decimal("1E-12"))
    except (InvalidOperation, ValueError):
        return value
    normalized = quantized.normalize()
    return normalized if normalized == value or abs(value - normalized) < Decimal("1E-15") else value


@functools.cache
def frame(unit: str) -> str:
    """``metric`` | ``imperial`` | ``dimensionless`` | ``other``.

    Used to distinguish "same fact, different unit system" (resolve silently, §3.3) from a genuine
    disagreement.
    """
    if unit == DIMENSIONLESS:
        return "dimensionless"
    try:
        container = registry().Unit(unit)._units
    except Exception:
        return "other"
    names = {registry().get_name(str(u)) for u in container}
    if names & _IMPERIAL_ROOTS:
        return "imperial"
    return "metric"


def comparison_unit(a: str, b: str) -> str:
    """Pick the frame two values are compared in: the metric side, or ``a`` if both agree.

    Deterministic on purpose. A comparison whose result depends on argument order is not a
    comparison, it is a coin toss with extra steps.
    """
    if a == b:
        return a
    fa, fb = frame(a), frame(b)
    if fa == "metric" and fb != "metric":
        return a
    if fb == "metric" and fa != "metric":
        return b
    return min(a, b)
