"""Relations between normalized values.

The organising principle: the cost of a missed error is one bad record, and the cost of a false
accusation is the reviewer's trust in every subsequent screen (§8.1). So the tests are arranged in
two blocks -- things that must never be reported as a disagreement, and things that must always be.
"""

from __future__ import annotations

import pytest

from errata_valuesem import Kind, Relation, compare, normalize


def rel(a: str, b: str, **kwargs: object) -> Relation:
    return compare(normalize(a, **kwargs), normalize(b, **kwargs)).relation  # type: ignore[arg-type]


# ------------------------------------------------------ must never be reported as a disagreement --


@pytest.mark.parametrize(
    "a,b",
    [
        ("M8", "M8x1.25"),
        ("M8 × 1.25", "M8-1.25"),
        ("3/8-16", "3/8-16 UNC"),
        ("1/2 NPT", "NPT 1/2-14"),
        ("0.5 in", "12.7 mm"),
        ('1/2"', "12.7 mm"),
        ("10 mm", "1 cm"),
        ("1 kA", "1000 A"),
        ("25 Nm", "25 N*m"),
        ("2500 mNm", "2.5 Nm"),
        ("0 degC", "32 degF"),
        ("100 degC", "212 degF"),
        ("1 bar", "100 kPa"),
        ("10 mm", "10.0 mm"),
        ("63 A", "63.0 A"),
        ("230 V", "230 V AC"),
        ("63 A", "63 A max"),
        ("IP67", "IP 67"),
        ("IP67", "IP-67"),
        ("IP66/IP67", "IP66/67"),
        ("Each", "EA"),
        ("EA", "PCE"),
        ("Box of 10", "Pack of 10"),
        ("10/PK", "Pack of 10"),
        ("-25 ... +70 °C", "-25 .. 70 degC"),
        ("230/400 V", "400/230 V"),
    ],
)
def test_equivalent_pairs_never_disagree(a: str, b: str) -> None:
    verdict = compare(normalize(a), normalize(b))
    assert verdict.is_equivalent, f"{a!r} vs {b!r} -> {verdict.relation.value}: {verdict.rationale}"


@pytest.mark.parametrize(
    "a,b",
    [
        ("316 SS", "A4"),
        ("316", "1.4401"),
        ("A4", "X5CrNiMo17-12-2"),
        ("304", "1.4301"),
        ("A2", "304"),
        ("18/8", "304"),
        ("6061-T6", "AA6061-T6"),
        ("CuZn39Pb3", "CW614N"),
        ("PA66", "nylon 66"),
        ("Viton", "FKM"),
        ("Teflon", "PTFE"),
    ],
)
def test_material_vocabularies_never_disagree(a: str, b: str) -> None:
    verdict = compare(normalize(a, expect=Kind.MATERIAL), normalize(b, expect=Kind.MATERIAL))
    assert verdict.is_equivalent, f"{a!r} vs {b!r} -> {verdict.relation.value}"


def test_the_headline_equivalence() -> None:
    """316 SS = A4 = 1.4401. The row that decides the company (§3.3)."""
    aliases = ["316 SS", "A4", "1.4401", "SUS316", "UNS S31600"]
    for left in aliases:
        for right in aliases:
            verdict = compare(
                normalize(left, expect=Kind.MATERIAL), normalize(right, expect=Kind.MATERIAL)
            )
            assert verdict.is_equivalent, f"{left!r} vs {right!r}"


# ------------------------------------------------------------------- must always be a contradiction --


@pytest.mark.parametrize(
    "a,b",
    [
        ("63 A", "6 A"),
        ("6 A", "60 A"),
        ("10 mm", "10 cm"),
        ("0.5 in", "0.5 mm"),
        ("230 V AC", "230 V DC"),
        ("25 Nm", "25 Ncm"),
        ("10 kA", "6 kA"),
        ("1.5 mm2", "2.5 mm2"),
        ("0 degC", "0 degF"),
        ("63 A max", "63 A min"),
        ("M8", "M8x1"),
        ("M10x1.5", "M10x1.25"),
        ("3/8-16 UNC", "3/8-24 UNF"),
        ("3/8-16 UNC", "M10x1.5"),
        ("1/2 NPT", "1/2 BSPT"),
        ("G1/2", "R1/2"),
        ("M8x1.25", "M8x1.25 LH"),
        ("IP67", "IP65"),
        ("IP44", "IP54"),
        ("IP69K", "IP69"),
        ("Each", "Box of 10"),
        ("Box of 10", "Box of 25"),
        ("Pair", "Each"),
        ("Box", "Each"),
    ],
)
def test_genuine_contradictions_are_reported(a: str, b: str) -> None:
    verdict = compare(normalize(a), normalize(b))
    assert verdict.relation is Relation.CONTRADICTION, (
        f"{a!r} vs {b!r} -> {verdict.relation.value}: {verdict.rationale}"
    )


@pytest.mark.parametrize(
    "a,b",
    [
        ("316", "304"),
        ("A2", "A4"),
        ("1.4301", "1.4401"),
        ("6061-T6", "6082"),
        ("PA66", "PA6"),
        ("NBR", "EPDM"),
        ("class 8.8", "class 10.9"),
        ("304L", "316L"),
    ],
)
def test_material_contradictions_are_reported(a: str, b: str) -> None:
    verdict = compare(normalize(a, expect=Kind.MATERIAL), normalize(b, expect=Kind.MATERIAL))
    assert verdict.relation is Relation.CONTRADICTION, f"{a!r} vs {b!r}"


# ---------------------------------------------------------------------------------- specificity --


def test_generic_terms_are_under_specified_not_wrong() -> None:
    assert rel("Threaded", "NPT 1/2-14") is Relation.B_MORE_SPECIFIC
    assert rel("Stainless steel", "316 SS") is Relation.B_MORE_SPECIFIC
    assert rel("Aluminium", "6061-T6") is Relation.B_MORE_SPECIFIC


def test_a_restricted_generic_that_does_not_cover_is_a_contradiction() -> None:
    """Subsumption is only a defence when the generic actually subsumes."""
    assert rel("NPT", "M8x1.25") is Relation.CONTRADICTION
    assert rel("Stainless steel", "PA66") is Relation.CONTRADICTION


def test_direction_is_read_not_ignored() -> None:
    """Catalog-vaguer and catalog-sharper are different findings, and must not be symmetric."""
    assert rel("IP2X", "IP20") is Relation.B_MORE_SPECIFIC
    assert rel("IP20", "IP2X") is Relation.A_MORE_SPECIFIC
    assert rel("M8x1.25", "M8x1.25-6g") is Relation.B_MORE_SPECIFIC
    assert rel("M8x1.25-6g", "M8x1.25") is Relation.A_MORE_SPECIFIC


def test_dropped_tolerance_is_precision_loss_in_the_right_direction() -> None:
    assert rel("10 mm", "10 ±0.2 mm") is Relation.A_PRECISION_LOSS
    assert rel("10 ±0.2 mm", "10 mm") is Relation.B_PRECISION_LOSS


def test_value_outside_the_stated_tolerance_is_a_contradiction() -> None:
    assert rel("10.4 mm", "10 ±0.2 mm") is Relation.CONTRADICTION


# ------------------------------------------------------------------------------------- abstention --


@pytest.mark.parametrize(
    "a,b",
    [
        ("63 A", "230 V"),
        ("10 mm", "10 kg"),
        ("3/8 in", "230/400 V"),
        ("63 A", "some free text"),
        ("some free text", "63 A"),
        ("1,000 V", "1000 V"),
        ("230/400 V", "400/690 V"),
        ("IPX4", "IP6X"),
    ],
)
def test_the_comparator_abstains_rather_than_guessing(a: str, b: str) -> None:
    verdict = compare(normalize(a), normalize(b))
    assert verdict.relation is Relation.INCOMPARABLE, (
        f"{a!r} vs {b!r} -> {verdict.relation.value}: {verdict.rationale}"
    )


def test_a_refusal_on_either_side_abstains() -> None:
    assert rel("total nonsense", "more nonsense") is Relation.INCOMPARABLE


def test_identical_strings_still_abstain_when_the_attribute_is_unresolved() -> None:
    """Two identical surfaces that mean different things in different attributes are not evidence
    of agreement -- they are evidence that the attribute was not resolved."""
    assert rel("Type B", "Type B") is Relation.INCOMPARABLE
    assert rel("Type B", "Type B", vocabulary="trip_curve") is Relation.EQUIVALENT


# ------------------------------------------------------------------------------------ properties --


@pytest.mark.parametrize(
    "a,b",
    [
        ("63 A", "6 A"),
        ("0.5 in", "12.7 mm"),
        ("316 SS", "A4"),
        ("M8", "M8x1.25"),
        ("Each", "Box of 10"),
        ("IP67", "IP65"),
    ],
)
def test_comparison_is_order_independent_in_kind(a: str, b: str) -> None:
    """A comparison whose result depends on argument order is a coin toss with extra steps.

    Equivalence and contradiction must be symmetric; the specificity relations invert.
    """
    forward = compare(normalize(a), normalize(b)).relation
    backward = compare(normalize(b), normalize(a)).relation
    inverse = {
        Relation.A_MORE_SPECIFIC: Relation.B_MORE_SPECIFIC,
        Relation.B_MORE_SPECIFIC: Relation.A_MORE_SPECIFIC,
        Relation.A_PRECISION_LOSS: Relation.B_PRECISION_LOSS,
        Relation.B_PRECISION_LOSS: Relation.A_PRECISION_LOSS,
    }
    assert backward is inverse.get(forward, forward)


def test_every_verdict_carries_a_rationale_fit_to_show_a_reviewer() -> None:
    for a, b in [("63 A", "6 A"), ("316 SS", "A4"), ("Each", "Box of 10"), ("M8", "M8x1")]:
        verdict = compare(normalize(a, expect=None), normalize(b, expect=None))
        assert verdict.rationale.strip()
        assert not verdict.rationale.startswith("Traceback")


# ------------------------------------------------- declining instead of accusing (R0 gate 1) --
#
# Three fixes that took the gate from STOP (6.22%) to PASS. Each one stopped the comparator
# raising a finding on a pair whose honest answer is "you cannot tell". The negative controls are
# the point: none of them may soften a real defect.

import pytest as _pytest

from errata_valuesem import Refusal


def _rel(a: str, b: str, **kw):
    return compare(normalize(a, **kw), normalize(b, **kw)).relation


@_pytest.mark.parametrize(
    "a,b",
    [("Box of 10", "Carton of 200"), ("Box of 10", "Carton of 20"), ("Pack of 5", "Case of 100")],
)
def test_packaging_hierarchy_declines_rather_than_accusing(a: str, b: str) -> None:
    """Inner pack inside a master carton is normal trade practice, not a frame error.

    An exact multiple between two DIFFERENT containers is equally the shape of a real error, so
    the honest verdict is to decline -- not to agree.
    """
    assert _rel(a, b) is Relation.INCOMPARABLE


@_pytest.mark.parametrize(
    "a,b",
    [
        ("Each", "Box of 10"),      # the single most important contradiction in the product
        ("EA", "BX10"),
        ("Piece", "10 Pieces"),
        ("Box of 10", "Box of 20"),      # same container noun = same level
        ("Box of 10", "Carton of 205"),  # not an exact multiple = not a nesting
    ],
)
def test_packaging_hierarchy_never_softens_a_real_frame_error(a: str, b: str) -> None:
    assert _rel(a, b) is Relation.CONTRADICTION


@_pytest.mark.parametrize(
    "a,b",
    [("class 8.8", "hot-dip galvanised"), ("12.9", "zinc plated steel"), ("8.8", "S235")],
)
def test_orthogonal_material_facets_decline(a: str, b: str) -> None:
    """A mechanical property class, a coating and a base grade are different AXES of one material.

    A bolt is routinely all three at once, so there is no reading under which they disagree -- and
    none under which they agree either.
    """
    assert _rel(a, b) is Relation.INCOMPARABLE


@_pytest.mark.parametrize("a,b", [("class 8.8", "class 10.9"), ("8.8", "12.9")])
def test_same_facet_different_value_still_contradicts(a: str, b: str) -> None:
    assert _rel(a, b) is Relation.CONTRADICTION


def test_the_canonical_material_equivalence_is_untouched() -> None:
    """316 = A4 = 1.4401 is the example the whole project is built on."""
    for other in ("A4", "1.4401"):
        assert _rel("316", other, expect=Kind.MATERIAL) is Relation.EQUIVALENT_VOCABULARY


@_pytest.mark.parametrize("text", ["IP6/7", "IP7X", "IP78"])
def test_out_of_range_ip_numerals_refuse(text: str) -> None:
    """IEC 60529 defines the first numeral over 0-6 and the second over 0-9.

    `IP6/7` is a mistyped `IP67`. Splitting it on the slash invented a two-element set containing
    `IP7` -- a rating the standard does not define -- which then "contradicted" a well-formed
    `IP67`. An accusation manufactured entirely from a delimiter. FR-4.2: refuse instead.
    """
    assert isinstance(normalize(text), Refusal)


@_pytest.mark.parametrize("text", ["IP67", "IP66/IP67", "IP66/67", "IPX7", "IP6X", "IP69K", "IP20"])
def test_well_formed_ip_codes_and_real_dual_ratings_still_parse(text: str) -> None:
    assert not isinstance(normalize(text), Refusal)


# --------------------------------------------------------------- device_type (finding 13) --
#
# Nine suite cases (trm-h062..h070) declined because no device-category vocabulary existed. The
# fix adds one. These tests pin BOTH directions: the contradictions that must now fire, and --
# more importantly -- the things the new vocabulary must not start accusing.


@pytest.mark.parametrize(
    "a,b",
    [
        # Two protection functions, three devices. Substituting across them changes what the
        # circuit is protected against, so these are safety-relevant, not naming preferences.
        ("MCB", "RCBO"),
        ("MCB", "RCCB"),
        ("RCBO", "RCCB"),
        # One letter apart in every catalog on earth, and a different product class.
        ("MCB", "MCCB"),
    ],
)
def test_device_types_contradict(a: str, b: str) -> None:
    assert compare(normalize(a), normalize(b)).relation is Relation.CONTRADICTION
    assert compare(normalize(b), normalize(a)).relation is Relation.CONTRADICTION


@pytest.mark.parametrize(
    "a,b",
    [
        ("MCB", "Miniature circuit breaker"),
        ("RCBO", "Residual current circuit breaker with overcurrent protection"),
        ("RCCB", "RCD without overcurrent protection"),
        ("MCCB", "moulded case circuit breaker"),
    ],
)
def test_device_abbreviation_equals_its_expansion(a: str, b: str) -> None:
    assert compare(normalize(a), normalize(b)).relation in {
        Relation.EQUIVALENT,
        Relation.EQUIVALENT_VOCABULARY,
    }


def test_circuit_breaker_is_generic_over_device_types() -> None:
    """Under-specified, not wrong -- the §3.3 granularity branch."""
    assert rel("Circuit breaker", "MCB") is Relation.B_MORE_SPECIFIC
    assert rel("MCB", "Circuit breaker") is Relation.A_MORE_SPECIFIC
    assert rel("Circuit breaker", "RCBO") is Relation.B_MORE_SPECIFIC


# -- negative controls: the new vocabulary must not widen the blast radius ---------------------


def test_circuit_breaker_generic_does_not_accuse_across_vocabularies() -> None:
    """'Circuit breaker' vs an RCD type is a category mismatch, not a disagreement.

    The generic lists device_type ids only. Anything from another vocabulary must return "no
    opinion" and decline -- if this ever contradicts, the generic has started answering a question
    nobody asked, which is exactly the over-resolution class the gate accounting was fixed for.
    """
    for other in ("Type A", "DIN rail", "Screw terminal"):
        assert rel("Circuit breaker", other) is not Relation.CONTRADICTION


def test_earth_leakage_stays_unregistered() -> None:
    """ELCB has three live readings (voltage-operated, RCCB, ETIM's RCBO-shaped EC000905).

    Rule 3: a grammar either parses or refuses. Registering it under any one reading would put a
    fabricated semantic choice into the comparator, so it must stay unresolvable.
    """
    from errata_valuesem import ontology

    onto = ontology.load()
    for surface in ("ELCB", "earth leakage circuit breaker"):
        assert onto.term(surface) is None
        assert onto.generic(surface) is None


def test_existing_generics_are_unaffected_by_subsumes_terms() -> None:
    assert rel("Threaded", "NPT 1/2-14") is Relation.B_MORE_SPECIFIC
    assert rel("Stainless steel", "316 SS") is Relation.B_MORE_SPECIFIC
    assert rel("Aluminium", "6061-T6") is Relation.B_MORE_SPECIFIC


# ------------------------------------------------- trip curve K/Z alias gap (trm-h006/h007) --


def test_reversed_trip_curve_word_order_resolves() -> None:
    """B/C/D registered both word orders; K and Z registered only one."""
    assert rel("type K", "K characteristic") is Relation.EQUIVALENT_VOCABULARY
    assert rel("type Z", "Z characteristic") is Relation.EQUIVALENT_VOCABULARY


def test_trip_curves_still_contradict_each_other() -> None:
    """Negative control for the alias addition: more aliases must not mean more agreement."""
    assert rel("type K", "type Z") is Relation.CONTRADICTION
    assert rel("K characteristic", "Z characteristic") is Relation.CONTRADICTION
    assert rel("characteristic B", "C curve") is Relation.CONTRADICTION


# --------------------------------------------------- galvanised vs zinc-plated (finding 9) --
#
# These were one ontology group with a caveat explaining that they are two different coatings.
# The caveat annotated; it never reached the verdict, so the comparator returned a flat semantic
# equivalence. ISO 1461 hot-dip is 45-85 micron and decades of outdoor life; ISO 4042 / ASTM B633
# electroplated zinc is 5-25 micron. Silently equating them ships a corrosion-performance defect.


@pytest.mark.parametrize(
    "a,b",
    [
        ("galvanised steel", "zinc plated steel"),
        ("HDG", "zinc plated steel"),
        ("galvanized steel", "zinc plated steel"),
        ("hot-dip galvanised", "electroplated zinc"),
    ],
)
def test_hot_dip_and_electroplated_zinc_contradict(a: str, b: str) -> None:
    assert compare(normalize(a), normalize(b)).relation is Relation.CONTRADICTION
    assert compare(normalize(b), normalize(a)).relation is Relation.CONTRADICTION


@pytest.mark.parametrize(
    "a,b",
    [
        ("hot-dip galvanised", "galvanised steel"),
        ("HDG", "hot dip galvanized"),
        ("zinc-plated", "zinc plated steel"),
        ("electro-galvanised", "zinc plated steel"),
    ],
)
def test_aliases_within_one_coating_still_agree(a: str, b: str) -> None:
    """The control. Splitting the group must not start accusing spellings of each other."""
    assert compare(normalize(a), normalize(b)).relation in {
        Relation.EQUIVALENT,
        Relation.EQUIVALENT_VOCABULARY,
    }


def test_bare_galvanised_is_under_specified_not_wrong() -> None:
    """Unqualified 'galvanised' does not name a process, so it subsumes both."""
    assert rel("Galvanised", "hot-dip galvanised") is Relation.B_MORE_SPECIFIC
    assert rel("Galvanised", "zinc plated steel") is Relation.B_MORE_SPECIFIC


# -- negative controls -------------------------------------------------------------------------


def test_coating_split_preserves_facet_orthogonality() -> None:
    """A bolt is a property class AND a coating at once. Finding 12 made those decline; the
    coating split must not undo it and start re-accusing across facets."""
    for coating in ("hot-dip galvanised", "zinc plated steel"):
        assert rel("class 8.8", coating) is not Relation.CONTRADICTION


def test_stainless_equivalences_untouched_by_the_coating_split() -> None:
    assert rel("316", "1.4401") is not Relation.CONTRADICTION
    assert rel("A4", "316") is not Relation.CONTRADICTION
    assert rel("Steel", "hot-dip galvanised") is Relation.B_MORE_SPECIFIC


def test_each_versus_box_still_contradicts() -> None:
    """The standing negative control from ground rule 7, re-asserted after ontology surgery."""
    assert rel("Each", "Box of 10") is Relation.CONTRADICTION
    assert rel("class 8.8", "class 10.9") is Relation.CONTRADICTION


# ------------------------------------------------------ 1.4404 vs 1.4435 (finding 10) --
#
# Two aliases of one group, so the comparator returned a flat equivalence. EN 10088 gives 1.4404
# Mo 2.00-2.50 and 1.4435 Mo 2.50-3.00: shifted bands, not nested ones. A bar meeting 1.4435 at
# Mo 2.8 fails 1.4404's ceiling, so the two designations are mutually exclusive claims.


def test_the_two_316L_grades_contradict() -> None:
    assert rel("1.4404", "1.4435") is Relation.CONTRADICTION
    assert rel("1.4435", "1.4404") is Relation.CONTRADICTION
    assert rel("X2CrNiMo17-12-2", "X2CrNiMo18-14-3") is Relation.CONTRADICTION


def test_the_316L_family_still_subsumes_both_grades() -> None:
    """Negative control: splitting the grades must not break the family relation above them."""
    assert rel("316L", "1.4404") is Relation.B_MORE_SPECIFIC
    assert rel("316L", "1.4435") is Relation.B_MORE_SPECIFIC
    assert rel("1.4404", "316L") is Relation.A_MORE_SPECIFIC


def test_316_to_316L_relation_survives_the_grade_split() -> None:
    """mat-302 / mat-h050: 316 against 316L stayed granularity, not contradiction."""
    assert rel("1.4401", "1.4404") is Relation.B_MORE_SPECIFIC
    assert rel("X5CrNiMo17-12-2", "1.4404") is Relation.B_MORE_SPECIFIC
    assert rel("316L", "316 L") is Relation.EQUIVALENT  # alias_key folds the space
