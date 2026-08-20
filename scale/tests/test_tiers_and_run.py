"""FR-8.7 -- tiered execution, and the catalog run that assembles it.

    "Cost report shows T2/T3 volume scaling with error count, not SKU count."

The commercial argument for auditing rather than extracting rests on that sentence, so it is
measured twice at two different catalog sizes rather than asserted once. The test pads a catalog
with *clean* records and demands that T0 grows while T2 and T3 do not move at all. A scaling claim
measured at one size is not a measurement.

The run tests cover the order of operations, which is the release: inventory before audit, T0 over
everything, cluster before rank. Getting that order wrong does not raise -- it produces a report
that is subtly flattering, which is the failure this project exists to detect in other people's
systems.
"""

from __future__ import annotations

from scalefixtures import catalog_of, row  # noqa: F401

from errata_audit import load_catalog
from errata_scale import Tier, index_feed, inventory, run_catalog, run_structural


def _defective_family(prefix: str) -> list[dict[str, str]]:
    return [
        row(f"{prefix}-1", mpn=f"MPN-{prefix}", rated_current="16 A"),
        row(f"{prefix}-2", mpn=f"MPN-{prefix}", rated_current="16 A"),
        row(f"{prefix}-3", mpn=f"MPN-{prefix}", rated_current="61 A"),
    ]


def test_t2_and_t3_do_not_move_when_clean_records_are_added(catalog_of):
    defects = _defective_family("A") + _defective_family("B")
    small = catalog_of(defects, "small.csv")
    padded = catalog_of(
        defects + [row(f"CLEAN-{n}") for n in range(200)],
        "padded.csv",
    )

    first = run_catalog(small)
    second = run_catalog(padded)

    assert len(second.records) == len(first.records) + 200

    t0_first = first.cost.of(Tier.T0_STRUCTURAL)
    t0_second = second.cost.of(Tier.T0_STRUCTURAL)
    assert t0_second.records_entered > t0_first.records_entered
    assert t0_second.work_units > t0_first.work_units

    for tier in (Tier.T2_DEEP, Tier.T3_HUMAN):
        assert first.cost.of(tier).work_units == second.cost.of(tier).work_units
        assert first.cost.of(tier).records_entered == second.cost.of(tier).records_entered

    assert first.cost.scales_with_error_count()
    assert second.cost.scales_with_error_count()


def test_t2_and_t3_grow_when_defects_are_added(catalog_of):
    """The other half of the claim: the volume tracks errors, so it must move when errors move."""
    one = run_catalog(catalog_of(_defective_family("A"), "one.csv"))
    two = run_catalog(catalog_of(_defective_family("A") + _defective_family("B"), "two.csv"))
    assert two.cost.of(Tier.T3_HUMAN).work_units == 2 * one.cost.of(Tier.T3_HUMAN).work_units


def test_the_cost_report_counts_operations_that_happened(catalog_of):
    run = run_catalog(catalog_of(_defective_family("A")))
    assert run.cost.error_count == run.findings
    assert run.cost.of(Tier.T3_HUMAN).work_units == run.findings
    # T1 did not run at all: no documents were supplied, and that is visible rather than implied
    assert run.cost.of(Tier.T1_GROUNDED).records_entered == 0
    assert "never entered this tier" in run.cost.of(Tier.T1_GROUNDED).note


def test_every_tier_states_what_it_scales_with():
    for tier in Tier:
        assert tier.description
        assert tier.scales_with


def test_the_inventory_is_computed_over_the_whole_feed_before_any_audit(catalog_of):
    catalog = catalog_of([*_defective_family("A"), row("SOLO")])
    run = run_catalog(catalog)
    assert run.groundable.total == len(run.records) == 4
    # and it agrees with a standalone inventory of the same feed -- one number, one method
    standalone = inventory(load_catalog(catalog), {}, catalog=catalog.name)
    assert standalone.counts() == run.groundable.counts()


def test_the_run_clusters_before_it_ranks(catalog_of):
    """`record_multiplicity` is a term in the ranking and is not knowable one record at a time."""
    catalog = catalog_of(_defective_family("A") + _defective_family("B"))
    run = run_catalog(catalog)
    assert run.clusters
    for entry in run.triage.entries:
        assert entry.cluster_size >= 1
        assert entry.redline.blast_radius.record_multiplicity == entry.cluster_size


def test_the_batch_id_is_the_same_for_the_same_inputs(catalog_of):
    catalog = catalog_of(_defective_family("A"))
    assert run_catalog(catalog).batch_id == run_catalog(catalog).batch_id


def test_a_label_makes_a_second_batch_over_the_same_inputs(catalog_of):
    catalog = catalog_of(_defective_family("A"))
    assert run_catalog(catalog).batch_id != run_catalog(catalog, label="rerun").batch_id


def test_a_changed_feed_is_a_different_batch(catalog_of):
    first = run_catalog(catalog_of(_defective_family("A"), "first.csv"))
    second = run_catalog(catalog_of([*_defective_family("A"), row("EXTRA")], "second.csv"))
    assert first.batch_id != second.batch_id


def test_the_manifest_records_what_the_run_was(catalog_of):
    run = run_catalog(catalog_of(_defective_family("A")))
    manifest = run.manifest()
    assert manifest["feed_sha256"] == index_feed(run.catalog).sha256
    assert manifest["records"] == 3
    assert manifest["policy_version"] == "electrical-conservative@v3"
    assert manifest["scale_version"]
    assert manifest["structural_version"]


def test_declined_reasons_from_both_tiers_appear_in_one_table(catalog_of):
    """Separating them would let a reader believe the coverage came from a smaller denominator."""
    catalog = catalog_of(
        [
            row("T-1", mpn="MPN-T", weight_kg="0.125 kg"),
            row("T-2", mpn="MPN-T", weight_kg="0.250 kg"),
            row("U-1", datasheet="not-supplied.pdf"),
        ]
    )
    run = run_catalog(catalog)
    reasons = run.declined_by_reason()
    assert reasons["equal_rank_source_conflict"] == 2
    assert reasons["no_source_document"] == 3


def test_a_run_with_no_documents_is_a_t0_report_rather_than_an_error(catalog_of):
    """The mode most real catalogs start in. Being able to hand somebody a report before any
    document has been collected is the difference between a pilot and a procurement exercise."""
    run = run_catalog(catalog_of(_defective_family("A")))
    assert run.groundable.groundable == 0
    assert run.findings > 0
    assert run.structural_findings == run.findings
    assert run.grounded_findings == 0


def test_the_structural_result_and_the_run_agree_on_the_findings(catalog_of):
    catalog = catalog_of(_defective_family("A"))
    run = run_catalog(catalog)
    standalone = run_structural(load_catalog(catalog), index_feed(catalog))
    assert len(standalone.findings) == run.structural_findings
