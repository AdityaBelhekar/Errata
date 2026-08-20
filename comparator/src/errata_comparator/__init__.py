"""errata-comparator -- disagreement classification and equivalence resolution.

Open source (§9.1): the taxonomy is the intellectual contribution. The tuned models and the
disagreement-pattern corpus behind it are not in this repository.

    from errata_comparator import AttributeSpec, compare_attribute
    from errata_valuesem import Kind

    rated_current = AttributeSpec(
        key="rated_current", label="Rated current", kinds=(Kind.QUANTITY,)
    )
    result = compare_attribute(rated_current, catalog_raw="63 A", evidence_raw="6 A")
    result.disagreement_class     # DisagreementClass.CONTRADICTION
    result.raises_finding         # True

    material = AttributeSpec(key="material_grade", kinds=(Kind.MATERIAL,))
    compare_attribute(material, "316 SS", "1.4401").raises_finding    # False
"""

from __future__ import annotations

from .compare import (
    GRAMMAR_VERSION,
    RELATION_TO_CLASS,
    AttributeSpec,
    Comparison,
    classify,
    compare_attribute,
)
from .redline import build_redline

__version__ = "0.1.0"

__all__ = [
    "GRAMMAR_VERSION",
    "RELATION_TO_CLASS",
    "AttributeSpec",
    "Comparison",
    "__version__",
    "build_redline",
    "classify",
    "compare_attribute",
]
