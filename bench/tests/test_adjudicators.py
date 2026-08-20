"""The external adjudicators, and the limits each one refuses to exceed.

Every adjudicator in this repository has, on its first run, produced a confident disagreement that
turned out to be its own limitation rather than a defect in the suite. UCUM did it three ways; the
ISO 261 adjudicator did it on the length-suffix cases. The pattern is consistent enough to be worth
naming: **an external source will happily answer a question it was not asked.**

So these tests are mostly about declining. Each one pins a case where the adjudicator must say
"not my question" rather than rule, and each records which real misfire it prevents.
"""

from __future__ import annotations

import pytest

from errata_bench.adjudicators import (
    Verdict,
    container_noun_verdict,
    ingress_verdict,
    release_characteristic_verdict,
    thread_verdict,
    unified_thread_verdict,
)
from errata_bench.standards import (
    ISO_261_COARSE_PITCH_MM,
    ISO_261_LARGEST_COARSE_PITCH_MM,
    ISO_261_LARGEST_PITCH_MM,
    etim_available,
    etim_ip_codes,
    iso_261_coarse_pitch,
)

needs_etim = pytest.mark.skipif(not etim_available(), reason="ETIM not fetched")


# -- ISO 261 -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [("M8", "M8x1.25"), ("M10", "M10x1.5"), ("M20", "M20x2.5"), ("M12x1.75", "M12")],
)
def test_a_bare_designation_completes_from_the_coarse_series(a: str, b: str) -> None:
    """The point of the threads family. `M20` is not "M20 with some unstated pitch"; it is
    M20x2.5 by reference to Table 2, which gives exactly one coarse pitch per diameter."""
    verdict, _ = thread_verdict(a, b)
    assert verdict is Verdict.EQUAL


@pytest.mark.parametrize(
    ("a", "b"), [("M20", "M20x1.5"), ("M8", "M8x1"), ("M10x1.5", "M10x1.25"), ("M8", "M10")]
)
def test_a_different_pitch_or_diameter_is_a_genuine_disagreement(a: str, b: str) -> None:
    """The negative control. An adjudicator that only ever agrees corroborates nothing."""
    verdict, _ = thread_verdict(a, b)
    assert verdict is Verdict.UNEQUAL


@pytest.mark.parametrize(("a", "b"), [("M8x40", "M8x1.25"), ("M6x30", "M6"), ("M10x50", "M10x1.5")])
def test_a_length_suffix_is_declined_not_ruled_on(a: str, b: str) -> None:
    """REGRESSION: this adjudicator first reported all three as UNEQUAL, reading the length as a
    pitch, and contradicted the suite on thr-h043/h044/h045.

    `M8x40` is a forty-millimetre M8 bolt. ISO 261 defines `M<diameter>x<pitch>` and says nothing
    about a trailing length, so it genuinely has no opinion here. Declining is the correct answer
    -- and reading the length as a length, which is what the shipped parser does, would make this
    a mirror of the code it is supposed to be checking.
    """
    verdict, detail = thread_verdict(a, b)
    assert verdict is Verdict.CANNOT_JUDGE
    assert "length suffix" in detail


def test_an_unlisted_diameter_is_declined() -> None:
    """M4.2 is not in Table 2, so a bare designation cannot be completed. Interpolating would be
    the exact failure the shipped parser documents refusing."""
    verdict, detail = thread_verdict("M4.2", "M4.2x0.7")
    assert verdict is Verdict.CANNOT_JUDGE
    assert "ISO 261 Table 2 lists" in detail


@pytest.mark.parametrize("text", ["3/8-16 UNC", "NPT 1/2", "G 1/2", "Threaded", "M8-6g"])
def test_non_metric_designations_are_declined(text: str) -> None:
    """ISO 261 covers metric threads. Unified, pipe and tolerance-class designations belong to
    other standards, none of which were opened."""
    assert thread_verdict(text, "M8")[0] is Verdict.CANNOT_JUDGE


def test_the_coarse_table_stops_where_the_standard_does() -> None:
    """Table 2 lists no coarse pitch above M68 -- above that it gives fine pitches only."""
    assert iso_261_coarse_pitch("68") is not None
    assert iso_261_coarse_pitch("72") is None
    assert iso_261_coarse_pitch("125") is None
    assert max(float(d) for d in ISO_261_COARSE_PITCH_MM) == 68


def test_the_two_maxima_are_not_confused() -> None:
    """The repository asserted the wrong one of these in three separate places: 6 mm is the
    largest COARSE pitch; 8 mm is the largest pitch anywhere in Table 2 (M125, M130)."""
    assert ISO_261_LARGEST_COARSE_PITCH_MM == 6
    assert ISO_261_LARGEST_PITCH_MM == 8


# -- ETIM IP codes -----------------------------------------------------------------------------


@needs_etim
def test_etim_publishes_the_ip_codes_this_suite_uses() -> None:
    codes = etim_ip_codes()
    assert {"IP20", "IP54", "IP65", "IP67", "IP68"} <= codes
    assert len(codes) >= 50


@needs_etim
@pytest.mark.parametrize(("a", "b"), [("IP67", "IP 67"), ("IP20", "IP 20"), ("ip54", "IP54")])
def test_the_same_ip_code_written_differently_is_one_value(a: str, b: str) -> None:
    assert ingress_verdict(a, b)[0] is Verdict.EQUAL


@needs_etim
@pytest.mark.parametrize(("a", "b"), [("IP67", "IP65"), ("IP67", "IP54"), ("IP20", "IP40")])
def test_two_different_ip_codes_are_two_values(a: str, b: str) -> None:
    """ETIM's committees list these as separate entries, which is the whole judgment."""
    verdict, detail = ingress_verdict(a, b)
    assert verdict is Verdict.UNEQUAL
    assert "separate entries" in detail


@needs_etim
@pytest.mark.parametrize(("a", "b"), [("IP20", "IP2X"), ("IP2X", "IP20"), ("IPX7", "IP67")])
def test_an_x_digit_is_always_declined(a: str, b: str) -> None:
    """In IEC 60529 `X` means the digit was NOT TESTED, not that it scored zero.

    So `IP20` vs `IP2X` is a question about how to treat missing information, and the suite
    labels cases of that shape four different ways on purpose -- agreement_specific, granularity,
    undetermined, equivalent. A value list has no opinion on which is right, and answering anyway
    would manufacture agreement on precisely the cases where the judgment is hardest.
    """
    verdict, detail = ingress_verdict(a, b)
    assert verdict is Verdict.CANNOT_JUDGE
    assert "not tested" in detail


@needs_etim
def test_a_code_outside_etims_list_is_declined() -> None:
    assert ingress_verdict("IP99", "IP67")[0] is Verdict.CANNOT_JUDGE


@pytest.mark.parametrize("text", ["NEMA 4X", "IP67/IP65", "protected", "IP6"])
def test_non_ip_strings_are_declined(text: str) -> None:
    assert ingress_verdict(text, "IP67")[0] is Verdict.CANNOT_JUDGE


# -- the shared discipline ---------------------------------------------------------------------


@pytest.mark.parametrize("adjudicate", [thread_verdict, ingress_verdict])
def test_every_adjudicator_explains_itself_when_it_declines(adjudicate) -> None:
    """A bare CANNOT_JUDGE is not useful. The reason is what tells a reader whether coverage is
    low because the standard does not apply or because something is broken."""
    verdict, detail = adjudicate("something unparseable", "something else")
    assert verdict is Verdict.CANNOT_JUDGE
    assert detail


@pytest.mark.parametrize("adjudicate", [thread_verdict, ingress_verdict])
def test_no_adjudicator_imports_the_comparator(adjudicate) -> None:
    """The whole value of a second opinion is that it is a second opinion."""
    import ast
    import inspect

    from errata_bench import adjudicators

    tree = ast.parse(inspect.getsource(adjudicators))
    imported = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "errata_valuesem" not in imported
    assert "errata_comparator" not in imported


# -- NBS Handbook H28 -- Unified inch threads ---------------------------------------------------
#
# ASME B1.1 is paywalled. H28 is a US Government publication in the public domain covering the
# same UNC/UNF/UNEF series, and B1.1 descends from it. That substitution is the reason the threads
# family went from 38 externally-judged cases to 58.


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("1 3/4 UNC", "1 3/4-5 UNC"),
        ("1 1/4 UNF", "1 1/4-12 UNF"),
        ("2-4.5 UNC", "2 UNC"),
        ("0.375-16 UNC", "3/8-16 UNC"),
        ("No. 10-32", "#10-32 UNF"),
        ("1-8 UN", "1-8 UNC"),
    ],
)
def test_a_series_designation_completes_from_h28(a: str, b: str) -> None:
    """`1 3/4 UNC` is 5 TPI by reference to Table III.3, exactly as `M20` is 2.5 mm by ISO 261.

    `0.375` and `3/8` are the same row, and `1-8 UN` equals `1-8 UNC` because the constant-pitch
    series coincides with the coarse series at 1 inch.
    """
    assert unified_thread_verdict(a, b)[0] is Verdict.EQUAL


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("2-8 UN", "2-4.5 UNC"),
        ("1 1/2-8 UN", "1 1/2-6 UNC"),
        ("1/2-28 UNEF", "1/2-20 UNF"),
        ("#6-32 UNC", "#6-40 UNF"),
        ("1/4-20 UNC", "1/2-13 UNC"),
    ],
)
def test_a_different_pitch_or_size_is_a_genuine_disagreement(a: str, b: str) -> None:
    assert unified_thread_verdict(a, b)[0] is Verdict.UNEQUAL


@pytest.mark.parametrize(
    ("a", "b", "why"),
    [
        ("1/4-20 UNJC", "1/4-20 UNC", "UNJ"),
        ("3/8-24 UNJF", "3/8-24 UNF", "UNJ"),
        ("1/4-20 UNC-2A", "1/4-20 UNC-2B", "tolerance class"),
        ("1/4-20 UNC-2A", "1/4-20 UNC-3A", "tolerance class"),
        ("3/8-16 UNC LH", "3/8-16 UNC", "hand"),
        ("NPT 1/2-14", "NPS 1/2-14", "pipe"),
    ],
)
def test_distinctions_h28s_tpi_tables_cannot_see_are_declined(a: str, b: str, why: str) -> None:
    """These pairs have IDENTICAL threads per inch and are genuinely different threads.

    `1/4-20 UNJC` and `1/4-20 UNC` differ by a controlled root radius; `-2A` and `-2B` are
    external and internal; `LH` is the other hand. The suite labels all of them `contradiction`,
    correctly. A TPI table asked to rule would answer EQUAL and *agree with nothing* -- it would
    be corroborating a number it never looked at. Declining is the only honest move, and it is why
    coverage is 17.8% rather than a flattering figure.
    """
    verdict, _ = unified_thread_verdict(a, b)
    assert verdict is Verdict.CANNOT_JUDGE, f"{why} is not something H28's TPI tables can rule on"


def test_an_illegible_cell_is_absent_rather_than_recalled() -> None:
    """`#4 UNC` and `#6 UNF` are smudged past reading in the scan.

    Their values are well known. That is exactly why they are NOT in the tables: "well known" is
    how an unread number gets recorded as though it had been read, which is the failure mode
    HANDOFF section 7 documents four times over. The adjudicator declines instead.
    """
    from errata_bench.standards import UNC_TPI, UNF_TPI

    assert "#4" not in UNC_TPI
    assert "#6" not in UNF_TPI
    assert unified_thread_verdict("#4 UNC", "#4-40 UNC")[0] is Verdict.CANNOT_JUDGE


def test_the_unf_and_unef_tables_differ_where_the_earlier_session_confused_them() -> None:
    """HANDOFF section 7: an earlier session "briefly wrote UNF's 12 TPI values into the UNEF
    table, where the correct value is 18".

    Reading both tables confirms it and shows how it happened -- from 1 inch upward UNF runs 12
    and UNEF runs 18, in adjacent columns of adjacent pages.
    """
    from errata_bench.standards import UNEF_TPI, UNF_TPI

    assert UNF_TPI["1"] == "12"
    assert UNF_TPI["1 1/8"] == "12"
    assert UNEF_TPI["1 1/16"] == "18"
    assert UNEF_TPI["1 1/8"] == "18"


# ================================================================================================
# ETIM EF000889 -- release characteristic (the trip curve)
#
# This family was previously written off with "ETIM's class synonyms are too thin". That was true
# of ETIMARTCLASSSYNONYMMAP and it was the wrong artifact to generalise from: the trip curve is a
# FEATURE with a closed value list, and ETIM publishes it.
# ================================================================================================


@needs_etim
@pytest.mark.parametrize(
    "a,b",
    [
        ("C", "Type C"),
        ("curve B", "Char. B"),
        ("type K", "K characteristic"),
        ("MA curve", "type MA"),
        ("tripping characteristic B", "B"),
        ("TYPE C", "c curve"),
    ],
)
def test_the_same_curve_written_differently_is_one_etim_value(a: str, b: str) -> None:
    verdict, why = release_characteristic_verdict(a, b)
    assert verdict is Verdict.EQUAL, why
    assert "ETIM" in why


@needs_etim
@pytest.mark.parametrize("a,b", [("B", "C"), ("Type C", "Type D"), ("K", "Z"), ("MA", "C")])
def test_different_curves_are_separate_etim_values(a: str, b: str) -> None:
    verdict, why = release_characteristic_verdict(a, b)
    assert verdict is Verdict.UNEQUAL, why


@needs_etim
def test_cs_is_not_c() -> None:
    """ETIM publishes `C` and `Cs` as distinct values, so the resolution cannot fold case.

    A case-insensitive equality on the raw designation would make these one value. The parse is
    case-insensitive -- `type c` and `TYPE C` are the same thing typed differently -- but the
    resolution matches against the published entries and keeps them apart.
    """
    assert release_characteristic_verdict("Cs", "C")[0] is Verdict.UNEQUAL


@needs_etim
def test_a_curve_against_a_current_multiple_is_declined() -> None:
    """What a curve MEANS in multiples of In is IEC 60947-2, which a value list does not contain."""
    verdict, why = release_characteristic_verdict("C", "5-10x In")
    assert verdict is Verdict.CANNOT_JUDGE
    assert "not a plain trip-curve designation" in why


# ================================================================================================
# UN/CEFACT Rec 21 -- container nouns
# ================================================================================================


def test_rec21_settles_that_a_drum_is_not_a_roll() -> None:
    """Finding N4, ruled on by somebody other than us.

    `valuesem`'s packaging ontology folds `drum` into the `RO` (Roll) frame along with reel, spool
    and coil, with a comment defending the reel/roll merge: for cable and tape the noun varies by
    vendor while the commercial fact does not. That argument is a good one and it does not reach
    `drum`. UN/CEFACT Rec 21 assigns DR to a drum and RO to a roll, and it files them in different
    packing groups -- 34 (drums and jerricans, closed cylindrical containers) against 13 (rolls).

    The ontology is entitled to disagree with Rec 21; what it is not entitled to is to disagree
    without anyone noticing, which is what this test changes.
    """
    verdict, why = container_noun_verdict("Drum", "Roll")
    assert verdict is Verdict.UNEQUAL
    assert "DR" in why and "RO" in why


def test_rec21_also_separates_reel_from_roll() -> None:
    """The merge the ontology defends explicitly. Recorded, not silently accepted.

    Unlike `drum`, this one has a written rationale in packaging.yaml. The disagreement stands as
    a documented divergence between our frame and Rec 21's codes rather than as a defect.
    """
    assert container_noun_verdict("Roll", "Reel")[0] is Verdict.UNEQUAL


def test_the_same_noun_is_one_rec21_code() -> None:
    assert container_noun_verdict("Box", "box")[0] is Verdict.EQUAL


@pytest.mark.parametrize("a,b", [("Box of 10", "Pack of 10"), ("10/PK", "Pack of 10")])
def test_a_quantity_frame_is_not_rec21s_question(a: str, b: str) -> None:
    """Rec 21 codes a container noun. Whether two packs of ten are the same commercial fact is
    the question the packaging family is actually about, and no code list rules on it."""
    verdict, why = container_noun_verdict(a, b)
    assert verdict is Verdict.CANNOT_JUDGE
    assert "not a bare container noun" in why


def test_a_noun_rec21_does_not_list_is_declined() -> None:
    assert container_noun_verdict("Blister", "Clamshell")[0] is Verdict.CANNOT_JUDGE
