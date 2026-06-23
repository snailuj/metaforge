#!/usr/bin/env python3
"""Derive metaphor-edge CANDIDATES combinatorially from shared property-clusters.

Mission artifact (H-A, derivational seeding): produce topic->vehicle candidate
edges from `synset_properties_curated` ALONE — zero per-topic LLM. The point is
to measure (a) whether pruning collapses the 455M shared->=1 fan-out into a
tractable per-topic candidate budget, and (b) feed those candidates to a judge
to measure apt(live) precision vs the generated baseline.

Scoring of a (topic, vehicle) candidate over their shared clusters S:
    raw      : |S|
    idf      : sum_{c in S} log(N / df_c)
    idf_sal  : sum_{c in S} log(N / df_c) * sqrt(sal_t(c) * sal_v(c))
where df_c = number of synsets in cluster c (cluster "document frequency"),
N = number of synsets with any curated cluster. Clusters with df_c > --df-cap
are dropped as stop-word/mega-clusters before scoring. Candidates must share
>= --min-shared surviving clusters.

Everything here is pure SQL+Python; reproducible and free.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path


def load_substrate(db: str):
    """Return (syn2clusters, cluster_df, syn2lemma, syn2concr, n_synsets).

    syn2clusters: {synset_id: {cluster_id: salience_sum}}
    cluster_df:   {cluster_id: n_synsets_in_cluster}
    syn2lemma:    {synset_id: canonical_lemma} (least-polysemous curated lemma)
    syn2concr:    {synset_id: concreteness 1-5} (may be missing keys)
    """
    con = sqlite3.connect(db)
    try:
        syn2clusters: dict[str, dict[int, float]] = defaultdict(dict)
        cluster_members: dict[int, set] = defaultdict(set)
        for sid, cid, sal in con.execute(
            "SELECT synset_id, cluster_id, salience_sum FROM synset_properties_curated"
        ):
            syn2clusters[sid][cid] = float(sal)
            cluster_members[cid].add(sid)
        cluster_df = {cid: len(m) for cid, m in cluster_members.items()}

        syn2lemma: dict[str, str] = {}
        # least-polysemous lemma per synset = best canonical word
        for sid, lemma in con.execute(
            "SELECT synset_id, lemma FROM property_vocab_curated "
            "ORDER BY polysemy ASC"
        ):
            syn2lemma.setdefault(sid, lemma)

        syn2concr: dict[str, float] = {}
        try:
            for sid, score in con.execute(
                "SELECT synset_id, score FROM synset_concreteness"
            ):
                syn2concr[sid] = float(score)
        except sqlite3.OperationalError:
            pass

        n_synsets = len(syn2clusters)
        return syn2clusters, cluster_df, syn2lemma, syn2concr, n_synsets
    finally:
        con.close()


def build_inverted_index(syn2clusters, cluster_df, df_cap):
    """cluster_id -> set(synset_id), only for surviving (df<=df_cap) clusters."""
    inv: dict[int, list] = defaultdict(list)
    for sid, clusters in syn2clusters.items():
        for cid in clusters:
            if cluster_df.get(cid, 0) <= df_cap:
                inv[cid].append(sid)
    return inv


def derive_for_topic(topic_sid, syn2clusters, cluster_df, inv, n_synsets,
                     df_cap, min_shared, mode, k, exclude_same_lemma_syn=None):
    """Return top-k (vehicle_sid, score, shared_cluster_ids) for a topic."""
    topic_clusters = {
        cid: sal for cid, sal in syn2clusters.get(topic_sid, {}).items()
        if cluster_df.get(cid, 0) <= df_cap
    }
    if not topic_clusters:
        return []
    # accumulate score over candidates sharing surviving clusters
    score: dict[str, float] = defaultdict(float)
    shared: dict[str, list] = defaultdict(list)
    for cid, sal_t in topic_clusters.items():
        idf = math.log(n_synsets / cluster_df[cid])
        for vsid in inv.get(cid, ()):
            if vsid == topic_sid:
                continue
            shared[vsid].append(cid)
            if mode == "raw":
                score[vsid] += 1.0
            elif mode == "idf":
                score[vsid] += idf
            elif mode == "idf_sal":
                sal_v = syn2clusters[vsid].get(cid, 0.0)
                score[vsid] += idf * math.sqrt(max(sal_t, 0.0) * max(sal_v, 0.0))
            else:
                raise ValueError(f"unknown mode {mode}")
    cands = [
        (vsid, sc, shared[vsid])
        for vsid, sc in score.items()
        if len(shared[vsid]) >= min_shared
    ]
    cands.sort(key=lambda t: t[1], reverse=True)
    return cands[:k]


def fanout_after_pruning(syn2clusters, cluster_df, df_cap, min_shared):
    """Estimate total candidate pairs after df-cap + min-shared, via inverted
    index. Counts unordered pairs sharing >= min_shared surviving clusters.

    For min_shared==1 this is exact via sum over surviving clusters of C(df,2)
    MINUS double counting (pairs sharing multiple clusters counted once)."""
    # Exact distinct-pair count is expensive; report two bounds:
    #  - upper: sum_c C(df_c,2) over surviving clusters (counts multiplicity)
    #  - For min_shared>1 we sample. Here return the upper bound + surviving
    #    cluster stats; the orchestrator runs the precise per-topic budget which
    #    is what actually matters operationally.
    surviving = {cid: df for cid, df in cluster_df.items() if df <= df_cap}
    upper_pairs = sum(df * (df - 1) // 2 for df in surviving.values())
    return {
        "df_cap": df_cap,
        "surviving_clusters": len(surviving),
        "dropped_clusters": len(cluster_df) - len(surviving),
        "upper_bound_pairs_shared>=1": upper_pairs,
        "max_surviving_df": max(surviving.values()) if surviving else 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data-pipeline/output/lexicon_v2.db")
    ap.add_argument("--topics-json", help="JSON {word: synset_id}; if omitted use --topic-sids")
    ap.add_argument("--topic-sids", nargs="*", default=[])
    ap.add_argument("--df-cap", type=int, default=200,
                    help="drop clusters with > this many synsets (stop-words)")
    ap.add_argument("--min-shared", type=int, default=2)
    ap.add_argument("--mode", choices=["raw", "idf", "idf_sal"], default="idf_sal")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--fanout-scan", action="store_true",
                    help="also report global fan-out after pruning")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    t0 = time.time()
    syn2clusters, cluster_df, syn2lemma, syn2concr, n_synsets = load_substrate(args.db)
    sys.stderr.write(
        f"loaded {n_synsets} synsets, {len(cluster_df)} clusters in "
        f"{time.time()-t0:.1f}s\n")

    if args.fanout_scan:
        fo = fanout_after_pruning(syn2clusters, cluster_df, args.df_cap, args.min_shared)
        print(json.dumps({"fanout": fo}, indent=2))

    inv = build_inverted_index(syn2clusters, cluster_df, args.df_cap)

    topics = {}
    if args.topics_json:
        topics = json.loads(Path(args.topics_json).read_text())
    for sid in args.topic_sids:
        topics[sid] = sid

    out = []
    for word, sid in topics.items():
        cands = derive_for_topic(
            sid, syn2clusters, cluster_df, inv, n_synsets,
            args.df_cap, args.min_shared, args.mode, args.k)
        rows = []
        for vsid, sc, shared in cands:
            rows.append({
                "vehicle_synset_id": vsid,
                "vehicle_lemma": syn2lemma.get(vsid, "?"),
                "score": round(sc, 4),
                "n_shared": len(shared),
                "topic_concr": syn2concr.get(sid),
                "vehicle_concr": syn2concr.get(vsid),
            })
        out.append({
            "topic": word,
            "topic_synset_id": sid,
            "topic_lemma": syn2lemma.get(sid, word),
            "n_topic_clusters_surviving": sum(
                1 for c in syn2clusters.get(sid, {}) if cluster_df.get(c, 0) <= args.df_cap),
            "candidates": rows,
        })

    result = {
        "params": vars(args),
        "n_synsets": n_synsets,
        "topics": out,
    }
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text)
        sys.stderr.write(f"wrote {args.output}\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
