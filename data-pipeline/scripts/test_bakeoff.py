"""Bake-off harness: candidate-command construction + per-model scoring."""
import bakeoff


def test_build_candidate_cmd_openai_provider():
    cand = {"name": "qwen", "model": "qwen/qwen-2.5-72b", "base_url": "https://or/v1",
            "api_key_env": "OPENROUTER_API_KEY"}
    cmd = bakeoff.build_candidate_cmd(
        cand, topics="t.json", db="db.sqlite", out="out/qwen.jsonl",
        summary="out/qwen.summary.json", python="py", runner="gen.py", max_topics=50)
    # provider + endpoint + both bulk models point at the candidate; tripwire off
    assert "--provider" in cmd and cmd[cmd.index("--provider") + 1] == "openai"
    assert cmd[cmd.index("--base-url") + 1] == "https://or/v1"
    assert cmd[cmd.index("--sonnet-model") + 1] == "qwen/qwen-2.5-72b"
    assert cmd[cmd.index("--haiku-model") + 1] == "qwen/qwen-2.5-72b"
    assert cmd[cmd.index("--api-key-env") + 1] == "OPENROUTER_API_KEY"
    assert cmd[cmd.index("--max-topics") + 1] == "50"
    assert "--no-tripwire" in cmd


def test_build_candidate_cmd_claude_baseline():
    cand = {"name": "claude", "model": "claude-sonnet-4-6", "provider": "claude"}
    cmd = bakeoff.build_candidate_cmd(
        cand, topics="t.json", db="db.sqlite", out="o.jsonl",
        summary="s.json", python="py", runner="gen.py", max_topics=50)
    assert cmd[cmd.index("--provider") + 1] == "claude"
    assert "--base-url" not in cmd  # claude path needs no endpoint


def test_build_candidate_cmd_reasoning_off_adds_flag():
    cand = {"name": "x", "model": "m", "base_url": "u", "reasoning": False}
    cmd = bakeoff.build_candidate_cmd(cand, topics="t", db="d", out="o", summary="s",
                                      python="py", runner="r", max_topics=10)
    assert "--reasoning-off" in cmd


def test_build_candidate_cmd_reasoning_on_omits_flag():
    cand = {"name": "x", "model": "m", "base_url": "u"}  # default = reasoning on
    cmd = bakeoff.build_candidate_cmd(cand, topics="t", db="d", out="o", summary="s",
                                      python="py", runner="r", max_topics=10)
    assert "--reasoning-off" not in cmd


def test_summarise_model_metrics():
    rows = [
        {"topic_synset_id": "1", "vehicle_synset_id": "9", "vehicle": "a",
         "chain": [{"gloss": "x"}, {"gloss": "y"}]},
        {"topic_synset_id": "1", "vehicle_synset_id": "1", "vehicle": "b",
         "chain": [{"gloss": "x"}, {"gloss": ""}]},  # one missing gloss + self-metaphor
    ]
    s = bakeoff.summarise_model(rows)
    assert s["chains"] == 2
    assert s["topics"] == 1
    assert s["distinct_vehicles"] == 2
    assert s["gloss_coverage"] == 0.75      # 3 of 4 nodes glossed
    assert s["self_metaphor"] == 1


def test_summarise_model_empty():
    s = bakeoff.summarise_model([])
    assert s["chains"] == 0 and s["gloss_coverage"] == 0


def test_chain_gloss_accuracy_pools_nodes_and_resumes(tmp_path):
    rows = [
        {"chain_signature": "a", "chain": [{"head": "x", "phrase": "x", "gloss": "g"},
                                           {"head": "y", "phrase": "y", "gloss": "g"}]},
        {"chain_signature": "b", "chain": [{"head": "z", "phrase": "z", "gloss": "g"}]},
    ]

    def judge(prompt, model, max_retries=2):
        n = prompt.count("(head:")
        return {"nodes": [{"accurate": i == 0} for i in range(n)]}  # first node ok, rest wrong

    cp = str(tmp_path / "cp.jsonl")
    # chain a: 1/2 ok; chain b: 1/1 ok -> pooled 2/3
    acc1 = bakeoff.gloss_accuracy(rows, 10, judge, "m", label="L", checkpoint_path=cp)
    assert acc1 == round(2 / 3, 3)

    calls = {"n": 0}

    def judge2(prompt, model, max_retries=2):
        calls["n"] += 1
        return {"nodes": [{"accurate": True}]}

    acc2 = bakeoff.gloss_accuracy(rows, 10, judge2, "m", label="L", checkpoint_path=cp)
    assert acc2 == round(2 / 3, 3) and calls["n"] == 0  # resumed from checkpoint, no new calls


def test_judge_slug_safe_for_filename():
    # slashes (and other path-hostile chars) collapse to underscores; dots/dashes kept
    assert bakeoff.judge_slug("anthropic/claude-sonnet-4.6") == "anthropic_claude-sonnet-4.6"
    assert bakeoff.judge_slug("anthropic/claude-haiku-4.5") == "anthropic_claude-haiku-4.5"


def _live_rows(n):
    return [{"chain_signature": chr(ord("a") + i), "topic": "t", "vehicle": "v",
             "chain": [{"phrase": "p"}]} for i in range(n)]


def test_proxy_live_rate_counts_live_not_dict_truthiness(tmp_path):
    rows = _live_rows(4)
    verdicts = iter(["live", "dead", "live", "irrelevant"])  # exactly 2 of 4 live

    def fake(prompt, model):
        return {"verdict": next(verdicts)}

    # old code did `if judge_chain(...)` on a dict (always truthy) -> ~1.0; correct is 0.5
    rate = bakeoff.proxy_live_rate(rows, 10, prompt_fn=fake, model="m",
                                   label="L", checkpoint_path=str(tmp_path / "cp.jsonl"))
    assert rate == 0.5


def test_proxy_live_rate_skips_failed_judge_no_deflate(tmp_path):
    rows = _live_rows(2)
    seq = iter(["boom", "live"])

    def fake(prompt, model):
        if next(seq) == "boom":
            raise RuntimeError("judge down")  # judge_chain catches -> ok=False
        return {"verdict": "live"}

    # one judge call fails (skipped, not counted dead); 1 live / 1 counted -> 1.0, not 0.5
    rate = bakeoff.proxy_live_rate(rows, 10, prompt_fn=fake, model="m",
                                   label="L", checkpoint_path=str(tmp_path / "cp.jsonl"))
    assert rate == 1.0


def test_proxy_live_rate_resumes_from_checkpoint(tmp_path):
    rows = _live_rows(2)
    cp = str(tmp_path / "cp.jsonl")
    rate1 = bakeoff.proxy_live_rate(rows, 10, prompt_fn=lambda p, model: {"verdict": "live"},
                                    model="m", label="L", checkpoint_path=cp)
    assert rate1 == 1.0

    calls = {"n": 0}

    def fake2(prompt, model):
        calls["n"] += 1
        return {"verdict": "dead"}

    rate2 = bakeoff.proxy_live_rate(rows, 10, prompt_fn=fake2, model="m", label="L", checkpoint_path=cp)
    assert rate2 == 1.0 and calls["n"] == 0  # resumed, no new judge calls
