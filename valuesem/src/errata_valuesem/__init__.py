"""errata-valuesem -- deterministic value semantics for industrial product data.

The hard rule of this package, enforced by ``tests/test_determinism_boundary.py`` rather than by
convention: **no model call and no network call in any code path.** Everything here has a knowable
right answer, and a lookup table that is asked to hallucinate is worse than no lookup table.

Typical use::

    from errata_valuesem import normalize, compare

    a = normalize("316 SS")
    b = normalize("1.4401")
    compare(a, b).relation          # Relation.EQUIVALENT_VOCABULARY

    compare(normalize("63 A"), normalize("6 A")).relation
                                     # Relation.CONTRADICTION

    normalize("some free-text blurb")
                                     # Refusal(reason=value_outside_known_grammar)
"""

from __future__ import annotations

from .compare import compare
from .model import (
    EQUIVALENT_RELATIONS,
    IngressSpec,
    Interval,
    Kind,
    MaterialSpec,
    NormalizedValue,
    PackagingSpec,
    ParseResult,
    Quantity,
    Refusal,
    RefusalReason,
    Relation,
    TermSpec,
    ThreadSpec,
    Tolerance,
    Verdict,
)
from .normalize import GRAMMAR_VERSION, normalize, parsers_for

__version__ = "0.1.0"

__all__ = [
    "EQUIVALENT_RELATIONS",
    "GRAMMAR_VERSION",
    "IngressSpec",
    "Interval",
    "Kind",
    "MaterialSpec",
    "NormalizedValue",
    "PackagingSpec",
    "ParseResult",
    "Quantity",
    "Refusal",
    "RefusalReason",
    "Relation",
    "TermSpec",
    "ThreadSpec",
    "Tolerance",
    "Verdict",
    "__version__",
    "compare",
    "normalize",
    "parsers_for",
]
