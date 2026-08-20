"""Stage 1 of the pipeline: lexical canonicalization.

Pure text rewriting -- no semantics, no lookups. It exists so every downstream grammar sees one
spelling of ``x``, one spelling of the degree sign, and one decimal separator, instead of each
grammar carrying its own tolerance for typographic variation.

The one place this stage refuses rather than rewrites is the thousands-separator ambiguity:
``1,000`` is 1000 in English and 1 in German, a factor of a thousand, and guessing is exactly the
failure mode the product exists to detect.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

__all__ = ["NULLISH", "AmbiguousNumberError", "CanonicalText", "NullishError", "canonicalize"]

GRAMMAR_VERSION = "canonical/1.0.0"

#: Surface forms that mean "no value recorded". These are not parse failures -- a blank catalog
#: field is a finding in its own right (§3.3 catalog-null/evidence-present).
NULLISH: frozenset[str] = frozenset(
    {
        "",
        "-",
        "--",
        "---",
        "—",
        "–",
        ".",
        "?",
        "n/a",
        "n.a.",
        "na",
        "nil",
        "none",
        "null",
        "not applicable",
        "not specified",
        "unspecified",
        "unknown",
        "tbd",
        "tbc",
        "to be confirmed",
        "#n/a",
        "#value!",
        "0000-00-00",
    }
)

_SUPERSCRIPTS = {
    "²": "**2",
    "³": "**3",
    "⁰": "**0",
    "¹": "**1",
    "⁴": "**4",
}

_VULGAR_FRACTIONS = {
    "½": "1/2",
    "¼": "1/4",
    "¾": "3/4",
    "⅓": "1/3",
    "⅔": "2/3",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
}

_MULTIPLICATION = {
    "×": "x",  # MULTIPLICATION SIGN
    "✕": "x",  # MULTIPLICATION X
    "✖": "x",
    "⨯": "x",  # VECTOR OR CROSS PRODUCT
}

_DASHES = {
    "−": "-",  # MINUS SIGN
    "‐": "-",  # HYPHEN
    "‑": "-",  # NON-BREAKING HYPHEN
    "‒": "-",  # FIGURE DASH
}

#: Separators that unambiguously mean "from .. to". En/em dashes land here rather than in
#: :data:`_DASHES` because a dash between two numbers in a datasheet is a range, not a subtraction.
_RANGE_TOKENS = [
    "…",  # HORIZONTAL ELLIPSIS
    "...",
    "..",
    "–",  # EN DASH
    "—",  # EM DASH
]

_SPACES = {
    " ": " ",  # NBSP
    " ": " ",
    " ": " ",  # NARROW NBSP
    " ": " ",  # THIN SPACE
    "\t": " ",
}


class NullishError(ValueError):
    """Raised when the input is a recognised placeholder for "no value"."""


class AmbiguousNumberError(ValueError):
    """Raised when a comma could be a decimal separator or a thousands separator.

    ``1,000`` is 1000 under ``en`` and 1 under ``de``. The difference is three orders of magnitude
    on a rated-current field. The library declines rather than picking a locale it was not told.
    """


@dataclass(frozen=True, slots=True)
class CanonicalText:
    """The rewritten string, plus what the rewriting had to assume."""

    text: str
    original: str
    notes: tuple[str, ...] = ()


def canonicalize(raw: str, *, decimal_separator: str | None = None) -> CanonicalText:
    """Rewrite ``raw`` into the library's canonical lexical form.

    Args:
        raw: the source string, exactly as it appeared in the catalog or the document.
        decimal_separator: ``"."`` or ``","`` to resolve the thousands-separator ambiguity
            explicitly. ``None`` means "refuse the ambiguous case", which is the default and the
            honest one.

    Raises:
        NullishError: the value is a placeholder, not a value.
        AmbiguousNumberError: a comma group could not be resolved without a locale.
    """
    if raw is None:
        raise NullishError("value is None")

    notes: list[str] = []
    text = raw

    for src, dst in _SPACES.items():
        text = text.replace(src, dst)
    text = text.strip()

    if text.strip().lower() in NULLISH:
        raise NullishError(f"{raw!r} is a null placeholder, not a value")

    for src, dst in _SUPERSCRIPTS.items():
        text = text.replace(src, dst)
    for src, dst in _VULGAR_FRACTIONS.items():
        text = text.replace(src, dst)

    # NFKC after the superscript pass, so mm² has already become mm**2 rather than mm2.
    text = unicodedata.normalize("NFKC", text)

    for src, dst in _MULTIPLICATION.items():
        text = text.replace(src, dst)
    for src, dst in _DASHES.items():
        text = text.replace(src, dst)

    text = _rewrite_range_separators(text)
    text = _rewrite_units(text)
    text = _rewrite_numbers(text, decimal_separator, notes)

    text = re.sub(r"\s+", " ", text).strip()

    if not text or text.lower() in NULLISH:
        raise NullishError(f"{raw!r} reduced to a null placeholder")

    return CanonicalText(text=text, original=raw, notes=tuple(notes))


def _rewrite_range_separators(text: str) -> str:
    for token in _RANGE_TOKENS:
        text = text.replace(token, " .. ")
    # Word forms, only between numbers, so "to" inside a unit name survives.
    text = re.sub(r"(?<=[\d\)])\s+(?:to|bis|until|through)\s+(?=[-+\d])", " .. ", text, flags=re.I)
    text = re.sub(r"\s*\.\.\s*", " .. ", text)
    return text


def _rewrite_units(text: str) -> str:
    # Degree forms. Order matters: the compound forms before the bare degree sign.
    text = re.sub(r"°\s*C\b", "degC", text)
    text = re.sub(r"°\s*F\b", "degF", text)
    text = text.replace("℃", "degC").replace("℉", "degF")
    text = re.sub(r"°(?![A-Za-z])", " deg ", text)

    # Inch and foot marks following a number or a fraction: 3/8" -> 3/8 in
    text = re.sub(r'(?<=[\d/])\s*(?:"|″|”|“)', " in", text)
    text = re.sub(r"(?<=[\d/])\s*(?:'|′|’)(?![\w])", " ft", text)

    text = text.replace("Ω", "ohm").replace("Ω", "ohm")
    text = text.replace("µ", "u").replace("μ", "u")
    text = text.replace("·", "*").replace("∙", "*").replace("⋅", "*")
    text = text.replace("⁄", "/")  # FRACTION SLASH
    text = text.replace("±", " +/- ")
    return text


_NUM_WITH_COMMAS = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+)(?![\d,])")
_NUM_WITH_DOT_GROUPS = re.compile(r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+)(?![\d.])")
_DECIMAL_COMMA = re.compile(r"(?<![\w.,])(\d+),(\d{1,2})(?![\d])")
_AMBIGUOUS_COMMA = re.compile(r"(?<![\w.,])(\d{1,3}),(\d{3})(?![\d,.])")


def _rewrite_numbers(text: str, decimal_separator: str | None, notes: list[str]) -> str:
    has_dot = "." in re.sub(r"\s\.\.\s", " ", text)
    has_comma = "," in text

    if not has_comma:
        return text

    if decimal_separator == ",":
        text = _NUM_WITH_DOT_GROUPS.sub(lambda m: m.group(1).replace(".", ""), text)
        text = re.sub(r"(?<=\d),(?=\d)", ".", text)
        notes.append("decimal separator declared as ','")
        return text

    if decimal_separator == ".":
        text = _NUM_WITH_COMMAS.sub(lambda m: m.group(1).replace(",", ""), text)
        notes.append("decimal separator declared as '.'")
        return text

    # 1,234,567 -- more than one group can only be thousands.
    def _strip_groups(m: re.Match[str]) -> str:
        return m.group(1).replace(",", "")

    if re.search(r"\d,\d{3},\d{3}", text):
        text = _NUM_WITH_COMMAS.sub(_strip_groups, text)
        notes.append("comma read as thousands separator (multiple groups)")
        has_comma = "," in text
        if not has_comma:
            return text

    # A dot elsewhere in the same string settles it: the comma groups thousands.
    if has_dot and _AMBIGUOUS_COMMA.search(text):
        text = _NUM_WITH_COMMAS.sub(_strip_groups, text)
        notes.append("comma read as thousands separator (decimal point present)")
        return text

    if _AMBIGUOUS_COMMA.search(text):
        raise AmbiguousNumberError(
            f"{text!r}: a comma before exactly three digits is 1000x ambiguous "
            "(en '1,000' = 1000, de '1,000' = 1). Pass decimal_separator to resolve."
        )

    # One or two digits after the comma can only be a decimal comma.
    if _DECIMAL_COMMA.search(text):
        text = _DECIMAL_COMMA.sub(lambda m: f"{m.group(1)}.{m.group(2)}", text)
        notes.append("comma read as decimal separator (fewer than three trailing digits)")
        return text

    return text
