"""Parsing behaviour, family by family.

The cases that matter most here are the refusals. FR-4.2: the grammar either parses or refuses, and
refusal is a routable signal rather than a best guess. A parser that quietly returns *something*
for an input it did not understand is the failure this whole library exists to avoid.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from errata_valuesem import Kind, NormalizedValue, Refusal, RefusalReason, normalize
from errata_valuesem.model import IngressSpec, MaterialSpec, PackagingSpec, Quantity, ThreadSpec


def parsed(text: str, **kwargs: object) -> NormalizedValue:
    result = normalize(text, **kwargs)  # type: ignore[arg-type]
    assert isinstance(result, NormalizedValue), f"{text!r} unexpectedly refused: {result}"
    return result


def refused(text: str, **kwargs: object) -> Refusal:
    result = normalize(text, **kwargs)  # type: ignore[arg-type]
    assert isinstance(result, Refusal), f"{text!r} unexpectedly parsed as {result}"
    return result


# ------------------------------------------------------------------------------------- threads --


@pytest.mark.parametrize(
    "text,pitch",
    [
        ("M8", Decimal("1.25")),
        ("M8x1.25", Decimal("1.25")),
        ("M8 x 1.25", Decimal("1.25")),
        ("M8-1.25", Decimal("1.25")),
        ("M8 × 1.25", Decimal("1.25")),
        ("M10", Decimal("1.5")),
        ("M6", Decimal("1")),
        ("M8x1", Decimal("1")),
    ],
)
def test_metric_thread_pitch_completion(text: str, pitch: Decimal) -> None:
    spec = parsed(text).payload
    assert isinstance(spec, ThreadSpec)
    assert spec.pitch_mm == pitch


def test_inferred_pitch_is_marked_as_inferred() -> None:
    """A value completed from a table must say so, or the evidence panel would imply the source
    document stated a pitch it never printed."""
    assert parsed("M8").payload.pitch_inferred is True
    assert parsed("M8x1.25").payload.pitch_inferred is False


def test_non_standard_metric_diameter_leaves_pitch_unknown() -> None:
    """Refuse to complete a pitch for a diameter ISO 261 does not list.

    This test previously used M9 as its example of "non-standard" -- but M9 *is* an ISO 261
    diameter (3rd choice, coarse pitch 1.25 mm). The test and the coarse-pitch table shared one
    factual gap, so the table's incompleteness was pinned in place rather than caught: the
    adversarial suite later flagged `M9` vs `M9x1.25` as a false positive and the table was
    extended. M13 is genuinely absent from the ISO 261 series (…10, 11, 12, 14…), which is what
    this test needs.
    """
    spec = parsed("M13").payload
    assert spec.pitch_mm is None
    assert any("not an ISO 261 standard diameter" in note for note in parsed("M13").notes)


@pytest.mark.parametrize("designation,pitch", [("M9", "1.25"), ("M11", "1.5"), ("M4.5", "0.75"),
                                               ("M2.2", "0.45"), ("M68", "6"), ("M1.1", "0.25"),
                                               ("M5.5", "0.9")])
def test_second_and_third_choice_iso261_diameters_complete(designation: str, pitch: str) -> None:
    """ISO 261 2nd/3rd-choice diameters must complete like 1st-choice ones.

    Regression guard for the false positives the threads suite surfaced: the table held only the
    common 1st-choice diameters, so `M9` against `M9x1.25` -- the same thread twice -- was reported
    as a granularity mismatch, i.e. a finding raised against a bolt and itself.
    """
    spec = parsed(designation).payload
    assert spec.pitch_mm == Decimal(pitch)
    assert spec.pitch_inferred is True


@pytest.mark.parametrize(
    "text,tpi,series",
    [
        ("3/8-16 UNC", Decimal("16"), "UNC"),
        ("3/8-16", Decimal("16"), "UNC"),
        ("3/8 UNC", Decimal("16"), "UNC"),
        ("1/4-20", Decimal("20"), "UNC"),
        ("#10-24 UNC", Decimal("24"), "UNC"),
        ("No. 8-32 UNF", Decimal("32"), "UNF"),
    ],
)
def test_unified_thread_series_completion(text: str, tpi: Decimal, series: str) -> None:
    spec = parsed(text).payload
    assert spec.tpi == tpi
    assert spec.series == series


@pytest.mark.parametrize(
    "text,system",
    [
        ("NPT 1/2-14", "pipe_npt"),
        ("1/2-14 NPT", "pipe_npt"),
        ("1/2 NPT", "pipe_npt"),
        ("G1/2", "pipe_bspp"),
        ("Rp 1/2", "pipe_bspp"),
        ("BSPT 3/4", "pipe_bspt"),
        ("1 1/2 NPT", "pipe_npt"),
    ],
)
def test_pipe_thread_systems(text: str, system: str) -> None:
    assert parsed(text).payload.system == system


def test_malformed_thread_refuses_rather_than_guessing() -> None:
    refusal = refused("M8x", expect=Kind.THREAD)
    assert refusal.reason is RefusalReason.MALFORMED


# ---------------------------------------------------------------------------------- magnitudes --


def test_trailing_zeros_are_preserved() -> None:
    """The number of digits written is the source's claim about its own precision."""
    assert parsed("10 mm").payload.magnitude == Decimal("10")
    assert parsed("10.0 mm").payload.magnitude.as_tuple().exponent == -1


def test_inch_fractions_are_exact() -> None:
    quantity = parsed("1/2 in").payload
    assert isinstance(quantity, Quantity)
    assert quantity.magnitude == Decimal("0.5")
    assert quantity.exact is True


def test_slash_numbers_split_by_denominator() -> None:
    assert parsed("3/8 in").kind is Kind.QUANTITY
    assert parsed("230/400 V").kind is Kind.QUANTITY_SET


def test_bare_dimensionless_integer_is_exact() -> None:
    """`2` poles is two poles, not "between 1.5 and 2.5"."""
    assert parsed("2").payload.exact is True


def test_tolerance_forms() -> None:
    symmetric = parsed("10 ±0.2 mm").payload
    assert symmetric.tolerance is not None
    assert symmetric.tolerance.plus == symmetric.tolerance.minus == Decimal("0.2")

    asymmetric = parsed("10 +0.2/-0.1 mm").payload
    assert asymmetric.tolerance.plus == Decimal("0.2")
    assert asymmetric.tolerance.minus == Decimal("0.1")

    relative = parsed("100 mm ±2%").payload
    assert relative.tolerance.relative is True


def test_qualifiers_are_separated_from_units() -> None:
    assert parsed("230 V AC").payload.qualifier == "AC"
    assert parsed("63 A max").payload.qualifier == "max"
    assert parsed("<= 40 °C").payload.qualifier == "max"


def test_min_is_a_unit_when_it_is_the_unit() -> None:
    """`10 min` is ten minutes. The rule priority that makes this work is easy to break."""
    quantity = parsed("10 min").payload
    assert quantity.qualifier == ""
    assert quantity.unit == "minute"


def test_ranges_and_separators() -> None:
    for text in ("-25 ... +70 °C", "-25…+70°C", "-25 to 70 degC"):
        value = parsed(text)
        assert value.kind is Kind.RANGE
        assert value.payload[0].magnitude == Decimal("-25")


def test_ambiguous_thousands_separator_refuses() -> None:
    """`1,000` is 1000 in English and 1 in German -- a 1000x difference on a rated-voltage field."""
    refusal = refused("1,000 V")
    assert refusal.reason is RefusalReason.AMBIGUOUS_PARSE
    # ...and resolves when the caller declares the locale.
    assert parsed("1,000 V", decimal_separator=".").payload.magnitude == Decimal("1000")
    assert parsed("1,000 V", decimal_separator=",").payload.magnitude == Decimal("1.000")


def test_unambiguous_decimal_comma_resolves() -> None:
    assert parsed("1,5 mm").payload.magnitude == Decimal("1.5")


# ------------------------------------------------------------------------------------- ingress --


@pytest.mark.parametrize("text", ["IP67", "IP 67", "IP-67"])
def test_ingress_spelling_variants(text: str) -> None:
    spec = parsed(text).payload
    assert isinstance(spec, IngressSpec)
    assert (spec.solids, spec.liquids) == (6, 7)


def test_ingress_x_is_not_zero() -> None:
    assert parsed("IP6X").payload.liquids is None
    assert parsed("IPX4").payload.solids is None
    assert parsed("IP60").payload.liquids == 0


def test_multiple_ingress_ratings() -> None:
    for text in ("IP66/IP67", "IP66/67"):
        payload = parsed(text).payload
        assert isinstance(payload, tuple)
        assert {s.designation for s in payload} == {"IP66", "IP67"}


def test_malformed_ingress_refuses() -> None:
    assert refused("IP678").reason is RefusalReason.MALFORMED


# ----------------------------------------------------------------------------------- materials --


def test_material_equivalence_classes() -> None:
    for alias in ("316 SS", "A4", "1.4401", "X5CrNiMo17-12-2", "SUS316"):
        spec = normalize(alias, expect=Kind.MATERIAL).payload
        assert isinstance(spec, MaterialSpec)
        assert spec.group_id == "steel/stainless/316"


def test_conditional_equivalences_carry_their_caveat() -> None:
    spec = normalize("A4", expect=Kind.MATERIAL).payload
    assert "property-class group" in spec.caveat


def test_bare_number_is_not_a_material_without_the_attribute_type() -> None:
    """`316` is a grade in a material field and the number 316 everywhere else."""
    assert parsed("316").kind is Kind.QUANTITY
    assert parsed("316", expect=Kind.MATERIAL).kind is Kind.MATERIAL


def test_unknown_material_refuses_when_a_material_was_expected() -> None:
    refusal = refused("Unobtainium 7", expect=Kind.MATERIAL)
    assert refusal.reason is RefusalReason.UNKNOWN_TERM


# --------------------------------------------------------------------------------------- terms --


def test_closed_vocabulary_requires_naming_the_vocabulary() -> None:
    """`Type B` is a trip curve and an RCD type. Without the attribute, there is no answer."""
    assert refused("Type B").reason is RefusalReason.AMBIGUOUS_PARSE
    assert parsed("Type B", vocabulary="trip_curve").payload.term_id == "trip_curve/B"
    assert parsed("Type B", vocabulary="rcd_type").payload.term_id == "rcd_type/B"


def test_value_outside_the_value_list_is_rejected_not_coerced() -> None:
    refusal = refused("Q", expect=Kind.TERM, vocabulary="trip_curve")
    assert refusal.reason is RefusalReason.UNKNOWN_TERM


def test_generic_terms_resolve_without_a_hint() -> None:
    assert parsed("Threaded").payload.term_id == "generic/threaded"
    assert parsed("Stainless steel").payload.term_id == "generic/stainless_steel"


def test_generic_terms_are_reachable_inside_a_constrained_chain() -> None:
    """A thread attribute is allowed to contain the word 'Threaded'.

    Without this, the most common granularity mismatch in the taxonomy becomes an unparseable
    value instead of a finding.
    """
    assert parsed("Threaded", expect=Kind.THREAD).payload.term_id == "generic/threaded"


def test_ambiguous_checkbox_marker_refuses() -> None:
    assert refused("x", expect=Kind.BOOLEAN).reason is RefusalReason.UNKNOWN_TERM


# ----------------------------------------------------------------------------------- packaging --


@pytest.mark.parametrize(
    "text,code,quantity",
    [
        ("Each", "EA", Decimal("1")),
        ("EA", "EA", Decimal("1")),
        ("PCE", "EA", Decimal("1")),
        ("Box of 10", "BX", Decimal("10")),
        ("BOX/10", "BX", Decimal("10")),
        ("10/PK", "PK", Decimal("10")),
        ("Pack of 25", "PK", Decimal("25")),
        ("Box (10)", "BX", Decimal("10")),
        ("Dozen", "DZN", Decimal("12")),  # Rec 20 code is DZN; "DZ" is not a Rec 20 code
    ],
)
def test_packaging_forms(text: str, code: str, quantity: Decimal) -> None:
    spec = parsed(text).payload
    assert isinstance(spec, PackagingSpec)
    assert (spec.uom_code, spec.quantity) == (code, quantity)


def test_bare_container_has_unknown_quantity_not_one() -> None:
    """Defaulting a bare `Box` to one is how the tool would manufacture the very error it hunts."""
    assert parsed("Box").payload.quantity is None


# ------------------------------------------------------------------------------- null and noise --


@pytest.mark.parametrize("text", ["", "  ", "-", "--", "n/a", "N/A", "TBD", "not specified"])
def test_null_placeholders(text: str) -> None:
    assert refused(text).reason is RefusalReason.EMPTY


def test_free_text_refuses_with_a_routable_reason() -> None:
    refusal = refused("suitable for most industrial applications")
    assert refusal.reason is RefusalReason.NO_GRAMMAR_MATCH
    assert refusal.attempted


def test_refusal_is_falsey_so_it_cannot_be_mistaken_for_success() -> None:
    assert not refused("nonsense value")


# ------------------------------------------------------------- prefixed area and volume units --
#
# REGRESSION GUARD for a silent order-of-magnitude bug, found by units_hard.yaml (unt-h026,
# unt-h064) during the R0 adversarial pass.
#
# Defining "m2 = meter ** 2" in units/industrial.txt makes the alias "m2" itself prefixable, so any
# prefixed spelling Pint is left to resolve on its own applies the prefix to the AREA instead of to
# the LENGTH being squared: um2 became micro*(m**2) = 1e-6 m2 rather than (micrometer)**2 = 1e-12
# m2. Nothing raised -- the value was simply wrong by the square of the prefix (1e6x on um2, 1e3x
# on km2), on conductor cross-section, the most common mm2 field in electrical data.
#
# These tests pin the FACTORS rather than any one comparison, because the bug class is "a prefixed
# spelling nobody defined explicitly", and the next one to go missing will not be um2.

import pytest as _pytest

from errata_valuesem.unitreg import parse_unit, registry


@_pytest.mark.parametrize(
    "unit,expected_m2",
    [
        ("nm2", 1e-18),
        ("um2", 1e-12),
        ("mm2", 1e-6),
        ("cm2", 1e-4),
        ("dm2", 1e-2),
        ("m2", 1.0),
        ("km2", 1e6),
    ],
)
def test_prefixed_area_units_square_the_prefix(unit: str, expected_m2: float) -> None:
    got = float(registry().Quantity(1, parse_unit(unit)).to("m**2").magnitude)
    assert got == _pytest.approx(expected_m2, rel=1e-9), (
        f"{unit} resolved to {got:g} m2, expected {expected_m2:g}. If this fails, a prefixed "
        f"spelling is being resolved by Pint's prefix fallback instead of an explicit definition "
        f"in units/industrial.txt -- the error is the square of the prefix and is silent."
    )


@_pytest.mark.parametrize(
    "unit,expected_m3",
    [("um3", 1e-18), ("mm3", 1e-9), ("cm3", 1e-6), ("dm3", 1e-3), ("m3", 1.0)],
)
def test_prefixed_volume_units_cube_the_prefix(unit: str, expected_m3: float) -> None:
    got = float(registry().Quantity(1, parse_unit(unit)).to("m**3").magnitude)
    assert got == _pytest.approx(expected_m3, rel=1e-9), (
        f"{unit} resolved to {got:g} m3, expected {expected_m3:g} -- see the area test above."
    )


def test_area_equivalence_across_prefixes_is_not_a_contradiction() -> None:
    """The end-to-end shape of the bug: these are the same cross-section, written two ways."""
    from errata_valuesem import Relation, compare, normalize

    verdict = compare(normalize("1.5 mm2"), normalize("1500000 um2"))
    assert verdict.relation is Relation.EQUIVALENT_UNIT_FRAME


# ------------------------------------------------------- thread completion regression guards --
#
# All three groups below were false positives surfaced by threads_hard.yaml: cases where the
# comparator raised a finding between a thread and itself. Each negative control matters as much
# as the positive case -- the fix must not merge threads that genuinely differ.


@_pytest.mark.parametrize(
    "text,expected_pitch",
    [("M8x40", "1.25"), ("M6x30", "1"), ("M10x50", "1.5"), ("M12x60", "1.75")],
)
def test_length_suffix_is_not_read_as_a_pitch(text: str, expected_pitch: str) -> None:
    """`M8x40` is an 8 mm bolt 40 mm long, not an 8 mm thread with a 40 mm pitch.

    The largest pitch in the whole ISO 261 series is 6 mm, so any larger second number is a length.
    Read as a pitch it made `M8x40` contradict `M8x1.25`.
    """
    spec = parsed(text).payload
    assert spec.pitch_mm == Decimal(expected_pitch)
    assert any("read as a length" in note for note in parsed(text).notes)


@_pytest.mark.parametrize("text,pitch", [("M68x6", "6"), ("M64x6", "6"), ("M8x1", "1")])
def test_a_real_pitch_at_or_below_the_maximum_is_still_a_pitch(text: str, pitch: str) -> None:
    """Negative control: 6 mm IS a legal pitch (M64/M68 coarse), so it must not be read as length."""
    assert parsed(text).payload.pitch_mm == Decimal(pitch)


def test_iso965_doubled_tolerance_class_abbreviates() -> None:
    """ISO 965-1: when the pitch-diameter and crest-diameter classes are identical the pair
    abbreviates to one, so `6g6g` and `6g` name the same class."""
    from errata_valuesem import Relation, compare

    assert compare(parsed("M8x1.25-6g"), parsed("M8x1.25-6g6g")).relation in {
        Relation.EQUIVALENT, Relation.EQUIVALENT_VOCABULARY,
    }
    assert compare(parsed("M8x1.25-6H6H"), parsed("M8x1.25-6H")).relation in {
        Relation.EQUIVALENT, Relation.EQUIVALENT_VOCABULARY,
    }
    # Negative controls: only the DOUBLED form collapses.
    assert compare(parsed("M8x1.25-6g"), parsed("M8x1.25-6H")).relation is Relation.CONTRADICTION
    assert compare(parsed("M8x1.25-6g5g"), parsed("M8x1.25-6g")).relation is Relation.CONTRADICTION


@_pytest.mark.parametrize(
    "decimal_form,fraction_form",
    [("0.5 NPT", "1/2 NPT"), ("0.75 NPT", "3/4 NPT"), ("1.25 NPT", "1 1/4 NPT")],
)
def test_decimal_inch_designation_folds_onto_its_fraction(
    decimal_form: str, fraction_form: str
) -> None:
    """Catalogs write `0.5 NPT`, datasheets write `1/2 NPT`. The tables are keyed on fractions, so
    the decimal spelling missed every lookup and left TPI unknown -- read as a disagreement."""
    from errata_valuesem import EQUIVALENT_RELATIONS, compare

    assert compare(parsed(decimal_form), parsed(fraction_form)).relation in EQUIVALENT_RELATIONS


def test_inch_series_tables_cover_the_large_sizes() -> None:
    """UNC/UNF/NPT/BSP stopped around 1 in, so large sizes silently failed completion."""
    from errata_valuesem import tables

    assert tables.series_tpi_for("UNC", "1 3/4") == Decimal("5")
    assert tables.series_tpi_for("UNF", "1 1/4") == Decimal("12")
    assert tables.NPT_TPI["3 1/2"] == Decimal("8")
    assert tables.BSP_TPI["5"] == Decimal("11")
    # UNEF above 1 in is 18 TPI, NOT the 12 of UNF -- these are different series and an earlier
    # edit briefly wrote UNF's values into UNEF. Pinned so that cannot recur silently.
    assert tables.UNEF_TPI["1 1/4"] == Decimal("18")


# ------------------------------------------------- UN/ECE code provenance (finding 15) --
#
# Three code letters in packaging.yaml were wrong and confidently asserted: CQ for "hundred"
# (CQ is cartridge; hundred is CEN), RL for "roll" (RL is reel; roll is RO), and DZ for "dozen"
# (not a Rec 20 code at all; dozen is DZN). None of them changed a verdict -- the aliases carried
# the behaviour -- which is exactly why they survived. Verified 2026-08-19 against the Rev 17
# machine-readable list. These tests pin the LETTERS, because the next wrong one will not be CQ.


@pytest.mark.parametrize(
    "surface,code",
    [
        ("Hundred", "CEN"),
        ("Dozen", "DZN"),
        ("Thousand", "MIL"),
        ("Each", "EA"),
        ("Roll", "RO"),
        ("Reel", "RO"),  # deliberately merged with roll; see the note in packaging.yaml
        ("RL", "RO"),
        ("RO", "RO"),
    ],
)
def test_uom_codes_match_the_published_code_lists(surface: str, code: str) -> None:
    spec = parsed(surface).payload
    assert isinstance(spec, PackagingSpec)
    assert spec.uom_code == code


def test_cartridge_code_is_not_an_alias_for_hundred() -> None:
    """CQ is 'cartridge'. Resolving it to Hundred would be a 100x price error -- the exact
    packaging-frame failure this ontology exists to catch, manufactured by the ontology."""
    from errata_valuesem import ontology

    assert ontology.load().uoms_by_alias.get("cq") is None


# ------------------------------------------------------------------ ISO 261 pitch ceiling --
#
# P1 task 1.1, 2026-08-19. `MAX_ISO_METRIC_PITCH_MM` was 6, on the stated belief that "the
# largest pitch anywhere in the ISO 261 metric series is 6 mm (at M64 and M68)". ISO 261:1998
# Table 2 was opened and it says otherwise: 6 mm is the largest COARSE pitch, and above M68 the
# table lists no coarse pitch at all while continuing to list fine pitches up to 8 mm at M125
# and M130.
#
# The same false premise was in two suite citations. One belief written down in three places,
# wrong in all three, and no copy could catch another. The fix is per-diameter rather than a
# new global constant, on the standard's own authority -- ISO 261 clause 5.2: "the 'coarse'
# pitches are the largest metric pitches used in current practice".
#
# The negative controls matter more than the fix here. The ceiling exists to tell a pitch from a
# fastener length, and getting that wrong turns `M8x40` into a contradiction between a bolt and
# itself, which is the defect the ceiling was introduced to remove.


def test_an_eight_millimetre_pitch_is_a_pitch_not_a_length():
    """ISO 261:1998 Table 2 lists pitch 8 at M125 and M130."""
    for text in ("M125x8", "M130x8"):
        spec = normalize(text).payload
        assert spec.pitch_mm == Decimal("8"), f"{text} lost its pitch"
        assert not spec.pitch_inferred


def test_the_ceiling_is_the_coarse_pitch_at_that_diameter():
    from errata_valuesem.parsers.thread import _max_pitch_for

    assert _max_pitch_for(Decimal("8")) == Decimal("1.25")
    assert _max_pitch_for(Decimal("20")) == Decimal("2.5")
    assert _max_pitch_for(Decimal("64")) == Decimal("6")
    assert _max_pitch_for(Decimal("68")) == Decimal("6")


def test_above_m68_the_ceiling_falls_back_to_the_table_maximum():
    """ISO 261 Table 2 lists no coarse pitch above M68, so there is no per-diameter ceiling to
    take; the global maximum is the honest fallback."""
    from errata_valuesem.parsers.thread import MAX_ISO_METRIC_PITCH_MM, _max_pitch_for

    assert Decimal("8") == MAX_ISO_METRIC_PITCH_MM
    for diameter in ("72", "100", "125", "300"):
        assert _max_pitch_for(Decimal(diameter)) == Decimal("8")


@pytest.mark.parametrize(
    ("written", "same_as"),
    [("M8x40", "M8x1.25"), ("M6x30", "M6"), ("M10x50", "M10x1.5"), ("M20x60", "M20x2.5")],
)
def test_length_suffixes_are_still_read_as_lengths(written, same_as):
    """NEGATIVE CONTROL. The whole reason the ceiling exists."""
    from errata_valuesem import compare

    assert compare(normalize(written), normalize(same_as)).is_equivalent


def test_a_short_screw_length_is_not_mistaken_for_a_pitch():
    """NEGATIVE CONTROL, and the case that rules out simply raising the constant to 8.

    An 8 mm long M6 screw is one of the commonest fasteners there is. A flat 8 mm ceiling would
    read that 8 as a pitch -- a pitch M6 cannot have, since its coarse pitch is 1 mm.
    """
    from errata_valuesem import compare

    assert normalize("M6x8").payload.pitch_mm == Decimal("1")
    assert compare(normalize("M6x8"), normalize("M6")).is_equivalent


def test_a_pitch_invalid_for_its_diameter_is_still_rejected():
    """NEGATIVE CONTROL. M6 has no 2 mm pitch; 2 is above M6's ceiling of 1 and is read as a
    length, exactly as the old flat ceiling would have done for a larger number."""
    assert normalize("M6x2").payload.pitch_mm == Decimal("1")


@pytest.mark.parametrize(
    ("a", "b"),
    [("M20", "M20x1.5"), ("M8x1.25", "M8x1"), ("M64", "M64x4"), ("M12", "M12x1.25")],
)
def test_fine_pitch_traps_still_fire(a, b):
    """NEGATIVE CONTROL. Loosening the ceiling must not soften the defect the threads family
    exists to catch: a bare designation is the coarse thread, not a wildcard."""
    from errata_valuesem import Relation, compare

    assert compare(normalize(a), normalize(b)).relation is Relation.CONTRADICTION
