"""IEC 60529 ingress protection codes.

``X`` is not zero. ``IP6X`` says the enclosure is dust-tight and says *nothing* about water; ``IP60``
says it was tested against water and offers none. Reading X as 0 turns an unspecified digit into a
failed one, which is a fabricated finding.
"""

from __future__ import annotations

import re
from typing import Any

from ..model import IngressSpec, Kind, NormalizedValue, Refusal, RefusalReason

__all__ = ["GRAMMAR_VERSION", "PREFILTER", "parse"]

GRAMMAR_VERSION = "ingress/1.0.0"
PARSER_NAME = "ingress"

PREFILTER = re.compile(r"\bIP\s*-?\s*[0-9X]", re.IGNORECASE)

_CODE = re.compile(
    r"^IP\s*-?\s*(?P<solids>[0-9X])\s*(?P<liquids>[0-9X])?\s*(?P<suffix>[A-Z]{1,2})?$",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"\s*(?:/|,|\bor\b|\band\b|\+)\s*", re.IGNORECASE)


def parse(text: str, ctx: dict[str, Any] | None = None) -> NormalizedValue | Refusal | None:
    if not PREFILTER.search(text):
        return None

    parts = [p.strip() for p in _SPLIT.split(text.strip()) if p.strip()]
    # "IP66/67" is written as often as "IP66/IP67"; restore the elided prefix.
    parts = [p if p.upper().startswith("IP") else f"IP{p}" for p in parts]

    specs: list[IngressSpec] = []
    for part in parts:
        match = _CODE.match(part)
        if match is None:
            return Refusal(
                reason=RefusalReason.MALFORMED,
                raw=text,
                detail=(
                    f"{part!r} is not a well-formed IEC 60529 code. Expected IP + two digits, "
                    "with X for an untested digit."
                ),
                attempted=(PARSER_NAME,),
            )
        solids = _digit(match.group("solids"))
        liquids = _digit(match.group("liquids"))

        # IEC 60529 Table 1 defines the first characteristic numeral over 0-6 and the second over
        # 0-9. A digit outside its range is not a code this parser may interpret.
        #
        # This is what makes `IP6/7` refuse rather than accuse. The slash split turns it into
        # `IP6` + `IP7`, and `IP7` claims a solids rating of 7 that the standard does not define --
        # so the string is almost certainly a mistyped `IP67`, not a set of two ratings. Without
        # this check the parser silently invented a two-element set, found it shared no key with a
        # well-formed `IP67`, and reported a CONTRADICTION manufactured entirely from a delimiter.
        # FR-4.2: a grammar either parses or refuses, and refusal is the routable signal.
        for numeral, value, ceiling in (("first", solids, 6), ("second", liquids, 9)):
            if value is not None and value > ceiling:
                return Refusal(
                    reason=RefusalReason.MALFORMED,
                    raw=text,
                    detail=(
                        f"{part!r} puts {value} in the {numeral} characteristic numeral, which "
                        f"IEC 60529 defines only over 0-{ceiling}. Refusing rather than reading a "
                        f"rating the standard does not define."
                    ),
                    attempted=(PARSER_NAME,),
                )

        specs.append(
            IngressSpec(
                solids=solids,
                liquids=liquids,
                suffix=(match.group("suffix") or "").upper(),
            )
        )

    notes: list[str] = []
    if len(specs) == 1 and specs[0].liquids is None and not specs[0].suffix:
        notes.append(
            "only the first characteristic numeral was given; the liquids digit is unspecified, "
            "not zero"
        )

    deduped = tuple(dict.fromkeys(specs))
    payload: Any = deduped[0] if len(deduped) == 1 else deduped
    return NormalizedValue(
        kind=Kind.INGRESS,
        payload=payload,
        raw=text,
        canonical_text="/".join(s.designation for s in deduped),
        grammar_version=GRAMMAR_VERSION,
        parser=PARSER_NAME,
        notes=tuple(notes),
    )


def _digit(char: str | None) -> int | None:
    if char is None or char.upper() == "X":
        return None
    return int(char)
