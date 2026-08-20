"""FR-9.1 / FR-9.2 -- the axes, and the two properties that make them a benchmark.

*Independently runnable*: every axis runs alone, and running one does not run another.
*Verbatim*: the grounding axis's number is the number ``errata_bench.operating_point`` produces
on the same corpus -- byte for byte the same call, not a re-implementation that agrees today.
"""

from __future__ import annotations

import pytest

from errata_bench.operating_point import (
    EXTRACTBENCH_WORD_GROUNDING_F1,
    GROUNDING_IOU_THRESHOLD,
    GroundingLevel,
    grounding_f1,
    load_corpus,
    value_f1,
)
from errata_ecosystem.axes import (
    AXES,
    DEFAULT_CORPUS,
    AxisStatus,
    axis_ids,
    run_all,
    run_axis,
)


@pytest.fixture(scope="module")
def results():
    return {r.axis: r for r in run_all()}


def test_every_registered_axis_is_runnable_on_its_own() -> None:
    for axis in axis_ids():
        result = run_axis(axis)
        assert result.axis == axis
        assert result.requirement.startswith("FR-9")


def test_an_unknown_axis_is_refused_by_name() -> None:
    with pytest.raises(KeyError, match="unknown axis"):
        run_axis("vibes")


def test_the_registry_and_the_id_list_cannot_drift() -> None:
    assert set(axis_ids()) == set(AXES)


def test_six_axes_one_of_which_is_somebody_elses_metric() -> None:
    assert len(axis_ids()) == 6
    assert axis_ids()[0] == "grounding"


# ------------------------------------------------------------------------------------------------
# FR-9.1 -- verbatim means verbatim
# ------------------------------------------------------------------------------------------------


def test_the_grounding_axis_reports_exactly_what_the_r0_module_computes(results) -> None:
    if not DEFAULT_CORPUS.exists():  # pragma: no cover - corpus is built by the P3 spike
        pytest.skip("no corpus on this machine")
    corpus = load_corpus(DEFAULT_CORPUS)
    direct = grounding_f1(
        corpus.records, level=GroundingLevel.WORD, iou_threshold=GROUNDING_IOU_THRESHOLD
    )
    assert results["grounding"].metrics["word_grounding_f1"] == f"{direct.f1 * 100:.2f}%"
    assert results["grounding"].metrics["value_f1"] == f"{value_f1(corpus.records).f1 * 100:.2f}%"


def test_the_axis_scores_against_the_published_figure_read_from_the_paper(results) -> None:
    assert results["grounding"].metrics["extractbench_word_f1"] == EXTRACTBENCH_WORD_GROUNDING_F1
    assert results["grounding"].metrics["iou_threshold"] == 0.5
    assert "arXiv" in results["grounding"].comparable_to or results["grounding"].comparable_to


def test_the_grounding_axis_refuses_to_score_a_corpus_that_is_not_there(tmp_path) -> None:
    result = run_axis("grounding", corpus=tmp_path / "nothing.yaml")
    assert result.status is AxisStatus.NOT_MEASURED
    assert "no corpus" in result.headline


def test_the_abstention_axis_refuses_the_same_way(tmp_path) -> None:
    result = run_axis("abstention", corpus=tmp_path / "nothing.yaml")
    assert result.status is AxisStatus.NOT_MEASURED


# ------------------------------------------------------------------------------------------------
# every axis states its n, its provenance, and what is wrong with it
# ------------------------------------------------------------------------------------------------


def test_every_measured_axis_carries_n_provenance_and_at_least_one_caveat(results) -> None:
    for result in results.values():
        if result.status is not AxisStatus.MEASURED:
            continue
        assert result.n > 0, result.axis
        assert result.provenance, result.axis
        assert result.caveats, result.axis


def test_a_constructed_axis_says_constructed(results) -> None:
    assert "CONSTRUCTED" in " ".join(results["supersession"].caveats).upper()


def test_the_thin_axis_says_how_thin_it_is(results) -> None:
    compound = results["compound_values"]
    assert compound.n < 30
    assert any("decide nothing" in c for c in compound.caveats)
    assert "95ci" in " ".join(compound.metrics)


# ------------------------------------------------------------------------------------------------
# the axes' own content
# ------------------------------------------------------------------------------------------------


def test_the_class_axis_scores_the_must_abstain_cases_separately(results) -> None:
    assert results["class_assignment"].metrics["must_abstain_held"] == "7/7"


def test_the_supersession_axis_requires_a_broken_history_to_raise(results) -> None:
    outcomes = results["supersession"].metrics["outcomes"]
    assert outcomes["forked history must raise"] == "raised"
    assert outcomes["cyclic history must raise"] == "raised"
    assert outcomes["linear chain, head is the last claim"] == "25 A"


def test_the_supersession_axis_reads_order_from_supersedes_not_from_file_order(results) -> None:
    outcomes = results["supersession"].metrics["outcomes"]
    key = "same chain shuffled -- order comes from supersedes, not file order"
    assert outcomes[key] == "25 A"


def test_the_crosswalk_axis_scores_silence_on_unmapped_codes(results) -> None:
    crosswalk = results["crosswalk"]
    assert crosswalk.metrics["unmapped_codes_abstained"] == "3/3"
    assert crosswalk.metrics["codes_delivering_nothing"] == "none"


def test_axis_results_serialise_without_losing_the_caveats(results) -> None:
    payload = results["grounding"].as_dict()
    assert payload["status"] == "MEASURED"
    assert payload["caveats"]
    assert payload["n"] == 1426
