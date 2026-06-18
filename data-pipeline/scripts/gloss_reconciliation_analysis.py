"""Gloss-Reconciliation analysis harness (Remediation Block 1).

Measures, offline and off the operator's human sense-labels:
  - the Gloss-Reconciliation subagent's precision / recall (is the 111-flag
    worklist trustworthy enough to drive Endpoint Cleanup?),
  - the silent-noise / true-contamination rate among endpoints the subagent
    passed (Wilson CI),
  - the sense-promiscuity distribution (split rate + apt-sense cardinality) that
    decides single-sense-classifier vs sense-SET-model for the Gloss-Matched
    Snapper,
  - a static dominant-sense (SemCor tagcount) baseline for the re-snapper.

The subagent is an unmeasured oracle: every metric here is computed against the
operator's labels, never against the subagent. Functions are pure; the CLI
driver at the bottom loads the JSONL inputs and emits a JSON + markdown report.

Verdict vocabulary (operator sense-labels): right / wrong / rare_ok / unsure /
split. `split` carries BOTH conflation (snap wrong, other senses apt) AND
poly-aptness (snap is one of several apt senses) — disambiguated via
`apt_synset_ids` membership.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, Optional

# snap_outcome classes: is the CURRENT snap apt for the operator?
APT = "apt"          # right, rare_ok, or split where the snapped sense is apt
WRONG = "wrong"      # wrong, or split where the snapped sense is NOT in the apt set
UNKNOWN = "unknown"  # unsure, or split with no apt senses recorded

_ENDPOINT_KEY = ("role", "word", "snapped_synset_id")


def _key(row: dict, fields: tuple[str, ...] = _ENDPOINT_KEY) -> tuple:
    return tuple(row.get(f) for f in fields)


def dedupe_latest(labels: Iterable[dict],
                  fields: tuple[str, ...] = _ENDPOINT_KEY) -> list[dict]:
    """Return one label per endpoint, keeping the chronologically latest by `ts`.

    Endpoints are identified by (role, word, snapped_synset_id) — the same
    endpoint can be labelled more than once (the operator changed his mind, or
    the sampler re-surfaced it). The latest label is authoritative.
    """
    latest: dict[tuple, dict] = {}
    for row in sorted(labels, key=lambda r: r["ts"]):
        latest[_key(row, fields)] = row
    return list(latest.values())


def count_revisions(labels: Iterable[dict],
                    fields: tuple[str, ...] = _ENDPOINT_KEY) -> int:
    """Count endpoints whose verdict CHANGED across successive labels.

    Re-affirming the same verdict does not count. This quantifies the operator's
    calibration drift (e.g. an early `wrong` later revised to `split`).
    """
    seen: dict[tuple, str] = {}
    revisions = 0
    for row in sorted(labels, key=lambda r: r["ts"]):
        k = _key(row, fields)
        verdict = row["verdict"]
        if k in seen and seen[k] != verdict:
            revisions += 1
        seen[k] = verdict
    return revisions


def _apt_ids(label: dict) -> list[str]:
    return label.get("apt_synset_ids") or []


def snap_outcome(label: dict) -> str:
    """Classify whether the operator considers the CURRENT snap apt.

    right    -> APT
    rare_ok  -> APT (rare but acceptable sense)
    wrong    -> WRONG
    unsure   -> UNKNOWN
    split    -> APT if the snapped sense is among the apt set (poly-aptness),
                WRONG if apt senses are recorded but exclude the snapped one,
                UNKNOWN if no apt senses were recorded.
    """
    verdict = label["verdict"]
    if verdict in ("right", "rare_ok"):
        return APT
    if verdict == "wrong":
        return WRONG
    if verdict == "unsure":
        return UNKNOWN
    if verdict == "split":
        apt = _apt_ids(label)
        if not apt:
            return UNKNOWN
        return APT if label["snapped_synset_id"] in apt else WRONG
    raise ValueError(f"unknown verdict: {verdict!r}")


def apt_target_set(label: dict) -> set[str]:
    """The synset_ids the operator considers apt for this endpoint.

    Used to score the re-snapper: a proposed snap "hits" if it lands in this set.
      right    -> {snapped}
      rare_ok  -> {snapped, intended}
      wrong    -> {intended}
      split    -> set(apt_synset_ids)
      unsure   -> {}  (no usable target)
    """
    verdict = label["verdict"]
    snapped = label["snapped_synset_id"]
    intended = label.get("intended_synset_id")
    if verdict == "right":
        return {snapped}
    if verdict == "rare_ok":
        return {snapped} | ({intended} if intended else set())
    if verdict == "wrong":
        return {intended} if intended else set()
    if verdict == "split":
        return set(_apt_ids(label))
    if verdict == "unsure":
        return set()
    raise ValueError(f"unknown verdict: {verdict!r}")


def flag_index(flags: Iterable[dict]) -> set[tuple]:
    """Set of (role, word, synset_id) the subagent flagged as contaminated."""
    return {(f["role"], f["word"], f["synset_id"]) for f in flags}


def is_flagged(label: dict, idx: set[tuple]) -> bool:
    """Whether the subagent flagged this endpoint (its positive prediction)."""
    return (label["role"], label["word"], label["snapped_synset_id"]) in idx


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion k/n.

    Robust at small n and near 0/1 (unlike the normal approximation). An empty
    sample returns the full [0, 1] interval.
    """
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def confusion(labels: Iterable[dict], idx: set[tuple]) -> dict:
    """Binary confusion of subagent flags vs the operator's WRONG verdicts.

    gold-positive  = the current snap is WRONG (snap_outcome == WRONG)
    pred-positive  = the subagent flagged the endpoint
    UNKNOWN outcomes (unsure / split-without-apt) are excluded from scoring.
    """
    tp = fp = fn = tn = excluded = 0
    for label in labels:
        outcome = snap_outcome(label)
        if outcome == UNKNOWN:
            excluded += 1
            continue
        gold_pos = outcome == WRONG
        pred_pos = is_flagged(label, idx)
        if gold_pos and pred_pos:
            tp += 1
        elif gold_pos and not pred_pos:
            fn += 1
        elif not gold_pos and pred_pos:
            fp += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "excluded": excluded}


def precision_recall_f1(cm: dict) -> dict:
    """Precision / recall / F1 from a confusion dict; zero denominators -> 0.0."""
    tp, fp, fn = cm["tp"], cm["fp"], cm["fn"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) else 0.0)
    return {"precision": precision, "recall": recall, "f1": f1}
