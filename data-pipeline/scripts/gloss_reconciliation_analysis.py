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


def contamination_rate(labels: Iterable[dict], idx: set[tuple]) -> dict:
    """Silent-noise rate: fraction of UNFLAGGED endpoints the operator judged WRONG.

    The unflagged endpoints are the subagent's negatives — what it passed. The
    sense-check random stratum draws from this population, so this estimates the
    true contamination the subagent MISSED, with a Wilson CI (n is small).
    """
    k = n = 0
    for label in labels:
        if is_flagged(label, idx):
            continue
        outcome = snap_outcome(label)
        if outcome == UNKNOWN:
            continue
        n += 1
        if outcome == WRONG:
            k += 1
    rate = k / n if n else 0.0
    lo, hi = wilson_ci(k, n)
    return {"k": k, "n": n, "rate": rate, "ci_lo": lo, "ci_hi": hi}


def promiscuity(labels: Iterable[dict],
                candidates_by_lemma: Optional[dict[str, list[dict]]] = None) -> dict:
    """Sense-promiscuity distribution: how often a node is apt across many senses.

    Computed over determinate labels (verdict != unsure). Reports the split rate,
    the apt-sense cardinality distribution, the count of poly-apt endpoints
    (>= 2 apt senses), and — when candidate senses are supplied — the mean share
    of a lemma's available senses the operator marked apt. A high split rate and
    a high apt-share argue for a sense-SET snapper over a single-sense classifier.
    """
    determinate = [r for r in labels if r["verdict"] != "unsure"]
    splits = [r for r in determinate if r["verdict"] == "split"]
    apt_with_ids = [r for r in splits if _apt_ids(r)]

    cardinality = Counter(len(_apt_ids(r)) for r in apt_with_ids)
    cards = [len(_apt_ids(r)) for r in apt_with_ids]
    mean_card = sum(cards) / len(cards) if cards else 0.0
    poly_apt = sum(1 for c in cards if c >= 2)

    out = {
        "n_determinate": len(determinate),
        "n_split": len(splits),
        "split_rate": len(splits) / len(determinate) if determinate else 0.0,
        "n_split_with_apt": len(apt_with_ids),
        "apt_cardinality": dict(cardinality),
        "mean_apt_cardinality": mean_card,
        "poly_apt": poly_apt,
    }

    if candidates_by_lemma is not None:
        shares = []
        for r in apt_with_ids:
            cands = candidates_by_lemma.get(r["word"])
            if cands:
                shares.append(len(_apt_ids(r)) / len(cands))
        out["mean_apt_share"] = sum(shares) / len(shares) if shares else 0.0
        out["n_apt_share_scored"] = len(shares)
    return out


def drift(labels: Iterable[dict]) -> dict:
    """Calibration drift: split rate in the first vs second chronological half.

    Operates on the raw label stream (each labelling action, sorted by ts) so it
    captures behaviour over the session, not the deduped endpoint set. Tests the
    operator's observation that his ratings drifted toward Split as he calibrated.
    """
    stream = [r for r in sorted(labels, key=lambda r: r["ts"])
              if r["verdict"] != "unsure"]
    mid = len(stream) // 2
    halves = {"first": stream[:mid], "second": stream[mid:]}
    result = {}
    for name, rows in halves.items():
        n = len(rows)
        n_split = sum(1 for r in rows if r["verdict"] == "split")
        result[name] = {"n": n, "n_split": n_split,
                        "split_rate": n_split / n if n else 0.0}
    result["delta"] = result["second"]["split_rate"] - result["first"]["split_rate"]
    return result


def _dominant_pick(candidates: list[dict]) -> Optional[str]:
    """Argmax SemCor tagcount (NULL -> 0); ties break to the lowest numeric
    synset_id, mirroring the current lowest-id snapper so an all-NULL lemma
    yields the current behaviour (no spurious improvement is claimed)."""
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda c: (-(c.get("tagcount") or 0), int(c["synset_id"])),
    )["synset_id"]


def resnapper_baseline(labels: Iterable[dict],
                       candidates_by_lemma: dict[str, list[dict]]) -> dict:
    """Static dominant-sense (SemCor tagcount) baseline for the re-snapper.

    For each label with a usable apt-target set whose target is covered by the
    lemma's candidate senses, compares the CURRENT snap against a dominant-tagcount
    pick. This is a lower-effort proxy for the Gloss-Matched Snapper (which adds
    gloss-overlap / Lesk WSD over the retained phrase) — it bounds how much the
    cheap SemCor prior alone recovers. Broken out for the WRONG subset, where the
    current snap is wrong by construction, to answer "what fraction of the
    operator's wrong snaps would a tagcount prior fix?".
    """
    n_scored = current_hits = dominant_hits = n_uncovered = 0
    wrong_n = wrong_dom = 0
    dominant_pick_for: dict[str, str] = {}
    for label in labels:
        target = apt_target_set(label)
        if not target:
            continue
        cands = candidates_by_lemma.get(label["word"])
        if not cands:
            n_uncovered += 1
            continue
        cand_ids = {c["synset_id"] for c in cands}
        # target must be reachable from the candidate set to be scorable
        if not (target & cand_ids):
            n_uncovered += 1
            continue
        n_scored += 1
        pick = _dominant_pick(cands)
        dominant_pick_for[f"{label['word']}::{label['snapped_synset_id']}"] = pick
        current_hit = label["snapped_synset_id"] in target
        dominant_hit = pick in target
        current_hits += int(current_hit)
        dominant_hits += int(dominant_hit)
        if snap_outcome(label) == WRONG:
            wrong_n += 1
            wrong_dom += int(dominant_hit)
    return {
        "n_scored": n_scored,
        "n_uncovered": n_uncovered,
        "current_hits": current_hits,
        "dominant_hits": dominant_hits,
        "current_acc": current_hits / n_scored if n_scored else 0.0,
        "dominant_acc": dominant_hits / n_scored if n_scored else 0.0,
        "wrong": {"n": wrong_n, "dominant_hits": wrong_dom,
                  "dominant_recovery": wrong_dom / wrong_n if wrong_n else 0.0},
        "dominant_pick_for": dominant_pick_for,
    }
