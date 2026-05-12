"""Discriminative aptness evaluator for Metaforge metaphor pairings.

Scores (target, vehicle) pairs as apt or inapt by measuring property
overlap in the curated vocabulary. Calibrates the classification
threshold against the MUNCH inapt control distribution (95th
percentile by default) and reports:

  * separation_score   = mean(apt) − mean(inapt)
  * aptness_rate       = fraction of apt pairs scoring above threshold
  * per_pair_scores    = full per-pair detail (class, score, resolved)
  * aggregate          = means + sample sizes
  * config             = thresholds + scoring name + commit + db path

Scoring is pluggable via the ``SCORING_FNS`` registry. Each scoring
function takes two ``{cluster_id: salience_sum}`` mappings and returns
a float in [0.0, 1.0]. Registered formulas:

  * ``jaccard_salience`` (default) — salience-weighted Jaccard. Favours
    pairs that share *salient* property clusters over pairs that merely
    co-occur via low-salience filler properties.
  * ``jaccard_raw`` — unweighted set-Jaccard over shared cluster_ids.
    Acts as a control for whether salience weighting helps.
  * ``cosine_salience`` — cosine similarity over salience vectors,
    aligned by cluster_id. Cluster_ids missing from one side are
    zero-padded (standard sparse-cosine convention).
  * ``random_uniform`` — deterministic pseudo-random null-control.
    blake2b hash of the sorted union of cluster_ids in pa∪pb mapped
    to [0, 1). Carries no semantic signal by construction — used as
    a null reference for sweep sensitivity validation: any apt/inapt
    structure should yield separation_score ≈ 0 under this scoring.

Conventions: registry keys are lowercase snake_case. Add new scoring
formulas by inserting into ``SCORING_FNS`` — the CLI ``--scoring``
flag accepts any registered name.

Usage:
    python evaluate_aptness.py \\
        --pairs    data-pipeline/fixtures/metaphor_pairs_v2.json \\
        --controls data-pipeline/fixtures/munch_inapt.jsonl \\
        --db       data-pipeline/output/lexicon_v2.db \\
        --scoring  jaccard_salience \\
        --output   data-pipeline/output/aptness_eval.json
"""
import argparse
import hashlib
import json
import logging
import math
import sqlite3
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

sys.path.insert(0, str(Path(__file__).parent))
from utils import LEXICON_V2, get_git_commit

log = logging.getLogger(__name__)

PIPELINE_DIR = Path(__file__).parent.parent
FIXTURES_DIR = PIPELINE_DIR / "fixtures"
DEFAULT_PAIRS = FIXTURES_DIR / "metaphor_pairs_v2.json"
DEFAULT_CONTROLS = FIXTURES_DIR / "munch_inapt.jsonl"


# --- Synset resolution -------------------------------------------------------

def lookup_primary_synset(conn: sqlite3.Connection, lemma: str) -> str | None:
    """Resolve a lemma to its primary synset_id.

    Prefers the curated vocabulary entry (least-polysemous lemma per synset).
    Falls back to the first synset in the lemmas table when curated vocab
    has no entry. Returns None if the lemma is unknown.
    """
    if not lemma:
        return None
    needle = lemma.strip().lower()

    row = conn.execute(
        "SELECT synset_id FROM property_vocab_curated "
        "WHERE LOWER(lemma) = ? "
        "ORDER BY polysemy ASC LIMIT 1",
        (needle,),
    ).fetchone()
    if row:
        return row[0]

    row = conn.execute(
        "SELECT synset_id FROM lemmas "
        "WHERE LOWER(lemma) = ? "
        "ORDER BY synset_id LIMIT 1",
        (needle,),
    ).fetchone()
    return row[0] if row else None


def _get_properties(conn: sqlite3.Connection, synset_id: str) -> dict[int, float]:
    """Return {cluster_id: salience_sum} for a synset's curated properties."""
    rows = conn.execute(
        "SELECT cluster_id, salience_sum "
        "FROM synset_properties_curated WHERE synset_id = ?",
        (synset_id,),
    ).fetchall()
    return {int(cid): float(sal) for cid, sal in rows}


# --- Scoring registry --------------------------------------------------------

ScoringFn = Callable[[Mapping[int, float], Mapping[int, float]], float]
"""Signature: (pa, pb) -> float in [0.0, 1.0].

Inputs are ``{cluster_id: salience_sum}`` mappings — the existing
internal shape produced by :func:`_get_properties`. The function is
called only when both sides are non-empty (the ``no_properties`` /
``unresolved`` statuses are handled in :func:`score_pair` before any
scoring runs), but implementations should still tolerate empty input
defensively for direct unit-test use.
"""


def _jaccard_salience(
    pa: Mapping[int, float], pb: Mapping[int, float],
) -> float:
    """Salience-weighted Jaccard over shared cluster_ids.

    num = sum_c min(pa[c], pb[c]) over shared clusters
    den = sum_c max(pa[c], pb[c]) over the union
    score = num / den (or 0.0 if den == 0)
    """
    shared = set(pa) & set(pb)
    if not shared:
        return 0.0
    union = set(pa) | set(pb)
    num = sum(min(pa[c], pb[c]) for c in shared)
    den = sum(max(pa.get(c, 0.0), pb.get(c, 0.0)) for c in union)
    return num / den if den > 0 else 0.0


def _jaccard_raw(
    pa: Mapping[int, float], pb: Mapping[int, float],
) -> float:
    """Unweighted set-Jaccard over cluster_ids.

    Salience values are ignored — only cluster overlap counts. Acts as
    a control for whether salience weighting helps.
    """
    sa, sb = set(pa), set(pb)
    if not sa or not sb:
        return 0.0
    inter = sa & sb
    union = sa | sb
    return len(inter) / len(union) if union else 0.0


def _cosine_salience(
    pa: Mapping[int, float], pb: Mapping[int, float],
) -> float:
    """Cosine similarity over salience vectors aligned by cluster_id.

    Cluster_ids missing from one side are zero-padded — the standard
    sparse-cosine convention. Returns 0.0 when either vector has zero
    norm (e.g. all-zero saliences).
    """
    keys = set(pa) | set(pb)
    if not keys:
        return 0.0
    dot = sum(pa.get(c, 0.0) * pb.get(c, 0.0) for c in keys)
    na = math.sqrt(sum(v * v for v in pa.values()))
    nb = math.sqrt(sum(v * v for v in pb.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _ortony_vehicle_salience(
    pa: Mapping[int, float], pb: Mapping[int, float],
) -> float:
    """Asymmetric vehicle-coverage scoring (Ortony 1979, normalised).

    Formula:
        f(pa, pb) = (Σ_{c ∈ pa ∩ pb} pb[c]) / (Σ_{c ∈ pb} pb[c])

    Reads as "what fraction of the vehicle's salience mass is captured
    by properties also present in the topic". Bounded [0, 1] because the
    numerator is a subset-sum of the denominator.

    Asymmetric by construction: swapping (pa, pb) normalises by a
    different mass and so produces a different score whenever the
    salience distributions differ. This is the M02 hypothesis: the
    symmetric variants (jaccard_salience, jaccard_raw, cosine_salience)
    treat overlap as overlap; Ortony's account of metaphor says the
    vehicle contributes its high-salience properties to the topic,
    regardless of how salient those properties are in the topic, and
    that asymmetry should be reflected in the score.

    Zero-vehicle-mass guard: if Σ pb[c] == 0 (empty vehicle or all-zero
    saliences) the formula is undefined; return 0.0 by convention to
    mirror the cosine_salience zero-norm handling and keep the registry
    uniformly safe.
    """
    vehicle_mass = sum(pb.values())
    if vehicle_mass <= 0.0:
        return 0.0
    shared = set(pa) & set(pb)
    if not shared:
        return 0.0
    return sum(pb[c] for c in shared) / vehicle_mass


def _ortony_imbalance(
    pa: Mapping[int, float], pb: Mapping[int, float],
) -> float:
    """Imbalance-weighted asymmetric scoring (Ortony 1979, variant 2).

    Formula:
        f(pa, pb) = (Σ_{c ∈ pa ∩ pb} pb[c] × max(0, pb[c] − pa[c]))
                   / (Σ_{c ∈ pb} pb[c]²)

    Reads as "fraction of the vehicle's imbalance-weighted prominence
    captured by properties on which the vehicle is more salient than
    the topic". Bounded [0, 1] because each numerator term is at most
    pb[c]² (when pa[c]=0 on a shared cluster) and the numerator only
    sums over shared clusters whereas the denominator covers all
    vehicle clusters.

    Difference from :func:`_ortony_vehicle_salience`: equal-salience
    properties contribute zero (max(0, pb − pa) = 0 when pb = pa).
    This directly targets the MUNCH-bias mechanism — paraphrase pairs
    that share equally-salient surface properties cannot move the
    score in this formula, addressing the failure mode documented in
    `data-pipeline/sweeps/M02-S02-sweep-findings.md`.

    Asymmetric by construction: swapping (pa, pb) changes BOTH the
    per-term subtraction direction (negative values clamp to zero) and
    the normaliser, so the answer differs for any non-equal
    distributions.

    Zero-vehicle-mass guard: if Σ pb[c]² == 0 the formula is undefined
    (empty vehicle or all-zero saliences); return 0.0 by convention to
    mirror the cosine_salience and ortony_vehicle_salience guards.
    """
    squared_mass = sum(v * v for v in pb.values())
    if squared_mass <= 0.0:
        return 0.0
    shared = set(pa) & set(pb)
    if not shared:
        return 0.0
    numerator = sum(
        pb[c] * max(0.0, pb[c] - pa[c]) for c in shared
    )
    return numerator / squared_mass


def _random_uniform(
    pa: Mapping[int, float], pb: Mapping[int, float],
) -> float:
    """Deterministic pseudo-random null-control scoring.

    Hashes the sorted union of cluster_ids in pa∪pb to a float in
    [0, 1) via blake2b. Order-symmetric: sort the union, don't
    concatenate side-by-side. Carries no semantic signal — apt and
    inapt cohorts in the V2 corpus should yield separation_score ≈ 0
    under this scoring, which is the slice's null reference for
    sensitivity validation.

    Determinism is via hashlib (NOT random.random / numpy.random,
    which are non-deterministic across processes without explicit
    seeding and would silently break reproducibility).

    Assumption: determinism + order-symmetry are sufficient null-
    reference properties; we are NOT proving uniformity statistically
    here (would require thousands of samples and is out of scope).

    Cohort-level caveat: the per-pair score is uniform over [0, 1)
    given a fixed ``cluster_ids_union``, but the cohort-level expected
    separation_score is unbiased ONLY when the apt and inapt cohorts
    share similar union-size distributions; if apt unions are
    systematically larger or smaller than inapt unions the null
    reference becomes biased. Treat this as a sanity-floor reference,
    not a calibrated null hypothesis test — do not interpret
    ``separation_score - random_uniform_separation`` as "real signal
    above null" without first checking union-size parity across
    cohorts.
    """
    union = sorted(set(pa) | set(pb))
    if not union:
        return 0.0
    # Comma-join is collision-free only because cluster_ids are ints and
    # `union` is sorted-unique: distinct sorted int sequences map to
    # distinct strings. Do not feed strings that may contain commas here.
    key = ",".join(str(c) for c in union).encode("utf-8")
    digest = hashlib.blake2b(key, digest_size=8).digest()
    n = int.from_bytes(digest, "big")
    return n / (1 << 64)


SCORING_FNS: dict[str, ScoringFn] = {
    "jaccard_salience": _jaccard_salience,
    "jaccard_raw": _jaccard_raw,
    "cosine_salience": _cosine_salience,
    "ortony_vehicle_salience": _ortony_vehicle_salience,
    "ortony_imbalance": _ortony_imbalance,
    "random_uniform": _random_uniform,
}

DEFAULT_SCORING = "jaccard_salience"


# --- Pair scoring ------------------------------------------------------------

PairStatus = Literal["scored", "unresolved", "no_properties"]


@dataclass(frozen=True)
class PairScore:
    """Outcome of scoring a (word_a, word_b) pair.

    The three statuses are semantically distinct and must be reported
    separately so a coverage gap is not conflated with a real zero score:

      * ``scored``        — both words resolved AND have curated properties;
                            ``score`` is in [0.0, 1.0] (0.0 = no overlap).
      * ``unresolved``    — at least one lemma did not resolve to a synset;
                            ``score`` is None.
      * ``no_properties`` — both resolved but at least one synset has zero
                            rows in synset_properties_curated (data
                            coverage gap); ``score`` is None.

    Invariant: ``score is None`` iff ``status != 'scored'`` — enforced at
    construction so cohort logic can rely on it without defensive checks.
    """
    status: PairStatus
    score: float | None

    def __post_init__(self) -> None:
        if self.status == "scored" and self.score is None:
            raise ValueError(
                "PairScore(status='scored') requires a numeric score; got None"
            )
        if self.status != "scored" and self.score is not None:
            raise ValueError(
                f"PairScore(status='{self.status}') must have score=None; "
                f"got {self.score!r}"
            )


def score_pair(
    conn: sqlite3.Connection,
    word_a: str,
    word_b: str,
    scoring_fn: ScoringFn = _jaccard_salience,
) -> PairScore:
    """Score a (word_a, word_b) pair by property overlap.

    See :class:`PairScore` for the status semantics — scoring formula
    choice never changes status: a coverage gap stays ``no_properties``
    and a real overlap-of-zero stays ``scored`` with score 0.0. Pass
    any callable from :data:`SCORING_FNS` (or a custom one matching
    :data:`ScoringFn`) to swap the formula; the default preserves the
    historic salience-weighted Jaccard behaviour.
    """
    sa = lookup_primary_synset(conn, word_a)
    sb = lookup_primary_synset(conn, word_b)
    if sa is None or sb is None:
        return PairScore(status="unresolved", score=None)

    pa = _get_properties(conn, sa)
    pb = _get_properties(conn, sb)
    if not pa or not pb:
        return PairScore(status="no_properties", score=None)

    return PairScore(status="scored", score=scoring_fn(pa, pb))


# --- Loaders -----------------------------------------------------------------

def load_apt_pairs(path: str) -> list[dict]:
    """Load apt metaphor pairs from metaphor_pairs_v2.json."""
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON array of pairs")
    return data


def load_inapt_controls(path: str) -> list[dict]:
    """Load MUNCH inapt controls from a JSONL file.

    Filters defensively to label == 'inapt'. The MUNCH dataset has known
    quirks (see MEM021) — preprocessing already produced an inapt-only
    file, but we re-filter here so the evaluator is robust to either
    source format.
    """
    rows: list[dict] = []
    with open(path) as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                # Tolerate truncated / garbled lines (e.g. from a crashed
                # producer run) — warn with file + line number and continue.
                log.warning(
                    "load_inapt_controls: skipping malformed JSONL at %s:%d (%s)",
                    path, line_no, exc,
                )
                continue
            # Valid JSON that is not a dict (e.g. `null`, a bare string, a list,
            # an int) would crash `row.get("label")` below and abort the whole
            # load. Skip with a warning to honour the documented "tolerate
            # garbled input" contract.
            if not isinstance(row, dict):
                log.warning(
                    "load_inapt_controls: skipping non-dict JSONL row at %s:%d "
                    "(got %s)",
                    path, line_no, type(row).__name__,
                )
                continue
            if row.get("label") == "inapt":
                rows.append(row)
    return rows


# --- Aggregation -------------------------------------------------------------

def _percentile(values: list[float], pct: float) -> float:
    """Return the requested percentile via linear interpolation. 0 if empty."""
    if not values:
        return 0.0
    if pct <= 0:
        return min(values)
    if pct >= 100:
        return max(values)
    s = sorted(values)
    rank = (pct / 100.0) * (len(s) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def classify_aptness(
    apt_scores: list[float],
    inapt_scores: list[float],
    threshold: float,
) -> dict:
    """Apply a threshold and report aptness + false-positive rates."""
    if not apt_scores:
        aptness_rate = 0.0
    else:
        aptness_rate = sum(1 for s in apt_scores if s > threshold) / len(apt_scores)

    if not inapt_scores:
        fp_rate = 0.0
    else:
        fp_rate = sum(1 for s in inapt_scores if s > threshold) / len(inapt_scores)

    return {
        "threshold": threshold,
        "aptness_rate": aptness_rate,
        "false_positive_rate": fp_rate,
    }


def aggregate_metrics(
    apt_scores: list[float], inapt_scores: list[float],
) -> dict:
    """Mean scores and separation score for the two cohorts.

    separation_score = mean_apt − mean_inapt. A positive value means
    the evaluator scores genuine metaphor pairs higher on average than
    MUNCH inapt confusions.
    """
    mean_apt = sum(apt_scores) / len(apt_scores) if apt_scores else 0.0
    mean_inapt = (
        sum(inapt_scores) / len(inapt_scores) if inapt_scores else 0.0
    )
    return {
        "mean_apt_score": round(mean_apt, 6),
        "mean_inapt_score": round(mean_inapt, 6),
        "separation_score": round(mean_apt - mean_inapt, 6),
        "n_apt": len(apt_scores),
        "n_inapt": len(inapt_scores),
    }


# --- Orchestrator ------------------------------------------------------------

@dataclass(frozen=True)
class CohortResult:
    """Aggregated outcome of scoring one cohort (apt or inapt).

    ``scores`` holds only values from pairs with status ``scored`` — the
    coverage-gap counters are kept separate so they cannot deflate the
    cohort mean. A frozen dataclass is used (rather than a positional
    tuple) so adding a future counter does not silently shift call-site
    indices.
    """
    scores: list[float]
    per_pair: list[dict]
    unresolved: int
    no_properties: int


def _score_cohort(
    conn: sqlite3.Connection,
    pairs: list[dict],
    word_a_key: str,
    word_b_key: str,
    cls: str,
    scoring_fn: ScoringFn = _jaccard_salience,
) -> CohortResult:
    """Score every pair in a cohort, returning a :class:`CohortResult`."""
    scores: list[float] = []
    per_pair: list[dict] = []
    unresolved = 0
    no_properties = 0
    for p in pairs:
        a = p.get(word_a_key)
        b = p.get(word_b_key)
        if not a or not b:
            # Missing keys behave like an unresolved lemma — no synset to score.
            unresolved += 1
            per_pair.append({
                "class": cls,
                "word_a": a,
                "word_b": b,
                "status": "unresolved",
                "score": None,
                "resolved": False,
            })
            continue
        result = score_pair(conn, a, b, scoring_fn=scoring_fn)
        if result.status == "unresolved":
            unresolved += 1
            per_pair.append({
                "class": cls,
                "word_a": a,
                "word_b": b,
                "status": "unresolved",
                "score": None,
                "resolved": False,
            })
            continue
        if result.status == "no_properties":
            no_properties += 1
            per_pair.append({
                "class": cls,
                "word_a": a,
                "word_b": b,
                "status": "no_properties",
                "score": None,
                "resolved": True,
            })
            continue
        # status == "scored" — PairScore.__post_init__ guarantees score is set.
        scores.append(result.score)
        per_pair.append({
            "class": cls,
            "word_a": a,
            "word_b": b,
            "status": "scored",
            "score": round(result.score, 6),
            "resolved": True,
        })
    return CohortResult(
        scores=scores,
        per_pair=per_pair,
        unresolved=unresolved,
        no_properties=no_properties,
    )


def evaluate(
    conn: sqlite3.Connection,
    pairs_file: str,
    controls_file: str,
    threshold_percentile: float = 95.0,
    db_path: str | None = None,
    scoring: str = DEFAULT_SCORING,
) -> dict:
    """Run the full evaluation. Returns the structured result dict.

    ``scoring`` selects a formula from :data:`SCORING_FNS`. Unknown
    names raise ``ValueError`` listing the registered options — fail
    fast so a typo in a sweep config does not silently fall back to
    the default.
    """
    if scoring not in SCORING_FNS:
        known = ", ".join(sorted(SCORING_FNS))
        raise ValueError(
            f"Unknown scoring name: {scoring!r}. Registered: {known}"
        )
    scoring_fn = SCORING_FNS[scoring]

    apt_pairs = load_apt_pairs(pairs_file)
    inapt_controls = load_inapt_controls(controls_file)

    log.info(
        "Loaded %d apt pairs, %d inapt controls (scoring=%s)",
        len(apt_pairs), len(inapt_controls), scoring,
    )

    apt = _score_cohort(
        conn, apt_pairs, "source", "target", "apt",
        scoring_fn=scoring_fn,
    )
    inapt = _score_cohort(
        conn, inapt_controls, "target", "paraphrase", "inapt",
        scoring_fn=scoring_fn,
    )

    log.info(
        "Scored: apt=%d/%d (unresolved=%d, no_properties=%d), "
        "inapt=%d/%d (unresolved=%d, no_properties=%d)",
        len(apt.scores), len(apt_pairs), apt.unresolved, apt.no_properties,
        len(inapt.scores), len(inapt_controls), inapt.unresolved, inapt.no_properties,
    )

    threshold = _percentile(inapt.scores, threshold_percentile)
    classification = classify_aptness(apt.scores, inapt.scores, threshold)
    agg = aggregate_metrics(apt.scores, inapt.scores)

    return {
        "aptness_rate": round(classification["aptness_rate"], 6),
        "false_positive_rate": round(
            classification["false_positive_rate"], 6,
        ),
        "separation_score": agg["separation_score"],
        "aggregate": {
            **agg,
            "apt_unresolved": apt.unresolved,
            "inapt_unresolved": inapt.unresolved,
            "apt_no_properties": apt.no_properties,
            "inapt_no_properties": inapt.no_properties,
        },
        "per_pair_scores": apt.per_pair + inapt.per_pair,
        "config": {
            "scoring": scoring,
            "threshold": round(threshold, 6),
            "threshold_percentile": threshold_percentile,
            "pairs_file": pairs_file,
            "controls_file": controls_file,
            "db": db_path,
            "git_commit": get_git_commit(),
        },
    }


# --- CLI ---------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discriminative aptness evaluator for Metaforge",
    )
    parser.add_argument(
        "--pairs", default=str(DEFAULT_PAIRS),
        help=f"Apt metaphor pairs JSON (default: {DEFAULT_PAIRS})",
    )
    parser.add_argument(
        "--controls", default=str(DEFAULT_CONTROLS),
        help=f"MUNCH inapt controls JSONL (default: {DEFAULT_CONTROLS})",
    )
    parser.add_argument(
        "--db", default=str(LEXICON_V2),
        help=f"Lexicon DB path (default: {LEXICON_V2})",
    )
    parser.add_argument(
        "--threshold-percentile", type=float, default=95.0,
        help="Inapt percentile to use as classification threshold (default: 95)",
    )
    parser.add_argument(
        "--scoring", default=DEFAULT_SCORING,
        choices=sorted(SCORING_FNS),
        help=(
            "Scoring formula from SCORING_FNS registry "
            f"(default: {DEFAULT_SCORING})"
        ),
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Optional output JSON file",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    db_path = Path(args.db)
    if not db_path.is_file():
        # sqlite3.connect would silently create an empty DB here, leading to
        # zero-result runs that are hard to diagnose. Fail fast instead.
        raise FileNotFoundError(
            f"--db points at non-existent file: {args.db} "
            f"(sqlite3 would silently create an empty DB; refusing)"
        )

    conn = sqlite3.connect(args.db)
    try:
        result = evaluate(
            conn=conn,
            pairs_file=args.pairs,
            controls_file=args.controls,
            threshold_percentile=args.threshold_percentile,
            db_path=args.db,
            scoring=args.scoring,
        )
    finally:
        conn.close()

    print(json.dumps(result, indent=2))
    print(
        f"\n=== Aptness Eval ({result['config']['git_commit']}, "
        f"scoring={result['config']['scoring']}) ===",
        file=sys.stderr,
    )
    agg = result["aggregate"]
    print(
        f"  apt:   n={agg['n_apt']:>4}  mean={agg['mean_apt_score']:.4f}  "
        f"unresolved={agg['apt_unresolved']}  "
        f"no_properties={agg['apt_no_properties']}",
        file=sys.stderr,
    )
    print(
        f"  inapt: n={agg['n_inapt']:>4}  mean={agg['mean_inapt_score']:.4f}  "
        f"unresolved={agg['inapt_unresolved']}  "
        f"no_properties={agg['inapt_no_properties']}",
        file=sys.stderr,
    )
    print(
        f"  separation_score = {result['separation_score']:.4f}",
        file=sys.stderr,
    )
    print(
        f"  threshold (p{args.threshold_percentile:g} of inapt) = "
        f"{result['config']['threshold']:.4f}",
        file=sys.stderr,
    )
    print(
        f"  aptness_rate         = {result['aptness_rate']:.4f}",
        file=sys.stderr,
    )
    print(
        f"  false_positive_rate  = {result['false_positive_rate']:.4f}",
        file=sys.stderr,
    )

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"  Results written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
