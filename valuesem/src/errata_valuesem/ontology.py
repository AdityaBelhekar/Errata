"""Stage 3 of the pipeline: the ontology.

Materials, controlled vocabularies, generic subsuming terms and packaging frames, loaded from the
YAML files in ``ontology/``. Pure data, deliberately: the equivalence set is finite, knowable and
testable, and asking a model to re-derive a known fact per call is paying rent on a lookup table
(§3.4).

Alias collisions across vocabularies are detected at load time and reported rather than silently
resolved. ``AC`` is a current type and an RCD type and a utilisation-category prefix; which one it
means depends on the attribute being audited, and if the caller did not say, the answer is that we
do not know.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from decimal import Decimal
from importlib import resources
from typing import Any

import yaml

__all__ = [
    "Generic",
    "MaterialGroup",
    "Ontology",
    "Term",
    "UomDef",
    "Vocabulary",
    "alias_key",
    "load",
]

GRAMMAR_VERSION = "ontology/1.1.0"

_ALIAS_STRIP = re.compile(r"[\s\-_]+")


def alias_key(text: str) -> str:
    """Fold a surface form into its lookup key.

    Spaces, hyphens and underscores are removed; case is folded. Dots are *kept*, because
    ``1.4401`` and ``14401`` are different designations and collapsing them would invent an
    equivalence.
    """
    return _ALIAS_STRIP.sub("", (text or "").strip().lower())


@dataclass(frozen=True, slots=True)
class MaterialGroup:
    id: str
    canonical: str
    aliases: tuple[str, ...]
    broader: tuple[str, ...]
    source: str
    caveats: dict[str, str] = field(default_factory=dict)
    facet: str = ""
    """Which AXIS of a material this group describes.

    A fastener is simultaneously a base grade, a mechanical property class, and a surface finish.
    Those are orthogonal facets, not competing claims: `class 8.8` and `hot-dip galvanised` are
    both true of one bolt, so comparing them answers a question nobody asked. Left empty the group
    compares as before; two groups with DIFFERENT non-empty facets are not comparable at all and
    the comparator declines instead of accusing.
    """

    def caveat_for(self, matched_alias: str) -> str:
        key = alias_key(matched_alias)
        for alias, text in self.caveats.items():
            if alias_key(alias) == key:
                return " ".join(text.split())
        return ""


@dataclass(frozen=True, slots=True)
class Term:
    id: str
    vocabulary: str
    canonical: str
    aliases: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True, slots=True)
class Vocabulary:
    id: str
    label: str
    source: str
    etim_feature: str
    terms: tuple[Term, ...]


@dataclass(frozen=True, slots=True)
class Generic:
    id: str
    canonical: str
    aliases: tuple[str, ...]
    subsumes_kinds: tuple[str, ...] = ()
    subsumes_groups: tuple[str, ...] = ()
    subsumes_terms: tuple[str, ...] = ()
    restrict_thread_system: str = ""


@dataclass(frozen=True, slots=True)
class UomDef:
    code: str
    canonical: str
    default_quantity: Decimal | None
    bulk: bool
    aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PackagingPattern:
    regex: re.Pattern[str]
    note: str


@dataclass(slots=True)
class Ontology:
    """The loaded ontology. Built once, cached, never mutated."""

    versions: dict[str, str]

    materials_by_id: dict[str, MaterialGroup]
    materials_by_alias: dict[str, MaterialGroup]

    vocabularies: dict[str, Vocabulary]
    terms_by_id: dict[str, Term]
    terms_by_vocab_alias: dict[str, dict[str, Term]]
    terms_by_global_alias: dict[str, tuple[Term, ...]]

    generics_by_alias: dict[str, Generic]

    uoms_by_code: dict[str, UomDef]
    uoms_by_alias: dict[str, UomDef]
    interchangeable_containers: tuple[frozenset[str], ...]
    packaging_patterns: tuple[PackagingPattern, ...]

    booleans: dict[str, bool]

    collisions: dict[str, tuple[str, ...]]
    """Aliases claimed by more than one vocabulary. Not an error -- a fact the caller must resolve
    by naming the vocabulary. Exposed so a contributor can see what they created."""

    # -- material queries ----------------------------------------------------------------------

    def material(self, surface: str) -> tuple[MaterialGroup, str] | None:
        key = alias_key(surface)
        group = self.materials_by_alias.get(key)
        if group is None:
            return None
        return group, surface

    def material_is_narrower(self, narrow: MaterialGroup, broad: MaterialGroup) -> bool:
        """True when ``narrow`` is a member of ``broad``'s family. ``316L`` within ``316``."""
        return broad.id in narrow.broader

    def group_matches_prefix(self, group: MaterialGroup, prefix: str) -> bool:
        if group.id == prefix or group.id.startswith(prefix + "/"):
            return True
        return any(b == prefix or b.startswith(prefix + "/") for b in group.broader)

    # -- term queries --------------------------------------------------------------------------

    def term(self, surface: str, vocabulary: str | None = None) -> Term | tuple[Term, ...] | None:
        """Resolve a surface form to a term.

        Returns a single :class:`Term` on an unambiguous hit, a tuple when the alias is claimed by
        several vocabularies and none was named, or ``None`` when unknown.
        """
        key = alias_key(surface)
        if vocabulary is not None:
            return self.terms_by_vocab_alias.get(vocabulary, {}).get(key)
        hits = self.terms_by_global_alias.get(key)
        if not hits:
            return None
        if len(hits) == 1:
            return hits[0]
        return hits

    def generic(self, surface: str) -> Generic | None:
        return self.generics_by_alias.get(alias_key(surface))

    def boolean(self, surface: str) -> bool | None:
        return self.booleans.get(alias_key(surface))

    def uom(self, surface: str) -> UomDef | None:
        return self.uoms_by_alias.get(alias_key(surface))

    def containers_interchangeable(self, a: str, b: str) -> bool:
        if a == b:
            return True
        return any({a, b} <= group for group in self.interchangeable_containers)


def _read(name: str) -> dict[str, Any]:
    text = resources.files("errata_valuesem").joinpath(f"ontology/{name}").read_text("utf-8")
    return yaml.safe_load(text) or {}


@functools.cache
def load() -> Ontology:
    """Load and index the ontology. Cached for the life of the process."""
    materials_doc = _read("materials.yaml")
    terms_doc = _read("terms.yaml")
    packaging_doc = _read("packaging.yaml")

    materials_by_id: dict[str, MaterialGroup] = {}
    materials_by_alias: dict[str, MaterialGroup] = {}
    for raw in materials_doc.get("groups", []):
        group = MaterialGroup(
            id=raw["id"],
            canonical=raw["canonical"],
            aliases=tuple(str(a) for a in raw.get("aliases", [])),
            broader=tuple(str(b) for b in raw.get("broader", [])),
            source=str(raw.get("source", "")),
            caveats={str(k): str(v) for k, v in (raw.get("caveats") or {}).items()},
            facet=str(raw.get("facet", "")),
        )
        if group.id in materials_by_id:
            raise ValueError(f"duplicate material group id: {group.id}")
        materials_by_id[group.id] = group
        for alias in group.aliases:
            key = alias_key(alias)
            existing = materials_by_alias.get(key)
            if existing is not None and existing.id != group.id:
                raise ValueError(
                    f"material alias {alias!r} claimed by both {existing.id} and {group.id}. "
                    "An alias that names two materials is a false-equivalence generator; "
                    "disambiguate it or drop it."
                )
            materials_by_alias[key] = group

    vocabularies: dict[str, Vocabulary] = {}
    terms_by_id: dict[str, Term] = {}
    terms_by_vocab_alias: dict[str, dict[str, Term]] = {}
    global_alias: dict[str, list[Term]] = {}

    for raw_vocab in terms_doc.get("vocabularies", []):
        vocab_id = raw_vocab["id"]
        terms: list[Term] = []
        by_alias: dict[str, Term] = {}
        for raw_term in raw_vocab.get("terms", []):
            term = Term(
                id=raw_term["id"],
                vocabulary=vocab_id,
                canonical=raw_term["canonical"],
                aliases=tuple(str(a) for a in raw_term.get("aliases", [])),
                note=" ".join(str(raw_term.get("note", "")).split()),
            )
            terms.append(term)
            terms_by_id[term.id] = term
            for alias in term.aliases:
                key = alias_key(alias)
                if key in by_alias and by_alias[key].id != term.id:
                    raise ValueError(
                        f"alias {alias!r} maps to two terms inside vocabulary {vocab_id}: "
                        f"{by_alias[key].id} and {term.id}"
                    )
                by_alias[key] = term
                claimants = global_alias.setdefault(key, [])
                # One term can reach the same key by several spellings ("2P" and "2 P"). Only a
                # *different* term makes an alias ambiguous.
                if all(existing.id != term.id for existing in claimants):
                    claimants.append(term)
        vocabularies[vocab_id] = Vocabulary(
            id=vocab_id,
            label=str(raw_vocab.get("label", vocab_id)),
            source=str(raw_vocab.get("source", "")),
            etim_feature=str(raw_vocab.get("etim_feature", "")),
            terms=tuple(terms),
        )
        terms_by_vocab_alias[vocab_id] = by_alias

    collisions = {
        key: tuple(t.id for t in hits) for key, hits in global_alias.items() if len(hits) > 1
    }

    generics_by_alias: dict[str, Generic] = {}
    for raw in terms_doc.get("generics", []):
        generic = Generic(
            id=raw["id"],
            canonical=raw["canonical"],
            aliases=tuple(str(a) for a in raw.get("aliases", [])),
            subsumes_kinds=tuple(str(k) for k in raw.get("subsumes_kinds", [])),
            subsumes_groups=tuple(str(g) for g in raw.get("subsumes_groups", [])),
            subsumes_terms=tuple(str(t) for t in raw.get("subsumes_terms", [])),
            restrict_thread_system=str(raw.get("restrict_thread_system", "")),
        )
        for alias in generic.aliases:
            generics_by_alias.setdefault(alias_key(alias), generic)

    booleans: dict[str, bool] = {}
    for label, aliases in (terms_doc.get("booleans") or {}).items():
        value = str(label).lower() == "true"
        for alias in aliases:
            booleans[alias_key(str(alias))] = value

    uoms_by_code: dict[str, UomDef] = {}
    uoms_by_alias: dict[str, UomDef] = {}
    for raw in packaging_doc.get("uoms", []):
        default_qty = raw.get("default_quantity")
        uom = UomDef(
            code=raw["code"],
            canonical=raw["canonical"],
            default_quantity=None if default_qty is None else Decimal(str(default_qty)),
            bulk=bool(raw.get("bulk", False)),
            aliases=tuple(str(a) for a in raw.get("aliases", [])),
        )
        uoms_by_code[uom.code] = uom
        uoms_by_alias.setdefault(alias_key(uom.code), uom)
        for alias in uom.aliases:
            uoms_by_alias.setdefault(alias_key(alias), uom)

    interchangeable = tuple(
        frozenset(str(code) for code in group)
        for group in packaging_doc.get("interchangeable_containers", [])
    )
    patterns = tuple(
        PackagingPattern(
            regex=re.compile(str(raw["regex"]), re.IGNORECASE),
            note=str(raw.get("note", "")),
        )
        for raw in packaging_doc.get("patterns", [])
    )

    return Ontology(
        versions={
            "materials": str(materials_doc.get("version", "")),
            "terms": str(terms_doc.get("version", "")),
            "packaging": str(packaging_doc.get("version", "")),
            "loader": GRAMMAR_VERSION,
        },
        materials_by_id=materials_by_id,
        materials_by_alias=materials_by_alias,
        vocabularies=vocabularies,
        terms_by_id=terms_by_id,
        terms_by_vocab_alias=terms_by_vocab_alias,
        terms_by_global_alias={k: tuple(v) for k, v in global_alias.items()},
        generics_by_alias=generics_by_alias,
        uoms_by_code=uoms_by_code,
        uoms_by_alias=uoms_by_alias,
        interchangeable_containers=interchangeable,
        packaging_patterns=patterns,
        booleans=booleans,
        collisions=collisions,
    )
