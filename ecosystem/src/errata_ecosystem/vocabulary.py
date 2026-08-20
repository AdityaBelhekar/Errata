"""One attribute, one identity -- the N15 fix, and the guard that keeps it fixed.

R2 raised finding N15: ``build_redline`` wrote ``rated_current`` into ``attribute_uri`` while
``stable_redline_id`` derived the id of the same finding from ``etim:EF000227``. One attribute,
two vocabularies, in adjacent lines of one object. Nothing noticed until R2 started clustering
across both, and then it showed up as two error signatures where there was one error.

R3 fixes it at the source -- :class:`errata_comparator.AttributeSpec` now carries the uri and
every redline is built from it -- and this module is what the rest of the ecosystem resolves
names through, because a bridge between two dictionaries is exactly where a second vocabulary
would creep back in.

**What the fix moved, measured rather than asserted** (``docs/R3-report.md`` §2):

* **Redline ids did not move.** Both id functions already hashed the uri. The ledger row recorded
  in R1 for ``S201M-B16UC`` / rated current still names the finding the current build produces,
  and ``test_vocabulary.py`` pins that id so a future change to the scheme cannot silently orphan
  a recorded adjudication.
* **Error-signature fingerprints did move**, because a fingerprint contains the attribute's name.
  No adjudication keys on a fingerprint -- clusters are computed, decisions are recorded against
  redline ids -- so this costs a recomputation and nothing else.
* **Ledger rows written before the fix carry the bare key.** :func:`canonical_uri` resolves those
  too, which is why reading history still works.
"""

from __future__ import annotations

from functools import lru_cache

from errata_audit import load_attributes

__all__ = [
    "CUSTOMER_SCHEME",
    "ETIM_SCHEME",
    "SCHEMES",
    "UnknownAttributeTerm",
    "canonical_uri",
    "is_canonical",
    "local_key",
    "scheme_of",
    "vocabulary_violations",
]

ETIM_SCHEME = "etim"
CUSTOMER_SCHEME = "customer"
SCHEMES = (ETIM_SCHEME, CUSTOMER_SCHEME)


class UnknownAttributeTerm(ValueError):
    """Raised when a term cannot be resolved and the caller asked for strictness.

    Guessing is the failure mode this whole module exists to prevent: an unresolved term silently
    becoming ``customer:<whatever-was-typed>`` is how a typo acquires an identity and starts
    collecting adjudications of its own.
    """


@lru_cache(maxsize=1)
def _alias_map() -> dict[str, str]:
    """Every term the R1 attribute map knows, mapped to the canonical uri.

    Built from ``config/attributes.yaml`` rather than written out here, so an attribute added to
    the map is bridgeable the same day and cannot be added in one place and forgotten in another.
    """
    aliases: dict[str, str] = {}
    for attribute in load_attributes():
        uri = attribute.uri
        aliases[attribute.key.lower()] = uri
        aliases[uri.lower()] = uri
        aliases[attribute.label.lower()] = uri
        for alias in attribute.aliases:
            # A published artifact's own name for this attribute -- see AuditAttribute.aliases.
            # Registered here rather than special-cased at each call site, because the whole point
            # of N15's fix is that there is exactly one place a name becomes an identity.
            aliases[alias.lower()] = uri
        if attribute.etim_feature:
            aliases[attribute.etim_feature.lower()] = uri
    return aliases


def canonical_uri(term: str, *, strict: bool = False) -> str:
    """The one identity for ``term``: ``rated_current``, ``EF000227`` and ``Rated current`` agree.

    A term with no entry in the map resolves to ``customer:<term>`` -- honestly local rather than
    wrongly interoperable -- unless ``strict`` is set, which is the right choice when the caller
    is a bridge or a benchmark axis and a silent local id would be scored as a real answer.
    """
    text = term.strip()
    if not text:
        raise UnknownAttributeTerm("an empty string is not an attribute")

    hit = _alias_map().get(text.lower())
    if hit is not None:
        return hit

    if ":" in text:
        scheme, _, rest = text.partition(":")
        if scheme.lower() in SCHEMES and rest:
            return f"{scheme.lower()}:{rest}"

    if strict:
        raise UnknownAttributeTerm(
            f"{term!r} is not in the attribute map and carries no known scheme; "
            "add it to errata_audit config/attributes.yaml rather than inventing an id for it"
        )
    return f"{CUSTOMER_SCHEME}:{text}"


def scheme_of(uri: str) -> str:
    scheme, sep, _ = uri.partition(":")
    return scheme if sep else ""


def local_key(uri: str) -> str:
    """``etim:EF000227`` -> ``EF000227``; a bare key is returned unchanged."""
    _, sep, rest = uri.partition(":")
    return rest if sep else uri


def is_canonical(uri: str) -> bool:
    return scheme_of(uri) in SCHEMES and bool(local_key(uri))


def vocabulary_violations(redlines) -> tuple[str, ...]:
    """Every redline whose ``attribute_uri`` is not a canonical uri -- N15's regression guard.

    Returns sentences rather than booleans so a failure names the offender. Called by the R3 test
    suite over both R1 and R2 output; a new code path that materialises a redline from a bare key
    fails there rather than being discovered by a clustering report months later.
    """
    bad: list[str] = []
    for redline in redlines:
        uri = getattr(redline, "attribute_uri", "")
        if not is_canonical(uri):
            bad.append(
                f"{getattr(redline, 'sku_id', '?')}: attribute_uri {uri!r} carries no scheme "
                f"(expected one of {SCHEMES}) -- finding N15"
            )
    return tuple(bad)
