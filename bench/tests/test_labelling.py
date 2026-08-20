"""FR-0.1's independent dual-labelling packet, and the agreement arithmetic.

The gate's headline number is not quotable outside this repository until a second labeller who
did not write the comparator has been through the suite. This module is the mechanical half of
that; these tests exist mostly to guard the one property that makes the packet worth anything --
that it does not leak the first labeller's answers.

No real dual-labelling has been performed. Nothing here reports an agreement figure for the
actual suite, and none should be quoted until a packet comes back from a human.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from errata_bench.equivalence import Case, Label, load_cases
from errata_bench.labelling import (
    PACKET_FIELDS,
    build_packet,
    cohen_kappa,
    render_agreement,
    score_packet,
    write_packet,
)

#: Fields that encode the first labeller's answer or their reasoning. If any of these reaches the
#: packet, the second labelling is a confirmation exercise and FR-0.1 is not satisfied.
LEAKING_FIELDS = ("expect", "expect_alternatives", "source", "rationale", "label_hint", "origin")


def _write(path: Path, cases: list[Case], labels: list[str]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PACKET_FIELDS)
        writer.writeheader()
        for case, label in zip(cases, labels, strict=True):
            writer.writerow(
                {
                    "case_id": case.id,
                    "family": case.family,
                    "attribute": "",
                    "value_a": case.a,
                    "value_b": case.b,
                    "label": label,
                    "note": "",
                }
            )
    return path


def test_packet_covers_every_case() -> None:
    assert len(build_packet()) == len(load_cases())


def test_packet_does_not_leak_the_existing_labels() -> None:
    """The single property this whole module exists for."""
    for row in build_packet():
        for field in LEAKING_FIELDS:
            assert field not in row, f"packet leaks {field!r} -- the labelling would be an echo"
        assert row["label"] == "", "the label column must come back empty"
        assert row["note"] == ""


def test_written_packet_round_trips_through_csv(tmp_path: Path) -> None:
    path = write_packet(tmp_path / "packet.csv")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(load_cases())
    assert tuple(rows[0]) == PACKET_FIELDS


def test_the_instructions_are_written_next_to_the_packet(tmp_path: Path) -> None:
    """A CSV of bare value pairs with no instructions gets labelled inconsistently, and the
    inconsistency is then read as a finding about the suite rather than about the packet."""
    path = write_packet(tmp_path / "packet.csv")
    readme = path.with_suffix(".README.txt")
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "did NOT write the comparator" in text
    for label in Label:
        assert label.value in text, f"the labeller is not told about {label.value}"


def test_scoring_a_perfect_packet_agrees_completely(tmp_path: Path) -> None:
    cases = load_cases()
    path = _write(tmp_path / "perfect.csv", cases, [c.expect.value for c in cases])
    report = score_packet(path)
    assert report.n == len(cases)
    assert report.agreed == len(cases)
    assert report.raw_agreement == 1.0
    assert report.kappa == pytest.approx(1.0)
    assert report.disagreements == ()


def test_scoring_flags_disagreements_without_privileging_either_labeller(tmp_path: Path) -> None:
    """The suite's label is not the marking scheme. If the independent labeller is right and the
    suite is wrong, that is a suite finding, and it is the more valuable of the two outcomes."""
    cases = load_cases()[:20]
    labels = [
        Label.UNDETERMINED.value if i % 4 == 0 else c.expect.value for i, c in enumerate(cases)
    ]
    report = score_packet(_write(tmp_path / "mixed.csv", cases, labels), cases)
    assert report.disagreements
    for case_id, ours, theirs in report.disagreements:
        assert ours != theirs
        assert case_id in {c.id for c in cases}


def test_blank_labels_are_excluded_and_reported(tmp_path: Path) -> None:
    """A half-filled packet measures the labeller's stamina, not the suite. Counting blanks as
    agreement or as disagreement would both be wrong; they are excluded and named."""
    cases = load_cases()[:10]
    labels = ["" if i < 4 else c.expect.value for i, c in enumerate(cases)]
    report = score_packet(_write(tmp_path / "partial.csv", cases, labels), cases)
    assert report.n == 6
    assert len(report.unlabelled) == 4
    assert any("without a label" in c for c in report.caveats)


def test_an_unknown_case_id_is_refused_rather_than_skipped(tmp_path: Path) -> None:
    """Silently dropping an unrecognised row would let a packet drift from the suite and still
    produce a confident agreement figure."""
    path = tmp_path / "drifted.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PACKET_FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                "case_id": "no-such-case", "family": "x", "attribute": "",
                "value_a": "a", "value_b": "b", "label": "equivalent", "note": "",
            }
        )
    with pytest.raises(KeyError, match="does not match any case"):
        score_packet(path)


def test_an_unknown_label_is_refused(tmp_path: Path) -> None:
    cases = load_cases()[:1]
    path = _write(tmp_path / "bad-label.csv", cases, ["probably fine"])
    with pytest.raises(ValueError, match="not one of"):
        score_packet(path)


# -- the kappa arithmetic -------------------------------------------------------------------


def test_kappa_is_one_for_perfect_agreement_on_a_mixed_distribution() -> None:
    pairs = [(Label.EQUIVALENT, Label.EQUIVALENT)] * 5
    pairs += [(Label.CONTRADICTION, Label.CONTRADICTION)] * 5
    assert cohen_kappa(pairs) == pytest.approx(1.0)


def test_kappa_is_zero_when_everything_is_one_category() -> None:
    """Expected agreement is 1.0 and kappa is undefined there. Returning 0 says "this measured
    nothing", which is true. Returning 1.0 would claim perfect agreement from a labelling that
    had no opportunity to disagree."""
    assert cohen_kappa([(Label.EQUIVALENT, Label.EQUIVALENT)] * 20) == 0.0


def test_kappa_is_near_zero_for_chance_agreement() -> None:
    """The reason kappa is reported at all: two labellers who both mostly guess the majority
    class agree often and establish nothing."""
    pairs = [(Label.EQUIVALENT, Label.EQUIVALENT)] * 90
    pairs += [(Label.CONTRADICTION, Label.EQUIVALENT)] * 5
    pairs += [(Label.EQUIVALENT, Label.CONTRADICTION)] * 5
    assert cohen_kappa(pairs) < 0.1


def test_high_agreement_with_low_kappa_produces_a_caveat(tmp_path: Path) -> None:
    """Otherwise the agreement figure gets quoted on its own and reads as validation."""
    cases = [c for c in load_cases() if c.expect is Label.EQUIVALENT][:40]
    assert len(cases) >= 20, "suite no longer has enough equivalent cases to build the scenario"
    report = score_packet(
        _write(tmp_path / "lopsided.csv", cases, [Label.EQUIVALENT.value] * len(cases)), cases
    )
    assert report.raw_agreement == 1.0
    assert report.kappa == 0.0
    assert any("lopsided" in c or "kappa" in c for c in report.caveats)


def test_render_agreement_names_every_disagreement(tmp_path: Path) -> None:
    cases = load_cases()[:8]
    labels = [Label.UNDETERMINED.value if i == 0 else c.expect.value for i, c in enumerate(cases)]
    report = score_packet(_write(tmp_path / "r.csv", cases, labels), cases)
    text = render_agreement(report)
    assert "Cohen's kappa" in text
    for case_id, _, _ in report.disagreements:
        assert case_id in text
