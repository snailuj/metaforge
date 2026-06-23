"""Tests for grading_sidecar.regrade — blind re-grade sampling + self-agreement.

The blind re-grade measures the operator's intra-rater reliability floor (the
audit's universal prerequisite: no κ gate or concordance lift is interpretable
without it). Safety property: regrades live in a SEPARATE JSONL and never touch
the gold file — resolve_verdicts is latest-wins per chain_signature, so a
regrade in the main file would silently replace the original verdict.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from grading_sidecar import regrade


def _v2(ts, sig, metaphor, *, topic="anxiety", tsid="72810", linkage="good",
        tags=None, supersedes=None):
    return {"schema_version": "judgement.v2", "ts": ts, "topic": topic,
            "topic_synset_id": tsid, "vehicle": "swarm", "vehicle_synset_id": "9",
            "chain_signature": sig, "linkage": linkage, "metaphor": metaphor,
            "tiers": [], "tags": tags or [], "confidence": "high",
            "supersedes_ts": supersedes}


# --- sample_regrade ---

def test_sample_excludes_recent_and_caps_n():
    rows = [
        _v2("2026-06-01T10:00:00+00:00", "old1", "live"),
        _v2("2026-06-02T10:00:00+00:00", "old2", "dead"),
        _v2("2026-06-11T10:00:00+00:00", "fresh", "live"),   # graded yesterday
    ]
    sample = regrade.sample_regrade(rows, n=10, min_age_days=3,
                                    today="2026-06-12", seed=1)
    sigs = {s["chain_signature"] for s in sample}
    assert "fresh" not in sigs            # too recent — re-grading tests memory, not stability
    assert sigs == {"old1", "old2"}       # n caps at what is eligible


def test_sample_only_resolved_live_dead():
    rows = [
        _v2("2026-06-01T09:00:00+00:00", "a", "dead"),
        _v2("2026-06-01T10:00:00+00:00", "a", "live"),                      # regrade: latest wins
        _v2("2026-06-01T10:01:00+00:00", "b", "irrelevant"),                # excluded class
        _v2("2026-06-01T10:02:00+00:00", "c", "dead",
            supersedes="2026-06-01T08:00:00+00:00"),
        _v2("2026-06-01T08:00:00+00:00", "d", "live"),                      # superseded by c's marker
    ]
    sample = regrade.sample_regrade(rows, n=10, min_age_days=1,
                                    today="2026-06-12", seed=1)
    by_sig = {s["chain_signature"]: s for s in sample}
    assert "b" not in by_sig                       # irrelevant never sampled
    assert "d" not in by_sig                       # superseded ts dropped
    assert by_sig["a"]["metaphor"] == "live"       # resolved verdict rides along (server-side only)


def test_sample_deterministic_for_seed():
    rows = [_v2(f"2026-06-01T10:0{i}:00+00:00", f"s{i}", "live" if i % 2 else "dead")
            for i in range(8)]
    s1 = regrade.sample_regrade(rows, n=4, min_age_days=1, today="2026-06-12", seed=7)
    s2 = regrade.sample_regrade(rows, n=4, min_age_days=1, today="2026-06-12", seed=7)
    assert [x["chain_signature"] for x in s1] == [x["chain_signature"] for x in s2]


def test_sample_stratifies_by_metaphor_class():
    rows = ([_v2(f"2026-06-01T10:0{i}:00+00:00", f"L{i}", "live") for i in range(6)]
            + [_v2(f"2026-06-01T11:0{i}:00+00:00", f"D{i}", "dead") for i in range(3)])
    sample = regrade.sample_regrade(rows, n=3, min_age_days=1, today="2026-06-12", seed=3)
    lives = sum(1 for s in sample if s["metaphor"] == "live")
    assert len(sample) == 3
    assert lives == 2                              # 6:3 corpus -> 2:1 sample


# --- self_agreement ---

def _pair(sig, orig_m, re_m, *, orig_link="good", re_link="good",
          orig_tags=None, re_tags=None):
    orig = _v2("2026-06-01T10:00:00+00:00", sig, orig_m, linkage=orig_link, tags=orig_tags)
    re_ = _v2("2026-06-12T10:00:00+00:00", sig, re_m, linkage=re_link, tags=re_tags)
    return orig, re_


def test_self_agreement_perfect():
    pairs = [_pair("s1", "live", "live"), _pair("s2", "dead", "dead")]
    rep = regrade.self_agreement([p[0] for p in pairs], [p[1] for p in pairs])
    assert rep["n_pairs"] == 2
    assert rep["metaphor"]["agreement"] == 1.0
    assert rep["metaphor"]["kappa"] == 1.0


def test_self_agreement_known_kappa():
    # orig: L L D D ; regrade: L D D D -> po=0.75, pe=0.5, kappa=0.5
    pairs = [_pair("s1", "live", "live"), _pair("s2", "live", "dead"),
             _pair("s3", "dead", "dead"), _pair("s4", "dead", "dead")]
    rep = regrade.self_agreement([p[0] for p in pairs], [p[1] for p in pairs])
    assert rep["metaphor"]["agreement"] == 0.75
    assert rep["metaphor"]["kappa"] == 0.5


def test_self_agreement_ignores_unmatched_sigs():
    o1, r1 = _pair("s1", "live", "live")
    orphan = _v2("2026-06-12T10:05:00+00:00", "nomatch", "dead")
    rep = regrade.self_agreement([o1], [r1, orphan])
    assert rep["n_pairs"] == 1


def test_self_agreement_linkage_uses_effective_rule():
    # Original: linkage good but tagged leap (forcing -> effective bad).
    # Regrade: explicit bad. These AGREE under the effective rule.
    o, r = _pair("s1", "dead", "dead", orig_link="good", orig_tags=["leap"], re_link="bad")
    rep = regrade.self_agreement([o], [r])
    assert rep["linkage"]["agreement"] == 1.0


def test_self_agreement_empty_is_safe():
    rep = regrade.self_agreement([], [])
    assert rep["n_pairs"] == 0
    assert rep["metaphor"]["kappa"] is None        # undefined, never a crash
