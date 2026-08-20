"""Content-addressed identity for everything R2 creates.

R1 learned this the expensive way (finding N14): a redline with a random id meant the adjudication
command the CLI printed stopped working after a re-run, and "has this been decided?" became
unanswerable. Ids are therefore derived from content, never from a clock or a counter, and the
namespaces are fixed constants written down here rather than generated -- a namespace that moved
would silently change the identity of every object in the ledger.

R2 adds one identity R1 did not need: the **batch**. FR-8.8 requires any audit batch's accepted
redlines to revert from the ledger *as a query*, which means a batch has to be nameable before it
is finished and re-nameable identically when the same run happens again. So a batch id is a hash
of what the run *is* -- the feed's bytes, the policy, the attribute map, the code versions -- and
not of when it started. Two identical runs produce one batch, which is correct: they found the
same things about the same file.
"""

from __future__ import annotations

import uuid

__all__ = [
    "BATCH_NAMESPACE",
    "SIGNATURE_NAMESPACE",
    "STRUCTURAL_REDLINE_NAMESPACE",
    "batch_id",
    "signature_id",
    "structural_redline_id",
]

#: Fixed namespaces. Generated once, written down, never regenerated.
STRUCTURAL_REDLINE_NAMESPACE = uuid.UUID("b6c4e2a1-7f38-5d90-a1b2-c3d4e5f60718")
BATCH_NAMESPACE = uuid.UUID("2d9f6e01-4a5b-5c6d-8e7f-90a1b2c3d4e5")
SIGNATURE_NAMESPACE = uuid.UUID("7a1c3e5d-2b4f-5068-9a7b-1c2d3e4f5061")


def structural_redline_id(
    *,
    feed_sha256: str,
    sku_id: str,
    attribute_uri: str,
    catalog_value: str,
    proposed_value: str,
) -> uuid.UUID:
    """The identity of a T0 finding.

    Deliberately a *different* namespace from :func:`errata_audit.stable_redline_id`. A structural
    finding and a grounded finding about the same cell are different claims resting on different
    evidence -- one on the feed's own rows, one on a manufacturer's document -- and collapsing them
    into one id would let the weaker one inherit the stronger one's adjudication.
    """
    key = "|".join((feed_sha256, sku_id, attribute_uri, catalog_value, proposed_value))
    return uuid.uuid5(STRUCTURAL_REDLINE_NAMESPACE, key)


def batch_id(
    *,
    feed_sha256: str,
    policy_version: str,
    attribute_map_version: str,
    code_versions: tuple[str, ...] = (),
    label: str = "",
) -> uuid.UUID:
    """The identity of one audit batch (FR-8.8).

    ``label`` exists for the case a customer genuinely wants two batches over the same inputs --
    a re-run after a policy discussion, say. It is part of the key, so naming it is how you get a
    second batch, and *not* naming it is how you get idempotence.
    """
    key = "|".join(
        (feed_sha256, policy_version, attribute_map_version, "+".join(code_versions), label)
    )
    return uuid.uuid5(BATCH_NAMESPACE, key)


def signature_id(fingerprint: str) -> uuid.UUID:
    """The identity of an error signature, from its own fingerprint string (FR-8.5)."""
    return uuid.uuid5(SIGNATURE_NAMESPACE, fingerprint)
