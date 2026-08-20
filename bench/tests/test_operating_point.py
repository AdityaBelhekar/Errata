"""Tests for the R0 kill test 2 measurement machinery (FR-0.3, operating_point.py).

RULER-CALIBRATION FIXTURES ONLY
--------------------------------
Every corpus, box, and triple built in this file is a hand-constructed fixture with a known,
hand-verified answer -- used to prove the metric arithmetic is correct. None of it is dressed up as
a measurement of a real audit. Where a "looks empirical" corpus is needed (to exercise the
EMPIRICAL code path of asymmetry_verdict), it is explicitly labelled in the test name and docstring
as a fixture with an engineered outcome, never as real data. The one real assertion this file makes
about the actual product is: on synthetic/fixture input, the verdict is NOT_MEASURED, always,
with no exceptions -- that is the whole point of this gate.
"""

from __future__ import annotations

from fractions import Fraction
from itertools import pairwise

import pytest

from errata_bench.operating_point import (
    DEFAULT_COVERAGE_POINTS,
    EXTRACTBENCH_WORD_GROUNDING_F1,
    GROUNDING_IOU_THRESHOLD,
    MIN_RECORDS_FOR_VERDICT,
    AsymmetryVerdict,
    BoundingBox,
    GroundingLevel,
    MCBCorpus,
    MCBRecord,
    Provenance,
    asymmetry_verdict,
    aurc,
    grounding_f1,
    load_corpus,
    operating_point_report,
    precision_at_coverage,
    render_report,
    report_as_dict,
    risk_coverage_curve,
    selective_accuracy_at_coverage,
    synthetic_corpus,
    value_f1,
)
from errata_bench.stats import wilson

BASELINE_FRACTION = EXTRACTBENCH_WORD_GROUNDING_F1 / 100.0


# ================================================================================================
# BoundingBox / IoU
# ================================================================================================


def test_iou_identical_boxes_is_one() -> None:
    box = BoundingBox(0, 0, 10, 10)
    assert box.iou(BoundingBox(0, 0, 10, 10)) == pytest.approx(1.0)


def test_iou_disjoint_boxes_is_zero() -> None:
    a = BoundingBox(0, 0, 10, 10)
    b = BoundingBox(20, 20, 30, 30)
    assert a.iou(b) == 0.0
    assert b.iou(a) == 0.0  # symmetric


def test_iou_partial_overlap_hand_computed() -> None:
    # box a: (0,0)-(10,10), area 100. box b: (5,5)-(15,15), area 100.
    # intersection: (5,5)-(10,10) -> 5 * 5 = 25.
    # union = 100 + 100 - 25 = 175.
    # IoU = 25 / 175 = 1/7.
    a = BoundingBox(0, 0, 10, 10)
    b = BoundingBox(5, 5, 15, 15)
    assert a.intersection_area(b) == pytest.approx(25.0)
    assert a.iou(b) == pytest.approx(1.0 / 7.0)
    assert b.iou(a) == pytest.approx(1.0 / 7.0)


def test_iou_exact_half_boundary_is_included() -> None:
    # box a: (0,0)-(10,10), area 100. box b: (0,0)-(10,20), area 200.
    # intersection is all of a (b fully contains a's footprint in x, and a's y-range fits inside
    # b's) -> intersection area 100. union = 100 + 200 - 100 = 200. IoU = 100/200 = 0.5 EXACTLY.
    a = BoundingBox(0, 0, 10, 10)
    b = BoundingBox(0, 0, 10, 20)
    assert a.iou(b) == pytest.approx(0.5)
    # ExtractBench's stated threshold is ">= IoU 0.5" -- exactly 0.5 must count as grounded.
    assert a.iou(b) >= GROUNDING_IOU_THRESHOLD


def test_iou_just_below_half_boundary_is_excluded() -> None:
    # Same construction, but b's height is 21 instead of 20: intersection still 100 (a's 10-unit
    # height fits inside b's 21), union = 100 + 10*21 - 100 = 210. IoU = 100/210 = 10/21 ~ 0.4762,
    # strictly below 0.5.
    a = BoundingBox(0, 0, 10, 10)
    b = BoundingBox(0, 0, 10, 21)
    iou = a.iou(b)
    assert iou == pytest.approx(10.0 / 21.0)
    assert iou < GROUNDING_IOU_THRESHOLD


def test_iou_zero_area_box_does_not_divide_by_zero() -> None:
    # A degenerate (zero-area) box against itself is 0/0 in the strict definition. This resolves
    # to 0.0 (documented, deliberate choice), never raises, and never claims a perfect match.
    point = BoundingBox(5, 5, 5, 5)
    assert point.area == 0.0
    assert point.iou(point) == 0.0
    assert point.iou(BoundingBox(0, 0, 10, 10)) == 0.0


def test_bounding_box_rejects_malformed_coordinates() -> None:
    with pytest.raises(ValueError):
        BoundingBox(10, 0, 0, 10)  # x1 < x0
    with pytest.raises(ValueError):
        BoundingBox(0, 10, 10, 0)  # y1 < y0


# ================================================================================================
# grounding_f1
# ================================================================================================


def _record(
    attribute_id: str,
    *,
    gold_value: str = "16 A",
    gold_box: BoundingBox | None = BoundingBox(0, 0, 10, 10),
    gold_page: int = 3,
    predicted_value: str | None = "16 A",
    predicted_box: BoundingBox | None = BoundingBox(0, 0, 10, 10),
    predicted_page: int | None = 3,
    confidence: float = 0.9,
    is_disagreement_predicted: bool = False,
    is_disagreement_actual: bool = False,
) -> MCBRecord:
    return MCBRecord(
        attribute_id=attribute_id,
        gold_value=gold_value,
        gold_evidence_boxes=(gold_box,) if gold_box is not None else (),
        gold_page=gold_page,
        predicted_value=predicted_value,
        predicted_box=predicted_box,
        predicted_page=predicted_page,
        confidence=confidence,
        is_disagreement_predicted=is_disagreement_predicted,
        is_disagreement_actual=is_disagreement_actual,
    )


def test_grounding_f1_word_level_hand_computed() -> None:
    """5 records, hand-verified precision/recall/F1.

    r1: value accepted, box matches (IoU 1.0)          -> grounded-correct (TP)
    r2: value accepted, box WRONG (disjoint, IoU 0.0)   -> NOT grounded-correct (value right,
                                                            box wrong -- must not count)
    r3: value WRONG, box matches                        -> NOT grounded-correct (value must also
                                                            be accepted)
    r4: abstained (predicted_value is None)              -> not in predicted_total; still in
                                                            gold_total (a recall miss)
    r5: value accepted, box matches                      -> grounded-correct (TP)

    gold_total = 5 (every record).
    predicted_total = 4 (every record except the abstention, r4).
    true_positives = 2 (r1, r5).

    precision = TP / predicted_total = 2 / 4 = 0.5
    recall    = TP / gold_total      = 2 / 5 = 0.4
    F1        = 2 * 0.5 * 0.4 / (0.5 + 0.4) = 0.4 / 0.9 = 4/9 = 0.44444...
    """
    off_box = BoundingBox(50, 50, 60, 60)  # disjoint from the (0,0,10,10) gold box
    records = [
        _record("r1", predicted_value="16 A", predicted_box=BoundingBox(0, 0, 10, 10)),
        _record("r2", predicted_value="16 A", predicted_box=off_box),
        _record("r3", predicted_value="20 A", predicted_box=BoundingBox(0, 0, 10, 10)),
        _record("r4", predicted_value=None, predicted_box=None, predicted_page=None),
        _record("r5", predicted_value="16 A", predicted_box=BoundingBox(0, 0, 10, 10)),
    ]
    result = grounding_f1(records, level=GroundingLevel.WORD)
    assert result.gold_total == 5
    assert result.predicted_total == 4
    assert result.true_positives == 2
    assert result.precision.point == pytest.approx(0.5)
    assert result.recall.point == pytest.approx(0.4)
    assert result.f1 == pytest.approx(4.0 / 9.0)


def test_grounding_f1_value_correct_box_wrong_is_not_grounded() -> None:
    """Isolates r2's condition from the hand-computed test: correct value, wrong box."""
    off_box = BoundingBox(50, 50, 60, 60)
    record = _record("only", predicted_value="16 A", predicted_box=off_box)
    assert record.value_accepted is True
    assert record.grounded(GroundingLevel.WORD) is False
    assert record.grounded_correct(GroundingLevel.WORD) is False
    result = grounding_f1([record], level=GroundingLevel.WORD)
    assert result.true_positives == 0


def test_grounding_f1_zero_gold_evidence_resolves_sensibly() -> None:
    """A gold field with NO evidence boxes can never be word-level grounded, even when the value
    is right and a predicted box exists: any(()) is False, no division, no exception. It still
    counts as a gold field (recall denominator) and as a prediction (precision denominator), but
    never as a true positive at word level -- there is nothing on the gold side to overlap.
    """
    record = _record(
        "no-evidence",
        gold_box=None,
        predicted_value="16 A",
        predicted_box=BoundingBox(0, 0, 10, 10),
    )
    assert record.gold_evidence_boxes == ()
    assert record.grounded(GroundingLevel.WORD) is False  # must not raise
    result = grounding_f1([record], level=GroundingLevel.WORD)
    assert result.gold_total == 1
    assert result.predicted_total == 1
    assert result.true_positives == 0
    assert result.precision.point == 0.0
    assert result.recall.point == 0.0


def test_grounding_f1_page_level() -> None:
    records = [
        _record("right-page", predicted_page=3, gold_page=3),  # value accepted by default
        _record("wrong-page", predicted_page=4, gold_page=3),
        _record("no-page-cited", predicted_page=None, gold_page=3),
    ]
    result = grounding_f1(records, level=GroundingLevel.PAGE)
    assert result.gold_total == 3
    assert result.predicted_total == 3  # all three carry a predicted VALUE
    assert result.true_positives == 1


def test_grounding_f1_empty_input_does_not_divide_by_zero() -> None:
    result = grounding_f1([], level=GroundingLevel.WORD)
    assert result.gold_total == 0
    assert result.predicted_total == 0
    assert result.true_positives == 0
    assert result.precision.point == 0.0
    assert result.recall.point == 0.0
    assert result.f1 == 0.0
    assert result.conservative_f1 == 0.0


def test_value_f1_ignores_grounding_entirely() -> None:
    off_box = BoundingBox(50, 50, 60, 60)
    records = [
        _record("right-value-wrong-box", predicted_value="16 A", predicted_box=off_box),
        _record("wrong-value", predicted_value="20 A"),
    ]
    result = value_f1(records)
    assert result.true_positives == 1  # only value matters here
    assert result.gold_total == 2
    assert result.predicted_total == 2


# ================================================================================================
# Risk-coverage curve / AURC / selective accuracy
# ================================================================================================


def test_risk_coverage_curve_perfectly_calibrated_is_non_decreasing() -> None:
    """A perfectly calibrated predictor -- every correct item outranks every incorrect one --
    produces a NON-DECREASING risk curve.

    Why non-decreasing and not non-increasing: while only correct items are covered, the error
    count stays 0, so risk stays 0 (flat, which trivially satisfies non-decreasing). Once coverage
    passes the fraction of correct items, every additional covered item is an error, and for a
    fixed positive error increment per step, errors/i is increasing in i (adding one more error to
    a shrinking-relative-weight denominator cannot decrease the ratio once errors are being added
    every step). So risk can only stay flat or rise as coverage grows -- it can never fall.
    """
    # 6 items, confidence strictly decreasing, sorted correct-before-incorrect already.
    triples = [
        ("p0", 0.99, True),
        ("p1", 0.90, True),
        ("p2", 0.80, True),
        ("p3", 0.50, False),
        ("p4", 0.30, False),
        ("p5", 0.10, False),
    ]
    curve = risk_coverage_curve(triples)
    risks = [point.risk for point in curve]
    assert all(b >= a for a, b in pairwise(risks)), f"risk curve not non-decreasing: {risks}"
    # first three covered items are all correct -> risk stays at 0 through coverage 0.5
    assert curve[3].risk == 0.0  # coverage 3/6 = 0.5, still all-correct
    # once incorrect items are forced in, risk becomes strictly positive
    assert curve[4].risk > 0.0


def test_risk_coverage_curve_shape_and_ties_are_stable() -> None:
    triples = [("a", 0.5, True), ("b", 0.5, False)]
    curve = risk_coverage_curve(triples)
    assert len(curve) == 3  # coverage=0 plus one point per item
    assert curve[0] == pytest.approx((0.0, 0.0), rel=1e-9) or (
        curve[0].coverage == 0.0 and curve[0].risk == 0.0
    )
    assert curve[-1].coverage == 1.0
    assert curve[-1].n_covered == 2


def test_risk_coverage_curve_empty_input() -> None:
    curve = risk_coverage_curve([])
    assert len(curve) == 1
    assert curve[0].coverage == 0.0
    assert curve[0].risk == 0.0


def test_aurc_linear_risk_coverage_relationship_closed_form() -> None:
    """A linear risk-coverage relationship risk(c) = c has a closed-form AURC: the area under the
    line from (0,0) to (1,1) is a right triangle of base 1 and height 1 -> area 0.5. Trapezoidal
    integration is exact for a linear function, so this must come back exactly 0.5 (to floating
    point precision), not merely approximately.
    """
    from errata_bench.operating_point import RiskCoveragePoint

    curve = tuple(
        RiskCoveragePoint(coverage=c, risk=c, n_covered=int(c * 100), n_errors=int(c * 100))
        for c in (0.0, 0.25, 0.5, 0.75, 1.0)
    )
    assert aurc(curve) == pytest.approx(0.5)


def test_aurc_hand_verified_from_triples() -> None:
    """4 items, confidences already best-first, correctness [True, True, False, False].

    Curve points (coverage, risk):
      (0,    0)
      (0.25, 0)      -- 1 correct covered, 0 errors
      (0.5,  0)      -- 2 correct covered, 0 errors
      (0.75, 1/3)    -- 3rd item wrong: 1 error / 3 covered
      (1.0,  0.5)    -- 4th item wrong: 2 errors / 4 covered

    Trapezoidal area, computed exactly with Fraction and cross-checked here:
      seg (0->0.25):   width 0.25 * avg(0,0)      = 0
      seg (0.25->0.5): width 0.25 * avg(0,0)      = 0
      seg (0.5->0.75): width 0.25 * avg(0, 1/3)   = 1/24
      seg (0.75->1.0): width 0.25 * avg(1/3, 1/2) = 5/48
      total = 1/24 + 5/48 = 2/48 + 5/48 = 7/48 ~= 0.14583333
    """
    triples = [("a", 0.9, True), ("b", 0.8, True), ("c", 0.5, False), ("d", 0.1, False)]
    curve = risk_coverage_curve(triples)
    expected = Fraction(7, 48)
    assert aurc(curve) == pytest.approx(float(expected), abs=1e-9)


def test_selective_accuracy_at_coverage_boundaries() -> None:
    triples = [("a", 0.9, True), ("b", 0.7, False), ("c", 0.5, True), ("d", 0.3, False)]
    at_zero = selective_accuracy_at_coverage(triples, 0.0)
    assert at_zero.total == 0  # n/a: nothing covered, nothing to be accurate about

    at_full = selective_accuracy_at_coverage(triples, 1.0)
    assert at_full.total == 4
    assert at_full.successes == 2  # 2 of 4 are correct overall


def test_selective_accuracy_at_coverage_picks_top_confidence_slice() -> None:
    # top 50% by confidence (2 of 4 items) are both correct.
    triples = [("a", 0.9, True), ("b", 0.8, True), ("c", 0.5, False), ("d", 0.3, False)]
    result = selective_accuracy_at_coverage(triples, 0.5)
    assert result.successes == 2
    assert result.total == 2
    assert result.point == pytest.approx(1.0)


def test_selective_accuracy_rejects_out_of_range_coverage() -> None:
    with pytest.raises(ValueError):
        selective_accuracy_at_coverage([("a", 0.5, True)], 1.5)
    with pytest.raises(ValueError):
        selective_accuracy_at_coverage([("a", 0.5, True)], -0.1)


# ================================================================================================
# precision_at_coverage -- disagreement-detection precision (a different question from grounding)
# ================================================================================================


def test_precision_at_coverage_boundary_zero() -> None:
    triples = [(True, 0.9, True), (True, 0.5, False)]
    result = precision_at_coverage(triples, 0.0)
    assert result.total == 0  # nothing covered -> n/a


def test_precision_at_coverage_boundary_full() -> None:
    # 4 records, top 100% = everything. Raised: a (real), b (not real), c (real). d not raised.
    triples = [
        (True, 0.9, True),  # raised, real -> correct
        (True, 0.8, False),  # raised, not real -> wrong
        (True, 0.6, True),  # raised, real -> correct
        (False, 0.4, True),  # not raised -- does not count for precision
    ]
    result = precision_at_coverage(triples, 1.0)
    assert result.total == 3  # 3 raised disagreements
    assert result.successes == 2  # 2 of them real


def test_precision_at_coverage_restricts_to_top_slice_by_confidence() -> None:
    # top 50% (2 of 4) by confidence: the two highest-confidence records only.
    triples = [
        (True, 0.95, True),  # covered, raised, real
        (True, 0.90, False),  # covered, raised, not real
        (True, 0.20, True),  # NOT covered (low confidence) -- must not count
        (False, 0.10, False),  # NOT covered
    ]
    result = precision_at_coverage(triples, 0.5)
    assert result.total == 2  # only the two raised-and-covered records
    assert result.successes == 1


def test_precision_at_coverage_is_a_different_question_than_grounding_f1() -> None:
    """A record can be perfectly grounded (right value, right box) while being a wrongly-raised
    disagreement, and vice versa -- the two metrics must not be conflated into one number.
    """
    off_box = BoundingBox(90, 90, 99, 99)
    # Grounded correctly (value + box both right), but wrongly flagged as a disagreement.
    grounded_but_wrong_flag = _record(
        "g1",
        predicted_value="16 A",
        predicted_box=BoundingBox(0, 0, 10, 10),
        is_disagreement_predicted=True,
        is_disagreement_actual=False,
    )
    # Correctly flagged as a real disagreement, but the box offered is nowhere near the evidence.
    flag_right_grounding_wrong = _record(
        "g2",
        predicted_value="16 A",
        predicted_box=off_box,
        is_disagreement_predicted=True,
        is_disagreement_actual=True,
    )
    records = [grounded_but_wrong_flag, flag_right_grounding_wrong]
    grounding_result = grounding_f1(records, level=GroundingLevel.WORD)
    disagreement_triples = [
        (r.is_disagreement_predicted, r.confidence, r.is_disagreement_actual) for r in records
    ]
    precision_result = precision_at_coverage(disagreement_triples, 1.0)

    # Grounding: g1 grounded-correct (TP), g2 not (box wrong) -> 1/2 true positives.
    assert grounding_result.true_positives == 1
    # Disagreement precision: both raised; only g2's flag was real -> 1/2.
    assert precision_result.successes == 1
    assert precision_result.total == 2
    # And critically: they disagree about WHICH record was the "good" one -- g1 is grounding-good/
    # disagreement-bad, g2 is the reverse. A single conflated metric could not represent this.


# ================================================================================================
# MCBRecord / MCBCorpus / load_corpus
# ================================================================================================


def test_mcb_corpus_rejects_duplicate_attribute_ids() -> None:
    with pytest.raises(ValueError):
        MCBCorpus(records=(_record("dup"), _record("dup")))


def test_mcb_record_rejects_confidence_out_of_range() -> None:
    with pytest.raises(ValueError):
        _record("bad", confidence=1.5)


def test_load_corpus_yaml_round_trip(tmp_path) -> None:
    yaml_text = """
name: test-corpus
provenance: empirical
source: unit test fixture
notes:
  - a note
records:
  - attribute_id: r1
    gold_value: "16 A"
    gold_page: 3
    gold_evidence_boxes:
      - {x0: 0, y0: 0, x1: 10, y1: 10}
    predicted_value: "16 A"
    predicted_page: 3
    predicted_box: {x0: 0, y0: 0, x1: 10, y1: 10}
    confidence: 0.9
    is_disagreement_predicted: false
    is_disagreement_actual: false
  - attribute_id: r2
    gold_value: "20 A"
    gold_page: 1
    predicted_value: null
    predicted_page: null
    confidence: 0.1
    is_disagreement_predicted: false
    is_disagreement_actual: true
"""
    path = tmp_path / "corpus.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    corpus = load_corpus(path)
    assert corpus.size == 2
    assert corpus.provenance is Provenance.EMPIRICAL
    assert corpus.is_synthetic is False
    r1 = next(r for r in corpus.records if r.attribute_id == "r1")
    assert r1.gold_evidence_boxes == (BoundingBox(0, 0, 10, 10),)
    r2 = next(r for r in corpus.records if r.attribute_id == "r2")
    assert r2.predicted_value is None
    assert r2.predicted_page is None


def test_load_corpus_csv_round_trip(tmp_path) -> None:
    csv_text = (
        "attribute_id,gold_value,gold_page,gold_evidence_boxes,predicted_value,predicted_page,"
        "predicted_box,confidence,is_disagreement_predicted,is_disagreement_actual\n"
        "r1,16 A,3,0:0:10:10,16 A,3,0:0:10:10,0.9,false,false\n"
        "r2,20 A,1,,,,,0.1,false,true\n"
    )
    path = tmp_path / "corpus.csv"
    path.write_text(csv_text, encoding="utf-8")
    corpus = load_corpus(path, provenance=Provenance.EMPIRICAL)
    assert corpus.size == 2
    r1 = next(r for r in corpus.records if r.attribute_id == "r1")
    assert r1.gold_evidence_boxes == (BoundingBox(0, 0, 10, 10),)
    assert r1.predicted_box == BoundingBox(0, 0, 10, 10)
    r2 = next(r for r in corpus.records if r.attribute_id == "r2")
    assert r2.predicted_value is None
    assert r2.predicted_page is None
    assert r2.is_disagreement_actual is True


def test_load_corpus_defaults_provenance_to_empirical_with_a_note_when_undeclared(tmp_path) -> None:
    yaml_text = """
name: undeclared
records:
  - attribute_id: r1
    gold_value: "16 A"
    gold_page: 1
    predicted_value: "16 A"
    predicted_page: 1
    confidence: 0.5
"""
    path = tmp_path / "corpus.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    corpus = load_corpus(path)
    assert corpus.provenance is Provenance.EMPIRICAL
    assert any("did not declare a provenance" in note for note in corpus.notes)


def test_synthetic_corpus_is_deterministic() -> None:
    a = synthetic_corpus(n=20)
    b = synthetic_corpus(n=20)
    assert a.records == b.records
    assert a.is_synthetic is True


# ================================================================================================
# asymmetry_verdict -- the honesty gate itself
# ================================================================================================


def _all_grounded_correct_records(n: int, *, confidence: float = 0.95) -> tuple[MCBRecord, ...]:
    """RULER-CALIBRATION FIXTURE: n records, every one grounded-correct. Used only to prove the
    gate's arithmetic path, never presented as a real audit result."""
    return tuple(
        _record(f"r{i}", confidence=confidence) for i in range(n)
    )


def test_asymmetry_verdict_is_not_measured_on_default_synthetic_corpus() -> None:
    report = operating_point_report()  # no corpus given -> synthetic_corpus()
    assert report.corpus.is_synthetic
    assert asymmetry_verdict(report) is AsymmetryVerdict.NOT_MEASURED
    assert report.verdict is AsymmetryVerdict.NOT_MEASURED


def test_asymmetry_verdict_is_not_measured_even_when_synthetic_numbers_look_perfect() -> None:
    """RULER-CALIBRATION FIXTURE: rig a SYNTHETIC-flagged corpus where every single record is
    grounded-correct at high confidence -- as good as an operating-point result could ever look.
    The verdict must still be NOT_MEASURED: provenance gates the verdict unconditionally, not the
    numbers. This is the central honesty property of this module.
    """
    records = _all_grounded_correct_records(50)
    corpus = MCBCorpus(records=records, name="rigged-perfect", provenance=Provenance.SYNTHETIC)
    report = operating_point_report(corpus)
    # Sanity: the numbers really do look perfect (so the NOT_MEASURED verdict below isn't an
    # accident of a weak fixture).
    best = report.best_row
    assert best is not None
    assert best.word_grounding.conservative_f1 > BASELINE_FRACTION
    assert asymmetry_verdict(report) is AsymmetryVerdict.NOT_MEASURED


def test_asymmetry_verdict_inconclusive_below_minimum_record_count() -> None:
    n = MIN_RECORDS_FOR_VERDICT - 5
    assert n > 0
    records = _all_grounded_correct_records(n)
    corpus = MCBCorpus(records=records, name="too-small", provenance=Provenance.EMPIRICAL)
    report = operating_point_report(corpus)
    assert asymmetry_verdict(report) is AsymmetryVerdict.INCONCLUSIVE


# Both fixtures below give every record a DISTINCT, strictly-descending confidence
# (0.990, 0.989, 0.988, ...) rather than a shared constant. _top_by_coverage() sorts by
# (-confidence, attribute_id), so with tied confidence the tiebreak falls to attribute_id's
# LEXICOGRAPHIC order -- "r1" < "r10" < "r11" < ... < "r19" < "r2" -- which does not match
# numeric record index. An earlier version of the second fixture below used tied confidence and a
# correctness pattern keyed to numeric index, and got lucky: the lexicographically-first 7 records
# of a 34-record corpus happened to land entirely inside the "correct" half by coincidence,
# silently defeating the trap the test was written to set. Strictly distinct confidence makes the
# sort order equal to construction order with no dependence on string comparison, so the intended
# correctness pattern actually lands where the test says it does.
_DESCENDING_CONFIDENCE = [0.990 - 0.001 * i for i in range(100)]


def test_asymmetry_verdict_confirmed_requires_real_data_and_a_defensible_margin() -> None:
    """RULER-CALIBRATION FIXTURE: 100 EMPIRICAL records, every one grounded-correct.

    best_row is chosen by max conservative_f1 across the three coverage points (20/40/60%); with
    uniform correctness the Wilson lower bound only tightens as n grows, so the 60%-coverage row
    (n_covered=60) wins over the 20% and 40% rows. 60 clears MIN_RECORDS_FOR_VERDICT on its own,
    so this is a defensible CONFIRMED case at the level that actually carries the verdict -- not
    just at the corpus total (see the n_covered=7-of-34 trap the sibling test below is built to
    avoid repeating).

    precision = recall = wilson(60, 60); the Wilson lower bound for 60/60 is comfortably above the
    ExtractBench baseline (46.43%), so conservative_f1 clears it too -- a defensible margin, not
    just a positive point-estimate difference.
    """
    records = tuple(
        _record(f"r{i}", confidence=_DESCENDING_CONFIDENCE[i]) for i in range(100)
    )
    corpus = MCBCorpus(records=records, name="rigged-confirmed", provenance=Provenance.EMPIRICAL)
    report = operating_point_report(corpus)
    best = report.best_row
    assert best is not None
    assert best.coverage == 0.60
    assert best.n_covered == 60
    p = wilson(60, 60)
    assert best.word_grounding.precision.lo == pytest.approx(p.lo)
    assert best.word_grounding.conservative_f1 > BASELINE_FRACTION
    assert asymmetry_verdict(report) is AsymmetryVerdict.ASYMMETRY_CONFIRMED


def test_asymmetry_verdict_not_confirmed_when_point_estimate_beats_baseline_but_interval_does_not() -> None:
    """RULER-CALIBRATION FIXTURE: the honesty case this whole gate exists for.

    100 EMPIRICAL records with PERFECTLY ALTERNATING correctness (even index grounded-correct, odd
    index not), so every prefix -- and so every one of the three coverage rows -- has exactly 50%
    empirical correctness by construction, independent of which prefix length wins as "best". At
    60% coverage (n_covered=60, tp=30): point-estimate F1 = 30/60 = 50%, which LOOKS like it beats
    the 46.43% baseline. But wilson(30, 60) has a lower bound of roughly 37.7% -- well below the
    baseline -- so conservative_f1 (built from precision.lo and recall.lo, equal here since
    predicted_total == gold_total == n_covered) also falls below it. A verdict built off a bare
    "is the point estimate bigger" comparison would wrongly say CONFIRMED here; asymmetry_verdict
    must say NOT_CONFIRMED, because the margin is not statistically defensible at this sample size.

    n_covered=60 at the winning row clears MIN_RECORDS_FOR_VERDICT (30) in its own right, so this
    exercises the "sample is big enough to trust, but the margin still isn't real" path -- distinct
    from test_asymmetry_verdict_inconclusive_below_minimum_record_count, which exercises "the
    sample was never big enough to ask the question at all".
    """
    off_box = BoundingBox(50, 50, 60, 60)
    on_box = BoundingBox(0, 0, 10, 10)
    n = 100
    records = []
    for i in range(n):
        box = on_box if i % 2 == 0 else off_box
        records.append(_record(f"r{i}", confidence=_DESCENDING_CONFIDENCE[i], predicted_box=box))
    corpus = MCBCorpus(records=tuple(records), name="borderline", provenance=Provenance.EMPIRICAL)
    report = operating_point_report(corpus)
    best = report.best_row
    assert best is not None
    assert best.coverage == 0.60
    assert best.n_covered == 60
    assert best.word_grounding.true_positives == 30

    # Confirm the trap is real: the point estimate does look like it clears the baseline...
    assert best.word_grounding.f1 == pytest.approx(0.5)
    assert best.word_grounding.f1 > BASELINE_FRACTION
    # ...but the conservative (Wilson-lower-bound) estimate does not.
    assert best.word_grounding.conservative_f1 < BASELINE_FRACTION
    # ...and specifically not because the sample was too small to ask the question (it clears
    # MIN_RECORDS_FOR_VERDICT); it is NOT_CONFIRMED on the merits, not INCONCLUSIVE on the size.
    assert best.n_covered >= MIN_RECORDS_FOR_VERDICT
    assert asymmetry_verdict(report) is AsymmetryVerdict.ASYMMETRY_NOT_CONFIRMED


def test_asymmetry_verdict_inconclusive_when_only_a_small_lucky_window_is_correct() -> None:
    """REGRESSION PIN for the bug this module shipped with: best_row can win on a row far smaller
    than the corpus total, and a small enough window can look perfect by chance.

    34 records -- comfortably above MIN_RECORDS_FOR_VERDICT (30) as a CORPUS TOTAL. But only the
    first 7 (by confidence) are grounded-correct; everything from record 8 onward is not. The
    20%-coverage row (n_covered=ceil(0.2*34)=7) is then 7-for-7: conservative_f1 = wilson(7, 7).lo
    ~= 64.6%, which clears the 46.43% baseline and would have won as "best" under the pre-fix
    code, which checked only report.corpus.size (34 >= 30) and returned ASYMMETRY_CONFIRMED off a
    seven-record sample. The 40% row (n_covered=14, tp=7, p=0.5) and 60% row (n_covered=21, tp=7,
    p=0.333) are both worse than the 20% row's inflated small-sample estimate, so the 20% row still
    wins best_row even after the fix -- but its n_covered=7 is below MIN_RECORDS_FOR_VERDICT, so
    asymmetry_verdict must now return INCONCLUSIVE rather than trusting it.

    This is the exact shape of the false CONFIRMED this module produced before the n_covered guard
    was added to asymmetry_verdict: a corpus that passes the total-size check while the specific
    row carrying the verdict is built from too few records to mean anything.

    UPDATED 2026-08-19 (finding N9). The verdict no longer reads ``best_row`` at all -- it reads
    the FULL-coverage grounding, because the ExtractBench baseline it is compared against is a
    full-coverage figure and the old comparison was apples to oranges. That change makes this
    whole attack structurally impossible rather than specially guarded: the sample carrying the
    verdict is now always the entire corpus, whose size is already checked.

    So the expected verdict moves from INCONCLUSIVE to ASYMMETRY_NOT_CONFIRMED -- and the
    protection is stronger, not weaker. The seven lucky records can no longer carry anything,
    and the other 27 are counted rather than dropped. The scenario is kept exactly as it was,
    because the thing worth pinning is that a small lucky window **cannot produce a CONFIRMED**,
    and that assertion is now made directly.
    """
    off_box = BoundingBox(50, 50, 60, 60)
    on_box = BoundingBox(0, 0, 10, 10)
    n = 34
    lucky_window = 7
    records = []
    for i in range(n):
        box = on_box if i < lucky_window else off_box
        records.append(_record(f"r{i}", confidence=_DESCENDING_CONFIDENCE[i], predicted_box=box))
    corpus = MCBCorpus(records=tuple(records), name="small-lucky-window", provenance=Provenance.EMPIRICAL)
    report = operating_point_report(corpus)

    # The corpus-level check alone would have let this through.
    assert corpus.size >= MIN_RECORDS_FOR_VERDICT

    best = report.best_row
    assert best is not None
    assert best.coverage == 0.20
    assert best.n_covered == lucky_window
    assert best.word_grounding.conservative_f1 > BASELINE_FRACTION  # the trap: this alone looks confirmable
    assert best.n_covered < MIN_RECORDS_FOR_VERDICT  # ...built on a sample too small to trust

    # The property that actually matters, asserted directly: a lucky window cannot confirm.
    assert asymmetry_verdict(report) is not AsymmetryVerdict.ASYMMETRY_CONFIRMED

    # And the reason is now structural. The verdict is taken over all 34 records, of which 7
    # ground correctly -- nowhere near the baseline -- so it is NOT_CONFIRMED on the merits.
    full = report.full_coverage_grounding
    assert full.true_positives == lucky_window
    assert full.conservative_f1 < BASELINE_FRACTION
    assert asymmetry_verdict(report) is AsymmetryVerdict.ASYMMETRY_NOT_CONFIRMED


def test_asymmetry_verdict_not_confirmed_when_clearly_below_baseline() -> None:
    """100 records, correct every 10th index (10% density, period-10 so every prefix -- and so
    every coverage row -- has the same ~10% empirical rate, clearly below baseline at every n).
    Uniform density across rows means the largest row (60% coverage, n_covered=60) wins best_row
    on the tightest Wilson interval, which also clears MIN_RECORDS_FOR_VERDICT -- so this is
    NOT_CONFIRMED on the merits at a trustworthy sample size, not a coincidence of which row won.
    """
    off_box = BoundingBox(50, 50, 60, 60)
    on_box = BoundingBox(0, 0, 10, 10)
    n = 100
    records = []
    for i in range(n):
        box = on_box if i % 10 == 0 else off_box
        records.append(_record(f"r{i}", confidence=_DESCENDING_CONFIDENCE[i], predicted_box=box))
    corpus = MCBCorpus(records=tuple(records), provenance=Provenance.EMPIRICAL)
    report = operating_point_report(corpus)
    best = report.best_row
    assert best is not None
    assert best.coverage == 0.60
    assert best.n_covered == 60
    assert best.n_covered >= MIN_RECORDS_FOR_VERDICT
    assert best.word_grounding.f1 < BASELINE_FRACTION  # not even the point estimate is close
    assert asymmetry_verdict(report) is AsymmetryVerdict.ASYMMETRY_NOT_CONFIRMED


# ================================================================================================
# operating_point_report / render_report / report_as_dict -- smoke + structural checks
# ================================================================================================


def test_operating_point_report_default_uses_fr_0_3_coverage_points() -> None:
    report = operating_point_report()
    assert tuple(row.coverage for row in report.rows) == DEFAULT_COVERAGE_POINTS
    assert DEFAULT_COVERAGE_POINTS == (0.20, 0.40, 0.60)


def test_operating_point_report_rows_cover_expected_fraction() -> None:
    corpus = MCBCorpus(records=_all_grounded_correct_records(50), provenance=Provenance.EMPIRICAL)
    report = operating_point_report(corpus)
    row20 = report.at(0.20)
    assert row20 is not None
    assert row20.n_covered == 10  # 20% of 50
    row60 = report.at(0.60)
    assert row60 is not None
    assert row60.n_covered == 30  # 60% of 50


def test_render_report_contains_verdict_and_synthetic_banner_when_applicable() -> None:
    report = operating_point_report()  # default synthetic
    text = render_report(report)
    assert "NOT MEASURED" in text
    assert "SYNTHETIC MCB CORPUS" in text
    assert "FR-0.3" in text
    assert f"{EXTRACTBENCH_WORD_GROUNDING_F1:.2f}" in text


def test_render_report_empirical_confirmed_has_no_synthetic_banner() -> None:
    # 100, not MIN_RECORDS_FOR_VERDICT + 5: every record is grounded-correct here, so the
    # lexicographic tiebreak among equal-confidence records doesn't matter (any subset is
    # correct) -- but the WINNING ROW still needs n_covered >= MIN_RECORDS_FOR_VERDICT for
    # CONFIRMED to be defensible, and the largest row at 60% coverage of 35 records was only 21.
    corpus = MCBCorpus(
        records=_all_grounded_correct_records(100),
        provenance=Provenance.EMPIRICAL,
    )
    report = operating_point_report(corpus)
    text = render_report(report)
    assert "SYNTHETIC MCB CORPUS" not in text
    assert "ASYMMETRY CONFIRMED" in text


def test_report_as_dict_round_trips_verdict_and_baseline() -> None:
    report = operating_point_report()
    payload = report_as_dict(report)
    assert payload["verdict"] == AsymmetryVerdict.NOT_MEASURED.value
    assert payload["synthetic"] is True
    assert payload["baseline"]["word_grounding_f1_percent"] == EXTRACTBENCH_WORD_GROUNDING_F1
    assert payload["baseline"]["value_f1_percent"] == pytest.approx(95.6)
    assert len(payload["rows"]) == 3
    assert payload["grounding_curve"]
    assert isinstance(payload["caveats"], list) and payload["caveats"]


def test_extractbench_constants_match_the_verified_figures() -> None:
    """Pins the cited figures to what the paper actually prints.

    CORRECTED 2026-08-19 (P3 task 3.10). This test previously pinned 46.43 / 44.14 / 43.30 /
    84.92, which is what the repository had carried from Phase 2 and what `HANDOFF.md` §7 flagged
    as never re-checked. The paper was fetched and read: **Table 3 on page 9 prints one decimal
    place** -- 46.4, 44.1, 43.3, 84.9. The extra digit was invented.

    The substance was right in every case, which is precisely why it survived: a wrong second
    decimal on a correctly-recalled figure is invisible to everyone except the person who opens
    the source. That is the §7 signature, and finding it here rather than in someone else's data
    is the point of the exercise.

    A test that pins a number is only as good as the reading behind it, so the reading is
    recorded: PDF sha256 533891e9…e982d, registered in `data/reference/manifest.json`, fetched
    from arxiv.org/pdf/2607.29677.
    """
    from errata_bench.operating_point import (
        EXTRACTBENCH_PAGE_GROUNDING_F1,
        EXTRACTBENCH_SYSTEMS_AT_ZERO_GROUNDING,
        EXTRACTBENCH_SYSTEMS_EVALUATED,
        EXTRACTBENCH_VALUE_F1,
        EXTRACTBENCH_WORD_GROUNDING_F1_REDUCTO,
        EXTRACTBENCH_WORD_GROUNDING_F1_SECOND,
    )

    # Table 3, p.9 -- word-level grounding F1, "Overall" column.
    assert EXTRACTBENCH_WORD_GROUNDING_F1 == 46.4          # LE Agentic Plus
    assert EXTRACTBENCH_WORD_GROUNDING_F1_SECOND == 44.1   # LE Agentic
    assert EXTRACTBENCH_WORD_GROUNDING_F1_REDUCTO == 43.3  # Reducto Deep
    # Table 3, p.9 -- page-level grounding F1, "Overall" column.
    assert EXTRACTBENCH_PAGE_GROUNDING_F1 == 84.9
    # §1 p.3 ("We compare 14 systems"), and Table 3's six named rows + "All other systems 0.0".
    assert EXTRACTBENCH_SYSTEMS_EVALUATED == 14
    assert EXTRACTBENCH_SYSTEMS_AT_ZERO_GROUNDING == 14 - 6
    # §3.2 p.7 -- "Agentic Plus reaches 95.6% at 8.1 ¢/page".
    assert EXTRACTBENCH_VALUE_F1 == 95.6


def test_the_citation_names_where_each_figure_was_read() -> None:
    """A citation that says "verified" without saying *where* is the thing this project exists to
    object to. The locator has to be in the string a reader sees."""
    from errata_bench.operating_point import EXTRACTBENCH_CITATION

    assert "2607.29677" in EXTRACTBENCH_CITATION
    assert "Table 3" in EXTRACTBENCH_CITATION
    assert "2026-08-19" in EXTRACTBENCH_CITATION


# ================================================================================================
# Finding N9 -- the verdict must compare like with like
#
# Gate 2's first run on a real corpus (1,426 ABB S200 records) reported ASYMMETRY CONFIRMED,
# "clearing the 46.43% ExtractBench baseline by 52.24pp", and printed "Proceed". It was comparing
# the audit's best SELECTIVE coverage point -- the top 20% of fields by confidence, which on that
# corpus is almost entirely order codes, the one attribute with a distinctive pattern -- against
# ExtractBench's FULL-coverage figure.
#
# Computed the way FR-0.3 actually specifies ("compared explicitly against ExtractBench's 46.43
# word-level / 95.6 value F1 at full coverage"), the same corpus scores 46.34% against 46.43%:
# a dead heat, and NOT_CONFIRMED once the Wilson lower bound is used.
#
# The report already carried a caveat naming the mismatch. It sat below a verdict that had
# already said "Proceed" -- which is the shape of R0 findings 1-4 exactly: the instrument knew
# and the verdict routed around it.
# ================================================================================================


def _split_corpus(n_correct: int, n_wrong: int) -> MCBCorpus:
    """A corpus whose correct records all sort above its wrong ones by confidence."""
    on_box, off_box = BoundingBox(0, 0, 10, 10), BoundingBox(50, 50, 60, 60)
    total = n_correct + n_wrong
    records = [
        _record(
            f"r{i}",
            confidence=1.0 - (i / (total + 1)),
            predicted_box=on_box if i < n_correct else off_box,
        )
        for i in range(total)
    ]
    return MCBCorpus(records=tuple(records), name="n9", provenance=Provenance.EMPIRICAL)


def test_the_verdict_is_taken_at_full_coverage_not_at_the_best_slice() -> None:
    """The regression pin for N9.

    200 records: the top 40 (20%) ground perfectly, the remaining 160 do not.

    Sized so the winning slice ITSELF clears MIN_RECORDS_FOR_VERDICT (40 >= 30). That matters:
    the pre-existing n_covered guard catches a small lucky window, so a scenario where the slice
    is undersized would be caught by the old code too and would not isolate N9. Here every prior
    guard passes and only the coverage mismatch is left.
    """
    report = operating_point_report(_split_corpus(n_correct=40, n_wrong=160))

    best = report.best_row
    assert best is not None
    assert best.coverage == 0.20
    assert best.n_covered >= MIN_RECORDS_FOR_VERDICT, "the old n_covered guard would NOT fire here"
    assert best.word_grounding.conservative_f1 > BASELINE_FRACTION, "the slice looks confirmable"

    assert report.full_coverage_grounding.conservative_f1 < BASELINE_FRACTION
    assert asymmetry_verdict(report) is AsymmetryVerdict.ASYMMETRY_NOT_CONFIRMED


def test_full_coverage_grounding_scores_every_record() -> None:
    report = operating_point_report(_split_corpus(n_correct=40, n_wrong=60))
    full = report.full_coverage_grounding
    assert full.true_positives == 40
    assert full.gold_total == 100


def test_a_genuinely_good_audit_still_confirms() -> None:
    """The negative control. The fix must not make CONFIRMED unreachable -- a gate that can only
    say no is as useless as one that can only say yes."""
    report = operating_point_report(_split_corpus(n_correct=95, n_wrong=5))
    assert report.full_coverage_grounding.conservative_f1 > BASELINE_FRACTION
    assert asymmetry_verdict(report) is AsymmetryVerdict.ASYMMETRY_CONFIRMED


def test_the_rendered_report_states_the_full_coverage_comparison_before_the_verdict() -> None:
    """The caveat existed before and was printed after the verdict, which is why it did not help.

    Position is the fix, not wording: a reader who stops at "VERDICT" must already have seen the
    only number comparable to the baseline.
    """
    text = render_report(operating_point_report(_split_corpus(n_correct=40, n_wrong=160)))
    assert "FULL COVERAGE" in text
    assert text.index("FULL COVERAGE") < text.index("VERDICT:")
    assert "SELECTIVE" in text


def test_best_margin_is_still_available_but_documented_as_incomparable() -> None:
    """`best_margin` is kept -- the selective operating point is genuinely interesting, and
    §0.3's mechanism 1 argues an audit needs only one workable low-coverage point. It simply is
    not the verdict comparison, and its docstring has to say so."""
    from errata_bench.operating_point import OperatingPointReport

    # Collapsed: the phrase wraps across lines in the docstring.
    doc = " ".join((OperatingPointReport.best_margin.__doc__ or "").split())
    assert "is **not** the verdict comparison" in doc
    assert "full_coverage_margin" in doc
