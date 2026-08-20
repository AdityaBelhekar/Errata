"""errata-ecosystem -- R3: the benchmark, and the parts of it other people are meant to use.

R0 asked whether the product could work. R1 audited one SKU, R2 a catalog. R3 asks the question
that decides whether any of those numbers mean anything outside this repository:

    can somebody who did not write this reproduce the scores from the repository alone?

Everything here serves that one sentence.

* **The grounding metric is not reimplemented** (FR-9.1). ``errata_bench.operating_point`` already
  carries ExtractBench's definition -- value accepted AND box overlapping an accepted box at
  IoU 0.5 -- and the benchmark calls it. A second implementation would be a second opinion.
* **Five axes nobody scores** (FR-9.2), each runnable on its own, each reporting NOT MEASURED
  rather than a number when it has no data.
* **Reviewer-seconds and evidence-acceptance are human measurements** (FR-9.3, FR-9.4). The
  protocol and the arithmetic ship; the numbers do not exist, and the harness refuses to invent
  them from synthetic sessions.
* **The gold set is URLs, hashes and annotations** (FR-9.5). No copyrighted document is
  redistributed, and the annotation layer is verified against the documents it annotates.
* **The hard tail is frozen** (FR-9.6), hashed, and guarded by a test that fails if tuning
  touches it.
* **The bridge is published** (FR-9.7), Apache-2.0, with ODC-By attribution and a rationale on
  every row -- including the rows that refuse to map.
* **ECLASS is bring-your-own-licence** (FR-9.8). No ECLASS content in the repository, and a
  scanner that fails the build if any appears.
* **The leaderboard prints our losing scores** (FR-9.9), because it is generated from the harness
  and there is no hand-editing step in which they could be dropped.
"""

from __future__ import annotations

from .bridge import (
    ATTRIBUTE_BEARING_RELATIONS,
    AttributeBinding,
    Bridge,
    BridgeValidationError,
    Mapping,
    load_bridge,
    load_unspsc,
)
from .vocabulary import (
    UnknownAttributeTerm,
    canonical_uri,
    is_canonical,
    local_key,
    vocabulary_violations,
)

__all__ = [
    "ATTRIBUTE_BEARING_RELATIONS",
    "AttributeBinding",
    "Bridge",
    "BridgeValidationError",
    "Mapping",
    "UnknownAttributeTerm",
    "canonical_uri",
    "is_canonical",
    "load_bridge",
    "load_unspsc",
    "local_key",
    "vocabulary_violations",
]
