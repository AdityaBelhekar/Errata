"""Citations in the suite are claims, and claims get checked.

Finding N1: the repository asserted "UN/ECE Rec 20" for codes that are Rec **21**. It was fixed
once in `ontology/packaging.yaml` and `model.py`, and it came straight back in the suite's own
`source:` fields, because a one-time correction does not survive the next author who copies a
neighbouring case.

So the rule is enforced rather than remembered. Rec 20 and Rec 21 are different recommendations:

* **Rec 20** is units of measure -- EA "each", PR "pair", CEN "hundred", DZN "dozen", H87 "piece".
* **Rec 21** is package types -- BX box, PK package, CT carton, BG bag, CS case, TU tube, RO roll,
  RL reel.

Rec 20 *lists* the container nouns, but every one of them carries status ``X`` with the
description "Use UN/ECE Recommendation 21". Citing them as Rec 20 codes is a mis-citation, and it
is the kind that survives review because nobody opens the list.

Verified 2026-08-19 against both machine-readable lists (Rec 20 Rev 17, 2136 codes; Rec 21, 406
codes). The lists are fetched by `scripts/fetch_reference_data.sh` and registered with their
sha256 in `data/reference/manifest.json`; these tests do not depend on them being present, because
a test that silently skips is not a test. The facts below are pinned as constants and the
provenance of each is recorded next to it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SUITE_DIR = Path(__file__).resolve().parents[1] / "src" / "errata_bench" / "suites" / "equivalence"

#: Container nouns that carry status X in Rec 20 Rev 17 with the description
#: "Use UN/ECE Recommendation 21 (refer to Note 2 in the spreadsheet introduction, 1st sheet)."
#: Each is also a real Rec 21 code. Verified 2026-08-19 against both lists.
REC21_CONTAINER_CODES = ("BX", "PK", "CT", "BG", "RL", "RO", "CS", "TU")

#: Genuine Rec 20 unit-of-measure codes, active status. Verified 2026-08-19.
REC20_UNIT_CODES = ("EA", "PR", "CEN", "DZN", "H87", "MIL")

#: Codes that are NOT in Rec 20 Rev 17 at all, and the trap each one sets.
NOT_REC20 = {
    "PCE": 'trade/EDIFACT abbreviation for "piece"; Rec 20\'s code is H87',
    "DZ": 'trade abbreviation for "dozen"; Rec 20\'s code is DZN',
}


def _suite_files() -> list[Path]:
    files = sorted(SUITE_DIR.glob("*.yaml"))
    assert files, f"no suite files under {SUITE_DIR}"
    return files


@pytest.mark.parametrize("code", REC21_CONTAINER_CODES)
def test_no_suite_file_calls_a_container_noun_a_rec_20_code(code: str) -> None:
    """The N1 regression guard.

    Matches the shape of the mis-citation -- "Rec 20 code CT", "Rec 20: CT ..." -- rather than
    any mention of the two numbers together, because the corrected citations deliberately name
    both recommendations in order to explain the distinction.
    """
    pattern = re.compile(
        rf"Rec\.?\s*20\b[^.\n]{{0,40}}?\bcode\s+{code}\b"
        rf"|Rec\.?\s*20\s*(?:code)?\s*:?\s*{code}\b",
        re.IGNORECASE,
    )
    offenders = []
    for path in _suite_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        f"{code} is a UN/ECE Recommendation 21 package-type code. In Rec 20 Rev 17 it carries "
        f"status X with the instruction 'Use UN/ECE Recommendation 21'. Cite Rec 21.\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(("code", "why"), sorted(NOT_REC20.items()))
def test_no_suite_file_claims_a_non_existent_rec_20_code(code: str, why: str) -> None:
    """Neither PCE nor DZ is a code in Rec 20 Rev 17 or in Rec 21.

    This is the sharper half of N1 and was not in the original finding: a mis-citation that
    points at the *wrong* recommendation is at least pointing at something. `Rec 20 code PCE`
    points at nothing, and reads as authoritative precisely because it is specific.
    """
    pattern = re.compile(rf"Rec\.?\s*2[01]\b[^.\n]{{0,40}}?\bcode\s+{code}\b", re.IGNORECASE)
    offenders = [
        f"{path.name}:{lineno}: {line.strip()}"
        for path in _suite_files()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert not offenders, f"{code} is not a UN/CEFACT code -- {why}.\n  " + "\n  ".join(offenders)


def test_every_case_still_carries_a_source() -> None:
    """The citation audit corrects `source:` fields; it must never empty one.

    A blank citation is worse than a wrong one -- a wrong one can be caught by reading the
    standard, a blank one just looks like the case was never checked.
    """
    missing = []
    for path in _suite_files():
        text = path.read_text(encoding="utf-8")
        ids = re.findall(r"^\s*-\s*id:\s*(\S+)", text, re.M)
        sources = re.findall(r"^\s+source:\s*(\S)", text, re.M)
        if len(sources) < len(ids):
            missing.append(f"{path.name}: {len(ids)} cases but {len(sources)} source fields")
    assert not missing, "\n".join(missing)


def test_the_reference_lists_are_registered_if_they_were_fetched() -> None:
    """If someone has run the fetcher, the manifest must describe what landed.

    Deliberately does not require the payload to be present -- the repository distributes URLs
    and hashes, not files (FR-9.5) -- but if the files are there, they are there because the
    manifest said to fetch them.
    """
    import json

    repo = Path(__file__).resolve().parents[2]
    manifest = json.loads((repo / "data" / "reference" / "manifest.json").read_text(encoding="utf-8"))
    ids = {a["id"] for a in manifest["artifacts"]}
    fetched = repo / "var" / "reference" / "uncefact"
    if fetched.is_dir() and any(fetched.glob("*.csv")):
        assert "uncefact-rec20-units" in ids and "uncefact-rec21-package-codes" in ids, (
            "UN/CEFACT lists are present under var/reference/ but not registered in the "
            "manifest -- provenance has to travel with the data"
        )


# ---------------------------------------------------------------------------------------------
# ISO 261 -- facts read out of the standard itself (P1 task 1.1, 2026-08-19)
#
# ISO 261:1998 Table 2 was opened via the free iTeh publisher preview, which carries the whole
# table. The three constants below are transcriptions, not recollections, and the citation audit
# of threads_hard.yaml turned on exactly them: three cases called M11, M4,5 and M2,2 "3rd-choice"
# diameters when Table 2 puts all three in Col. 2. Their pitches were correct, so nothing failed
# and the error survived.
#
# That is the failure mode HANDOFF section 7 describes -- disciplined about the fact that looked
# shaky, careless about the one nobody was expected to open. Pinned here so a future author
# copying a neighbouring case cannot quietly reintroduce it.
# ---------------------------------------------------------------------------------------------

#: Choice column in ISO 261:1998 Table 2, for the diameters threads_hard.yaml discusses by column.
ISO_261_CHOICE_COLUMN = {"M9": 3, "M11": 2, "M4.5": 2, "M2.2": 2, "M68": 2}

#: Coarse pitch in millimetres, ISO 261:1998 Table 2.
ISO_261_COARSE_PITCH_MM = {
    "M2.2": "0.45", "M4.5": "0.75", "M6": "1", "M8": "1.25", "M9": "1.25", "M10": "1.5",
    "M11": "1.5", "M12": "1.75", "M14": "2", "M16": "2", "M18": "2.5", "M20": "2.5",
    "M22": "2.5", "M24": "3", "M30": "3.5", "M36": "4", "M52": "5", "M64": "6", "M68": "6",
}

#: The largest pitch anywhere in Table 2. NOT 6 mm -- 6 mm is the largest *coarse* pitch, and
#: above M68 the table lists no coarse pitch at all.
ISO_261_LARGEST_PITCH_MM = 8
ISO_261_LARGEST_COARSE_PITCH_MM = 6


def _threads_hard() -> str:
    return (SUITE_DIR / "threads_hard.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "designation", [d for d, col in ISO_261_CHOICE_COLUMN.items() if col != 3]
)
def test_no_second_choice_diameter_is_called_third_choice(designation: str) -> None:
    """M11, M4,5, M2,2 and M68 are Col. 2 diameters. M9 is the only 3rd-choice one here.

    Matches the assertive form only. `thr-h023`'s rationale legitimately reads "Not even a
    3rd-choice size -- M68 is 2nd choice", and a guard that cannot tell that sentence from a
    misattribution would be demanding the removal of a correct one.
    """
    bare = re.escape(designation[1:])
    pattern = rf"M{bare}\s+(?:is|was)\s+a\s+3rd[- ]choice"
    assert not re.search(pattern, _threads_hard(), re.IGNORECASE), (
        f"{designation} is a Col. 2 (2nd choice) diameter in ISO 261:1998 Table 2, not 3rd choice"
    )


def test_m9_is_still_correctly_called_third_choice() -> None:
    """The negative control for the test above.

    A guard that only ever removes the string "3rd-choice" would pass by deleting a correct
    claim as readily as an incorrect one. M9 genuinely is Col. 3, and must stay described that way.
    """
    assert re.search(r"M9 is a 3rd-choice", _threads_hard()), (
        "M9 IS a 3rd-choice diameter in ISO 261 Table 2 -- do not 'fix' this one"
    )


def test_no_case_claims_six_millimetres_is_the_largest_metric_pitch() -> None:
    """ISO 261:1998 Table 2 lists a pitch of 8 mm at M125 and M130.

    Two cases argued that a trailing number in `M8x40` cannot be a pitch because the metric
    series was claimed to stop at 6 mm. The verdicts were right and the premise was false. The
    corrected citations argue from the M8 row instead, which is the row that actually decides it.
    """
    # Scan the case data, not the file's commentary: the audit record in the header necessarily
    # describes the error it corrected, and a guard that cannot tell an assertion from a
    # description of a fixed assertion will fight its own documentation.
    text = "\n".join(
        line for line in _threads_hard().splitlines() if not line.lstrip().startswith("#")
    )
    for claim in (
        r"no metric pitch exceeds 6\s*mm",
        r"largest pitch in the whole metric series is 6\s*mm",
    ):
        assert not re.search(claim, text, re.IGNORECASE), (
            f"ISO 261 Table 2 lists {ISO_261_LARGEST_PITCH_MM} mm (M125, M130). "
            f"{ISO_261_LARGEST_COARSE_PITCH_MM} mm is the largest COARSE pitch."
        )


def test_the_parser_agrees_with_the_standard_on_coarse_pitch() -> None:
    """Cross-check the shipped coarse-pitch table against ISO 261:1998 Table 2.

    Not circular: the right-hand side is a transcription from the standard, and the left-hand
    side is the table the comparator actually uses. A disagreement means one of them is wrong,
    and either way it is a finding.
    """
    from decimal import Decimal

    from errata_valuesem.tables import ISO_COARSE_PITCH_MM

    disagreements = []
    for designation, pitch in ISO_261_COARSE_PITCH_MM.items():
        diameter = Decimal(designation[1:])
        shipped = ISO_COARSE_PITCH_MM.get(diameter)
        if shipped is None:
            disagreements.append(f"{designation}: absent from the shipped table")
        elif Decimal(shipped) != Decimal(pitch):
            disagreements.append(f"{designation}: shipped {shipped}, ISO 261 Table 2 says {pitch}")
    assert not disagreements, "\n  ".join(["parser vs ISO 261:1998 Table 2:", *disagreements])
