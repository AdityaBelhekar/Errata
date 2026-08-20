"""The production corpus builder, the extractors, and the two findings they close.

Three things are asserted here and each one is load-bearing:

1. **The production builder reproduces the frozen gate-2 corpus exactly.** That is the proof the
   port is faithful, and it is what lets ``spike/`` be deleted -- ``spike/README.md`` kept it
   frozen solely because ``build_corpus.py`` was "the only thing that can regenerate
   ``var/spike/corpus.yaml``". Now it is not.
2. **FR-3.4 is enforced on live objects.** ``assert_blind`` inspects a signature rather than
   reading source, so an extractor that grows a way to see the answer fails the build.
3. **A score that shares a mechanism with gold is marked not-comparable.** R1 as it ships reports
   100% against this gold set, and the report must refuse to present that as a measurement.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from errata_ecosystem.corpusbuild import (
    ACCEPTING_CLASSES,
    DEFECT_RATE,
    SEED,
    build_corpus,
    load_gold,
)
from errata_ecosystem.corpusscore import render_score, score_corpus
from errata_ecosystem.extractors import (
    EXTRACTORS,
    Prediction,
    TableBlindExtractor,
    assert_blind,
    get_extractor,
)
from errata_ecosystem.vocabulary import canonical_uri

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_CORPUS = REPO_ROOT / "var" / "spike" / "corpus.yaml"
DATASHEETS = REPO_ROOT / "var" / "spike" / "datasheets"

needs_documents = pytest.mark.skipif(
    not DATASHEETS.exists() or not list(DATASHEETS.glob("*.pdf")),
    reason="the ABB datasheets are not committed (FR-9.5); run scripts/fetch_reference_data.sh",
)
needs_frozen_corpus = pytest.mark.skipif(
    not FROZEN_CORPUS.exists(),
    reason="var/spike/corpus.yaml is not present; it is generated, not committed",
)


# ------------------------------------------------------------------------------------------------
# 1. The spike's last reason to exist
# ------------------------------------------------------------------------------------------------


@needs_documents
@needs_frozen_corpus
def test_the_production_builder_reproduces_the_frozen_gate_2_corpus_exactly() -> None:
    """Every record, every field. This is why ``spike/`` can be deleted.

    Not "close enough" and not "the same score": the same bytes, field for field, in the same
    order. A corpus that merely scores the same could differ on which records it got right, and
    the published 46.34% would then be reproduced by coincidence rather than by construction.

    The ``frozen`` comparator spec is required and is itself a finding: the gate-2 corpus was
    built describing each attribute to the comparator as a key and a column header only, which is
    less than the product tells it on a real run. See ``COMPARATOR_SPECS``.
    """
    frozen = yaml.safe_load(FROZEN_CORPUS.read_text("utf-8"))["records"]
    rebuilt = build_corpus("tableblind", comparator_spec="frozen")["records"]

    assert len(rebuilt) == len(frozen), "record count moved"
    assert [r["attribute_id"] for r in rebuilt] == [r["attribute_id"] for r in frozen], (
        "record ORDER moved. The constructed catalog draws from a seeded RNG once per gold record, "
        "so order is part of the contract rather than presentation."
    )

    for new, old in zip(rebuilt, frozen, strict=True):
        for field in old:
            assert new[field] == old[field], (
                f"{old['attribute_id']}.{field}: rebuilt {new[field]!r}, frozen {old[field]!r}. "
                "A published number just moved."
            )


@needs_documents
def test_the_product_comparator_spec_trades_false_positives_for_declines() -> None:
    """The finding rebuilding produced, and it cuts both ways.

    Gate 2's corpus described each attribute to the comparator as a key and a column header and
    nothing else -- no kinds, no vocabulary. Told that much, the comparator cannot tell that a
    packing unit is a PACKAGING value or that poles read through a term vocabulary, so it compares
    surfaces and raises. Told what the product tells it, it does neither.

    303 records move, and they are not all improvements:

    * **222 stop being raised and should never have been** -- 171 correct catalog values and 51
      FR-5.3 cosmetic-but-equivalent variants. Every one was a false positive in the published
      gate-2 disagreement half.
    * **81 stop being raised and were genuine injected defects.** With the real kinds in hand the
      comparator DECLINES a bare unitless token rather than string-comparing it, and a decline is
      not a finding. Those are false negatives the frozen spec did not have.

    So the product configuration is not simply better. It is more truthful and less covering,
    which is the same trade this repository publishes everywhere else -- and it is the reason the
    frozen spec is kept rather than deleted.
    """
    frozen = build_corpus("tableblind", comparator_spec="frozen")["records"]
    product = build_corpus("tableblind", comparator_spec="product")["records"]

    moved = [
        (f, p) for f, p in zip(frozen, product, strict=True)
        if f["is_disagreement_predicted"] != p["is_disagreement_predicted"]
    ]
    assert moved, "the two specs no longer differ; the fork has become dead code"

    # Every move is in one direction: the frozen spec raised, the product spec does not. A move the
    # other way would mean the richer spec had started raising things the poorer one missed, which
    # is a different claim entirely and must not pass silently.
    assert all(f["is_disagreement_predicted"] and not p["is_disagreement_predicted"] for f, p in moved)

    lost_real_defects = sum(1 for f, _ in moved if f["is_disagreement_actual"])
    removed_false_positives = len(moved) - lost_real_defects
    assert removed_false_positives > lost_real_defects, (
        "the product spec now loses more genuine defects than it removes false positives. That "
        "inverts the trade and needs reading before any number from either spec is quoted."
    )
    assert lost_real_defects > 0, (
        "the product spec no longer costs anything. If that is real it is good news and this test "
        "should record the new figure -- but it must not become true by a comparator change that "
        "nobody noticed."
    )


# ------------------------------------------------------------------------------------------------
# 2. FR-3.4, on live objects
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(EXTRACTORS))
def test_every_shipped_extractor_is_blind(name: str) -> None:
    assert_blind(get_extractor(name))


@pytest.mark.parametrize(
    "parameter",
    ["gold_value", "catalog_value", "expected", "known_answer", "hint", "record"],
)
def test_an_extractor_that_can_see_the_answer_is_rejected(parameter: str) -> None:
    """FR-3.4 is "the requirement most likely to be quietly broken during optimisation"."""
    source = (
        "class Leaky:\n"
        "    name = 'leaky'\n"
        "    version = '0'\n"
        f"    def predict(self, layer, tables, *, mpn, attribute, {parameter}=None):\n"
        "        return None\n"
    )
    namespace: dict[str, object] = {}
    exec(source, namespace)  # the point of the test is a signature built at runtime

    with pytest.raises(TypeError, match=re.escape("FR-3.4")):
        assert_blind(namespace["Leaky"]())


def test_an_extractor_that_accepts_arbitrary_keywords_is_rejected() -> None:
    """A signature that accepts anything enforces nothing."""

    class Wide:
        name = "wide"
        version = "0"

        def predict(self, layer, tables, *, mpn, attribute, **kwargs):
            return None

    with pytest.raises(TypeError, match="arbitrary keywords"):
        assert_blind(Wide())


def test_the_baseline_ignores_the_tables_it_is_handed() -> None:
    """Table-blind has to mean blind even when the structure is in the caller's hand."""

    class Exploding(tuple):
        def __iter__(self):
            raise AssertionError("the baseline looked at the tables")

    baseline = TableBlindExtractor()
    layer = _empty_layer()
    attribute = _any_attribute()
    assert baseline.predict(layer, Exploding(), mpn="nothing", attribute=attribute) is None


# ------------------------------------------------------------------------------------------------
# 3. A tautology must not be presentable as a measurement
# ------------------------------------------------------------------------------------------------


@needs_documents
def test_r1_as_it_ships_is_scored_but_marked_not_comparable() -> None:
    """R1 reads the same cell gold does. 100% is the same act performed twice.

    The score is still produced -- hiding it would be its own dishonesty, and seeing it is how a
    reader understands the circularity -- but no stratum may be marked comparable, and the
    rendered report must say so in words rather than leaving it to be inferred from a column.
    """
    score = score_corpus(build_corpus("r1"))

    assert score.grounding.f1 == pytest.approx(1.0), (
        "R1 no longer agrees with gold by construction. That is either a real improvement in the "
        "gold set's independence or a regression in derive; either way it needs reading, not a "
        "relaxed assertion."
    )
    assert not any(s.comparable for s in score.strata)
    assert "NO STRATUM OF THIS RUN IS COMPARABLE" in render_score(score)


@needs_documents
def test_r1_with_tables_withheld_produces_a_comparable_stratum() -> None:
    """The configuration that yields R1's real number, and the coverage it is paid for with."""
    score = score_corpus(build_corpus("r1-textwindow"))

    window = next(s for s in score.strata if s.method == "text_window")
    assert window.comparable
    assert score.coverage < 0.5, (
        "R1's fallback abstains on most records by design (finding N12: it refuses to pick a "
        "value by tie-break). A high coverage here means that refusal has been weakened."
    )


@needs_documents
def test_the_baseline_answers_where_the_shipped_extractor_declines() -> None:
    """The whole finding, as one assertion.

    Gate 2's 46.34% belongs to a system that guesses when the window is ambiguous. The shipped
    extractor declines those records. The gap between the two coverages is what the published
    number costs.
    """
    baseline = score_corpus(build_corpus("tableblind"))
    shipped = score_corpus(build_corpus("r1-textwindow"))

    assert baseline.coverage > shipped.coverage * 5, (
        "the baseline no longer commits far more often than the shipped extractor. If R1 has "
        "started guessing, finding N12 has regressed."
    )


# ------------------------------------------------------------------------------------------------
# The gold set's vocabulary, and the constructed catalog's contract
# ------------------------------------------------------------------------------------------------


def test_every_gold_attribute_key_resolves_to_an_attribute_in_the_r1_map() -> None:
    """A gold key with no home would be silently dropped, improving every rate in the report."""
    keys = {row.attribute_key for rows in load_gold().values() for row in rows}
    assert keys, "the published gold set is empty"
    for key in keys:
        assert canonical_uri(key).split(":", 1)[1], f"{key!r} resolves to nothing"


def test_the_gold_sets_packing_unit_and_the_maps_packaging_uom_are_one_attribute() -> None:
    """N15, in the one place it still applied: one attribute, one identity."""
    assert canonical_uri("packing_unit") == canonical_uri("packaging_uom")


def test_the_catalogs_seed_and_rates_are_the_ones_the_published_number_used() -> None:
    """Constants rather than parameters, because changing one moves a published number."""
    assert SEED == 20260819
    assert DEFECT_RATE == 0.18


def test_undetermined_is_not_an_accepted_value() -> None:
    """"We could not check" is not "we checked and it is fine", and the taxonomy keeps them
    apart precisely so a scorer cannot quietly merge them."""
    assert not any(c.value == "undetermined" for c in ACCEPTING_CLASSES)
    assert not any(c.value == "precision_mismatch" for c in ACCEPTING_CLASSES)


def test_prediction_claims_what_it_read_when_it_composed_nothing() -> None:
    prediction = Prediction(value="6", page=1, box=(0, 0, 1, 1), confidence=0.5, method="x")
    assert prediction.claim == "6"
    composed = Prediction(
        value="6", page=1, box=(0, 0, 1, 1), confidence=0.5, method="x", asserted_value="6 A"
    )
    assert composed.claim == "6 A"


# ------------------------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------------------------


def _empty_layer():
    from errata_audit.layout import TextLayer

    return TextLayer(text="", words=(), pages=(), columns=())


def _any_attribute():
    from errata_audit import load_attributes

    return load_attributes().get("rated_current")
