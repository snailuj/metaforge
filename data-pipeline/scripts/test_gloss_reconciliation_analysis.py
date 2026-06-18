"""Tests for gloss_reconciliation_analysis.py.

Offline harness that measures the Gloss-Reconciliation subagent's flags and the
current snapper against the operator's human sense-labels (Remediation Block 1).
All inputs are already-parsed dict lists; functions are pure so the numbers are
reproducible and CI-checked rather than hand-calculated.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from gloss_reconciliation_analysis import (
    APT,
    WRONG,
    UNKNOWN,
    dedupe_latest,
    count_revisions,
    snap_outcome,
    apt_target_set,
    flag_index,
    is_flagged,
    wilson_ci,
    confusion,
    precision_recall_f1,
)


# --- Fixtures ---------------------------------------------------------------

def label(role, word, snapped, verdict, ts, intended=None, apt=None):
    r = {
        "role": role,
        "word": word,
        "snapped_synset_id": snapped,
        "verdict": verdict,
        "ts": ts,
        "intended_synset_id": intended,
    }
    if apt is not None:
        r["apt_synset_ids"] = apt
    return r


# --- dedupe_latest ----------------------------------------------------------

def test_dedupe_latest_keeps_one_per_endpoint():
    rows = [
        label("topic", "decay", "94423", "unsure", "2026-06-18T13:00:00Z"),
        label("topic", "decay", "94423", "wrong", "2026-06-18T13:05:00Z", intended="999"),
        label("vehicle", "hush", "12", "right", "2026-06-18T13:01:00Z"),
    ]
    out = dedupe_latest(rows)
    assert len(out) == 2
    decay = [r for r in out if r["word"] == "decay"][0]
    assert decay["verdict"] == "wrong"  # latest ts wins


def test_dedupe_latest_distinguishes_endpoints_by_snapped_id():
    rows = [
        label("vehicle", "glance", "1", "right", "2026-06-18T13:00:00Z"),
        label("vehicle", "glance", "2", "wrong", "2026-06-18T13:01:00Z", intended="3"),
    ]
    out = dedupe_latest(rows)
    assert len(out) == 2  # same word, different snapped synset = different endpoints


# --- count_revisions --------------------------------------------------------

def test_count_revisions_counts_changed_minds_only():
    rows = [
        label("topic", "decay", "94423", "unsure", "2026-06-18T13:00:00Z"),
        label("topic", "decay", "94423", "wrong", "2026-06-18T13:05:00Z", intended="9"),
        # re-affirmed (no change) should NOT count
        label("vehicle", "hush", "12", "right", "2026-06-18T13:01:00Z"),
        label("vehicle", "hush", "12", "right", "2026-06-18T13:09:00Z"),
    ]
    assert count_revisions(rows) == 1


# --- snap_outcome -----------------------------------------------------------

def test_snap_outcome_right_is_apt():
    assert snap_outcome(label("v", "w", "1", "right", "t")) == APT


def test_snap_outcome_wrong_is_wrong():
    assert snap_outcome(label("v", "w", "1", "wrong", "t", intended="2")) == WRONG


def test_snap_outcome_rare_ok_is_apt():
    assert snap_outcome(label("v", "w", "1", "rare_ok", "t", intended="2")) == APT


def test_snap_outcome_unsure_is_unknown():
    assert snap_outcome(label("v", "w", "1", "unsure", "t")) == UNKNOWN


def test_snap_outcome_split_snapped_in_apt_is_apt():
    # poly-aptness: the current snap is one of several apt senses
    r = label("v", "w", "1", "split", "t", apt=["1", "2", "3"])
    assert snap_outcome(r) == APT


def test_snap_outcome_split_snapped_not_in_apt_is_wrong():
    # the operator marked OTHER senses apt, not the snapped one
    r = label("v", "w", "1", "split", "t", apt=["2", "3"])
    assert snap_outcome(r) == WRONG


def test_snap_outcome_split_no_apt_recorded_is_unknown():
    r = label("v", "w", "1", "split", "t", apt=[])
    assert snap_outcome(r) == UNKNOWN


# --- apt_target_set ---------------------------------------------------------

def test_apt_target_set_right_is_snapped():
    assert apt_target_set(label("v", "w", "1", "right", "t")) == {"1"}


def test_apt_target_set_wrong_is_intended():
    assert apt_target_set(label("v", "w", "1", "wrong", "t", intended="2")) == {"2"}


def test_apt_target_set_rare_ok_includes_both():
    assert apt_target_set(label("v", "w", "1", "rare_ok", "t", intended="2")) == {"1", "2"}


def test_apt_target_set_split_is_apt_ids():
    r = label("v", "w", "1", "split", "t", apt=["2", "3"])
    assert apt_target_set(r) == {"2", "3"}


def test_apt_target_set_unsure_is_empty():
    assert apt_target_set(label("v", "w", "1", "unsure", "t")) == set()


# --- flag_index / is_flagged ------------------------------------------------

def test_flag_index_and_is_flagged():
    flags = [
        {"role": "topic", "word": "marrow", "synset_id": "61455", "verdict": "RARE_OK"},
        {"role": "vehicle", "word": "hush", "synset_id": "5", "verdict": "WRONG_SENSE"},
    ]
    idx = flag_index(flags)
    assert is_flagged(label("topic", "marrow", "61455", "split", "t"), idx) is True
    assert is_flagged(label("vehicle", "hush", "5", "wrong", "t", intended="6"), idx) is True
    assert is_flagged(label("vehicle", "glow", "9", "right", "t"), idx) is False


# --- wilson_ci --------------------------------------------------------------

def test_wilson_ci_known_value():
    lo, hi = wilson_ci(4, 33)
    # 4/33 ~= 0.121; Wilson 95% interval is roughly [0.048, 0.277]
    assert 0.04 < lo < 0.06
    assert 0.26 < hi < 0.29


def test_wilson_ci_zero_events_is_bounded():
    lo, hi = wilson_ci(0, 10)
    assert lo == 0.0
    assert 0.0 < hi < 0.35


def test_wilson_ci_empty_sample_is_full_interval():
    lo, hi = wilson_ci(0, 0)
    assert (lo, hi) == (0.0, 1.0)


# --- confusion / precision_recall -------------------------------------------

def test_confusion_positive_is_wrong_predicted_is_flagged():
    flags = [{"role": "v", "word": "a", "synset_id": "1", "verdict": "WRONG_SENSE"},
             {"role": "v", "word": "b", "synset_id": "1", "verdict": "WRONG_SENSE"}]
    idx = flag_index(flags)
    labels = [
        label("v", "a", "1", "wrong", "t", intended="9"),   # flagged + wrong  -> TP
        label("v", "b", "1", "right", "t"),                  # flagged + apt    -> FP
        label("v", "c", "1", "wrong", "t", intended="9"),   # unflagged + wrong-> FN
        label("v", "d", "1", "right", "t"),                  # unflagged + apt  -> TN
        label("v", "e", "1", "unsure", "t"),                 # excluded
    ]
    cm = confusion(labels, idx)
    assert cm["tp"] == 1
    assert cm["fp"] == 1
    assert cm["fn"] == 1
    assert cm["tn"] == 1
    assert cm["excluded"] == 1


def test_precision_recall_f1():
    cm = {"tp": 3, "fp": 1, "fn": 1, "tn": 5, "excluded": 0}
    out = precision_recall_f1(cm)
    assert out["precision"] == pytest.approx(0.75)
    assert out["recall"] == pytest.approx(0.75)
    assert out["f1"] == pytest.approx(0.75)


def test_precision_recall_f1_handles_zero_denominators():
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "excluded": 0}
    out = precision_recall_f1(cm)
    assert out["precision"] == 0.0
    assert out["recall"] == 0.0
    assert out["f1"] == 0.0
