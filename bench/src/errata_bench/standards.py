"""Reference data read out of published standards, for use as an independent second opinion.

Everything here was read from a source that exists outside this project, and each constant records
which one. This is the shared home for that data so there is exactly one copy: the citation-audit
tests and the corroboration harness both import from here rather than each carrying their own
transcription, because two transcriptions eventually disagree and the disagreement is silent.

Sources, and how each was obtained:

* **ISO 261:1998 Table 2** -- read from the standard itself, via the free publisher preview that
  carries the complete table. Registered in `data/reference/manifest.json` with its sha256. This is
  the transcription that found three wrong choice-column claims and two false "largest pitch"
  claims in `threads_hard.yaml` during the P1 citation audit.
* **ETIM 10.0** -- the free ODC-By release, loaded at runtime from `var/reference/etim/`. Its value
  lists are curated by ETIM's technical committees.

Nothing here is derived from `errata_valuesem`, and nothing here may import it. The whole point is
to be a source the comparator has never seen.
"""

from __future__ import annotations

import csv
import io
import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

__all__ = [
    "ETIM_EXTRACTED",
    "ISO_261_CHOICE_COLUMN",
    "ISO_261_COARSE_PITCH_MM",
    "ISO_261_LARGEST_COARSE_PITCH_MM",
    "ISO_261_LARGEST_PITCH_MM",
    "etim_available",
    "etim_ip_codes",
    "iso_261_coarse_pitch",
]

# ================================================================================================
# ISO 261:1998 Table 2 -- read from the standard, 2026-08-19
# ================================================================================================

#: Coarse pitch in millimetres, by nominal diameter. Table 2 lists **no coarse pitch above M68**,
#: which is why this table simply stops there rather than extrapolating.
ISO_261_COARSE_PITCH_MM: dict[str, str] = {
    "1": "0.25", "1.1": "0.25", "1.2": "0.25", "1.4": "0.3",
    "1.6": "0.35", "1.8": "0.35", "2": "0.4", "2.2": "0.45", "2.5": "0.45",
    "3": "0.5", "3.5": "0.6", "4": "0.7", "4.5": "0.75", "5": "0.8",
    "6": "1", "7": "1", "8": "1.25", "9": "1.25", "10": "1.5", "11": "1.5",
    "12": "1.75", "14": "2", "16": "2", "18": "2.5", "20": "2.5", "22": "2.5",
    "24": "3", "27": "3", "30": "3.5", "33": "3.5", "36": "4", "39": "4",
    "42": "4.5", "45": "4.5", "48": "5", "52": "5", "56": "5.5", "60": "5.5",
    "64": "6", "68": "6",
}

#: Which of Table 2's three preference columns a diameter sits in. Only the diameters the suite
#: discusses by column are recorded -- the ones whose miscategorisation the audit found.
ISO_261_CHOICE_COLUMN: dict[str, int] = {"M9": 3, "M11": 2, "M4.5": 2, "M2.2": 2, "M68": 2}

#: The largest pitch anywhere in Table 2 -- at M125 and M130. **Not 6 mm**: 6 is the largest
#: *coarse* pitch, and the repository asserted the wrong one of these in three separate places.
ISO_261_LARGEST_PITCH_MM = 8
ISO_261_LARGEST_COARSE_PITCH_MM = 6


def iso_261_coarse_pitch(diameter: Decimal | str) -> Decimal | None:
    """The ISO 261 coarse pitch for a nominal diameter, or None if it is not a listed size.

    None rather than an interpolation, for the same reason the shipped parser does it: a diameter
    the standard does not list has no coarse pitch, and inventing one would be the whole failure
    mode this project exists to catch.
    """
    key = str(Decimal(str(diameter)).normalize())
    if key.startswith("0E"):  # Decimal normalises 0 oddly; not a thread size either way
        return None
    pitch = ISO_261_COARSE_PITCH_MM.get(key)
    if pitch is None:
        pitch = ISO_261_COARSE_PITCH_MM.get(str(diameter))
    return Decimal(pitch) if pitch is not None else None


# ================================================================================================
# ETIM 10.0 -- loaded at runtime from the fetched release
# ================================================================================================

ETIM_EXTRACTED = Path("var/reference/etim/extracted")

#: The ETIM CSVs are UTF-16-LE **with no byte-order mark**, so `encoding="utf-16"` raises
#: outright, and the delimiter is `;`. Both facts cost time to rediscover; both are recorded in
#: `data/reference/manifest.json` as loader notes.
_ETIM_ENCODING = "utf-16-le"
_ETIM_DELIMITER = ";"

_IP_CODE = re.compile(r"IP[0-9X]{2}", re.IGNORECASE)


def etim_available() -> bool:
    return (ETIM_EXTRACTED / "ETIMVALUE.csv").is_file()


def _read_etim(name: str) -> list[list[str]]:
    text = (ETIM_EXTRACTED / name).read_text(encoding=_ETIM_ENCODING)
    return list(csv.reader(io.StringIO(text), delimiter=_ETIM_DELIMITER))[1:]


@lru_cache(maxsize=1)
def etim_ip_codes() -> frozenset[str]:
    """The IP codes ETIM's committees list as distinct values.

    Used as an authority on *which codes exist*, not on what they mean. Two codes present as
    separate entries are two values in ETIM's vocabulary; a string that is not in the list is one
    this corroborator has no standing to judge.
    """
    if not etim_available():
        return frozenset()
    return frozenset(
        row[1].strip().upper()
        for row in _read_etim("ETIMVALUE.csv")
        if len(row) > 1 and _IP_CODE.fullmatch(row[1].strip())
    )


def _etim_rows_with_header(name: str) -> tuple[list[str], list[list[str]]]:
    text = (ETIM_EXTRACTED / name).read_text(encoding=_ETIM_ENCODING)
    rows = list(csv.reader(io.StringIO(text), delimiter=_ETIM_DELIMITER))
    return rows[0], rows[1:]


@lru_cache(maxsize=16)
def etim_feature_values(class_id: str, feature_id: str) -> frozenset[str]:
    """The values ETIM's committees declare for one feature of one class.

    ``etim_ip_codes`` reads ETIMVALUE.csv and filters by *shape*, which works for IP codes because
    ``IP44`` is unmistakable. It does not generalise: the release-characteristic values are ``B``,
    ``C``, ``K``, ``Z`` -- single letters that appear all over a 60,000-row value table meaning
    entirely different things. So this reads the actual mapping, through the join ETIM publishes:

        ETIMARTCLASSFEATUREMAP   (class, feature) -> ARTCLASSFEATURENR
        ETIMARTCLASSFEATUREVALUEMAP  ARTCLASSFEATURENR -> VALUEID
        ETIMVALUE                    VALUEID -> VALUEDESC

    That join is what makes the result an authority: it is not "letters that look like curves", it
    is "the values ETIM says this feature of this class may take".

    Returns an empty set when the release is not fetched, and callers decline on empty rather than
    treating an unfetched authority as an authority with nothing to say.
    """
    if not etim_available():
        return frozenset()

    map_header, map_rows = _etim_rows_with_header("ETIMARTCLASSFEATUREMAP.csv")
    i_nr = map_header.index("ARTCLASSFEATURENR")
    i_class = map_header.index("ARTCLASSID")
    i_feature = map_header.index("FEATUREID")
    numbers = {
        row[i_nr]
        for row in map_rows
        if len(row) > max(i_nr, i_class, i_feature)
        and row[i_class] == class_id
        and row[i_feature] == feature_id
    }
    if not numbers:
        return frozenset()

    value_header, value_rows = _etim_rows_with_header("ETIMARTCLASSFEATUREVALUEMAP.csv")
    j_nr = value_header.index("ARTCLASSFEATURENR")
    j_value = value_header.index("VALUEID")
    value_ids = {
        row[j_value]
        for row in value_rows
        if len(row) > max(j_nr, j_value) and row[j_nr] in numbers
    }

    descriptions = {row[0]: row[1] for row in _read_etim("ETIMVALUE.csv") if len(row) > 1}
    return frozenset(
        descriptions[value_id].strip() for value_id in value_ids if value_id in descriptions
    )


# ================================================================================================
# UN/CEFACT Recommendations 20 and 21 -- unit and package-type codes
#
# Both are UNECE code lists, freely published, and both are already fetched. Rec 20 lists units of
# measure; Rec 21 lists the codes for the package types goods are shipped in.
#
# **What they are an authority on, narrowly.** Whether two container NOUNS are separate entries in
# an internationally maintained list. That is a smaller question than "are these the same
# packaging" and it is deliberately the only one asked here -- Rec 21 assigns BX to a box and PK
# to a package, and it has no opinion whatsoever about whether "Box of 10" and "Pack of 10"
# describe the same commercial fact. That second question is the one the suite is mostly about,
# and it belongs to a human.
# ================================================================================================

UNCEFACT_DIR = Path("var/reference/uncefact")


def uncefact_available() -> bool:
    return (UNCEFACT_DIR / "rec21-package-codes.csv").is_file()


@lru_cache(maxsize=1)
def rec21_package_types() -> dict[str, str]:
    """``{"BX": "Box", "DR": "Drum", "RO": "Roll", "RL": "Reel", ...}``.

    Keyed by code, so two nouns resolving to two different codes is the finding. Names are
    lowercased on lookup rather than here, because the file's own capitalisation is the published
    form and rewriting it would put a second spelling of an external standard in this repository.
    """
    if not uncefact_available():
        return {}
    text = (UNCEFACT_DIR / "rec21-package-codes.csv").read_text(encoding="utf-8-sig")
    out: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(text)):
        code = (row.get("Code") or "").strip()
        name = (row.get("Name") or "").strip()
        if code and name:
            out[code] = name
    return out


@lru_cache(maxsize=1)
def rec21_code_for_noun() -> dict[str, str]:
    """The reverse index: a bare container noun to its Rec 21 code.

    Only entries whose published name is a **single bare noun** are indexed. Rec 21 is full of
    qualified forms -- "Drum, steel", "Box, fibreboard" -- and mapping the noun "drum" to whichever
    qualified entry happened to be read last would be inventing a canonical form the standard does
    not declare. A qualified entry still identifies its family; it just is not what this index is
    for.
    """
    index: dict[str, str] = {}
    for code, name in rec21_package_types().items():
        cleaned = name.strip()
        if "," in cleaned or " " in cleaned:
            continue
        index.setdefault(cleaned.lower(), code)
    return index


# ================================================================================================
# NBS Handbook H28 (1957) Part I -- Unified inch screw threads
#
# ASME B1.1 is the current standard for Unified threads and is paywalled. **NBS Handbook H28 is a
# United States Government publication and is in the public domain**, it covers the same UNC / UNF
# / UNEF series, and it is the document ASME B1.1 descends from. That is the whole trick: where the
# current standard is behind a paywall, the federal standard covering the same subject often is
# not.
#
# Read visually from a rendered scan of Tables III.3 (coarse), III.4 (fine) and III.5 (extra-fine)
# on pages 25-26, exactly as ISO 261 Table 2 was read. The OCR text layer of this document is bad
# enough to be dangerous -- it renders 40 as "4b" and 56 as "6" -- so nothing here was taken from
# it. sha256 registered in data/reference/manifest.json.
#
# TWO CELLS ARE DELIBERATELY ABSENT. `#4 UNC` and `#6 UNF` are smudged past legibility in this
# scan. Their values are well known and are NOT recorded here, because "well known" is how an
# unread number gets written down as though it had been read. An adjudicator asked about either
# declines instead.
# ================================================================================================

#: Threads per inch, Unified coarse series. NBS H28 (1957) Table III.3, p.25.
UNC_TPI: dict[str, str] = {
    "#1": "64", "#2": "56", "#3": "48", "#5": "40", "#6": "32", "#8": "32",
    "#10": "24", "#12": "24",
    "1/4": "20", "5/16": "18", "3/8": "16", "7/16": "14", "1/2": "13",
    "9/16": "12", "5/8": "11", "3/4": "10", "7/8": "9",
    "1": "8", "1 1/8": "7", "1 1/4": "7", "1 3/8": "6", "1 1/2": "6",
    "1 3/4": "5", "2": "4.5", "2 1/4": "4.5", "2 1/2": "4", "2 3/4": "4",
    "3": "4", "3 1/4": "4", "3 1/2": "4", "3 3/4": "4", "4": "4",
}

#: Threads per inch, Unified fine series. NBS H28 (1957) Table III.4, pp.25-26.
UNF_TPI: dict[str, str] = {
    "#0": "80", "#1": "72", "#2": "64", "#3": "56", "#4": "48", "#5": "44",
    "#8": "36", "#10": "32", "#12": "28",
    "1/4": "28", "5/16": "24", "3/8": "24", "7/16": "20", "1/2": "20",
    "9/16": "18", "5/8": "18", "3/4": "16", "7/8": "14",
    "1": "12", "1 1/8": "12", "1 1/4": "12", "1 3/8": "12", "1 1/2": "12",
}

#: Threads per inch, Unified extra-fine series. NBS H28 (1957) Table III.5, p.26.
#:
#: This is the table HANDOFF section 7 records an earlier session getting wrong -- UNF's 12 was
#: written into it where the answer is 18. Reading both tables side by side shows exactly how:
#: from 1 in upward UNF runs 12 and UNEF runs 18, in adjacent columns of adjacent pages.
UNEF_TPI: dict[str, str] = {
    "#12": "32", "1/4": "32", "5/16": "32", "3/8": "32", "7/16": "28", "1/2": "28",
    "9/16": "24", "5/8": "24", "11/16": "24",
    "3/4": "20", "13/16": "20", "7/8": "20", "15/16": "20", "1": "20",
    "1 1/16": "18", "1 1/8": "18", "1 3/16": "18", "1 1/4": "18", "1 5/16": "18",
    "1 3/8": "18", "1 7/16": "18", "1 1/2": "18", "1 9/16": "18", "1 5/8": "18",
    "1 11/16": "18", "1 3/4": "16", "2": "16",
}

UNIFIED_SERIES: dict[str, dict[str, str]] = {"UNC": UNC_TPI, "UNF": UNF_TPI, "UNEF": UNEF_TPI}
