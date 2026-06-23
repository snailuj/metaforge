#!/usr/bin/env python3
"""Wide-beam / depth-sweep confirmation of the guided traversal result, to
preempt 'you didn't give it enough beam or the right depth'. Best scheme
(smooth+cross+concr), beam up to 2000, depth 2 and 3. Reuses the first script."""
from __future__ import annotations
import sys
from collections import defaultdict
from pathlib import Path
import numpy as np
ART = Path("docs/inbox/2026-06-03-context-free-edges/artifacts")
sys.path.insert(0, str(ART))
from guided_traversal_experiment import load, beam_frontier, load_pairs, auc

resolve, ids, idx, C, cz, concr, pos = load()
pairs, miss = load_pairs(resolve, idx, pos)
by_topic = defaultdict(list)
for tw, ti, vw, vi, lab in pairs:
    by_topic[ti].append((vw, vi, lab))
print(f"cohort {len(pairs)} pairs / {len(by_topic)} topics", flush=True)

for depth in (2, 3):
    for beam in (800, 2000):
        rows = []
        for ti, vlist in by_topic.items():
            front = beam_frontier(ti, C, cz, lam_cross=2.0, lam_concr=2.0,
                                  depth=depth, k=40, beam=beam)
            order = sorted(front.items(), key=lambda kv: kv[1], reverse=True)
            rank_of = {n: r for r, (n, s) in enumerate(order)}
            for vw, vi, lab in vlist:
                rows.append({"label": lab, "reached": vi in front,
                             "rank": rank_of.get(vi, 10**9), "score": front.get(vi, -1e9)})
        y = np.array([r["label"] for r in rows]); rk = np.array([r["rank"] for r in rows])
        reached = np.array([r["reached"] for r in rows]); sc = np.array([r["score"] for r in rows])
        print(f"\n=== depth={depth} beam={beam} (smooth+cross+concr) ===")
        for lab, nm in [(1, "apt"), (0, "inapt")]:
            mk = y == lab; rr = rk[mk]
            print(f"  {nm}: reached {reached[mk].mean():.1%}; recall@200 {np.mean(rr<200):.1%} "
                  f"@1000 {np.mean(rr<1000):.1%}")
        print(f"  AUC(path-score) = {auc(y, sc):.3f}")
print("\nbaseline direct-embedding apt recall@200=13%.")
