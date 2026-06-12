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


# --- checkpointing + observability (batch practice, 2026-06-12 operator finding:
# an all-or-nothing -o write threw away a 99%-complete run when the session
# limit hit; only the call-level cache saved the spend) ------------------------

def test_checkpoint_fn_called_per_repeat_with_partials():
    rows = _corpus(4, 4)
    payloads = []
    result = jh.run_axis(rows, lambda fs, item: int(item["y_live"]), "y_live",
                         k_shot=2, n_repeats=3, seed=0, checkpoint_fn=payloads.append)
    assert len(payloads) == 3                       # one flush per completed repeat
    assert all(p["complete"] is False for p in payloads)
    assert [len(p["per_repeat"]) for p in payloads] == [1, 2, 3]
    assert result["complete"] is True
    assert result["elapsed_s"] >= 0
    import json as _json
    _json.dumps(payloads[-1])                       # checkpoint payloads must be JSON-safe


def test_session_limit_flushes_partial_checkpoint_before_raising():
    class SessionLimitError(Exception):
        pass

    rows = _corpus(4, 4)
    calls = {"n": 0}

    def limited_judge(few_shot, item):
        calls["n"] += 1
        if calls["n"] == 7:
            raise SessionLimitError("429 session limit")
        return int(item["y_live"])

    payloads = []
    with pytest.raises(SessionLimitError):
        jh.run_axis(rows, limited_judge, "y_live", k_shot=2, n_repeats=3, seed=0,
                    checkpoint_fn=payloads.append)
    assert payloads, "halt must flush a partial result before re-raising"
    last = payloads[-1]
    assert last["halted"] == "session_limit"
    assert last["complete"] is False
    assert last["n_scored"] == 6                    # everything scored pre-halt is kept
    assert last["per_repeat"][-1].get("partial") is True


def test_heartbeat_logs_progress(monkeypatch, caplog):
    import logging as _logging
    monkeypatch.setattr(jh, "_HEARTBEAT_EVERY", 5)
    rows = _corpus(4, 4)
    with caplog.at_level(_logging.INFO):
        jh.run_axis(rows, lambda fs, item: int(item["y_live"]), "y_live",
                    k_shot=2, n_repeats=2, seed=0)
    beats = [r for r in caplog.records if "progress:" in r.getMessage()]
    assert beats, "expected periodic progress heartbeats at INFO"
    assert "eta" in beats[0].getMessage()


def test_atomic_write_json(tmp_path):
    target = tmp_path / "out.json"
    jh._atomic_write_json(str(target), {"a": 1})
    import json as _json
    assert _json.loads(target.read_text()) == {"a": 1}
    assert not (tmp_path / "out.json.tmp").exists()


def test_main_session_limit_exits_75_with_partial_file(tmp_path, monkeypatch):
    class SessionLimitError(Exception):
        pass

    def fake_run_axis(rows, judge_fn, axis_key, *, checkpoint_fn=None, **kw):
        if checkpoint_fn:
            checkpoint_fn({"complete": False, "halted": "session_limit",
                           "n_scored": 3, "per_repeat": []})
        raise SessionLimitError("429 session limit")

    import json as _json
    gold = tmp_path / "gold.jsonl"
    gold.write_text("\n".join(_json.dumps(_v2_gold(
        f"2026-06-01T10:0{i}:00+00:00", c * 64, m, t, tid))
        for i, (c, m, t, tid) in enumerate([("a", "live", "anxiety", "1"),
                                            ("b", "dead", "anxiety", "1"),
                                            ("c", "live", "anchor", "2"),
                                            ("d", "dead", "anchor", "2")])) + "\n")
    out = tmp_path / "result.json"
    monkeypatch.setattr(jh, "run_axis", fake_run_axis)
    rc = jh.main(["--axis", "liveness", "--judge", "stub-perfect",
                  "--gold", str(gold), "-o", str(out)])
    assert rc == 75                                  # EX_TEMPFAIL: resumable halt
    saved = _json.loads(out.read_text())
    assert saved["halted"] == "session_limit"
    assert saved["judge"] == "stub-perfect"          # run metadata rides every flush


def test_main_writes_complete_result(tmp_path):
    import json as _json
    gold = tmp_path / "gold.jsonl"
    gold.write_text("\n".join(_json.dumps(_v2_gold(
        f"2026-06-01T10:0{i}:00+00:00", c * 64, m, t, tid))
        for i, (c, m, t, tid) in enumerate([("a", "live", "anxiety", "1"),
                                            ("b", "dead", "anxiety", "1"),
                                            ("c", "live", "anchor", "2"),
                                            ("d", "dead", "anchor", "2")])) + "\n")
    out = tmp_path / "result.json"
    rc = jh.main(["--axis", "liveness", "--judge", "stub-perfect",
                  "--gold", str(gold), "-o", str(out), "--n-repeats", "2"])
    assert rc == 0
    saved = _json.loads(out.read_text())
    assert saved["complete"] is True
    assert saved["judge"] == "stub-perfect" and "git_commit" in saved


# --- session-limit auto-resume (operator finding 2026-06-12: the 429 message
# carries the reset time — parse it and wait, don't crash) ---------------------

def test_parse_reset_utc_variants():
    import datetime as dt
    now = dt.datetime(2026, 6, 12, 14, 0, tzinfo=dt.timezone.utc)
    at = jh._parse_reset_utc('429; "You\'ve hit your session limit · resets 5:30pm (UTC)"', now)
    assert (at.hour, at.minute, at.day) == (17, 30, 12)        # later today
    at = jh._parse_reset_utc("session limit · resets 10am (UTC)",
                             dt.datetime(2026, 6, 12, 18, 0, tzinfo=dt.timezone.utc))
    assert (at.hour, at.minute, at.day) == (10, 0, 13)         # already past -> tomorrow
    at = jh._parse_reset_utc("resets 12am (UTC)", now)
    assert (at.hour, at.day) == (0, 13)                        # midnight = start of tomorrow
    assert jh._parse_reset_utc("no time in here", now) is None


def test_main_waits_for_reset_then_resumes(tmp_path, monkeypatch):
    class SessionLimitError(Exception):
        pass

    import json as _json
    calls = {"n": 0}

    def flaky_run_axis(rows, judge_fn, axis_key, *, checkpoint_fn=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            if checkpoint_fn:
                checkpoint_fn({"complete": False, "halted": "session_limit",
                               "n_scored": 3, "per_repeat": []})
            raise SessionLimitError("hit your session limit · resets 5:30pm (UTC)")
        return {"complete": True, "kappa": 1.0, "kappa_band": [1.0, 1.0],
                "accuracy": 1.0, "majority_baseline": 0.5, "confusion": [[1, 0], [0, 1]],
                "n_items": 2, "n_scored": 2, "n_abstain": 0, "n_folds_skipped": 0,
                "n_topics": 2, "per_repeat": [], "halted": None, "elapsed_s": 1.0,
                "items_per_s": 2.0, "axis_key": axis_key,
                "config": {"k_shot": 6, "n_repeats": 5, "seed": 0}}

    slept = []
    monkeypatch.setattr(jh, "run_axis", flaky_run_axis)
    monkeypatch.setattr(jh, "_sleep", slept.append)
    gold = tmp_path / "gold.jsonl"
    gold.write_text(_json.dumps(_v2_gold("2026-06-01T10:00:00+00:00", "a" * 64,
                                         "live", "anxiety", "1")) + "\n")
    out = tmp_path / "result.json"
    rc = jh.main(["--axis", "liveness", "--judge", "stub-perfect",
                  "--gold", str(gold), "-o", str(out)])
    assert rc == 0
    assert calls["n"] == 2                          # halted once, resumed once
    assert len(slept) == 1 and slept[0] > 0         # really waited for the reset
    assert _json.loads(out.read_text())["complete"] is True


def test_main_no_wait_flag_halts_75(tmp_path, monkeypatch):
    class SessionLimitError(Exception):
        pass

    import json as _json

    def limited_run_axis(rows, judge_fn, axis_key, *, checkpoint_fn=None, **kw):
        raise SessionLimitError("hit your session limit · resets 5:30pm (UTC)")

    slept = []
    monkeypatch.setattr(jh, "run_axis", limited_run_axis)
    monkeypatch.setattr(jh, "_sleep", slept.append)
    gold = tmp_path / "gold.jsonl"
    gold.write_text(_json.dumps(_v2_gold("2026-06-01T10:00:00+00:00", "a" * 64,
                                         "live", "anxiety", "1")) + "\n")
    rc = jh.main(["--axis", "liveness", "--judge", "stub-perfect",
                  "--gold", str(gold), "--no-wait-on-limit"])
    assert rc == 75
    assert slept == []                              # the flag means halt, never sleep
