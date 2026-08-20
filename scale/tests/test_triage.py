"""FR-8.4 -- the triage router.

    "Ranking is reproducible and each factor is independently inspectable in the UI."

Two properties, tested as two groups. Reproducibility is checked by feeding the router the same
findings in a different order and demanding the same queue, including through the ties -- a ranking
that is stable only when nothing ties is not stable, and at catalog scale almost everything ties.

Inspectability is checked as a property of the data rather than of a screen: every term of the
product is present, carries the sentence that says where it came from, and is flagged when it is a
stated default rather than a measurement. The last part matters most. A ``revenue weight = 1.0``
that looks like a measurement is how a ranking quietly becomes a fiction.
"""

from __future__ import annotations

from errata_comparator.redline import SAFETY_MULTIPLIER
from errata_scale import cluster_signatures, route
from errata_spec import (
    BlastRadius,
    CounterEvidence,
    DisagreementClass,
    Evidence,
    Redline,
    Severity,
)

DIGEST = "c" * 64


def _redline(
    sku: str,
    *,
    attribute: str = "weight_kg",
    label: str = "Weight",
    catalog: str = "0.9 kg",
    proposed: str = "0.125 kg",
    probability: float | None = None,
    safety: bool = False,
) -> Redline:
    return Redline(
        sku_id=sku,
        attribute_uri=attribute,
        attribute_label=label,
        catalog_value=catalog,
        proposed_value=proposed,
        disagreement_class=DisagreementClass.CONTRADICTION,
        severity=Severity.SEV1,
        evidence=(
            Evidence(
                doc_id="feed.csv",
                doc_revision_sha256=DIGEST,
                page=1,
                char_span=(0, 8),
                snippet=proposed,
                column_header=attribute,
            ),
        ),
        counter_evidence=CounterEvidence.none_found(catalog),
        blast_radius=BlastRadius(
            safety_class_multiplier=SAFETY_MULTIPLIER if safety else 1.0
        ),
        probability_catalog_wrong=probability,
    )


def test_every_factor_of_the_product_is_carried_separately():
    redline = _redline("A")
    result = route([redline], cluster_signatures([redline]))
    entry = result.entries[0]
    names = [factor.name for factor in entry.factors]
    assert names == [
        "P(catalog wrong)",
        "revenue weight",
        "safety multiplier",
        "propagation count",
        "record multiplicity",
    ]
    assert all(factor.provenance for factor in entry.factors)


def test_unsupplied_factors_are_marked_as_defaults_rather_than_measurements():
    redline = _redline("A")
    entry = route([redline], cluster_signatures([redline])).entries[0]
    by_name = {factor.name: factor for factor in entry.factors}
    assert by_name["revenue weight"].measured is False
    assert by_name["propagation count"].measured is False
    assert by_name["P(catalog wrong)"].measured is False
    assert "no calibration set exists" in by_name["P(catalog wrong)"].provenance
    assert "(not supplied -- stated default)" in by_name["revenue weight"].sentence()


def test_a_calibrated_finding_reports_its_probability_as_measured():
    redline = _redline("A", probability=0.83)
    entry = route([redline], cluster_signatures([redline])).entries[0]
    factor = next(f for f in entry.factors if f.name == "P(catalog wrong)")
    assert factor.measured is True
    assert factor.value == 0.83


def test_record_multiplicity_is_the_computed_cluster_size():
    """R1 left this term at 1 because it is not knowable one record at a time. R2 is where it
    becomes real, and it must come from the cluster rather than from an assertion."""
    redlines = [_redline(f"SKU-{n}") for n in range(4)]
    clusters = cluster_signatures(redlines)
    result = route(redlines, clusters)
    for entry in result.entries:
        assert entry.cluster_size == 4
        assert entry.redline.blast_radius.record_multiplicity == 4
        factor = next(f for f in entry.factors if f.name == "record multiplicity")
        assert factor.value == 4.0
        assert "counted not asserted" in factor.provenance


def test_expected_review_value_is_the_stated_product():
    redlines = [_redline(f"SKU-{n}", safety=True) for n in range(3)]
    result = route(
        redlines, cluster_signatures(redlines), propagation={"weight_kg": 4}
    )
    entry = result.entries[0]
    assert entry.expected_review_value == 0.5 * 1.0 * SAFETY_MULTIPLIER * 4 * 3


def test_the_ranking_is_reproducible_including_through_ties():
    redlines = [_redline(f"SKU-{n:03d}") for n in range(25)]
    forward = route(redlines, cluster_signatures(redlines))
    backward = route(list(reversed(redlines)), cluster_signatures(list(reversed(redlines))))
    assert [e.redline_id for e in forward.entries] == [e.redline_id for e in backward.entries]


def test_a_safety_finding_outranks_an_equally_probable_cosmetic_one():
    safety = _redline("S", attribute="rated_current", label="Rated current", safety=True)
    cosmetic = _redline("C")
    result = route([cosmetic, safety], cluster_signatures([cosmetic, safety]))
    assert result.entries[0].redline.sku_id == "S"
    assert result.entries[0].requires_two_signatures
    assert not result.entries[1].requires_two_signatures


def test_a_queue_row_reads_as_a_sentence_and_never_as_a_bare_percentage():
    redline = _redline("A")
    entry = route([redline], cluster_signatures([redline])).entries[0]
    sentence = entry.sentence()
    assert "Catalog says" in sentence
    assert "%" not in sentence


def test_a_finding_with_no_proposal_still_reads_as_a_sentence():
    """The structural case: the class declares the catalog's value unsupported without knowing
    what the right one is. "The evidence says ''" is not something to show a reviewer."""
    redline = Redline(
        sku_id="A",
        attribute_uri="rated_current",
        attribute_label="Rated current",
        catalog_value="0.125 kg",
        proposed_value="",
        disagreement_class=DisagreementClass.UNSUPPORTED_VALUE,
        severity=Severity.SEV2,
        evidence=(
            Evidence(
                doc_id="feed.csv",
                doc_revision_sha256=DIGEST,
                page=1,
                char_span=(0, 8),
                snippet="0.125 kg",
            ),
        ),
        counter_evidence=CounterEvidence.none_found("0.125 kg"),
    )
    entry = route([redline], cluster_signatures([redline])).entries[0]
    assert "nothing in the evidence supports it" in entry.sentence()
    assert "''" not in entry.sentence()


def test_by_severity_counts_what_the_queue_holds():
    redlines = [_redline("A"), _redline("B")]
    result = route(redlines, cluster_signatures(redlines))
    assert result.by_severity() == {1: 2}


def test_as_dict_carries_the_factors_and_the_evidence():
    redline = _redline("A")
    entry = route([redline], cluster_signatures([redline])).entries[0]
    payload = entry.as_dict()
    assert len(payload["factors"]) == 5
    assert payload["evidence"][0]["doc_revision_sha256"] == DIGEST
    assert payload["counter_evidence"]
