"""Tests for judge_harness — topic-grouped agreement harness for candidate judges.

Pure-Python stub judges only (no LLM, no IO). The headline correctness property
is leakage-freedom: leave-one-topic-out folds must never share a topic between
train and test, and few-shot examples handed to the judge must never come from
the held-out topic — at the fold level AND at the prompt level.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import judge_harness as jh  # noqa: E402


# --- fixtures -----------------------------------------------------------------

def _row(sig: str, topic_id: str, y: int, axis_key: str = "y_live") -> dict:
    """A synthetic corpus ROW honouring the shared interface contract keys."""
    return {
        "chain_signature": sig,
        "topic": f"topic-{topic_id}",
        "topic_synset_id": str(topic_id),
        "vehicle": "swarm",
        "vehicle_synset_id": "9",
        "metaphor": "live" if y else "dead",
        "linkage_effective": "good",
        "tags": [],
        "notes": "",
        "ts": "2026-06-01T00:00:00+00:00",
        axis_key: y,
    }


def _corpus(n_topics: int = 10, per_topic: int = 8, axis_key: str = "y_live") -> list[dict]:
    """Every topic both-class (alternating labels) so no fold is single-class."""
    return [
        _row(f"t{t}-{i}", f"T{t}", i % 2, axis_key)
        for t in range(n_topics)
        for i in range(per_topic)
    ]


def _perfect(axis_key: str):
    return lambda few_shot, item: int(item[axis_key])


# --- topic_folds: leakage + coverage (THE load-bearing test) --------------------

def test_topic_folds_no_leakage_and_full_coverage_per_repeat():
    rows = _corpus(n_topics=6, per_topic=4)
    all_topics = {r["topic_synset_id"] for r in rows}
    n_repeats = 3
    folds = list(jh.topic_folds(rows, n_repeats=n_repeats, seed=0))
    assert len(folds) == n_repeats * len(all_topics)

    for rep in range(n_repeats):
        held_out = []
        for train, test in folds[rep * len(all_topics):(rep + 1) * len(all_topics)]:
            train_topics = {r["topic_synset_id"] for r in train}
            test_topics = {r["topic_synset_id"] for r in test}
            assert len(test_topics) == 1                     # leave-ONE-topic-out
            assert not (train_topics & test_topics)          # no topic in both sides
            assert train_topics | test_topics == all_topics  # nothing silently dropped
            held_out.extend(test_topics)
        # every topic held out exactly once per repeat
        assert sorted(held_out) == sorted(all_topics)


def test_topic_folds_deterministic_for_seed():
    rows = _corpus(n_topics=5, per_topic=4)

    def sig_sequence(seed):
        return [tuple(r["chain_signature"] for r in test)
                for _, test in jh.topic_folds(rows, n_repeats=2, seed=seed)]

    assert sig_sequence(7) == sig_sequence(7)
    assert sig_sequence(7) != sig_sequence(8)


def test_run_axis_prompt_level_leakage_guard():
    """The judge itself observes its inputs: few-shot must never share the
    held-out item's topic, and must be drawn from train rows only."""
    rows = _corpus(n_topics=6, per_topic=4)
    all_sigs = {r["chain_signature"] for r in rows}
    seen = {"calls": 0}

    def spy_judge(few_shot, item):
        seen["calls"] += 1
        assert few_shot, "few-shot should be non-empty for this fixture"
        for ex in few_shot:
            assert ex["topic_synset_id"] != item["topic_synset_id"]
            assert ex["chain_signature"] != item["chain_signature"]
            assert ex["chain_signature"] in all_sigs
        return int(item["y_live"])

    jh.run_axis(rows, spy_judge, "y_live", k_shot=4, n_repeats=2, seed=0)
    assert seen["calls"] == len(rows) * 2


# --- select_few_shot ------------------------------------------------------------

def test_few_shot_class_balanced_and_deterministic():
    train = _corpus(n_topics=4, per_topic=6)
    train_sigs = {r["chain_signature"] for r in train}
    few = jh.select_few_shot(train, k=4, seed=3, balance_key="y_live")
    assert len(few) == 4
    assert sum(r["y_live"] for r in few) == 2                 # 2 positive / 2 negative
    assert {r["chain_signature"] for r in few} <= train_sigs  # drawn ONLY from train
    again = jh.select_few_shot(train, k=4, seed=3, balance_key="y_live")
    assert [r["chain_signature"] for r in few] == [r["chain_signature"] for r in again]


def test_few_shot_short_class_tops_up_from_other():
    # One lonely positive: balance is impossible, but k must still be honoured.
    train = [_row("p0", "T0", 1)] + [_row(f"n{i}", f"T{i % 3}", 0) for i in range(8)]
    few = jh.select_few_shot(train, k=4, seed=0, balance_key="y_live")
    assert len(few) == 4
    assert sum(r["y_live"] for r in few) == 1                 # the only positive is in


def test_few_shot_k_larger_than_train_returns_all():
    train = [_row("a", "T0", 1), _row("b", "T1", 0)]
    few = jh.select_few_shot(train, k=10, seed=0, balance_key="y_live")
    assert {r["chain_signature"] for r in few} == {"a", "b"}


# --- run_axis: stub-judge calibration --------------------------------------------

def test_perfect_stub_scores_kappa_one():
    rows = _corpus(n_topics=8, per_topic=6)
    result = jh.run_axis(rows, _perfect("y_live"), "y_live",
                         k_shot=4, n_repeats=3, seed=0)
    assert result["kappa"] == pytest.approx(1.0)
    assert result["kappa_band"] == [pytest.approx(1.0), pytest.approx(1.0)]
    assert result["accuracy"] == pytest.approx(1.0)
    assert result["majority_baseline"] == pytest.approx(0.5)
    assert result["n_items"] == len(rows) * 3
    assert result["n_scored"] == result["n_items"]
    assert result["n_abstain"] == 0
    # perfect judge -> zero off-diagonal mass
    (tn, fp), (fn, tp) = result["confusion"]
    assert fp == 0 and fn == 0 and tn > 0 and tp > 0
    assert len(result["per_repeat"]) == 3
    assert all(r["kappa"] == pytest.approx(1.0) for r in result["per_repeat"])


def test_random_stub_scores_near_zero_kappa():
    rows = _corpus(n_topics=10, per_topic=8)
    rng = random.Random(0)
    result = jh.run_axis(rows, lambda fs, item: rng.randint(0, 1), "y_live",
                         k_shot=4, n_repeats=3, seed=0)
    assert abs(result["kappa"]) < 0.25
    assert result["n_scored"] == len(rows) * 3


def test_run_axis_works_on_construction_axis_key():
    rows = _corpus(n_topics=4, per_topic=4, axis_key="y_link")
    result = jh.run_axis(rows, _perfect("y_link"), "y_link",
                         k_shot=2, n_repeats=2, seed=1)
    assert result["kappa"] == pytest.approx(1.0)


# --- run_axis: abstention + fold guards -------------------------------------------

def test_abstaining_judge_counted_and_excluded_not_crashed():
    rows = _corpus(n_topics=6, per_topic=4)
    perfect = _perfect("y_live")

    def flaky(few_shot, item):
        if item["chain_signature"] == "t0-0":
            raise ValueError("parse failure")  # any judge error = abstention
        return perfect(few_shot, item)

    result = jh.run_axis(rows, flaky, "y_live", k_shot=4, n_repeats=3, seed=0)
    assert result["n_abstain"] == 3                        # once per repeat
    assert result["n_scored"] == result["n_items"] - 3
    assert result["kappa"] == pytest.approx(1.0)           # abstentions excluded from kappa


def test_single_class_fold_skipped_not_crashed():
    mixed = _corpus(n_topics=4, per_topic=4)
    pure = [_row(f"pure{i}", "PURE", 1) for i in range(4)]  # test side would be one class
    result = jh.run_axis(mixed + pure, _perfect("y_live"), "y_live",
                         k_shot=4, n_repeats=2, seed=0)
    assert result["n_folds_skipped"] == 2                  # the PURE fold, once per repeat
    assert result["n_items"] == len(mixed) * 2             # skipped fold's items never judged
    assert result["kappa"] == pytest.approx(1.0)


def test_keyboard_interrupt_propagates():
    rows = _corpus(n_topics=4, per_topic=4)

    def interrupted(few_shot, item):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        jh.run_axis(rows, interrupted, "y_live", k_shot=2, n_repeats=1, seed=0)


def test_session_limit_error_propagates_by_class_name():
    # Duck-typed by name so the harness needs no judge_llm/claude_client import.
    class SessionLimitError(Exception):
        pass

    rows = _corpus(n_topics=4, per_topic=4)

    def limited(few_shot, item):
        raise SessionLimitError("429 session limit")

    with pytest.raises(SessionLimitError):
        jh.run_axis(rows, limited, "y_live", k_shot=2, n_repeats=1, seed=0)


# --- report + CLI surface ----------------------------------------------------------

def test_render_markdown_report_shape():
    rows = _corpus(n_topics=5, per_topic=4)
    result = jh.run_axis(rows, _perfect("y_live"), "y_live",
                         k_shot=2, n_repeats=2, seed=0)
    md = jh.render_markdown_report(result, title="Stage 1 — construction (stub)")
    assert md.startswith("# Stage 1 — construction (stub)")
    assert "kappa" in md.lower()
    assert "majority" in md.lower()
    assert "| repeat |" in md.lower()
    assert "abstentions" in md.lower()


def test_axis_keys_contract():
    assert jh.AXIS_KEYS == {"construction": "y_link", "liveness": "y_live"}


def test_arg_parser_defaults():
    args = jh._build_arg_parser().parse_args(
        ["--axis", "construction", "--judge", "stub-perfect", "--gold", "g.jsonl"])
    assert args.axis == "construction"
    assert args.judge == "stub-perfect"
    assert args.k_shot == 6
    assert args.n_repeats == 5
    assert args.seed == 0
    assert args.grading_dir is None
    assert args.model is None and args.cache is None and args.output is None


def test_arg_parser_requires_gold():
    # judge_corpus.load_resolved has a deliberately required path — the CLI must
    # not advertise a default that does not exist (verify finding, 2026-06-12).
    with pytest.raises(SystemExit):
        jh._build_arg_parser().parse_args(["--axis", "construction", "--judge", "stub-perfect"])


def _v2_gold(ts, sig, metaphor, topic, tsid):
    return {"schema_version": "judgement.v2", "ts": ts, "judged_by": "julian",
            "round": 1, "topic": topic, "topic_synset_id": tsid, "vehicle": "swarm",
            "vehicle_synset_id": "9", "proposer": "sonnet", "chain_signature": sig,
            "linkage": "good", "metaphor": metaphor, "tiers": [], "tags": [],
            "confidence": "high", "notes": "", "supersedes_ts": None}


def _chain_v1(sig, topic, tsid):
    return {"schema_version": "chain.v1", "topic": topic, "topic_synset_id": tsid,
            "vehicle": "swarm", "vehicle_synset_id": "9", "proposer": "sonnet",
            "round": 1, "chain_signature": sig,
            "chain": [{"phrase": topic, "head": topic, "synset_id": tsid},
                      {"phrase": "shoal", "head": "shoal", "synset_id": "5"},
                      {"phrase": "swarm", "head": "swarm", "synset_id": "9"}],
            "generated_at": "2026-06-01T00:00:00+00:00"}


def test_load_rows_attaches_context_from_grading_dir(tmp_path):
    # End-to-end regression for the --grading-dir CLI path (verify finding: the
    # directory was handed to load_glosses, which wants the glosses FILE).
    import json as _json
    sig = "a" * 64
    gold = tmp_path / "judgements.jsonl"
    gold.write_text(_json.dumps(_v2_gold("2026-06-01T10:00:00+00:00", sig, "live",
                                         "anxiety", "72810")) + "\n")
    (tmp_path / "sonnet_chains_provisional_r1.jsonl").write_text(
        _json.dumps(_chain_v1(sig, "anxiety", "72810")) + "\n")
    (tmp_path / "chain_glosses_provisional.jsonl").write_text(
        _json.dumps({"synset_id": "72810", "pos": "n", "definition": "a worried state"}) + "\n")

    rows = jh._load_rows("liveness", str(gold), str(tmp_path))
    assert len(rows) == 1
    assert rows[0]["chain_missing"] is False
    assert len(rows[0]["chain"]) == 3
    assert rows[0]["topic_gloss"] == {"pos": "n", "definition": "a worried state"}
