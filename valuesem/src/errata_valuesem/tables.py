"""Standard reference tables.

These exist so that ``M8`` and ``M8x1.25`` compare as the same thread. ISO 261 fixes the coarse
pitch for M8 at 1.25 mm, so a bare ``M8`` is not vaguer than ``M8x1.25`` -- it is fully specified
by reference to a published standard. ``M8x1`` is a different thread and must contradict both.

Without these tables an auditor either flags ``M8`` against ``M8x1.25`` (a false accusation on the
single most common fastener designation in existence) or treats every unpitched metric thread as
unparseable. Both are worse than a lookup table.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

__all__ = [
    "BSP_TPI",
    "GAUGE_DIAMETER_IN",
    "ISO_COARSE_PITCH_MM",
    "ISO_FINE_PITCHES_MM",
    "NPT_TPI",
    "PIPE_SERIES",
    "UNC_TPI",
    "UNEF_TPI",
    "UNF_TPI",
    "coarse_pitch_for",
    "fraction_to_decimal",
    "inch_to_mm",
    "infer_unified_series",
    "series_tpi_for",
]

GRAMMAR_VERSION = "tables/1.0.0"

MM_PER_INCH = Decimal("25.4")

#: ISO 261 / ISO 262 coarse pitch series, nominal diameter (mm) -> pitch (mm).
ISO_COARSE_PITCH_MM: dict[Decimal, Decimal] = {
    Decimal("1"): Decimal("0.25"),
    Decimal("1.1"): Decimal("0.25"),
    Decimal("1.2"): Decimal("0.25"),
    Decimal("1.4"): Decimal("0.3"),
    Decimal("1.6"): Decimal("0.35"),
    Decimal("1.8"): Decimal("0.35"),
    Decimal("2"): Decimal("0.4"),
    Decimal("2.2"): Decimal("0.45"),
    Decimal("2.5"): Decimal("0.45"),
    Decimal("3"): Decimal("0.5"),
    Decimal("3.5"): Decimal("0.6"),
    Decimal("4"): Decimal("0.7"),
    Decimal("4.5"): Decimal("0.75"),
    Decimal("5"): Decimal("0.8"),
    Decimal("5.5"): Decimal("0.9"),
    Decimal("6"): Decimal("1"),
    Decimal("7"): Decimal("1"),
    Decimal("8"): Decimal("1.25"),
    Decimal("9"): Decimal("1.25"),
    Decimal("10"): Decimal("1.5"),
    Decimal("11"): Decimal("1.5"),
    Decimal("12"): Decimal("1.75"),
    Decimal("14"): Decimal("2"),
    Decimal("16"): Decimal("2"),
    Decimal("18"): Decimal("2.5"),
    Decimal("20"): Decimal("2.5"),
    Decimal("22"): Decimal("2.5"),
    Decimal("24"): Decimal("3"),
    Decimal("27"): Decimal("3"),
    Decimal("30"): Decimal("3.5"),
    Decimal("33"): Decimal("3.5"),
    Decimal("36"): Decimal("4"),
    Decimal("39"): Decimal("4"),
    Decimal("42"): Decimal("4.5"),
    Decimal("45"): Decimal("4.5"),
    Decimal("48"): Decimal("5"),
    Decimal("52"): Decimal("5"),
    Decimal("56"): Decimal("5.5"),
    Decimal("60"): Decimal("5.5"),
    Decimal("64"): Decimal("6"),
    Decimal("68"): Decimal("6"),
}

#: Recognised fine pitches per nominal diameter, used to validate that a stated pitch is real.
ISO_FINE_PITCHES_MM: dict[Decimal, tuple[Decimal, ...]] = {
    Decimal("6"): (Decimal("0.75"),),
    Decimal("8"): (Decimal("1"), Decimal("0.75")),
    Decimal("10"): (Decimal("1.25"), Decimal("1"), Decimal("0.75")),
    Decimal("12"): (Decimal("1.5"), Decimal("1.25"), Decimal("1")),
    Decimal("14"): (Decimal("1.5"), Decimal("1.25"), Decimal("1")),
    Decimal("16"): (Decimal("1.5"), Decimal("1")),
    Decimal("18"): (Decimal("2"), Decimal("1.5"), Decimal("1")),
    Decimal("20"): (Decimal("2"), Decimal("1.5"), Decimal("1")),
    Decimal("22"): (Decimal("2"), Decimal("1.5"), Decimal("1")),
    Decimal("24"): (Decimal("2"), Decimal("1.5"), Decimal("1")),
    Decimal("27"): (Decimal("2"), Decimal("1.5"), Decimal("1")),
    Decimal("30"): (Decimal("2"), Decimal("1.5"), Decimal("1")),
    Decimal("36"): (Decimal("3"), Decimal("2"), Decimal("1.5")),
}

#: Nominal designation -> threads per inch. ASME B1.1 coarse series.
UNC_TPI: dict[str, Decimal] = {
    "#1": Decimal("64"),
    "#2": Decimal("56"),
    "#3": Decimal("48"),
    "#4": Decimal("40"),
    "#5": Decimal("40"),
    "#6": Decimal("32"),
    "#8": Decimal("32"),
    "#10": Decimal("24"),
    "#12": Decimal("24"),
    "1/4": Decimal("20"),
    "5/16": Decimal("18"),
    "3/8": Decimal("16"),
    "7/16": Decimal("14"),
    "1/2": Decimal("13"),
    "9/16": Decimal("12"),
    "5/8": Decimal("11"),
    "3/4": Decimal("10"),
    "7/8": Decimal("9"),
    "1": Decimal("8"),
    "1 1/8": Decimal("7"),
    "1 1/4": Decimal("7"),
    "1 3/8": Decimal("6"),
    "1 1/2": Decimal("6"),
    "1 3/4": Decimal("5"),
    "2": Decimal("4.5"),
    "2 1/4": Decimal("4.5"),
    "2 1/2": Decimal("4"),
    "2 3/4": Decimal("4"),
    "3": Decimal("4"),
}

#: ASME B1.1 fine series.
UNF_TPI: dict[str, Decimal] = {
    "#0": Decimal("80"),
    "#1": Decimal("72"),
    "#2": Decimal("64"),
    "#3": Decimal("56"),
    "#4": Decimal("48"),
    "#5": Decimal("44"),
    "#6": Decimal("40"),
    "#8": Decimal("36"),
    "#10": Decimal("32"),
    "#12": Decimal("28"),
    "1/4": Decimal("28"),
    "5/16": Decimal("24"),
    "3/8": Decimal("24"),
    "7/16": Decimal("20"),
    "1/2": Decimal("20"),
    "9/16": Decimal("18"),
    "5/8": Decimal("18"),
    "3/4": Decimal("16"),
    "7/8": Decimal("14"),
    "1": Decimal("12"),
    "1 1/8": Decimal("12"),
    "1 1/4": Decimal("12"),
    "1 3/8": Decimal("12"),
    "1 1/2": Decimal("12"),
}

UNEF_TPI: dict[str, Decimal] = {
    "1/4": Decimal("32"),
    "5/16": Decimal("32"),
    "3/8": Decimal("32"),
    "7/16": Decimal("28"),
    "1/2": Decimal("28"),
    "9/16": Decimal("24"),
    "5/8": Decimal("24"),
    "3/4": Decimal("20"),
    "7/8": Decimal("20"),
    "1": Decimal("20"),
    "1 1/8": Decimal("18"),
    "1 1/4": Decimal("18"),
    "1 3/8": Decimal("18"),
    "1 1/2": Decimal("18"),
}

#: ASME B1.20.1 national pipe taper.
NPT_TPI: dict[str, Decimal] = {
    "1/16": Decimal("27"),
    "1/8": Decimal("27"),
    "1/4": Decimal("18"),
    "3/8": Decimal("18"),
    "1/2": Decimal("14"),
    "3/4": Decimal("14"),
    "1": Decimal("11.5"),
    "1 1/4": Decimal("11.5"),
    "1 1/2": Decimal("11.5"),
    "2": Decimal("11.5"),
    "2 1/2": Decimal("8"),
    "3": Decimal("8"),
    "3 1/2": Decimal("8"),
    "4": Decimal("8"),
    "5": Decimal("8"),
    "6": Decimal("8"),
    "8": Decimal("8"),
}

#: ISO 228 / BS 2779 British Standard Pipe.
BSP_TPI: dict[str, Decimal] = {
    "1/16": Decimal("28"),
    "1/8": Decimal("28"),
    "1/4": Decimal("19"),
    "3/8": Decimal("19"),
    "1/2": Decimal("14"),
    "5/8": Decimal("14"),
    "3/4": Decimal("14"),
    "1": Decimal("11"),
    "1 1/4": Decimal("11"),
    "1 1/2": Decimal("11"),
    "2": Decimal("11"),
    "2 1/2": Decimal("11"),
    "3": Decimal("11"),
    "3 1/2": Decimal("11"),
    "4": Decimal("11"),
    "5": Decimal("11"),
    "6": Decimal("11"),
}

#: Unified numbered gauge -> major diameter in inches. ASME B1.1: d = 0.060 + 0.013 * gauge.
GAUGE_DIAMETER_IN: dict[str, Decimal] = {
    f"#{n}": (Decimal("0.060") + Decimal("0.013") * n) for n in range(0, 15)
}

#: Pipe-thread series and whether they are tapered, keyed by the designation prefix.
PIPE_SERIES: dict[str, dict[str, object]] = {
    "NPT": {"system": "pipe_npt", "tapered": True, "tpi": NPT_TPI, "standard": "ASME B1.20.1"},
    "NPTF": {"system": "pipe_npt", "tapered": True, "tpi": NPT_TPI, "standard": "ASME B1.20.3"},
    "NPS": {"system": "pipe_nps", "tapered": False, "tpi": NPT_TPI, "standard": "ASME B1.20.1"},
    "NPSM": {"system": "pipe_nps", "tapered": False, "tpi": NPT_TPI, "standard": "ASME B1.20.1"},
    "G": {"system": "pipe_bspp", "tapered": False, "tpi": BSP_TPI, "standard": "ISO 228-1"},
    "BSPP": {"system": "pipe_bspp", "tapered": False, "tpi": BSP_TPI, "standard": "ISO 228-1"},
    "RP": {"system": "pipe_bspp", "tapered": False, "tpi": BSP_TPI, "standard": "ISO 7-1"},
    "R": {"system": "pipe_bspt", "tapered": True, "tpi": BSP_TPI, "standard": "ISO 7-1"},
    "RC": {"system": "pipe_bspt", "tapered": True, "tpi": BSP_TPI, "standard": "ISO 7-1"},
    "BSPT": {"system": "pipe_bspt", "tapered": True, "tpi": BSP_TPI, "standard": "ISO 7-1"},
    "BSP": {"system": "pipe_bsp", "tapered": False, "tpi": BSP_TPI, "standard": "BS 2779"},
}

_SERIES_TABLES: dict[str, dict[str, Decimal]] = {
    "UNC": UNC_TPI,
    "UNF": UNF_TPI,
    "UNEF": UNEF_TPI,
    "UNJC": UNC_TPI,
    "UNJF": UNF_TPI,
}


def fraction_to_decimal(text: str) -> Decimal:
    """``"3/8"`` -> ``Decimal("0.375")``. Exact, because inch fractions are exact designations."""
    text = text.strip()
    if " " in text:  # mixed number: "1 1/2"
        whole, _, frac = text.partition(" ")
        return Decimal(whole) + fraction_to_decimal(frac)
    if "/" in text:
        f = Fraction(text)
        return Decimal(f.numerator) / Decimal(f.denominator)
    return Decimal(text)


def inch_to_mm(inches: Decimal) -> Decimal:
    return inches * MM_PER_INCH


def coarse_pitch_for(nominal_mm: Decimal) -> Decimal | None:
    """The ISO 261 coarse pitch for a nominal diameter, or ``None`` if the diameter is not a
    standard size. Returning ``None`` rather than interpolating is the point."""
    return ISO_COARSE_PITCH_MM.get(nominal_mm.normalize()) or ISO_COARSE_PITCH_MM.get(nominal_mm)


def series_tpi_for(series: str, designation: str) -> Decimal | None:
    table = _SERIES_TABLES.get(series.upper())
    if table is None:
        return None
    return table.get(designation)


def infer_unified_series(designation: str, tpi: Decimal) -> str:
    """Name the series a size/TPI pair belongs to, or ``""`` when it belongs to none.

    ``3/8-16`` is UNC; ``3/8-24`` is UNF; ``3/8-20`` is neither, and saying so is more useful than
    guessing the nearest.
    """
    for series, table in (("UNC", UNC_TPI), ("UNF", UNF_TPI), ("UNEF", UNEF_TPI)):
        if table.get(designation) == tpi:
            return series
    return ""
