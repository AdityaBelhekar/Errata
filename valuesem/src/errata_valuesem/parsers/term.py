"""Controlled-vocabulary terms, generic subsuming terms, and booleans.

Closed vocabularies only run when the caller names one. ``AC`` is a current type, an RCD type and
the head of a utilisation category, and resolving it without knowing the attribute would be a coin
toss dressed as a lookup. When an alias is claimed by several vocabularies and none was named, this
parser refuses and says which ones -- a reviewer can act on that; a wrong guess they cannot see is
how a false accusation gets made.

Generic terms (``Threaded``, ``Stainless steel``) are different: they carry no vocabulary
ambiguity, so they resolve without a hint. They exist to make the granularity-mismatch branch of
§3.3 possible -- to say "under-specified" where a naive comparator says "wrong".
"""

from __future__ import annotations

import re
from typing import Any

from .. import ontology
from ..model import Kind, NormalizedValue, Refusal, RefusalReason, TermSpec

__all__ = ["GRAMMAR_VERSION", "PREFILTER", "parse", "parse_boolean", "parse_generic"]

GRAMMAR_VERSION = "term/1.1.0"
PARSER_NAME = "term"

PREFILTER = re.compile(r"^[\w\s./+\-()]{1,64}$")


def parse(text: str, ctx: dict[str, Any] | None = None) -> NormalizedValue | Refusal | None:
    """Resolve inside a named vocabulary. Requires ``ctx['vocabulary']``."""
    vocabulary = (ctx or {}).get("vocabulary")
    if not vocabulary:
        return None
    if not PREFILTER.match(text.strip()):
        return None

    onto = ontology.load()
    if vocabulary not in onto.vocabularies:
        return Refusal(
            reason=RefusalReason.UNKNOWN_TERM,
            raw=text,
            detail=f"unknown vocabulary {vocabulary!r}; known: {sorted(onto.vocabularies)}",
            attempted=(PARSER_NAME,),
        )

    hit = onto.term(text, vocabulary=vocabulary)
    if hit is None:
        return Refusal(
            reason=RefusalReason.UNKNOWN_TERM,
            raw=text,
            detail=(
                f"{text!r} is not a listed value of {vocabulary!r} "
                f"({onto.vocabularies[vocabulary].label}). Constrained decoding rejects it "
                "rather than coercing it to the nearest listed value."
            ),
            attempted=(PARSER_NAME,),
        )

    assert not isinstance(hit, tuple)
    return _value(hit, text)


_HAS_LETTER = re.compile(r"[A-Za-z]")


def parse_ambiguous(text: str, ctx: dict[str, Any] | None = None) -> NormalizedValue | Refusal | None:
    """Resolve without a vocabulary. Succeeds only when exactly one vocabulary claims the alias.

    Requires a letter in the surface form. ``2`` is a listed value of the pole-count vocabulary and
    it is also the number two; without the attribute's identity there is no way to tell, and
    silently choosing "2 poles" would put a fabricated semantic reading into the comparator.
    """
    if not PREFILTER.match(text.strip()) or not _HAS_LETTER.search(text):
        return None
    hit = ontology.load().term(text)
    if hit is None:
        return None
    if isinstance(hit, tuple):
        return Refusal(
            reason=RefusalReason.AMBIGUOUS_PARSE,
            raw=text,
            detail=(
                f"{text!r} is a listed value of several vocabularies "
                f"({', '.join(t.vocabulary for t in hit)}); name one to resolve it"
            ),
            attempted=(PARSER_NAME,),
        )
    return _value(hit, text)


def parse_generic(text: str, ctx: dict[str, Any] | None = None) -> NormalizedValue | Refusal | None:
    """Resolve a generic subsuming term such as ``Threaded`` or ``Stainless steel``."""
    if not PREFILTER.match(text.strip()):
        return None
    generic = ontology.load().generic(text)
    if generic is None:
        return None
    spec = TermSpec(
        vocabulary="generic",
        term_id=generic.id,
        canonical=generic.canonical,
        matched_alias=text.strip(),
        subsumes_kinds=generic.subsumes_kinds,
        subsumes_groups=generic.subsumes_groups,
        subsumes_terms=generic.subsumes_terms,
        restrict_thread_system=generic.restrict_thread_system,
    )
    notes = ()
    if generic.restrict_thread_system:
        notes = (f"restricted to the {generic.restrict_thread_system} thread system",)
    return NormalizedValue(
        kind=Kind.TERM,
        payload=spec,
        raw=text,
        canonical_text=generic.id,
        grammar_version=GRAMMAR_VERSION,
        parser="generic",
        notes=notes,
    )


def parse_boolean(text: str, ctx: dict[str, Any] | None = None) -> NormalizedValue | Refusal | None:
    """Resolve a yes/no. Only runs when the caller expects a boolean, because ``1`` and ``0`` are
    boolean in a feature flag and numeric everywhere else."""
    if not (ctx or {}).get("expects_boolean"):
        return None
    value = ontology.load().boolean(text)
    if value is None:
        return Refusal(
            reason=RefusalReason.UNKNOWN_TERM,
            raw=text,
            detail=f"{text!r} is not a recognised boolean surface form",
            attempted=("boolean",),
        )
    return NormalizedValue(
        kind=Kind.BOOLEAN,
        payload=value,
        raw=text,
        canonical_text="true" if value else "false",
        grammar_version=GRAMMAR_VERSION,
        parser="boolean",
    )


def _value(term: Any, text: str) -> NormalizedValue:
    return NormalizedValue(
        kind=Kind.TERM,
        payload=TermSpec(
            vocabulary=term.vocabulary,
            term_id=term.id,
            canonical=term.canonical,
            matched_alias=text.strip(),
        ),
        raw=text,
        canonical_text=term.id,
        grammar_version=GRAMMAR_VERSION,
        parser=PARSER_NAME,
        notes=(term.note,) if term.note else (),
    )
