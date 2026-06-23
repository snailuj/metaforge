#!/usr/bin/env python3
"""HUB-PENALIZED guided beam search (operator refinement).

Observed failure: the smooth kNN walk drifts into generic 'god-node' hubs (nodes
that are the kNN of very many others — the embedding 'hubness' pathology), so it
pools among generic/synonym concepts and misses the specific cross-domain
vehicle. Fix: down-weight a hop prev->next by the IN-DEGREE of `next` in the kNN
graph (edges leading into that hub). This penalises routing THROUGH god-nodes.

step_score(prev->next) = cos(prev,next) - lam_hub * hubness_norm(next)
path kept by: sum(step_score) + lam_cross*(1 - cos(next, topic))
endpoint rank score adds lam_concr*concreteness (+ optional endpoint hub penalty).

Sweep depth{2,3} x lam_hub{0,0.5,1,2} on beam=2000, scheme cross+concr.
Baseline to beat: direct embedding apt recall@200 = 13%. API-free.
"""
from __future__ import annotations
import sys, time
from collections import defaultdict
from pathlib import Path
import numpy as np
ART = Path("docs/inbox/2026-06-03-context-free-edges/artifacts")
sys.path.insert(0, str(ART))
from guided_traversal_experiment import load, load_pairs, auc, K

BEAM = 2000


def knn_indegree(C, k=K, chunk=1500):
    """In-degree of each node in the directed kNN graph (how many nodes have
    this node among their top-k cosine neighbours)."""
    N = C.shape[0]
    indeg = np.zeros(N, dtype=np.int32)
    for a in range(0, N, chunk):
        b = min(a + chunk, N)
        sims = C[a:b] @ C.T                       # (chunk x N)
        for i in range(b - a):
            sims[i, a + i] = -1
        nbr = np.argpartition(-sims, k, axis=1)[:, :k]
        np.add.at(indeg, nbr.ravel(), 1)
    return indeg


def beam_hub(t, C, cz, hpn, lam_cross, lam_concr, lam_hub, depth, k=K, beam=BEAM,
             penalize_endpoint=False):
    tvec = C[t]
    frontier = {t: 0.0}
    for d in range(depth):
        rows = np.array(list(frontier.keys()))
        cum = np.array([frontier[r] for r in rows])
        sims = C[rows] @ C.T
        for i in range(len(rows)):
            sims[i, rows[i]] = -1
        nbr = np.argpartition(-sims, k, axis=1)[:, :k]
        nxt = {}
        for i, r in enumerate(rows):
            for j in nbr[i]:
                step = sims[i, j] - lam_hub * hpn[j]     # HUB PENALTY on landing j
                cross = 1.0 - float(C[j] @ tvec)
                score = cum[i] + step + lam_cross * cross
                if j not in nxt or score > nxt[j]:
                    nxt[j] = score
        frontier = dict(sorted(nxt.items(), key=lambda kv: kv[1], reverse=True)[:beam])
    out = {}
    for node, sc in frontier.items():
        cross = 1.0 - float(C[node] @ tvec)
        s = sc + lam_concr * cz[node] + lam_cross * cross
        if penalize_endpoint:
            s -= lam_hub * hpn[node]
        out[node] = s
    return out


def main():
    t0 = time.time()
    resolve, ids, idx, C, cz, concr, pos = load()
    print(f"loaded {len(ids)} noun centroids in {time.time()-t0:.1f}s", flush=True)
    t0 = time.time()
    indeg = knn_indegree(C)
    h = np.log1p(indeg).astype(np.float32)
    hpn = (h - h.min()) / (h.max() - h.min() + 1e-8)        # 0..1
    print(f"kNN in-degree computed in {time.time()-t0:.1f}s; "
          f"indeg max={int(indeg.max())} mean={indeg.mean():.1f} "
          f"p99={int(np.percentile(indeg,99))}", flush=True)

    pairs, miss = load_pairs(resolve, idx, pos)
    by_topic = defaultdict(list)
    for tw, ti, vw, vi, lab in pairs:
        by_topic[ti].append((vw, vi, lab))
    print(f"cohort {len(pairs)} pairs / {len(by_topic)} topics", flush=True)

    for depth in (2, 3):
        for lam_hub in (0.0, 0.5, 1.0, 2.0):
            rows = []
            for ti, vlist in by_topic.items():
                front = beam_hub(ti, C, cz, hpn, lam_cross=2.0, lam_concr=2.0,
                                 lam_hub=lam_hub, depth=depth)
                order = sorted(front.items(), key=lambda kv: kv[1], reverse=True)
                rank = {n: r for r, (n, s) in enumerate(order)}
                for vw, vi, lab in vlist:
                    rows.append({"label": lab, "reached": vi in front,
                                 "rank": rank.get(vi, 10**9), "score": front.get(vi, -1e9)})
            y = np.array([r["label"] for r in rows]); rk = np.array([r["rank"] for r in rows])
            reached = np.array([r["reached"] for r in rows]); sc = np.array([r["score"] for r in rows])
            ap, ip = y == 1, y == 0
            print(f"\n=== depth={depth} lam_hub={lam_hub} (beam={BEAM}, cross+concr) ===", flush=True)
            print(f"  apt:   reached {reached[ap].mean():.1%}  recall@200 {np.mean(rk[ap]<200):.1%}  @1000 {np.mean(rk[ap]<1000):.1%}")
            print(f"  inapt: reached {reached[ip].mean():.1%}  recall@200 {np.mean(rk[ip]<200):.1%}  @1000 {np.mean(rk[ip]<1000):.1%}")
            print(f"  AUC(path-score) = {auc(y, sc):.3f}   [baseline direct-embedding apt recall@200=13%]")


if __name__ == "__main__":
    main()
