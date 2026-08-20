"""NFR-4 -- the calibration drift alarm.

    "Fires on calibration degradation, not just accuracy degradation.
     Alarm triggers on a synthetic drift fixture."

Three fixtures, and the third is the requirement:

* :func:`drifted_overconfident` -- probabilities shifted up, ordering untouched. **Must fire.**
* :func:`stable` -- well calibrated. **Must not fire**, or the alarm is noise.
* :func:`degraded_but_calibrated` -- accuracy collapses to a coin flip while every promise stays
  exactly true. **Must not fire.** This is the one that separates a calibration alarm from an
  accuracy alarm with a calibration label on it, and it is the clause NFR-4 spends half its words
  on.

Synthetic input is correct here and does not touch ground rule 5. The rule keeps *gates* at
NOT_MEASURED on synthetic data because a gate measures the product against the world. This is not
a gate; the thing under test is the alarm, and the only way to test an alarm is to cause the
condition it watches for. Nothing here reports a calibration quality.
"""

from __future__ import annotations

import pytest

from errata_audit.drift import (
    MIN_OBSERVATIONS,
    DriftVerdict,
    degraded_but_calibrated,
    drifted_overconfident,
    monitor,
    stable,
)
from errata_audit.drift import _wilson as audit_wilson

# ------------------------------------------------------------------------------------------------
# The acceptance criterion
# ------------------------------------------------------------------------------------------------


def test_the_alarm_fires_on_the_synthetic_drift_fixture() -> None:
    """NFR-4's acceptance criterion, verbatim."""
    result = monitor(drifted_overconfident())

    assert result.verdict is DriftVerdict.DRIFTED
    assert result.tripped_bins, "DRIFTED with no tripped bin is a verdict with no evidence"
    assert all(b.overconfident for b in result.tripped_bins), (
        "the fixture shifts probabilities UP, so every trip should be over-confidence. A "
        "under-confident trip here means the alarm is detecting something other than the injected "
        "drift."
    )
    assert "FR-6.1" in result.text()


def test_the_alarm_is_silent_when_calibration_holds() -> None:
    """An alarm that cannot be silent is not an alarm."""
    assert monitor(stable()).verdict is DriftVerdict.STABLE


def test_the_alarm_is_silent_when_accuracy_collapses_but_calibration_is_honest() -> None:
    """The clause the requirement spends half its words on.

    Every record is predicted at the base rate: the model has lost all power to tell a defect from
    a clean record, and it is saying so truthfully -- it promises 0.5 and is right half the time.
    A monitor that fired here would be an accuracy monitor wearing a calibration label, and it
    would train its operator to ignore it long before the drift NFR-4 is about arrived.
    """
    result = monitor(degraded_but_calibrated())

    assert result.accuracy == pytest.approx(0.5, abs=0.1), "the fixture is no longer a coin flip"
    assert result.verdict is DriftVerdict.STABLE
    assert result.observed_ece < 0.05


def test_drift_and_degradation_are_visibly_different_in_the_report() -> None:
    """Both numbers are printed, so a reader can see them move independently.

    Accuracy is reported and never used to reach the verdict. That is worth an assertion rather
    than a comment, because the cheapest way to "improve" this alarm later is to fold accuracy
    into the decision, and doing so would quietly delete the requirement.
    """
    drifted = monitor(drifted_overconfident())
    degraded = monitor(degraded_but_calibrated())

    assert drifted.fired and not degraded.fired
    assert degraded.accuracy < drifted.accuracy, (
        "the degraded fixture is supposed to be WORSE at the job and still not trip the alarm; "
        "if it is no longer worse, the fixture has stopped testing anything"
    )
    assert "NOT used to reach the verdict" in drifted.text()


# ------------------------------------------------------------------------------------------------
# Not firing and not knowing are different
# ------------------------------------------------------------------------------------------------


def test_a_short_window_is_insufficient_data_not_stable() -> None:
    """Collapsing these two is how a monitor goes quiet without anybody deciding it should."""
    result = monitor(drifted_overconfident(n=MIN_OBSERVATIONS - 1))

    assert result.verdict is DriftVerdict.INSUFFICIENT_DATA
    assert "NOT 'stable'" in result.text()


def test_an_empty_window_does_not_raise() -> None:
    result = monitor([])
    assert result.verdict is DriftVerdict.INSUFFICIENT_DATA
    assert result.n == 0


def test_sensitivity_comes_from_sample_size_rather_than_a_tuned_threshold() -> None:
    """The same drift, seen through more observations, is what makes a small gap detectable.

    There is no threshold to turn up. A bin trips when the promise falls outside the Wilson
    interval of the outcomes, so a large window trips on a small gap -- correctly, because with a
    large window a small gap is real -- and a small window cannot trip on noise.
    """
    small = monitor(drifted_overconfident(n=MIN_OBSERVATIONS, shift=0.05))
    large = monitor(drifted_overconfident(n=4000, shift=0.05))

    assert large.verdict is DriftVerdict.DRIFTED
    assert len(large.tripped_bins) >= len(small.tripped_bins)


# ------------------------------------------------------------------------------------------------
# The boundary, and the arithmetic it costs
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "successes,total",
    [(0, 10), (1, 10), (5, 10), (10, 10), (3, 400), (200, 400), (399, 400), (0, 1)],
)
def test_the_local_wilson_matches_the_benchs(successes: int, total: int) -> None:
    """``errata_audit`` may not import ``errata_bench`` -- the product must not import its scorer.

    So the interval arithmetic is duplicated, twelve lines of it. That is the right price for the
    boundary and the wrong thing to leave unchecked: two implementations of one statistic drift,
    and this alarm's sensitivity IS the interval. The test crosses the boundary because a test is
    allowed to; the module is not.
    """
    from errata_bench.stats import wilson

    theirs = wilson(successes, total)
    mine = audit_wilson(successes, total)

    assert mine[0] == pytest.approx(theirs.lo, abs=1e-9)
    assert mine[1] == pytest.approx(theirs.hi, abs=1e-9)


def test_drift_does_not_import_the_scorer() -> None:
    """The rule this module pays twelve lines to keep."""
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src" / "errata_audit" / "drift.py"
    tree = ast.parse(source.read_text("utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    assert not any(n.startswith("errata_bench") for n in names)
