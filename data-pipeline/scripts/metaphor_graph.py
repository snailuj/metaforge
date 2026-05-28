"""Metaphor graph schema, path hashing, snap, insert, judgment, view helpers.

Implements the bridge-centric metaphor graph layer specified in
docs/superpowers/specs/2026-05-28-metaphor-graph-schema-design.md.

Public surface:
    compute_path_hash(step_synset_ids)        -> str        # idempotency hash
    apply_schema(conn)                        -> None       # creates tables + view
    snap_concept_string(conn, text)           -> str | None # exact + morphological
    insert_bridge(conn, ...)                  -> int        # returns bridge_id
    record_judgment(conn, ...)                -> int        # returns judgment_id
"""
from __future__ import annotations

import hashlib


def compute_path_hash(step_synset_ids: list[str]) -> str:
    """Order-preserving sha256 over the bridge's intermediate node IDs.

    Used as the idempotency key alongside (topic, vehicle, proposer): re-running
    a proposer with the same bridge does not create a duplicate row.

    Raises ValueError if the path is empty — every bridge must have at least
    one intermediate, per the spec.
    """
    if not step_synset_ids:
        raise ValueError("path_hash: empty path — every bridge needs >=1 intermediate")
    joined = "|".join(step_synset_ids)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
