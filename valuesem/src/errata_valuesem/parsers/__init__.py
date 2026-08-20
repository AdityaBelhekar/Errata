"""Family parsers.

Each parser is a small, self-contained module exposing two things:

``PREFILTER``
    A cheap regex that says "this might be mine". Stage 2 of the FR-4.1 pipeline: regex first, so
    a grammar is only ever invoked on a string with a plausible shape.

``parse(text, ctx) -> NormalizedValue | Refusal | None``
    ``None`` means "not my family, try the next one". A ``Refusal`` means "this is my family and
    it is malformed" -- a materially different statement, and the one that routes to the Declined
    bucket with a useful reason instead of a shrug.

Adding a family is the smallest useful contribution to this repository (§9.4): one module, one
prefilter, one grammar or table, and fixtures.
"""

from __future__ import annotations

__all__ = ["dimension", "ingress", "material", "packaging", "term", "thread"]
