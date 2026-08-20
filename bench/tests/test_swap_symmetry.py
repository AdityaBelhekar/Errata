"""Swap symmetry audit (false-negative hunt, added by the red-team pass).

The comparator's ``a`` side is the catalog and its ``b`` side is the evidence, so
``RELATION_TO_CLASS`` is asymmetric *on purpose*: a catalog that is sharper than the datasheet is
AGREEMENT, while a catalog that is vaguer is GRANULARITY_MISMATCH. ``ing-103``/``ing-111`` in
``test_r0_gate.py`` pin that intent.

What must NOT be direction-sensitive is the *existence* of a defect. Swapping the two sides may
change what a disagreement is called; it must not turn a contradiction into a non-finding, nor
turn a decline into an accusation. This module runs the entire suite with ``a`` and ``b`` swapped
and separates the two kinds of change.
"""

from __future__ import annotations

from functools import lru_cache

from errata_bench import load_cases
from errata_bench.equivalence import Case
from errata_comparator import compare_attribute
from errata_spec import DisagreementClass as D
from errata_spec.taxonomy import CLASS_PROFILE

#: Class pairs that ``RELATION_TO_CLASS`` is documented to swap between. Seeing one of these under
#: a swap is the design working, not a bug.
BY_DESIGN_SWAPS: frozenset[frozenset[D]] = frozenset(
    {
        frozenset({D.AGREEMENT, D.GRANULARITY_MISMATCH}),  # A_MORE_SPECIFIC / B_MORE_SPECIFIC
        frozenset({D.AGREEMENT, D.PRECISION_MISMATCH}),  # B_PRECISION_LOSS / A_PRECISION_LOSS
        # a blank side changes meaning when it changes which side is blank
        frozenset({D.UNSUPPORTED_VALUE, D.CATALOG_NULL_EVIDENCE_PRESENT}),
    }
)

_ACCUSATORY = frozenset({D.CONTRADICTION, D.PACKAGING_FRAME_ERROR})


def _swapped(case: Case) -> Case:
    from dataclasses import replace

    return replace(case, a=case.b, b=case.a)


@lru_cache(maxsize=1)
def _pairs() -> tuple[tuple[Case, D, D], ...]:
    out = []
    for case in load_cases():
        fwd = compare_attribute(case.attribute, case.a, case.b).disagreement_class
        rev = compare_attribute(case.attribute, case.b, case.a).disagreement_class
        out.append((case, fwd, rev))
    return tuple(out)


def classify_swap(fwd: D, rev: D) -> str:
    if fwd is rev:
        return "symmetric"
    if frozenset({fwd, rev}) in BY_DESIGN_SWAPS:
        return "by_design"
    if (fwd in _ACCUSATORY) != (rev in _ACCUSATORY):
        return "VIOLATION_accusation_flips"
    if (fwd is D.UNDETERMINED) != (rev is D.UNDETERMINED):
        return "VIOLATION_coverage_flips"
    if CLASS_PROFILE[fwd].raises_finding != CLASS_PROFILE[rev].raises_finding:
        return "VIOLATION_finding_flips"
    return "VIOLATION_other"


def test_swapping_sides_never_creates_or_destroys_an_accusation() -> None:
    """The severe case: a contradiction in one direction and not the other.

    A defect is a property of the pair, not of which column it was read from.
    """
    bad = [
        (c.id, c.a, c.b, f.value, r.value)
        for c, f, r in _pairs()
        if classify_swap(f, r) == "VIOLATION_accusation_flips"
    ]
    assert not bad, f"{len(bad)} pairs where swapping a/b creates or destroys an accusation: {bad}"


def test_swapping_sides_never_changes_whether_the_pair_is_answerable() -> None:
    """Coverage asymmetry: declined one way, answered the other.

    Whether a value parses is a property of the value, so this can only come from an
    order-dependent comparison path.
    """
    bad = [
        (c.id, c.a, c.b, f.value, r.value)
        for c, f, r in _pairs()
        if classify_swap(f, r) == "VIOLATION_coverage_flips"
    ]
    assert not bad, f"{len(bad)} pairs declined in one direction and answered in the other: {bad}"


def test_swapping_sides_never_flips_whether_a_finding_is_raised_outside_the_designed_pairs() -> None:
    bad = [
        (c.id, c.a, c.b, f.value, r.value)
        for c, f, r in _pairs()
        if classify_swap(f, r) in {"VIOLATION_finding_flips", "VIOLATION_other"}
    ]
    assert not bad, f"{len(bad)} pairs change finding status under swap outside the design: {bad}"
