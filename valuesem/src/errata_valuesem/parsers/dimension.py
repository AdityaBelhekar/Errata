"""Magnitudes: quantities, tolerances, ranges and alternative-value sets.

Two decisions in this module carry most of the false-positive risk in the whole library.

**Trailing zeros are kept.** ``Decimal("10.0")`` is not ``Decimal("10")``, because the number of
digits the source chose to write is the source's claim about its own precision, and that claim is
what :mod:`~errata_valuesem.precision` reasons over.

**A bare dimensionless integer is exact.** ``2`` poles is two poles, not "between 1.5 and 2.5".
A dimensionless measurement would have been written with a decimal point.
"""

from __future__ import annotations

import functools
import re
from decimal import Decimal, InvalidOperation
from importlib import resources
from typing import Any

from lark import Lark, Tree
from lark.exceptions import LarkError
from lark.lexer import Token

from ..model import Kind, NormalizedValue, Quantity, Refusal, RefusalReason, Tolerance
from ..unitreg import DIMENSIONLESS, UnknownUnit, parse_unit

__all__ = ["GRAMMAR_VERSION", "PREFILTER", "parse"]

GRAMMAR_VERSION = "dimension/1.1.0"
PARSER_NAME = "dimension"

#: Anything with a digit in it could be a magnitude.
PREFILTER = re.compile(r"\d")

#: Denominators that mark an inch fraction rather than a set of alternative values.
#: ``3/8`` is three eighths; ``230/400`` is two voltages.
_FRACTION_DENOMINATORS = frozenset({Decimal(2), Decimal(3), Decimal(4), Decimal(8),
                                    Decimal(16), Decimal(32), Decimal(64)})

_CMP_TO_QUALIFIER = {"<": "max", "<=": "max", ">": "min", ">=": "min"}

_TOL_SYMMETRIC = re.compile(r"^\+/-\s*(?P<mag>\d+(?:\.\d+)?)\s*(?P<pct>%?)$")
_TOL_ASYMMETRIC = re.compile(
    r"^\+\s*(?P<plus>\d+(?:\.\d+)?)\s*(?P<ppct>%?)\s*/?\s*-\s*(?P<minus>\d+(?:\.\d+)?)\s*(?P<mpct>%?)$"
)


@functools.cache
def _grammar() -> Lark:
    text = resources.files("errata_valuesem").joinpath("grammars/dimension.lark").read_text("utf-8")
    return Lark(text, start="start", parser="earley", maybe_placeholders=False)


def parse(text: str, ctx: dict[str, Any] | None = None) -> NormalizedValue | Refusal | None:
    if not PREFILTER.search(text):
        return None
    try:
        tree = _grammar().parse(text)
    except LarkError:
        return None  # not a magnitude; let another family try
    try:
        if tree.data == "rangev":
            return _build_range(tree, text)
        if tree.data == "tolv":
            return _build_tolerance(tree, text)
        if tree.data in {"plainv", "bare"}:
            return _build_plain(tree, text)
        return None
    except UnknownUnit as exc:
        return Refusal(
            reason=RefusalReason.UNKNOWN_UNIT,
            raw=text,
            detail=str(exc),
            attempted=(PARSER_NAME,),
        )
    except (InvalidOperation, ArithmeticError, ValueError) as exc:
        return Refusal(
            reason=RefusalReason.MALFORMED,
            raw=text,
            detail=f"magnitude did not evaluate: {exc}",
            attempted=(PARSER_NAME,),
        )


# ------------------------------------------------------------------------------------------------
# Builders
# ------------------------------------------------------------------------------------------------


def _build_plain(tree: Tree, raw: str) -> NormalizedValue | Refusal:
    qualifier = _qualifier_of(tree)
    unit = _unit_at(tree, 0)
    magnitudes, is_set, notes = _magnitudes_of(_signed_children(tree)[0], unit)

    if is_set:
        payload = tuple(
            _quantity(m, unit, qualifier=qualifier, exact=exact) for m, exact in magnitudes
        )
        return NormalizedValue(
            kind=Kind.QUANTITY_SET,
            payload=payload,
            raw=raw,
            canonical_text=" | ".join(_render(q) for q in payload),
            grammar_version=GRAMMAR_VERSION,
            parser=PARSER_NAME,
            notes=tuple(notes),
        )

    magnitude, exact = magnitudes[0]
    quantity = _quantity(magnitude, unit, qualifier=qualifier, exact=exact)
    return NormalizedValue(
        kind=Kind.QUANTITY,
        payload=quantity,
        raw=raw,
        canonical_text=_render(quantity),
        grammar_version=GRAMMAR_VERSION,
        parser=PARSER_NAME,
        notes=tuple(notes),
    )


def _build_tolerance(tree: Tree, raw: str) -> NormalizedValue | Refusal:
    unit = _unit_at(tree, 0) or _unit_at(tree, 1)
    signed = _signed_children(tree)[0]
    magnitudes, is_set, notes = _magnitudes_of(signed, unit)
    if is_set:
        return Refusal(
            reason=RefusalReason.MALFORMED,
            raw=raw,
            detail="a tolerance cannot attach to a set of alternative values",
            attempted=(PARSER_NAME,),
        )

    token = _token(tree, "TOL")
    tolerance = _parse_tolerance(re.sub(r"\s+", "", token or ""))
    if tolerance is None:
        return Refusal(
            reason=RefusalReason.MALFORMED,
            raw=raw,
            detail=f"tolerance {token!r} did not parse",
            attempted=(PARSER_NAME,),
        )

    magnitude, _exact = magnitudes[0]
    quantity = Quantity(
        magnitude=magnitude,
        unit=unit,
        tolerance=tolerance,
        qualifier=_qualifier_of(tree),
    )
    return NormalizedValue(
        kind=Kind.QUANTITY,
        payload=quantity,
        raw=raw,
        canonical_text=_render(quantity),
        grammar_version=GRAMMAR_VERSION,
        parser=PARSER_NAME,
        notes=tuple(notes),
    )


def _build_range(tree: Tree, raw: str) -> NormalizedValue | Refusal:
    dash_form = any(isinstance(c, Token) and c.type == "DASH" for c in tree.children)
    if dash_form:
        nums = [Decimal(str(c)) for c in tree.children if isinstance(c, Token) and c.type == "NUM"]
        lo_mag, hi_mag = nums[0], nums[1]
        lo_unit = hi_unit = _unit_at(tree, 0)
    else:
        signeds = _signed_children(tree)
        units = _split_units_around_separator(tree)
        lo_unit, hi_unit = units
        lo_mag = _single_magnitude(signeds[0])
        hi_mag = _single_magnitude(signeds[1])

    unit = hi_unit or lo_unit
    if lo_unit and hi_unit and lo_unit != hi_unit:
        return Refusal(
            reason=RefusalReason.MALFORMED,
            raw=raw,
            detail=f"range endpoints carry different units ({lo_unit} and {hi_unit})",
            attempted=(PARSER_NAME,),
        )
    if lo_mag > hi_mag:
        return Refusal(
            reason=RefusalReason.MALFORMED,
            raw=raw,
            detail=f"range runs backwards: {lo_mag} .. {hi_mag}",
            attempted=(PARSER_NAME,),
        )

    payload = (
        _quantity(lo_mag, unit, qualifier=""),
        _quantity(hi_mag, unit, qualifier=""),
    )
    return NormalizedValue(
        kind=Kind.RANGE,
        payload=payload,
        raw=raw,
        canonical_text=f"{_render(payload[0])} .. {_render(payload[1])}",
        grammar_version=GRAMMAR_VERSION,
        parser=PARSER_NAME,
    )


# ------------------------------------------------------------------------------------------------
# Pieces
# ------------------------------------------------------------------------------------------------


def _quantity(
    magnitude: Decimal, unit: str, *, qualifier: str = "", exact: bool = False
) -> Quantity:
    integral = magnitude == magnitude.to_integral_value() and magnitude.as_tuple().exponent >= 0
    return Quantity(
        magnitude=magnitude,
        unit=unit,
        qualifier=qualifier,
        exact=exact or (unit == DIMENSIONLESS and integral),
    )


def _magnitudes_of(
    signed: Tree, unit: str
) -> tuple[list[tuple[Decimal, bool]], bool, list[str]]:
    """Return ``([(magnitude, exact)], is_set, notes)`` for one ``signed`` subtree."""
    notes: list[str] = []
    sign = -1 if _token(signed, "SIGN") == "-" else 1
    magnitude_tree = _subtree(signed, "magnitude")
    assert magnitude_tree is not None

    mixed = _token(magnitude_tree, "MIXED")
    if mixed is not None:
        value = _mixed_to_decimal(mixed)
        return [(sign * value, True)], False, notes

    slashes = _token(magnitude_tree, "SLASHNUMS")
    if slashes is not None:
        parts = [Decimal(p) for p in slashes.split("/")]
        if _looks_like_fraction(parts):
            value = parts[0] / parts[1]
            notes.append(f"{slashes} read as the fraction {parts[0]}/{parts[1]}")
            return [(sign * value, True)], False, notes
        notes.append(
            f"{slashes} read as {len(parts)} alternative values, not a fraction "
            "(denominator is not a binary inch subdivision)"
        )
        return [(sign * p, False) for p in parts], True, notes

    num = _token(magnitude_tree, "NUM")
    return [(sign * Decimal(str(num)), False)], False, notes


def _single_magnitude(signed: Tree) -> Decimal:
    magnitudes, is_set, _ = _magnitudes_of(signed, DIMENSIONLESS)
    if is_set:
        raise ValueError("a range endpoint cannot itself be a set of values")
    return magnitudes[0][0]


def _looks_like_fraction(parts: list[Decimal]) -> bool:
    if len(parts) != 2:
        return False
    numerator, denominator = parts
    if denominator == 0:
        return False
    return denominator in _FRACTION_DENOMINATORS and numerator < denominator


def _mixed_to_decimal(text: str) -> Decimal:
    whole, _, frac = re.sub(r"\s+", " ", text.strip()).partition(" ")
    numerator, _, denominator = frac.partition("/")
    return Decimal(whole) + Decimal(numerator) / Decimal(denominator)


def _parse_tolerance(text: str) -> Tolerance | None:
    symmetric = _TOL_SYMMETRIC.match(text)
    if symmetric:
        magnitude = Decimal(symmetric.group("mag"))
        return Tolerance(plus=magnitude, minus=magnitude, relative=bool(symmetric.group("pct")))
    asymmetric = _TOL_ASYMMETRIC.match(text)
    if asymmetric:
        relative = bool(asymmetric.group("ppct") or asymmetric.group("mpct"))
        return Tolerance(
            plus=Decimal(asymmetric.group("plus")),
            minus=Decimal(asymmetric.group("minus")),
            relative=relative,
        )
    return None


def _qualifier_of(tree: Tree) -> str:
    qual = _token(tree, "QUAL")
    if qual:
        text = str(qual)
        return text.upper() if text.upper() in {"AC", "DC", "AC/DC", "RMS"} else text.lower()
    cmp_token = _token(tree, "CMP")
    if cmp_token:
        return _CMP_TO_QUALIFIER.get(str(cmp_token), "")
    return ""


def _unit_at(tree: Tree, index: int) -> str:
    units = [c for c in tree.children if isinstance(c, Tree) and c.data == "unit"]
    if index >= len(units):
        return DIMENSIONLESS
    return parse_unit(str(units[index].children[0]))


def _split_units_around_separator(tree: Tree) -> tuple[str, str]:
    before: str = DIMENSIONLESS
    after: str = DIMENSIONLESS
    seen_separator = False
    for child in tree.children:
        if isinstance(child, Token) and child.type == "RANGESEP":
            seen_separator = True
        elif isinstance(child, Tree) and child.data == "unit":
            resolved = parse_unit(str(child.children[0]))
            if seen_separator:
                after = resolved
            else:
                before = resolved
    return before, after


def _signed_children(tree: Tree) -> list[Tree]:
    return [c for c in tree.children if isinstance(c, Tree) and c.data == "signed"]


def _subtree(tree: Tree, data: str) -> Tree | None:
    for child in tree.children:
        if isinstance(child, Tree) and child.data == data:
            return child
    return None


def _token(tree: Tree, type_: str) -> str | None:
    for child in tree.children:
        if isinstance(child, Token) and child.type == type_:
            return str(child)
    return None


def _render(quantity: Quantity) -> str:
    text = format(quantity.magnitude, "f")
    if quantity.tolerance is not None:
        tol = quantity.tolerance
        suffix = "%" if tol.relative else ""
        if tol.plus == tol.minus:
            text += f" +/-{format(tol.plus, 'f')}{suffix}"
        else:
            text += f" +{format(tol.plus, 'f')}{suffix}/-{format(tol.minus, 'f')}{suffix}"
    if quantity.unit:
        text += f" {quantity.unit}"
    if quantity.qualifier:
        text += f" {quantity.qualifier}"
    return text
