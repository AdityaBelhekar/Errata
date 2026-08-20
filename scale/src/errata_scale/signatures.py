"""FR-8.5 and FR-8.6 -- error signatures: computed, clustered, and never keyed to a company.

    FR-8.5: "Group records sharing a systematic pattern, report cluster size. The '1,240 SKUs
    share this pattern' claim is computed, not asserted."
    FR-8.6: "Signatures key to document/data artifacts only. Named-organisation signatures are
    prohibited. Schema has no field for it; test asserts absence."

**Why the claim has to be computed.** "1,240 SKUs share this error" is the sentence that turns a
list of defects into a decision: it is the difference between a reviewer fixing rows and an
engineering manager fixing a mapping. It is also the easiest number in this product to fake, since
nobody checks a cluster size. So the size here is ``len(members)`` of an enumerable set, every
member is addressable, and the fingerprint that grouped them is printed next to the count. If the
cluster is wrong, a reader can see *why* it is wrong.

**Why the prohibition is structural rather than a policy.** The natural next feature after
clustering is "which supplier sends us the worst data", and it is a product that gets its author
sued: a defect count keyed to a named company, computed by a system with a false-positive rate,
published inside a customer's organisation, is defamation with a dashboard. phase5-red-team.md
raised it and the PRD answers it with the only durable defence -- **there is no field to put the
name in**. Not a redaction step, not a permission: the schema cannot hold it, a test asserts the
absence, and a second test asserts that the same defect under two different manufacturers lands in
one cluster rather than two.

What a signature *may* key on is the artifact: the document revision the defect was found against,
the column it was found in, the attribute, the disagreement class, and the shape of the difference.
Those are properties of data, and they are what a fix has to be aimed at anyway.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation

from errata_spec import Redline

from .ids import signature_id

__all__ = [
    "BANNED_SIGNATURE_TERMS",
    "DefectShape",
    "ErrorSignature",
    "NamedOrganisationSignatureError",
    "SignatureCluster",
    "assert_no_named_organisation_field",
    "cluster_signatures",
    "defect_shape",
    "signature_for",
]


class NamedOrganisationSignatureError(TypeError):
    """Raised when a signature schema grows a field that names a company (FR-8.6)."""


#: Field-name fragments that would make a signature organisational. Checked against the signature
#: schema itself, so the prohibition fails at import time rather than at review time.
BANNED_SIGNATURE_TERMS: frozenset[str] = frozenset(
    {
        "manufacturer",
        "supplier",
        "vendor",
        "brand",
        "company",
        "organisation",
        "organization",
        "distributor",
        "seller",
        "merchant",
        "reseller",
        "account",
        "partner",
        "owner",
    }
)


class DefectShape(str):
    """How the two values differ, as a shape rather than as a pair of values.

    A shape is what makes a cluster useful: ``digit_transposition`` on ``rated_current`` is a
    keying error in an upstream process, and ``order_of_magnitude`` on ``weight`` is a unit
    conversion applied twice. The values themselves differ row by row; the shape does not.
    """

    DIGIT_TRANSPOSITION = "digit_transposition"
    ORDER_OF_MAGNITUDE = "order_of_magnitude"
    DIMENSION_MISMATCH = "dimension_mismatch"
    BLANK_CELL = "blank_cell"
    VALUE_SUBSTITUTION = "value_substitution"
    NO_PROPOSAL = "no_proposal"
    UNPARSED = "unparsed"


_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def defect_shape(catalog_value: str, proposed_value: str) -> str:
    """Classify the *shape* of a difference, from the two strings alone.

    Deterministic and total: every pair gets a shape, and the fallbacks say what they are rather
    than guessing. ``UNPARSED`` is a real answer -- a cluster of values nobody could parse is
    itself a finding about a feed.
    """
    catalog = (catalog_value or "").strip()
    proposed = (proposed_value or "").strip()
    if not catalog:
        return DefectShape.BLANK_CELL
    if not proposed:
        return DefectShape.NO_PROPOSAL

    catalog_number = _NUMBER.search(catalog)
    proposed_number = _NUMBER.search(proposed)
    if not catalog_number or not proposed_number:
        return DefectShape.VALUE_SUBSTITUTION

    catalog_unit = _unit_tail(catalog, catalog_number.end())
    proposed_unit = _unit_tail(proposed, proposed_number.end())
    if catalog_unit and proposed_unit and catalog_unit != proposed_unit:
        return DefectShape.DIMENSION_MISMATCH

    try:
        a = Decimal(catalog_number.group(0).replace(",", "."))
        b = Decimal(proposed_number.group(0).replace(",", "."))
    except InvalidOperation:
        return DefectShape.UNPARSED

    # Order matters, and it is not arbitrary. ``125`` against ``12.5`` is *both* a digit
    # permutation and an exact factor of ten, and the two readings point at different upstream
    # bugs: a decimal-point or unit-scaling error, versus a keying error. An exact power of ten is
    # much stronger evidence than a coincidental permutation of the same digits, so it is tested
    # first -- otherwise every decimal-shift defect in a catalog would be clustered as a typing
    # mistake and the fix would be aimed at the wrong process.
    if b and _is_power_of_ten(a / b):
        return DefectShape.ORDER_OF_MAGNITUDE
    if _digits(a) == _digits(b) and a != b:
        return DefectShape.DIGIT_TRANSPOSITION
    return DefectShape.VALUE_SUBSTITUTION


def _unit_tail(text: str, start: int) -> str:
    return text[start:].strip().lower()


def _digits(value: Decimal) -> tuple[str, ...]:
    return tuple(sorted(character for character in str(value) if character.isdigit()))


def _is_power_of_ten(ratio: Decimal) -> bool:
    if ratio <= 0 or ratio == 1:
        return False
    normalized = ratio.normalize()
    text = format(abs(normalized), "e")
    mantissa = text.split("e")[0].rstrip("0").rstrip(".")
    return mantissa in {"1", "1.0"}


@dataclass(frozen=True, slots=True)
class ErrorSignature:
    """What a group of records has in common. **Artifacts and data only** (FR-8.6).

    Every field below is a property of a document, a column, or a value. There is no field for a
    manufacturer, a supplier or a brand, and :func:`assert_no_named_organisation_field` fails the
    build if one is ever added.
    """

    disagreement_class: str
    attribute_uri: str
    defect_shape: str
    source_artifact_sha256: str
    """The **document revision** the finding was grounded in -- a hash of bytes, not a party."""

    column_header: str = ""
    tier: str = ""

    @property
    def fingerprint(self) -> str:
        return "|".join(
            (
                self.disagreement_class,
                self.attribute_uri,
                self.defect_shape,
                self.source_artifact_sha256,
                self.column_header,
                self.tier,
            )
        )

    @property
    def signature_id(self) -> str:
        return str(signature_id(self.fingerprint))

    def sentence(self) -> str:
        return (
            f"{self.defect_shape.replace('_', ' ')} on {self.attribute_uri} "
            f"({self.disagreement_class}), found against document "
            f"{self.source_artifact_sha256[:12] or '(none)'}"
        )


def assert_no_named_organisation_field(schema: type = ErrorSignature) -> None:
    """FR-8.6, enforced on the schema itself.

    Called at import time and asserted again by test. The failure mode this defends against is not
    malice; it is a well-meaning pull request adding ``supplier_id`` because a customer asked which
    of their vendors is worst. The answer has to be no, and the cheapest place to say no is here.
    """
    for field in fields(schema):
        lowered = field.name.lower()
        for banned in BANNED_SIGNATURE_TERMS:
            if banned in lowered:
                raise NamedOrganisationSignatureError(
                    f"{schema.__name__}.{field.name} names an organisation. FR-8.6 prohibits "
                    "organisation-keyed error signatures: signatures key to document and data "
                    "artifacts only. Remove the field; do not redact it at render time."
                )


assert_no_named_organisation_field()


@dataclass(frozen=True, slots=True)
class SignatureCluster:
    """A computed group. ``size`` is ``len(members)`` and nothing else."""

    signature: ErrorSignature
    members: tuple[str, ...]
    """Redline ids, sorted. Enumerable is the point: a cluster nobody can open is an assertion."""

    skus: tuple[str, ...] = ()

    @property
    def size(self) -> int:
        return len(self.members)

    def sentence(self) -> str:
        return f"{self.size:,} record(s) share this pattern: {self.signature.sentence()}"


def signature_for(redline: Redline, *, tier: str = "") -> ErrorSignature:
    """The signature of one finding. Built from a fixed whitelist of inputs.

    Note what is *not* read off the redline: ``sku_id``, ``mpn`` and anything that could carry a
    company name. That is not an oversight the reader should mentally correct -- it is FR-8.6.
    """
    evidence = redline.evidence[0] if redline.evidence else None
    return ErrorSignature(
        disagreement_class=redline.disagreement_class.value,
        attribute_uri=redline.attribute_uri,
        defect_shape=defect_shape(redline.catalog_value, redline.proposed_value),
        source_artifact_sha256=evidence.doc_revision_sha256 if evidence else "",
        column_header=evidence.column_header if evidence else "",
        tier=tier,
    )


def cluster_signatures(
    redlines: Iterable[Redline] | Sequence[Redline],
    *,
    tier_of: dict[str, str] | None = None,
) -> tuple[SignatureCluster, ...]:
    """Group findings by signature and report the size of each group.

    Sorted by size descending, then by fingerprint, so the ordering is reproducible across runs and
    across dict iteration orders (NFR-1).
    """
    tier_of = tier_of or {}
    buckets: dict[str, tuple[ErrorSignature, list[str], list[str]]] = {}
    for redline in redlines:
        signature = signature_for(redline, tier=tier_of.get(str(redline.redline_id), ""))
        entry = buckets.setdefault(signature.fingerprint, (signature, [], []))
        entry[1].append(str(redline.redline_id))
        entry[2].append(redline.sku_id)

    clusters = [
        SignatureCluster(
            signature=signature,
            members=tuple(sorted(members)),
            skus=tuple(sorted(set(skus))),
        )
        for signature, members, skus in buckets.values()
    ]
    return tuple(sorted(clusters, key=lambda c: (-c.size, c.signature.fingerprint)))
