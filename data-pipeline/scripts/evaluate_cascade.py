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

import logging
import math
import sqlite3
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

sys.path.insert(0, str(Path(__file__).parent))
from evaluate_aptness import (
    SCORING_FNS,
    _get_properties,
    _percentile,
    classify_aptness,
    load_apt_pairs,
    load_inapt_controls,
    lookup_primary_synset,
)
from utils import get_git_commit

log = logging.getLogger(__name__)

_VALID_COMPOSITIONS = ("multiplicative", "additive")


CascadeStatus = Literal[
    "scored",                 # cascade ran end-to-end, final_score is populated
    "gate_dropped",           # gate rejected the pair (signed delta < threshold)
    "missing_concreteness",   # one or both sides absent from synset_concreteness
    "no_properties",          # gate passed but no curated properties for scoring
    "unresolved",             # synset_id not found (caller error or DB state issue)
]


@dataclass(frozen=True)
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

    def __post_init__(self) -> None:
        if self.composition not in _VALID_COMPOSITIONS:
            raise ValueError(
                f"composition must be 'multiplicative' or 'additive', "
                f"got {self.composition!r}"
            )
        if self.ortony_scoring not in SCORING_FNS:
            raise ValueError(
                f"ortony_scoring {self.ortony_scoring!r} not in SCORING_FNS; "
                f"valid: {sorted(SCORING_FNS.keys())}"
            )
        if self.d_cap <= 0.0:
            raise ValueError(f"d_cap must be > 0, got {self.d_cap}")
        if self.alpha < 0.0:
            raise ValueError(f"alpha must be >= 0, got {self.alpha}")


@dataclass(frozen=True)
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
    except sqlite3.OperationalError as exc:
        # "no such table: synset_centroids" on fixture DBs / pre-pipeline
        # snapshots is expected fail-open. Anything else (lock, corruption,
        # IO) MUST surface — silently swallowing those would let the cascade
        # produce systematically degraded scores without any signal.
        if "no such table" in str(exc).lower():
            log.debug(
                "synset_centroids table absent (fixture DB?) — fail-open for %s",
                synset_id,
            )
            return None
        log.error(
            "unexpected OperationalError reading centroid for %s: %s",
            synset_id, exc,
        )
        raise
    if row is None or row[0] is None or len(row[0]) == 0:
        return None
    blob = row[0]
    if len(blob) % 4 != 0:
        # Packed float32 BLOBs are always multiples of 4 bytes; anything
        # else is malformed. Fail-open with a WARNING so operators can
        # spot bad rows without taking the cascade offline.
        log.warning(
            "malformed centroid blob for %s: %d bytes (not multiple of 4)",
            synset_id, len(blob),
        )
        return None
    n_floats = len(blob) // 4
    return list(struct.unpack(f"{n_floats}f", blob))


def _cosine_distance(va: list[float], vb: list[float]) -> Optional[float]:
    """Cosine distance ∈ [0, 2]. Returns None if either vector has zero norm
    (cosine is undefined for the zero vector — treat as 'missing centroid').

    Also returns None on dim-mismatch — zip() would silently truncate to the
    shorter vector and produce a meaningless distance, masking a real
    upstream bug (mixed embedding dims, partial migration, etc.).
    """
    if len(va) != len(vb):
        return None
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


# --- Cohort orchestrator -----------------------------------------------------

def _score_cascade_cohort(
    conn: sqlite3.Connection,
    pairs: list[dict],
    word_topic_key: str,
    word_vehicle_key: str,
    cohort_label: str,
    config: CascadeConfig,
) -> dict:
    """Score every pair in a cohort through the cascade.

    Returns a dict with the cohort label, list of scored final_scores,
    per-pair detail rows, and the cascade-specific attrition counters
    (gate_dropped, missing_concreteness, no_properties, unresolved).

    word_topic_key / word_vehicle_key let one helper serve both cohorts:
      * apt cohort  → topic_key='source',  vehicle_key='target'
      * inapt cohort → topic_key='target',  vehicle_key='paraphrase'

    On apt pairs the direction is the Lakoff one. On inapt MUNCH pairs
    there's no inherent direction — the helper simply preserves the
    field order the fixture stores, so an asymmetric gate filters out
    most paraphrase substitutes (which lack the concrete-vehicle shape
    that defines a metaphor pair).
    """
    log.info("scoring cohort %s: %d pairs", cohort_label, len(pairs))
    scores: list[float] = []
    per_pair: list[dict] = []
    counters: dict[str, int] = {
        "unresolved": 0,
        "missing_concreteness": 0,
        "gate_dropped": 0,
        "no_properties": 0,
        "scored": 0,
        # Re-rank attrition (subset of "scored") — track how many scored
        # pairs actually got the cosine re-rank vs fell through fail-open.
        # Without this split we can't tell whether the re-rank stage is
        # genuinely contributing or being silently skipped en masse —
        # which is the silent-fail class the 3948dedf regression hit.
        # The result alone can't tell missing-centroid from zero-norm
        # apart (both surface as re_rank_bonus is None), so collapse to a
        # single skipped bucket — operators chasing low coverage can
        # re-run with debug logging from _centroid/_cosine_distance for
        # the finer split.
        "rerank_applied": 0,
        "rerank_skipped": 0,
    }

    for p in pairs:
        word_topic = p.get(word_topic_key)
        word_vehicle = p.get(word_vehicle_key)
        if not word_topic or not word_vehicle:
            counters["unresolved"] += 1
            per_pair.append({
                "class": cohort_label,
                "word_topic": word_topic,
                "word_vehicle": word_vehicle,
                "status": "unresolved",
                "score": None,
            })
            continue
        sid_topic = lookup_primary_synset(conn, word_topic)
        sid_vehicle = lookup_primary_synset(conn, word_vehicle)
        if sid_topic is None or sid_vehicle is None:
            counters["unresolved"] += 1
            per_pair.append({
                "class": cohort_label,
                "word_topic": word_topic,
                "word_vehicle": word_vehicle,
                "status": "unresolved",
                "score": None,
            })
            continue

        result = evaluate_cascade_pair(conn, sid_topic, sid_vehicle, config)
        counters[result.status] = counters.get(result.status, 0) + 1
        row = {
            "class": cohort_label,
            "word_topic": word_topic,
            "word_vehicle": word_vehicle,
            "synset_topic": sid_topic,
            "synset_vehicle": sid_vehicle,
            "status": result.status,
            "score": round(result.final_score, 6) if result.final_score is not None else None,
            "gate_passed": result.gate_passed,
            "ortony_score": round(result.ortony_score, 6) if result.ortony_score is not None else None,
            "cosine_distance": round(result.cosine_distance, 6) if result.cosine_distance is not None else None,
            "re_rank_bonus": round(result.re_rank_bonus, 6) if result.re_rank_bonus is not None else None,
        }
        per_pair.append(row)

        # Scoring policy: pairs the gate dropped contribute 0.0 to the
        # cohort mean (they're explicitly judged "not metaphorical").
        # missing_concreteness / no_properties / unresolved do NOT
        # contribute — they're attrition, not scored zeros, so they
        # cannot deflate the mean.
        if result.status == "scored":
            scores.append(result.final_score)  # type: ignore[arg-type]
            if result.re_rank_bonus is not None:
                counters["rerank_applied"] += 1
            else:
                counters["rerank_skipped"] += 1
        elif result.status == "gate_dropped":
            scores.append(0.0)

    if counters["scored"] > 0:
        applied_rate = counters["rerank_applied"] / counters["scored"]
        if applied_rate < 0.05:
            log.warning(
                "cohort %s: only %d/%d scored pairs got the re-rank "
                "(%.1f%%) — check synset_centroids coverage",
                cohort_label, counters["rerank_applied"],
                counters["scored"], applied_rate * 100,
            )
    log.info("cohort %s done: %s", cohort_label, counters)
    return {
        "cohort": cohort_label,
        "scores": scores,
        "per_pair": per_pair,
        "counters": counters,
    }


def evaluate_cohort(
    conn: sqlite3.Connection,
    pairs_file: str,
    controls_file: str,
    config: CascadeConfig,
    threshold_percentile: float = 95.0,
    db_path: str | None = None,
) -> dict:
    """Run the cascade on an apt+inapt cohort and return a sweep-compatible
    result dict.

    Shape parity with ``evaluate_aptness.evaluate``:
      * aptness_rate, false_positive_rate, separation_score at top level
      * aggregate dict with mean_apt_score, mean_inapt_score, n_apt,
        n_inapt — plus cascade-specific attrition counters
      * per_pair_scores list with both cohorts
      * config block with cascade hyperparameters

    The aggregate-level attrition counters are namespaced by cohort
    (`apt_gate_dropped`, `inapt_gate_dropped`, etc.) so the sweep
    harness can render ablation slices without re-walking the per-pair
    list.
    """
    apt_pairs = load_apt_pairs(pairs_file)
    inapt_controls = load_inapt_controls(controls_file)

    apt = _score_cascade_cohort(
        conn, apt_pairs, "source", "target", "apt", config,
    )
    inapt = _score_cascade_cohort(
        conn, inapt_controls, "target", "paraphrase", "inapt", config,
    )

    apt_scores = apt["scores"]
    inapt_scores = inapt["scores"]

    threshold = _percentile(inapt_scores, threshold_percentile)
    classification = classify_aptness(apt_scores, inapt_scores, threshold)

    mean_apt = sum(apt_scores) / len(apt_scores) if apt_scores else 0.0
    mean_inapt = sum(inapt_scores) / len(inapt_scores) if inapt_scores else 0.0

    aggregate = {
        "mean_apt_score": round(mean_apt, 6),
        "mean_inapt_score": round(mean_inapt, 6),
        "separation_score": round(mean_apt - mean_inapt, 6),
        "n_apt": len(apt_scores),
        "n_inapt": len(inapt_scores),
    }
    # Namespace the attrition counters by cohort so the aggregate-level
    # dict carries everything the sweep harness's ablation table needs
    # without forcing per-pair walks.
    for status, count in apt["counters"].items():
        aggregate[f"apt_{status}"] = count
    for status, count in inapt["counters"].items():
        aggregate[f"inapt_{status}"] = count

    return {
        "aptness_rate": round(classification["aptness_rate"], 6),
        "false_positive_rate": round(classification["false_positive_rate"], 6),
        "separation_score": aggregate["separation_score"],
        "aggregate": aggregate,
        "per_pair_scores": apt["per_pair"] + inapt["per_pair"],
        "config": {
            "evaluator": "cascade",
            "concreteness_threshold": config.concreteness_threshold,
            "ortony_scoring": config.ortony_scoring,
            "d_cap": config.d_cap,
            "alpha": config.alpha,
            "composition": config.composition,
            "threshold": round(threshold, 6),
            "threshold_percentile": threshold_percentile,
            "pairs_file": pairs_file,
            "controls_file": controls_file,
            "db": db_path,
            "git_commit": get_git_commit(),
        },
    }
