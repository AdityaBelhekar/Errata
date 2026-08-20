"""Materials, by ontology lookup.

The rule that keeps this from inventing equivalences: **a purely numeric surface is not a material
unless the caller said the attribute is a material.** ``316`` is a stainless grade in a material
field and the number three hundred and sixteen everywhere else, and the library is not entitled to
guess which field it is looking at.
"""

from __future__ import annotations

import re
from typing import Any

from .. import ontology
from ..model import Kind, MaterialSpec, NormalizedValue, Refusal, RefusalReason

__all__ = ["GRAMMAR_VERSION", "PREFILTER", "parse"]

GRAMMAR_VERSION = "material/1.1.0"
PARSER_NAME = "material"

PREFILTER = re.compile(r"^[\w\s./+\-]{1,48}$")
_HAS_LETTER = re.compile(r"[A-Za-z]")

#: Numeric surfaces distinctive enough to be a material even when nobody said the attribute is one.
#: An EN 10027-2 material number (``1.4401``) and the old chromium/nickel trade ratios (``18/8``)
#: are not plausible readings of anything else in a product attribute. Bare grade numbers such as
#: ``316`` and property classes such as ``8.8`` are deliberately excluded: they are ordinary
#: numbers in most fields, and resolving them needs ``expect=Kind.MATERIAL``.
_NUMERIC_MATERIAL = re.compile(r"^(?:\d\.\d{4}|\d{2}/\d)$")


def parse(text: str, ctx: dict[str, Any] | None = None) -> NormalizedValue | Refusal | None:
    if not PREFILTER.match(text.strip()):
        return None

    expects_material = bool(ctx and ctx.get("expects_material"))
    # A bare number in an unknown field is a number. See the module docstring.
    if (
        not expects_material
        and not _HAS_LETTER.search(text)
        and not _NUMERIC_MATERIAL.match(text.strip())
    ):
        return None

    onto = ontology.load()
    hit = onto.material(text)
    if hit is None:
        if expects_material:
            return Refusal(
                reason=RefusalReason.UNKNOWN_TERM,
                raw=text,
                detail=(
                    f"{text!r} is not in the material ontology "
                    f"({onto.versions.get('materials')}). Adding a group with its standard "
                    "reference is a one-file contribution."
                ),
                attempted=(PARSER_NAME,),
            )
        return None

    group, matched = hit
    caveat = group.caveat_for(matched)
    return NormalizedValue(
        kind=Kind.MATERIAL,
        payload=MaterialSpec(
            group_id=group.id,
            canonical=group.canonical,
            matched_alias=matched.strip(),
            caveat=caveat,
            broader=group.broader,
        ),
        raw=text,
        canonical_text=group.id,
        grammar_version=GRAMMAR_VERSION,
        parser=PARSER_NAME,
        notes=(caveat,) if caveat else (),
    )
