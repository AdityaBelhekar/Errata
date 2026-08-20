"""Independent corroboration of suite labels against external, human-curated standards.

FR-0.1 wants the equivalence suite dual-labelled by someone who did not write the comparator.
There is no second person. This is the part of that gap that can be closed without one.

**The idea.** Many suite labels turn on a *factual* question with a published answer. "Is 0.5 in
the same length as 12.7 mm" is settled by UCUM, a unit standard maintained by a committee with no
connection to this project. If our label says `equivalent` and UCUM's arithmetic says the two
quantities differ, that is a finding about our suite reached without our own code participating in
the judgment. That is exactly what an independent labeller provides, for the subset where an
external standard has an opinion.

**What this is not.** It is not a substitute for the human pass, and claiming otherwise would be
the kind of overreach this repository exists to catch. Three limits, all real:

1. **It only judges facts, not taxonomy.** The suite's seven labels encode judgments -- is this
   `granularity` or `precision`? should an ambiguous pair be `undetermined`? -- that no external
   dataset encodes. That is the harder half of labelling and it is untouched by this.
2. **Coverage is partial**, and reported per family rather than averaged into a headline.
3. **The spelling map is ours.** Turning `Nm` into UCUM's `N.m` is a small judgment we make, and
   it is the one place our own reading enters. It is kept deliberately literal, and any spelling
   not in it produces `CANNOT_JUDGE` rather than a guess.

Agreement here strengthens the suite. Disagreement is a finding either way -- our label may be
wrong, or the pair may be one UCUM cannot see the point of -- and both are reported case by case
rather than reduced to a rate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from .adjudicators import Verdict, ingress_verdict, thread_verdict, unified_thread_verdict
from .equivalence import Case, Label, load_cases
from .standards import etim_available
from .ucum import UcumNotAvailable, convert, resolve, ucum_available

__all__ = [
    "SPELLING_TO_UCUM",
    "CorroborationReport",
    "CorroborationResult",
    "Verdict",
    "corroborate",
    "corroborate_units",
    "render_corroboration",
]


#: Trade spelling -> UCUM code. **The one place our own reading enters**, so it is kept literal
#: and short. Nothing is inferred: an unlisted spelling yields CANNOT_JUDGE.
#:
#: Note `in` -> `[in_i]` (international inch) rather than the US survey inch `[in_us]`. Industrial
#: product data uses the international inch, they differ in the eighth significant figure, and no
#: case in this suite turns on the difference -- but the choice is a choice and is recorded here.
SPELLING_TO_UCUM: dict[str, str] = {
    # length
    "mm": "mm", "cm": "cm", "m": "m", "km": "km", "um": "um", "µm": "um", "nm": "nm",
    "in": "[in_i]", '"': "[in_i]", "inch": "[in_i]", "inches": "[in_i]",
    "ft": "[ft_i]", "foot": "[ft_i]", "feet": "[ft_i]", "mil": "[mil_i]",
    # area
    "mm2": "mm2", "mm²": "mm2", "cm2": "cm2", "cm²": "cm2", "m2": "m2", "m²": "m2",
    "um2": "um2", "µm²": "um2", "km2": "km2",
    # mass
    "g": "g", "kg": "kg", "mg": "mg", "t": "t", "lb": "[lb_av]", "oz": "[oz_av]",
    # electrical
    "A": "A", "mA": "mA", "kA": "kA", "V": "V", "mV": "mV", "kV": "kV",
    "W": "W", "kW": "kW", "mW": "mW", "VA": "V.A", "kVA": "kV.A",
    "Hz": "Hz", "kHz": "kHz", "ohm": "Ohm", "Ohm": "Ohm", "Ω": "Ohm",
    "mOhm": "mOhm", "kOhm": "kOhm", "F": "F", "uF": "uF", "µF": "uF", "nF": "nF", "pF": "pF",
    "H": "H", "mH": "mH", "uH": "uH",
    # torque / force / pressure
    "Nm": "N.m", "N*m": "N.m", "N.m": "N.m", "N-m": "N.m",
    "mNm": "mN.m", "mN*m": "mN.m", "mN.m": "mN.m",
    "kNm": "kN.m", "N": "N", "kN": "kN",
    "Pa": "Pa", "kPa": "kPa", "MPa": "MPa", "bar": "bar", "mbar": "mbar", "psi": "[psi]",
    # temperature
    "degC": "Cel", "°C": "Cel", "C": "Cel", "degF": "[degF]", "°F": "[degF]", "K": "K",
    # time
    "s": "s", "ms": "ms", "us": "us", "min": "min", "h": "h",
}

#: Denominators that make a vulgar fraction an inch size. The binary series is the whole
#: convention -- halves through sixty-fourths -- and anything outside it in this notation is
#: something else wearing a slash, usually a dual rating like `230/400 V`.
_INCH_DENOMINATORS = frozenset({2, 4, 8, 16, 32, 64})

#: `number unit`, with the number allowed as a decimal or a vulgar fraction (`1/2"`).
_QUANTITY = re.compile(
    r"^\s*(?P<num>-?\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?)\s*(?P<unit>[^\s].*?)\s*$"
)


@dataclass(frozen=True, slots=True)
class CorroborationResult:
    case_id: str
    family: str
    a: str
    b: str
    suite_label: Label
    verdict: Verdict
    detail: str = ""
    source: str = ""
    """Which external standard ruled on this pair. Empty when none could."""

    @property
    def is_judged(self) -> bool:
        return self.verdict is not Verdict.CANNOT_JUDGE

    @property
    def agrees(self) -> bool:
        """Does the external standard corroborate the suite's label.

        Only the two labels UCUM has an opinion about are scored. `granularity`, `precision`,
        `undetermined` and the rest are taxonomy judgments; a unit standard has nothing to say
        about them and pretending otherwise would manufacture agreement.
        """
        if not self.is_judged:
            return False
        if self.suite_label is Label.EQUIVALENT:
            return self.verdict is Verdict.EQUAL
        if self.suite_label is Label.CONTRADICTION:
            return self.verdict is Verdict.UNEQUAL
        return False

    @property
    def is_scoreable(self) -> bool:
        return self.is_judged and self.suite_label in {Label.EQUIVALENT, Label.CONTRADICTION}


@dataclass(frozen=True, slots=True)
class CorroborationReport:
    source: str
    results: tuple[CorroborationResult, ...]

    @property
    def scoreable(self) -> tuple[CorroborationResult, ...]:
        return tuple(r for r in self.results if r.is_scoreable)

    @property
    def agreements(self) -> tuple[CorroborationResult, ...]:
        return tuple(r for r in self.scoreable if r.agrees)

    @property
    def disagreements(self) -> tuple[CorroborationResult, ...]:
        return tuple(r for r in self.scoreable if not r.agrees)

    @property
    def coverage(self) -> float:
        return len(self.scoreable) / len(self.results) if self.results else 0.0

    @property
    def agreement_rate(self) -> float:
        scoreable = self.scoreable
        return len(self.agreements) / len(scoreable) if scoreable else 0.0


def _parse_quantity(text: str) -> tuple[Fraction, str, int] | None:
    """Magnitude, unit spelling, and the granularity of the last written digit.

    The third value is what makes an honest comparison possible. `13 mm` and `13.0 mm` are the
    same number and NOT the same assertion: the first is written to the nearest millimetre, the
    second to the nearest tenth. A corroborator that ignores that would call `0.5 in` vs `13 mm`
    a mismatch on a 0.3 mm difference the author never claimed was absent.

    Returned as a power of ten, so `13` -> 0 and `12.70` -> -2.
    """
    match = _QUANTITY.match(text)
    if match is None:
        return None
    raw = match.group("num").replace(" ", "")

    if "/" in raw:
        # A vulgar fraction, as in `1/2"` or `3/32 in`.
        #
        # Restricted to the inch series -- integer over a power of two up to 64 -- because that is
        # the only place this notation means a fraction in industrial data. `230/400 V` is a
        # DUAL-VOLTAGE designation, and reading it as 0.575 V is exactly how this corroborator
        # first reported a false disagreement against uni-304. A "proper fraction" test does not
        # catch it: 230/400 is numerically proper.
        numerator, _, denominator = raw.partition("/")
        if not (numerator.lstrip("-").isdigit() and denominator.isdigit()):
            return None
        top, bottom = int(numerator), int(denominator)
        if bottom not in _INCH_DENOMINATORS or abs(top) >= bottom:
            return None
        top, bottom = Fraction(top), Fraction(bottom)
        magnitude = top / bottom
        exponent = -9  # exact by construction; no rounding was performed
    else:
        try:
            magnitude = Fraction(raw)
        except (ValueError, ZeroDivisionError):
            return None
        _, _, decimals = raw.partition(".")
        exponent = -len(decimals)

    return magnitude, match.group("unit").strip(), exponent


def _verdict_for(a: str, b: str) -> tuple[Verdict, str]:
    left, right = _parse_quantity(a), _parse_quantity(b)
    if left is None or right is None:
        return Verdict.CANNOT_JUDGE, "not a bare `number unit` quantity"

    (a_mag, a_spelling, _), (b_mag, b_spelling, b_exponent) = left, right
    a_code = SPELLING_TO_UCUM.get(a_spelling)
    b_code = SPELLING_TO_UCUM.get(b_spelling)
    if a_code is None or b_code is None:
        missing = a_spelling if a_code is None else b_spelling
        return Verdict.CANNOT_JUDGE, f"no UCUM spelling mapped for {missing!r}"

    a_unit, b_unit = resolve(a_code), resolve(b_code)
    if a_unit is None or b_unit is None:
        return Verdict.CANNOT_JUDGE, "UCUM does not define one of the codes"
    if a_unit.dimension != b_unit.dimension:
        return Verdict.UNEQUAL, f"different dimensions ({a_code} vs {b_code})"

    # An affine unit on either side and different scales: decline.
    #
    # `80 degC` vs `144 degF` is correct if the attribute is a temperature RISE (a delta scales
    # by 9/5 with no offset) and wrong if it is a point reading (which takes the +32). Nothing in
    # either string says which. UCUM defines the scales, not the semantics of the field, so this
    # corroborator has no standing to rule -- and ruling anyway is how it first reported a false
    # disagreement against unt-h031, a case the suite documents at length and pins deliberately.
    if (a_unit.is_affine or b_unit.is_affine) and a_code != b_code:
        return Verdict.CANNOT_JUDGE, (
            "affine temperature scales: point-vs-delta is not decidable from the surface form, "
            "and the two readings disagree"
        )

    converted = convert(a_mag, a_unit, b_unit)
    if converted is None:
        return Verdict.CANNOT_JUDGE, "not convertible"
    if converted == b_mag:
        return Verdict.EQUAL, f"{a_mag} {a_code} = {b_mag} {b_code} exactly"

    # Not exactly equal. Is the gap bigger than the precision the author actually wrote?
    #
    # `13 mm` is written to the nearest millimetre, so it asserts nothing finer than +/-0.5 mm,
    # and 12.7 sits inside that. Calling it a mismatch would be holding the author to a precision
    # they did not claim. Where the gap EXCEEDS the written granularity the values genuinely
    # differ and that holds under any rounding convention, so it is safe to rule.
    #
    # Inside the band, this declines rather than agreeing: whether overlapping written-precision
    # intervals count as `equivalent` or as `precision` is a taxonomy judgment, which is the half
    # of labelling this module has already said it cannot do.
    half_step = Fraction(1, 2) * Fraction(10) ** b_exponent
    gap = abs(converted - b_mag)
    if gap <= half_step:
        return Verdict.CANNOT_JUDGE, (
            f"{a_mag} {a_code} = {converted} {b_code}; differs from {b_mag} by {float(gap):g}, "
            f"within the +/-{float(half_step):g} the written precision of {b_mag!s} implies. "
            "Whether that is `equivalent` or `precision` is a taxonomy call, not a unit fact."
        )
    return Verdict.UNEQUAL, (
        f"{a_mag} {a_code} = {converted} {b_code}, not {b_mag} -- a gap of {float(gap):g}, "
        f"beyond the +/-{float(half_step):g} its written precision allows"
    )


#: Every external standard with an opinion, and the function that asks it.
#:
#: A case is offered to each in turn and the first that rules, rules. Order matters only for the
#: explanation a declined case carries, because the shapes each adjudicator recognises do not
#: overlap: a metric thread designation is not a unit quantity and is not an IP code.
ADJUDICATORS: tuple[tuple[str, object], ...] = (
    ("UCUM 2.2", _verdict_for),
    ("ISO 261:1998 Table 2", thread_verdict),
    ("NBS Handbook H28 (1957)", unified_thread_verdict),
    ("ETIM 10.0 value list", ingress_verdict),
)


def corroborate(cases: list[Case] | None = None) -> CorroborationReport:
    """Adjudicate the whole suite against every external standard available."""
    if not ucum_available():
        raise UcumNotAvailable("UCUM is not present. Run scripts/fetch_reference_data.sh.")

    results = []
    for case in cases if cases is not None else load_cases():
        verdict, detail, source = Verdict.CANNOT_JUDGE, "no external source applies", ""
        for name, adjudicate in ADJUDICATORS:
            candidate, explanation = adjudicate(case.a, case.b)  # type: ignore[operator]
            if candidate is not Verdict.CANNOT_JUDGE:
                verdict, detail, source = candidate, explanation, name
                break
            # Keep the most specific decline reason: an adjudicator that recognised the SHAPE and
            # still declined ("an X digit means not tested") is telling the reader something,
            # where one that never recognised it ("not a plain IP code") is not.
            if not explanation.startswith("not a"):
                detail = explanation
        results.append(
            CorroborationResult(
                case_id=case.id,
                family=case.family,
                a=case.a,
                b=case.b,
                suite_label=case.expect,
                verdict=verdict,
                detail=detail,
                source=source,
            )
        )

    sources = ["UCUM 2.2 (2024-06-17)", "ISO 261:1998 Table 2"]
    if etim_available():
        sources.append("ETIM 10.0 value list")
    return CorroborationReport(source=" + ".join(sources), results=tuple(results))


def corroborate_units(cases: list[Case] | None = None) -> CorroborationReport:
    """UCUM only. Kept because the UCUM pass is worth being able to run on its own when the
    question is specifically about unit handling."""
    if not ucum_available():
        raise UcumNotAvailable("UCUM is not present. Run scripts/fetch_reference_data.sh.")
    results = []
    for case in cases if cases is not None else load_cases():
        verdict, detail = _verdict_for(case.a, case.b)
        results.append(
            CorroborationResult(
                case_id=case.id,
                family=case.family,
                a=case.a,
                b=case.b,
                suite_label=case.expect,
                verdict=verdict,
                detail=detail,
                source="UCUM 2.2" if verdict is not Verdict.CANNOT_JUDGE else "",
            )
        )
    return CorroborationReport(
        source="UCUM 2.2 (2024-06-17), unitsofmeasure.org", results=tuple(results)
    )


def render_corroboration(report: CorroborationReport) -> str:
    lines = [
        "",
        "INDEPENDENT CORROBORATION -- suite labels vs an external standard",
        f"source: {report.source}",
        "-" * 94,
        "",
        "  This is a PARTIAL substitute for FR-0.1's independent dual-labelling. It settles",
        "  questions of FACT (is 0.5 in the same length as 12.7 mm) using a standard maintained by",
        "  people unconnected to this project. It has no opinion on the taxonomy judgments --",
        "  granularity vs precision vs undetermined -- which are the harder half of labelling.",
        "",
        f"  cases examined      {len(report.results)}",
        f"  externally judged   {len(report.scoreable)}  ({report.coverage:.1%} of the suite)",
        f"  agreement           {report.agreement_rate:.2%}  "
        f"({len(report.agreements)}/{len(report.scoreable)})",
        "",
    ]

    families: dict[str, list[CorroborationResult]] = {}
    for result in report.results:
        families.setdefault(result.family, []).append(result)
    lines.append("  by family")
    for family, items in sorted(families.items()):
        scoreable = [r for r in items if r.is_scoreable]
        agreed = sum(1 for r in scoreable if r.agrees)
        if scoreable:
            lines.append(
                f"    {family:12} {len(scoreable):4}/{len(items):<4} judged   "
                f"agreement {agreed / len(scoreable):7.2%}  ({agreed}/{len(scoreable)})"
            )
        else:
            lines.append(
                f"    {family:12} {0:4}/{len(items):<4} judged   "
                f"-- no external standard applies to these values"
            )

    if report.disagreements:
        lines += ["", f"  DISAGREEMENTS ({len(report.disagreements)}) -- each one is a finding"]
        for result in report.disagreements:
            lines.append(
                f"    {result.case_id:10} {result.a!r} vs {result.b!r}  "
                f"suite={result.suite_label.value}  UCUM={result.verdict.value}"
            )
            lines.append(f"      {result.detail}")
    else:
        lines += ["", "  No disagreements. Every externally judgeable label is corroborated."]

    uncovered = sorted(
        family for family, items in families.items() if not any(r.is_scoreable for r in items)
    )
    if uncovered:
        lines += ["", "  What would extend this, and what it would cost"]
        for family in uncovered:
            lines.append(f"    {family:12} {UNLOCKS.get(family, 'no candidate source identified')}")

    lines += [
        "",
        "  Still outstanding for FR-0.1: the taxonomy judgments -- granularity vs precision vs",
        "  undetermined -- and every family above with no external coverage. Those need a human",
        "  who did not write the comparator. This narrows that job; it does not remove it.",
        "",
    ]
    return "\n".join(lines)


#: What it would take to give an uncovered family an external source. Recorded next to the report
#: rather than in a planning document, because the person who notices the gap is the person
#: reading this output.
#:
#: `materials` deserves its note in full. Steel-grade cross-references are all over the web, and
#: every one found is a vendor marketing page or a PDF copying another vendor marketing page --
#: unattributed, uncited, and agreeing with each other for no traceable reason. Treating those as
#: an independent authority would be weak evidence dressed as corroboration, which is the exact
#: failure ground rule 1 exists to prevent, and the same reasoning that ruled out an inferred
#: distributor crosswalk for gate 3. The primary sources are paywalled; buying one is the honest
#: route and it is cheap next to the 112 cases it would unlock.
UNLOCKS: dict[str, str] = {
    "materials": (
        "EN 10088-1 or ASTM A959 (paywalled). 112 cases. Vendor cross-reference tables are "
        "NOT an acceptable substitute -- uncited, and they copy each other"
    ),
    "terms": (
        "IEC 60947-2 for trip curves and pole notation (paywalled). 119 cases. ETIM's class "
        "synonyms were tried and are too thin -- rccb, elcb and fuse return nothing"
    ),
    "ingress": "IEC 60529 (paywalled) would reach beyond the 57 codes ETIM publishes",
    "packaging": "UN/CEFACT Rec 20/21 are already fetched; a quantity-word adjudicator would fit",
    "threads": (
        "ISO 965-1 (tolerance classes) and ASME B1.1 (unified threads), both paywalled -- "
        "they would reach the 106 cases ISO 261 alone cannot"
    ),
}
