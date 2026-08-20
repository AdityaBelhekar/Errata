"""NFR-6 -- the deployment mode where no record-level finding leaves the customer's tenant.

The requirement had zero lines of code and zero mentions outside the PRD table and one sentence of
``phase4-full-spec.md``. What it asks for is not a feature so much as a refusal, so most of these
tests assert that something does NOT happen.

The property under test, stated once: **under TENANT_LOCAL, nothing carrying a record identifier
can be handed to anything that egresses, and the guard refuses rather than filters.** Filtering
would hand a caller a payload it believed was complete, and the failure this requirement exists to
prevent is a record-level finding leaving without anyone noticing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from errata_scale.residency import (
    AGGREGATE_FIELDS,
    RECORD_LEVEL_FIELDS,
    EgressRefused,
    ResidencyMode,
    ResidencyPolicy,
    aggregate_payload,
    assert_egress_allowed,
    classify_field,
)


@pytest.fixture
def tenant(tmp_path: Path) -> ResidencyPolicy:
    root = tmp_path / "acme-tenant"
    root.mkdir()
    return ResidencyPolicy(mode=ResidencyMode.TENANT_LOCAL, tenant_root=root)


OPEN = ResidencyPolicy()


class _Run:
    """The parts of a CatalogRun this module reads. Enough to test the contract without paying for
    a 10,001-record audit in a unit test."""

    batch_id = "b-123"
    priced = None

    def manifest(self) -> dict:
        return {
            "catalog": "acme-electrical-master.csv",
            "feed_sha256": "abc123",
            "records": 10_001,
            "findings": 1_495,
            "clusters": 12,
            "groundable_fraction": 0.0277,
            "policy_version": "electrical-conservative@v3",
            "attribute_map_version": "errata-attributes/1.0.0",
            "etim_release": "10.0",
            "scale_version": "1",
            "audit_version": "1",
            "structural_version": "1",
            "started_utc": "2026-08-21T00:00:00+00:00",
            "notes": ["constructed catalog"],
        }


# ------------------------------------------------------------------------------------------------
# The mode itself
# ------------------------------------------------------------------------------------------------


def test_tenant_local_requires_somewhere_to_be_local_to() -> None:
    """A promise about a location needs the location."""
    with pytest.raises(ValueError, match="requires tenant_root"):
        ResidencyPolicy(mode=ResidencyMode.TENANT_LOCAL)


def test_open_is_the_default_and_constrains_nothing() -> None:
    """There is no "leaving" when the operator and the data owner are the same person."""
    assert OPEN.mode is ResidencyMode.OPEN
    assert not OPEN.restricted
    assert_egress_allowed({"sku_id": "S201M-B16UC", "value_raw": "16 A"}, OPEN)


def test_the_mode_describes_itself_in_terms_of_what_it_refuses(tenant: ResidencyPolicy) -> None:
    assert "TENANT_LOCAL" in tenant.describe()
    assert "refused" in tenant.describe()
    assert str(tenant.tenant_root) in tenant.describe()


# ------------------------------------------------------------------------------------------------
# The guard
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"sku_id": "S201M-B16UC"},
        {"findings_detail": [{"mpn": "S201M-B16UC"}]},
        {"queue": [{"redline_id": "x"}]},
        {"records": 10, "evidence": {"snippet": "Rated current 16 A"}},
    ],
)
def test_record_level_payloads_are_refused(payload: dict, tenant: ResidencyPolicy) -> None:
    with pytest.raises(EgressRefused, match="NFR-6"):
        assert_egress_allowed(payload, tenant)


def test_an_unclassified_field_is_treated_as_record_level(tenant: ResidencyPolicy) -> None:
    """A field nobody has classified is a field nobody has thought about.

    The safe reading of an unclassified field in a residency guard is the strict one, and this is
    the assertion that stops "unknown" quietly becoming a third, permissive state the day someone
    adds a column.
    """
    assert classify_field("some_new_column") == "unknown"
    with pytest.raises(EgressRefused, match="unclassified"):
        assert_egress_allowed({"some_new_column": 1}, tenant)


def test_a_record_identifier_is_caught_whatever_key_it_arrives_under(
    tenant: ResidencyPolicy,
) -> None:
    """A guard that trusted field names alone would be defeated by one rename."""
    with pytest.raises(EgressRefused, match="looks like a record identifier"):
        assert_egress_allowed(
            {"notes": ["abb-s200-2CDC002142D0207::S201M-B16UC-rated_current"]}, tenant
        )

    with pytest.raises(EgressRefused, match="looks like a record identifier"):
        assert_egress_allowed(
            {"notes": ["3f2504e0-4f89-41d3-9a0c-0305e82c3301"]}, tenant
        )


def test_the_guard_refuses_rather_than_redacting(tenant: ResidencyPolicy) -> None:
    """The whole design decision, as a test.

    A redacting guard returns something. This one returns nothing and raises, so a caller cannot
    end up believing it exported a complete payload when fields were dropped underneath it.
    """
    payload = {"records": 10, "sku_id": "S201M-B16UC"}
    with pytest.raises(EgressRefused):
        assert_egress_allowed(payload, tenant)
    assert payload == {"records": 10, "sku_id": "S201M-B16UC"}, "the guard mutated its input"


def test_the_refusal_names_every_offender_and_says_what_to_do(tenant: ResidencyPolicy) -> None:
    with pytest.raises(EgressRefused) as caught:
        assert_egress_allowed({"sku_id": "a", "mpn": "b", "records": 1}, tenant)
    message = str(caught.value)
    assert "sku_id" in message and "mpn" in message
    assert "aggregate_payload" in message


# ------------------------------------------------------------------------------------------------
# The sink
# ------------------------------------------------------------------------------------------------


def test_a_record_level_artifact_lands_under_the_tenant_root(tenant: ResidencyPolicy) -> None:
    resolved = tenant.resolve_sink("report.html")
    assert tenant.tenant_root is not None
    assert tenant.tenant_root.resolve() in resolved.parents


def test_a_path_that_escapes_the_tenant_root_raises_rather_than_being_clamped(
    tenant: ResidencyPolicy,
) -> None:
    """Silently clamping a traversal would make the guard's error the only record of the attempt."""
    with pytest.raises(EgressRefused, match="outside the declared tenant root"):
        tenant.resolve_sink("../../escaped.html")


def test_open_mode_writes_where_it_is_told(tmp_path: Path) -> None:
    assert OPEN.resolve_sink("report.html") == Path("report.html")


# ------------------------------------------------------------------------------------------------
# The aggregate payload
# ------------------------------------------------------------------------------------------------


def test_the_aggregate_payload_passes_its_own_guard(tenant: ResidencyPolicy) -> None:
    """Built by construction and then checked by the guard, so a mistake fails here not in the wild."""
    payload = aggregate_payload(_Run(), tenant)
    assert_egress_allowed(payload, tenant)
    assert payload["records"] == 10_001
    assert payload["findings"] == 1_495
    assert payload["residency"] == "tenant_local"


def test_the_aggregate_payload_omits_the_catalog_filename(tenant: ResidencyPolicy) -> None:
    """"acme-electrical-master.csv" names the company as surely as a `supplier` field would.

    This is FR-8.6's reasoning one level up: the repository refuses to key a defect count to a
    named company, and a filename that carries the company's name into an egressing payload is the
    same disclosure by a different route.
    """
    payload = aggregate_payload(_Run(), tenant)
    assert "catalog" not in payload
    assert "acme" not in str(payload).lower()


def test_the_aggregate_payload_carries_no_record_field_at_all(tenant: ResidencyPolicy) -> None:
    payload = aggregate_payload(_Run(), tenant)
    assert not (set(payload) & RECORD_LEVEL_FIELDS)
    assert set(payload) <= AGGREGATE_FIELDS, (
        f"aggregate_payload emitted {sorted(set(payload) - AGGREGATE_FIELDS)}, which is not on the "
        "aggregate list. Either classify it or stop emitting it -- an unclassified field in the "
        "one payload allowed to leave is the exact hole this requirement is about."
    )


def test_a_cluster_size_may_leave_but_its_members_may_not(tenant: ResidencyPolicy) -> None:
    """The distinction the whole module turns on, pinned.

    How many records share an error signature is a fact about the run. WHICH records share it is a
    list of the customer's defective products.
    """
    assert_egress_allowed({"clusters": 12}, tenant)
    with pytest.raises(EgressRefused):
        assert_egress_allowed({"clusters": [{"sku_id": "S201M-B16UC"}]}, tenant)


def test_the_two_field_lists_do_not_overlap() -> None:
    """A field classified both ways would resolve by dictionary order, which is not a policy."""
    assert not (RECORD_LEVEL_FIELDS & AGGREGATE_FIELDS)


def test_an_explicitly_aggregate_key_is_trusted_for_its_own_scalar(
    tenant: ResidencyPolicy,
) -> None:
    """The batch id is a UUID and is not a record identifier, and the guard has to know that.

    Found by running it: the value-shape heuristic refused a legitimate aggregate payload because
    ``batch_id`` matched the UUID pattern. A batch id names the RUN -- it is a UUID5 over the feed
    hash and the policy version -- and classifying it aggregate is a deliberate act by somebody
    who thought about it. The heuristic exists to catch identifiers arriving under keys nobody
    classified, which is a different problem, so an explicitly classified key is exempt from it.
    """
    assert_egress_allowed({"batch_id": "c0f5383c-dc9a-524a-a070-35b3b8d0a24a"}, tenant)


def test_the_exemption_does_not_extend_through_containers(tenant: ResidencyPolicy) -> None:
    """Trusting a key's own scalar must not become trusting everything underneath it."""
    with pytest.raises(EgressRefused):
        assert_egress_allowed({"notes": [{"sku_id": "S201M-B16UC"}]}, tenant)
