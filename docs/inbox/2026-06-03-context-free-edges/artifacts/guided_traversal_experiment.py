#!/usr/bin/env python3
"""GUIDED multi-hop beam search (steelman of graph-traversal, per operator).

The earlier PageRank test used a UNIFORM random walk — no signal. This uses the
project's real signals as edge/endpoint scores, POS-filtered to nouns:
  - edges = top-K cosine-nearest noun synsets (smooth conceptual steps)
  - beam keeps paths that take SMOOTH steps (high step-cosine) while REACHING
    CROSS-DOMAIN (far from the topic in embedding space)
  - frontier at depth D ranked toward cross-domain distance + concreteness
Premise: anger->volcano may be far in DIRECT embedding space but reachable via
stepping-stones (pressure->eruption->volcano), each a short justified hop.

Eval on the spike apt/inapt cohort:
  (1) reachability: is the cohort vehicle within D kNN-hops at all?
  (2) generation recall: rank of the apt vehicle in topic's depth-D scored
      frontier; recall@k — compare to DIRECT embedding (H-B: recall@200=13%,
      median rank 2870).
  (3) discrimination: AUC of best-path-score, apt vs inapt.
Several scoring schemes tried. Pure numpy; no API.
"""
from __future__ import annotations
import json, sqlite3, sys, time
from collections import defaultdict
from pathlib import Path
import numpy as np

ART = Path("docs/inbox/2026-06-03-context-free-edges/artifacts")
sys.path.insert(0, str(ART))
from separability_experiment import build_resolver  # noqa: E402
from sklearn.metrics import roc_auc_score

DB = "data-pipeline/output/lexicon_v2.db"
APT = "data-pipeline/output/metaphor_spike_apt_phase2_20260525T004154.jsonl"
INAPT = "data-pipeline/output/metaphor_spike_inapt_phase2_20260525T004154.jsonl"
K = 40          # neighbours expanded per node (graph degree)
BEAM = 300      # beam width
DEPTH = 3


def load():
    con = sqlite3.connect(DB)
    resolve = build_resolver(con)
    pos = {s: p for s, p in con.execute("SELECT synset_id,pos FROM synsets")}
    concr = {s: float(v) for s, v in con.execute("SELECT synset_id,score FROM synset_concreteness")}
    ids, vecs = [], []
    for s, blob in con.execute("SELECT synset_id,centroid FROM synset_centroids"):
        if pos.get(s) == 'n':                       # POS filter: nouns
            ids.append(s); vecs.append(np.frombuffer(blob, dtype=np.float32))
    con.close()
    C = np.array(vecs, dtype=np.float32)
    C /= (np.linalg.norm(C, axis=1, keepdims=True) + 1e-8)
    idx = {s: i for i, s in enumerate(ids)}
    # concreteness vector aligned to C (default 3.0), normalised 1-5 -> 0..1
    cz = np.array([(concr.get(s, 3.0) - 1) / 4 for s in ids], dtype=np.float32)
    return resolve, ids, idx, C, cz, concr, pos


def knn(C, rows, k):
    """top-k cosine neighbour indices for each row index in `rows`."""
    sims = C[rows] @ C.T                              # (len(rows) x N)
    sims[np.arange(len(rows)), rows] = -1
    nbr = np.argpartition(-sims, k, axis=1)[:, :k]
    return nbr, sims


def beam_frontier(t, C, cz, lam_cross, lam_concr, depth=DEPTH, k=K, beam=BEAM):
    """Return dict node_idx -> best score at depth `depth` reached from t."""
    tvec = C[t]
    # frontier: dict node -> (cum_smooth, path_len). start at t.
    frontier = {t: 0.0}
    for d in range(depth):
        rows = np.array(list(frontier.keys()))
        cum = np.array([frontier[r] for r in rows])
        nbr, sims = knn(C, rows, k)
        nxt = {}
        for i, r in enumerate(rows):
            for j in nbr[i]:
                step = sims[i, j]                    # cosine(prev, j): smoothness
                # partial objective: accumulate smoothness, reward distance from t
                cross = 1.0 - float(C[j] @ tvec)
                score = cum[i] + step + lam_cross * cross
                if j not in nxt or score > nxt[j]:
                    nxt[j] = score
        # keep top-beam by score
        items = sorted(nxt.items(), key=lambda kv: kv[1], reverse=True)[:beam]
        frontier = dict(items)
    # final endpoint score: path score + concreteness bonus + cross-domain
    out = {}
    for node, sc in frontier.items():
        cross = 1.0 - float(C[node] @ tvec)
        out[node] = sc + lam_concr * cz[node] + lam_cross * cross
    return out


def load_pairs(resolve, idx, pos):
    out = []
    miss = 0
    for path, key, lab in [(APT, "metaphors", 1), (INAPT, "inapt_metaphors", 0)]:
        for line in Path(path).read_text().splitlines():
            if not line.strip(): continue
            d = json.loads(line); t = resolve(d["topic"])
            if t is None or t not in idx: miss += 1; continue
            for m in d.get(key, []):
                v = resolve(m.get("vehicle"))
                if v is None or v not in idx: continue
                out.append((d["topic"], idx[t], m.get("vehicle"), idx[v], lab))
    return out, miss


def auc(y, x):
    try:
        a = roc_auc_score(y, x); return max(a, 1 - a)
    except Exception:
        return float("nan")


def main():
    t0 = time.time()
    resolve, ids, idx, C, cz, concr, pos = load()
    print(f"loaded {len(ids)} noun centroids in {time.time()-t0:.1f}s", flush=True)
    pairs, miss = load_pairs(resolve, idx, pos)
    by_topic = defaultdict(list)
    for tw, ti, vw, vi, lab in pairs:
        by_topic[ti].append((vw, vi, lab))
    print(f"cohort: {len(pairs)} noun-resolved pairs over {len(by_topic)} topics (miss={miss})", flush=True)

    schemes = {
        "smooth_only":        dict(lam_cross=0.0, lam_concr=0.0),
        "smooth+concr":       dict(lam_cross=0.0, lam_concr=2.0),
        "smooth+cross":       dict(lam_cross=2.0, lam_concr=0.0),
        "smooth+cross+concr": dict(lam_cross=2.0, lam_concr=2.0),
    }
    for sname, params in schemes.items():
        rows = []
        for ti, vlist in by_topic.items():
            front = beam_frontier(ti, C, cz, depth=DEPTH, **params)
            order = sorted(front.items(), key=lambda kv: kv[1], reverse=True)
            rank_of = {node: r for r, (node, sc) in enumerate(order)}
            for vw, vi, lab in vlist:
                rows.append({"label": lab,
                             "reached": vi in front,
                             "rank": rank_of.get(vi, 10**9),
                             "score": front.get(vi, -1e9)})
        y = np.array([r["label"] for r in rows])
        rk = np.array([r["rank"] for r in rows])
        reached = np.array([r["reached"] for r in rows])
        sc = np.array([r["score"] for r in rows])
        print(f"\n=== scheme '{sname}'  (depth {DEPTH}, K={K}, beam={BEAM}; frontier<= {BEAM}) ===")
        for lab, nm in [(1, "apt"), (0, "inapt")]:
            mrk = y == lab
            rr = rk[mrk]
            print(f"  {nm}: reached(in depth-{DEPTH} frontier) {reached[mrk].mean():.1%}; "
                  f"median rank {int(np.median(rr)) if (rr<10**9).any() else 'NA'}; "
                  f"recall@50 {np.mean(rr<50):.1%} @200 {np.mean(rr<200):.1%}")
        print(f"  AUC(path-score, apt-vs-inapt) = {auc(y, sc):.3f}")
    print("\nBASELINE direct-embedding (H-B): apt recall@200=13%, median rank 2870.")
    print("If guided traversal apt-recall >> 13% AND apt reaches >> inapt, the signal-guided graph idea WORKS.")


if __name__ == "__main__":
    main()
