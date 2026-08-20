"""FR-8.5 and FR-8.6 -- clustering that is computed, and a prohibition that is structural.

The FR-8.6 tests are the important ones and they are deliberately awkward to satisfy by accident.
It is not enough that today's schema has no supplier field; the prohibition has to survive the pull
request that adds one because a customer asked which vendor sends the worst data. So:

* the schema is inspected by field name against a banned lexicon, at import time and again here;
* a class that *does* carry such a field is constructed inside a test and the check is asserted to
  reject it, which is what proves the check would fire on a real one;
* and the behavioural test -- the same defect under two different manufacturers landing in **one**
  cluster -- proves the organisation is not in the key even if somebody later renames the field.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from errata_scale import (
    BANNED_SIGNATURE_TERMS,
    DefectShape,
    ErrorSignature,
    NamedOrganisationSignatureError,
    assert_no_named_organisation_field,
    cluster_signatures,
    defect_shape,
    signature_for,
)
from errata_spec import (
    BlastRadius,
    CounterEvidence,
    DisagreementClass,
    Evidence,
    Redline,
    Severity,
)

DIGEST = "a" * 64


def _redline(
    sku: str,
    *,
    catalog: str = "61 A",
    proposed: str = "16 A",
    attribute: str = "rated_current",
    digest: str = DIGEST,
    disagreement: DisagreementClass = DisagreementClass.CONTRADICTION,
) -> Redline:
    return Redline(
        sku_id=sku,
        attribute_uri=attribute,
        attribute_label="Rated current",
        catalog_value=catalog,
        proposed_value=proposed,
        disagreement_class=disagreement,
        severity=Severity.SEV1,
        evidence=(
            Evidence(
                doc_id="feed.csv",
                doc_revision_sha256=digest,
                page=1,
                char_span=(0, 4),
                snippet=proposed,
                column_header=attribute,
            ),
        ),
        counter_evidence=CounterEvidence.none_found(catalog),
        blast_radius=BlastRadius(),
    )


# ------------------------------------------------------------------------------------------------
# FR-8.6 -- named-organisation signatures are prohibited
# ------------------------------------------------------------------------------------------------


def test_the_signature_schema_has_no_organisation_field():
    assert_no_named_organisation_field()  # the shipped schema
    names = {field for field in ErrorSignature.__dataclass_fields__}
    for banned in BANNED_SIGNATURE_TERMS:
        assert not any(banned in name.lower() for name in names)


def test_the_check_rejects_a_schema_that_grows_one():
    """The check is only worth having if it fires. This is the pull request it has to stop."""

    @dataclass(frozen=True)
    class SupplierSignature:
        disagreement_class: str
        supplier_id: str

    with pytest.raises(NamedOrganisationSignatureError) as error:
        assert_no_named_organisation_field(SupplierSignature)
    assert "FR-8.6" in str(error.value)


def test_the_same_defect_under_two_manufacturers_is_one_cluster():
    """The behavioural half of FR-8.6: even if a field were renamed, the organisation is not in
    the key, so a defect pattern cannot be reported per company."""
    clusters = cluster_signatures([_redline("MAKER-A-1"), _redline("MAKER-B-1")])
    assert len(clusters) == 1
    assert clusters[0].size == 2


def test_a_signature_reads_nothing_from_the_sku_or_the_part_number():
    first = signature_for(_redline("SKU-0001"))
    second = signature_for(_redline("SKU-9999"))
    assert first == second
    assert first.fingerprint == second.fingerprint


# ------------------------------------------------------------------------------------------------
# FR-8.5 -- the cluster size is counted
# ------------------------------------------------------------------------------------------------


def test_cluster_size_is_the_length_of_an_enumerable_member_list():
    redlines = [_redline(f"SKU-{n}") for n in range(7)]
    clusters = cluster_signatures(redlines)
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.size == len(cluster.members) == 7
    assert set(cluster.members) == {str(r.redline_id) for r in redlines}
    assert "7 record(s) share this pattern" in cluster.sentence()


def test_different_documents_are_different_signatures():
    """A defect found against the feed and one found against a datasheet rest on different
    evidence. Merging them would let the weaker inherit the stronger's cluster size."""
    clusters = cluster_signatures(
        [_redline("A", digest="a" * 64), _redline("B", digest="b" * 64)]
    )
    assert len(clusters) == 2


def test_clusters_are_ordered_reproducibly():
    redlines = [_redline(f"X-{n}") for n in range(3)] + [
        _redline("Y-1", catalog="", proposed="10 pcs", attribute="packaging_uom",
                 disagreement=DisagreementClass.CATALOG_NULL_EVIDENCE_PRESENT)
    ]
    first = cluster_signatures(redlines)
    second = cluster_signatures(list(reversed(redlines)))
    assert [c.signature.fingerprint for c in first] == [c.signature.fingerprint for c in second]
    assert [c.size for c in first] == [3, 1]


# ------------------------------------------------------------------------------------------------
# defect shapes
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("catalog", "proposed", "expected"),
    [
        ("61 A", "16 A", DefectShape.DIGIT_TRANSPOSITION),
        ("125 A", "12.5 A", DefectShape.ORDER_OF_MAGNITUDE),
        ("0.125 kg", "16 A", DefectShape.DIMENSION_MISMATCH),
        ("", "10 pcs", DefectShape.BLANK_CELL),
        ("16 A", "", DefectShape.NO_PROPOSAL),
        ("16 A", "25 A", DefectShape.VALUE_SUBSTITUTION),
        ("Threaded", "NPT 1/2-14", DefectShape.VALUE_SUBSTITUTION),
    ],
)
def test_defect_shapes_are_classified_from_the_strings_alone(catalog, proposed, expected):
    assert defect_shape(catalog, proposed) == expected


def test_every_pair_gets_a_shape():
    """Total by construction: a pair with no shape would silently drop out of every cluster."""
    for pair in [("", ""), ("x", "y"), ("1", "1"), ("NaN", "1"), ("16 A", "16 A")]:
        assert defect_shape(*pair)
