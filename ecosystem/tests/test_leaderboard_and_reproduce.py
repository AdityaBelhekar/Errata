"""FR-9.9 and the exit criterion: the table prints our losses, and the receipt pins our numbers.

The leaderboard's requirement is a social one enforced structurally -- *the published leaderboard
includes our own losing scores* -- so the tests here are about what the generator cannot do:
it cannot produce a table without our row, it cannot produce one where a loss has been dropped,
and it cannot turn "nobody else measures this" into a win.
"""

from __future__ import annotations

import json

import pytest

from errata_ecosystem.axes import AxisStatus, run_all
from errata_ecosystem.leaderboard import (
    NOT_SCORED,
    leaderboard,
    losses,
    render_html,
    render_json,
    render_text,
)
from errata_ecosystem.reproduce import PUBLISHED, PUBLISHED_GOLD, Verdict, reproduce
from errata_ecosystem.reviewer import report as reviewer_report


@pytest.fixture(scope="module")
def axes():
    return run_all()


@pytest.fixture(scope="module")
def board(axes):
    return leaderboard(axes, reviewer_report(()))


# ------------------------------------------------------------------------------------------------
# FR-9.9
# ------------------------------------------------------------------------------------------------


def test_our_row_is_in_the_table_and_is_not_first(board) -> None:
    rank = board.our_rank("word_grounding_f1")
    assert rank is not None
    position, total = rank
    assert total >= 8
    assert position == 2, "we are second on word-level grounding; if that changed, say so here"


def test_the_losses_section_is_not_empty_and_names_the_system_that_beats_us(board) -> None:
    sentences = losses(board)
    assert sentences
    assert any("LE Agentic Plus" in s and "beats Errata" in s for s in sentences)
    assert any("value F1" in s for s in sentences)


def test_the_biggest_loss_is_printed_rather_than_the_smallest(board) -> None:
    """Value F1 is where we lose by 28 points. A table that showed only the near-tie on grounding
    would be true and misleading, which is the failure mode FR-9.9 exists to prevent."""
    text = render_text(board)
    assert "value F1" in text
    assert "95.60" in text and "67.15" in text


def test_a_metric_nobody_else_reports_is_not_scored_rather_than_zero(board) -> None:
    """Rendering 'not scored' as 0.0 would manufacture a win on five axes at once."""
    text = render_text(board)
    assert NOT_SCORED in text
    for row in board.rows:
        if row.system == "LE Cost-Eff.":
            assert row.value_f1 is None
            assert row.cell("value_f1") == NOT_SCORED


def test_a_measured_zero_is_still_printed_as_zero(board) -> None:
    """ExtractBench's Table 3 records 0.0 for systems returning no boxes. That is a measurement."""
    row = next(r for r in board.rows if r.system == "all other evaluated systems")
    assert row.word_grounding_f1 == 0.0
    assert "8 of 14" in row.note


def test_the_corpus_caveat_travels_with_the_table(board) -> None:
    for rendered in (render_text(board), render_html(board)):
        assert "different corpora" in rendered
        assert "370 documents" in rendered


def test_the_two_human_numbers_are_reported_alongside_grounding(board) -> None:
    """FR-9.4 says 'reported alongside grounding F1'. NOT MEASURED is a report."""
    text = render_text(board)
    assert "evidence-acceptance rate" in text
    assert "NOT MEASURED" in text


def test_rendering_is_deterministic(board) -> None:
    assert render_text(board) == render_text(board)
    assert render_json(board) == render_json(board)


def test_the_json_render_is_json(board) -> None:
    payload = json.loads(render_json(board))
    assert payload["our_rank_word_grounding_f1"] == [2, 8]
    assert payload["losses"]
    assert len(payload["axes"]) == 6


def test_the_html_marks_our_row_so_a_reader_can_find_it(board) -> None:
    html = render_html(board)
    assert 'class="ours"' in html
    assert "Where we lose" in html
    assert "no hand-editing step" in html


# ------------------------------------------------------------------------------------------------
# the exit criterion
# ------------------------------------------------------------------------------------------------


def test_every_published_value_names_a_metric_the_axis_actually_produces(axes) -> None:
    """A pin that names a key nobody emits would pass forever without checking anything."""
    by_id = {a.axis: a for a in axes}
    for axis_id, expectations in PUBLISHED.items():
        result = by_id[axis_id]
        if result.status is not AxisStatus.MEASURED:  # pragma: no cover - needs the fetched data
            continue
        for key in expectations:
            if key == "n":
                continue
            assert key in result.metrics, f"{axis_id}.{key} is pinned but not emitted"


def test_the_repository_reproduces_its_own_published_scores() -> None:
    receipt = reproduce()
    if receipt.verdict is Verdict.INCOMPLETE:  # pragma: no cover - needs the fetched data
        pytest.skip("reference data absent on this machine")
    assert receipt.verdict is Verdict.REPRODUCED, "\n".join(
        c.line() for c in receipt.failures
    )
    assert len(receipt.checks) >= 24


def test_the_receipt_hashes_every_input_the_numbers_depend_on() -> None:
    receipt = reproduce()
    for key in ("corpus", "gold_annotations", "hard_tail_split", "bridge", "unspsc_codeset"):
        assert key in receipt.inputs
        assert receipt.inputs[key] != "ABSENT", key
        assert len(receipt.inputs[key]) == 64


def test_the_receipt_records_the_versions_that_produced_the_numbers() -> None:
    environment = reproduce().environment
    assert environment["errata-ecosystem"] == "0.1.0"
    assert environment["python"].startswith("3.")


def test_no_third_party_attestation_is_claimed() -> None:
    """The exit criterion is 'a THIRD PARTY reproduces'. This is the line that would have to
    change for that to be claimed, and changing it without a receipt would be a fabrication."""
    from errata_ecosystem.reproduce import THIRD_PARTY_ATTESTATIONS

    assert THIRD_PARTY_ATTESTATIONS == ()
    assert "NO THIRD PARTY HAS RUN THIS" in reproduce().text()


def test_a_missing_corpus_makes_the_verdict_incomplete_not_reproduced(tmp_path) -> None:
    receipt = reproduce(corpus=tmp_path / "absent.yaml")
    assert receipt.verdict is Verdict.INCOMPLETE
    assert any("grounding" in note for note in receipt.notes)


def test_the_gold_pins_match_the_gold_set_that_ships() -> None:
    from errata_ecosystem.goldset import load_gold_set

    assert len(load_gold_set()) == PUBLISHED_GOLD["records"]
