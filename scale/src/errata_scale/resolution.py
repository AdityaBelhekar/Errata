"""FR-8.3 -- the resolution policy, executed.

    "Resolution policy as a versioned declarative document (source rank, recency, specificity,
    tolerance-never-dropped, safety-class escalation, equal-rank abstention). Every resolved value
    records the policy version that resolved it."

``errata_spec.policy`` already loads and validates the document; R1 only ever *consulted* it, to
ask whether an attribute escalates. R2 is the first release where two claims about the same
attribute actually compete -- a datasheet against a feed, one feed row against another -- so R2 is
where the document has to be executed rather than quoted.

The engine is small and the order of its rules is the whole design:

1. **Safety-class escalation first.** Before rank, before recency, before anything. A rule that ran
   second could be reached by a code path that resolved the conflict before asking, and ADR-001's
   promise -- *no automated resolution of a safety-class attribute, at any confidence, with no
   configuration override* -- would then depend on the order of an ``if``.
2. **Rank beats recency, always.** A current manufacturer datasheet outranks a distributor page
   scraped this morning. Chronology is not evidence.
3. **Specificity and tolerance never lose.** ``10 +/-0.2 mm`` supersedes ``10 mm`` and never the
   reverse; a generic term never replaces a specific one.
4. **Equal rank abstains.** Two sources of identical standing disagree, so the policy declines to
   arbitrate and surfaces both. This is the rule that most often gets quietly deleted in favour of
   "just pick the newer one", and it is the one that keeps a wrong value from becoming a resolved
   value with a provenance chain that looks convincing.

Every :class:`Resolution` carries ``policy_version`` and the name of the rule that decided it, so
"why does this field say 6 A" is answerable by reading one object.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from errata_comparator import AttributeSpec, compare_attribute
from errata_spec import DeclinedReason, ResolutionPolicy, RuleAction, builtin_policy
from errata_valuesem import Relation

__all__ = [
    "ClaimCandidate",
    "Resolution",
    "resolve",
]


@dataclass(frozen=True, slots=True)
class ClaimCandidate:
    """One competing statement about an attribute, with everything the policy is allowed to see."""

    value: str
    source_rank_key: str
    """A key of the policy's ``source_rank`` map. An unknown key ranks 0 -- below everything
    named -- so an unrecognised feed can never outrank a manufacturer document by accident."""

    asserted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    claim_id: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Resolution:
    """What the policy decided, and which version of which policy decided it."""

    policy_version: str
    """FR-8.3's acceptance criterion, and the reason this class exists at all."""

    rule: str
    """The name of the rule that fired. ``""`` only when there was nothing to resolve."""

    action: str
    value: str | None
    """``None`` whenever the policy did not resolve -- escalation and equal-rank abstention both
    land here. A resolved value and an unresolved conflict are different types of answer and the
    caller cannot read one as the other."""

    winner: ClaimCandidate | None
    considered: tuple[ClaimCandidate, ...]
    declined_reason: DeclinedReason | None = None
    explanation: str = ""

    @property
    def resolved(self) -> bool:
        return self.value is not None

    @property
    def escalated(self) -> bool:
        return self.action == RuleAction.ESCALATE_TO_HUMAN

    def as_dict(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "rule": self.rule,
            "action": self.action,
            "value": self.value,
            "resolved": self.resolved,
            "declined_reason": self.declined_reason.value if self.declined_reason else None,
            "considered": [
                {
                    "value": candidate.value,
                    "source_rank_key": candidate.source_rank_key,
                    "asserted_at": candidate.asserted_at.isoformat(),
                    "claim_id": candidate.claim_id,
                }
                for candidate in self.considered
            ],
            "explanation": self.explanation,
        }


def resolve(
    candidates: Sequence[ClaimCandidate],
    *,
    attribute: AttributeSpec,
    policy: ResolutionPolicy | None = None,
) -> Resolution:
    """Apply the policy to competing claims about one attribute of one SKU."""
    policy = policy or builtin_policy()
    ordered = tuple(candidates)

    if not ordered:
        return Resolution(
            policy_version=policy.version_tag,
            rule="",
            action="",
            value=None,
            winner=None,
            considered=(),
            explanation="nothing to resolve: no candidate claims were supplied",
        )

    if len(ordered) == 1:
        return Resolution(
            policy_version=policy.version_tag,
            rule="single_candidate",
            action=RuleAction.SELECT_HIGHER_RANK,
            value=ordered[0].value,
            winner=ordered[0],
            considered=ordered,
            explanation=(
                f"one candidate, from {ordered[0].source_rank_key!r}; no conflict to resolve. "
                f"Resolved by {policy.version_tag}."
            ),
        )

    # -- rule 1: safety-class escalation, before anything else can resolve it -------------------
    if policy.escalates(attribute.key) or policy.escalates(attribute.label):
        rule = policy.rule("safety_class_override")
        return Resolution(
            policy_version=policy.version_tag,
            rule=rule.name if rule else "safety_class_override",
            action=RuleAction.ESCALATE_TO_HUMAN,
            value=None,
            winner=None,
            considered=ordered,
            explanation=(
                f"{attribute.key} is a safety-class attribute. {policy.version_tag} never resolves "
                "it automatically, at any confidence and with no configuration override "
                "(ADR-001); acceptance needs a second named adjudicator (FR-8.9)."
            ),
        )

    # If every candidate says the same thing, there is no conflict to resolve, whatever their
    # ranks. Equivalence is decided by the comparator, so 125 g and 0.125 kg are one answer.
    distinct = _distinct(ordered, attribute)
    if len(distinct) == 1:
        best = max(ordered, key=lambda c: (policy.rank_of(c.source_rank_key), c.asserted_at))
        return Resolution(
            policy_version=policy.version_tag,
            rule="no_conflict",
            action=RuleAction.SELECT_HIGHER_RANK,
            value=best.value,
            winner=best,
            considered=ordered,
            explanation=(
                f"{len(ordered)} candidates, all stating the same value. Resolved by "
                f"{policy.version_tag} with no rule needing to arbitrate."
            ),
        )

    # -- rule 2: rank beats everything ------------------------------------------------------------
    ranked = sorted(ordered, key=lambda c: policy.rank_of(c.source_rank_key), reverse=True)
    top_rank = policy.rank_of(ranked[0].source_rank_key)
    top = [c for c in ranked if policy.rank_of(c.source_rank_key) == top_rank]
    if len(top) == 1:
        return Resolution(
            policy_version=policy.version_tag,
            rule="prefer_higher_rank",
            action=RuleAction.SELECT_HIGHER_RANK,
            value=top[0].value,
            winner=top[0],
            considered=ordered,
            explanation=(
                f"{top[0].source_rank_key!r} ranks {top_rank} and outranks every competing source; "
                f"selected by rule prefer_higher_rank of {policy.version_tag}."
            ),
        )

    # -- rules 3: specificity, and a tolerance is never dropped ----------------------------------
    specific = _most_specific(top, attribute)
    if specific is not None:
        winner, rule_name, why = specific
        return Resolution(
            policy_version=policy.version_tag,
            rule=rule_name,
            action=RuleAction.SELECT_MORE_SPECIFIC,
            value=winner.value,
            winner=winner,
            considered=ordered,
            explanation=f"{why} Selected by rule {rule_name} of {policy.version_tag}.",
        )

    # -- rule 4: recency, only inside a rank, and only inside the window --------------------------
    recency = policy.rule("recency_within_rank")
    if recency is not None:
        newest, second = sorted(top, key=lambda c: c.asserted_at, reverse=True)[:2]
        window = recency.window_days
        age_days = abs((newest.asserted_at - second.asserted_at).days)
        if newest.asserted_at != second.asserted_at and (window is None or age_days <= window):
            return Resolution(
                policy_version=policy.version_tag,
                rule=recency.name,
                action=RuleAction.SELECT_MORE_RECENT,
                value=newest.value,
                winner=newest,
                considered=ordered,
                explanation=(
                    f"both candidates rank {top_rank}, so recency applies inside the rank: the "
                    f"newer was asserted {age_days} day(s) later, inside the {window}-day window. "
                    f"Selected by rule {recency.name} of {policy.version_tag}."
                ),
            )

    # -- rule 5: equal rank, and the policy declines to arbitrate --------------------------------
    conflict = policy.rule("equal_rank_conflict")
    return Resolution(
        policy_version=policy.version_tag,
        rule=conflict.name if conflict else "equal_rank_conflict",
        action=RuleAction.ABSTAIN_AND_SURFACE_BOTH,
        value=None,
        winner=None,
        considered=ordered,
        declined_reason=(
            conflict.declined_reason if conflict else DeclinedReason.EQUAL_RANK_SOURCE_CONFLICT
        )
        or DeclinedReason.EQUAL_RANK_SOURCE_CONFLICT,
        explanation=(
            f"{len(top)} sources of identical evidentiary rank ({top_rank}) disagree and no rule "
            f"separates them. {policy.version_tag} declines to arbitrate and surfaces both, rather "
            "than picking one and calling it resolution."
        ),
    )


def _distinct(
    candidates: Sequence[ClaimCandidate], attribute: AttributeSpec
) -> list[ClaimCandidate]:
    """Candidates that genuinely differ, with equivalence decided by the comparator.

    String inequality is not difference: ``125 g`` and ``0.125 kg`` are one statement, and a policy
    engine that treated them as a conflict would escalate a fact nobody disputes.
    """
    distinct: list[ClaimCandidate] = []
    for candidate in candidates:
        if any(
            not compare_attribute(attribute, candidate.value, seen.value).raises_finding
            and not compare_attribute(attribute, candidate.value, seen.value).is_declined
            for seen in distinct
        ):
            continue
        distinct.append(candidate)
    return distinct


def _most_specific(
    candidates: Sequence[ClaimCandidate], attribute: AttributeSpec
) -> tuple[ClaimCandidate, str, str] | None:
    """The candidate every other candidate is a less specific version of, if there is one.

    Requires a *total* win: a candidate that refines one competitor and contradicts another has not
    earned the resolution, and returning it would hide the contradiction behind a specificity rule.
    """
    for candidate in candidates:
        rule_name = ""
        why = ""
        wins_all = True
        for other in candidates:
            if other is candidate:
                continue
            comparison = compare_attribute(attribute, candidate.value, other.value)
            relation = comparison.relation
            if relation is Relation.A_MORE_SPECIFIC:
                rule_name = rule_name or "prefer_more_specific"
                why = why or (
                    f"{candidate.value!r} refines {other.value!r}; a generic value never "
                    "supersedes a specific one."
                )
                continue
            if relation is Relation.B_PRECISION_LOSS:
                rule_name = "tolerance_never_dropped"
                why = (
                    f"{other.value!r} dropped a tolerance that {candidate.value!r} carries; a bare "
                    "value never supersedes a toleranced one."
                )
                continue
            wins_all = False
            break
        if wins_all and rule_name:
            return candidate, rule_name, why
    return None
