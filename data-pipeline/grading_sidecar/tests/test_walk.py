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
