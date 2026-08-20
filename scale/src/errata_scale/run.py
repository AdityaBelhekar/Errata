"""The catalog run: the R2 assembly, in the order the tiers demand.

One function, and its order of operations is the release:

1. **Index the feed** as a citable artifact. The catalog's own bytes get a sha256 and its cells get
   char spans, so a structural finding can be evidenced rather than asserted.
2. **Inventory before auditing** (FR-8.1). The groundable fraction is computed over the whole feed
   *before* a single value is re-derived, because a coverage number produced after the fact is a
   number chosen with hindsight.
3. **T0 over everything** (FR-8.7). Document-free checks, every record.
4. **T1/T2 over what can be grounded.** ``errata_audit.audit_sku`` unchanged -- R2 adds scale, not
   a second opinion about how a single SKU is audited. The document's text layer and tables are
   extracted once per document rather than once per record, which is the only reason a 10,000-row
   run finishes in seconds.
5. **Cluster, then rank** (FR-8.5, FR-8.4). In that order, because ``record_multiplicity`` is a
   term in the ranking and it is not knowable one record at a time. R1 left it at 1; this is where
   it becomes a computed number.
6. **Record the batch** (FR-8.8), so reversal is a query.

What the run refuses to do is as load-bearing as what it does: it does not fill a missing document
with a similar one, it does not default a class, it does not drop a record it could not handle, and
it does not convert a record with no evidence into a finding. Every record leaves this function
countable, in exactly one bucket, with a reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from errata_audit import (
    AttributeMap,
    CalibrationModel,
    CatalogRecord,
    DocumentSource,
    EtimModel,
    Ledger,
    Outcome,
    SkuAudit,
    audit_sku,
    extract_layer,
    extract_tables,
    load_attributes,
    load_catalog,
)
from errata_audit.audit import AUDIT_VERSION
from errata_audit.classify import ClassScope
from errata_spec import Redline, ResolutionPolicy, builtin_policy

from .feedindex import FeedIndex, index_feed
from .groundable import GroundableFractionReport, GroundingStatus, inventory
from .ids import batch_id
from .queue import ReviewQueue
from .signatures import SignatureCluster, cluster_signatures
from .structural import STRUCTURAL_VERSION, StructuralResult, run_structural
from .tiers import CostReport, Tier, TierCost
from .triage import TriageResult, route

__all__ = ["SCALE_VERSION", "CatalogRun", "run_catalog"]

SCALE_VERSION = "errata-scale/1.0.0"


@dataclass(frozen=True, slots=True)
class CatalogRun:
    """One audit of one catalog. Everything downstream reads this object."""

    batch_id: str
    catalog: str
    feed: FeedIndex
    records: tuple[CatalogRecord, ...]
    groundable: GroundableFractionReport
    structural: StructuralResult
    audits: tuple[SkuAudit, ...]
    triage: TriageResult
    cost: CostReport
    policy_version: str
    attribute_map_version: str
    etim_release: str
    etim_attribution: str
    started_utc: datetime = field(default_factory=lambda: datetime.now(UTC))
    scale_version: str = SCALE_VERSION
    audit_version: str = AUDIT_VERSION
    structural_version: str = STRUCTURAL_VERSION
    notes: tuple[str, ...] = ()

    # -- the numbers -------------------------------------------------------------------------

    @property
    def clusters(self) -> tuple[SignatureCluster, ...]:
        return self.triage.clusters

    @property
    def findings(self) -> int:
        return len(self.triage.entries)

    @property
    def grounded_findings(self) -> int:
        return sum(1 for entry in self.triage.entries if entry.tier == Tier.T1_GROUNDED.value)

    @property
    def structural_findings(self) -> int:
        return sum(1 for entry in self.triage.entries if entry.tier == Tier.T0_STRUCTURAL.value)

    def declined_by_reason(self) -> dict[str, int]:
        """Every decline from both tiers, in one table.

        The structural tier's declines and the grounded tier's declines are the same kind of fact
        -- "we looked and could not answer" -- and separating them in the report would let a reader
        believe the coverage number came from a smaller denominator than it did.
        """
        counts = dict(self.structural.declined_by_reason())
        for sku in self.audits:
            for outcome in sku.declined:
                key = outcome.declined_reason.value if outcome.declined_reason else "unspecified"
                counts[key] = counts.get(key, 0) + 1
        ungrounded = self.groundable.counts()
        for status in (
            GroundingStatus.DOCUMENT_NAMED_NOT_SUPPLIED,
            GroundingStatus.NO_DOCUMENT_NAMED,
            GroundingStatus.DOCUMENT_UNREADABLE,
        ):
            reason = status.declined_reason
            if reason is None or not ungrounded[status]:
                continue
            counts[reason.value] = counts.get(reason.value, 0) + ungrounded[status]
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    @property
    def grounded_coverage(self) -> float:
        """Coverage over the records that had a document. Read it next to the groundable fraction.

        Quoting this number alone would be the most flattering honest sentence available -- it
        describes the population where evidence existed. The report never prints it without the
        groundable fraction beside it, and neither should anyone else.
        """
        considered = [
            outcome
            for sku in self.audits
            for outcome in sku.outcomes
            if outcome.outcome != Outcome.NOT_IN_FEED
        ]
        audited = [o for o in considered if o.outcome in {Outcome.FINDING, Outcome.RESOLVED}]
        return len(audited) / len(considered) if considered else 0.0

    @property
    def catalog_coverage(self) -> float:
        """The fraction of the *whole catalog* on which any tier reached a verdict.

        The number a customer actually experiences.
        """
        verdicts = {
            (outcome.sku_id, outcome.attribute.key)
            for outcome in self.structural.outcomes
            if outcome.outcome in {Outcome.FINDING, Outcome.RESOLVED}
        }
        verdicts |= {
            (sku.record.sku_id, outcome.attribute.key)
            for sku in self.audits
            for outcome in sku.outcomes
            if outcome.outcome in {Outcome.FINDING, Outcome.RESOLVED}
        }
        cells = sum(
            1
            for record in self.records
            for key in self._audited_keys()
            if record.value(key) is not None
        )
        return len(verdicts) / cells if cells else 0.0

    def _audited_keys(self) -> tuple[str, ...]:
        return tuple(
            sorted({outcome.attribute.key for outcome in self.structural.outcomes})
            or sorted(
                {
                    outcome.attribute.key
                    for sku in self.audits
                    for outcome in sku.outcomes
                }
            )
        )

    def redlines(self) -> tuple[Redline, ...]:
        return tuple(entry.redline for entry in self.triage.entries)

    def manifest(self) -> dict[str, object]:
        """What this run was, in a form the ledger can hold and a reader can check."""
        return {
            "catalog": self.catalog,
            "feed_sha256": self.feed.sha256,
            "records": len(self.records),
            "policy_version": self.policy_version,
            "attribute_map_version": self.attribute_map_version,
            "etim_release": self.etim_release,
            "scale_version": self.scale_version,
            "audit_version": self.audit_version,
            "structural_version": self.structural_version,
            "started_utc": self.started_utc.isoformat(),
            "groundable_fraction": round(self.groundable.groundable_fraction, 6),
            "findings": self.findings,
            "clusters": len(self.clusters),
            "notes": list(self.notes),
        }


def run_catalog(
    catalog: Path | str,
    documents: Mapping[str, DocumentSource] | Sequence[DocumentSource] = (),
    *,
    etim: EtimModel | None = None,
    scope: ClassScope | None = None,
    attributes: AttributeMap | None = None,
    calibration: CalibrationModel | None = None,
    policy: ResolutionPolicy | None = None,
    limit: int = 0,
    label: str = "",
    ledger: Ledger | None = None,
    propagation: dict[str, int] | None = None,
    revenue_weight: dict[str, float] | None = None,
    notes: Sequence[str] = (),
) -> CatalogRun:
    """Audit a whole catalog, tier by tier.

    ``etim`` and ``scope`` may be omitted, and then T1 does not run: the result is a T0-only audit
    with an honest groundable fraction of whatever the documents support. That is not a degraded
    mode to be ashamed of -- it is the mode most real catalogs start in, and being able to hand
    somebody a report on day one, before any document has been collected, is the difference between
    a pilot and a procurement exercise.
    """
    catalog_path = Path(catalog)
    attributes = attributes or load_attributes()
    policy = policy or builtin_policy()

    records = load_catalog(catalog_path)
    if limit:
        records = records[:limit]

    feed = index_feed(catalog_path)
    supplied = dict(documents) if isinstance(documents, Mapping) else {
        document.path.name: document for document in documents
    }

    ground = inventory(records, supplied, catalog=catalog_path.name)

    structural = run_structural(records, feed, attributes=attributes)

    audits: list[SkuAudit] = []
    layers: dict[str, object] = {}
    tables: dict[str, object] = {}
    if etim is not None and scope is not None:
        groundable_rows = {
            entry.sku_id: entry
            for entry in ground.records_in(GroundingStatus.GROUNDABLE)
        }
        by_name = {name.replace("\\", "/").rsplit("/", 1)[-1]: doc for name, doc in supplied.items()}
        only = next(iter(supplied.values())) if len(supplied) == 1 else None
        for record in records:
            if record.sku_id not in groundable_rows:
                continue
            named = record.datasheet.replace("\\", "/").rsplit("/", 1)[-1]
            document = by_name.get(named) or only
            if document is None:
                continue
            if document.sha256 not in layers:
                layers[document.sha256] = extract_layer(
                    document.path, document_sha256=document.sha256
                )
                tables[document.sha256] = extract_tables(
                    document.path, document_sha256=document.sha256
                )
            audits.append(
                audit_sku(
                    record,
                    document,
                    etim=etim,
                    scope=scope,
                    attributes=attributes,
                    calibration=calibration,
                    policy=policy,
                    layer=layers[document.sha256],  # type: ignore[arg-type]
                    tables=tables[document.sha256],  # type: ignore[arg-type]
                    propagation=propagation,
                )
            )

    tier_of: dict[str, str] = {}
    redlines: list[Redline] = []
    for outcome in structural.findings:
        assert outcome.redline is not None
        redlines.append(outcome.redline)
        tier_of[str(outcome.redline.redline_id)] = Tier.T0_STRUCTURAL.value
    for sku in audits:
        for outcome in sku.findings:
            assert outcome.redline is not None
            redlines.append(outcome.redline)
            tier_of[str(outcome.redline.redline_id)] = Tier.T1_GROUNDED.value

    clusters = cluster_signatures(redlines, tier_of=tier_of)
    triage = route(
        redlines,
        clusters,
        tier_of=tier_of,
        propagation=propagation,
        revenue_weight=revenue_weight,
    )

    cost = _cost_report(
        records=records,
        structural=structural,
        audits=audits,
        ground=ground,
        queue_rows=len(triage.entries),
        attributes_examined=structural.attributes_examined,
    )

    identifier = str(
        batch_id(
            feed_sha256=feed.sha256,
            policy_version=policy.version_tag,
            attribute_map_version=attributes.version,
            code_versions=(SCALE_VERSION, AUDIT_VERSION, STRUCTURAL_VERSION),
            label=label,
        )
    )

    run = CatalogRun(
        batch_id=identifier,
        catalog=str(catalog_path),
        feed=feed,
        records=records,
        groundable=ground,
        structural=structural,
        audits=tuple(audits),
        triage=triage,
        cost=cost,
        policy_version=policy.version_tag,
        attribute_map_version=attributes.version,
        etim_release=etim.release if etim is not None else "",
        etim_attribution=etim.attribution if etim is not None else "",
        notes=tuple(notes),
    )

    if ledger is not None:
        ReviewQueue(triage, ledger=ledger, batch_id=identifier).record_batch(run.manifest())

    return run


def _cost_report(
    *,
    records: Sequence[CatalogRecord],
    structural: StructuralResult,
    audits: Sequence[SkuAudit],
    ground: GroundableFractionReport,
    queue_rows: int,
    attributes_examined: int,
) -> CostReport:
    """Count what each tier actually did. Nothing here is estimated."""
    disagreements = len(structural.findings) + sum(len(sku.findings) for sku in audits)
    derivations = sum(
        1
        for sku in audits
        for outcome in sku.outcomes
        if outcome.outcome != Outcome.NOT_IN_FEED
    )

    return CostReport(
        records=len(records),
        error_count=disagreements,
        groundable=ground.groundable,
        tiers=(
            TierCost(
                tier=Tier.T0_STRUCTURAL,
                records_entered=len(records),
                work_units=len(records) * max(1, attributes_examined),
                unit="cell checks",
                note=(
                    "one pass over every cell of every record; no document is opened and no model "
                    "is called"
                ),
            ),
            TierCost(
                tier=Tier.T1_GROUNDED,
                records_entered=len(audits),
                work_units=derivations,
                unit="re-derivations",
                note=(
                    "runs only on records the groundable-fraction report placed in GROUNDABLE; "
                    f"{ground.total - ground.groundable:,} record(s) never entered this tier"
                ),
            ),
            TierCost(
                tier=Tier.T2_DEEP,
                records_entered=disagreements,
                work_units=sum(len(sku.findings) for sku in audits),
                unit="counter-evidence searches",
                note=(
                    "errata_audit.audit._judge calls find_counter_evidence only after a comparison "
                    "raises a finding, so the tier boundary is a code path rather than a diagram"
                ),
            ),
            TierCost(
                tier=Tier.T3_HUMAN,
                records_entered=queue_rows,
                work_units=queue_rows,
                unit="queue rows offered",
                note="one row per finding; a reviewer may stop at any point and the rest stay open",
            ),
        ),
    )
