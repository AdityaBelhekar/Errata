"""FR-8.3 -- the resolution policy, executed.

    "Every resolved value records the policy version that resolved it."

That criterion is checked on every path through the engine, including the paths that resolve
nothing: an escalation and an equal-rank abstention are answers too, and an answer that cannot say
which policy produced it is an opinion.

The rule *order* is the other thing under test. Safety-class escalation has to be unreachable-past,
rank has to beat recency, and a tolerance has to survive. Each of those is a rule somebody will
eventually propose relaxing under deadline pressure, so each has a test naming what it protects.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from errata_comparator import AttributeSpec
from errata_scale import ClaimCandidate, resolve
from errata_spec import DeclinedReason, RuleAction, builtin_policy
from errata_valuesem import Kind

NOW = datetime(2026, 8, 20, tzinfo=UTC)

WEIGHT = AttributeSpec(key="weight_kg", label="Weight", kinds=(Kind.QUANTITY,))
CURRENT = AttributeSpec(key="rated_current", label="Rated current", kinds=(Kind.QUANTITY,))
LENGTH = AttributeSpec(key="body_length", label="Body length", kinds=(Kind.QUANTITY,))


def _candidate(value: str, rank: str, *, days: int = 0) -> ClaimCandidate:
    return ClaimCandidate(
        value=value, source_rank_key=rank, asserted_at=NOW + timedelta(days=days)
    )


def test_every_resolution_records_the_policy_version():
    policy = builtin_policy()
    cases = [
        [],
        [_candidate("0.125 kg", "manufacturer_datasheet_current")],
        [
            _candidate("0.125 kg", "manufacturer_datasheet_current"),
            _candidate("0.9 kg", "distributor_feed"),
        ],
        [
            _candidate("0.125 kg", "distributor_feed"),
            _candidate("0.9 kg", "distributor_feed"),
        ],
    ]
    for candidates in cases:
        result = resolve(candidates, attribute=WEIGHT, policy=policy)
        assert result.policy_version == policy.version_tag == "electrical-conservative@v3"


def test_a_safety_class_attribute_never_resolves_automatically():
    """ADR-001: no automated resolution, at any confidence, with no configuration override. The
    rule runs before rank, so no code path can resolve the conflict before asking."""
    result = resolve(
        [
            _candidate("16 A", "manufacturer_datasheet_current"),
            _candidate("61 A", "scraped_product_page"),
        ],
        attribute=CURRENT,
    )
    assert result.resolved is False
    assert result.escalated is True
    assert result.value is None
    assert result.action == RuleAction.ESCALATE_TO_HUMAN
    assert "second named adjudicator" in result.explanation


def test_rank_beats_recency_always():
    result = resolve(
        [
            _candidate("0.125 kg", "manufacturer_datasheet_current", days=-400),
            _candidate("0.9 kg", "scraped_product_page", days=0),
        ],
        attribute=WEIGHT,
    )
    assert result.value == "0.125 kg"
    assert result.rule == "prefer_higher_rank"


def test_an_unknown_source_ranks_below_everything_named():
    result = resolve(
        [
            _candidate("0.125 kg", "manufacturer_datasheet_current"),
            _candidate("0.9 kg", "somebody's spreadsheet"),
        ],
        attribute=WEIGHT,
    )
    assert result.value == "0.125 kg"


def test_recency_applies_only_inside_a_rank():
    result = resolve(
        [
            _candidate("0.125 kg", "distributor_feed", days=-10),
            _candidate("0.9 kg", "distributor_feed", days=0),
        ],
        attribute=WEIGHT,
    )
    assert result.value == "0.9 kg"
    assert result.rule == "recency_within_rank"
    assert result.action == RuleAction.SELECT_MORE_RECENT


def test_equal_rank_and_equal_time_abstains_rather_than_arbitrating():
    result = resolve(
        [
            _candidate("0.125 kg", "distributor_feed"),
            _candidate("0.9 kg", "distributor_feed"),
        ],
        attribute=WEIGHT,
    )
    assert result.resolved is False
    assert result.declined_reason is DeclinedReason.EQUAL_RANK_SOURCE_CONFLICT
    assert result.action == RuleAction.ABSTAIN_AND_SURFACE_BOTH
    assert len(result.considered) == 2


def test_a_tolerance_is_never_dropped():
    result = resolve(
        [
            _candidate("10 +/-0.2 mm", "distributor_feed"),
            _candidate("10 mm", "distributor_feed"),
        ],
        attribute=LENGTH,
    )
    assert result.value == "10 +/-0.2 mm"
    assert result.rule == "tolerance_never_dropped"


def test_candidates_that_say_the_same_thing_are_not_a_conflict():
    """125 g and 0.125 kg are one statement. A policy engine that escalated this would escalate a
    fact nobody disputes -- and at catalog scale that is thousands of escalations."""
    result = resolve(
        [
            _candidate("0.125 kg", "distributor_feed"),
            _candidate("125 g", "distributor_feed"),
        ],
        attribute=WEIGHT,
    )
    assert result.resolved is True
    assert result.rule == "no_conflict"


def test_one_candidate_resolves_to_itself_and_says_so():
    result = resolve([_candidate("0.125 kg", "distributor_feed")], attribute=WEIGHT)
    assert result.value == "0.125 kg"
    assert result.rule == "single_candidate"


def test_no_candidates_resolves_nothing_and_does_not_pretend_otherwise():
    result = resolve([], attribute=WEIGHT)
    assert result.value is None
    assert result.rule == ""
    assert "nothing to resolve" in result.explanation


def test_a_resolution_serialises_with_everything_it_considered():
    result = resolve(
        [
            _candidate("0.125 kg", "manufacturer_datasheet_current"),
            _candidate("0.9 kg", "distributor_feed"),
        ],
        attribute=WEIGHT,
    )
    payload = result.as_dict()
    assert payload["policy_version"] == "electrical-conservative@v3"
    assert payload["resolved"] is True
    assert len(payload["considered"]) == 2
    assert payload["explanation"]
