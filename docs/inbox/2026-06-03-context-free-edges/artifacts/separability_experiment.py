#!/usr/bin/env python3
"""DECISIVE EXPERIMENT: can a context-free function separate apt from inapt
metaphor pairs, using only features computable WITHOUT per-pair LLM?

If yes -> a cheap classifier is a viable near-free edge proposer/filter at 100k,
and the LLM drops to spot-checking (H-C viable; derivation/distillation lives).
If no  -> the discriminative signal is NOT in the context-free substrate; edges
must be LLM-generated/verified (H-C/H-A-refined dead; route to tiered generation).

Cohort: metaphor_spike_apt_phase2 (1112 apt pairs) + _inapt_phase2 (600 inapt,
'single_dimension'-dominant plausible controls) over 200 shared topics.

Features (all context-free, no LLM):
  cos_dist        embedding cosine distance between synset centroids
  concr_t/v/gap   Brysbaert concreteness + gap (vehicle - topic)
  shared_df<=200  count of shared curated clusters (mega-clusters dropped)
  shared_idf      sum of idf over shared clusters
  type_new        # vehicle property-types not in topic (M05 diversity)
  type_union      # distinct property-types across the pair
  poly_t/v        polysemy
  pcount_t/v      property_count from synset_centroids

Eval is topic-grouped to prevent topic leakage:
  - GroupKFold(5) logistic regression: ROC-AUC mean +/- std (the variance)
  - within-topic separation: mean within-topic AUC; frac topics apt>inapt
  - single-feature pooled AUCs (which feature carries signal)
"""
from __future__ import annotations
import json, math, sqlite3, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline

DB = "data-pipeline/output/lexicon_v2.db"
APT = "data-pipeline/output/metaphor_spike_apt_phase2_20260525T004154.jsonl"
INAPT = "data-pipeline/output/metaphor_spike_inapt_phase2_20260525T004154.jsonl"
DF_CAP = 200


def load_db(con):
    cents = {}
    for sid, blob in con.execute("SELECT synset_id, centroid FROM synset_centroids"):
        cents[sid] = np.frombuffer(blob, dtype=np.float32)
    concr = {sid: float(s) for sid, s in con.execute("SELECT synset_id, score FROM synset_concreteness")}
    poly = {}
    for sid, p in con.execute("SELECT synset_id, polysemy FROM property_vocab_curated"):
        poly.setdefault(sid, p)
    pcount = {sid: c for sid, c in con.execute("SELECT synset_id, property_count FROM synset_centroids")}
    # synset -> {cluster: salience}; cluster df; cluster dominant_type
    syn2cl = defaultdict(dict)
    cl_members = defaultdict(int)
    for sid, cid, sal in con.execute("SELECT synset_id, cluster_id, salience_sum FROM synset_properties_curated"):
        syn2cl[sid][cid] = float(sal); cl_members[cid] += 1
    cl_type = {}
    for cid, dt in con.execute("SELECT cluster_id, dominant_type FROM vocab_clusters WHERE is_representative=1"):
        if dt: cl_type[cid] = dt
    # fallback: any row's dominant_type per cluster
    for cid, dt in con.execute("SELECT cluster_id, dominant_type FROM vocab_clusters"):
        if dt: cl_type.setdefault(cid, dt)
    n = len(syn2cl)
    return cents, concr, poly, pcount, syn2cl, cl_members, cl_type, n


def build_resolver(con):
    """Fast in-memory word->synset_id resolver: noun-preferred, least-polysemous.

    Replaces metaphor_graph.lookup_primary_synset (whose morphological fallback
    is ~0.4s/word). Drops words that don't resolve directly; coverage reported.
    Mirrors the noun-preferred / least-polysemous primary-sense rule.
    """
    pos = {sid: p for sid, p in con.execute("SELECT synset_id, pos FROM synsets")}
    # curated: lemma -> best (prefer noun, then min polysemy)
    best = {}
    for sid, lemma, p, poly in con.execute(
        "SELECT synset_id, lemma, pos, polysemy FROM property_vocab_curated"
    ):
        key = lemma.strip().lower()
        # rank: noun first (0), else 1; then lower polysemy
        rank = (0 if p == 'n' else 1, poly)
        if key not in best or rank < best[key][0]:
            best[key] = (rank, sid)
    curated = {k: v[1] for k, v in best.items()}
    # lemmas fallback: lemma -> noun-preferred synset
    lem = {}
    for lemma, sid in con.execute("SELECT lemma, synset_id FROM lemmas"):
        key = lemma.strip().lower()
        is_noun = pos.get(sid) == 'n'
        if key not in lem or (is_noun and pos.get(lem[key]) != 'n'):
            lem[key] = sid

    def resolve(w):
        if not w:
            return None
        k = w.strip().lower()
        if k in curated:
            return curated[k]
        if k in lem:
            return lem[k]
        # light morphological strips (cheap, dict lookups only)
        for suf in ("s", "es", "ing", "ed"):
            if k.endswith(suf):
                base = k[: -len(suf)]
                if base in curated:
                    return curated[base]
                if base in lem:
                    return lem[base]
        return None

    return resolve


def cosdist(a, b):
    if a is None or b is None: return None
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0: return None
    return 1.0 - float(np.dot(a, b) / (na * nb))


def feats(tsid, vsid, D):
    cents, concr, poly, pcount, syn2cl, cl_members, cl_type, n = D
    cd = cosdist(cents.get(tsid), cents.get(vsid))
    if cd is None: return None
    tcl = {c: s for c, s in syn2cl.get(tsid, {}).items() if cl_members.get(c, 0) <= DF_CAP}
    vcl = {c: s for c, s in syn2cl.get(vsid, {}).items() if cl_members.get(c, 0) <= DF_CAP}
    shared = set(tcl) & set(vcl)
    shared_idf = sum(math.log(n / cl_members[c]) for c in shared) if shared else 0.0
    ttypes = {cl_type[c] for c in tcl if c in cl_type}
    vtypes = {cl_type[c] for c in vcl if c in cl_type}
    ct, cv = concr.get(tsid), concr.get(vsid)
    return {
        "cos_dist": cd,
        "concr_t": ct if ct is not None else 3.0,
        "concr_v": cv if cv is not None else 3.0,
        "concr_gap": (cv - ct) if (ct is not None and cv is not None) else 0.0,
        "shared_n": float(len(shared)),
        "shared_idf": shared_idf,
        "type_new": float(len(vtypes - ttypes)),
        "type_union": float(len(ttypes | vtypes)),
        "poly_t": float(poly.get(tsid, 0)),
        "poly_v": float(poly.get(vsid, 0)),
        "pcount_t": float(pcount.get(tsid, 0)),
        "pcount_v": float(pcount.get(vsid, 0)),
    }


def load_pairs(con, D, resolve):
    rows = []
    miss = {"topic": 0, "vehicle": 0, "feat": 0}
    for path, key, label in [(APT, "metaphors", 1), (INAPT, "inapt_metaphors", 0)]:
        for line in Path(path).read_text().splitlines():
            if not line.strip(): continue
            d = json.loads(line); topic = d["topic"]; tsid = resolve(topic)
            if not tsid: miss["topic"] += 1; continue
            for m in d.get(key, []):
                v = m.get("vehicle")
                if not v: continue
                vsid = resolve(v)
                if not vsid: miss["vehicle"] += 1; continue
                f = feats(tsid, vsid, D)
                if f is None: miss["feat"] += 1; continue
                rows.append({"topic": topic, "vehicle": v, "label": label, **f})
    return rows, miss


def auc_single(y, x):
    # AUC of a single feature (handle direction)
    try:
        a = roc_auc_score(y, x)
        return max(a, 1 - a)
    except Exception:
        return float("nan")


def main():
    con = sqlite3.connect(DB)
    D = load_db(con)
    resolve = build_resolver(con)
    rows, miss = load_pairs(con, D, resolve)
    con.close()
    n_apt = sum(r["label"] for r in rows); n_in = len(rows) - n_apt
    print(f"resolved pairs: {len(rows)} (apt={n_apt}, inapt={n_in}); misses={miss}")
    if n_apt < 20 or n_in < 20:
        print("INSUFFICIENT resolved pairs — aborting"); return

    fnames = ["cos_dist","concr_t","concr_v","concr_gap","shared_n","shared_idf",
              "type_new","type_union","poly_t","poly_v","pcount_t","pcount_v"]
    X = np.array([[r[f] for f in fnames] for r in rows], dtype=float)
    y = np.array([r["label"] for r in rows])
    groups = np.array([r["topic"] for r in rows])

    print("\n=== single-feature pooled AUC (direction-corrected) ===")
    for i, f in enumerate(fnames):
        print(f"  {f:>12}: AUC={auc_single(y, X[:, i]):.3f}")

    def grouped_auc(cols, label):
        idx = [fnames.index(c) for c in cols]
        Xs = X[:, idx]
        gkf = GroupKFold(n_splits=5)
        aucs = []
        for tr, te in gkf.split(Xs, y, groups):
            clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
            clf.fit(Xs[tr], y[tr])
            p = clf.predict_proba(Xs[te])[:, 1]
            try: aucs.append(roc_auc_score(y[te], p))
            except Exception: pass
        aucs = np.array(aucs)
        print(f"  {label:<34} MEAN AUC = {aucs.mean():.3f} +/- {aucs.std():.3f}  folds={np.round(aucs,3).tolist()}")
        return aucs.mean()

    print("\n=== topic-grouped 5-fold logistic regression — ABLATIONS ===")
    grouped_auc(fnames, "ALL features")
    grouped_auc(["concr_v","concr_t","concr_gap"], "concreteness ONLY")
    grouped_auc(["cos_dist","shared_n","shared_idf","type_new","type_union"], "topic-specific ONLY (no concr)")
    grouped_auc(["shared_n","shared_idf","type_new","type_union"], "shared-feature substrate ONLY")
    grouped_auc(["cos_dist"], "embedding distance ONLY")

    print("\n=== concreteness distribution apt vs inapt (artifact check) ===")
    cv = np.array([r["concr_v"] for r in rows]); ya = y == 1
    print(f"  apt   vehicle concreteness: mean={cv[ya].mean():.2f} sd={cv[ya].std():.2f} n={ya.sum()}")
    print(f"  inapt vehicle concreteness: mean={cv[~ya].mean():.2f} sd={cv[~ya].std():.2f} n={(~ya).sum()}")
    ct = np.array([r["concr_t"] for r in rows])
    print(f"  topic concreteness: apt-side mean={ct[ya].mean():.2f}  inapt-side mean={ct[~ya].mean():.2f} (should be ~equal; topics shared)")
    aucs = np.array([0.0])

    # within-topic separation (no leakage by construction)
    by_topic = defaultdict(list)
    for i, r in enumerate(rows): by_topic[r["topic"]].append(i)
    # train one global model (grouped CV proxy), score within topic
    clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
    clf.fit(X, y)  # NB: in-sample; within-topic AUC reported as upper bound, flagged
    s = clf.predict_proba(X)[:, 1]
    wt_aucs = []; apt_gt = 0; n_top = 0
    for t, idxs in by_topic.items():
        yt = y[idxs]
        if yt.min() == yt.max(): continue
        n_top += 1
        try:
            a = roc_auc_score(yt, s[idxs]); wt_aucs.append(a)
            if s[[i for i in idxs if y[i]==1]].mean() > s[[i for i in idxs if y[i]==0]].mean(): apt_gt += 1
        except Exception: pass
    wt_aucs = np.array(wt_aucs)
    print("\n=== RECALL CEILING of shared-feature candidate generation ===")
    sn = np.array([r["shared_n"] for r in rows])
    print(f"  apt   pairs sharing >=1 df-capped cluster: {(sn[ya]>=1).mean():.2%}  >=2: {(sn[ya]>=2).mean():.2%}  mean_shared={sn[ya].mean():.2f}")
    print(f"  inapt pairs sharing >=1 df-capped cluster: {(sn[~ya]>=1).mean():.2%}  >=2: {(sn[~ya]>=2).mean():.2%}  mean_shared={sn[~ya].mean():.2f}")
    print("  (If apt pairs rarely share a cluster, shared-feature DERIVATION cannot even propose the apt vehicles -> zero recall.)")

    print(f"\n=== within-topic separation (IN-SAMPLE upper bound, {n_top} mixed topics) ===")
    print(f"  mean within-topic AUC = {wt_aucs.mean():.3f}; frac topics apt-mean>inapt-mean = {apt_gt}/{n_top} = {apt_gt/n_top:.2f}")
    print("\nINTERPRETATION: grouped-CV MEAN AUC is the honest out-of-sample number.")
    print("AUC ~0.5 => context-free features cannot separate apt from plausible-inapt (=> must LLM-generate/verify).")
    print("AUC >=0.75 => a cheap context-free proposer/filter is viable (=> H-C lives).")


if __name__ == "__main__":
    main()
