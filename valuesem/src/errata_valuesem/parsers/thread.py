"""Screw threads.

The interesting work is not the parse, it is the *completion*: filling in the pitch that the source
omitted, from ISO 261 or ASME B1.1. Without that step ``M8`` and ``M8x1.25`` look like different
values, and flagging the most common fastener designation in the world against itself is how an
auditor loses a pilot in the first session.
"""

from __future__ import annotations

import functools
import re
from decimal import Decimal
from importlib import resources
from typing import Any

from lark import Lark, Tree
from lark.exceptions import LarkError
from lark.lexer import Token

from .. import tables
from ..model import Kind, NormalizedValue, Refusal, RefusalReason, ThreadSpec

__all__ = ["GRAMMAR_VERSION", "PREFILTER", "parse"]

GRAMMAR_VERSION = "thread/1.1.0"
PARSER_NAME = "thread"

#: Stage 2. Cheap enough to run on every value, specific enough that "63 A" never reaches the
#: grammar.
PREFILTER = re.compile(
    r"""
    (?: \bM\s?\d+(?:\s*[xX*]\s*\d)?            # M8, M8x1.25
      | \bUN[CFEJSR]                           # UNC, UNF, UNEF, UNJC
      | \bNPTF? | \bNPSM? | \bBSPP? | \bBSPT   # pipe series
      | \bRp?\s*\d+\s*/                        # Rp 1/2, R 1/2
      | \bG\s*\d+\s*/                          # G1/2
      | \#\s?\d{1,2}\s*-\s*\d                  # #10-24
      | \bNo\.?\s?\d{1,2}\s*-\s*\d             # No. 10-24
      | \b\d+\s*/\s*\d+\s*-\s*\d               # 3/8-16
      | \bthread
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_METRIC_TOLERANCE_CLASS = re.compile(r"^[1-9][ghefGHEF]", re.ASCII)


@functools.cache
def _grammar() -> Lark:
    text = resources.files("errata_valuesem").joinpath("grammars/thread.lark").read_text("utf-8")
    return Lark(text, start="start", parser="earley", maybe_placeholders=False)


def parse(text: str, ctx: dict[str, Any] | None = None) -> NormalizedValue | Refusal | None:
    if not PREFILTER.search(text):
        return None
    try:
        tree = _grammar().parse(text)
    except LarkError as exc:
        return Refusal(
            reason=RefusalReason.MALFORMED,
            raw=text,
            detail=f"looks like a thread designation but does not parse: {_first_line(exc)}",
            attempted=(PARSER_NAME,),
        )

    builder = {"metric": _build_metric, "unified": _build_unified, "pipe": _build_pipe}
    build = builder.get(tree.data)
    if build is None:  # pragma: no cover - grammar and builders are kept in step by tests
        return Refusal(
            reason=RefusalReason.MALFORMED,
            raw=text,
            detail=f"unhandled thread form {tree.data!r}",
            attempted=(PARSER_NAME,),
        )
    spec, notes = build(tree)
    return NormalizedValue(
        kind=Kind.THREAD,
        payload=spec,
        raw=text,
        canonical_text=spec.designation,
        grammar_version=GRAMMAR_VERSION,
        parser=PARSER_NAME,
        notes=tuple(notes),
    )


# ------------------------------------------------------------------------------------------------
# Builders
# ------------------------------------------------------------------------------------------------


#: The largest pitch listed anywhere in ISO 261:1998 Table 2, at M125 and M130.
#:
#: CORRECTED 2026-08-19 (P1 task 1.1). This was 6 mm, with the comment "the largest pitch anywhere
#: in the ISO 261 metric series is 6 mm (at M64 and M68)". That is false, and the standard was
#: opened to establish it: 6 mm is the largest *coarse* pitch, and above M68 Table 2 lists no
#: coarse pitch at all while continuing to list fine pitches up to 8 mm. The consequence was that
#: ``M125x8`` -- a valid, standard designation -- had its pitch silently discarded as a "length"
#: and came out as M125 with no pitch at all.
#:
#: The same false premise was found in two suite citations during the same audit. One belief,
#: written down twice, wrong in both places, and neither copy could catch the other.
MAX_ISO_METRIC_PITCH_MM = Decimal("8")


def _max_pitch_for(diameter: Decimal) -> Decimal:
    """The largest number that could legitimately be a pitch at this diameter.

    A second number in ``M8x40`` is either a pitch or a fastener LENGTH in mm -- the
    ``M8x1.25x40`` form with the pitch omitted, which is how a great many catalogs write it.
    Reading it as a pitch turned ``M8x40`` and ``M8x1.25`` into a contradiction between a bolt
    and itself.

    A single global ceiling gets this wrong in both directions. At 6 mm it discarded the real
    8 mm pitches; at 8 mm it would read the 8 in ``M6x8`` -- an 8 mm long M6 screw, one of the
    commonest fasteners there is -- as a pitch M6 cannot have.

    So the ceiling is per-diameter, on the standard's own authority. ISO 261:1998 clause 5.2:
    "It shall be understood that the 'coarse' pitches are the largest metric pitches used in
    current practice." Where the diameter has a coarse pitch, that pitch IS the maximum. Above
    M68, where Table 2 lists no coarse pitch, fall back to the largest pitch in the table.
    """
    coarse = tables.coarse_pitch_for(diameter)
    return coarse if coarse is not None else MAX_ISO_METRIC_PITCH_MM


def _build_metric(tree: Tree) -> tuple[ThreadSpec, list[str]]:
    notes: list[str] = []
    nums = _tokens(tree, "NUM")
    diameter = Decimal(nums[0])
    pitch: Decimal | None = Decimal(nums[1]) if len(nums) > 1 else None
    inferred = False

    ceiling = _max_pitch_for(diameter)
    if pitch is not None and pitch > ceiling:
        notes.append(
            f"{_plain(pitch)} exceeds the largest ISO 261 pitch available at "
            f"M{_plain(diameter)} ({_plain(ceiling)} mm), so it is read as a length in mm, not a "
            f"pitch; the thread is completed from the coarse series instead"
        )
        pitch = None

    if pitch is None:
        table_pitch = tables.coarse_pitch_for(diameter)
        if table_pitch is not None:
            pitch = table_pitch
            inferred = True
            notes.append(
                f"pitch {pitch} mm supplied from the ISO 261 coarse series for M{_plain(diameter)}"
            )
        else:
            notes.append(
                f"M{_plain(diameter)} is not an ISO 261 standard diameter; pitch left unknown "
                "rather than guessed"
            )
    else:
        coarse = tables.coarse_pitch_for(diameter)
        fine = tables.ISO_FINE_PITCHES_MM.get(diameter.normalize(), ())
        if coarse is not None and pitch != coarse and pitch not in fine:
            notes.append(
                f"pitch {_plain(pitch)} mm is neither the coarse ({_plain(coarse)}) nor a listed "
                f"fine pitch for M{_plain(diameter)}"
            )

    mclass = _subtree_token(tree, "mclass", "MCLASS")
    hand = _subtree_token(tree, "hand", "HAND")

    spec = ThreadSpec(
        system="metric",
        nominal_mm=diameter,
        nominal_designation=f"M{_plain(diameter)}",
        pitch_mm=pitch,
        series="coarse" if inferred or (pitch is not None and pitch == tables.coarse_pitch_for(diameter)) else "fine",
        tolerance_class=mclass or "",
        left_hand=_is_left_hand(hand),
        pitch_inferred=inferred,
    )
    return spec, notes


def _build_unified(tree: Tree) -> tuple[ThreadSpec, list[str]]:
    notes: list[str] = []
    designation = _normalize_size(_subtree_text(tree, "usize"))
    tpi_tokens = [t for t in tree.children if isinstance(t, Token) and t.type == "NUM"]
    tpi: Decimal | None = Decimal(tpi_tokens[0]) if tpi_tokens else None
    series = (_subtree_token(tree, "userseries", "UNSERIES") or "").upper()
    uclass = _subtree_token(tree, "uclass", "UNCLASS") or ""

    if tpi is None and series:
        looked_up = tables.series_tpi_for(series, designation)
        if looked_up is not None:
            tpi = looked_up
            notes.append(f"{_plain(tpi)} TPI supplied from the ASME B1.1 {series} series")
        else:
            notes.append(f"{designation} is not a listed size in the {series} series")
    elif tpi is not None and not series:
        inferred_series = tables.infer_unified_series(designation, tpi)
        if inferred_series:
            series = inferred_series
            notes.append(f"series read as {series} from the {designation}-{_plain(tpi)} pairing")
        else:
            notes.append(
                f"{designation}-{_plain(tpi)} matches no standard unified series; left unnamed"
            )
    elif tpi is not None and series:
        expected = tables.series_tpi_for(series, designation)
        if expected is not None and expected != tpi:
            notes.append(
                f"stated {_plain(tpi)} TPI disagrees with the {series} table value "
                f"({_plain(expected)}) for {designation}"
            )

    nominal_in = _designation_to_inches(designation)
    spec = ThreadSpec(
        system="unified",
        nominal_mm=tables.inch_to_mm(nominal_in) if nominal_in is not None else None,
        nominal_designation=designation,
        tpi=tpi,
        series=series,
        tolerance_class=uclass,
        left_hand=_is_left_hand(_subtree_token(tree, "hand", "HAND")),
        pitch_inferred=bool(tpi_tokens) is False and tpi is not None,
    )
    return spec, notes


def _build_pipe(tree: Tree) -> tuple[ThreadSpec, list[str]]:
    notes: list[str] = []
    prefix = (_token(tree, "PIPESERIES") or "").upper()
    meta = tables.PIPE_SERIES.get(prefix, {})
    designation = _normalize_size(_subtree_text(tree, "psize"))
    tpi_tokens = [t for t in tree.children if isinstance(t, Token) and t.type == "NUM"]
    tpi: Decimal | None = Decimal(tpi_tokens[0]) if tpi_tokens else None

    table = meta.get("tpi") or {}
    if tpi is None:
        looked_up = table.get(designation) if isinstance(table, dict) else None
        if looked_up is not None:
            tpi = looked_up
            notes.append(f"{_plain(tpi)} TPI supplied from {meta.get('standard', prefix)}")
    else:
        expected = table.get(designation) if isinstance(table, dict) else None
        if expected is not None and expected != tpi:
            notes.append(
                f"stated {_plain(tpi)} TPI disagrees with {meta.get('standard', prefix)} "
                f"({_plain(expected)}) for {designation}"
            )

    spec = ThreadSpec(
        system=str(meta.get("system", "pipe")),
        nominal_designation=designation,
        tpi=tpi,
        series=prefix,
        tolerance_class=_subtree_token(tree, "pipeclass", "PIPECLASS") or "",
    )
    if meta.get("tapered"):
        notes.append(f"{prefix} is a tapered thread ({meta.get('standard', '')})".strip())
    return spec, notes


# ------------------------------------------------------------------------------------------------
# Tree helpers
# ------------------------------------------------------------------------------------------------


def _tokens(tree: Tree, type_: str) -> list[str]:
    return [str(t) for t in tree.children if isinstance(t, Token) and t.type == type_]


def _token(tree: Tree, type_: str) -> str | None:
    found = _tokens(tree, type_)
    return found[0] if found else None


def _subtree(tree: Tree, data: str) -> Tree | None:
    for child in tree.children:
        if isinstance(child, Tree) and child.data == data:
            return child
    return None


def _subtree_token(tree: Tree, data: str, type_: str) -> str | None:
    sub = _subtree(tree, data)
    return _token(sub, type_) if sub is not None else None


def _subtree_text(tree: Tree, data: str) -> str:
    sub = _subtree(tree, data)
    if sub is None:
        return ""
    return " ".join(str(t) for t in sub.children if isinstance(t, Token))


#: Decimal spellings of the fractional inch designations used by the pipe and unified tables.
#: Catalogs write "0.5 NPT" and datasheets write "1/2 NPT" for one size; the tables are keyed on
#: the fractional form, so a decimal spelling missed every lookup and left TPI unknown -- which the
#: comparator then read as a genuine disagreement rather than as two spellings of one designation.
#: Only exact, unambiguous equivalents belong here; a decimal that is not a listed size must stay
#: unmatched so the parser reports it rather than rounding it onto a neighbouring size.
_DECIMAL_TO_FRACTION_IN: dict[str, str] = {
    "0.0625": "1/16", "0.125": "1/8", "0.1875": "3/16", "0.25": "1/4", "0.3125": "5/16",
    "0.375": "3/8", "0.4375": "7/16", "0.5": "1/2", "0.5625": "9/16", "0.625": "5/8",
    "0.6875": "11/16", "0.75": "3/4", "0.8125": "13/16", "0.875": "7/8", "0.9375": "15/16",
    "1.125": "1 1/8", "1.25": "1 1/4", "1.375": "1 3/8", "1.5": "1 1/2", "1.75": "1 3/4",
    "2.25": "2 1/4", "2.5": "2 1/2", "2.75": "2 3/4", "3.5": "3 1/2",
}


def _normalize_size(text: str) -> str:
    """``No. 10`` and ``# 10`` both become ``#10``; ``1  1/2`` becomes ``1 1/2``.

    A decimal inch spelling is folded onto its fractional equivalent (``0.5`` -> ``1/2``) so that
    table lookups keyed on fractions succeed. Trailing zeros are trimmed first, so ``0.50`` and
    ``.5`` reach the same key as ``0.5``.
    """
    cleaned = re.sub(r"\s+", " ", text.strip())
    gauge = re.match(r"^(?:#|No\.?)\s*(\d{1,2})$", cleaned, re.IGNORECASE)
    if gauge:
        return f"#{gauge.group(1)}"
    if re.fullmatch(r"\d*\.\d+", cleaned):
        key = cleaned.lstrip("0") or cleaned
        key = ("0" + key) if key.startswith(".") else key
        key = key.rstrip("0").rstrip(".") if "." in key else key
        # re-append a single trailing form so "0.50" -> "0.5" and "0.5" -> "0.5"
        fraction = _DECIMAL_TO_FRACTION_IN.get(key)
        if fraction is not None:
            return fraction
    return cleaned


def _designation_to_inches(designation: str) -> Decimal | None:
    if designation.startswith("#"):
        return tables.GAUGE_DIAMETER_IN.get(designation)
    try:
        return tables.fraction_to_decimal(designation)
    except (ValueError, ZeroDivisionError, ArithmeticError):
        return None


def _is_left_hand(hand: str | None) -> bool:
    return bool(hand) and hand.upper().startswith("L")


def _plain(value: Decimal | None) -> str:
    return "" if value is None else format(value.normalize(), "f")


def _first_line(exc: Exception) -> str:
    return str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
