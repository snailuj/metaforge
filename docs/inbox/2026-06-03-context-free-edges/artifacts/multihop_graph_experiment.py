#!/usr/bin/env python3
"""MULTI-HOP GRAPH-TRAVERSAL test of the unified property-union-synset graph.

Addresses the proposal: build ONE graph whose vertices are the UNION of
{synset_ids} and {canonical property nodes}, with no privileged role for
topic/vehicle/feature, edges = has_property (synset<->property), property nodes
DEDUPLICATED to a canonical id (= cluster_id, which is exactly the snap
pipeline's dedup of synonymous properties). Then ask: does MULTI-HOP traversal
of this graph recover apt topic->vehicle metaphor edges?

This is distinct from the pairwise shared-feature test (which is the 2-hop
special case, already shown to fail). Here we use graph-native metrics that
integrate paths of length 4, 6, ... and down-weight the mega-hub property nodes:

  - Personalized PageRank (PPR): a random walk with restart from the topic over
    the bipartite synset<->cluster graph. PPR[vehicle] = multi-hop graph
    proximity. Two variants: raw, and IDF-edge-weighted (walks avoid hub
    clusters). This IS the "traverse the deduplicated graph" framing.
  - Adamic-Adar / Resource-Allocation: hub-down-weighted 2-hop link prediction
    (Sigma over shared clusters of 1/log(deg) and 1/deg). The classic
    co-occurrence-graph link predictors.
  - Unweighted shortest-path length distribution (BFS) apt vs inapt — exposes
    the "everything connects within 4 hops via hubs" artifact.

Eval against the spike apt/inapt cohort, BOTH:
  (a) discrimination: AUC(score, apt-vs-inapt)
  (b) generation/recall: rank of the apt vehicle in topic's PPR ranking over all
      synsets (can traversal PROPOSE the apt vehicle?). recall@k.
All pure graph computation; no API.
"""
from __future__ import annotations
import json, math, sqlite3, sys
from collections import defaultdict, deque
from pathlib import Path
import numpy as np
import scipy.sparse as sp

ART = Path("docs/inbox/2026-06-03-context-free-edges/artifacts")
sys.path.insert(0, str(ART))
from separability_experiment import build_resolver  # noqa: E402
from sklearn.metrics import roc_auc_score

DB = "data-pipeline/output/lexicon_v2.db"
APT = "data-pipeline/output/metaphor_spike_apt_phase2_20260525T004154.jsonl"
INAPT = "data-pipeline/output/metaphor_spike_inapt_phase2_20260525T004154.jsonl"
ALPHA = 0.15      # restart probability
ITERS = 60


def auc(y, x):
    try:
        a = roc_auc_score(y, x); return max(a, 1 - a)
    except Exception:
        return float("nan")


def main():
    con = sqlite3.connect(DB)
    resolve = build_resolver(con)
    # synset<->cluster incidence
    syn2cl = defaultdict(dict)
    cl_deg = defaultdict(int)
    for sid, cid, sal in con.execute(
        "SELECT synset_id, cluster_id, salience_sum FROM synset_properties_curated"):
        syn2cl[sid][cid] = float(sal); cl_deg[cid] += 1
    con.close()

    syns = sorted(syn2cl.keys())
    s_idx = {s: i for i, s in enumerate(syns)}
    cls = sorted(cl_deg.keys())
    c_idx = {c: len(syns) + j for j, c in enumerate(cls)}
    N = len(syns) + len(cls)
    nS = len(syns)

    # Build bipartite adjacency (undirected) with two edge-weightings.
    rows, cols, w_raw, w_idf = [], [], [], []
    Ntot = nS  # synset count for idf base
    for s, cm in syn2cl.items():
        si = s_idx[s]
        for c, sal in cm.items():
            ci = c_idx[c]
            idf = math.log(Ntot / cl_deg[c]) if cl_deg[c] > 0 else 0.0
            for (a, b) in ((si, ci), (ci, si)):
                rows.append(a); cols.append(b)
                w_raw.append(1.0); w_idf.append(max(idf, 1e-6))
    A_raw = sp.csr_matrix((w_raw, (rows, cols)), shape=(N, N))
    A_idf = sp.csr_matrix((w_idf, (rows, cols)), shape=(N, N))

    def col_stochastic(A):
        # column-normalise: P = A @ diag(1/colsum) so each column sums to 1
        # (a random-walk transition matrix). NOTE: must be the matrix product
        # A @ diag, NOT element-wise A.multiply(diag) — the latter zeroes a
        # hollow (no-diagonal) bipartite A. (bug fixed 2026-06-03 post-factcheck)
        d = np.asarray(A.sum(axis=0)).ravel()
        d[d == 0] = 1.0
        return (A @ sp.diags(1.0 / d)).tocsr()
    P_raw = col_stochastic(A_raw)
    P_idf = col_stochastic(A_idf)
    assert abs(P_raw.sum(axis=0).max() - 1.0) < 1e-6, "transition matrix not column-stochastic"

    def ppr(P, topic_idx):
        e = np.zeros(N); e[topic_idx] = 1.0
        x = e.copy()
        for _ in range(ITERS):
            x = ALPHA * e + (1 - ALPHA) * (P @ x)
        return x

    # load cohort
    def load(path, key, label):
        out = []
        for line in Path(path).read_text().splitlines():
            if not line.strip(): continue
            d = json.loads(line); t = resolve(d["topic"])
            if t is None or t not in s_idx: continue
            for m in d.get(key, []):
                v = resolve(m.get("vehicle"))
                if v is None or v not in s_idx: continue
                out.append((d["topic"], t, m.get("vehicle"), v, label))
        return out
    pairs = load(APT, "metaphors", 1) + load(INAPT, "inapt_metaphors", 0)

    # group by topic so we compute each PPR once
    by_topic = defaultdict(list)
    for tw, ts, vw, vs, lab in pairs:
        by_topic[ts].append((vw, vs, lab))

    rec = []  # per-pair feature rows
    sp_lengths = {1: [], 0: []}
    # precompute adjacency neighbour sets for BFS + AA/RA
    syn_neigh = {s: set(cm.keys()) for s, cm in syn2cl.items()}
    cl_members = defaultdict(set)
    for s, cm in syn2cl.items():
        for c in cm: cl_members[c].add(s)

    def bfs_len(ts, vs, maxhop=6):
        if ts == vs: return 0
        # BFS over bipartite graph from synset ts to synset vs
        seen = {("s", ts)}
        q = deque([(("s", ts), 0)])
        while q:
            (kind, node), dist = q.popleft()
            if dist >= maxhop: continue
            if kind == "s":
                for c in syn_neigh.get(node, ()):
                    nxt = ("c", c)
                    if nxt not in seen:
                        seen.add(nxt); q.append((nxt, dist + 1))
            else:
                for s in cl_members.get(node, ()):
                    if s == vs: return dist + 1
                    nxt = ("s", s)
                    if nxt not in seen:
                        seen.add(nxt); q.append((nxt, dist + 1))
        return -1  # unreachable within maxhop

    n_topics = len(by_topic)
    for ti, (ts, vlist) in enumerate(by_topic.items()):
        x_raw = ppr(P_raw, s_idx[ts])
        x_idf = ppr(P_idf, s_idx[ts])
        # rank vehicles among all synsets by PPR (idf variant) — generation test
        syn_scores = x_idf[:nS].copy()
        syn_scores[s_idx[ts]] = -1
        order = np.argsort(-syn_scores)
        rank_of = {}
        for r, idx in enumerate(order):
            rank_of[idx] = r
        tc = syn_neigh.get(ts, set())
        for vw, vs, lab in vlist:
            vc = syn_neigh.get(vs, set())
            shared = tc & vc
            aa = sum(1.0 / math.log(cl_deg[c]) for c in shared if cl_deg[c] > 1)
            ra = sum(1.0 / cl_deg[c] for c in shared)
            vi = s_idx[vs]
            rec.append({
                "label": lab,
                "ppr_raw": float(x_raw[vi]),
                "ppr_idf": float(x_idf[vi]),
                "adamic_adar": aa,
                "resource_alloc": ra,
                "common_neigh": float(len(shared)),
                "veh_rank": int(rank_of.get(vi, nS)),
            })
        if (ti + 1) % 50 == 0:
            print(f"  PPR {ti+1}/{n_topics} topics", file=sys.stderr, flush=True)

    # shortest path lengths (subsample for cost): up to 120 apt + 120 inapt
    apt_pairs = [(ts, vs) for ts, vl in by_topic.items() for (_, vs, lab) in vl if lab == 1]
    in_pairs = [(ts, vs) for ts, vl in by_topic.items() for (_, vs, lab) in vl if lab == 0]
    import itertools
    for ts, vs in apt_pairs[:120]: sp_lengths[1].append(bfs_len(ts, vs))
    for ts, vs in in_pairs[:120]: sp_lengths[0].append(bfs_len(ts, vs))

    y = np.array([r["label"] for r in rec])
    print(f"\nresolved cohort pairs: {len(rec)} (apt={int(y.sum())}, inapt={int((1-y).sum())})")
    print("\n=== DISCRIMINATION: AUC(metric, apt-vs-inapt) ===")
    for f in ["ppr_raw", "ppr_idf", "adamic_adar", "resource_alloc", "common_neigh"]:
        x = np.array([r[f] for r in rec])
        print(f"  {f:>15}: AUC={auc(y, x):.3f}")

    print("\n=== GENERATION: can PPR(idf) PROPOSE the apt vehicle? rank over 81k synsets ===")
    ranks = np.array([r["veh_rank"] for r in rec])
    for lab, name in [(1, "apt"), (0, "inapt")]:
        rr = ranks[y == lab]
        print(f"  {name}: median rank {int(np.median(rr))}, recall@10 {np.mean(rr<10):.1%}, "
              f"@100 {np.mean(rr<100):.1%}, @1000 {np.mean(rr<1000):.1%}, @5000 {np.mean(rr<5000):.1%}")

    print("\n=== shortest-path length distribution (BFS, bipartite; hub-connectivity artifact) ===")
    for lab, name in [(1, "apt"), (0, "inapt")]:
        L = [x for x in sp_lengths[lab] if x > 0]
        unreach = sum(1 for x in sp_lengths[lab] if x < 0)
        import collections
        dist = dict(sorted(collections.Counter(L).items()))
        print(f"  {name} (n={len(sp_lengths[lab])}): len_dist={dist}, unreachable(<=6 hops)={unreach}")

    print("\nINTERPRETATION: if PPR/AA/RA AUC ~0.5 AND apt-vehicle median PPR rank is deep,")
    print("AND apt/inapt path-length distributions overlap, then multi-hop graph traversal")
    print("of the deduplicated property-union-synset graph ALSO fails — completing the refutation.")

    json.dump(rec, open(ART / "multihop_graph_rows.json", "w"))


if __name__ == "__main__":
    main()
