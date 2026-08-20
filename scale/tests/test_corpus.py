"""The R2 demonstration corpus, and what the audit actually finds in it.

This is the file that keeps the headline numbers honest. The corpus states, family by family, what
a competent reviewer should conclude; the audit then runs over it and the two are compared. If they
ever disagree, one of them is wrong and the build says so -- which is the only arrangement under
which "1,428 defects, 0 false positives on 654 equivalence traps" means anything.

The corpus is regenerated inside the test rather than read from disk wherever that is affordable,
so the properties hold for any size and are not a fact about one committed file.
"""

from __future__ import annotations

import csv

import pytest
from scalefixtures import R1_CATALOG, demo_catalog  # noqa: F401

from errata_audit import Outcome, load_catalog
from errata_scale import index_feed, run_catalog, run_structural
from errata_scale.corpus import (
    CORPUS_VERSION,
    FamilyKind,
    build_rows,
    expected_counts,
    family_kind,
    provenance,
    write_catalog,
)
from errata_scale.structural import StructuralCheck


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    """A 2,000-row corpus, generated the same way the 10,000-row one is."""
    path = tmp_path_factory.mktemp("corpus") / "catalog.csv"
    if not R1_CATALOG.exists():
        pytest.skip("the R1 demonstration catalog is not present")
    real, synthetic_count, synthetic = write_catalog(
        path, real_catalog=R1_CATALOG, target_total=2000
    )
    return path, real, synthetic_count, synthetic


# ------------------------------------------------------------------------------------------------
# determinism
# ------------------------------------------------------------------------------------------------


def test_a_family_kind_is_decided_by_its_own_name_and_nothing_else():
    assert family_kind("SYN-000000") is family_kind("SYN-000000")
    kinds = {family_kind(f"SYN-{n:06d}") for n in range(400)}
    assert kinds == set(FamilyKind), "every family kind should appear in a few hundred families"


def test_the_corpus_is_reproducible_from_the_target_alone():
    first = build_rows(target=500)
    second = build_rows(target=500)
    assert [r.sku for r in first] == [r.sku for r in second]
    assert [r.as_row() for r in first] == [r.as_row() for r in second]


def test_growing_the_corpus_extends_it_rather_than_reshuffling_it():
    """Content-hash mutation, not a seeded RNG: asking for more rows must not change the old ones."""
    small = build_rows(target=200)
    large = build_rows(target=800)
    assert [r.sku for r in large][: len(small)] == [r.sku for r in small]


def test_no_synthetic_row_carries_a_plausible_company_name():
    """A plausible name in a defect corpus is one copy-paste away from a defamatory claim about a
    real company. FR-8.6's reasoning, applied to the fixtures."""
    for record in build_rows(target=300):
        assert record.manufacturer.startswith("SYN-MFR-")
        assert record.sku.startswith("SYN-")


# ------------------------------------------------------------------------------------------------
# what the audit finds, against what the corpus says it should
# ------------------------------------------------------------------------------------------------


def test_the_audit_finds_exactly_what_the_corpus_says_is_there(corpus):
    path, _real, _count, synthetic = corpus
    expected = expected_counts(synthetic)

    records = load_catalog(path)
    result = run_structural(records, index_feed(path))

    synthetic_findings = [o for o in result.findings if o.sku_id.startswith("SYN-")]
    synthetic_declines = [o for o in result.declined if o.sku_id.startswith("SYN-")]

    assert len(synthetic_findings) == expected["expected_findings"]
    assert len(synthetic_declines) == expected["expected_declines"]


def test_no_equivalence_trap_is_ever_flagged(corpus):
    """FR-5.3, at scale. This is the false positive that ends a pilot, and the corpus contains
    hundreds of chances to make it."""
    path, _real, _count, synthetic = corpus
    traps = {record.family for record in synthetic if record.kind.is_trap}
    assert traps, "a detection corpus with no traps reports a precision that was never tested"

    result = run_structural(load_catalog(path), index_feed(path))
    flagged = {o.sku_id.rsplit("-", 1)[0] for o in result.findings}
    assert not (flagged & traps)

    declined = {o.sku_id.rsplit("-", 1)[0] for o in result.declined}
    assert not (declined & traps), "an equivalence is not a conflict to abstain from either"


def test_consistent_families_produce_no_findings(corpus):
    path, _real, _count, synthetic = corpus
    consistent = {
        record.family
        for record in synthetic
        if record.kind in {FamilyKind.CONSISTENT_PAIR, FamilyKind.CLEAN_SINGLE}
    }
    result = run_structural(load_catalog(path), index_feed(path))
    flagged = {o.sku_id.rsplit("-", 1)[0] for o in result.findings}
    assert not (flagged & consistent)


def test_each_defect_family_produces_the_check_it_was_built_for(corpus):
    path, _real, _count, synthetic = corpus
    kind_of = {record.family: record.kind for record in synthetic}
    result = run_structural(load_catalog(path), index_feed(path))

    wanted = {
        FamilyKind.CONTRADICTION_TRIPLE: StructuralCheck.SIBLING_CONTRADICTION,
        FamilyKind.FILL_GAP_TRIPLE: StructuralCheck.SIBLING_FILL_GAP,
        FamilyKind.DIMENSION_SINGLE: StructuralCheck.UNIT_DIMENSION,
    }
    seen: dict[FamilyKind, set[StructuralCheck]] = {kind: set() for kind in wanted}
    for outcome in result.findings:
        family = outcome.sku_id.rsplit("-", 1)[0]
        kind = kind_of.get(family)
        if kind in wanted:
            seen[kind].add(outcome.check)

    for kind, check in wanted.items():
        assert seen[kind] == {check}, f"{kind.value} produced {seen[kind]}"


def test_the_documented_stratum_is_carried_through_unchanged(corpus):
    path, real, _count, _synthetic = corpus
    with R1_CATALOG.open("r", encoding="utf-8-sig", newline="") as handle:
        original = list(csv.DictReader(handle))
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        combined = list(csv.DictReader(handle))

    assert real == len(original)
    for source, copied in zip(original, combined[:real], strict=True):
        assert source["sku"] == copied["sku"]
        assert source["rated_current"] == copied["rated_current"]
        assert source["datasheet"] == copied["datasheet"]


def test_the_provenance_document_states_what_is_constructed(corpus):
    path, real, _count, synthetic = corpus
    document = provenance(
        real_count=real,
        synthetic=synthetic,
        real_catalog=str(R1_CATALOG),
        destination=str(path),
    )
    assert document["corpus_version"] == CORPUS_VERSION
    assert "THE CATALOG IS CONSTRUCTED" in document["warning"]
    assert "no public 10k+ industrial catalog" in document["warning"]
    assert document["strata"]["S1_documented"]["rows"] == real
    assert document["strata"]["S2_undocumented"]["rows"] == len(synthetic)
    for kind in FamilyKind:
        assert document["families_by_kind"][kind.value]["expectation"]


def test_the_run_over_the_corpus_reports_a_groundable_fraction_that_is_mostly_zero(corpus):
    """The point of the S2 stratum: it is the groundable-fraction story, not a detection story."""
    path, real, count, _synthetic = corpus
    run = run_catalog(path)
    assert run.groundable.total == real + count
    assert run.groundable.groundable == 0  # no documents were supplied to this run
    assert run.groundable.percentages_sum()
    assert run.declined_by_reason()["no_source_document"] == real + count


# ------------------------------------------------------------------------------------------------
# the real, committed-by-generation corpus
# ------------------------------------------------------------------------------------------------


def test_the_shipped_corpus_is_at_least_ten_thousand_records(demo_catalog):
    records = load_catalog(demo_catalog)
    assert len(records) >= 10_000


def test_the_shipped_corpus_audits_end_to_end(demo_catalog):
    run = run_catalog(demo_catalog)
    assert run.findings > 1_000
    assert run.clusters
    assert run.cost.scales_with_error_count()
    assert run.groundable.percentages_sum()
    # every finding is evidenced, every decline has exactly one reason: no silent skips anywhere
    for entry in run.triage.entries:
        assert entry.redline.evidence
    for outcome in run.structural.declined:
        assert outcome.declined_reason is not None
    assert all(
        outcome.outcome
        in {Outcome.FINDING, Outcome.RESOLVED, Outcome.DECLINED, Outcome.NOT_IN_FEED}
        for outcome in run.structural.outcomes
    )
