#!/usr/bin/env python3
"""Minimal: anchor the Sonnet chain-generation cost (3 calls) to complete the
baseline cost picture / reconcile the H-D discrepancy. Reuses cli_call."""
import json, sys
from pathlib import Path
ROOT = Path("/home/agent/projects/metaforge")
sys.path.insert(0, str(ROOT / "docs/inbox/2026-06-03-context-free-edges/artifacts"))
sys.path.insert(0, str(ROOT / "data-pipeline/scripts"))
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "data-pipeline/grading_sidecar"))
from measure_generation_cost import cli_call, load_topics
from run_chain_spike import build_prompt as build_chain_prompt
import statistics as st

data = load_topics({"anger", "life", "hope"})
rows = []
for t in ["anger", "life", "hope"]:
    gloss, vehicles = data[t]
    r = cli_call(build_chain_prompt(t, gloss, vehicles), "sonnet")
    r["topic"] = t
    rows.append(r)
    print(f"  sonnet {t:>6}: ${r.get('cost_usd')}, wall={r.get('wall_s')}s, out={r.get('out_tok')}tok, "
          f"cache_read={r.get('cache_read')}", flush=True)
costs = [r["cost_usd"] for r in rows if r.get("cost_usd")]
walls = [r["wall_s"] for r in rows if r.get("wall_s")]
print(f"\nSONNET chain: cost ${st.mean(costs):.4f}±{st.pstdev(costs):.4f}  wall {st.mean(walls):.1f}±{st.pstdev(walls):.1f}s  (n={len(costs)})")
print(f"run spend ${sum(costs):.4f}")
