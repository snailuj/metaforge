#!/usr/bin/env python3
"""JUDGE FEASIBILITY probe: the recommendation says the deliverable is an LLM
live/dead judge calibrated to Julian's grading. Test that directly on the only
human labels that exist — the graded chains in the live worktree — measuring
agreement of a Haiku/Sonnet/Opus judge with Julian's verdicts.

SEED feasibility signal, NOT validation: n small, 3 topics, in-sample (Julian
graded these exact chains). But it tests the load-bearing assumption within the
<=20-synset budget. Costs tracked to generation_cost_log.jsonl.
"""
from __future__ import annotations
import json, os, re, subprocess, time, sys
from pathlib import Path

ROOT = Path("/home/agent/projects/metaforge")
CHAINS = ROOT / "data-pipeline/grading/sonnet_chains_provisional_r1.jsonl"
JUDGE = ROOT / ".worktrees/next/data-pipeline/grading/judgements_provisional.jsonl"
COSTLOG = ROOT / "docs/inbox/2026-06-03-context-free-edges/artifacts/generation_cost_log.jsonl"
EMPTY_MCP = str(ROOT / "lib/empty_mcp.json")


def cli(prompt, model):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    cmd = ["claude", "-p", "--output-format", "json", "--model", model,
           "--max-turns", "1", "--no-session-persistence",
           "--strict-mcp-config", "--mcp-config", EMPTY_MCP]
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=300, env=env)
    try:
        j = json.loads(proc.stdout)
    except Exception:
        return "", None
    cost = j.get("total_cost_usd")
    with open(COSTLOG, "a") as f:
        f.write(json.dumps({"model": model, "step": "judge_feasibility", "cost_usd": cost,
                            "out_tok": j.get("usage", {}).get("output_tokens")}) + "\n")
    return j.get("result", ""), cost


def load_human():
    latest = {}
    for l in JUDGE.read_text().splitlines():
        if not l.strip(): continue
        r = json.loads(l); k = r.get("chain_signature"); ts = r.get("ts", "")
        if k not in latest or ts >= latest[k][0]:
            latest[k] = (ts, r)
    out = {}
    for k, (ts, r) in latest.items():
        live = r.get("metaphor") or r.get("label")
        if live in ("live", "dead"):
            out[k] = {"topic": r["topic"], "vehicle": r["vehicle"], "human": live}
    return out


def load_chains():
    return {json.loads(l)["chain_signature"]: json.loads(l)
            for l in CHAINS.read_text().splitlines() if l.strip()}


def judge_prompt(topic, vehicle, phrases):
    path = " -> ".join(p for p in phrases if p)
    return f"""You are grading a candidate metaphor for a creative-writing thesaurus. The product wants LIVE metaphors: genuine, non-cliched CROSS-DOMAIN mappings an attentive reader finds apt. Reject as DEAD: cliches, dead/conventional metaphors, near-synonyms, same-domain pairings, or non-apt leaps.

Topic: {topic}
Vehicle: {vehicle}
Proposed conceptual path: {path}

Is "{topic} is (a) {vehicle}" a LIVE or DEAD metaphor for creative writing? Answer with STRICT JSON only:
{{"verdict": "live" | "dead", "reason": "<one short clause>"}}"""


def parse(raw):
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m: return None
    try: return json.loads(m.group(0)).get("verdict")
    except Exception: return None


ROWS_JSONL = ROOT / "docs/inbox/2026-06-03-context-free-edges/artifacts/judge_feasibility_rows.jsonl"


def main():
    human = load_human(); chains = load_chains()
    items = [(s, h, chains[s]) for s, h in human.items() if s in chains]
    print(f"matched {len(items)} graded chains with paths (of {len(human)} human verdicts); "
          f"human dist: live={sum(1 for _,h,_ in items if h['human']=='live')} "
          f"dead={sum(1 for _,h,_ in items if h['human']=='dead')}", flush=True)
    models = ["haiku", "sonnet", "opus"]
    # resume: load already-judged (sig, model)
    done = set(); rows = {m: [] for m in models}
    if ROWS_JSONL.exists():
        for l in ROWS_JSONL.read_text().splitlines():
            if not l.strip(): continue
            r = json.loads(l); done.add((r["sig"], r["model"])); rows[r["model"]].append(r)
    with open(ROWS_JSONL, "a") as out:
        for s, h, ch in items:
            phrases = [st.get("phrase", "") for st in ch.get("chain", [])]
            p = judge_prompt(h["topic"], h["vehicle"], phrases)
            line = []
            for m in models:
                if (s, m) in done:
                    line.append(f"{m}=cached"); continue
                raw, cost = cli(p, m)
                rec = {"sig": s, "model": m, "topic": h["topic"], "vehicle": h["vehicle"],
                       "human": h["human"], "pred": parse(raw)}
                out.write(json.dumps(rec) + "\n"); out.flush()
                rows[m].append(rec); line.append(f"{m}={rec['pred']}")
            print(f"  judged {h['topic']}->{h['vehicle']} (human={h['human']}): " + ", ".join(line), flush=True)

    print("\n=== AGREEMENT with Julian (live/dead) ===")
    for m in models:
        rs = [r for r in rows[m] if r["pred"] in ("live", "dead")]
        agree = sum(1 for r in rs if r["pred"] == r["human"])
        tp = sum(1 for r in rs if r["pred"] == "live" and r["human"] == "live")
        tn = sum(1 for r in rs if r["pred"] == "dead" and r["human"] == "dead")
        fp = sum(1 for r in rs if r["pred"] == "live" and r["human"] == "dead")
        fn = sum(1 for r in rs if r["pred"] == "dead" and r["human"] == "live")
        n = len(rs); nlive = sum(1 for r in rs if r["human"] == "live")
        # Cohen's kappa
        po = agree / n if n else 0
        p_live = (tp + fp) / n if n else 0; p_dead = 1 - p_live
        h_live = nlive / n if n else 0; h_dead = 1 - h_live
        pe = p_live * h_live + p_dead * h_dead
        kappa = (po - pe) / (1 - pe) if (1 - pe) else 0
        print(f"  {m:>7}: agree {agree}/{n} = {po:.0%}  kappa={kappa:+.2f}  "
              f"[TP{tp} TN{tn} FP{fp} FN{fn}; parsed {n}/{len(rows[m])}]")
    json.dump(rows, open(ROOT / "docs/inbox/2026-06-03-context-free-edges/artifacts/judge_feasibility_rows.json", "w"), indent=1)


if __name__ == "__main__":
    main()
