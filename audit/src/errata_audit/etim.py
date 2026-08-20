"""FR-2.1 -- the ETIM dictionary loader, release-parameterised, with attribution recorded.

    "ETIM 10.0 loads; loader is release-parameterised so 11.0 (1 Dec 2026) loads without code
     change."

ETIM is the one piece of reference data in this project that is genuinely open: verified on
2026-08-19 as a direct download, no login, under the **Open Data Commons Attribution Licence**.
ODC-By requires attribution, so the licence and the release travel with the loaded model
(:attr:`EtimModel.attribution`) and are printed by any report that uses it. Attribution that lives
only in a README is attribution that is lost the first time a number is copied into a slide.

**Release-parameterised means the release is data.** The class ids, the file names and the encoding
are read from the distribution; the only thing the code knows is the shape of the CSVs. ETIM 11.0
is due 2026-12-01 (verified, PRD §schedule) and is expected to load by pointing at the new archive.
That expectation is stated, not proven -- nobody here has seen 11.0 -- so the loader records which
release it actually read rather than assuming.

**The two traps in this distribution, both discovered by reading the bytes** (recorded in
``data/reference/manifest.json``):

* the CSVs are **UTF-16-LE with no BOM**. ``encoding="utf-16"`` raises outright, and
  ``encoding="utf-8"`` yields a first column full of NUL characters that then fails to match
  anything, silently, forever.
* the delimiter is ``;``, not ``,``.

Neither is exotic and both are the kind of thing a loader gets wrong once and then carries as a
mysterious empty result, which is why they are asserted by a test rather than remembered.
"""

from __future__ import annotations

import csv
import functools
import io
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ETIM_ATTRIBUTION",
    "ETIM_ENCODING",
    "EtimClass",
    "EtimFeature",
    "EtimModel",
    "EtimValue",
    "load_etim",
]

#: Read off the bytes, not recalled. See the module docstring.
ETIM_ENCODING = "utf-16-le"
ETIM_DELIMITER = ";"

#: ODC-By requires attribution wherever the data is used. Carried in the model so it reaches the
#: report rather than stopping at the README.
ETIM_ATTRIBUTION = (
    "Classification data: ETIM International, Open Data Commons Attribution Licence (ODC-By). "
    "https://www.etim-international.com/"
)

_FILES = {
    "classes": "ETIMARTCLASS.csv",
    "groups": "ETIMARTGROUP.csv",
    "features": "ETIMFEATURE.csv",
    "values": "ETIMVALUE.csv",
    "units": "ETIMUNIT.csv",
    "class_features": "ETIMARTCLASSFEATUREMAP.csv",
    "class_feature_values": "ETIMARTCLASSFEATUREVALUEMAP.csv",
    "synonyms": "ETIMARTCLASSSYNONYMMAP.csv",
}

#: ETIM's ``FEATURETYPE`` column. One letter, and the letter decides how a value may be compared:
#: an ``A`` (alphanumeric) feature has a closed value list and anything outside it is rejected
#: before it can become a claim (FR-3.1); an ``N`` carries a unit; an ``L`` is a boolean.
FEATURE_TYPES = {"A": "alphanumeric", "N": "numeric", "L": "logical", "R": "range"}


@dataclass(frozen=True, slots=True)
class EtimValue:
    """One permitted value of one feature, in one class."""

    value_id: str
    description: str
    sort: int = 0


@dataclass(frozen=True, slots=True)
class EtimFeature:
    """One feature of one class -- ETIM's word for an attribute."""

    feature_id: str
    description: str
    feature_type: str
    unit_id: str = ""
    unit: str = ""
    sort: int = 0
    values: tuple[EtimValue, ...] = ()

    @property
    def type_name(self) -> str:
        return FEATURE_TYPES.get(self.feature_type, self.feature_type or "unknown")

    @property
    def is_closed_list(self) -> bool:
        """True when the class declares an explicit value list for this feature.

        FR-3.1: "output outside the class's declared value list is rejected before it becomes a
        claim". This property is what makes that check possible, and its absence is why an
        unconstrained numeric feature has to be bounded some other way.
        """
        return bool(self.values)

    @property
    def uri(self) -> str:
        return f"etim:{self.feature_id}"


@dataclass(frozen=True, slots=True)
class EtimClass:
    """One ETIM class: the schema an audited product is judged against."""

    class_id: str
    group_id: str
    description: str
    version: str = ""
    group_description: str = ""
    synonyms: tuple[str, ...] = ()
    features: tuple[EtimFeature, ...] = ()

    def uri(self, release: str) -> str:
        """``etim:EC000042 @ 10.0`` -- the release is part of the identity (``Claim.class_uri``).

        A class id without its release is ambiguous the moment the model is revised, and the
        product's whole proposition is that a stored claim stays reconstructible.
        """
        return f"etim:{self.class_id} @ {release}"

    def feature(self, feature_id: str) -> EtimFeature | None:
        for candidate in self.features:
            if candidate.feature_id == feature_id:
                return candidate
        return None

    @property
    def search_text(self) -> str:
        """Everything a lexical retriever may match on: description plus published synonyms.

        Synonyms are ETIM's own (``ETIMARTCLASSSYNONYMMAP``), not ours. A synonym list we invented
        would make class resolution agree with our own vocabulary rather than with the standard's.
        """
        return " ".join((self.description, *self.synonyms))


@dataclass(frozen=True, slots=True)
class EtimModel:
    """A loaded ETIM release."""

    release: str
    source: str
    classes: dict[str, EtimClass] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    attribution: str = ETIM_ATTRIBUTION

    def __len__(self) -> int:
        return len(self.classes)

    def get(self, class_id: str) -> EtimClass | None:
        return self.classes.get(class_id)

    def __contains__(self, class_id: object) -> bool:
        return class_id in self.classes

    def __iter__(self) -> Iterator[EtimClass]:
        return iter(self.classes.values())


class _Archive:
    """Reads the release's CSVs, whether they arrive as a zip or an unpacked directory.

    Both shapes exist in the wild -- ``scripts/fetch_reference_data.sh`` keeps the zip, a
    workstation usually has it extracted -- and which one an operator has is not a fact worth
    making them think about.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._zip = zipfile.ZipFile(path) if path.is_file() else None
        if self._zip is None and not path.is_dir():
            raise FileNotFoundError(f"{path} is neither a zip nor a directory")

    def read_rows(self, name: str) -> Iterator[dict[str, str]]:
        if self._zip is not None:
            members = {Path(n).name: n for n in self._zip.namelist()}
            member = members.get(name)
            if member is None:
                raise KeyError(f"{name} is not in {self.path.name}")
            payload = self._zip.read(member)
        else:
            candidate = self.path / name
            if not candidate.exists():
                raise KeyError(f"{name} is not in {self.path}")
            payload = candidate.read_bytes()

        text = payload.decode(ETIM_ENCODING).lstrip("﻿")
        yield from csv.DictReader(io.StringIO(text, newline=""), delimiter=ETIM_DELIMITER)

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()


def load_etim(
    path: Path | str,
    *,
    release: str,
    class_ids: frozenset[str] | set[str] | None = None,
) -> EtimModel:
    """Load an ETIM release from its published archive.

    ``class_ids`` restricts the *feature* load to a set of classes. Every class is always loaded --
    class resolution has to be able to retrieve a class in order to reject it, and a retriever that
    can only see the classes it was told about would report perfect accuracy by construction. What
    the restriction avoids is parsing 4.9MB of feature mappings for 5,640 classes when R1 audits
    four (FR-2.4).

    ``release`` is supplied by the caller rather than sniffed from the archive. The distribution
    carries per-class version numbers but no single release label, and inferring "10.0" from a
    filename is exactly the kind of confident guess ground rule 1 forbids.
    """
    archive = _Archive(Path(path))
    try:
        groups = {
            row["ARTGROUPID"]: row.get("GROUPDESC", "")
            for row in archive.read_rows(_FILES["groups"])
        }
        units = {
            row["UNITOFMEASID"]: row.get("UNITDESC", "")
            for row in archive.read_rows(_FILES["units"])
        }
        feature_names = {
            row["FEATUREID"]: row.get("FEATUREDESC", "")
            for row in archive.read_rows(_FILES["features"])
        }
        value_names = {
            row["VALUEID"]: row.get("VALUEDESC", "") for row in archive.read_rows(_FILES["values"])
        }

        raw_classes = list(archive.read_rows(_FILES["classes"]))
        wanted = set(class_ids) if class_ids else {row["ARTCLASSID"] for row in raw_classes}

        synonyms: dict[str, list[str]] = {}
        for row in archive.read_rows(_FILES["synonyms"]):
            synonyms.setdefault(row["ARTCLASSID"], []).append(row.get("CLASSSYNONYM", ""))

        # ARTCLASSFEATURENR is the join key between the feature map and the value map. Keeping it
        # rather than the (class, feature) pair matters: the same feature appears in hundreds of
        # classes with different value lists, and joining on the feature id would give a class the
        # union of every other class's permitted values.
        class_features: dict[str, list[dict[str, str]]] = {}
        by_feature_nr: dict[str, dict[str, str]] = {}
        for row in archive.read_rows(_FILES["class_features"]):
            if row["ARTCLASSID"] not in wanted:
                continue
            class_features.setdefault(row["ARTCLASSID"], []).append(row)
            by_feature_nr[row["ARTCLASSFEATURENR"]] = row

        feature_values: dict[str, list[EtimValue]] = {}
        if by_feature_nr:
            for row in archive.read_rows(_FILES["class_feature_values"]):
                key = row["ARTCLASSFEATURENR"]
                if key not in by_feature_nr:
                    continue
                feature_values.setdefault(key, []).append(
                    EtimValue(
                        value_id=row["VALUEID"],
                        description=value_names.get(row["VALUEID"], ""),
                        sort=_as_int(row.get("SORTNR")),
                    )
                )

        classes: dict[str, EtimClass] = {}
        for row in raw_classes:
            class_id = row["ARTCLASSID"]
            features = tuple(
                EtimFeature(
                    feature_id=mapping["FEATUREID"],
                    description=feature_names.get(mapping["FEATUREID"], ""),
                    feature_type=mapping.get("FEATURETYPE", ""),
                    unit_id=mapping.get("UNITOFMEASID", "") or "",
                    unit=units.get(mapping.get("UNITOFMEASID", "") or "", ""),
                    sort=_as_int(mapping.get("SORTNR")),
                    values=tuple(
                        sorted(
                            feature_values.get(mapping["ARTCLASSFEATURENR"], ()),
                            key=lambda v: (v.sort, v.value_id),
                        )
                    ),
                )
                for mapping in sorted(
                    class_features.get(class_id, ()), key=lambda m: _as_int(m.get("SORTNR"))
                )
            )
            classes[class_id] = EtimClass(
                class_id=class_id,
                group_id=row.get("ARTGROUPID", ""),
                description=row.get("ARTCLASSDESC", ""),
                version=row.get("ARTCLASSVERSION", ""),
                group_description=groups.get(row.get("ARTGROUPID", ""), ""),
                synonyms=tuple(s for s in synonyms.get(class_id, ()) if s),
                features=features,
            )

        return EtimModel(
            release=release, source=str(Path(path)), classes=classes, units=units
        )
    finally:
        archive.close()


@functools.lru_cache(maxsize=4)
def _cached(path: str, release: str, class_ids: frozenset[str] | None) -> EtimModel:
    return load_etim(Path(path), release=release, class_ids=class_ids)


def load_etim_cached(
    path: Path | str, *, release: str, class_ids: frozenset[str] | None = None
) -> EtimModel:
    """Memoised :func:`load_etim`. Loading the full model takes seconds; a CLI run wants it once."""
    return _cached(str(path), release, class_ids)


def _as_int(value: str | None) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0
