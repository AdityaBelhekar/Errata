"""External adjudicators — one per standard that has an opinion about a kind of value.

Each function takes two raw strings and answers one question: does this standard say these are the
same value, different values, or is it not something this standard rules on? Nothing here consults
`errata_valuesem`, which is the point — an adjudicator that used the comparator to check the
comparator would be a mirror, not a second opinion.

The discipline every adjudicator follows:

* **Recognise narrowly.** Each matches only the shapes it can actually rule on and declines the
  rest, so a case is never judged by a standard that does not cover it.
* **Decline the taxonomy questions.** Every one of these standards can say whether two values are
  the same. None of them can say whether a difference should be filed as `granularity` rather than
  `precision`, or whether missing information makes a pair `undetermined`. Where that is the real
  question, the honest answer is to decline, and the code says so in the returned explanation.
* **Never guess.** A diameter ISO 261 does not list, an IP code ETIM does not publish, a unit
  spelling that is not mapped -- all produce `CANNOT_JUDGE` with a reason, never a best effort.
"""

from __future__ import annotations

import enum
import re
from decimal import Decimal, InvalidOperation

from .standards import (
    UNIFIED_SERIES,
    etim_feature_values,
    etim_ip_codes,
    iso_261_coarse_pitch,
    rec21_code_for_noun,
)

__all__ = [
    "Verdict",
    "container_noun_verdict",
    "ingress_verdict",
    "release_characteristic_verdict",
    "thread_verdict",
    "unified_thread_verdict",
]


class Verdict(str, enum.Enum):
    """What an external standard says about a pair."""

    EQUAL = "equal"
    UNEQUAL = "unequal"
    CANNOT_JUDGE = "cannot_judge"
    """Not this standard's question, or not answerable from the strings alone. Reported, and
    **never** counted as agreement -- an adjudicator that scores its own silence is worthless."""


# ================================================================================================
# ISO 261:1998 Table 2 -- metric thread designations
# ================================================================================================

_METRIC_THREAD = re.compile(
    r"^M\s*(?P<dia>\d+(?:\.\d+)?)(?:\s*[x×*]\s*(?P<pitch>\d+(?:\.\d+)?))?$",
    re.IGNORECASE,
)


def thread_verdict(a: str, b: str) -> tuple[Verdict, str]:
    """Adjudicate two metric thread designations against ISO 261:1998 Table 2.

    The whole question is what a **bare** designation means. `M20` is not "M20 with some unstated
    pitch that might be 1.5"; it is M20 x 2.5 by reference to the standard, because Table 2 gives
    exactly one coarse pitch per diameter. That is the fine-pitch trap the threads family exists to
    test, and ISO 261 settles it without this project's parser being consulted at all.

    A diameter Table 2 does not list has no coarse pitch, so a bare designation at that diameter
    cannot be completed and the pair is declined rather than guessed at.
    """
    left, right = _METRIC_THREAD.match(a.strip()), _METRIC_THREAD.match(b.strip())
    if left is None or right is None:
        return Verdict.CANNOT_JUDGE, "not a plain metric thread designation"

    resolved: list[tuple[Decimal, Decimal, str]] = []
    for match in (left, right):
        try:
            diameter = Decimal(match.group("dia"))
        except InvalidOperation:  # pragma: no cover - the regex already constrains this
            return Verdict.CANNOT_JUDGE, "unparseable nominal diameter"
        stated = match.group("pitch")
        coarse_for_check = iso_261_coarse_pitch(diameter)
        if stated is not None:
            pitch = Decimal(stated)
            # `M8x40` is an M8 bolt forty millimetres long, not a thread of pitch 40. ISO 261
            # defines the designation `M<diameter>x<pitch>` and says nothing whatever about a
            # trailing length -- that is a trade convention living outside the standard -- so
            # this adjudicator has no standing to read it either way and declines.
            #
            # The test is clause 5.2: "It shall be understood that the 'coarse' pitches are the
            # largest metric pitches used in current practice." A second number above the coarse
            # pitch for that diameter cannot be a pitch, so the string is not a pure ISO 261
            # designation.
            #
            # Declining rather than ruling is deliberate. Reading the length as a length would
            # reproduce the shipped parser's own rule and turn this into a mirror; ruling the pair
            # UNEQUAL would contradict the suite over a convention ISO 261 never addresses. This
            # adjudicator first did the latter, against thr-h043/h044/h045.
            if coarse_for_check is not None and pitch > coarse_for_check:
                return Verdict.CANNOT_JUDGE, (
                    f"{pitch} exceeds the largest pitch ISO 261 lists at M{diameter} "
                    f"({coarse_for_check}), so it is a length suffix -- a trade convention the "
                    "standard does not define, and not something it can rule on"
                )
            resolved.append((diameter, pitch, "stated"))
            continue
        coarse = coarse_for_check
        if coarse is None:
            return Verdict.CANNOT_JUDGE, (
                f"M{diameter} is not a diameter ISO 261 Table 2 lists, so a bare designation "
                "cannot be completed"
            )
        resolved.append((diameter, coarse, "ISO 261 coarse"))

    (a_dia, a_pitch, a_how), (b_dia, b_pitch, b_how) = resolved
    if a_dia != b_dia:
        return Verdict.UNEQUAL, f"different nominal diameters: M{a_dia} against M{b_dia}"
    if a_pitch == b_pitch:
        return Verdict.EQUAL, f"both resolve to M{a_dia}x{a_pitch} ({a_how} / {b_how})"
    return Verdict.UNEQUAL, (
        f"M{a_dia}x{a_pitch} ({a_how}) against M{b_dia}x{b_pitch} ({b_how}); ISO 261 Table 2 "
        "gives one coarse pitch per diameter"
    )


# ================================================================================================
# ETIM 10.0 value list -- IP degree-of-protection codes
# ================================================================================================

_IP_PAIR = re.compile(r"^IP\s*(?P<solids>[0-9X])(?P<liquids>[0-9X])$", re.IGNORECASE)


def ingress_verdict(a: str, b: str) -> tuple[Verdict, str]:
    """Adjudicate two IP codes against ETIM's curated value list.

    ETIM's technical committees publish 57 IP codes as distinct entries in their value vocabulary.
    Two codes that both appear there are two values in an external, human-maintained list, and
    whether they are the same value is then simply whether they are the same entry.

    **An `X` digit is always declined.** In IEC 60529, `X` means that digit was not tested -- not
    that it was tested and scored zero. So `IP20` against `IP2X` is a question about how to treat
    missing information, and the suite labels cases of that shape four different ways on purpose:
    `agreement_specific`, `granularity`, `undetermined`, `equivalent`. A value list has no opinion
    on which is right, and pretending otherwise would manufacture agreement on the exact cases
    where the judgment is hardest.
    """
    left, right = _IP_PAIR.match(a.strip()), _IP_PAIR.match(b.strip())
    if left is None or right is None:
        return Verdict.CANNOT_JUDGE, "not a plain IP code"

    a_code = f"IP{left.group('solids')}{left.group('liquids')}".upper()
    b_code = f"IP{right.group('solids')}{right.group('liquids')}".upper()

    if "X" in a_code or "X" in b_code:
        return Verdict.CANNOT_JUDGE, (
            "an X digit means 'not tested' rather than 'zero'; whether that makes the pair "
            "granularity, agreement-specific or undetermined is a taxonomy judgment"
        )

    known = etim_ip_codes()
    if not known:
        return Verdict.CANNOT_JUDGE, "ETIM value list not fetched"
    missing = [code for code in (a_code, b_code) if code not in known]
    if missing:
        return Verdict.CANNOT_JUDGE, f"not in ETIM's IP value list: {', '.join(missing)}"

    if a_code == b_code:
        return Verdict.EQUAL, f"both are {a_code}, a single entry in ETIM's IP value list"
    return Verdict.UNEQUAL, (
        f"{a_code} and {b_code} are separate entries in ETIM's curated IP value list"
    )


# ================================================================================================
# NBS Handbook H28 (1957) -- Unified inch screw threads
# ================================================================================================

#: `#6-32 UNC`, `1/4-20 UNC`, `1 1/4 UNF`, `0.375-16 UNC`, `No. 10-32`, `2-4.5 UNC`.
_UNIFIED = re.compile(
    r"""^\s*
    (?:(?:No\.?|\#)\s*(?P<num>\d+)|(?P<size>\d+(?:\s+\d+/\d+)?(?:/\d+)?(?:\.\d+)?))
    \s*(?:[-\s]\s*(?P<tpi>\d+(?:\.\d+)?))?
    \s*(?P<series>UNC|UNF|UNEF|UN)?\s*$""",
    re.IGNORECASE | re.VERBOSE,
)

#: Shapes H28's threads-per-inch tables have no standing to rule on. Each is declined outright.
_UNIFIED_OUT_OF_SCOPE = (
    (re.compile(r"\bUNJ|MJ\b", re.IGNORECASE),
     "UNJ/MJ is a controlled-root-radius profile defined by ASME B1.15/B1.21M, not by H28's "
     "threads-per-inch tables"),
    (re.compile(r"-\s*[123][AB]\b", re.IGNORECASE),
     "a tolerance class (2A/2B/3A...) distinguishes external from internal and one fit grade "
     "from another; H28's TPI tables say nothing about either"),
    (re.compile(r"\bLH\b|left[- ]hand", re.IGNORECASE),
     "hand of thread is not a threads-per-inch question"),
    (re.compile(r"\bNPT|NPTF|NPS|BSP|BSPP|BSPT|\bG\s*\d|\bR[cp]?\s*\d", re.IGNORECASE),
     "pipe threads are ASME B1.20.1 / ISO 7-1 / ISO 228-1, not H28 Part I"),
)

#: Fractional sizes as written in H28's tables, keyed by their decimal inch value, so `0.375`
#: and `3/8` resolve to the same row.
_DECIMAL_TO_FRACTION = {
    "0.25": "1/4", "0.3125": "5/16", "0.375": "3/8", "0.4375": "7/16", "0.5": "1/2",
    "0.5625": "9/16", "0.625": "5/8", "0.6875": "11/16", "0.75": "3/4", "0.8125": "13/16",
    "0.875": "7/8", "0.9375": "15/16",
}


def _unified_size_key(match: re.Match[str]) -> str | None:
    """Normalise a size to the key H28's tables use."""
    if match.group("num") is not None:
        return f"#{int(match.group('num'))}"
    size = " ".join((match.group("size") or "").split())
    if not size:
        return None
    if "." in size:
        try:
            return _DECIMAL_TO_FRACTION.get(str(Decimal(size).normalize()), size)
        except InvalidOperation:
            return size
    return size


def unified_thread_verdict(a: str, b: str) -> tuple[Verdict, str]:
    """Adjudicate two Unified inch thread designations against NBS Handbook H28 (1957).

    ASME B1.1 is the current standard and is paywalled; H28 is a US Government publication in the
    public domain covering the same UNC/UNF/UNEF series, and B1.1 descends from it. Where the
    current standard costs money, the federal one it grew out of often does not.

    Declines rather than rules on anything H28's threads-per-inch tables do not address --
    controlled-root-radius profiles, tolerance classes, hand of thread, pipe threads. Those are
    real distinctions and the suite labels several of them `contradiction`; a TPI table that
    answered them would be agreeing for the wrong reason, which is worse than not answering.
    """
    for pattern, reason in _UNIFIED_OUT_OF_SCOPE:
        if pattern.search(a) or pattern.search(b):
            return Verdict.CANNOT_JUDGE, reason

    left, right = _UNIFIED.match(a.strip()), _UNIFIED.match(b.strip())
    if left is None or right is None:
        return Verdict.CANNOT_JUDGE, "not a plain Unified inch thread designation"
    if not (left.group("series") or left.group("tpi")):
        return Verdict.CANNOT_JUDGE, "no series or pitch given on one side"
    if not (right.group("series") or right.group("tpi")):
        return Verdict.CANNOT_JUDGE, "no series or pitch given on one side"

    resolved: list[tuple[str, Decimal, str]] = []
    for match in (left, right):
        size = _unified_size_key(match)
        if size is None:
            return Verdict.CANNOT_JUDGE, "unparseable size"
        stated = match.group("tpi")
        if stated is not None:
            resolved.append((size, Decimal(stated), "stated"))
            continue
        series = (match.group("series") or "").upper()
        table = UNIFIED_SERIES.get(series)
        if table is None:
            return Verdict.CANNOT_JUDGE, (
                f"{series or 'no series'} is not one of H28's UNC/UNF/UNEF tables"
            )
        tpi = table.get(size)
        if tpi is None:
            return Verdict.CANNOT_JUDGE, (
                f"H28's {series} table does not legibly give a value for {size} in the scan read"
            )
        resolved.append((size, Decimal(tpi), f"H28 {series}"))

    (a_size, a_tpi, a_how), (b_size, b_tpi, b_how) = resolved
    if a_size != b_size:
        return Verdict.UNEQUAL, f"different nominal sizes: {a_size} against {b_size}"
    if a_tpi == b_tpi:
        return Verdict.EQUAL, f"both are {a_size} at {a_tpi} TPI ({a_how} / {b_how})"
    return Verdict.UNEQUAL, (
        f"{a_size} at {a_tpi} TPI ({a_how}) against {b_tpi} TPI ({b_how})"
    )


# ================================================================================================
# ETIM 10.0 -- release characteristic (EF000889 on EC000042), the trip curve
#
# The corroboration report has said for some time that the terms family needs IEC 60947-2 and that
# "ETIM's class synonyms were tried and are too thin". Both halves were true and the conclusion was
# too broad: what was tried was ETIMARTCLASSSYNONYMMAP, an index of alternative names for a
# *class*. The trip curve is not a class, it is a FEATURE with a closed value list, and ETIM
# publishes it:
#
#     EF000889 "Release characteristic" on EC000042 -> A, B, C, Cs, D, E, F, G, K, KM, MA, S, Z
#
# That is a curated list maintained by ETIM's technical committees, free under ODC-By, already
# fetched, and completely unconnected to this project. It settles exactly one question -- are these
# two designations the same entry in that list -- which is the question most of the trip-curve
# cases ask.
# ================================================================================================

#: The class the release characteristic is read from. R1 audits miniature circuit breakers and
#: EC000042 is ETIM's class for them; the value list is a property of the (class, feature) pair,
#: not of the feature alone, so the class is named rather than searched for.
MCB_CLASS = "EC000042"
RELEASE_CHARACTERISTIC = "EF000889"

#: `C`, `Type C`, `type  c`, `C curve`, `curve B`, `Char. B`, `Characteristic C`,
#: `tripping characteristic B`, `K characteristic`, `MA curve`.
_RELEASE = re.compile(
    r"""^\s*
    (?:(?:tripping\s+|trip\s+)?(?:characteristic|char\.?|curve|type)\s*)?
    (?P<code>[A-Za-z]{1,2})
    (?:\s*[-\s]\s*(?:characteristic|char\.?|curve|type))?
    \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def release_characteristic_verdict(a: str, b: str) -> tuple[Verdict, str]:
    """Adjudicate two trip-curve designations against ETIM's published value list.

    **Case is significant and that is a fact about the list, not a convenience.** ETIM publishes
    both ``C`` and ``Cs`` as distinct values, so a case-insensitive match would silently fold two
    entries into one. The parse is case-insensitive because ``type c`` and ``TYPE C`` are the same
    designation typed differently; the *resolution* to a list entry is then done by matching
    case-insensitively against the published entries and rejecting anything that matches more than
    one -- so ``cs`` resolves to ``Cs``, and a designation that could be either of two entries is
    declined rather than assigned to the first.

    **What this does not rule on.** Whether a curve designation and a *current range* say the same
    thing -- ``C`` against ``5-10x In`` -- is a question about IEC 60947-2's definitions, which are
    paywalled and which a value list does not contain. Declined.
    """
    known = etim_feature_values(MCB_CLASS, RELEASE_CHARACTERISTIC)
    if not known:
        return Verdict.CANNOT_JUDGE, "ETIM release-characteristic value list not fetched"

    left, right = _RELEASE.match(a.strip()), _RELEASE.match(b.strip())
    if left is None or right is None:
        return Verdict.CANNOT_JUDGE, "not a plain trip-curve designation"

    resolved: list[str] = []
    for match in (left, right):
        code = match.group("code")
        hits = [entry for entry in known if entry.lower() == code.lower()]
        if len(hits) != 1:
            return Verdict.CANNOT_JUDGE, (
                f"{code!r} matches {len(hits)} entries in ETIM's release-characteristic list; "
                "a designation that could be more than one value is not one this list settles"
            )
        resolved.append(hits[0])

    if resolved[0] == resolved[1]:
        return Verdict.EQUAL, (
            f"both designate {resolved[0]!r}, a single entry in ETIM's release-characteristic "
            f"value list for {MCB_CLASS}/{RELEASE_CHARACTERISTIC}"
        )
    return Verdict.UNEQUAL, (
        f"{resolved[0]!r} and {resolved[1]!r} are separate entries in ETIM's "
        "release-characteristic value list"
    )


# ================================================================================================
# UN/CEFACT Recommendation 21 -- package type codes
#
# Narrow on purpose. Rec 21 assigns a code to a container noun and has NO opinion about whether
# "Box of 10" and "Pack of 10" describe the same commercial fact -- which is what most of the
# packaging family is actually about. So this adjudicator answers one question and declines
# everything else: are these two bare container nouns separate entries in Rec 21.
#
# It is worth having for one reason. The value layer's packaging ontology deliberately merges
# several nouns into a single frame, with a comment explaining why for reel and roll ("for cable
# and tape the noun varies by vendor while the commercial fact does not"). That merge is a
# judgment, and a judgment is exactly the kind of thing an external list should be allowed to
# disagree with in public.
# ================================================================================================

_BARE_NOUN = re.compile(r"^\s*(?P<noun>[A-Za-z]+)\s*$")


def container_noun_verdict(a: str, b: str) -> tuple[Verdict, str]:
    """Adjudicate two bare container nouns against UN/CEFACT Rec 21.

    Declines anything carrying a quantity. ``Box of 10`` is not a container noun, it is a container
    noun and a multiplier, and the multiplier is the part the packaging family is testing.
    """
    index = rec21_code_for_noun()
    if not index:
        return Verdict.CANNOT_JUDGE, "UN/CEFACT Rec 21 not fetched"

    left, right = _BARE_NOUN.match(a), _BARE_NOUN.match(b)
    if left is None or right is None:
        return Verdict.CANNOT_JUDGE, "not a bare container noun (a quantity is not Rec 21's question)"

    a_noun, b_noun = left.group("noun").lower(), right.group("noun").lower()
    a_code, b_code = index.get(a_noun), index.get(b_noun)
    missing = [n for n, c in ((a_noun, a_code), (b_noun, b_code)) if c is None]
    if missing:
        return Verdict.CANNOT_JUDGE, f"not a bare Rec 21 package name: {', '.join(missing)}"

    if a_code == b_code:
        return Verdict.EQUAL, f"both are Rec 21 {a_code} ({a_noun})"
    return Verdict.UNEQUAL, (
        f"Rec 21 assigns {a_noun} = {a_code} and {b_noun} = {b_code}, two separate entries"
    )
