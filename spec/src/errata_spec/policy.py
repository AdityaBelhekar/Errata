"""The resolution-policy DSL (§4.2).

Last-write-wins is how catalogs get poisoned. Every conflict between competing claims runs through
a versioned, human-readable document, and the resolved value records which policy version resolved
it. Two consequences worth the machinery:

* When a customer asks "why does this field say 6 A", the answer is a chain -- this claim, from
  this document revision, selected by policy v3 rule ``prefer_higher_rank`` over that claim. That
  is an audit trail. The alternative is an opinion.
* The policy is a customer-editable artifact, which converts "your tool disagrees with our
  conventions" from a product objection into a configuration change.

The schema is fixed and only the values are editable. Phase 5 was right that fifty customers means
fifty policy dialects; a fixed schema is what keeps that a configuration surface rather than a fork.
"""

from __future__ import annotations

import functools
from importlib import resources
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .taxonomy import DeclinedReason, is_safety_class

__all__ = ["PolicyRule", "ResolutionPolicy", "RuleAction", "builtin_policy", "load_policy"]


class RuleAction(str):
    """Actions a policy rule may take. A closed set: a policy cannot invent behaviour."""

    SELECT_HIGHER_RANK = "select_higher_rank"
    SELECT_MORE_RECENT = "select_more_recent"
    SELECT_MORE_SPECIFIC = "select_more_specific"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    ABSTAIN_AND_SURFACE_BOTH = "abstain_and_surface_both"

    ALL = frozenset(
        {
            "select_higher_rank",
            "select_more_recent",
            "select_more_specific",
            "escalate_to_human",
            "abstain_and_surface_both",
        }
    )


class PolicyRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    action: str
    note: str = ""
    window_days: int | None = None
    attributes: tuple[str, ...] = ()
    applies_to_relations: tuple[str, ...] = ()
    declined_reason: DeclinedReason | None = None

    @model_validator(mode="after")
    def _action_is_known(self) -> PolicyRule:
        if self.action not in RuleAction.ALL:
            raise ValueError(
                f"rule {self.name!r} uses unknown action {self.action!r}; "
                f"allowed: {sorted(RuleAction.ALL)}"
            )
        return self


class ResolutionPolicy(BaseModel):
    """A loaded, validated policy document."""

    model_config = ConfigDict(frozen=True)

    policy_id: str
    version: int
    description: str = ""
    source_rank: dict[str, int] = Field(default_factory=dict)
    rules: tuple[PolicyRule, ...] = ()

    @model_validator(mode="after")
    def _safety_override_is_present_and_escalating(self) -> ResolutionPolicy:
        """A policy without a safety-class escalation rule is rejected at load time.

        §4.2 and ADR-001 make this categorical: no automated resolution of a safety-class
        attribute, at any confidence, with no configuration override. A customer-editable policy
        file is exactly where that promise would be quietly deleted, so the loader refuses to
        accept a document that deletes it.
        """
        safety_rules = [r for r in self.rules if r.attributes]
        escalating = [
            r
            for r in safety_rules
            if r.action in {RuleAction.ESCALATE_TO_HUMAN, RuleAction.ABSTAIN_AND_SURFACE_BOTH}
        ]
        if not escalating:
            raise ValueError(
                f"policy {self.policy_id!r} v{self.version} defines no attribute-scoped "
                "escalation rule. Safety-class attributes must never resolve automatically "
                "(§4.2, ADR-001); a policy that omits the rule is not a valid configuration."
            )
        return self

    @property
    def version_tag(self) -> str:
        return f"{self.policy_id}@v{self.version}"

    def rank_of(self, source_key: str) -> int:
        """Evidentiary rank of a source bucket. Unknown sources rank 0 -- below everything named,
        so an unrecognised feed can never outrank a manufacturer document by accident."""
        return self.source_rank.get(source_key, 0)

    def escalates(self, attribute_key: str) -> bool:
        """True when this attribute must go to a human regardless of confidence."""
        if is_safety_class(attribute_key):
            return True
        key = attribute_key.strip().lower().rsplit(":", 1)[-1]
        for rule in self.rules:
            if rule.action != RuleAction.ESCALATE_TO_HUMAN:
                continue
            if key in {a.lower() for a in rule.attributes}:
                return True
        return False

    def rule(self, name: str) -> PolicyRule | None:
        for candidate in self.rules:
            if candidate.name == name:
                return candidate
        return None


def load_policy(document: dict[str, Any]) -> ResolutionPolicy:
    """Validate a parsed policy document."""
    return ResolutionPolicy(
        policy_id=document["policy_id"],
        version=int(document["version"]),
        description=str(document.get("description", "")).strip(),
        source_rank=dict(document.get("source_rank", {})),
        rules=tuple(PolicyRule(**rule) for rule in document.get("rules", [])),
    )


@functools.cache
def builtin_policy(name: str = "electrical-conservative") -> ResolutionPolicy:
    """Load one of the policies shipped with this package."""
    text = resources.files("errata_spec").joinpath(f"policies/{name}.yaml").read_text("utf-8")
    return load_policy(yaml.safe_load(text))
