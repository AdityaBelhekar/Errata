"""FR-2.2 / FR-2.3 / FR-2.4 -- class resolution as three stages, and an abstention when it cannot.

    "Architecture is literally three stages; an LLM is never given more than 5 candidates."

The requirement is about *shape*, and the shape is the point. A single call that hands a language
model five thousand class descriptions and asks it to choose is not a resolution architecture, it
is a prompt, and it fails in the way prompts fail: silently, plausibly, and differently each time.
Three stages make each failure inspectable -- a class that was never retrieved is a retrieval bug,
a class retrieved and ranked twelfth is a reranking bug, and a class ranked first and not chosen is
a selection bug. One number cannot tell you which.

    retrieve  -> up to 50 candidates   lexical (shipped) + embedding (interface, not shipped)
    rerank    -> exactly the top 5     deterministic feature scorer (cross-encoder interface)
    select    -> one class, or abstain LLM adapter interface; deterministic default

**What is shipped and what is an interface, stated plainly.** FR-2.2 specifies "lexical + embedding
retrieval to top-50, cross-encoder to top-5, LLM selects". This package ships the *lexical*
retriever, a *deterministic* reranker and a *deterministic* selector. The embedding retriever, the
cross-encoder and the LLM selector are protocols with no default implementation, because this
repository has no model dependency and inventing one would mean shipping a component nobody has
evaluated. The stages are real and the substitution points are typed; the model-backed halves are
absent and every report says so. That is the honest position and it is worth more than a number
produced by a model chosen for being installable.

**The five-candidate cap is structural, not documentary.** :func:`select` raises if handed more
than :data:`MAX_SELECT_CANDIDATES`. A future LLM selector cannot be given fifty candidates by
accident, because the function it must be called through refuses.

**Abstention beats a default class** (FR-2.3). When the top candidates are not separable the
resolver returns no class and a reason, and the record lands in the Declined bucket. A default
class is the worst outcome available: every downstream attribute is then judged against the wrong
schema, and the resulting redlines are confident, evidenced and wrong.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml

from errata_spec import DeclinedReason

from .etim import EtimClass, EtimModel

__all__ = [
    "MAX_SELECT_CANDIDATES",
    "RETRIEVE_K",
    "ClassCandidate",
    "ClassResolution",
    "ClassScope",
    "Embedder",
    "Reranker",
    "Selector",
    "load_scope",
    "rerank",
    "resolve_class",
    "retrieve",
    "select",
]

RESOLVER_VERSION = "errata-classify/1.0.0"

#: FR-2.2's top-50. Not tuned: it is the number in the requirement, and moving it is a change to
#: the specified architecture rather than a knob.
RETRIEVE_K = 50

#: FR-2.2's top-5, enforced by :func:`select` rather than trusted.
MAX_SELECT_CANDIDATES = 5

#: How much clear water the top candidate needs before the resolver commits (FR-2.3). Stated as an
#: assumption, not presented as a measurement: it was chosen so that two classes whose descriptions
#: differ only in a qualifier ("MCB" vs "MCB plug model") abstain rather than coin-flip. A labelled
#: evaluation can move it; until one exists, the conservative direction is the defensible one.
SEPARATION_MARGIN = 0.15

#: The second, non-lexical tie-break: how much better the winning class's *schema fit* must be
#: before a lexical tie is broken on it. See :func:`select`.
SCHEMA_FIT_MARGIN = 0.25

_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    """The embedding half of FR-2.2's retrieval stage. **No implementation is shipped.**"""

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class Reranker(Protocol):
    """The cross-encoder stage. A deterministic default is shipped; a model may replace it."""

    def score(self, query: str, candidates: Sequence[ClassCandidate]) -> Sequence[float]: ...


class Selector(Protocol):
    """The final stage. An LLM adapter implements this -- and only ever sees five candidates."""

    def choose(self, query: str, candidates: Sequence[ClassCandidate]) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ClassCandidate:
    """One class under consideration, with the score of the stage that last touched it."""

    class_id: str
    description: str
    score: float
    stage: str
    group_description: str = ""
    matched_terms: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.class_id} {self.description}"


@dataclass(frozen=True, slots=True)
class ClassResolution:
    """The outcome: one class, or an honest refusal to choose one."""

    query: str
    class_id: str | None
    confidence: float
    margin: float
    retrieved: tuple[ClassCandidate, ...]
    reranked: tuple[ClassCandidate, ...]
    resolver_version: str = RESOLVER_VERSION
    declined_reason: DeclinedReason | None = None
    detail: str = ""
    retrieval_method: str = "lexical"
    """What actually ran. ``lexical`` means the embedding half of FR-2.2 was not in the path, and
    a report that prints this field is telling the reader something a bare accuracy cannot."""

    selector: str = "deterministic-margin"

    @property
    def abstained(self) -> bool:
        return self.class_id is None

    @property
    def top5(self) -> tuple[ClassCandidate, ...]:
        return self.reranked[:MAX_SELECT_CANDIDATES]


@dataclass(frozen=True, slots=True)
class ClassScope:
    """FR-2.4's allow-list: R1 audits low-voltage circuit protection and declines the rest.

    "Class allow-list is configuration, not hardcoded logic" -- so it is a YAML file, it carries
    the reason each class is in or out, and the loader is the only thing that knows its shape.
    """

    name: str
    release: str
    class_ids: tuple[str, ...]
    excluded: dict[str, str] = field(default_factory=dict)
    note: str = ""

    def __contains__(self, class_id: object) -> bool:
        return class_id in self.class_ids

    @property
    def as_set(self) -> frozenset[str]:
        return frozenset(self.class_ids)


def load_scope(path: Path | str | None = None) -> ClassScope:
    """Load the R1 class allow-list."""
    if path is None:
        path = Path(__file__).parent / "config" / "r1-classes.yaml"
    document = yaml.safe_load(Path(path).read_text("utf-8"))
    return ClassScope(
        name=document["name"],
        release=str(document["release"]),
        class_ids=tuple(entry["class_id"] for entry in document.get("classes", ())),
        excluded={
            entry["class_id"]: entry.get("reason", "") for entry in document.get("excluded", ())
        },
        note=str(document.get("note", "")).strip(),
    )


# ------------------------------------------------------------------------------------------------
# Stage 1 -- retrieve
# ------------------------------------------------------------------------------------------------


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _idf(model: EtimModel) -> dict[str, float]:
    """Inverse document frequency over class search text.

    Plain IDF rather than anything cleverer, and it earns its place: without it "circuit" and
    "breaker" -- which appear in hundreds of class names -- outweigh "residual", which appears in a
    handful and is the word that decides between an MCB and an RCCB.
    """
    frequency: dict[str, int] = {}
    for klass in model:
        for token in set(_tokens(klass.search_text)):
            frequency[token] = frequency.get(token, 0) + 1
    total = max(1, len(model))
    return {token: math.log(1 + total / count) for token, count in frequency.items()}


_IDF_CACHE: dict[int, dict[str, float]] = {}


def _idf_for(model: EtimModel) -> dict[str, float]:
    key = id(model)
    if key not in _IDF_CACHE:
        _IDF_CACHE[key] = _idf(model)
    return _IDF_CACHE[key]


def retrieve(
    query: str,
    model: EtimModel,
    *,
    k: int = RETRIEVE_K,
    scope: ClassScope | None = None,
    embedder: Embedder | None = None,
) -> tuple[ClassCandidate, ...]:
    """Stage 1: up to ``k`` candidates by lexical overlap, scope-filtered.

    ``embedder`` is accepted and, when supplied, its results are unioned with the lexical ones --
    the *architecture* takes both halves of FR-2.2. None is shipped, so in every run in this
    repository the retrieval method is lexical and the resolution says so.

    Scope filtering happens here rather than at the end because FR-2.4 makes out-of-scope classes
    out of scope, not merely unlikely: an audit that resolved a lamp to a lamp class and then
    audited it would be operating outside the only region R1 claims to be calibrated in.
    """
    query_tokens = _tokens(query)
    if not query_tokens:
        return ()
    idf = _idf_for(model)
    wanted = scope.as_set if scope else None

    scored: list[ClassCandidate] = []
    for klass in model:
        if wanted is not None and klass.class_id not in wanted:
            continue
        score, matched = _lexical_score(query_tokens, klass, idf)
        if score > 0:
            scored.append(
                ClassCandidate(
                    class_id=klass.class_id,
                    description=klass.description,
                    score=score,
                    stage="retrieve",
                    group_description=klass.group_description,
                    matched_terms=matched,
                )
            )

    if embedder is not None:  # pragma: no cover - no implementation ships with this package
        scored = _union_embedding(query, model, scored, embedder, wanted)

    scored.sort(key=lambda c: (-c.score, c.class_id))
    return tuple(scored[:k])


def _lexical_score(
    query_tokens: Sequence[str], klass: EtimClass, idf: dict[str, float]
) -> tuple[float, tuple[str, ...]]:
    """IDF-weighted overlap, normalised by the query's own weight.

    Normalising by the *query* rather than by the class keeps a long class description from being
    penalised for being descriptive, and keeps the score interpretable: 1.0 means every meaningful
    word of the query appeared in the class.
    """
    class_tokens = set(_tokens(klass.search_text))
    matched = tuple(dict.fromkeys(t for t in query_tokens if t in class_tokens))
    if not matched:
        return 0.0, ()
    hit = sum(idf.get(token, 0.0) for token in matched)
    total = sum(idf.get(token, 0.0) for token in dict.fromkeys(query_tokens)) or 1.0
    return hit / total, matched


def _union_embedding(  # pragma: no cover - interface only
    query: str,
    model: EtimModel,
    lexical: list[ClassCandidate],
    embedder: Embedder,
    wanted: frozenset[str] | None,
) -> list[ClassCandidate]:
    raise NotImplementedError(
        "no embedding retriever ships with errata-audit. FR-2.2's embedding half is an interface "
        "here; wiring one is a change with its own evaluation, not a default."
    )


# ------------------------------------------------------------------------------------------------
# Stage 2 -- rerank
# ------------------------------------------------------------------------------------------------


def rerank(
    query: str,
    candidates: Sequence[ClassCandidate],
    *,
    model: EtimModel,
    k: int = MAX_SELECT_CANDIDATES,
    reranker: Reranker | None = None,
) -> tuple[ClassCandidate, ...]:
    """Stage 2: cut to the top ``k``, with a scorer that reads the whole candidate.

    The shipped scorer is deterministic and combines three observable signals -- retrieval score,
    how much of the *class* the query accounted for (a query matching every word of a short class
    name is a better fit than one matching three words of a long one), and an exact-name bonus. A
    cross-encoder replaces it through the :class:`Reranker` protocol without touching this
    function's contract.
    """
    if not candidates:
        return ()
    if reranker is not None:
        scores = reranker.score(query, candidates)
        rescored = [
            ClassCandidate(
                class_id=c.class_id,
                description=c.description,
                score=float(s),
                stage="rerank",
                group_description=c.group_description,
                matched_terms=c.matched_terms,
            )
            for c, s in zip(candidates, scores, strict=True)
        ]
    else:
        query_tokens = set(_tokens(query))
        rescored = []
        for candidate in candidates:
            klass = model.get(candidate.class_id)
            class_tokens = set(_tokens(klass.description)) if klass else set()
            covered = (
                len(class_tokens & query_tokens) / len(class_tokens) if class_tokens else 0.0
            )
            exact = 1.0 if klass and klass.description.strip().lower() == query.strip().lower() else 0.0
            score = 0.6 * candidate.score + 0.3 * covered + 0.1 * exact
            rescored.append(
                ClassCandidate(
                    class_id=candidate.class_id,
                    description=candidate.description,
                    score=round(score, 6),
                    stage="rerank",
                    group_description=candidate.group_description,
                    matched_terms=candidate.matched_terms,
                )
            )

    rescored.sort(key=lambda c: (-c.score, c.class_id))
    return tuple(rescored[:k])


# ------------------------------------------------------------------------------------------------
# Stage 3 -- select
# ------------------------------------------------------------------------------------------------


def select(
    query: str,
    candidates: Sequence[ClassCandidate],
    *,
    selector: Selector | None = None,
    margin: float = SEPARATION_MARGIN,
    schema_fit: dict[str, float] | None = None,
    fit_margin: float = SCHEMA_FIT_MARGIN,
) -> tuple[str | None, float, str]:
    """Stage 3: choose one class, or decline. Returns ``(class_id, margin, selector_name)``.

    **The cap is enforced here.** FR-2.2 says an LLM is never given more than five candidates; a
    requirement enforced by a comment is a requirement until the first deadline. Handing this
    function six candidates is a programming error and it raises.

    The default selector commits only when the top candidate leads the second by ``margin``. That
    is a deliberate refusal to break ties on noise: two classes the reranker cannot separate are
    two classes whose schemas differ, and picking one at random is how an audit ends up judging a
    residual current device against a circuit breaker's attribute list.

    **When the lexical scores tie, one further piece of evidence is admitted: schema fit.**
    ``schema_fit`` maps class id to the fraction of the record's attributes that class can actually
    express. A description reading "miniature circuit breaker" cannot separate EC000042 from
    EC000271 "MCB plug model" -- neither can any lexical method, because the words are the same --
    but a record carrying a pole count separates them decisively, since EC000271 declares no pole
    feature at all. This is evidence about the product, not a tie-break dressed up as one, and it
    is deliberately *not* the catalog's attribute **values**: only which attributes exist. A
    resolver that read the values would be choosing the schema that makes those values look right.
    """
    if len(candidates) > MAX_SELECT_CANDIDATES:
        raise ValueError(
            f"select() was given {len(candidates)} candidates; FR-2.2 caps the selection stage at "
            f"{MAX_SELECT_CANDIDATES}. Rerank first -- this limit is the architecture, not a "
            "performance guard."
        )
    if not candidates:
        return None, 0.0, "none"

    if selector is not None:
        chosen = selector.choose(query, candidates)
        known = {c.class_id for c in candidates}
        if chosen is not None and chosen not in known:
            # A selector that returns a class it was not shown has hallucinated one. It is not
            # accepted, and the run declines rather than auditing against an invented schema.
            return None, 0.0, type(selector).__name__
        gap = _margin(candidates)
        return chosen, gap, type(selector).__name__

    gap = _margin(candidates)
    if gap >= margin:
        return candidates[0].class_id, gap, "deterministic-margin"

    if schema_fit:
        ranked = sorted(
            ((schema_fit.get(c.class_id, 0.0), -index, c.class_id) for index, c in enumerate(candidates)),
            reverse=True,
        )
        best_fit, _, best_id = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        if best_fit > 0 and best_fit - runner_up >= fit_margin:
            return best_id, gap, "deterministic-schema-fit"

    return None, gap, "deterministic-margin"


def _margin(candidates: Sequence[ClassCandidate]) -> float:
    if len(candidates) == 1:
        return candidates[0].score
    return round(candidates[0].score - candidates[1].score, 6)


# ------------------------------------------------------------------------------------------------
# The three stages, run in order
# ------------------------------------------------------------------------------------------------


def resolve_class(
    query: str,
    model: EtimModel,
    *,
    scope: ClassScope | None = None,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
    selector: Selector | None = None,
    margin: float = SEPARATION_MARGIN,
    attribute_features: Sequence[str] = (),
) -> ClassResolution:
    """Resolve a product description to one ETIM class, or abstain with a reason (FR-2.2, FR-2.3).

    ``query`` is whatever identifies the product in the catalog -- typically manufacturer, MPN and
    description concatenated. It is *not* the catalog's attribute values: class resolution that
    read the values under audit would be choosing the schema that makes those values look correct.

    ``attribute_features`` are the ETIM feature ids of the attributes the record *carries*, used
    only to break a lexical tie on schema fit (see :func:`select`). Which columns a feed sends is a
    fact about the product; what they say is the thing under audit, and only the first is admitted.
    """
    retrieved = retrieve(query, model, scope=scope, embedder=embedder)
    if not retrieved:
        return ClassResolution(
            query=query,
            class_id=None,
            confidence=0.0,
            margin=0.0,
            retrieved=(),
            reranked=(),
            declined_reason=DeclinedReason.CALIBRATION_OUT_OF_DISTRIBUTION,
            detail=(
                "no class in the R1 scope shares a meaningful term with this product description; "
                "the product is outside the region this audit is calibrated for (FR-2.4)"
            ),
        )

    reranked = rerank(query, retrieved, model=model, reranker=reranker)
    class_id, gap, selector_name = select(
        query,
        reranked,
        selector=selector,
        margin=margin,
        schema_fit=_schema_fit(reranked, model, attribute_features),
    )

    if class_id is None:
        return ClassResolution(
            query=query,
            class_id=None,
            confidence=reranked[0].score if reranked else 0.0,
            margin=gap,
            retrieved=retrieved,
            reranked=reranked,
            declined_reason=DeclinedReason.CLASS_UNRESOLVED,
            detail=(
                f"the top candidates are not separable (margin {gap:.3f} < {margin:.3f}): "
                + ", ".join(f"{c.class_id} {c.description!r}" for c in reranked[:3])
                + ". Choosing one would judge every attribute against a schema that may not apply."
            ),
            selector=selector_name,
        )

    chosen = next(c for c in reranked if c.class_id == class_id)
    return ClassResolution(
        query=query,
        class_id=class_id,
        confidence=chosen.score,
        margin=gap,
        retrieved=retrieved,
        reranked=reranked,
        selector=selector_name,
    )


def _schema_fit(
    candidates: Sequence[ClassCandidate], model: EtimModel, features: Sequence[str]
) -> dict[str, float]:
    """Fraction of the record's declared attributes each candidate class can express.

    Empty when the record declares no mapped features, which is the right default: with nothing to
    fit, the resolver falls back to abstaining on a tie rather than to a tie-break computed from an
    empty set, which would divide by zero or -- worse -- score every class 1.0.
    """
    wanted = {f for f in features if f}
    if not wanted:
        return {}
    fit: dict[str, float] = {}
    for candidate in candidates:
        klass = model.get(candidate.class_id)
        if klass is None:
            continue
        declared = {f.feature_id for f in klass.features}
        fit[candidate.class_id] = len(wanted & declared) / len(wanted)
    return fit


def top_k_accuracy(
    resolutions: Iterable[tuple[ClassResolution, str]], *, k: int = 1
) -> tuple[int, int, float]:
    """Top-``k`` accuracy over ``(resolution, gold class id)`` pairs -- FR-2.2's reported metric.

    Returns ``(hits, total, rate)`` rather than a bare rate, because a rate without its denominator
    is the shape of number this repository has already been burned by once.

    **The two k's measure different stages, and the asymmetry is deliberate.**

    * ``k=1`` scores the *selector*: it counts only a committed, correct choice. An abstention is
      not a hit, because a resolver that declines everything has resolved nothing.
    * ``k>1`` scores the *retriever and reranker*: it asks whether the gold class was in the
      shortlist the selector was handed, whether or not the selector then committed. Folding
      abstentions into this would make a selection decision look like a retrieval failure, and the
      whole reason FR-2.2 specifies three stages is so that those two failures are distinguishable.

    Read both next to the abstention count, which the caller reports separately: a resolver can buy
    top-1 accuracy by declining the hard cases, exactly as a comparator can flatter its
    false-positive rate by refusing to commit.
    """
    hits = 0
    total = 0
    for resolution, gold in resolutions:
        total += 1
        if k == 1:
            hits += 1 if resolution.class_id == gold else 0
        else:
            hits += 1 if gold in [c.class_id for c in resolution.reranked[:k]] else 0
    return hits, total, (hits / total if total else 0.0)
