#!/usr/bin/env python3
"""Invariant #2: a STABLE, variance-characterised benchmark of baseline metaphor
generation cost (Haiku vehicle-proposal + Sonnet chain), before any 100k
extrapolation. Uses the REAL prompts (metaphor_spike_1a.build_apt_prompt,
run_chain_spike.build_prompt). Captures total_cost_usd + latency + cache
dynamics per call from the claude CLI JSON. Cold (first) vs warm (cache-hit)
costs are reported separately — production batches run warm.

Spend is tracked: every call's total_cost_usd is logged to
artifacts/generation_cost_log.jsonl and summed.
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path("/home/agent/projects/metaforge")
sys.path.insert(0, str(ROOT / "data-pipeline/scripts"))
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "data-pipeline/grading_sidecar"))

from metaphor_spike_1a import build_apt_prompt           # noqa: E402
from run_chain_spike import build_prompt as build_chain_prompt  # noqa: E402

APT = ROOT / "data-pipeline/output/metaphor_spike_apt_phase2_20260525T004154.jsonl"
COSTLOG = ROOT / "docs/inbox/2026-06-03-context-free-edges/artifacts/generation_cost_log.jsonl"
EMPTY_MCP = str(ROOT / "lib/empty_mcp.json")


def cli_call(prompt: str, model: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    cmd = ["claude", "-p", "--output-format", "json", "--model", model,
           "--max-turns", "1", "--no-session-persistence",
           "--strict-mcp-config", "--mcp-config", EMPTY_MCP]
    t = time.time()
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                          timeout=900, env=env)
    wall = time.time() - t
    try:
        j = json.loads(proc.stdout)
    except Exception:
        return {"ok": False, "wall_s": wall, "err": proc.stdout[:200] + proc.stderr[:200]}
    u = j.get("usage", {})
    rec = {
        "ok": not j.get("is_error", False),
        "model": model,
        "wall_s": round(wall, 1),
        "duration_ms": j.get("duration_ms"),
        "cost_usd": j.get("total_cost_usd"),
        "in_tok": u.get("input_tokens"),
        "out_tok": u.get("output_tokens"),
        "cache_creation": u.get("cache_creation_input_tokens"),
        "cache_read": u.get("cache_read_input_tokens"),
        "result_len": len(j.get("result", "")),
    }
    with open(COSTLOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def load_topics(words):
    out = {}
    for l in APT.read_text().splitlines():
        if not l.strip():
            continue
        d = json.loads(l)
        if d["topic"] in words:
            out[d["topic"]] = (d.get("_gloss", ""), d.get("metaphors", []))
    return out


def main():
    measure = ["anger", "life", "hope", "grief", "courage"]
    repeat_topic = "doubt"
    data = load_topics(set(measure + [repeat_topic]))
    print(f"# measuring {len(measure)} topics + {repeat_topic} (repeats) — REAL prompts\n")

    rows = []
    # Haiku vehicle-proposal step (cold then warm within the same 5-min window)
    print("## Haiku vehicle-proposal (build_apt_prompt)")
    for i, t in enumerate(measure):
        gloss, _ = data[t]
        r = cli_call(build_apt_prompt(t, gloss), "haiku")
        r["topic"] = t; r["step"] = "haiku_vehicles"; rows.append(r)
        print(f"  {t:>8}: ${r.get('cost_usd')}, wall={r.get('wall_s')}s, out={r.get('out_tok')}tok, "
              f"cache_create={r.get('cache_creation')}, cache_read={r.get('cache_read')}")

    # Sonnet chain step (the expensive one)
    print("\n## Sonnet chain generation (run_chain_spike.build_prompt)")
    for i, t in enumerate(measure):
        gloss, vehicles = data[t]
        r = cli_call(build_chain_prompt(t, gloss, vehicles), "sonnet")
        r["topic"] = t; r["step"] = "sonnet_chains"; rows.append(r)
        print(f"  {t:>8}: ${r.get('cost_usd')}, wall={r.get('wall_s')}s, out={r.get('out_tok')}tok, "
              f"cache_create={r.get('cache_creation')}, cache_read={r.get('cache_read')}")

    # within-topic variance: repeat one topic 3x per model
    print(f"\n## variance — {repeat_topic} x3 each model")
    gloss, vehicles = data[repeat_topic]
    for m, builder, arg in [("haiku", build_apt_prompt, None), ("sonnet", build_chain_prompt, vehicles)]:
        for k in range(3):
            p = build_apt_prompt(repeat_topic, gloss) if m == "haiku" else build_chain_prompt(repeat_topic, gloss, vehicles)
            r = cli_call(p, m)
            r["topic"] = repeat_topic; r["step"] = f"{m}_repeat"; rows.append(r)
            print(f"  {m} #{k+1}: ${r.get('cost_usd')}, wall={r.get('wall_s')}s, out={r.get('out_tok')}tok, cache_read={r.get('cache_read')}")

    # summary
    import statistics as st
    def summ(step):
        rs = [x for x in rows if x.get("step") == step and x.get("ok")]
        costs = [x["cost_usd"] for x in rs if x.get("cost_usd") is not None]
        walls = [x["wall_s"] for x in rs if x.get("wall_s") is not None]
        if not costs:
            return None
        return {"n": len(costs), "cost_mean": round(st.mean(costs), 4),
                "cost_sd": round(st.pstdev(costs), 4) if len(costs) > 1 else 0,
                "wall_mean": round(st.mean(walls), 1),
                "wall_sd": round(st.pstdev(walls), 1) if len(walls) > 1 else 0}
    print("\n## SUMMARY")
    for step in ["haiku_vehicles", "sonnet_chains", "haiku_repeat", "sonnet_repeat"]:
        s = summ(step)
        if s: print(f"  {step:>16}: cost ${s['cost_mean']}+/-{s['cost_sd']}  wall {s['wall_mean']}+/-{s['wall_sd']}s  (n={s['n']})")
    total = sum(x.get("cost_usd") or 0 for x in rows)
    print(f"\n  TOTAL investigation spend this run: ${round(total,4)} over {len(rows)} calls")
    print("  (cost log appended to artifacts/generation_cost_log.jsonl)")


if __name__ == "__main__":
    main()
