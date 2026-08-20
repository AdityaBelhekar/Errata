"""FR-8.4 -- the triage router: rank by expected review value, and show the working.

    "Ranking by expected review value = P(catalog wrong) x blast radius (revenue weight x safety
    multiplier x propagation count x record multiplicity). Ranking is reproducible and each factor
    is independently inspectable in the UI."

A ranked queue is the product's actual deliverable. A customer with 40,000 records and two people
does not buy "we found 6,100 problems"; they buy "start at the top, and you may stop whenever you
like". That promise is only worth something if the order is defensible, and an order is defensible
only when the reviewer can take it apart.

So this module does two things and refuses a third.

**It multiplies the factors.** Nothing clever: the formula is the one the PRD states, and it is
computed rather than tuned. Where a factor is unknown the router says the factor is unknown instead
of substituting a plausible-looking number -- ``revenue_weight`` is 1.0 until a customer supplies
revenue, and the entry says "not supplied" rather than showing a 1.0 that reads like a measurement.

**It keeps every factor separately.** :class:`Factor` carries the value *and the sentence that
explains where it came from*, so the UI requirement "independently inspectable" is satisfied by the
data structure rather than by a screen that may or may not get built. A reviewer who disagrees with
a ranking can see which term they disagree with.

**It refuses to blend in a tuned weight.** There is no learned ranker and no hand-set boost. The
safety multiplier is a declared constant with its own docstring in
:mod:`errata_comparator.redline`, and the record multiplicity comes from a computed cluster
(FR-8.5). Every number in the product of terms is traceable to a stated source, which is the only
way the ranking survives the first customer who asks why row 400 is above row 12.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from errata_spec import BlastRadius, Redline, is_safety_class

from .signatures import SignatureCluster

__all__ = [
    "Factor",
    "QueueEntry",
    "TriageResult",
    "route",
]


@dataclass(frozen=True, slots=True)
class Factor:
    """One term of the expected-review-value product, with its provenance in words."""

    name: str
    value: float
    provenance: str
    measured: bool
    """False when the value is a stated default rather than a measurement. Rendered differently,
    on purpose: a default that looks like a measurement is the quiet way a ranking becomes a
    fiction."""

    def sentence(self) -> str:
        suffix = "" if self.measured else "  (not supplied -- stated default)"
        return f"{self.name} = {self.value:g}{suffix}: {self.provenance}"


@dataclass(frozen=True, slots=True)
class QueueEntry:
    """One row of the reviewer queue."""

    redline: Redline
    tier: str
    signature_id: str
    cluster_size: int
    factors: tuple[Factor, ...]

    @property
    def redline_id(self) -> str:
        return str(self.redline.redline_id)

    @property
    def expected_review_value(self) -> float:
        return self.redline.expected_review_value

    @property
    def requires_two_signatures(self) -> bool:
        return self.redline.requires_two_signatures

    def sentence(self) -> str:
        """FR-7.5: a queue row reads as a sentence, never as a bare confidence percentage.

        R2 renders its own rather than reusing :meth:`errata_spec.Redline.queue_sentence` for one
        reason: a structural finding may have no proposed value (the class declares the catalog's
        value unsupported without knowing what the right one is), and "the evidence says ''" is not
        a sentence a reviewer should ever be shown.
        """
        redline = self.redline
        head = (
            f"SEV-{int(redline.severity)} - {redline.sku_id} - "
            f"{redline.attribute_label or redline.attribute_uri}"
        )
        if redline.proposed_value:
            body = (
                f"Catalog says {redline.catalog_value!r}. The evidence says "
                f"{redline.proposed_value!r}."
            )
        elif redline.catalog_value:
            body = (
                f"Catalog says {redline.catalog_value!r}, and nothing in the evidence supports it."
            )
        else:
            body = (
                f"Catalog is blank, and the evidence states {redline.proposed_value!r}."
                if redline.proposed_value
                else "Catalog is blank."
            )
        lines = [head, body]
        if self.cluster_size > 1:
            lines.append(f"{self.cluster_size:,} record(s) share this error signature.")
        lines.extend(
            line
            for line in redline.blast_radius.explain()
            if not line.endswith("share this error signature")
        )
        if self.requires_two_signatures:
            lines.append("Safety class: acceptance needs a second named adjudicator.")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, object]:
        redline = self.redline
        return {
            "redline_id": self.redline_id,
            "tier": self.tier,
            "sku_id": redline.sku_id,
            "attribute_uri": redline.attribute_uri,
            "attribute_label": redline.attribute_label,
            "severity": int(redline.severity),
            "disagreement_class": redline.disagreement_class.value,
            "catalog_value": redline.catalog_value,
            "proposed_value": redline.proposed_value,
            "probability_catalog_wrong": redline.probability_catalog_wrong,
            "expected_review_value": round(self.expected_review_value, 6),
            "signature_id": self.signature_id,
            "cluster_size": self.cluster_size,
            "requires_two_signatures": self.requires_two_signatures,
            "factors": [
                {
                    "name": factor.name,
                    "value": factor.value,
                    "measured": factor.measured,
                    "provenance": factor.provenance,
                }
                for factor in self.factors
            ],
            "evidence": [
                {
                    "doc_id": evidence.doc_id,
                    "doc_revision_sha256": evidence.doc_revision_sha256,
                    "page": evidence.page,
                    "char_span": list(evidence.char_span),
                    "snippet": evidence.snippet,
                    "column_header": evidence.column_header,
                    "row_header": evidence.row_header,
                }
                for evidence in redline.evidence
            ],
            "counter_evidence": redline.counter_evidence.summary,
            "rationale": redline.rationale,
        }


@dataclass(frozen=True, slots=True)
class TriageResult:
    """The ranked queue, plus the clusters that shaped it."""

    entries: tuple[QueueEntry, ...]
    clusters: tuple[SignatureCluster, ...]

    def __len__(self) -> int:
        return len(self.entries)

    def top(self, count: int = 10) -> tuple[QueueEntry, ...]:
        return self.entries[:count]

    def by_severity(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for entry in self.entries:
            key = int(entry.redline.severity)
            out[key] = out.get(key, 0) + 1
        return dict(sorted(out.items()))

    def safety_entries(self) -> tuple[QueueEntry, ...]:
        return tuple(entry for entry in self.entries if entry.requires_two_signatures)


def route(
    redlines: Sequence[Redline],
    clusters: Sequence[SignatureCluster],
    *,
    tier_of: dict[str, str] | None = None,
    propagation: dict[str, int] | None = None,
    revenue_weight: dict[str, float] | None = None,
) -> TriageResult:
    """Rank findings by expected review value, with the cluster sizes folded in.

    The blast radius is *recomputed* here rather than trusted from the audit, because
    ``record_multiplicity`` is not knowable one record at a time -- it is exactly the term that
    requires the whole catalog to have been seen, which is why R1 left it at 1 and R2 is where it
    becomes real.

    The recomputed redline is re-validated rather than copied: ``model_copy(update=...)`` skips
    pydantic's validators, and ``Redline`` is where the rules that keep semantic equivalence out of
    a queue live.
    """
    tier_of = tier_of or {}
    propagation = propagation or {}
    revenue_weight = revenue_weight or {}

    size_by_redline: dict[str, tuple[str, int]] = {}
    for cluster in clusters:
        for member in cluster.members:
            size_by_redline[member] = (cluster.signature.signature_id, cluster.size)

    entries: list[QueueEntry] = []
    for redline in redlines:
        key = str(redline.redline_id)
        signature, size = size_by_redline.get(key, ("", 1))
        attribute_key = redline.attribute_uri.rsplit(":", 1)[-1]
        safety = is_safety_class(redline.attribute_uri) or is_safety_class(redline.attribute_label)

        radius = BlastRadius(
            revenue_weight=revenue_weight.get(redline.sku_id, 1.0),
            safety_class_multiplier=redline.blast_radius.safety_class_multiplier,
            propagation_count=propagation.get(attribute_key, 0),
            record_multiplicity=max(1, size),
        )
        ranked = Redline.model_validate(
            redline.model_copy(update={"blast_radius": radius}).model_dump()
        )

        probability = ranked.probability_catalog_wrong
        entries.append(
            QueueEntry(
                redline=ranked,
                tier=tier_of.get(key, ""),
                signature_id=signature,
                cluster_size=max(1, size),
                factors=(
                    Factor(
                        name="P(catalog wrong)",
                        value=probability if probability is not None else 0.5,
                        provenance=(
                            "calibrated probability from the fitted calibration set"
                            if probability is not None
                            else (
                                "no calibration set exists (FR-6.1 is unmet), so this finding is "
                                "ranked at the neutral 0.5 and is not promoted above a calibrated "
                                "one on the strength of a number nobody can check"
                            )
                        ),
                        measured=probability is not None,
                    ),
                    Factor(
                        name="revenue weight",
                        value=radius.revenue_weight,
                        provenance=(
                            "supplied by the customer for this SKU"
                            if redline.sku_id in revenue_weight
                            else "no revenue data was supplied to this run"
                        ),
                        measured=redline.sku_id in revenue_weight,
                    ),
                    Factor(
                        name="safety multiplier",
                        value=radius.safety_class_multiplier,
                        provenance=(
                            "the attribute is on errata_spec.SAFETY_CLASS_ATTRIBUTES; the "
                            "multiplier is a declared constant, not a tuned weight"
                            if safety
                            else "the attribute is not on the safety-class list"
                        ),
                        measured=True,
                    ),
                    Factor(
                        name="propagation count",
                        value=float(radius.propagation_count),
                        provenance=(
                            "downstream surfaces this attribute feeds, as configured"
                            if radius.propagation_count
                            else (
                                "no downstream-surface map was supplied; the term is held at zero "
                                "and contributes 1 to the product rather than an invented count"
                            )
                        ),
                        measured=bool(radius.propagation_count),
                    ),
                    Factor(
                        name="record multiplicity",
                        value=float(radius.record_multiplicity),
                        provenance=(
                            f"computed: {radius.record_multiplicity} finding(s) share error "
                            f"signature {signature[:8] or '(none)'} (FR-8.5, counted not asserted)"
                        ),
                        measured=True,
                    ),
                ),
            )
        )

    entries.sort(key=lambda entry: (-entry.expected_review_value, entry.redline_id))
    return TriageResult(entries=tuple(entries), clusters=tuple(clusters))
