"""A minimal, independent UCUM resolver — a second opinion on unit equality.

**Why this exists.** FR-0.1 requires the equivalence suite to be dual-labelled by someone who did
not write the comparator. There is no second labeller available. This is a partial substitute:
for the subset of the suite that turns on a *factual* question -- is 0.5 in the same length as
12.7 mm -- an external, human-curated standard can answer independently, and we can check whether
it agrees with our label.

UCUM (the Unified Code for Units of Measure) is maintained by a standards committee, publishes
exact conversion values, and has nothing to do with this project. If our suite says two values are
equivalent and UCUM's arithmetic says they are not, that is a finding about our suite, arrived at
without our own code being involved in the judgment.

**Deliberately not built on Pint.** `errata_valuesem` uses Pint, so resolving through Pint here
would be asking the same library the same question twice and calling the echo corroboration. This
module reads UCUM's own `ucum-essence.xml` and does its own arithmetic in `Fraction`, so the two
paths share nothing but the answer they are supposed to agree on.

**What it cannot do, stated up front.** UCUM adjudicates whether two quantities are the same
quantity. It has no opinion on whether a difference should be labelled `granularity` rather than
`precision`, or whether an ambiguous pair should be `undetermined`. Those are taxonomy judgments,
they are the harder half of the labelling, and no external dataset encodes them. This closes part
of the FR-0.1 gap and is not a substitute for closing the rest.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

__all__ = [
    "UCUM_PATH",
    "Dimension",
    "UcumNotAvailable",
    "UcumUnit",
    "convert",
    "resolve",
    "ucum_available",
]

NS = "{http://unitsofmeasure.org/ucum-essence}"

#: Where `scripts/fetch_reference_data.sh` puts it. Gitignored (FR-9.5): the repo carries the URL
#: and hash, not the payload.
UCUM_PATH = Path("var/reference/ucum/ucum-essence.xml")

#: Exponents over UCUM's seven base units, in a fixed order.
Dimension = tuple[int, int, int, int, int, int, int]
_BASE_ORDER = ("m", "s", "g", "rad", "K", "C", "cd")


class UcumNotAvailable(RuntimeError):
    """Raised when the essence file has not been fetched.

    A distinct type so callers can skip corroboration cleanly. Silently returning "cannot judge"
    would make a missing file indistinguishable from a genuinely unjudgeable pair, which is
    exactly the sort of quiet degradation this project exists to object to.
    """


@dataclass(frozen=True, slots=True)
class UcumUnit:
    """A unit reduced to base dimensions and a scale factor.

    ``offset`` is non-zero only for the affine temperature scales, where conversion is
    ``value * factor + offset`` rather than a bare multiplication. Keeping it explicit means
    degrees Celsius cannot be quietly treated as multiplicative -- the mistake that makes
    ``0 degC == 0 degF`` look true.
    """

    code: str
    name: str
    dimension: Dimension
    factor: Fraction
    offset: Fraction = Fraction(0)

    @property
    def is_affine(self) -> bool:
        return self.offset != 0


#: Offsets, in kelvin, for UCUM's affine temperature scales.
#:
#: Celsius:    T_K = T_C + 273.15                     -> offset 273.15
#: Fahrenheit: T_K = (T_F + 459.67) x 5/9             -> offset 459.67 x 5/9 = 2298.35/9
#:
#: Written as exact Fractions. These are the two constants that decide whether `0 degC` and
#: `32 degF` corroborate as equal, and a float here would make that turn on rounding.
_AFFINE_OFFSETS_K: dict[str, Fraction] = {
    "Cel": Fraction(5463, 20),
    "degF": Fraction(45967, 100) * Fraction(5, 9),
}

_PREFIXES: dict[str, Fraction] = {}
_UNITS: dict[str, UcumUnit] = {}


def ucum_available() -> bool:
    return UCUM_PATH.is_file()


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, Fraction], dict[str, UcumUnit]]:
    if not ucum_available():
        raise UcumNotAvailable(
            f"{UCUM_PATH} is not present. Run scripts/fetch_reference_data.sh -- the repository "
            "carries UCUM's URL and sha256, not the file itself (FR-9.5)."
        )
    root = ET.parse(UCUM_PATH).getroot()

    prefixes: dict[str, Fraction] = {}
    for node in root.findall(NS + "prefix"):
        value = node.find(NS + "value")
        code = node.get("Code")
        if code and value is not None and value.get("value"):
            prefixes[code] = Fraction(_decimal(value.get("value", "1")))

    units: dict[str, UcumUnit] = {}

    # The seven base units define the dimension space.
    for index, node in enumerate(root.findall(NS + "base-unit")):
        code = node.get("Code") or ""
        dim = [0] * 7
        dim[index] = 1
        units[code] = UcumUnit(
            code=code,
            name=(node.findtext(NS + "name") or code),
            dimension=tuple(dim),  # type: ignore[arg-type]
            factor=Fraction(1),
        )

    # Derived units are defined against other units, sometimes several links deep. Resolve by
    # repeated passes rather than recursion: the dependency graph is shallow, and a fixed-point
    # loop cannot blow the stack on a malformed file.
    pending = list(root.findall(NS + "unit"))
    for _ in range(12):
        remaining = []
        for node in pending:
            code = node.get("Code") or ""
            value = node.find(NS + "value")
            if value is None:
                continue
            offset = Fraction(0)
            function = value.find(NS + "function")

            if function is not None:
                # A "special" unit. Its `value/@Unit` reads `cel(1 K)` -- a function expression,
                # not a unit expression -- so the definition has to come from the function child:
                # name, a magnitude, and the unit it is expressed against.
                #
                # Only the two affine temperature scales are handled. Everything else special in
                # UCUM (log scales, arbitrary units) is skipped rather than approximated: a
                # corroborator that quietly linearises a decibel would be worse than one that
                # declines to judge it.
                name = function.get("name", "")
                if name not in _AFFINE_OFFSETS_K:
                    continue
                resolved = _resolve_expression(function.get("Unit", "K"), prefixes, units)
                if resolved is None:
                    remaining.append(node)
                    continue
                dimension, scale = resolved
                magnitude = Fraction(_decimal(function.get("value", "1")))
                offset = _AFFINE_OFFSETS_K[name]
            else:
                resolved = _resolve_expression(value.get("Unit", "1"), prefixes, units)
                if resolved is None:
                    remaining.append(node)
                    continue
                dimension, scale = resolved
                magnitude = Fraction(_decimal(value.get("value", "1")))
            units[code] = UcumUnit(
                code=code,
                name=(node.findtext(NS + "name") or code),
                dimension=dimension,
                factor=magnitude * scale,
                offset=offset,
            )
        if not remaining or len(remaining) == len(pending):
            break
        pending = remaining

    return prefixes, units


def _decimal(text: str) -> Fraction:
    """UCUM writes values as decimals or as ``254e-2``. Fraction keeps them exact."""
    text = (text or "1").strip()
    if not text:
        return Fraction(1)
    if "e" in text.lower():
        mantissa, _, exponent = text.lower().partition("e")
        return Fraction(mantissa or "1") * Fraction(10) ** int(exponent)
    return Fraction(text)


_TERM = re.compile(r"([A-Za-z_\[\]'%]+)(-?\d+)?")


def _resolve_expression(
    expression: str, prefixes: dict[str, Fraction], units: dict[str, UcumUnit]
) -> tuple[Dimension, Fraction] | None:
    """Reduce a UCUM expression like ``[lbf_av]/[in_i]2`` to a dimension and a scale.

    Returns None when any component is not yet resolved, which is what drives the fixed-point
    loop above.
    """
    expression = (expression or "1").strip()
    if expression in {"1", ""}:
        return (0, 0, 0, 0, 0, 0, 0), Fraction(1)

    dimension = [0] * 7
    scale = Fraction(1)
    # Split on . and / keeping the operator, so division inverts what follows.
    parts = re.split(r"([./])", expression)
    sign = 1
    for part in parts:
        if part == "/":
            sign = -1
            continue
        if part == ".":
            sign = 1
            continue
        if not part:
            continue
        match = _TERM.fullmatch(part)
        if match is None:
            if part.isdigit():
                scale *= Fraction(part) ** sign
                continue
            return None
        code, exponent_text = match.group(1), match.group(2)
        exponent = int(exponent_text) if exponent_text else 1
        resolved = _lookup(code, prefixes, units)
        if resolved is None:
            return None
        unit_dimension, unit_scale = resolved
        for i in range(7):
            dimension[i] += sign * exponent * unit_dimension[i]
        scale *= unit_scale ** (sign * exponent)
    return tuple(dimension), scale  # type: ignore[return-value]


def _lookup(
    code: str, prefixes: dict[str, Fraction], units: dict[str, UcumUnit]
) -> tuple[Dimension, Fraction] | None:
    unit = units.get(code)
    if unit is not None:
        return unit.dimension, unit.factor
    # Try a metric prefix, longest first so "da" beats "d".
    for length in (2, 1):
        if len(code) > length:
            prefix, rest = code[:length], code[length:]
            if prefix in prefixes and rest in units:
                base = units[rest]
                return base.dimension, base.factor * prefixes[prefix]
    return None


def resolve(code: str) -> UcumUnit | None:
    """A UCUM unit code, with metric prefixes applied, or None if unknown."""
    prefixes, units = _load()
    unit = units.get(code)
    if unit is not None:
        return unit
    for length in (2, 1):
        if len(code) > length:
            prefix, rest = code[:length], code[length:]
            if prefix in prefixes and rest in units:
                base = units[rest]
                return UcumUnit(
                    code=code,
                    name=f"{prefix}{base.name}",
                    dimension=base.dimension,
                    factor=base.factor * prefixes[prefix],
                    offset=base.offset,
                )
    resolved = _resolve_expression(code, prefixes, units)
    if resolved is None:
        return None
    dimension, scale = resolved
    return UcumUnit(code=code, name=code, dimension=dimension, factor=scale)


def convert(magnitude: Fraction, source: UcumUnit, target: UcumUnit) -> Fraction | None:
    """Exact conversion, or None when the dimensions differ.

    Exact because it is all `Fraction`: a corroboration that disagreed with the suite because of
    a float rounding artefact would be worse than no corroboration at all.
    """
    if source.dimension != target.dimension:
        return None
    in_base = magnitude * source.factor + source.offset
    return (in_base - target.offset) / target.factor
