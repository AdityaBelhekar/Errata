"""FR-9.7 -- the ETIM <-> UNSPSC attribute bridge, and the validation that makes it citable.

UNSPSC codes a product across four levels and carries **no attribute layer**. ETIM carries the
attribute layer and lacks UNSPSC's procurement reach. The bridge is the join, and it is published
Apache-2.0 with ODC-By attribution because a bridge nobody else can use is a moat, not a standard.

**The design decision that matters here is what the file is allowed to contain.** A mapping is a
judgement, so the judgements live in ``data/etim-unspsc-bridge.yaml`` with their rationales and
their author. The *attribute layer* is not in that file at all: it is derived from the ETIM release
at load time, so it cannot drift from ETIM, and a feature id that stops existing in ETIM 11.0
produces a load failure rather than a mapping that quietly points at nothing.

Three refusals are load-bearing, and each is tested:

* **A code that does not exist does not load.** Both sides are checked against the hash-registered
  source files. There is no "unknown code" fallback.
* **A title that has changed does not load.** UNSPSC is revised roughly annually and our snapshot
  is dated. If ``39121603`` stops being "Miniature circuit breakers", the mapping it anchors is
  stale by definition, and a stale bridge that still resolves is worse than one that stops.
* **A ``closeMatch`` yields no attribute layer.** "Similar" is not "carry the schema across". The
  caller can ask for the mapping and read the rationale; what they cannot do is get 27 features
  out of a row whose own text says the two descriptors describe different properties.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from errata_audit import EtimModel, load_etim

__all__ = [
    "ATTRIBUTE_BEARING_RELATIONS",
    "BRIDGE_FILE",
    "AttributeBinding",
    "Bridge",
    "BridgeValidationError",
    "Mapping",
    "UnspscCode",
    "load_bridge",
    "load_unspsc",
    "validate_bridge",
]

REPO_ROOT = Path(__file__).resolve().parents[3]
BRIDGE_FILE = Path(__file__).parent / "data" / "etim-unspsc-bridge.yaml"
REFERENCE_MANIFEST = REPO_ROOT / "data" / "reference" / "manifest.json"
DEFAULT_UNSPSC = REPO_ROOT / "var" / "reference" / "unspsc" / "ok-unspsc-codes.csv"
DEFAULT_ETIM = REPO_ROOT / "var" / "reference" / "etim" / "extracted"

#: Relations across which an attribute layer may be carried. ``closeMatch`` is deliberately not
#: here: the bridge's own rationale for the one closeMatch it contains says the two descriptors
#: turn on different properties, and a loader that carried features across it anyway would be
#: contradicting the file it just read.
ATTRIBUTE_BEARING_RELATIONS = frozenset({"skos:exactMatch", "skos:narrowMatch"})

_KNOWN_RELATIONS = frozenset(
    {
        "skos:exactMatch",
        "skos:narrowMatch",
        "skos:broadMatch",
        "skos:closeMatch",
        "skos:relatedMatch",
        "no_match",
        "declined",
    }
)


class BridgeValidationError(ValueError):
    """A mapping that does not hold against the dictionaries it claims to bridge."""


@dataclass(frozen=True, slots=True)
class UnspscCode:
    """One eight-digit commodity code and the four levels above it, as published."""

    commodity: str
    commodity_name: str
    cls: str
    class_name: str
    family: str
    family_name: str
    segment: str
    segment_name: str

    @property
    def path(self) -> str:
        return f"{self.segment} > {self.family} > {self.cls} > {self.commodity}"


@dataclass(frozen=True, slots=True)
class AttributeBinding:
    """One ETIM feature, offered to a UNSPSC code. The thing UNSPSC does not have."""

    feature_id: str
    description: str
    unit: str
    feature_type: str
    from_etim_class: str
    via_relation: str

    @property
    def uri(self) -> str:
        return f"etim:{self.feature_id}"

    def sentence(self) -> str:
        unit = f" [{self.unit}]" if self.unit else ""
        return (
            f"{self.uri} {self.description}{unit} ({self.feature_type}) "
            f"-- from {self.from_etim_class} via {self.via_relation}"
        )


@dataclass(frozen=True, slots=True)
class Mapping:
    """One judged row of the bridge."""

    unspsc: str | None
    unspsc_title: str | None
    etim_class: str | None
    etim_description: str | None
    relation: str
    confidence: str
    rationale: str

    @property
    def carries_attributes(self) -> bool:
        return self.relation in ATTRIBUTE_BEARING_RELATIONS

    @property
    def is_refusal(self) -> bool:
        """``no_match`` and ``declined`` -- the rows that exist so a search is not repeated."""
        return self.relation in {"no_match", "declined"}

    def sentence(self) -> str:
        left = f"{self.unspsc} {self.unspsc_title!r}" if self.unspsc else "(no UNSPSC code)"
        right = (
            f"{self.etim_class} {self.etim_description!r}"
            if self.etim_class
            else "(no ETIM class)"
        )
        return f"{left}  --{self.relation}-->  {right}"


@dataclass(frozen=True, slots=True)
class Bridge:
    """The loaded, validated bridge."""

    version: str
    released: str
    licence: str
    decided_by: str
    attribution: dict[str, str]
    mappings: tuple[Mapping, ...]
    etim_release: str
    unspsc_sha256: str
    etim_source: str

    def for_unspsc(self, code: str) -> tuple[Mapping, ...]:
        return tuple(m for m in self.mappings if m.unspsc == code)

    def for_etim(self, class_id: str) -> tuple[Mapping, ...]:
        return tuple(m for m in self.mappings if m.etim_class == class_id)

    @property
    def refusals(self) -> tuple[Mapping, ...]:
        return tuple(m for m in self.mappings if m.is_refusal)

    def attributes_for(self, code: str, model: EtimModel) -> tuple[AttributeBinding, ...]:
        """The attribute layer this bridge gives an eight-digit UNSPSC code.

        Derived from ETIM here and now -- never read from the bridge file, which contains no
        feature ids at all. Ordered by feature id so two runs produce the same list, and
        de-duplicated across mappings: an MCB and an MCB plug model share most of their schema and
        a caller wants one attribute list, not two overlapping ones.
        """
        seen: dict[str, AttributeBinding] = {}
        for mapping in self.for_unspsc(code):
            if not mapping.carries_attributes or not mapping.etim_class:
                continue
            etim_class = model.get(mapping.etim_class)
            if etim_class is None:  # pragma: no cover - validate_bridge refuses this at load
                raise BridgeValidationError(
                    f"{mapping.etim_class} is not in the loaded ETIM release"
                )
            for feature in etim_class.features:
                seen.setdefault(
                    feature.feature_id,
                    AttributeBinding(
                        feature_id=feature.feature_id,
                        description=feature.description,
                        unit=feature.unit,
                        feature_type=feature.type_name,
                        from_etim_class=mapping.etim_class,
                        via_relation=mapping.relation,
                    ),
                )
        return tuple(sorted(seen.values(), key=lambda b: b.feature_id))

    def as_dict(self, model: EtimModel | None = None) -> dict:
        payload: dict = {
            "version": self.version,
            "released": self.released,
            "licence": self.licence,
            "attribution": self.attribution,
            "decided_by": self.decided_by,
            "sources": {
                "etim_release": self.etim_release,
                "etim_source": self.etim_source,
                "unspsc_sha256": self.unspsc_sha256,
            },
            "mappings": [
                {
                    "unspsc": m.unspsc,
                    "unspsc_title": m.unspsc_title,
                    "etim_class": m.etim_class,
                    "etim_description": m.etim_description,
                    "relation": m.relation,
                    "confidence": m.confidence,
                    "carries_attributes": m.carries_attributes,
                }
                for m in self.mappings
            ],
        }
        if model is not None:
            codes = sorted({m.unspsc for m in self.mappings if m.unspsc})
            payload["attribute_layer"] = {
                code: [b.uri for b in self.attributes_for(code, model)] for code in codes
            }
        return payload


def load_unspsc(path: Path | str | None = None) -> dict[str, UnspscCode]:
    """The UNSPSC codeset, keyed by eight-digit commodity code.

    Not committed to this repository -- ``scripts/fetch_reference_data.sh`` reconstructs it from
    the URL and hash in ``data/reference/manifest.json``, which is the FR-9.5 pattern applied to
    somebody else's code list rather than to our own gold set.
    """
    csv_path = Path(path) if path is not None else DEFAULT_UNSPSC
    if not csv_path.exists():
        raise FileNotFoundError(
            f"no UNSPSC codeset at {csv_path}. Run scripts/fetch_reference_data.sh -- the codeset "
            "is fetched and hash-verified, never committed."
        )
    codes: dict[str, UnspscCode] = {}
    # TRAP, recorded here and in the manifest's loader_notes: the published file is **cp1252**,
    # not UTF-8. 93 of its bytes are non-ASCII -- an acute e in a orchid cultivar, a non-breaking
    # space in "Optical transmitter", an acute e in "cliche" -- and utf-8 raises on the first of
    # them, 5,779 bytes in. Guessing the encoding per line, or decoding with errors="replace",
    # would silently corrupt three commodity titles; the titles are what the bridge validates
    # against, so a corrupted one is a mapping that stops loading for no visible reason.
    with csv_path.open(encoding="cp1252", newline="") as handle:
        for row in csv.DictReader(handle):
            commodity = (row.get("Commodity") or "").strip()
            if not commodity:
                continue
            codes[commodity] = UnspscCode(
                commodity=commodity,
                commodity_name=(row.get("Commodity Name") or "").strip(),
                cls=(row.get("Class") or "").strip(),
                class_name=(row.get("Class Name") or "").strip(),
                family=(row.get("Family") or "").strip(),
                family_name=(row.get("Family Name") or "").strip(),
                segment=(row.get("Segment") or "").strip(),
                segment_name=(row.get("Segment Name") or "").strip(),
            )
    return codes


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_sha256(artifact_id: str) -> str | None:
    if not REFERENCE_MANIFEST.exists():  # pragma: no cover - the manifest is committed
        return None
    doc = json.loads(REFERENCE_MANIFEST.read_text(encoding="utf-8"))
    for artifact in doc.get("artifacts", []):
        if artifact.get("id") == artifact_id:
            return artifact.get("sha256")
    return None


def validate_bridge(
    raw: dict,
    *,
    codes: dict[str, UnspscCode],
    model: EtimModel,
) -> tuple[Mapping, ...]:
    """Every row, checked against both dictionaries. Raises on the first thing that does not hold.

    Collecting all the failures and reporting them together was the other option and it is the
    wrong one here: a bridge is a published artifact, and a partially-valid published artifact is
    the thing this function exists to make impossible.
    """
    mappings: list[Mapping] = []
    for index, row in enumerate(raw.get("mappings") or ()):
        where = f"mapping {index}"
        relation = str(row.get("relation") or "")
        if relation not in _KNOWN_RELATIONS:
            raise BridgeValidationError(
                f"{where}: {relation!r} is not a known relation. "
                f"Use one of {sorted(_KNOWN_RELATIONS)}"
            )

        rationale = str(row.get("rationale") or "").strip()
        if not rationale:
            raise BridgeValidationError(
                f"{where}: no rationale. A mapping without its reasoning is a number without a "
                "citation -- ground rule 1 applies to judgements as well as to measurements."
            )

        unspsc = row.get("unspsc")
        title = row.get("unspsc_title")
        if unspsc is not None:
            code = codes.get(str(unspsc))
            if code is None:
                raise BridgeValidationError(
                    f"{where}: UNSPSC {unspsc} is not in the codeset that was loaded"
                )
            if title is not None and code.commodity_name != title:
                raise BridgeValidationError(
                    f"{where}: UNSPSC {unspsc} is titled {code.commodity_name!r} in the loaded "
                    f"codeset, but this mapping was judged against {title!r}. UNSPSC has been "
                    "revised under the mapping: re-judge it, do not re-type the title."
                )

        etim_class = row.get("etim_class")
        if etim_class is not None:
            resolved = model.get(str(etim_class))
            if resolved is None:
                raise BridgeValidationError(
                    f"{where}: ETIM class {etim_class} is not in the loaded release"
                )
            described = row.get("etim_description")
            if described is not None and resolved.description != described:
                raise BridgeValidationError(
                    f"{where}: ETIM {etim_class} is {resolved.description!r} in the loaded "
                    f"release, not {described!r}"
                )
            if relation in ATTRIBUTE_BEARING_RELATIONS and not resolved.features:
                raise BridgeValidationError(
                    f"{where}: {etim_class} carries no features in this release, so there is no "
                    "attribute layer to bridge. A mapping that promises attributes and delivers "
                    "none is worse than no mapping."
                )

        if relation == "no_match" and unspsc is not None:
            raise BridgeValidationError(
                f"{where}: no_match names a UNSPSC code. A no_match records that nothing was "
                "found on one side; naming both is a match with a discouraging label."
            )
        if relation not in {"no_match", "declined"} and (unspsc is None or etim_class is None):
            raise BridgeValidationError(
                f"{where}: {relation} needs both sides. Use no_match or declined for one-sided rows."
            )

        mappings.append(
            Mapping(
                unspsc=str(unspsc) if unspsc is not None else None,
                unspsc_title=str(title) if title is not None else None,
                etim_class=str(etim_class) if etim_class is not None else None,
                etim_description=(
                    str(row["etim_description"]) if row.get("etim_description") else None
                ),
                relation=relation,
                confidence=str(row.get("confidence") or "unstated"),
                rationale=rationale,
            )
        )

    if not mappings:
        raise BridgeValidationError("a bridge with no mappings is not a bridge")
    return tuple(mappings)


def load_bridge(
    path: Path | str | None = None,
    *,
    unspsc: Path | str | None = None,
    etim: Path | str | None = None,
    model: EtimModel | None = None,
) -> tuple[Bridge, EtimModel]:
    """Load, validate and return the bridge together with the ETIM model it was validated against.

    Returning the model rather than hiding it is deliberate: the attribute layer is derived from
    it, and a caller that got the bridge without the release it holds for could print an attribute
    list next to the wrong release number.
    """
    bridge_path = Path(path) if path is not None else BRIDGE_FILE
    raw = yaml.safe_load(bridge_path.read_text(encoding="utf-8"))

    codes = load_unspsc(unspsc)
    etim_dir = Path(etim) if etim is not None else DEFAULT_ETIM
    release = str((raw.get("sources") or {}).get("etim", {}).get("release") or "10.0")
    if model is None:
        model = load_etim(etim_dir, release=release)

    mappings = validate_bridge(raw, codes=codes, model=model)

    unspsc_path = Path(unspsc) if unspsc is not None else DEFAULT_UNSPSC
    return (
        Bridge(
            version=str(raw.get("version") or ""),
            released=str(raw.get("released") or ""),
            licence=str(raw.get("licence") or ""),
            decided_by=str(raw.get("decided_by") or "").strip(),
            attribution={k: str(v).strip() for k, v in (raw.get("attribution") or {}).items()},
            mappings=mappings,
            etim_release=release,
            unspsc_sha256=_sha256(unspsc_path),
            etim_source=str(etim_dir),
        ),
        model,
    )


@lru_cache(maxsize=1)
def expected_unspsc_sha256() -> str | None:
    """The hash the manifest records for the codeset, so a caller can say whether it matches."""
    return _manifest_sha256("unspsc-codeset-ok-open-data")
