"""The attribute map: what R1 audits, and what each attribute is allowed to be.

This is the bridge between three vocabularies that do not otherwise meet -- the customer's column
names, ETIM's feature ids, and ``errata_valuesem``'s value kinds -- and it is deliberately data
(``config/attributes.yaml``) rather than code. FR-3.1 requires extraction to be "constrained to the
resolved class's schema: its attributes, its enums, its units", and a schema expressed as a
dictionary in a Python file is a schema nobody can review.

Two things this module is careful about:

**The unit lives in the header, and stays evidence.** A cell containing ``16`` under a column
headed *Rated current In A* means sixteen amperes, and the audit composes the two -- but it records
the header cell as evidence alongside the value cell, so the reviewer sees where the ampere came
from. A pipeline that folded the unit in silently would produce a value string that appears nowhere
in the document.

**An attribute the value layer cannot read stays in the map.** ``order_code`` has no grammar and
will be refused. It is audited anyway so that the refusal is *visible* (FR-6.2: no silent skips).
Dropping unparseable columns is the cheapest possible way to improve every rate in the report and
it is exactly the move this repository has already been burned by.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from errata_comparator import AttributeSpec
from errata_spec import is_safety_class
from errata_valuesem import Kind

__all__ = [
    "ATTRIBUTES_CONFIG",
    "AttributeMap",
    "AuditAttribute",
    "load_attributes",
]

ATTRIBUTES_CONFIG = Path(__file__).parent / "config" / "attributes.yaml"


@dataclass(frozen=True, slots=True)
class AuditAttribute:
    """One attribute under audit, in all three vocabularies at once."""

    key: str
    label: str
    etim_feature: str
    classes: tuple[str, ...]
    kinds: tuple[Kind, ...]
    column_headers: tuple[re.Pattern[str], ...]
    value_pattern: re.Pattern[str]
    specificity: float
    vocabulary: str = ""
    aliases: tuple[str, ...] = ()
    """Other names this same attribute is published under.

    Not decoration and not convenience. The gold set (``data/gold/annotations``) is a *published,
    hashed* artifact whose attribute keys were frozen before this map existed, and it names the
    packing unit ``packing_unit`` where this map says ``packaging_uom``. One attribute under two
    names is exactly finding N15 -- it is how a single error becomes two error signatures -- and
    the fix for N15 was to give an attribute one identity, resolved through
    ``errata_ecosystem.vocabulary``. Aliases are how a name that cannot be changed (a hash covers
    it) still resolves to that one identity, rather than acquiring a second one by omission.
    """

    unit_from_header: str = ""
    header_unit_pattern: re.Pattern[str] | None = None
    note: str = ""

    @property
    def uri(self) -> str:
        """``etim:EF000227`` where ETIM declares the feature, ``customer:`` where it does not.

        The prefix is not decoration: a claim's ``attribute_uri`` is what makes two catalogs
        comparable, and asserting an ETIM id for an attribute ETIM does not define would make the
        claim look interoperable while being local.
        """
        return f"etim:{self.etim_feature}" if self.etim_feature else f"customer:{self.key}"

    @property
    def is_safety_class(self) -> bool:
        return is_safety_class(self.key) or is_safety_class(self.label)

    def applies_to(self, class_id: str | None) -> bool:
        return class_id is None or not self.classes or class_id in self.classes

    def matches_header(self, header: str) -> bool:
        return any(pattern.search(header) for pattern in self.column_headers)

    def header_states_unit(self, header: str) -> bool:
        """Whether this column header carries the unit ETIM declares for the feature.

        Required before the unit is composed onto a value. A header that does not state it leaves
        the value bare, which the comparator will usually decline -- the correct outcome, since
        the alternative is to assert a unit the document never printed.
        """
        if not self.unit_from_header or self.header_unit_pattern is None:
            return False
        return bool(self.header_unit_pattern.search(header))

    def compose(self, cell_text: str, header: str) -> str:
        """The value as the document states it, with the header's unit attached when it has one."""
        text = cell_text.strip()
        if not text:
            return text
        if self.header_states_unit(header):
            return f"{text} {self.unit_from_header}"
        return text

    def to_spec(self) -> AttributeSpec:
        """The comparator's view of this attribute."""
        return AttributeSpec(
            key=self.key,
            label=self.label,
            kinds=self.kinds,
            vocabulary=self.vocabulary,
            # N15: the comparator used to name the attribute by its key while the redline id was
            # derived from this uri. Passing it through is the whole fix -- one attribute, one
            # identity, in the redline and in the claim alike.
            uri=self.uri,
        )


@dataclass(frozen=True, slots=True)
class AttributeMap:
    version: str
    attributes: tuple[AuditAttribute, ...]

    def __iter__(self):
        return iter(self.attributes)

    def __len__(self) -> int:
        return len(self.attributes)

    def get(self, key: str) -> AuditAttribute | None:
        for attribute in self.attributes:
            if attribute.key == key:
                return attribute
        return None

    def for_class(self, class_id: str | None) -> tuple[AuditAttribute, ...]:
        return tuple(a for a in self.attributes if a.applies_to(class_id))

    @property
    def feature_ids(self) -> tuple[str, ...]:
        return tuple(a.etim_feature for a in self.attributes if a.etim_feature)


def load_attributes(path: Path | str | None = None) -> AttributeMap:
    document = yaml.safe_load(Path(path or ATTRIBUTES_CONFIG).read_text("utf-8"))
    attributes = tuple(_attribute(entry) for entry in document.get("attributes", ()))
    _reject_duplicates(attributes)
    return AttributeMap(version=str(document.get("version", "")), attributes=attributes)


@lru_cache(maxsize=4)
def _cached(path: str) -> AttributeMap:
    return load_attributes(path)


def load_attributes_cached(path: Path | str | None = None) -> AttributeMap:
    return _cached(str(path or ATTRIBUTES_CONFIG))


def _attribute(entry: dict) -> AuditAttribute:
    unit_pattern = entry.get("header_unit_pattern") or ""
    return AuditAttribute(
        key=entry["key"],
        label=entry.get("label", entry["key"]),
        etim_feature=entry.get("etim_feature", "") or "",
        classes=tuple(entry.get("classes", ())),
        kinds=tuple(Kind[name] for name in entry.get("kinds", ())),
        vocabulary=entry.get("vocabulary", "") or "",
        aliases=tuple(entry.get("aliases", ()) or ()),
        column_headers=tuple(re.compile(p) for p in entry.get("column_headers", ())),
        value_pattern=re.compile(entry["value_pattern"]) if entry.get("value_pattern") else re.compile(r"^.+$"),
        specificity=float(entry.get("specificity", 0.5)),
        unit_from_header=entry.get("unit_from_header", "") or "",
        header_unit_pattern=re.compile(unit_pattern) if unit_pattern else None,
        note=str(entry.get("note", "")).strip(),
    )


def _reject_duplicates(attributes: tuple[AuditAttribute, ...]) -> None:
    seen: set[str] = set()
    for attribute in attributes:
        if attribute.key in seen:
            raise ValueError(
                f"attribute {attribute.key!r} is declared twice in the attribute map; the second "
                "declaration would silently win and half the configuration would be inert"
            )
        seen.add(attribute.key)
