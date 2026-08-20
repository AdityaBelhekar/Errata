"""FR-2.2 / FR-2.3 / FR-2.4 -- three stages, a hard cap, and an abstention that means it.

The requirement's acceptance criterion is unusually structural: *"Architecture is literally three
stages; an LLM is never given more than 5 candidates."* So the tests are structural too. The cap is
not tested by counting candidates in a log; it is tested by handing :func:`select` six of them and
asserting that it raises.

The abstention tests matter more than the accuracy tests. A resolver that picks a class on a tie
produces a run in which every attribute is judged against a schema that may not apply -- and every
resulting redline is confident, evidenced, and about the wrong product.
"""

from __future__ import annotations

import pytest
from conftest import etim_archive, requires_etim

from errata_audit.classify import (
    MAX_SELECT_CANDIDATES,
    RETRIEVE_K,
    ClassCandidate,
    load_scope,
    rerank,
    resolve_class,
    retrieve,
    select,
    top_k_accuracy,
)
from errata_audit.etim import load_etim

pytestmark = requires_etim


@pytest.fixture(scope="module")
def model():
    return load_etim(etim_archive(), release="10.0", class_ids=load_scope().as_set)


@pytest.fixture(scope="module")
def scope():
    return load_scope()


# ------------------------------------------------------------------------------------------------
# The shape of the architecture
# ------------------------------------------------------------------------------------------------


def test_retrieval_returns_at_most_the_specified_k(model, scope) -> None:
    assert len(retrieve("circuit breaker", model, scope=scope)) <= RETRIEVE_K


def test_rerank_cuts_to_five(model, scope) -> None:
    retrieved = retrieve("miniature circuit breaker", model, scope=scope)
    assert len(rerank("miniature circuit breaker", retrieved, model=model)) <= MAX_SELECT_CANDIDATES


def test_select_refuses_more_than_five_candidates() -> None:
    """FR-2.2's cap, enforced by a raise rather than by a comment. A future LLM selector cannot be
    handed fifty candidates by accident, because the function it must be called through refuses."""
    candidates = [
        ClassCandidate(class_id=f"EC00000{i}", description="x", score=1.0, stage="rerank")
        for i in range(6)
    ]
    with pytest.raises(ValueError, match="caps the selection stage"):
        select("anything", candidates)


def test_the_three_stages_are_all_recorded_in_the_result(model, scope) -> None:
    resolution = resolve_class("residual current circuit breaker 30 mA", model, scope=scope)
    assert resolution.retrieved
    assert resolution.reranked
    assert resolution.selector
    assert resolution.retrieval_method == "lexical"


def test_the_retrieval_method_is_reported_honestly(model, scope) -> None:
    """FR-2.2 specifies lexical **and** embedding retrieval. No embedder ships, so every resolution
    says ``lexical`` -- which tells a reader something a bare accuracy never would."""
    assert resolve_class("MCB 16 A", model, scope=scope).retrieval_method == "lexical"


# ------------------------------------------------------------------------------------------------
# Abstention -- FR-2.3
# ------------------------------------------------------------------------------------------------


def test_an_unseparable_pair_abstains_rather_than_guessing(model, scope) -> None:
    resolution = resolve_class("circuit breaker", model, scope=scope)
    assert resolution.abstained
    assert resolution.declined_reason is not None
    assert "not separable" in resolution.detail


def test_an_out_of_scope_product_declines_with_a_reason(model, scope) -> None:
    resolution = resolve_class("LED floodlight 50 W IP65", model, scope=scope)
    assert resolution.abstained
    assert resolution.declined_reason.value == "calibration_out_of_distribution"


def test_a_clearly_named_class_resolves(model, scope) -> None:
    resolution = resolve_class("selective main line circuit breaker 63 A", model, scope=scope)
    assert resolution.class_id == "EC001047"
    assert resolution.margin > 0


def test_the_schema_fit_tie_break_uses_which_attributes_exist_not_what_they_say(
    model, scope
) -> None:
    """A record carrying a pole count separates an MCB from an MCB plug model, because the plug
    model declares no pole feature at all. That is evidence about the product. The *values* are
    never consulted -- a resolver that read them would pick the schema that makes them look right.
    """
    query = "ABB miniature circuit breaker"
    without = resolve_class(query, model, scope=scope)
    with_features = resolve_class(
        query, model, scope=scope, attribute_features=("EF000227", "EF008618")
    )
    assert without.abstained
    assert with_features.class_id == "EC000042"
    assert with_features.selector == "deterministic-schema-fit"


def test_the_tie_break_still_abstains_when_the_fit_is_equally_good(model, scope) -> None:
    """Rated current alone is declared by every in-scope class, so it separates nothing."""
    resolution = resolve_class(
        "circuit breaker", model, scope=scope, attribute_features=("EF000227",)
    )
    assert resolution.abstained


def test_a_selector_that_invents_a_class_is_not_believed(model, scope) -> None:
    class Hallucinating:
        def choose(self, query, candidates):
            return "EC999999"

    retrieved = retrieve("miniature circuit breaker", model, scope=scope)
    reranked = rerank("miniature circuit breaker", retrieved, model=model)
    chosen, _margin, name = select("miniature circuit breaker", reranked, selector=Hallucinating())
    assert chosen is None
    assert name == "Hallucinating"


# ------------------------------------------------------------------------------------------------
# Scope -- FR-2.4
# ------------------------------------------------------------------------------------------------


def test_scope_filters_retrieval_not_just_the_final_answer(model, scope) -> None:
    ids = {candidate.class_id for candidate in retrieve("fuse base", model, scope=scope)}
    assert ids <= scope.as_set


def test_the_allow_list_is_loaded_from_configuration(scope) -> None:
    assert scope.name == "r1-low-voltage-circuit-protection"
    assert scope.class_ids == ("EC000042", "EC000003", "EC000271", "EC001047")
    assert scope.release == "10.0"


def test_excluded_classes_carry_their_reason(scope) -> None:
    assert "EC000905" in scope.excluded
    assert "RCBO" in scope.excluded["EC000905"]


# ------------------------------------------------------------------------------------------------
# Reporting -- FR-2.2's "top-1 and top-5 accuracy reported on a labelled set"
# ------------------------------------------------------------------------------------------------


def test_top1_does_not_count_an_abstention_as_a_hit(model, scope) -> None:
    resolution = resolve_class("circuit breaker", model, scope=scope)
    hits, total, rate = top_k_accuracy([(resolution, "EC000042")], k=1)
    assert (hits, total, rate) == (0, 1, 0.0)


def test_top5_scores_the_shortlist_even_when_the_selector_held(model, scope) -> None:
    """The two k's measure different stages. Folding abstentions into top-5 would make a selection
    decision look like a retrieval failure, which is precisely the confusion three stages exist to
    prevent."""
    resolution = resolve_class("circuit breaker", model, scope=scope)
    hits, _total, _rate = top_k_accuracy([(resolution, "EC000042")], k=5)
    assert hits == 1


def test_the_labelled_set_ships_with_its_own_caveat() -> None:
    """The rates are single-labelled by the implementer. FR-0.1 identified that conflict of
    interest for the equivalence suite; it applies here unchanged, and the file has to say so."""
    from pathlib import Path

    import yaml

    import errata_audit

    document = yaml.safe_load(
        (Path(errata_audit.__file__).parent / "demo" / "class-labels.yaml").read_text("utf-8")
    )
    assert "labelled_by" in document and document["labelled_by"].strip()
    assert "caveat" in document and document["caveat"].strip()
    assert any(case.get("class_id") is None for case in document["cases"])
