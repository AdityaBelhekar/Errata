"""Independent corroboration of suite labels against UCUM.

This module is a partial answer to FR-0.1's independent dual-labelling, so the thing that most
needs testing is **its own honesty**. A corroborator that quietly scores its silences as agreement,
or that manufactures disagreements out of its own limitations, is worse than not having one: it
produces a number that looks like external validation and is not.

The first run of this harness reported **8 disagreements**. Every one turned out to be a defect in
the corroborator rather than in the suite, and the three causes are each pinned below:

* `230/400 V` was read as the fraction 230/400 = 0.575 V. It is a dual-voltage designation.
* `0.5 in` vs `13 mm` was called unequal on a 0.3 mm gap, when `13` is written to the nearest
  millimetre and asserts nothing finer.
* `80 degC` vs `144 degF` was called unequal by applying the point-reading formula to what the
  case documents as a temperature *rise*.

That is the useful lesson and the reason these tests exist: check the instrument before believing
what it says about the thing being measured.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from errata_bench.corroborate import (
    SPELLING_TO_UCUM,
    Verdict,
    _parse_quantity,
    _verdict_for,
    corroborate_units,
    render_corroboration,
)
from errata_bench.equivalence import Label, load_cases
from errata_bench.ucum import convert, resolve, ucum_available

needs_ucum = pytest.mark.skipif(
    not ucum_available(), reason="UCUM not fetched (scripts/fetch_reference_data.sh)"
)


# -- the resolver ------------------------------------------------------------------------------


@needs_ucum
@pytest.mark.parametrize(
    ("magnitude", "source", "target", "expected"),
    [
        ("1", "[in_i]", "mm", "25.4"),
        ("0.5", "[in_i]", "mm", "12.7"),
        ("10", "mm", "cm", "1"),
        ("1", "kA", "A", "1000"),
        ("2500", "mN.m", "N.m", "2.5"),
        ("1.5", "mm2", "mm2", "1.5"),
    ],
)
def test_conversions_are_exact(magnitude: str, source: str, target: str, expected: str) -> None:
    """Exact, in Fractions. A corroboration that disagreed with the suite because of float
    rounding would be worse than no corroboration at all."""
    got = convert(Fraction(magnitude), resolve(source), resolve(target))
    assert got == Fraction(expected)


@needs_ucum
@pytest.mark.parametrize(
    ("celsius", "fahrenheit"), [("0", "32"), ("100", "212"), ("-40", "-40"), ("37", "98.6")]
)
def test_affine_temperature_scales_carry_their_offset(celsius: str, fahrenheit: str) -> None:
    """The -40 crossover is the one that catches a missing offset: it is the single point where
    a multiplicative-only conversion happens to give the right answer."""
    assert convert(Fraction(celsius), resolve("Cel"), resolve("[degF]")) == Fraction(fahrenheit)


@needs_ucum
def test_the_resolver_does_not_use_pint() -> None:
    """The whole point of a second opinion is that it is a second opinion.

    `errata_valuesem` resolves units through Pint. If this module did too, it would be asking one
    library the same question twice and reporting the echo as corroboration.
    """
    # Checks the IMPORTS, not the word: the module's own docstring explains at length that it is
    # deliberately not built on Pint, and a substring search for "pint" fails on that sentence.
    import ast
    import inspect

    from errata_bench import ucum

    tree = ast.parse(inspect.getsource(ucum))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "pint" not in imported
    assert "errata_valuesem" not in imported


# -- the parser, and the three defects it shipped with -----------------------------------------


def test_a_dual_voltage_designation_is_not_a_fraction() -> None:
    """REGRESSION: `230/400 V` was read as 230/400 = 0.575 V, producing a false disagreement
    against uni-304. Only PROPER fractions are vulgar fractions."""
    assert _parse_quantity("230/400 V") is None
    parsed = _parse_quantity('1/2"')
    assert parsed is not None
    assert parsed[0] == Fraction(1, 2)


@pytest.mark.parametrize(
    ("text", "magnitude", "exponent"),
    [("13 mm", Fraction(13), 0), ("12.7 mm", Fraction(127, 10), -1), ("6.35 mm", Fraction(127, 20), -2)],
)
def test_written_precision_is_recovered_from_the_text(
    text: str, magnitude: Fraction, exponent: int
) -> None:
    """`13` and `13.0` are the same number and not the same assertion."""
    parsed = _parse_quantity(text)
    assert parsed is not None
    assert parsed[0] == magnitude
    assert parsed[2] == exponent


@needs_ucum
def test_a_gap_inside_the_written_precision_is_not_called_a_disagreement() -> None:
    """REGRESSION: `0.5 in` vs `13 mm` was reported UNEQUAL on a 0.3 mm gap.

    `13 mm` is written to the nearest millimetre, so it claims nothing finer than +/-0.5 mm and
    12.7 sits inside that. Declines rather than agreeing, because whether an overlapping
    written-precision interval is `equivalent` or `precision` is a taxonomy call this module has
    already said it cannot make.
    """
    verdict, detail = _verdict_for("0.5 in", "13 mm")
    assert verdict is Verdict.CANNOT_JUDGE
    assert "written precision" in detail


@needs_ucum
def test_a_gap_beyond_the_written_precision_is_still_called_out() -> None:
    """The negative control. A corroborator that declines everything is not a corroborator --
    the precision allowance must not swallow a genuine mismatch."""
    verdict, detail = _verdict_for("0.5 in", "20 mm")
    assert verdict is Verdict.UNEQUAL
    assert "beyond" in detail


@needs_ucum
def test_cross_scale_temperature_is_declined_not_ruled_on() -> None:
    """REGRESSION: `80 degC` vs `144 degF` was reported UNEQUAL.

    It is correct for a temperature RISE (a delta scales by 9/5 with no offset) and wrong for a
    point reading. Nothing in either string says which, UCUM defines the scales rather than the
    semantics of the field, and unt-h031 documents this at length as a known comparator false
    positive. Declining is the only defensible answer.
    """
    verdict, detail = _verdict_for("80 degC", "144 degF")
    assert verdict is Verdict.CANNOT_JUDGE
    assert "point-vs-delta" in detail


@needs_ucum
def test_same_scale_temperature_is_still_judged() -> None:
    """Declining CROSS-scale comparisons must not mean declining all temperature."""
    assert _verdict_for("80 degC", "80 degC")[0] is Verdict.EQUAL


@needs_ucum
def test_an_unmapped_spelling_declines_rather_than_guessing() -> None:
    verdict, detail = _verdict_for("5 furlongs", "1 km")
    assert verdict is Verdict.CANNOT_JUDGE
    assert "no UCUM spelling mapped" in detail


@needs_ucum
def test_incommensurable_dimensions_are_a_genuine_disagreement() -> None:
    assert _verdict_for("10 mm", "10 A")[0] is Verdict.UNEQUAL


# -- the report --------------------------------------------------------------------------------


@needs_ucum
def test_every_externally_judgeable_label_is_corroborated() -> None:
    """The result this module exists to produce.

    If this ever fails, read the disagreement before touching the suite: on the first run all
    eight were the corroborator's fault, not the suite's.
    """
    report = corroborate_units()
    assert report.scoreable, "nothing was judged -- the corroborator has stopped working"
    assert not report.disagreements, "\n".join(
        f"{r.case_id}: {r.a!r} vs {r.b!r} suite={r.suite_label.value} "
        f"external={r.verdict.value} -- {r.detail}"
        for r in report.disagreements
    )
    assert report.agreement_rate == 1.0


@needs_ucum
def test_silence_is_never_counted_as_agreement() -> None:
    """The failure mode that would make this whole module dishonest."""
    report = corroborate_units()
    for result in report.results:
        if result.verdict is Verdict.CANNOT_JUDGE:
            assert not result.agrees
            assert not result.is_scoreable


@needs_ucum
def test_only_the_two_labels_ucum_has_an_opinion_about_are_scored() -> None:
    """`granularity`, `precision` and `undetermined` are taxonomy judgments. Scoring them against
    a unit standard would manufacture agreement out of a question it was never asked."""
    for result in corroborate_units().scoreable:
        assert result.suite_label in {Label.EQUIVALENT, Label.CONTRADICTION}


@needs_ucum
def test_coverage_is_reported_and_is_honestly_partial() -> None:
    """Coverage is 6.2%. Reporting it is the point: a headline agreement rate without the
    denominator would read as though the suite had been independently validated."""
    report = corroborate_units()
    assert 0.0 < report.coverage < 0.5
    text = render_corroboration(report)
    assert "% of the suite" in text
    assert "PARTIAL substitute" in text
    assert "Still outstanding for FR-0.1" in text


@needs_ucum
def test_families_with_no_external_source_say_so_rather_than_showing_zero() -> None:
    """A family showing "0/144 judged" next to families with real numbers reads as a failure.
    It is not -- no external standard applies -- and the report has to say which it is."""
    text = render_corroboration(corroborate_units())
    assert "no external standard applies" in text


def test_the_spelling_map_is_the_only_place_our_reading_enters() -> None:
    """Documented as such in the module, and worth pinning: every entry maps a trade spelling to
    a UCUM code, and none of them invents a unit."""
    assert SPELLING_TO_UCUM["in"] == "[in_i]"
    assert SPELLING_TO_UCUM["Nm"] == "N.m"
    assert SPELLING_TO_UCUM["degC"] == "Cel"
    assert len(set(SPELLING_TO_UCUM)) == len(SPELLING_TO_UCUM)


@needs_ucum
def test_the_corroborator_examines_the_whole_suite() -> None:
    assert len(corroborate_units().results) == len(load_cases())


# ================================================================================================
# The combined pass -- every external source at once
# ================================================================================================


@needs_ucum
def test_the_combined_pass_covers_more_than_units_alone() -> None:
    """Adding ISO 261 and ETIM took coverage from 6.2% to 14.6%. The point of asserting it is
    that a source silently falling out of the rotation would otherwise look like nothing."""
    from errata_bench.corroborate import corroborate

    combined, units_only = corroborate(), corroborate_units()
    assert len(combined.scoreable) > len(units_only.scoreable)
    assert len(combined.scoreable) >= 85


@needs_ucum
def test_every_externally_judgeable_label_is_corroborated_by_every_source() -> None:
    """The headline result. Read any failure here before touching the suite: on both runs so far,
    every apparent disagreement was the adjudicator's limitation rather than a suite defect."""
    from errata_bench.corroborate import corroborate

    report = corroborate()
    assert not report.disagreements, "\n".join(
        f"{r.case_id} [{r.source}]: {r.a!r} vs {r.b!r} suite={r.suite_label.value} "
        f"external={r.verdict.value} -- {r.detail}"
        for r in report.disagreements
    )
    assert report.agreement_rate == 1.0


@needs_ucum
def test_four_families_now_have_external_coverage() -> None:
    from errata_bench.corroborate import corroborate

    covered = {r.family for r in corroborate().scoreable}
    assert {"units", "threads", "ingress"} <= covered


@needs_ucum
def test_every_ruling_records_which_standard_made_it() -> None:
    """Attribution is the difference between corroboration and an assertion. A reader has to be
    able to ask "says who" of any individual verdict."""
    from errata_bench.corroborate import corroborate

    for result in corroborate().results:
        if result.is_judged:
            assert result.source, f"{result.case_id} was ruled on by nobody in particular"
        else:
            assert not result.source


@needs_ucum
def test_materials_and_terms_remain_uncovered_and_say_so() -> None:
    """The honest half of the result. 112 materials cases and 119 terms cases have no external
    source: steel-grade cross-references are paywalled, and ETIM's class synonyms are too thin
    for the trip-curve and pole-count vocabulary. Asserted so that a future reader does not
    mistake the improved headline for full coverage.
    """
    from errata_bench.corroborate import corroborate, render_corroboration

    report = corroborate()
    covered = {r.family for r in report.scoreable}
    assert "materials" not in covered
    assert "terms" not in covered
    assert "no external standard applies" in render_corroboration(report)
