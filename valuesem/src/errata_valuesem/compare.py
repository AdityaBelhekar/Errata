"""How two normalized values stand to one another.

This is the false-positive surface of the entire product. §8.1: a missed error costs one bad
record; a false accusation costs the reviewer's trust, and there is no second session. So every
branch here is written to answer one question first -- *is there any reading under which these two
strings say the same thing?* -- and only reaches ``CONTRADICTION`` when the answer is no.

Three rules follow from that and are applied without exception:

1. **A refusal on either side abstains.** The library never compares a value it did not understand.
2. **Different semantic families abstain**, unless one of them is a generic term that demonstrably
   subsumes the other. ``Threaded`` against ``NPT 1/2-14`` is under-specified, not wrong.
3. **Incommensurable dimensions abstain.** Amperes against volts is a pipeline error upstream, and
   reporting it as a product defect would be a fabricated finding.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from .model import (
    IngressSpec,
    Kind,
    MaterialSpec,
    NormalizedValue,
    PackagingSpec,
    ParseResult,
    Quantity,
    Refusal,
    Relation,
    TermSpec,
    ThreadSpec,
    Verdict,
)
from .ontology import alias_key
from .ontology import load as load_ontology
from .precision import interval_in, intervals_overlap
from .unitreg import DIMENSIONLESS, comparison_unit, frame, same_dimension

__all__ = ["GRAMMAR_VERSION", "compare"]

GRAMMAR_VERSION = "compare/1.1.0"

#: Qualifiers that change the fact. ``230 V AC`` and ``230 V DC`` are different products.
_FRAME_QUALIFIERS = frozenset({"AC", "DC", "AC/DC", "RMS", "peak", "pk", "pp", "p-p"})

#: Qualifiers that describe how a number was arrived at. They never, on their own, create a
#: disagreement with an unqualified value.
_ADVISORY_QUALIFIERS = frozenset({"max", "min", "typ", "nom", "approx", "eff", "abs"})


def compare(a: ParseResult, b: ParseResult) -> Verdict:
    """Compare two parse results. Total: every input pair yields a verdict."""
    if isinstance(a, Refusal) or isinstance(b, Refusal):
        return _abstain_on_refusal(a, b)

    generic = _generic_subsumption(a, b)
    if generic is not None:
        return generic

    if a.kind is not b.kind:
        cross = _cross_kind(a, b)
        if cross is not None:
            return cross
        return Verdict(
            Relation.INCOMPARABLE,
            f"{a.kind.value} and {b.kind.value} are different semantic families; "
            "no comparison is defined, so no finding is raised",
            {"a_kind": a.kind.value, "b_kind": b.kind.value},
        )

    handler = _HANDLERS.get(a.kind)
    if handler is None:  # pragma: no cover - every Kind has a handler; a test asserts it
        return Verdict(Relation.INCOMPARABLE, f"no comparator for kind {a.kind.value}")
    return handler(a, b)


# ------------------------------------------------------------------------------------------------
# Abstention paths
# ------------------------------------------------------------------------------------------------


def _abstain_on_refusal(a: ParseResult, b: ParseResult) -> Verdict:
    sides: list[str] = []
    detail: dict[str, Any] = {}
    for label, side in (("catalog-side", a), ("evidence-side", b)):
        if isinstance(side, Refusal):
            sides.append(f"{label} value {side.raw!r} ({side.reason.value}: {side.detail})")
            detail[label.replace("-", "_")] = side.reason.value
    return Verdict(
        Relation.INCOMPARABLE,
        "abstaining because a value did not parse -- " + "; ".join(sides),
        detail,
    )


# ------------------------------------------------------------------------------------------------
# Generic subsumption: the granularity-mismatch branch of §3.3
# ------------------------------------------------------------------------------------------------


def _generic_subsumption(a: NormalizedValue, b: NormalizedValue) -> Verdict | None:
    a_generic = _as_generic(a)
    b_generic = _as_generic(b)
    if a_generic is None and b_generic is None:
        return None
    if a_generic is not None and b_generic is not None:
        return _compare_generics(a_generic, b_generic)

    if a_generic is not None:
        outcome = _subsumes(a_generic, b)
        if outcome is True:
            return Verdict(
                Relation.B_MORE_SPECIFIC,
                f"{a_generic.canonical!r} is a generic term that covers {b.canonical_text!r}; "
                "the catalog value is under-specified rather than wrong",
                {"generic": a_generic.term_id, "specific": b.canonical_text},
            )
        if outcome is False:
            return Verdict(
                Relation.CONTRADICTION,
                f"{a_generic.canonical!r} does not cover {b.canonical_text!r}",
                {"generic": a_generic.term_id, "specific": b.canonical_text},
            )
        return None

    assert b_generic is not None
    outcome = _subsumes(b_generic, a)
    if outcome is True:
        return Verdict(
            Relation.A_MORE_SPECIFIC,
            f"{b_generic.canonical!r} is a generic term that covers {a.canonical_text!r}",
            {"generic": b_generic.term_id, "specific": a.canonical_text},
        )
    if outcome is False:
        return Verdict(
            Relation.CONTRADICTION,
            f"{b_generic.canonical!r} does not cover {a.canonical_text!r}",
            {"generic": b_generic.term_id, "specific": a.canonical_text},
        )
    return None


def _as_generic(value: NormalizedValue) -> TermSpec | None:
    if value.kind is not Kind.TERM:
        return None
    spec = value.payload
    if isinstance(spec, TermSpec) and spec.vocabulary == "generic":
        return spec
    return None


def _subsumes(generic: TermSpec, other: NormalizedValue) -> bool | None:
    """``True`` covered, ``False`` demonstrably not covered, ``None`` no opinion."""
    if generic.subsumes_kinds and other.kind.value in generic.subsumes_kinds:
        if other.kind is Kind.THREAD and generic.restrict_thread_system:
            spec = other.payload
            assert isinstance(spec, ThreadSpec)
            return spec.system == generic.restrict_thread_system
        return True
    if generic.subsumes_groups and other.kind is Kind.MATERIAL:
        onto = load_ontology()
        group = onto.materials_by_id.get(other.payload.group_id)
        if group is None:
            return None
        return any(onto.group_matches_prefix(group, prefix) for prefix in generic.subsumes_groups)
    if generic.subsumes_terms and other.kind is Kind.TERM:
        spec = other.payload
        if not isinstance(spec, TermSpec) or spec.vocabulary == "generic":
            return None
        if spec.term_id in generic.subsumes_terms:
            return True
        covered = {tid.split("/", 1)[0] for tid in generic.subsumes_terms}
        if spec.vocabulary in covered:
            # Same vocabulary, deliberately left out of the generic's list: a real "does not
            # cover". A hypothetical generic 'RCD' listing only RCCB/RCBO must contradict MCB.
            return False
        # A different vocabulary entirely -- 'Circuit breaker' against 'Type A' is a category
        # mismatch, not a disagreement. No opinion; the caller declines.
        return None
    if generic.subsumes_kinds or generic.subsumes_groups or generic.subsumes_terms:
        return None
    return None


def _compare_generics(a: TermSpec, b: TermSpec) -> Verdict:
    if a.term_id == b.term_id:
        relation = (
            Relation.EQUIVALENT
            if alias_key(a.matched_alias) == alias_key(b.matched_alias)
            else Relation.EQUIVALENT_VOCABULARY
        )
        return Verdict(relation, f"both name {a.canonical!r}", {"term": a.term_id})
    if _prefix_covers(a.subsumes_groups, b.subsumes_groups):
        return Verdict(
            Relation.B_MORE_SPECIFIC,
            f"{a.canonical!r} covers {b.canonical!r}",
            {"broader": a.term_id, "narrower": b.term_id},
        )
    if _prefix_covers(b.subsumes_groups, a.subsumes_groups):
        return Verdict(
            Relation.A_MORE_SPECIFIC,
            f"{b.canonical!r} covers {a.canonical!r}",
            {"broader": b.term_id, "narrower": a.term_id},
        )
    return Verdict(
        Relation.CONTRADICTION,
        f"{a.canonical!r} and {b.canonical!r} name different things",
        {"a": a.term_id, "b": b.term_id},
    )


def _prefix_covers(broad: tuple[str, ...], narrow: tuple[str, ...]) -> bool:
    if not broad or not narrow:
        return False
    return all(
        any(n == p or n.startswith(p + "/") for p in broad) for n in narrow
    ) and set(broad) != set(narrow)


# ------------------------------------------------------------------------------------------------
# Cross-kind: quantity against set, quantity against range
# ------------------------------------------------------------------------------------------------


def _commensurable(a: Quantity, b: Quantity) -> bool:
    """Whether two quantities are even in the same business.

    Checked before membership and containment, because "0.375 inch is not among 230 V | 400 V" is
    true and is not a finding. Both surfaces are digits around a slash; the reading is settled by
    the denominator and the unit, and when those disagree the answer is that we cannot compare
    them, not that the catalog is wrong.
    """
    if a.unit == DIMENSIONLESS or b.unit == DIMENSIONLESS:
        return True
    return same_dimension(a.unit, b.unit)


def _cross_kind(a: NormalizedValue, b: NormalizedValue) -> Verdict | None:
    pair = {a.kind, b.kind}
    if pair == {Kind.QUANTITY, Kind.QUANTITY_SET}:
        single, multi = (a, b) if a.kind is Kind.QUANTITY else (b, a)
        if not all(_commensurable(single.payload, m) for m in multi.payload):
            return Verdict(
                Relation.INCOMPARABLE,
                f"{single.canonical_text!r} and the alternatives in {multi.canonical_text!r} are "
                "not the same kind of measurement",
            )
        inside = any(_quantities_agree(single.payload, m) for m in multi.payload)
        if inside:
            relation = Relation.A_MORE_SPECIFIC if single is a else Relation.B_MORE_SPECIFIC
            return Verdict(
                relation,
                f"{single.canonical_text!r} names one of the alternatives in "
                f"{multi.canonical_text!r}",
            )
        return Verdict(
            Relation.CONTRADICTION,
            f"{single.canonical_text!r} is not among the alternatives in {multi.canonical_text!r}",
        )

    if pair == {Kind.QUANTITY, Kind.RANGE}:
        single, rng = (a, b) if a.kind is Kind.QUANTITY else (b, a)
        lo, hi = rng.payload
        if not _commensurable(single.payload, lo):
            return Verdict(
                Relation.INCOMPARABLE,
                f"{single.canonical_text!r} and the range {rng.canonical_text!r} are not the same "
                "kind of measurement",
            )
        if _within_range(single.payload, lo, hi):
            relation = Relation.A_MORE_SPECIFIC if single is a else Relation.B_MORE_SPECIFIC
            return Verdict(
                relation,
                f"{single.canonical_text!r} falls inside the range {rng.canonical_text!r}",
            )
        return Verdict(
            Relation.CONTRADICTION,
            f"{single.canonical_text!r} falls outside the range {rng.canonical_text!r}",
        )
    return None


# ------------------------------------------------------------------------------------------------
# Quantities
# ------------------------------------------------------------------------------------------------


def _compare_quantity(a: NormalizedValue, b: NormalizedValue) -> Verdict:
    qa, qb = a.payload, b.payload
    assert isinstance(qa, Quantity) and isinstance(qb, Quantity)

    conflict, qualifier_note = _qualifier_relation(qa.qualifier, qb.qualifier)
    if conflict:
        return Verdict(
            Relation.CONTRADICTION,
            f"qualifiers disagree: {qa.qualifier or '(none)'} against {qb.qualifier or '(none)'}",
            {"a_qualifier": qa.qualifier, "b_qualifier": qb.qualifier},
        )

    if (qa.unit == DIMENSIONLESS) != (qb.unit == DIMENSIONLESS):
        return _bare_against_united(a, b, qa, qb, qualifier_note)

    if qa.unit != DIMENSIONLESS and not same_dimension(qa.unit, qb.unit):
        return Verdict(
            Relation.INCOMPARABLE,
            f"{qa.unit} and {qb.unit} measure different physical quantities; abstaining rather "
            "than reporting a defect that is really a schema mismatch",
            {"a_unit": qa.unit, "b_unit": qb.unit},
        )

    unit = qa.unit if qa.unit == qb.unit else comparison_unit(qa.unit, qb.unit)
    ia, ib = interval_in(qa, unit), interval_in(qb, unit)
    detail = {
        "unit": unit,
        "a_interval": [str(ia.lo), str(ia.hi)],
        "b_interval": [str(ib.lo), str(ib.hi)],
    }

    if not intervals_overlap(ia, ib):
        return Verdict(
            Relation.CONTRADICTION,
            f"{a.canonical_text} asserts {_span(ia)} and {b.canonical_text} asserts {_span(ib)}; "
            "the two cannot both be true",
            detail,
        )

    if qa.has_explicit_tolerance != qb.has_explicit_tolerance:
        relation = (
            Relation.A_PRECISION_LOSS if not qa.has_explicit_tolerance else Relation.B_PRECISION_LOSS
        )
        toleranced = b if relation is Relation.A_PRECISION_LOSS else a
        return Verdict(
            relation,
            f"the values agree, but {toleranced.canonical_text!r} carries a stated tolerance the "
            "other side dropped",
            detail,
        )

    if qa.unit == qb.unit:
        relation = Relation.EQUIVALENT
        rationale = f"both assert {_span(ia)}"
    else:
        relation = Relation.EQUIVALENT_UNIT_FRAME
        rationale = (
            f"same value in different unit frames: {a.canonical_text} "
            f"({frame(qa.unit)}) and {b.canonical_text} ({frame(qb.unit)}) both resolve to "
            f"{_span(ia)}"
        )
    if qualifier_note:
        rationale += f"; {qualifier_note}"
    return Verdict(relation, rationale, detail)


def _bare_against_united(
    a: NormalizedValue, b: NormalizedValue, qa: Quantity, qb: Quantity, note: str
) -> Verdict:
    bare, united = (qa, qb) if qa.unit == DIMENSIONLESS else (qb, qa)
    bare_is_a = bare is qa
    if bare.magnitude == united.magnitude:
        relation = Relation.B_MORE_SPECIFIC if bare_is_a else Relation.A_MORE_SPECIFIC
        return Verdict(
            relation,
            f"same magnitude, but only one side states a unit ({united.unit}); the bare number is "
            "under-specified rather than wrong",
            {"unit": united.unit},
        )
    return Verdict(
        Relation.CONTRADICTION,
        f"magnitudes differ ({bare.magnitude} against {united.magnitude} {united.unit}) and only "
        "one side states a unit",
    )


def _qualifier_relation(a: str, b: str) -> tuple[bool, str]:
    if a == b:
        return False, ""
    if not a or not b:
        present = a or b
        if present in _FRAME_QUALIFIERS:
            return False, (
                f"one side qualifies the value as {present} and the other does not state a frame"
            )
        return False, f"one side carries the advisory qualifier {present!r}"
    if a in _FRAME_QUALIFIERS or b in _FRAME_QUALIFIERS:
        return True, ""
    if {a, b} == {"max", "min"}:
        return True, ""
    return False, f"differing advisory qualifiers ({a} and {b})"


def _quantities_agree(a: Quantity, b: Quantity) -> bool:
    if (a.unit == DIMENSIONLESS) != (b.unit == DIMENSIONLESS):
        return a.magnitude == b.magnitude
    if a.unit != DIMENSIONLESS and not same_dimension(a.unit, b.unit):
        return False
    unit = a.unit if a.unit == b.unit else comparison_unit(a.unit, b.unit)
    return intervals_overlap(interval_in(a, unit), interval_in(b, unit))


def _within_range(value: Quantity, lo: Quantity, hi: Quantity) -> bool:
    if (
        value.unit != DIMENSIONLESS
        and lo.unit != DIMENSIONLESS
        and not same_dimension(value.unit, lo.unit)
    ):
        return False
    unit = lo.unit if lo.unit == value.unit else comparison_unit(value.unit, lo.unit)
    point = interval_in(value, unit)
    low = interval_in(lo, unit)
    high = interval_in(hi, unit)
    return point.hi >= low.lo and point.lo <= high.hi


def _compare_quantity_set(a: NormalizedValue, b: NormalizedValue) -> Verdict:
    sa, sb = list(a.payload), list(b.payload)
    a_in_b = [any(_quantities_agree(x, y) for y in sb) for x in sa]
    b_in_a = [any(_quantities_agree(y, x) for x in sa) for y in sb]

    if all(a_in_b) and all(b_in_a):
        relation = (
            Relation.EQUIVALENT
            if a.canonical_text == b.canonical_text
            else Relation.EQUIVALENT_UNIT_FRAME
        )
        return Verdict(relation, f"both list the same alternatives: {a.canonical_text}")
    if all(a_in_b):
        return Verdict(
            Relation.A_MORE_SPECIFIC,
            f"{a.canonical_text!r} is a subset of {b.canonical_text!r}",
        )
    if all(b_in_a):
        return Verdict(
            Relation.B_MORE_SPECIFIC,
            f"{b.canonical_text!r} is a subset of {a.canonical_text!r}",
        )
    if not any(a_in_b):
        return Verdict(
            Relation.CONTRADICTION,
            f"{a.canonical_text!r} and {b.canonical_text!r} share no alternative",
        )
    return Verdict(
        Relation.INCOMPARABLE,
        f"{a.canonical_text!r} and {b.canonical_text!r} overlap partially; neither contains the "
        "other, and calling that a defect would be a guess",
    )


def _compare_range(a: NormalizedValue, b: NormalizedValue) -> Verdict:
    alo, ahi = a.payload
    blo, bhi = b.payload
    lo_verdict = _compare_quantity(_wrap(alo), _wrap(blo))
    hi_verdict = _compare_quantity(_wrap(ahi), _wrap(bhi))

    if lo_verdict.is_equivalent and hi_verdict.is_equivalent:
        relation = (
            Relation.EQUIVALENT if alo.unit == blo.unit else Relation.EQUIVALENT_UNIT_FRAME
        )
        return Verdict(relation, f"both ranges span {a.canonical_text}")
    if Relation.INCOMPARABLE in {lo_verdict.relation, hi_verdict.relation}:
        return Verdict(
            Relation.INCOMPARABLE,
            f"range endpoints are not comparable: {lo_verdict.rationale}",
        )
    if _range_contains(a, b):
        return Verdict(
            Relation.B_MORE_SPECIFIC,
            f"{b.canonical_text!r} lies inside {a.canonical_text!r}",
        )
    if _range_contains(b, a):
        return Verdict(
            Relation.A_MORE_SPECIFIC,
            f"{a.canonical_text!r} lies inside {b.canonical_text!r}",
        )
    if _ranges_disjoint(a, b):
        return Verdict(
            Relation.CONTRADICTION,
            f"{a.canonical_text!r} and {b.canonical_text!r} do not overlap at all",
        )
    return Verdict(
        Relation.INCOMPARABLE,
        f"{a.canonical_text!r} and {b.canonical_text!r} overlap without containment",
    )


def _wrap(quantity: Quantity) -> NormalizedValue:
    return NormalizedValue(
        kind=Kind.QUANTITY,
        payload=quantity,
        raw=str(quantity.magnitude),
        canonical_text=f"{quantity.magnitude} {quantity.unit}".strip(),
        grammar_version=GRAMMAR_VERSION,
    )


def _range_bounds(value: NormalizedValue, unit: str) -> tuple[Decimal, Decimal]:
    lo, hi = value.payload
    return interval_in(lo, unit).lo, interval_in(hi, unit).hi


def _common_range_unit(a: NormalizedValue, b: NormalizedValue) -> str | None:
    ua, ub = a.payload[0].unit, b.payload[0].unit
    if ua == ub:
        return ua
    if ua == DIMENSIONLESS or ub == DIMENSIONLESS or not same_dimension(ua, ub):
        return None
    return comparison_unit(ua, ub)


def _range_contains(outer: NormalizedValue, inner: NormalizedValue) -> bool:
    unit = _common_range_unit(outer, inner)
    if unit is None:
        return False
    olo, ohi = _range_bounds(outer, unit)
    ilo, ihi = _range_bounds(inner, unit)
    return olo <= ilo and ihi <= ohi


def _ranges_disjoint(a: NormalizedValue, b: NormalizedValue) -> bool:
    unit = _common_range_unit(a, b)
    if unit is None:
        return False
    alo, ahi = _range_bounds(a, unit)
    blo, bhi = _range_bounds(b, unit)
    return ahi < blo or bhi < alo


# ------------------------------------------------------------------------------------------------
# Threads
# ------------------------------------------------------------------------------------------------


def _compare_thread(a: NormalizedValue, b: NormalizedValue) -> Verdict:
    ta, tb = a.payload, b.payload
    assert isinstance(ta, ThreadSpec) and isinstance(tb, ThreadSpec)

    if ta.system != tb.system:
        return Verdict(
            Relation.CONTRADICTION,
            f"{a.canonical_text} is a {ta.system} thread and {b.canonical_text} is a "
            f"{tb.system} thread; they do not mate",
            {"a_system": ta.system, "b_system": tb.system},
        )

    if ta.left_hand != tb.left_hand:
        return Verdict(
            Relation.CONTRADICTION,
            "one side is a left-hand thread and the other is right-hand",
        )

    if not _nominals_match(ta, tb):
        return Verdict(
            Relation.CONTRADICTION,
            f"nominal sizes differ: {ta.nominal_designation} against {tb.nominal_designation}",
        )

    pitch = _compare_pitch(ta, tb, a, b)
    if pitch is not None:
        return pitch

    return _compare_thread_class(ta, tb, a, b)


def _nominals_match(ta: ThreadSpec, tb: ThreadSpec) -> bool:
    if ta.nominal_designation and ta.nominal_designation == tb.nominal_designation:
        return True
    if ta.nominal_mm is not None and tb.nominal_mm is not None:
        return abs(ta.nominal_mm - tb.nominal_mm) <= Decimal("0.001")
    return False


def _compare_pitch(
    ta: ThreadSpec, tb: ThreadSpec, a: NormalizedValue, b: NormalizedValue
) -> Verdict | None:
    a_pitch, b_pitch = ta.pitch_mm, tb.pitch_mm
    a_tpi, b_tpi = ta.tpi, tb.tpi

    if a_pitch is not None and b_pitch is not None and a_pitch != b_pitch:
        return Verdict(
            Relation.CONTRADICTION,
            f"pitches differ: {a_pitch} mm against {b_pitch} mm"
            + _inferred_note(ta, tb),
            {"a_pitch_mm": str(a_pitch), "b_pitch_mm": str(b_pitch)},
        )
    if a_tpi is not None and b_tpi is not None and a_tpi != b_tpi:
        return Verdict(
            Relation.CONTRADICTION,
            f"thread counts differ: {a_tpi} TPI against {b_tpi} TPI" + _inferred_note(ta, tb),
            {"a_tpi": str(a_tpi), "b_tpi": str(b_tpi)},
        )
    if (a_pitch is None) != (b_pitch is None) and ta.system == "metric":
        relation = Relation.B_MORE_SPECIFIC if a_pitch is None else Relation.A_MORE_SPECIFIC
        return Verdict(relation, "one side states a pitch and the other does not")
    if (a_tpi is None) != (b_tpi is None) and ta.system != "metric":
        relation = Relation.B_MORE_SPECIFIC if a_tpi is None else Relation.A_MORE_SPECIFIC
        return Verdict(relation, "one side states a thread count and the other does not")
    return None


def _inferred_note(ta: ThreadSpec, tb: ThreadSpec) -> str:
    inferred = [
        spec.designation for spec in (ta, tb) if spec.pitch_inferred
    ]
    if not inferred:
        return ""
    return (
        f" (the pitch for {', '.join(inferred)} was taken from the standard coarse series, not "
        "from the source text)"
    )


_ISO965_DOUBLED_CLASS = re.compile(r"^(\d[A-Za-z])\1$", re.IGNORECASE)


def _canonical_thread_class(text: str) -> str:
    """Collapse an ISO 965-1 tolerance class written in its long form.

    A metric thread tolerance class is the pitch-diameter class followed by the crest-diameter
    class. ISO 965-1 abbreviates the pair to a single designation **when the two are identical**,
    so ``6g6g`` and ``6g`` name one class, as do ``6H6H`` and ``6H``. Comparing the raw strings
    reported a contradiction between a thread and itself.

    Only the doubled form collapses. ``6g5g`` is two genuinely different classes and is left alone,
    which is the distinction that makes this safe: it never merges classes that actually differ.
    """
    stripped = text.strip()
    match = _ISO965_DOUBLED_CLASS.match(stripped)
    return match.group(1).upper() if match else stripped.upper()


def _compare_thread_class(
    ta: ThreadSpec, tb: ThreadSpec, a: NormalizedValue, b: NormalizedValue
) -> Verdict:
    ca = _canonical_thread_class(ta.tolerance_class)
    cb = _canonical_thread_class(tb.tolerance_class)
    if ca and cb and ca != cb:
        return Verdict(
            Relation.CONTRADICTION,
            f"thread tolerance classes differ: {ta.tolerance_class} against {tb.tolerance_class}",
        )
    if ca and not cb:
        return Verdict(Relation.A_MORE_SPECIFIC, "only one side states a thread tolerance class")
    if cb and not ca:
        return Verdict(Relation.B_MORE_SPECIFIC, "only one side states a thread tolerance class")

    if a.canonical_text == b.canonical_text and a.raw.strip() == b.raw.strip():
        return Verdict(Relation.EQUIVALENT, f"both designate {a.canonical_text}")
    return Verdict(
        Relation.EQUIVALENT_VOCABULARY,
        f"{a.raw!r} and {b.raw!r} both designate {a.canonical_text}"
        + _inferred_note(ta, tb),
        {"designation": a.canonical_text},
    )


# ------------------------------------------------------------------------------------------------
# Ingress
# ------------------------------------------------------------------------------------------------


def _compare_ingress(a: NormalizedValue, b: NormalizedValue) -> Verdict:
    sa = _ingress_set(a)
    sb = _ingress_set(b)

    if len(sa) == 1 and len(sb) == 1:
        return _compare_ingress_single(sa[0], sb[0], a, b)

    keys_a = {s.designation for s in sa}
    keys_b = {s.designation for s in sb}
    if keys_a == keys_b:
        return Verdict(Relation.EQUIVALENT, f"both declare {a.canonical_text}")
    if keys_a < keys_b:
        return Verdict(
            Relation.B_MORE_SPECIFIC,
            f"{b.canonical_text!r} declares every rating in {a.canonical_text!r} and more",
        )
    if keys_b < keys_a:
        return Verdict(
            Relation.A_MORE_SPECIFIC,
            f"{a.canonical_text!r} declares every rating in {b.canonical_text!r} and more",
        )
    if keys_a & keys_b:
        return Verdict(
            Relation.INCOMPARABLE,
            f"{a.canonical_text!r} and {b.canonical_text!r} share some ratings and differ on "
            "others; neither reading dominates",
        )
    return Verdict(
        Relation.CONTRADICTION,
        f"{a.canonical_text!r} and {b.canonical_text!r} declare entirely different protection",
    )


def _ingress_set(value: NormalizedValue) -> list[IngressSpec]:
    payload = value.payload
    return list(payload) if isinstance(payload, tuple) else [payload]


def _compare_ingress_single(
    ia: IngressSpec, ib: IngressSpec, a: NormalizedValue, b: NormalizedValue
) -> Verdict:
    if ia.suffix != ib.suffix:
        # K is not a supplementary letter. IP69K is a distinct high-pressure, high-temperature
        # test under ISO 20653 / DIN 40050-9, and a catalog claiming it against a datasheet that
        # does not is over-claiming a rating, not being more precise about the same one. The
        # informational letters (H, M, S, W) of IEC 60529 are a different matter and do behave as
        # a refinement.
        if "K" in {ia.suffix.upper(), ib.suffix.upper()}:
            return Verdict(
                Relation.CONTRADICTION,
                f"{ia.designation} and {ib.designation} are different tests: the K suffix denotes "
                "the ISO 20653 high-pressure steam-jet rating, not a refinement of IEC 60529",
                {"a": ia.designation, "b": ib.designation},
            )
        if ia.suffix and not ib.suffix:
            return Verdict(
                Relation.A_MORE_SPECIFIC,
                f"{ia.designation} adds the supplementary letter {ia.suffix}",
            )
        if ib.suffix and not ia.suffix:
            return Verdict(
                Relation.B_MORE_SPECIFIC,
                f"{ib.designation} adds the supplementary letter {ib.suffix}",
            )
        return Verdict(
            Relation.CONTRADICTION,
            f"supplementary letters differ: {ia.designation} against {ib.designation}",
        )

    a_more = False
    b_more = False
    for name, x, y in (("solids", ia.solids, ib.solids), ("liquids", ia.liquids, ib.liquids)):
        if x is None and y is None:
            continue
        if x is None:
            b_more = True
            continue
        if y is None:
            a_more = True
            continue
        if x != y:
            return Verdict(
                Relation.CONTRADICTION,
                f"{name} protection differs: {ia.designation} against {ib.designation}",
                {"a": ia.designation, "b": ib.designation},
            )

    if a_more and b_more:
        return Verdict(
            Relation.INCOMPARABLE,
            f"{ia.designation} and {ib.designation} each leave a different digit unspecified",
        )
    if a_more:
        return Verdict(
            Relation.A_MORE_SPECIFIC,
            f"{ia.designation} specifies a digit that {ib.designation} leaves as X",
        )
    if b_more:
        return Verdict(
            Relation.B_MORE_SPECIFIC,
            f"{ib.designation} specifies a digit that {ia.designation} leaves as X",
        )
    relation = (
        Relation.EQUIVALENT if a.raw.strip() == b.raw.strip() else Relation.EQUIVALENT_VOCABULARY
    )
    return Verdict(relation, f"both declare {ia.designation}")


# ------------------------------------------------------------------------------------------------
# Materials, terms, booleans, packaging
# ------------------------------------------------------------------------------------------------


def _compare_material(a: NormalizedValue, b: NormalizedValue) -> Verdict:
    ma, mb = a.payload, b.payload
    assert isinstance(ma, MaterialSpec) and isinstance(mb, MaterialSpec)
    caveats = tuple(c for c in (ma.caveat, mb.caveat) if c)

    if ma.group_id == mb.group_id:
        relation = (
            Relation.EQUIVALENT
            if alias_key(ma.matched_alias) == alias_key(mb.matched_alias)
            else Relation.EQUIVALENT_VOCABULARY
        )
        rationale = (
            f"{ma.matched_alias!r} and {mb.matched_alias!r} are the same material "
            f"({ma.canonical})"
        )
        if caveats:
            rationale += " -- " + " ".join(caveats)
        return Verdict(relation, rationale, {"group": ma.group_id, "caveats": list(caveats)})

    onto = load_ontology()
    ga = onto.materials_by_id.get(ma.group_id)
    gb = onto.materials_by_id.get(mb.group_id)
    if ga is not None and gb is not None:
        if ga.facet and gb.facet and ga.facet != gb.facet:
            return Verdict(
                Relation.INCOMPARABLE,
                f"{ma.canonical} describes the {ga.facet.replace('_', ' ')} of a material and "
                f"{mb.canonical} describes its {gb.facet.replace('_', ' ')}. These are orthogonal "
                f"facets, not competing claims -- one fastener is routinely both at once -- so "
                f"there is no reading under which they disagree, and none under which they agree "
                f"either. Declining rather than accusing.",
                {"a_facet": ga.facet, "b_facet": gb.facet},
            )
        if onto.material_is_narrower(ga, gb):
            return Verdict(
                Relation.A_MORE_SPECIFIC,
                f"{ma.canonical} is a member of the {gb.canonical} family",
                {"narrow": ma.group_id, "broad": mb.group_id},
            )
        if onto.material_is_narrower(gb, ga):
            return Verdict(
                Relation.B_MORE_SPECIFIC,
                f"{mb.canonical} is a member of the {ga.canonical} family",
                {"narrow": mb.group_id, "broad": ma.group_id},
            )

    return Verdict(
        Relation.CONTRADICTION,
        f"{ma.matched_alias!r} is {ma.canonical} and {mb.matched_alias!r} is {mb.canonical}; "
        "these are different materials",
        {"a_group": ma.group_id, "b_group": mb.group_id},
    )


def _compare_term(a: NormalizedValue, b: NormalizedValue) -> Verdict:
    ta, tb = a.payload, b.payload
    assert isinstance(ta, TermSpec) and isinstance(tb, TermSpec)

    if ta.vocabulary != tb.vocabulary:
        return Verdict(
            Relation.INCOMPARABLE,
            f"{ta.matched_alias!r} is a {ta.vocabulary} value and {tb.matched_alias!r} is a "
            f"{tb.vocabulary} value; different vocabularies are not comparable",
        )
    if ta.term_id == tb.term_id:
        relation = (
            Relation.EQUIVALENT
            if alias_key(ta.matched_alias) == alias_key(tb.matched_alias)
            else Relation.EQUIVALENT_VOCABULARY
        )
        return Verdict(relation, f"both name {ta.canonical!r}", {"term": ta.term_id})
    return Verdict(
        Relation.CONTRADICTION,
        f"{ta.canonical!r} and {tb.canonical!r} are different values of the same vocabulary "
        f"({ta.vocabulary})",
        {"a_term": ta.term_id, "b_term": tb.term_id},
    )


def _compare_boolean(a: NormalizedValue, b: NormalizedValue) -> Verdict:
    if a.payload == b.payload:
        return Verdict(Relation.EQUIVALENT, f"both are {str(a.payload).lower()}")
    return Verdict(
        Relation.CONTRADICTION,
        f"{a.raw!r} is {str(a.payload).lower()} and {b.raw!r} is {str(b.payload).lower()}",
    )


def _plausible_packaging_hierarchy(pa: PackagingSpec, pb: PackagingSpec, onto: Any) -> bool:
    """Could these two be different LEVELS of one packaging hierarchy rather than a frame error?

    Industrial goods routinely ship as an inner pack nested inside a master carton -- 20 boxes of
    10 in a carton of 200. A catalog quoting the inner level and a datasheet quoting the outer are
    both correct and describe one product. The comparator has no concept of packaging levels, so it
    read every quantity difference as an error and fired the maximum-severity verdict at a normal
    trade practice.

    Declining is the honest answer here, not agreeing: an exact multiple is *also* exactly what a
    real frame error looks like, and nothing in the two values themselves separates the two
    readings. §5.5 -- abstain with a stated reason rather than guess.

    Three conditions, and each one is load-bearing:

    * **Both sides are container nouns that carry no implied count** (``default_quantity is None``:
      Box, Pack, Carton, Bag, Case, Tube, Roll, Set). This is what excludes ``Each`` -- and with it
      the single most important contradiction in the product, ``Each`` against ``Box of 10``, which
      must never be softened. It also excludes Pair/Dozen/Hundred/Thousand, which are quantity
      words rather than packaging levels.
    * **The container nouns differ.** ``Box of 10`` against ``Box of 20`` is one level quoted twice
      with different numbers, which is a straight contradiction.
    * **The quantities are an exact integer multiple.** A hierarchy nests exactly. ``Box of 10``
      against ``Carton of 205`` is not a nesting and stays an accusation.
    """
    if pa.quantity is None or pb.quantity is None or pa.uom_code == pb.uom_code:
        return False
    for code in (pa.uom_code, pb.uom_code):
        uom = onto.uoms_by_code.get(code)
        if uom is None or not uom.bulk or uom.default_quantity is not None:
            return False
    larger, smaller = sorted((pa.quantity, pb.quantity), reverse=True)
    if smaller <= 0:
        return False
    ratio = larger / smaller
    return ratio > 1 and ratio == ratio.to_integral_value()


def _compare_packaging(a: NormalizedValue, b: NormalizedValue) -> Verdict:
    pa, pb = a.payload, b.payload
    assert isinstance(pa, PackagingSpec) and isinstance(pb, PackagingSpec)
    onto = load_ontology()

    if pa.quantity is None or pb.quantity is None:
        if pa.quantity is None and pb.quantity is None:
            same = pa.uom_code == pb.uom_code or onto.containers_interchangeable(
                pa.uom_code, pb.uom_code
            )
            relation = Relation.EQUIVALENT if same else Relation.CONTRADICTION
            return Verdict(
                relation,
                f"neither side states a pack quantity ({pa.uom_canonical} / {pb.uom_canonical})",
            )
        known, unknown = (a, b) if pa.quantity is not None else (b, a)
        compatible = onto.containers_interchangeable(pa.uom_code, pb.uom_code) or (
            pa.uom_code == pb.uom_code
        )
        if not compatible:
            return Verdict(
                Relation.CONTRADICTION,
                f"{pa.uom_canonical} and {pb.uom_canonical} are different packaging frames",
            )
        relation = Relation.A_MORE_SPECIFIC if known is a else Relation.B_MORE_SPECIFIC
        return Verdict(
            relation,
            f"{known.canonical_text!r} states how many are in the container and "
            f"{unknown.canonical_text!r} does not",
        )

    if pa.quantity != pb.quantity:
        if _plausible_packaging_hierarchy(pa, pb, onto):
            larger, smaller = sorted((pa.quantity, pb.quantity), reverse=True)
            return Verdict(
                Relation.INCOMPARABLE,
                f"{pa.uom_canonical} of {_plain(pa.quantity)} against {pb.uom_canonical} of "
                f"{_plain(pb.quantity)}: two DIFFERENT containers whose quantities are an exact "
                f"{_plain(larger / smaller)}x multiple. That is the shape of an inner-pack inside "
                f"a master carton -- a normal packaging hierarchy where each side states a "
                f"different level -- and it is equally the shape of a real frame error. Nothing "
                f"in these two values distinguishes them, so this declines rather than accusing.",
                {
                    "a_quantity": str(pa.quantity),
                    "b_quantity": str(pb.quantity),
                    "multiple": str(larger / smaller),
                    "declined_reason": "possible_packaging_level_mismatch",
                },
            )
        return Verdict(
            Relation.CONTRADICTION,
            f"pack quantities differ: {pa.uom_canonical} of {_plain(pa.quantity)} against "
            f"{pb.uom_canonical} of {_plain(pb.quantity)}. A packaging-frame error prices the "
            f"line at {_ratio(pa.quantity, pb.quantity)} of cost",
            {"a_quantity": str(pa.quantity), "b_quantity": str(pb.quantity)},
        )

    if pa.uom_code == pb.uom_code:
        return Verdict(
            Relation.EQUIVALENT,
            f"both are {pa.uom_canonical} of {_plain(pa.quantity)}",
        )
    if onto.containers_interchangeable(pa.uom_code, pb.uom_code):
        return Verdict(
            Relation.EQUIVALENT_VOCABULARY,
            f"{pa.uom_canonical} and {pb.uom_canonical} both hold {_plain(pa.quantity)}; the "
            "container noun differs but the commercial fact does not",
        )
    return Verdict(
        Relation.CONTRADICTION,
        f"{pa.uom_canonical} and {pb.uom_canonical} are different packaging frames even at the "
        "same quantity",
    )


_HANDLERS = {
    Kind.QUANTITY: _compare_quantity,
    Kind.QUANTITY_SET: _compare_quantity_set,
    Kind.RANGE: _compare_range,
    Kind.THREAD: _compare_thread,
    Kind.INGRESS: _compare_ingress,
    Kind.MATERIAL: _compare_material,
    Kind.TERM: _compare_term,
    Kind.BOOLEAN: _compare_boolean,
    Kind.PACKAGING: _compare_packaging,
    Kind.COUNT: _compare_quantity,
}


def _span(interval: Any) -> str:
    if interval.lo == interval.hi:
        return f"{_plain(interval.lo)} {interval.unit}".strip()
    return f"{_plain(interval.lo)} .. {_plain(interval.hi)} {interval.unit}".strip()


def _plain(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _ratio(a: Decimal, b: Decimal) -> str:
    if a == 0 or b == 0:
        return "an undefined multiple"
    smaller, larger = (a, b) if a < b else (b, a)
    return f"1/{_plain(larger / smaller)}"
