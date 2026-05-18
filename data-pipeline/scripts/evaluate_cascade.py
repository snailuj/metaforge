"""M03 cascade evaluator — concreteness gate → Ortony rank → domain-distance re-rank.

This is the architectural shift from M02's pointwise SCORING_FNS family
to a composed cascade. S01 shipped the scaffolding + concreteness gate;
S02 adds the domain-distance re-rank stage (monotonic-up-to-cap reward
shape, fail-open on missing centroids).

Pre-flight findings ([`M03-S01-preflight-findings.md`](docs/roadmap/...))
established:
  * The gate is signed — `concreteness(vehicle) − concreteness(topic) ≥
    threshold` — not absolute. Apt-cohort signed delta has mean +1.81
    on the M02 baseline DB while inapt sits at +0.08, so directionality
    is the entire signal.
  * Missing concreteness fails closed: the gate cannot make a Lakoff-#1
    judgement without both scores, and silently passing such pairs
    would mask cohort coverage gaps.
  * The post-gate Ortony scorer is honoured from M02's existing
    SCORING_FNS registry — the cascade reuses pointwise primitives,
    it doesn't replace them.

The CascadeResult contract carries the diagnostic fields the sweep
harness needs to surface ablation slices in one run: gate_passed,
ortony_score, cosine_distance, re_rank_bonus, plus a typed status
distinguishing gate_dropped from missing_concreteness from
no_properties from unresolved.
"""
from __future__ import annotations

import math
import sqlite3
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

sys.path.insert(0, str(Path(__file__).parent))
from evaluate_aptness import SCORING_FNS, _get_properties

_VALID_COMPOSITIONS = ("multiplicative", "additive")


CascadeStatus = Literal[
    "scored",                 # cascade ran end-to-end, final_score is populated
    "gate_dropped",           # gate rejected the pair (signed delta < threshold)
    "missing_concreteness",   # one or both sides absent from synset_concreteness
    "no_properties",          # gate passed but no curated properties for scoring
    "unresolved",             # synset_id not found (caller error or DB state issue)
]


@dataclass
class CascadeConfig:
    """Hyperparameters for the cascade evaluator.

    Defaults align with the M03 pre-flight findings (apt-cohort signed
    concreteness delta median +2.03, so threshold=1.0 sits comfortably
    on the discriminative slope). The S01 slice does not exercise the
    re-rank stage; ``d_cap``/``alpha``/``composition`` are present in
    the contract so callers can reach for them in S02 without a
    signature change.
    """
    concreteness_threshold: float = 1.0
    ortony_scoring: str = "jaccard_salience"
    # --- S02 fields (not yet exercised in S01) -------------------------------
    d_cap: float = 0.77
    alpha: float = 0.5
    composition: Literal["multiplicative", "additive"] = "multiplicative"


@dataclass
class CascadeResult:
    """Output of one cascade evaluation.

    ``final_score`` is the scalar fed to the harness — 0.0 for
    gate-dropped pairs (so they land in the bottom bucket without
    breaking the score aggregation), None for un-scorable pairs
    (so the harness can route them to the right attrition counter).

    The diagnostic fields (gate_passed / ortony_score / cosine_distance
    / re_rank_bonus) let the sweep harness compute ablation slices
    from a single run.
    """
    final_score: Optional[float]
    gate_passed: bool
    ortony_score: Optional[float]
    cosine_distance: Optional[float]   # populated in S02
    re_rank_bonus: Optional[float]     # populated in S02
    status: CascadeStatus


# --- Concreteness lookup -----------------------------------------------------

def _concreteness(conn: sqlite3.Connection, synset_id: str) -> Optional[float]:
    """Return concreteness score for a synset, or None if absent."""
    row = conn.execute(
        "SELECT score FROM synset_concreteness WHERE synset_id = ?",
        (synset_id,),
    ).fetchone()
    return float(row[0]) if row else None


# --- Centroid lookup + cosine distance ---------------------------------------

def _centroid(conn: sqlite3.Connection, synset_id: str) -> Optional[list[float]]:
    """Return the centroid vector for a synset, or None if absent.

    synset_centroids.centroid is a packed float32 BLOB (300 floats in
    the real DB, sized by FastText embedding dim). Test fixtures use a
    smaller dim; the decode handles either by reading the BLOB length.

    Returns None on any of: row missing, BLOB NULL, BLOB empty, OR
    synset_centroids table absent entirely. The last case happens on
    pre-M03 DB snapshots / fixture DBs that pre-date the centroid
    pipeline — the cascade must remain usable on those by failing open
    through the re-rank rather than crashing on `no such table`.
    """
    try:
        row = conn.execute(
            "SELECT centroid FROM synset_centroids WHERE synset_id = ?",
            (synset_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        # Likely "no such table: synset_centroids" on a fixture DB or
        # pre-pipeline snapshot. Fail open.
        return None
    if row is None or row[0] is None or len(row[0]) == 0:
        return None
    blob = row[0]
    n_floats = len(blob) // 4
    return list(struct.unpack(f"{n_floats}f", blob))


def _cosine_distance(va: list[float], vb: list[float]) -> Optional[float]:
    """Cosine distance ∈ [0, 2]. Returns None if either vector has zero norm
    (cosine is undefined for the zero vector — treat as 'missing centroid').
    """
    dot = sum(a * b for a, b in zip(va, vb))
    na = math.sqrt(sum(a * a for a in va))
    nb = math.sqrt(sum(b * b for b in vb))
    if na == 0.0 or nb == 0.0:
        return None
    return 1.0 - (dot / (na * nb))


def _re_rank_bonus(d: float, d_cap: float) -> float:
    """Monotonic-up-to-cap reward shape.

    bonus = clip(d / d_cap, 0.0, 1.0). Distances above d_cap saturate
    at 1.0; distances ≤ 0 yield 0. The triangular-around-intermediate
    shape from the initial roadmap draft was discarded after pre-flight
    showed the inapt MUNCH cohort doesn't sample the too-far arm at all.
    """
    if d_cap <= 0.0:
        return 0.0
    ratio = d / d_cap
    if ratio < 0.0:
        return 0.0
    if ratio > 1.0:
        return 1.0
    return ratio


# --- Main evaluator ----------------------------------------------------------

def evaluate_cascade_pair(
    conn: sqlite3.Connection,
    synset_id_topic: str,
    synset_id_vehicle: str,
    config: CascadeConfig,
) -> CascadeResult:
    """Run the cascade on one (topic, vehicle) pair.

    Returns a CascadeResult with status routing the caller to one of:
      * scored — full path through gate + Ortony scorer
      * gate_dropped — signed delta below threshold; final_score = 0.0
      * missing_concreteness — one or both sides absent from the
        synset_concreteness table; final_score = None
      * no_properties — gate passed but no curated properties on one or
        both sides; final_score = None
      * unresolved — synset_id not found (this is a caller-side error;
        callers should resolve lemmas to synset_ids upstream and check
        for None there, but the cascade still handles the case
        defensively rather than crashing)

    The function never raises on data-shape issues — only on caller
    contract violations (e.g. an unknown ortony_scoring name, which
    matches the fail-fast contract evaluate_aptness.evaluate uses).
    """
    # Validate ortony scoring fn up front so a sweep config typo crashes
    # immediately rather than after every batch of cohort work.
    if config.ortony_scoring not in SCORING_FNS:
        known = ", ".join(sorted(SCORING_FNS))
        raise ValueError(
            f"Unknown ortony_scoring: {config.ortony_scoring!r}. "
            f"Registered in SCORING_FNS: {known}"
        )
    if config.composition not in _VALID_COMPOSITIONS:
        raise ValueError(
            f"Unknown composition: {config.composition!r}. "
            f"Valid: {', '.join(_VALID_COMPOSITIONS)}"
        )

    # --- Stage 1: concreteness gate ------------------------------------------
    c_topic = _concreteness(conn, synset_id_topic)
    c_vehicle = _concreteness(conn, synset_id_vehicle)
    if c_topic is None or c_vehicle is None:
        return CascadeResult(
            final_score=None,
            gate_passed=False,
            ortony_score=None,
            cosine_distance=None,
            re_rank_bonus=None,
            status="missing_concreteness",
        )

    signed_delta = c_vehicle - c_topic
    if signed_delta < config.concreteness_threshold:
        return CascadeResult(
            final_score=0.0,
            gate_passed=False,
            ortony_score=None,
            cosine_distance=None,
            re_rank_bonus=None,
            status="gate_dropped",
        )

    # --- Stage 2: Ortony rank ------------------------------------------------
    pa = _get_properties(conn, synset_id_topic)
    pb = _get_properties(conn, synset_id_vehicle)
    if not pa or not pb:
        return CascadeResult(
            final_score=None,
            gate_passed=True,
            ortony_score=None,
            cosine_distance=None,
            re_rank_bonus=None,
            status="no_properties",
        )

    scoring_fn = SCORING_FNS[config.ortony_scoring]
    ortony_score = scoring_fn(pa, pb)

    # --- Stage 3: domain-distance re-rank (S02) ------------------------------
    # Fail-open: if either centroid is missing OR has zero norm, the re-rank
    # stage skips entirely and the final_score falls back to the Ortony
    # score. cosine_distance / re_rank_bonus stay None so the harness can
    # route these pairs into a missing-centroid ablation bucket.
    va = _centroid(conn, synset_id_topic)
    vb = _centroid(conn, synset_id_vehicle)
    cosine_distance: Optional[float] = None
    re_rank_bonus: Optional[float] = None
    if va is not None and vb is not None:
        d = _cosine_distance(va, vb)
        if d is not None:
            cosine_distance = d
            re_rank_bonus = _re_rank_bonus(d, config.d_cap)

    if re_rank_bonus is None:
        final_score = ortony_score
    elif config.composition == "multiplicative":
        final_score = ortony_score * (1.0 + config.alpha * re_rank_bonus)
    else:  # "additive" — validated above
        final_score = ortony_score + config.alpha * re_rank_bonus

    return CascadeResult(
        final_score=final_score,
        gate_passed=True,
        ortony_score=ortony_score,
        cosine_distance=cosine_distance,
        re_rank_bonus=re_rank_bonus,
        status="scored",
    )
