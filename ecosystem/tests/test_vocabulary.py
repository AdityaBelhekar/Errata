"""Finding N15: one attribute, one identity -- and the ids that were not allowed to move.

The fix is small and the risk in it was not: a redline's ``attribute_uri`` is an input to error
signatures, to clustering, and (in R1 and R2 alike) to nothing else that carries an adjudication.
These tests pin both halves -- that the vocabulary converged, and that the identities did not.
"""

from __future__ import annotations

import pytest

from errata_audit import load_attributes
from errata_audit.audit import stable_redline_id
from errata_comparator import AttributeSpec
from errata_ecosystem.vocabulary import (
    UnknownAttributeTerm,
    canonical_uri,
    is_canonical,
    local_key,
    vocabulary_violations,
)
from errata_scale.ids import structural_redline_id


def test_every_alias_of_one_attribute_resolves_to_one_uri() -> None:
    for term in ("rated_current", "RATED_CURRENT", "EF000227", "etim:EF000227", "Rated current"):
        assert canonical_uri(term) == "etim:EF000227"


def test_an_attribute_etim_does_not_declare_says_so_rather_than_borrowing_an_id() -> None:
    # `packaging_uom` has no ETIM feature in the R1 map. The prefix is the honesty.
    assert canonical_uri("packaging_uom") == "customer:packaging_uom"
    assert is_canonical("customer:packaging_uom")


def test_strict_refuses_to_invent_an_identity() -> None:
    with pytest.raises(UnknownAttributeTerm):
        canonical_uri("whatever the feed called this column", strict=True)


def test_local_key_survives_a_bare_key() -> None:
    assert local_key("etim:EF000227") == "EF000227"
    assert local_key("rated_current") == "rated_current"


def test_the_comparator_spec_now_carries_the_uri_and_falls_back_honestly() -> None:
    with_uri = AttributeSpec(key="rated_current", uri="etim:EF000227")
    without = AttributeSpec(key="local_thing")
    assert with_uri.attribute_uri == "etim:EF000227"
    assert without.attribute_uri == "customer:local_thing"


def test_the_audit_attribute_map_hands_its_uri_to_the_comparator() -> None:
    for attribute in load_attributes():
        assert attribute.to_spec().attribute_uri == attribute.uri


def test_the_violation_scanner_names_the_offender() -> None:
    class FakeRedline:
        def __init__(self, uri: str) -> None:
            self.attribute_uri = uri
            self.sku_id = "SKU-1"

    assert vocabulary_violations([FakeRedline("etim:EF000227")]) == ()
    problems = vocabulary_violations([FakeRedline("rated_current")])
    assert len(problems) == 1
    assert "N15" in problems[0] and "SKU-1" in problems[0]


# ------------------------------------------------------------------------------------------------
# The half that could have gone wrong: identity
# ------------------------------------------------------------------------------------------------


def test_the_r1_redline_id_recorded_before_the_fix_is_still_the_id_after_it() -> None:
    """Pinned against the ledger row R1 wrote on 2026-08-20.

    ``var/audit/ledger.jsonl`` carries an adjudication for S201M-B16UC / rated current under
    ``025b25e5-6233-561d-a509-482ecfb6aa65``. That id was derived from ``attribute.uri`` even
    while the redline *stored* the bare key -- which is exactly the inconsistency N15 named -- so
    fixing the stored value must not move it. If this test fails, a recorded human decision has
    been orphaned from the finding it decided.
    """
    assert str(
        stable_redline_id(
            document_sha256=(
                "07b267e711236a27934be66d72e84d009284dcb4fc6a40862c32be8315d560df"
            ),
            sku_id="S201M-B16UC",
            attribute_uri="etim:EF000227",
            catalog_value="61 A",
            proposed_value="16 A",
        )
    ) == "025b25e5-6233-561d-a509-482ecfb6aa65"


def test_the_structural_id_function_was_already_fed_the_uri_so_r2_ids_did_not_move() -> None:
    """R2's ``build_structural_redline`` passed ``attribute.uri`` to the id function and
    ``attribute.key`` to the stored field. Only the second changed."""
    before = structural_redline_id(
        feed_sha256="f" * 64,
        sku_id="SKU-1",
        attribute_uri="etim:EF000227",
        catalog_value="18 A",
        proposed_value="16 A",
    )
    after = structural_redline_id(
        feed_sha256="f" * 64,
        sku_id="SKU-1",
        attribute_uri=canonical_uri("rated_current"),
        catalog_value="18 A",
        proposed_value="16 A",
    )
    assert before == after


def test_a_bare_key_and_a_uri_are_different_identities_and_that_is_the_point() -> None:
    """The negative control for the test above: the id function is not doing any normalising of
    its own, so the stability proved there comes from the callers agreeing, not from luck."""
    assert structural_redline_id(
        feed_sha256="f" * 64,
        sku_id="SKU-1",
        attribute_uri="rated_current",
        catalog_value="18 A",
        proposed_value="16 A",
    ) != structural_redline_id(
        feed_sha256="f" * 64,
        sku_id="SKU-1",
        attribute_uri="etim:EF000227",
        catalog_value="18 A",
        proposed_value="16 A",
    )
