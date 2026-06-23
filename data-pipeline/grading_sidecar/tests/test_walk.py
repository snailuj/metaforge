"""Tests for grading_sidecar.walk — the signal-prioritised grading walk.

The walk turns triaged paths into a flat, acquisition-ordered list for next/prev
grading: per-TOPIC dwell (a small contrastive set that also exercises the panel),
topics ordered by contrast potential, already-graded paths skipped.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from grading_sidecar import walk


def _p(topic, vehicle, liveness, sig, *, bad_head=False, leap=False, weak=False):
    return {
        "chain_signature": sig, "topic": topic, "vehicle": vehicle,
        "liveness": liveness, "bad_head": bad_head, "leap": leap, "weak_linkage": weak,
    }


# --- dwell_set --------------------------------------------------------------
def test_dwell_set_picks_live_and_dead_extremes():
    paths = [_p("t", "a", 8, "1"), _p("t", "b", 5, "2"), _p("t", "c", 2, "3")]
    got = {p["chain_signature"] for p in walk.dwell_set(paths)}
    assert "1" in got and "3" in got  # clearest-live (8) and clearest-dead (2)


def test_dwell_set_includes_a_structurally_weak_path():
    # a mid-liveness path with bad_head must be pulled in to exercise that control
    paths = [_p("t", "a", 8, "1"), _p("t", "b", 7, "2"),
             _p("t", "c", 6, "3", bad_head=True), _p("t", "d", 5, "4")]
    got = {p["chain_signature"] for p in walk.dwell_set(paths, n_max=5)}
    assert "3" in got


def test_dwell_set_dedupes_by_vehicle():
    # two paths to the SAME topic->vehicle pairing are redundant for the linkage signal
    paths = [_p("t", "same", 8, "1"), _p("t", "same", 2, "2"), _p("t", "other", 5, "3")]
    got = walk.dwell_set(paths)
    vehicles = [p["vehicle"] for p in got]
    assert len(vehicles) == len(set(vehicles))  # no repeated vehicle


def test_dwell_set_clamps_to_n_max():
    paths = [_p("t", f"v{i}", i, str(i)) for i in range(11)]  # 11 distinct vehicles
    assert len(walk.dwell_set(paths, n_max=4)) == 4


def test_dwell_set_small_topic_returns_all():
    assert len(walk.dwell_set([_p("t", "a", 5, "1")])) == 1
    assert len(walk.dwell_set([_p("t", "a", 8, "1"), _p("t", "b", 2, "2")])) == 2


def test_dwell_set_recovers_weak_path_when_first_candidate_collides():
    # The FIRST weak candidate (lowest liveness) shares a vehicle with the clearest-live
    # pick, so it dedups out. A distinct-vehicle weak path exists but is neither the
    # boundary nor reached by fill (n_max=3) — so only the weak slot can recover it. The
    # weak slot exists to exercise bad_head/leap/linkage controls; it must not silently
    # give up after one colliding candidate.
    paths = [
        _p("t", "shared", 9, "live"),
        _p("t", "d", 1, "dead"),
        _p("t", "shared", 6, "weaklow", bad_head=True),   # first weak candidate, vehicle collides
        _p("t", "other", 7, "weakhigh", bad_head=True),   # distinct-vehicle weak — only the weak slot recovers it
        _p("t", "B", 5, "bound"),                         # the boundary pick (closest to midpoint)
    ]
    got = {p["chain_signature"] for p in walk.dwell_set(paths, n_max=3)}
    assert "weakhigh" in got, f"weak path silently dropped: {got}"


def test_dwell_set_emits_live_dead_weak_boundary_in_order():
    # documented grading order: clearest-live -> clearest-dead -> a weak path -> boundary -> extras
    paths = [
        _p("t", "L", 9, "live"),
        _p("t", "D", 1, "dead"),
        _p("t", "W", 6, "weak", bad_head=True),
        _p("t", "B", 5, "bound"),
        _p("t", "E", 7, "extra"),
    ]
    order = [p["chain_signature"] for p in walk.dwell_set(paths, n_max=5)]
    assert order == ["live", "dead", "weak", "bound", "extra"]


# --- build_walk -------------------------------------------------------------
def test_build_walk_skips_graded():
    paths = [_p("t", "a", 8, "1"), _p("t", "b", 2, "2")]
    out = walk.build_walk(paths, graded_sigs={"1"})
    sigs = {e["chain_signature"] for e in out}
    assert "1" not in sigs and "2" in sigs


def test_build_walk_orders_topics_by_contrast_spread():
    # topic WIDE spans 1..9 (cheap contrast); NARROW spans 5..6 -> WIDE first
    paths = [
        _p("WIDE", "a", 9, "w1"), _p("WIDE", "b", 1, "w2"),
        _p("NARROW", "c", 6, "n1"), _p("NARROW", "d", 5, "n2"),
    ]
    out = walk.build_walk(paths)
    assert out[0]["topic"] == "WIDE"


def test_build_walk_is_topic_grouped_not_per_path_shuffled():
    # you DWELL on a topic (its entries are contiguous), then advance — not interleaved
    paths = [
        _p("A", "a", 9, "a1"), _p("A", "b", 1, "a2"),
        _p("B", "c", 8, "b1"), _p("B", "d", 2, "b2"),
    ]
    out = walk.build_walk(paths)
    topics_in_order = [e["topic"] for e in out]
    # each topic appears in one contiguous run (no A,B,A,B interleaving)
    runs = [t for i, t in enumerate(topics_in_order) if i == 0 or topics_in_order[i - 1] != t]
    assert len(runs) == len(set(runs))


def test_build_walk_entries_carry_dwell_position():
    paths = [_p("A", "a", 9, "a1"), _p("A", "b", 1, "a2")]
    out = walk.build_walk(paths)
    a = [e for e in out if e["topic"] == "A"]
    assert all("dwell_index" in e and "dwell_n" in e for e in a)
    assert a[0]["dwell_n"] == len(a)
    assert sorted(e["dwell_index"] for e in a) == list(range(len(a)))


# --- assemble_paths (join chains x liveness x structural) --------------------
def test_assemble_joins_liveness_and_structural():
    chains = [{"chain_signature": "1", "topic": "t", "vehicle": "a"}]
    paths = walk.assemble_paths(
        chains, liveness_by_sig={"1": 8},
        structural_by_sig={"1": {"bad_head": True, "leap": False, "weak_linkage": True}})
    assert paths[0]["liveness"] == 8
    assert paths[0]["bad_head"] is True and paths[0]["weak_linkage"] is True and paths[0]["leap"] is False


def test_assemble_defaults_missing_liveness_to_midpoint():
    chains = [{"chain_signature": "x", "topic": "t", "vehicle": "a"}]
    paths = walk.assemble_paths(chains, liveness_by_sig={}, structural_by_sig={}, default_liveness=5)
    assert paths[0]["liveness"] == 5  # untriaged chain still appears, mid-ranked


def test_assemble_missing_structural_is_unflagged():
    chains = [{"chain_signature": "x", "topic": "t", "vehicle": "a"}]
    paths = walk.assemble_paths(chains, liveness_by_sig={"x": 6}, structural_by_sig={})
    assert paths[0]["bad_head"] is False and paths[0]["leap"] is False and paths[0]["weak_linkage"] is False


# --- topic_axis_signals (what panel axes a topic's paths can exercise) --------
def test_topic_axis_signals_maps_liveness_and_flags():
    # high-liveness -> metaphor:live, low -> metaphor:dead, flag -> its tag/linkage axis
    paths = [_p("t", "a", 9, "1"), _p("t", "b", 2, "2"),
             _p("t", "c", 6, "3", bad_head=True), _p("t", "d", 5, "4", weak=True)]
    sigs = walk.topic_axis_signals(paths)
    assert "metaphor:live" in sigs          # 9 >= LIVE_THRESHOLD
    assert "metaphor:dead" in sigs          # 2 <= DEAD_THRESHOLD
    assert "tag:bad_head" in sigs
    assert "linkage:bad" in sigs            # weak_linkage predicts a bad-linkage verdict


def test_topic_axis_signals_midband_has_no_metaphor_signal():
    # a topic that is all mid-liveness and unflagged predicts neither live nor dead
    sigs = walk.topic_axis_signals([_p("t", "a", 5, "1"), _p("t", "b", 6, "2")])
    assert "metaphor:live" not in sigs and "metaphor:dead" not in sigs


# --- collected_labels_from_verdicts ------------------------------------------
def test_collected_labels_counts_axes_from_verdicts():
    verdicts = [
        {"linkage": "good", "metaphor": "live", "tags": ["bad_head"]},
        {"linkage": "bad", "metaphor": "dead", "tags": []},
    ]
    c = walk.collected_labels_from_verdicts(verdicts)
    assert c["metaphor:live"] == 1 and c["metaphor:dead"] == 1
    assert c["linkage:good"] == 1 and c["linkage:bad"] == 1
    assert c["tag:bad_head"] == 1


def test_collected_labels_ignores_none_axes():
    # v1 bad_path -> metaphor None; irrelevant -> linkage None; must not count "None" keys
    verdicts = [{"linkage": None, "metaphor": "irrelevant", "tags": []},
                {"linkage": "bad", "metaphor": None, "tags": ["leap"]}]
    c = walk.collected_labels_from_verdicts(verdicts)
    assert c.get("metaphor:irrelevant") == 1
    assert c.get("linkage:bad") == 1
    assert c.get("tag:leap") == 1
    assert "metaphor:None" not in c and "linkage:None" not in c


# --- build_walk label-coverage steering --------------------------------------
def test_build_walk_no_collected_labels_is_pure_spread():
    # steering OFF (None) -> identical to spread ordering (regression guard)
    paths = [
        _p("WIDE", "a", 9, "w1"), _p("WIDE", "b", 1, "w2"),
        _p("NARROW", "c", 6, "n1"), _p("NARROW", "d", 5, "n2"),
    ]
    out = walk.build_walk(paths, collected_labels=None)
    assert out[0]["topic"] == "WIDE"


def test_build_walk_steers_toward_undercollected_axis():
    # both topics flagged (so the flagged-first tiebreak is neutral) and equal spread;
    # live/dead AND tag:leap are saturated, tag:bad_head is starved -> the bad_head
    # topic must surface first purely on the coverage deficit.
    paths = [
        _p("BADHEAD", "a", 8, "h1"), _p("BADHEAD", "b", 2, "h2"), _p("BADHEAD", "c", 5, "h3", bad_head=True),
        _p("LEAP", "d", 8, "l1"), _p("LEAP", "e", 2, "l2"), _p("LEAP", "f", 5, "l3", leap=True),
    ]
    collected = {"metaphor:live": 50, "metaphor:dead": 50, "tag:leap": 50}
    out = walk.build_walk(paths, collected_labels=collected)
    assert out[0]["topic"] == "BADHEAD"


def test_build_walk_steering_can_override_spread():
    # NARROW_FLAG has a small spread but exercises a STARVED axis (bad_head);
    # WIDE_PLAIN has a wide spread but only well-covered axes -> steering flips order.
    paths = [
        _p("NARROW_FLAG", "a", 6, "n1"), _p("NARROW_FLAG", "b", 4, "n2", bad_head=True),
        _p("WIDE_PLAIN", "c", 9, "w1"), _p("WIDE_PLAIN", "d", 1, "w2"),
    ]
    collected = {"metaphor:live": 50, "metaphor:dead": 50}
    out = walk.build_walk(paths, collected_labels=collected)
    assert out[0]["topic"] == "NARROW_FLAG"
