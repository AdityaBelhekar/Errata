"""Packaging frames.

Highest-severity family in the system. ``Each`` where the manufacturer ships ``Box of 10`` prices
the line at a tenth of cost and returns a punchout requisition the buyer's ERP accepts without
complaint. Phase 1's finding on getting this wrong once: "you will never get another meeting."
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .. import ontology
from ..model import Kind, NormalizedValue, PackagingSpec, Refusal, RefusalReason

__all__ = ["GRAMMAR_VERSION", "PREFILTER", "parse"]

GRAMMAR_VERSION = "packaging/1.0.0"
PARSER_NAME = "packaging"

PREFILTER = re.compile(r"^[\w\s./():\-]{1,40}$")
_WORD = re.compile(r"[A-Za-z]{1,12}")


def parse(text: str, ctx: dict[str, Any] | None = None) -> NormalizedValue | Refusal | None:
    stripped = re.sub(r"\s+", " ", text.strip())
    if not PREFILTER.match(stripped):
        return None

    onto = ontology.load()
    # A packaging value must name a container or a piece word. Without one there is nothing here
    # for this parser and the value belongs to another family.
    if not any(onto.uom(word) is not None for word in _WORD.findall(stripped)):
        return None

    for pattern in onto.packaging_patterns:
        match = pattern.regex.match(stripped)
        if match is None:
            continue
        groups = match.groupdict()
        uom = onto.uom(groups.get("uom") or "")
        if uom is None:
            continue

        quantity: Decimal | None
        raw_qty = groups.get("qty")
        if raw_qty is not None:
            try:
                quantity = Decimal(raw_qty)
            except InvalidOperation:
                continue
        else:
            quantity = uom.default_quantity

        if quantity is not None and quantity <= 0:
            return Refusal(
                reason=RefusalReason.MALFORMED,
                raw=text,
                detail=f"pack quantity {raw_qty!r} is not positive",
                attempted=(PARSER_NAME,),
            )

        notes: list[str] = []
        if quantity is None:
            notes.append(
                f"{uom.canonical!r} names a container but not how many are in it; the pack "
                "quantity is unspecified, not one"
            )
        if (
            uom.default_quantity is not None
            and raw_qty is not None
            and Decimal(raw_qty) != uom.default_quantity
        ):
            notes.append(
                f"stated quantity {raw_qty} overrides the {uom.canonical} default of "
                f"{uom.default_quantity}"
            )

        spec = PackagingSpec(
            uom_code=uom.code,
            uom_canonical=uom.canonical,
            quantity=quantity,
            is_bulk_container=uom.bulk,
        )
        return NormalizedValue(
            kind=Kind.PACKAGING,
            payload=spec,
            raw=text,
            canonical_text=(
                f"{uom.code}"
                if quantity is None
                else f"{uom.code}/{format(quantity.normalize(), 'f')}"
            ),
            grammar_version=GRAMMAR_VERSION,
            parser=PARSER_NAME,
            notes=tuple(notes),
        )

    return None
