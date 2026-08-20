"""errata-scale -- R2: the catalog-scale audit.

R1 proved one SKU can be audited against one document. R2 asks the question a buyer actually asks:
*what does this tool tell me about my whole catalog, and can two people act on it?*

    from errata_scale import run_catalog, ReviewQueue

    run = run_catalog("catalog.csv", documents)
    run.groundable.text()      # FR-8.1 -- what could be audited at all, stated first
    run.cost.text()            # FR-8.7 -- T0 -> T3, measured, not estimated
    run.triage.top(10)         # FR-8.4 -- ranked, with every factor inspectable
    run.clusters[0].sentence() # FR-8.5 -- "1,240 records share this pattern", counted

Five commitments, each of which is a requirement rather than a preference:

* **The groundable fraction is reported before anything is audited** (FR-8.1). A defect count
  without it is unreadable.
* **Nothing updates and nothing deletes** (FR-8.2). A correction is a new claim; batch reversal is
  therefore a query (FR-8.8) rather than a recovery project.
* **Error signatures key to artifacts, never to companies** (FR-8.5, FR-8.6). There is no schema
  field for a supplier name, and a test asserts the absence rather than a reviewer noticing it.
* **The ranking shows its working** (FR-8.4). Every factor of expected review value is carried
  separately, with the sentence that says where it came from and whether it was measured at all.
* **Cost tracks errors, not rows** (FR-8.7), and the cost report counts real operations.

**What R2 does not claim.** There is still no calibration set (FR-6.1), so structural findings
carry no probability and are ranked on blast radius alone -- the queue says so on every row. The
demonstration catalog is constructed; its provenance file and every report state which parts are
real and which are not. Errata grades; it never enriches, and it never writes to a customer PIM
(ADR-001).
"""

from __future__ import annotations

from .chains import (
    ChainIntegrityError,
    ClaimChain,
    ClaimNode,
    MutationFinding,
    claim_chains,
    scan_for_mutation,
)
from .feedindex import FEED_LAYER_VERSION, FeedIndex, index_feed
from .groundable import (
    GroundableFractionReport,
    GroundingStatus,
    RecordGrounding,
    SourceType,
    inventory,
)
from .ids import batch_id, signature_id, structural_redline_id
from .queue import DrainReport, ReviewQueue, SecondAdjudicatorRequired
from .resolution import ClaimCandidate, Resolution, resolve
from .reversal import ReversalReport, accepted_in_batch, reverse_batch
from .run import SCALE_VERSION, CatalogRun, run_catalog
from .signatures import (
    BANNED_SIGNATURE_TERMS,
    DefectShape,
    ErrorSignature,
    NamedOrganisationSignatureError,
    SignatureCluster,
    assert_no_named_organisation_field,
    cluster_signatures,
    defect_shape,
    signature_for,
)
from .structural import (
    STRUCTURAL_VERSION,
    StructuralCheck,
    StructuralOutcome,
    StructuralResult,
    run_structural,
)
from .tiers import CostReport, Tier, TierCost
from .triage import Factor, QueueEntry, TriageResult, route

__version__ = "0.1.0"

__all__ = [
    "BANNED_SIGNATURE_TERMS",
    "FEED_LAYER_VERSION",
    "SCALE_VERSION",
    "STRUCTURAL_VERSION",
    "CatalogRun",
    "ChainIntegrityError",
    "ClaimCandidate",
    "ClaimChain",
    "ClaimNode",
    "CostReport",
    "DefectShape",
    "DrainReport",
    "ErrorSignature",
    "Factor",
    "FeedIndex",
    "GroundableFractionReport",
    "GroundingStatus",
    "MutationFinding",
    "NamedOrganisationSignatureError",
    "QueueEntry",
    "RecordGrounding",
    "Resolution",
    "ReversalReport",
    "ReviewQueue",
    "SecondAdjudicatorRequired",
    "SignatureCluster",
    "SourceType",
    "StructuralCheck",
    "StructuralOutcome",
    "StructuralResult",
    "Tier",
    "TierCost",
    "TriageResult",
    "__version__",
    "accepted_in_batch",
    "assert_no_named_organisation_field",
    "batch_id",
    "claim_chains",
    "cluster_signatures",
    "defect_shape",
    "index_feed",
    "inventory",
    "resolve",
    "reverse_batch",
    "route",
    "run_catalog",
    "run_structural",
    "scan_for_mutation",
    "signature_for",
    "signature_id",
    "structural_redline_id",
]
