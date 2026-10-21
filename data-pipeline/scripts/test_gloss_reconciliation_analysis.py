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
    contamination_rate,
    promiscuity,
    drift,
    resnapper_baseline,
    load_jsonl,
    candidates_by_lemma,
    build_report,
    render_markdown,
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


# --- contamination_rate (silent noise among subagent negatives) --------------

def test_contamination_rate_counts_wrong_among_unflagged():
    flags = [{"role": "v", "word": "flagged", "synset_id": "1", "verdict": "WRONG_SENSE"}]
    idx = flag_index(flags)
    labels = [
        # unflagged endpoints (subagent said "right" by omission):
        label("v", "a", "1", "wrong", "t", intended="9"),   # silent miss
        label("v", "b", "1", "right", "t"),                  # genuinely clean
        label("v", "c", "1", "right", "t"),                  # genuinely clean
        label("v", "d", "1", "unsure", "t"),                 # excluded (no determinate outcome)
        # a flagged endpoint must NOT count toward the unflagged contamination rate:
        label("v", "flagged", "1", "wrong", "t", intended="9"),
    ]
    out = contamination_rate(labels, idx)
    assert out["k"] == 1       # one wrong among unflagged-determinate
    assert out["n"] == 3       # a, b, c (d excluded, flagged excluded)
    assert out["rate"] == pytest.approx(1 / 3)
    assert 0.0 <= out["ci_lo"] <= out["rate"] <= out["ci_hi"] <= 1.0


# --- promiscuity ------------------------------------------------------------

def test_promiscuity_split_rate_and_cardinality():
    labels = [
        label("v", "a", "1", "split", "t", apt=["1", "2"]),       # poly-apt, card 2
        label("v", "b", "1", "split", "t", apt=["1", "2", "3"]),  # poly-apt, card 3
        label("v", "c", "1", "right", "t"),
        label("v", "d", "1", "wrong", "t", intended="9"),
        label("v", "e", "1", "unsure", "t"),                       # excluded from rate base
    ]
    out = promiscuity(labels)
    # 2 splits out of 4 non-unsure labels
    assert out["n_determinate"] == 4
    assert out["n_split"] == 2
    assert out["split_rate"] == pytest.approx(0.5)
    assert out["poly_apt"] == 2          # both splits have >= 2 apt senses
    assert out["apt_cardinality"] == {2: 1, 3: 1}
    assert out["mean_apt_cardinality"] == pytest.approx(2.5)


def test_promiscuity_apt_share_of_candidate_senses():
    labels = [label("v", "glance", "1", "split", "t", apt=["1", "2", "3"])]
    candidates = {"glance": [
        {"synset_id": "1", "pos": "n", "gloss": "", "tagcount": 5},
        {"synset_id": "2", "pos": "v", "gloss": "", "tagcount": 1},
        {"synset_id": "3", "pos": "v", "gloss": "", "tagcount": None},
        {"synset_id": "4", "pos": "n", "gloss": "", "tagcount": None},
    ]}
    out = promiscuity(labels, candidates)
    # operator marked 3 of 4 candidate senses apt
    assert out["mean_apt_share"] == pytest.approx(0.75)


# --- drift (calibration over time) ------------------------------------------

def test_drift_split_rate_rises_across_halves():
    # chronological: first half mostly non-split, second half mostly split
    labels = [
        label("v", "a", "1", "wrong", "2026-06-18T10:00:00Z", intended="9"),
        label("v", "b", "1", "wrong", "2026-06-18T10:01:00Z", intended="9"),
        label("v", "c", "1", "split", "2026-06-18T10:02:00Z", apt=["1", "2"]),
        label("v", "d", "1", "split", "2026-06-18T10:03:00Z", apt=["1", "2"]),
    ]
    out = drift(labels)
    assert out["first"]["split_rate"] == pytest.approx(0.0)
    assert out["second"]["split_rate"] == pytest.approx(1.0)
    assert out["delta"] == pytest.approx(1.0)


# --- resnapper_baseline (dominant-tagcount prior) ---------------------------

def test_resnapper_baseline_dominant_prior_recovers_wrong_snap():
    # current snapper snapped lemma "x" to synset "1" (a process-nominal); the
    # operator's intended sense is "2", which also has the dominant SemCor count.
    labels = [label("topic", "x", "1", "wrong", "t", intended="2")]
    candidates = {"x": [
        {"synset_id": "1", "pos": "n", "gloss": "", "tagcount": 0},
        {"synset_id": "2", "pos": "n", "gloss": "", "tagcount": 9},
    ]}
    out = resnapper_baseline(labels, candidates)
    assert out["n_scored"] == 1
    assert out["current_hits"] == 0           # snapped "1" not in target {2}
    assert out["dominant_hits"] == 1          # argmax tagcount -> "2" in target
    assert out["wrong"]["n"] == 1
    assert out["wrong"]["dominant_hits"] == 1


def test_resnapper_baseline_tiebreak_lowest_id_when_no_tagcount():
    # all tagcounts NULL -> dominant prior ties, breaks to lowest numeric id,
    # mirroring the current lowest-id snapper (so no spurious improvement claimed)
    labels = [label("topic", "y", "10", "right", "t")]
    candidates = {"y": [
        {"synset_id": "10", "pos": "n", "gloss": "", "tagcount": None},
        {"synset_id": "20", "pos": "n", "gloss": "", "tagcount": None},
    ]}
    out = resnapper_baseline(labels, candidates)
    assert out["dominant_pick_for"]["y::10"] == "10"  # lowest-id tie-break


def test_resnapper_baseline_skips_uncovered_targets():
    # operator's intended sense is not among the candidate list -> can't be scored
    labels = [label("topic", "z", "1", "wrong", "t", intended="999")]
    candidates = {"z": [{"synset_id": "1", "pos": "n", "gloss": "", "tagcount": 3}]}
    out = resnapper_baseline(labels, candidates)
    assert out["n_scored"] == 0
    assert out["n_uncovered"] == 1


# --- load_jsonl / candidates_by_lemma ---------------------------------------

def test_load_jsonl_skips_blank_lines(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1}\n\n{"a": 2}\n')
    rows = load_jsonl(p)
    assert rows == [{"a": 1}, {"a": 2}]


def test_candidates_by_lemma_indexes_senses():
    rows = [{"lemma": "glance", "senses": [{"synset_id": "1", "tagcount": 5}]}]
    idx = candidates_by_lemma(rows)
    assert idx["glance"][0]["synset_id"] == "1"


# --- build_report (wiring) --------------------------------------------------

def test_build_report_assembles_all_sections():
    flags = [{"role": "v", "word": "a", "synset_id": "1", "verdict": "WRONG_SENSE"}]
    labels = [
        label("v", "a", "1", "wrong", "2026-06-18T10:00:00Z", intended="2"),  # flagged, TP
        label("v", "b", "1", "right", "2026-06-18T10:01:00Z"),                # unflagged, clean
        label("v", "c", "1", "split", "2026-06-18T10:02:00Z", apt=["1", "2"]),# unflagged, poly-apt
        label("v", "a", "1", "wrong", "2026-06-18T10:03:00Z", intended="2"),  # dup of first
    ]
    candidates = {
        "a": [{"synset_id": "1", "pos": "n", "gloss": "", "tagcount": 0},
              {"synset_id": "2", "pos": "n", "gloss": "", "tagcount": 9}],
        "c": [{"synset_id": "1", "pos": "n", "gloss": "", "tagcount": 1},
              {"synset_id": "2", "pos": "v", "gloss": "", "tagcount": 1}],
    }
    rep = build_report(labels, flags, candidates)
    assert rep["counts"]["n_raw"] == 4
    assert rep["counts"]["n_distinct"] == 3
    assert rep["verdict_distribution"]["wrong"] == 1
    assert rep["strata"]["n_flagged"] == 1
    assert rep["strata"]["n_unflagged"] == 2
    assert "precision" in rep["subagent"]
    assert "rate" in rep["contamination"]
    assert "split_rate" in rep["promiscuity"]
    assert "delta" in rep["drift"]
    assert "dominant_acc" in rep["resnapper"]


def test_render_markdown_contains_key_numbers():
    flags = [{"role": "v", "word": "a", "synset_id": "1", "verdict": "WRONG_SENSE"}]
    labels = [label("v", "a", "1", "wrong", "2026-06-18T10:00:00Z", intended="2")]
    rep = build_report(labels, flags, {})
    md = render_markdown(rep)
    assert isinstance(md, str)
    assert "Gloss-Reconciliation" in md
    assert "Subagent reliability" in md
