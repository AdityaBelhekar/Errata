"""NFR-1 -- the canonical payload a re-run must reproduce byte for byte.

The requirement: *"Identical inputs + identical component versions -> identical claims."* The
acceptance criterion: *"Re-run produces byte-identical claim payloads excluding timestamps and
ids."*

Determinism was asserted in prose in several modules -- ``layout.py`` stamps a version "whenever
anything changes that could move a char offset", ``derive.py`` calls itself "deterministic and
parameterless", ``valuesem`` has a test forbidding network and model calls -- and **nothing ran an
audit twice and diffed the output**. Each of those is a claim about a component. NFR-1 is a claim
about the whole pipeline, and a pipeline is exactly where non-determinism hides: a dict iteration
order, a set that reaches a serialiser, a float formatted differently on a second pass.

**The exclusions are named, not inferred.** It would be easy to elide anything that looks like a
UUID or a timestamp, and that would be a check which weakens itself every time somebody adds a
field. :data:`VOLATILE_FIELDS` lists them, so widening the exclusion is a visible edit in a diff
rather than a pattern quietly matching more. :func:`canonical_payload` also reports how much it
elided, and :func:`assert_reproducible` refuses to pass on a payload that is mostly holes -- a
determinism test that excluded everything would pass forever and mean nothing.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "VOLATILE_FIELDS",
    "CanonicalPayload",
    "NotReproducible",
    "assert_reproducible",
    "canonical_payload",
    "payload_digest",
]

#: Fields excluded from the comparison, and why each one is legitimately excluded.
#:
#: * ``claim_id`` / ``abstention_id`` / ``redline_id`` -- freshly minted UUID4 per emission. NFR-1
#:   says "excluding ... ids" precisely because a claim's identity is not part of its content.
#: * ``asserted_at`` / ``decided_at`` / ``recorded_at`` / ``observed_at`` -- wall clock.
#: * ``supersedes`` -- points at another claim by its (excluded) id.
#:
#: Nothing else. In particular ``doc_revision_sha256``, ``char_span``, ``bbox`` and every version
#: stamp stay IN: they are the fields a re-run is supposed to reproduce, and an exclusion list that
#: grew to cover them would turn this check into a formality.
VOLATILE_FIELDS = frozenset(
    {
        "claim_id",
        "abstention_id",
        "redline_id",
        "batch_id",
        "asserted_at",
        "decided_at",
        "recorded_at",
        "observed_at",
        "generated_at",
        "supersedes",
    }
)


class NotReproducible(AssertionError):
    """Two runs of the same pipeline over the same bytes produced different payloads."""


@dataclass(frozen=True, slots=True)
class CanonicalPayload:
    text: str
    elided: int
    """How many volatile fields were removed. Reported so that a vacuous comparison is visible."""

    retained: int
    """How many scalar fields survived. This is the size of what is actually being asserted."""

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def _normalise(value: Any, counters: dict[str, int]) -> Any:
    """Everything reduced to JSON-serialisable primitives, in a stable order.

    A set encountered here is **counted, and then made to fail** in :func:`canonical_payload`. It
    is sorted on the way through only so that the failure message can show what was in it; the
    payload is never returned. Quietly ordering a set to make a determinism test pass is fixing
    the thermometer -- a set has no defined iteration order across processes, so its presence is
    the very defect NFR-1 exists to find.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value, key=str):
            if str(key) in VOLATILE_FIELDS:
                counters["elided"] += 1
                continue
            out[str(key)] = _normalise(value[key], counters)
        return out

    if isinstance(value, (set, frozenset)):
        counters["sets"] += 1
        return sorted((_normalise(v, counters) for v in value), key=json.dumps)

    if isinstance(value, (list, tuple)):
        return [_normalise(v, counters) for v in value]

    if isinstance(value, (str, int, float, bool)) or value is None:
        counters["retained"] += 1
        return value

    # Pydantic models. Dumping by mode="json" rather than str() keeps the nested structure
    # comparable field by field, which is what lets VOLATILE_FIELDS reach inside it.
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return _normalise({"__type__": type(value).__name__, **dump(mode="json")}, counters)

    # Dataclasses -- SkuAudit, AttributeOutcome, Derivation and most of R1's own result types.
    # Handled explicitly rather than falling through to str(), which was the bug this comment
    # exists because of: a dataclass reduced to its repr became ONE opaque string, so every
    # nested claim_id and asserted_at inside it sailed past the exclusion list and two runs
    # "differed" on exactly the fields NFR-1 says to ignore. A canonicaliser that cannot see
    # inside the object it is canonicalising is not one.
    #
    # `dataclasses.fields` rather than `asdict`, because `asdict` deep-copies and converts nested
    # dataclasses itself while leaving pydantic models untouched -- two traversals with two sets
    # of rules, and the pydantic half would go back to being a repr.
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}
        return _normalise({"__type__": type(value).__name__, **fields}, counters)

    if isinstance(value, enum.Enum):
        counters["retained"] += 1
        return str(value.value)

    # UUIDs, datetimes, Paths and anything else. Reached only for values NOT excluded by name, so
    # a UUID arriving here is one under a field this module has not been told is an id -- which
    # will show up as a difference between two runs, loudly, which is the correct outcome.
    counters["retained"] += 1
    return str(value)


def canonical_payload(obj: Any) -> CanonicalPayload:
    """The comparable form of a claim, an abstention, a redline, or any collection of them."""
    counters = {"elided": 0, "retained": 0, "sets": 0}
    normalised = _normalise(obj, counters)

    if counters["sets"]:
        raise NotReproducible(
            f"{counters['sets']} set(s) reached the payload. A set has no defined iteration order "
            "across processes, so a payload containing one is not reproducible -- sorting it here "
            "would hide exactly the defect NFR-1 exists to find. Use a tuple or a sorted list at "
            "the source."
        )

    return CanonicalPayload(
        text=json.dumps(normalised, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
        elided=counters["elided"],
        retained=counters["retained"],
    )


def payload_digest(obj: Any) -> str:
    return canonical_payload(obj).digest


#: Below this many retained scalar fields, a "the two runs matched" result is not evidence of
#: anything. Set from the shape of a single R1 audit -- one SKU's outcomes carry hundreds of
#: scalars -- so a payload that collapses to a handful means the pipeline returned almost nothing
#: and the comparison succeeded by being empty.
MINIMUM_RETAINED = 50


def assert_reproducible(first: Any, second: Any, *, what: str = "payload") -> CanonicalPayload:
    """Assert two runs produced the same payload, and that the payload was worth comparing.

    Returns the canonical payload so a caller can record its digest -- a receipt that names what
    was compared is more useful than a boolean.
    """
    left = canonical_payload(first)
    right = canonical_payload(second)

    if left.retained < MINIMUM_RETAINED:
        raise NotReproducible(
            f"{what}: only {left.retained} field(s) survived canonicalisation, below the "
            f"{MINIMUM_RETAINED} this check requires to mean anything. Two runs that agree about "
            "almost nothing agree trivially; this is a failure of the test, not a pass of the "
            "pipeline."
        )

    if left.text != right.text:
        raise NotReproducible(
            f"{what}: two runs over identical bytes produced different payloads.\n"
            f"  first  sha256 {left.digest}\n"
            f"  second sha256 {right.digest}\n"
            f"  {_first_difference(left.text, right.text)}\n"
            "NFR-1: identical inputs and identical component versions must produce identical "
            "claims. A stored char_span is an offset into a layer, so a pipeline that is not "
            "reproducible has silently invalidated every claim it ever made."
        )
    return left


def _first_difference(left: str, right: str) -> str:
    """Where they diverge, with enough either side to see it. A digest mismatch alone is useless."""
    for index, (a, b) in enumerate(zip(left, right, strict=False)):
        if a != b:
            lo = max(0, index - 120)
            return (
                f"first difference at character {index}:\n"
                f"    first  ...{left[lo : index + 120]}...\n"
                f"    second ...{right[lo : index + 120]}..."
            )
    return f"one payload is a prefix of the other ({len(left)} vs {len(right)} characters)"


def digests(objs: Iterable[Any]) -> tuple[str, ...]:
    return tuple(payload_digest(o) for o in objs)
