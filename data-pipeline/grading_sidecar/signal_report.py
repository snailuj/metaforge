"""Signal/coverage report logic for the grading tool's on-demand dashboard.

Pure functions (no IO) so the route stays thin and this stays unit-testable.
Two layers:

  * COVERAGE — graded n, live/dead, distinct topics, both-class topics, and
    "powered" topics (>=5 within-topic live x dead pairs). This is the binding
    constraint surfaced after each grading batch: the metaphor-graph signal
    needs topic BREADTH, not chain depth (see docs/inbox path-geometry findings).
  * GEOMETRY CONCORDANCE — optional within-topic concordance of the path-geometry
    features (max_hop_cos, std_hop_cos, path_total_cos), joined from a
    precomputed geometry file. Degrades cleanly to coverage-only when absent
    (the sidecar has no DB/numpy to compute centroid hops itself).

Verdict resolution mirrors data-pipeline grading_io: drop superseded ts, then
latest-wins per chain_signature — so the dashboard matches the offline analysis
rather than counting every raw line (which stats.py does deliberately).
"""
from __future__ import annotations

from .models import normalise_judgement

# The within-topic discriminators that survived the adversarial audit. max_hop /
# dispersion = "one big leap"; path_total is the length-ish companion.
GEOMETRY_FEATURES = ("max_hop_cos", "std_hop_cos", "path_total_cos")

# A topic needs this many within-topic live x dead pairs to power a comparison.
_POWERED_PAIR_THRESHOLD = 5


def resolve_verdicts(judgements: list[dict]) -> list[dict]:
    """Latest-wins per chain_signature, dropping any ts named by a supersedes_ts."""
    superseded = {j["supersedes_ts"] for j in judgements if j.get("supersedes_ts")}
    alive = [j for j in judgements if j.get("ts") not in superseded]
    by_sig: dict[str, dict] = {}
    for j in sorted(alive, key=lambda r: r.get("ts", "")):
        by_sig[j.get("chain_signature")] = j
    return list(by_sig.values())


def binary_label(norm: dict):
    """Normalised verdict → 'live' / 'dead' / None (drops irrelevant/None)."""
    metaphor = norm.get("metaphor")
    return metaphor if metaphor in ("live", "dead") else None


def coverage(rows: list[dict]) -> dict:
    """Per-topic live/dead breakdown + breadth counts from binary rows.

    rows: [{sig, tsid, topic, y}] where y=1 live, 0 dead.
    """
    by_topic: dict[str, dict] = {}
    for r in rows:
        bucket = by_topic.setdefault(r["tsid"], {"topic": r["topic"], "live": 0, "dead": 0})
        bucket["live" if r["y"] == 1 else "dead"] += 1

    per_topic = [
        {"topic_synset_id": tsid, "topic": b["topic"], "live": b["live"],
         "dead": b["dead"], "pairs": b["live"] * b["dead"]}
        for tsid, b in by_topic.items()
    ]
    per_topic.sort(key=lambda p: (-p["pairs"], -(p["live"] + p["dead"])))

    n = len(rows)
    n_live = sum(r["y"] == 1 for r in rows)
    return {
        "n": n,
        "n_live": n_live,
        "n_dead": n - n_live,
        "base_rate_live": round(n_live / n, 3) if n else 0.0,
        "n_topics": len(by_topic),
        "n_both_class_topics": sum(1 for p in per_topic if p["live"] and p["dead"]),
        "n_powered_topics": sum(1 for p in per_topic if p["pairs"] >= _POWERED_PAIR_THRESHOLD),
        "per_topic": per_topic,
    }


def within_topic_concordance(rows: list[dict], geometry_by_sig: dict, feature: str):
    """Pooled within-topic concordance (Mann-Whitney AUC) for one feature.

    Returns (auc, n_pairs); auc is None when no live x dead pair has geometry.
    """
    by_topic: dict[str, list] = {}
    for r in rows:
        geo = geometry_by_sig.get(r["sig"])
        if not geo:
            continue
        value = geo.get(feature)
        if value is None:
            continue
        by_topic.setdefault(r["tsid"], []).append((value, r["y"]))

    concordant = 0.0
    total = 0
    for vs in by_topic.values():
        lives = [v for v, y in vs if y == 1]
        deads = [v for v, y in vs if y == 0]
        for lv in lives:
            for dv in deads:
                total += 1
                concordant += 1.0 if lv > dv else (0.5 if lv == dv else 0.0)
    return (round(concordant / total, 3) if total else None), total


def build_signal_report(judgements: list[dict], geometry_by_sig: dict, *, server_ts: str) -> dict:
    """Assemble the full dashboard from raw verdicts + an optional geometry map."""
    resolved = [normalise_judgement(j) for j in resolve_verdicts(judgements)]
    rows = []
    for n in resolved:
        label = binary_label(n)
        if label is None:
            continue
        rows.append({
            "sig": n.get("chain_signature"),
            "tsid": n.get("topic_synset_id"),
            "topic": n.get("topic"),
            "y": 1 if label == "live" else 0,
        })

    report = coverage(rows)
    features = []
    if geometry_by_sig:
        for name in GEOMETRY_FEATURES:
            auc, n_pairs = within_topic_concordance(rows, geometry_by_sig, name)
            features.append({"name": name, "within_topic_auc": auc, "n_pairs": n_pairs})
    report["geometry_available"] = bool(geometry_by_sig)
    report["geometry_features"] = features
    report["server_ts"] = server_ts
    return report
