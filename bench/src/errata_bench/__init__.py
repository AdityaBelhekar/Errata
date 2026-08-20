"""errata-bench -- the R0 kill tests and the evaluation harness.

Open source, matching ExtractBench's Apache 2.0 so the ecosystem we want to be cited by can adopt
ours without a licence conversation. A benchmark nobody can run is marketing (§9.1).

Today this package contains kill test 1. Kill tests 2 and 3 print what they need instead of a
number, and the public benchmark axes (FR-9.1 .. FR-9.9) are R3 work that does not start until R0
reports.
"""

from __future__ import annotations

from .equivalence import (
    Case,
    CaseResult,
    Gate,
    Label,
    Outcome,
    SuiteReport,
    load_cases,
    run_suite,
)
from .stats import Proportion, wilson

__version__ = "0.1.0"

__all__ = [
    "Case",
    "CaseResult",
    "Gate",
    "Label",
    "Outcome",
    "Proportion",
    "SuiteReport",
    "__version__",
    "load_cases",
    "run_suite",
    "wilson",
]
