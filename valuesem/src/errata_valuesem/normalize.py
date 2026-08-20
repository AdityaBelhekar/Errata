"""The normalizer pipeline: regex -> grammar -> ontology -> units (FR-4.1).

Two properties this module is responsible for, both testable:

**No model, no network.** Nothing here, and nothing it calls, opens a socket or invokes a model.
See ``tests/test_determinism_boundary.py``.

**A refusal from one family does not end the search.** ``10 EA`` is not a Pint quantity and the
dimension parser says so; the packaging parser then reads it correctly. Only when every applicable
family has declined does the value get refused -- and then it is refused with the most specific
reason any parser produced, not a generic shrug.

Attribute typing matters. ``normalize("316")`` is the number three hundred and sixteen;
``normalize("316", expect=Kind.MATERIAL)`` is AISI 316. The pipeline knows the ETIM attribute it is
auditing (FR-3.1), so it can say which, and where it cannot it declines to guess.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

from .canonical import AmbiguousNumberError, NullishError, canonicalize
from .model import Kind, NormalizedValue, ParseResult, Refusal, RefusalReason
from .ontology import GRAMMAR_VERSION as ONTOLOGY_VERSION
from .parsers import dimension, ingress, material, packaging, term, thread

__all__ = ["GRAMMAR_VERSION", "PARSER_ORDER", "normalize", "parsers_for"]

GRAMMAR_VERSION = (
    f"valuesem/1.1.0 [{thread.GRAMMAR_VERSION} {dimension.GRAMMAR_VERSION} "
    f"{ingress.GRAMMAR_VERSION} {material.GRAMMAR_VERSION} {term.GRAMMAR_VERSION} "
    f"{packaging.GRAMMAR_VERSION} {ONTOLOGY_VERSION}]"
)

Parser = Callable[[str, dict[str, Any]], ParseResult | None]

#: Default order when the caller has not named an expected kind.
#:
#: ``term.parse_ambiguous`` deliberately sits ahead of ``dimension``: Pint reads ``P`` as poise, so
#: ``2P`` becomes two poise unless the pole-count vocabulary gets first refusal. ``material`` sits
#: ahead of both because ``18/8`` is a steel and not a fraction.
PARSER_ORDER: tuple[tuple[str, Parser], ...] = (
    ("thread", thread.parse),
    ("ingress", ingress.parse),
    ("packaging", packaging.parse),
    ("material", material.parse),
    ("generic", term.parse_generic),
    ("term", term.parse_ambiguous),
    ("dimension", dimension.parse),
)

#: Chains per expected kind.
#:
#: Every chain ends with the generic-term parser, without exception. A catalog is entitled to say
#: "Threaded" in a thread field and "Stainless steel" in a material field, and if the chain for
#: Kind.THREAD contains only the thread grammar then the single most common granularity mismatch
#: in the taxonomy (§3.3) becomes an unparseable value instead of a finding. Constraining the
#: chain is about excluding *wrong readings*, not about excluding legitimate vaguer ones.
_GENERIC: tuple[str, Parser] = ("generic", term.parse_generic)

_BY_KIND: dict[Kind, tuple[tuple[str, Parser], ...]] = {
    Kind.THREAD: (("thread", thread.parse), _GENERIC),
    Kind.INGRESS: (("ingress", ingress.parse), _GENERIC),
    Kind.MATERIAL: (("material", material.parse), _GENERIC),
    Kind.PACKAGING: (("packaging", packaging.parse), _GENERIC),
    Kind.BOOLEAN: (("boolean", term.parse_boolean),),
    Kind.TERM: (("term", term.parse), _GENERIC, ("term*", term.parse_ambiguous)),
    Kind.QUANTITY: (("dimension", dimension.parse), _GENERIC),
    Kind.QUANTITY_SET: (("dimension", dimension.parse), _GENERIC),
    Kind.RANGE: (("dimension", dimension.parse), _GENERIC),
    Kind.COUNT: (("dimension", dimension.parse), _GENERIC),
}

#: Reasons ranked by how useful they are to whoever reads the Declined bucket. A refusal that names
#: the unit it did not know beats one that says "no grammar matched".
_REASON_RANK: dict[RefusalReason, int] = {
    RefusalReason.AMBIGUOUS_PARSE: 5,
    RefusalReason.MALFORMED: 4,
    RefusalReason.UNKNOWN_UNIT: 3,
    RefusalReason.UNKNOWN_TERM: 2,
    RefusalReason.EMPTY: 1,
    RefusalReason.NO_GRAMMAR_MATCH: 0,
}


def parsers_for(expect: Kind | Iterable[Kind] | None) -> tuple[tuple[str, Parser], ...]:
    """The parser chain that will run for a given expectation."""
    if expect is None:
        return PARSER_ORDER
    kinds: Sequence[Kind] = [expect] if isinstance(expect, Kind) else list(expect)
    chain: list[tuple[str, Parser]] = []
    seen: set[str] = set()
    for kind in kinds:
        for name, parser in _BY_KIND.get(kind, ()):
            if name not in seen:
                seen.add(name)
                chain.append((name, parser))
    return tuple(chain)


def normalize(
    raw: str,
    *,
    expect: Kind | Iterable[Kind] | None = None,
    vocabulary: str | None = None,
    decimal_separator: str | None = None,
) -> ParseResult:
    """Parse ``raw`` into a :class:`~errata_valuesem.model.NormalizedValue` or a
    :class:`~errata_valuesem.model.Refusal`.

    Args:
        raw: the source string, preserved verbatim on the result.
        expect: the kind(s) the attribute's schema allows. Restricting the chain both speeds it up
            and removes whole classes of misreading -- ``2P`` is a pole count, not two poise.
        vocabulary: required to resolve a value inside a closed ETIM-style value list.
        decimal_separator: ``"."`` or ``","``. Resolves the ``1,000`` ambiguity instead of
            refusing it.

    Returns:
        Never ``None``. Every input produces a value or a reasoned refusal.
    """
    if raw is None:
        return Refusal(reason=RefusalReason.EMPTY, raw="", detail="value is None")

    try:
        canonical = canonicalize(raw, decimal_separator=decimal_separator)
    except NullishError as exc:
        return Refusal(reason=RefusalReason.EMPTY, raw=raw, detail=str(exc))
    except AmbiguousNumberError as exc:
        return Refusal(reason=RefusalReason.AMBIGUOUS_PARSE, raw=raw, detail=str(exc))

    ctx: dict[str, Any] = {
        "vocabulary": vocabulary,
        "expects_material": _expects(expect, Kind.MATERIAL),
        "expects_boolean": _expects(expect, Kind.BOOLEAN),
        "decimal_separator": decimal_separator,
    }

    chain = parsers_for(expect)
    if vocabulary and expect is None:
        chain = (("term", term.parse), *chain)

    refusals: list[Refusal] = []
    attempted: list[str] = []
    for name, parser in chain:
        attempted.append(name)
        result = parser(canonical.text, ctx)
        if result is None:
            continue
        if isinstance(result, Refusal):
            refusals.append(result)
            continue
        return _finish(result, raw, canonical.notes)

    if refusals:
        best = max(refusals, key=lambda r: _REASON_RANK.get(r.reason, 0))
        return Refusal(
            reason=best.reason,
            raw=raw,
            detail=best.detail,
            attempted=tuple(attempted),
        )

    return Refusal(
        reason=RefusalReason.NO_GRAMMAR_MATCH,
        raw=raw,
        detail=(
            f"no registered grammar recognised {canonical.text!r}. This is a routable signal, not "
            "a value: it belongs in the Declined bucket, and a new grammar is a one-file fix."
        ),
        attempted=tuple(attempted),
    )


def _finish(value: NormalizedValue, raw: str, canonical_notes: tuple[str, ...]) -> NormalizedValue:
    """Restore the caller's original string and attach any notes canonicalization made."""
    from dataclasses import replace

    return replace(
        value,
        raw=raw,
        notes=tuple(n for n in (*canonical_notes, *value.notes) if n),
        grammar_version=f"{GRAMMAR_VERSION} :: {value.grammar_version}",
    )


def _expects(expect: Kind | Iterable[Kind] | None, kind: Kind) -> bool:
    if expect is None:
        return False
    if isinstance(expect, Kind):
        return expect is kind
    return kind in set(expect)
