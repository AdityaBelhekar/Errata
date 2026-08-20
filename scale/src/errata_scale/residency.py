"""NFR-6 -- a deployment mode in which no record-level finding leaves the customer's infrastructure.

    "Record-level findings storable in the customer's own tenant. Deployment mode where no
    record-level finding leaves customer infrastructure."

``phase4-full-spec.md`` §664 is where this requirement comes from and it is worth quoting, because
it explains why the requirement is commercial rather than regulatory: *"Report at aggregate
severity levels with record-level detail held in the customer's own tenant rather than yours."*

**What the product actually holds, and why a customer's lawyer will care.** Errata produces a
ranked list of records where a named company's catalog contradicts a named manufacturer's
datasheet, with the page and the box. That artifact is discoverable. If it lives in a vendor's
tenant it is a third party's file describing the customer's defects, produced by a system with a
non-zero false-positive rate. The repository already refuses to key a defect count to a supplier
name -- ``FR-8.6``, with a test asserting the schema field's absence, because "a defect count keyed
to a named company, produced by a system with a non-zero false-positive rate, is defamation with a
dashboard". Residency is the same argument one level up: it is about where the file *sits*, not
what is in it.

**The mechanism is a classification, not a flag.** Every field a run can emit is either
RECORD-LEVEL or AGGREGATE, declared here, once. In :attr:`ResidencyMode.TENANT_LOCAL` the egress
guard walks a payload and refuses it if any record-level key or any value that looks like a record
identifier is present. That is deliberately stricter than filtering: a filter that silently drops
fields would let a caller believe it had exported something it had not, and the failure mode this
requirement guards is *not noticing*.

**What "leaves" means here, honestly.** This module governs a payload handed to something that
egresses -- telemetry, a vendor-side dashboard, an error report. It cannot govern a network stack,
and it does not claim to: NFR-6's acceptance criterion is a deployment *mode*, and a mode is a
contract about what the software will hand over. What makes the contract enforceable rather than
aspirational is that the aggregate payload is the ONLY thing with a function that produces it, and
that function cannot be given record-level content without raising.

**One thing this mode does not do, stated so nobody assumes it.** It does not encrypt, it does not
authenticate, and it does not stop an operator opening the local report and emailing it. It stops
*Errata* from being the thing that moved it.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "AGGREGATE_FIELDS",
    "RECORD_LEVEL_FIELDS",
    "EgressRefused",
    "ResidencyMode",
    "ResidencyPolicy",
    "aggregate_payload",
    "assert_egress_allowed",
    "classify_field",
]


class ResidencyMode(str, enum.Enum):
    """Where record-level findings are allowed to go."""

    OPEN = "open"
    """No residency constraint. The default, and correct for a local run against your own catalog
    -- there is no "leaving" when the operator and the data owner are the same person."""

    TENANT_LOCAL = "tenant_local"
    """NFR-6. Record-level findings are written only under the customer's declared root, and
    nothing carrying a record identifier may be handed to anything that egresses."""


class EgressRefused(PermissionError):
    """A payload carrying record-level detail was offered for egress under TENANT_LOCAL.

    A ``PermissionError`` rather than a ``ValueError``: the payload is not malformed, it is not
    allowed, and the two call for different reactions from a caller.
    """


#: Fields that identify a single record of the customer's catalog, or a single finding about one.
#: This is the list the guard enforces, so it is the list to extend when a new field appears --
#: and extending it is a visible edit rather than a pattern quietly matching more or less.
RECORD_LEVEL_FIELDS = frozenset(
    {
        "sku",
        "sku_id",
        "mpn",
        "record_id",
        "attribute_id",
        "redline_id",
        "claim_id",
        "abstention_id",
        "catalog_value",
        "value_raw",
        "evidence_value",
        "proposed_value",
        "snippet",
        "char_span",
        "bbox",
        "evidence",
        "row_header",
        "table_cell",
        "datasheet",
        "description",
        "entries",
        "findings_detail",
        "queue",
    }
)

#: Fields that describe the run rather than any record in it. These are what an aggregate payload
#: may carry. Counts, rates, versions and durations say how the audit went; none of them says
#: which product was wrong.
AGGREGATE_FIELDS = frozenset(
    {
        "batch_id",
        "catalog",
        "feed_sha256",
        "records",
        "findings",
        "clusters",
        "groundable_fraction",
        "policy_version",
        "attribute_map_version",
        "etim_release",
        "scale_version",
        "audit_version",
        "structural_version",
        "started_utc",
        "notes",
        "severity_counts",
        "declined_counts",
        "cost_report",
        "priced_cost",
        "versus_extractbench",
        "residency",
    }
    # The cost payload's own keys (errata_scale.costing.PricedCost.as_dict). Listed rather than
    # granted wholesale by their parent key, because the guard deliberately recurses INTO an
    # aggregate-keyed value: `{"clusters": 12}` is a count and `{"clusters": [{"sku_id": ...}]}`
    # is a list of the customer's defective products, and only recursion tells them apart. The
    # price of that strictness is that every nested key has to be named here, which is the right
    # price.
    | {
        "rate_card_id",
        "currency",
        "machine",
        "measured",
        "total_cents",
        "total_seconds",
        "cents_per_record",
        "cents_per_page_processed",
        "cents_per_error",
        "tiers",
        "tier",
        "seconds",
        "work_units",
        "cents",
        "basis",
        "caveats",
        "reference_cents_per_page",
        "reference_source",
        "pages_processed",
        "catalog_records",
        "errata_cents_per_page_processed",
        "errata_cents_per_catalog_record",
        "note",
    }
)

#: Value shapes that are record identifiers whatever key they arrive under. A guard that trusted
#: field names alone would be defeated by one rename, and a rename is exactly what happens when a
#: dashboard is built in a hurry.
_LOOKS_LIKE_RECORD_ID = (
    # `<document>::<sku>-<attribute>` -- the corpus and gold-set record id shape.
    re.compile(r"^[\w.-]+::[\w.-]+$"),
    # A UUID. Claim, abstention and redline ids are all UUID4.
    re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"),
)


def classify_field(name: str) -> str:
    """``record`` | ``aggregate`` | ``unknown``.

    ``unknown`` is not a third state to be relaxed into. :func:`assert_egress_allowed` treats it
    as record-level, because a field nobody has classified is a field nobody has thought about,
    and the safe reading of an unclassified field in a residency guard is the strict one.
    """
    key = name.lower()
    if key in RECORD_LEVEL_FIELDS:
        return "record"
    if key in AGGREGATE_FIELDS:
        return "aggregate"
    return "unknown"


@dataclass(frozen=True, slots=True)
class ResidencyPolicy:
    """Where this deployment may write record-level findings, and whether anything may leave."""

    mode: ResidencyMode = ResidencyMode.OPEN
    tenant_root: Path | None = None
    """The customer's own storage. Required in TENANT_LOCAL: a mode that promises record-level
    detail stays in the customer's tenant has to be told where the tenant is."""

    def __post_init__(self) -> None:
        if self.mode is ResidencyMode.TENANT_LOCAL and self.tenant_root is None:
            raise ValueError(
                "TENANT_LOCAL requires tenant_root. NFR-6 promises record-level findings are "
                "stored in the customer's own tenant, and a promise about a location needs the "
                "location -- defaulting it to the working directory would put the customer's "
                "defect list wherever the process happened to start."
            )

    @property
    def restricted(self) -> bool:
        return self.mode is ResidencyMode.TENANT_LOCAL

    def resolve_sink(self, filename: str) -> Path:
        """Where a record-level artifact may be written under this policy.

        In TENANT_LOCAL this is always under :attr:`tenant_root`, and a filename that tries to
        escape it -- ``../``, an absolute path -- raises rather than being normalised. Silently
        clamping a traversal would mean the guard's own error message was the only place the
        attempt was ever recorded.
        """
        if not self.restricted:
            return Path(filename)

        assert self.tenant_root is not None  # guaranteed by __post_init__
        root = self.tenant_root.resolve()
        target = (root / filename).resolve()
        if root not in target.parents and target != root:
            raise EgressRefused(
                f"{filename!r} resolves to {target}, which is outside the declared tenant root "
                f"{root}. Under NFR-6 a record-level artifact has exactly one legal home and this "
                "is not it."
            )
        return target

    def describe(self) -> str:
        if not self.restricted:
            return (
                "residency: OPEN -- no constraint. Correct for a local run where the operator and "
                "the data owner are the same party."
            )
        return (
            f"residency: TENANT_LOCAL -- record-level findings are written only under "
            f"{self.tenant_root}, and any payload offered for egress that carries a record "
            "identifier is refused rather than filtered (NFR-6)."
        )


def _offending(payload: Any, path: str = "") -> Iterable[str]:
    """Every place in ``payload`` that carries record-level content, as readable paths."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}" if path else str(key)
            kind = classify_field(str(key))
            if kind != "aggregate":
                # Unknown counts as record-level. See classify_field.
                yield f"{here} ({'record-level' if kind == 'record' else 'unclassified'})"
                continue

            # An explicitly aggregate key is trusted for its OWN scalar value, and the value-shape
            # heuristic below is not applied to it. That exemption was earned the hard way: the
            # guard refused a legitimate aggregate payload because `batch_id` is a UUID and the
            # heuristic matches UUIDs. A batch id names the RUN, not a record -- it is a UUID5 over
            # the feed hash and the policy version -- and classifying it aggregate is a deliberate
            # act by someone who thought about it. The heuristic exists to catch identifiers
            # arriving under keys nobody classified, which is a different thing.
            #
            # Containers are still walked, so `{"clusters": 12}` passes and
            # `{"clusters": [{"sku_id": ...}]}` does not. That distinction is the whole module.
            if isinstance(value, (dict, list, tuple)):
                yield from _offending(value, here)
        return

    if isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            yield from _offending(item, f"{path}[{index}]")
        return

    if isinstance(payload, str):
        for pattern in _LOOKS_LIKE_RECORD_ID:
            if pattern.match(payload):
                yield f"{path} (value looks like a record identifier: {payload!r})"
                return


def assert_egress_allowed(payload: Any, policy: ResidencyPolicy) -> None:
    """Refuse a payload that carries record-level detail out of a TENANT_LOCAL deployment.

    Refuses rather than redacts, on purpose. A guard that quietly stripped the offending fields
    would hand the caller a payload it believed was complete, and the thing NFR-6 protects against
    is a record-level finding leaving without anyone noticing. An exception is noticed.
    """
    if not policy.restricted:
        return
    offenders = sorted(set(_offending(payload)))
    if offenders:
        raise EgressRefused(
            "NFR-6: this payload may not leave the customer's infrastructure under TENANT_LOCAL.\n"
            + "\n".join(f"  - {o}" for o in offenders[:20])
            + (f"\n  ... and {len(offenders) - 20} more" if len(offenders) > 20 else "")
            + "\n\nUse errata_scale.residency.aggregate_payload() to build something that may "
            "leave, or write the full report to the tenant root and send nobody a copy."
        )


def aggregate_payload(run: Any, policy: ResidencyPolicy) -> dict[str, Any]:
    """The only thing a TENANT_LOCAL deployment will hand to something that egresses.

    Counts, rates, versions and the cost model. No sku, no mpn, no value, no span, no box, no
    error-signature membership -- a cluster's *size* is aggregate, its *members* are not.

    Built by construction rather than by filtering a full report, and that is the load-bearing
    choice: a filter has to be right about every field that exists now and every field added
    later, while a constructor has to be right about the fields it names. The guard then runs over
    its own output, so a mistake here fails immediately rather than shipping.
    """
    manifest = run.manifest() if hasattr(run, "manifest") else dict(run)
    payload: dict[str, Any] = {
        "residency": policy.mode.value,
        "batch_id": manifest.get("batch_id", getattr(run, "batch_id", "")),
        "feed_sha256": manifest.get("feed_sha256", ""),
        "records": manifest.get("records", 0),
        "findings": manifest.get("findings", 0),
        "clusters": manifest.get("clusters", 0),
        "groundable_fraction": manifest.get("groundable_fraction", 0.0),
        "policy_version": manifest.get("policy_version", ""),
        "attribute_map_version": manifest.get("attribute_map_version", ""),
        "etim_release": manifest.get("etim_release", ""),
        "scale_version": manifest.get("scale_version", ""),
        "audit_version": manifest.get("audit_version", ""),
        "structural_version": manifest.get("structural_version", ""),
        "started_utc": manifest.get("started_utc", ""),
        "notes": list(manifest.get("notes", ())),
    }

    # `catalog` is the catalog's FILE NAME and is deliberately omitted. It is not a record
    # identifier and it is very often a customer identifier -- "acme-electrical-master.csv" names
    # the company as surely as a field called `supplier` would, which is the same reasoning that
    # keeps a supplier name out of an error signature (FR-8.6).
    priced = getattr(run, "priced", None)
    if priced is not None:
        payload["priced_cost"] = priced.as_dict()

    assert_egress_allowed(payload, policy)
    return payload
