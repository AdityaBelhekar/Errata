"""errata-spec -- the claim schema, the disagreement taxonomy, and the resolution-policy DSL.

Open source on purpose (§9.1): a provenance format only becomes an interchange standard if it is
free, and adoption by a PIM vendor is a win rather than a leak.

Three ideas carry the design:

**Claims, not values.** Nothing stores "the value of attribute X for SKU Y". It stores immutable
assertions *about* that value, each with its evidence, its extractor fingerprint and its calibrated
confidence. Conflicts are resolved by a versioned policy document, and the resolved value records
which policy version resolved it -- so "why does this field say 6 A" has an answer that is a chain
of facts rather than an opinion.

**Abstentions are a different type from claims.** Not a null, not an empty string. A type the
downstream code cannot mistake for a value.

**Redlines, not writes.** The output is addressed to a human and carries the case against itself.
"""

from __future__ import annotations

from .claim import (
    Abstention,
    AsserterKind,
    BBox,
    Claim,
    ClaimStatus,
    Confidence,
    EmptyEvidenceError,
    Evidence,
    ExtractorFingerprint,
    emit_abstention,
    emit_extracted_claim,
)
from .policy import ResolutionPolicy, RuleAction, builtin_policy, load_policy
from .redline import (
    Adjudication,
    BlastRadius,
    CounterEvidence,
    Decision,
    Redline,
)
from .registry import (
    DocumentRegister,
    DocumentRevision,
    Fetch,
    RevisionNotFoundError,
    sha256_bytes,
)
from .taxonomy import (
    CLASS_PROFILE,
    SAFETY_CLASS_ATTRIBUTES,
    ClassProfile,
    DeclinedReason,
    DisagreementClass,
    Severity,
    is_safety_class,
)

__version__ = "0.1.0"

__all__ = [
    "CLASS_PROFILE",
    "SAFETY_CLASS_ATTRIBUTES",
    "Abstention",
    "Adjudication",
    "AsserterKind",
    "BBox",
    "BlastRadius",
    "Claim",
    "ClaimStatus",
    "ClassProfile",
    "Confidence",
    "CounterEvidence",
    "Decision",
    "DeclinedReason",
    "DisagreementClass",
    "DocumentRegister",
    "DocumentRevision",
    "EmptyEvidenceError",
    "Evidence",
    "ExtractorFingerprint",
    "Fetch",
    "Redline",
    "ResolutionPolicy",
    "RevisionNotFoundError",
    "RuleAction",
    "Severity",
    "__version__",
    "builtin_policy",
    "emit_abstention",
    "emit_extracted_claim",
    "is_safety_class",
    "load_policy",
    "sha256_bytes",
]
