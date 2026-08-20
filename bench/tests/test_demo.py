"""The demo must stay tied to the suite it claims to be grounded in.

A demonstration that quietly drifts from the measured data is worse than no demonstration: it
becomes a set of hand-picked strings that agree with whatever the code currently does. These tests
pin the property that makes the demo honest -- every value in it is a cited suite case.
"""

from __future__ import annotations

import pytest
import yaml

from errata_bench.demo import load_demo, render_html, render_text, run_demo
from errata_bench.equivalence import load_cases
from errata_spec.taxonomy import Severity


def test_every_demo_value_is_a_real_suite_case() -> None:
    known = {case.id for case in load_cases()}
    referenced = {
        str(attribute["case"])
        for sku in load_demo().get("skus", [])
        for attribute in sku.get("attributes", [])
    }
    assert referenced, "the demo catalog references no cases at all"
    assert referenced <= known, f"demo references cases not in the suite: {referenced - known}"


def test_a_missing_case_id_fails_loudly(tmp_path) -> None:
    """Silently skipping is how a demo starts lying."""
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        yaml.safe_dump(
            {"title": "t", "skus": [{"sku": "X", "attributes": [{"case": "nope-999"}]}]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(KeyError, match="nope-999"):
        run_demo(catalog)


def test_the_demo_shows_all_three_outcomes() -> None:
    """Findings alone would misrepresent the product. Silence and refusal are the other half."""
    result = run_demo()
    assert result.findings, "no findings -- the demo would not show the tool working"
    assert result.resolved_silently, "no silent resolutions -- the trust argument disappears"
    assert result.declined, "no declines -- the 'refuses rather than guesses' claim is unshown"
    total = len(result.findings) + len(result.resolved_silently) + len(result.declined)
    assert total == len(result.every_attribute)


def test_findings_are_ordered_worst_first() -> None:
    severities = [a.comparison.severity for a in run_demo().findings]
    assert severities == sorted(severities)
    assert severities[0] is Severity.SEV1


def test_the_packaging_error_is_present_and_sev1() -> None:
    """`Each` against `Box of 10` is the highest-severity case in the product. If the demo ever
    stops showing it at SEV-1, either the demo or the comparator has regressed."""
    packaging = [
        a
        for a in run_demo().findings
        if a.catalog == "Each" and a.datasheet == "Box of 10"
    ]
    assert len(packaging) == 1
    assert packaging[0].comparison.severity is Severity.SEV1


def test_renderers_produce_output_and_state_their_scope() -> None:
    result = run_demo()
    text = render_text(result)
    page = render_html(result)
    for rendered in (text, page):
        assert "316" in rendered
        # The scope caveat is not decoration -- it is the thing that keeps the demo honest.
        assert "NOT MEASURED" in rendered
    assert page.startswith("<title>")
    assert "grounding" in page.lower()
