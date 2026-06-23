#!/usr/bin/env python3
"""H-C FAST multivariate separability (no API). Same features as
separability_experiment.py but bulk-loads centroids and reports, in addition:
  - topic-grouped 5-fold logistic-regression ROC-AUC (mean +/- std) = headline
  - precision@k operating points (apt-precision of the top-k-scored fraction)
  - calibration curve (predicted-prob bins vs empirical apt rate)
  - per-inapt-class recall-at-fixed-apt-recall (dead-metaphor leakage)
  - spot-check rate implied to hit a target admitted-edge precision

The headline grouped-CV AUC is the decisive H-C number; everything else
characterises the quality/cost trade at 100k.
"""
from __future__ import annotations
import json, math, sqlite3, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path("data-pipeline/scripts").resolve()))
from metaphor_graph import lookup_primary_synset  # noqa: E402
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
    rows = con.execute("SELECT synset_id, centroid, property_count FROM synset_centroids").fetchall()
    cents = {sid: np.frombuffer(blob, dtype=np.float32) for sid, blob, _ in rows}
    pcount = {sid: c for sid, _, c in rows}
    concr = {sid: float(s) for sid, s in con.execute("SELECT synset_id, score FROM synset_concreteness")}
    poly = {}
    for sid, p in con.execute("SELECT synset_id, polysemy FROM property_vocab_curated"):
        poly.setdefault(sid, p)
    syn2cl = defaultdict(dict); cl_members = defaultdict(int)
    for sid, cid, sal in con.execute("SELECT synset_id, cluster_id, salience_sum FROM synset_properties_curated"):
        syn2cl[sid][cid] = float(sal); cl_members[cid] += 1
    cl_type = {}
    for cid, dt in con.execute("SELECT cluster_id, dominant_type FROM vocab_clusters"):
        if dt: cl_type.setdefault(cid, dt)
    # lemma-mean concreteness (sense-agnostic) per surface word, built on demand
    return cents, concr, poly, pcount, syn2cl, cl_members, cl_type, len(syn2cl)


def cosdist(a, b):
    if a is None or b is None: return None
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0: return None
    return 1.0 - float(np.dot(a, b) / (na * nb))


def feats(tsid, vsid, lemma_grad, D):
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
        "concr_gap_snap": (cv - ct) if (ct is not None and cv is not None) else 0.0,
        "concr_grad_lemma": lemma_grad if lemma_grad is not None else 0.0,
        "shared_n": float(len(shared)),
        "shared_idf": shared_idf,
        "type_new": float(len(vtypes - ttypes)),
        "type_union": float(len(ttypes | vtypes)),
        "poly_t": float(poly.get(tsid, 0)),
        "poly_v": float(poly.get(vsid, 0)),
        "pcount_t": float(pcount.get(tsid, 0)),
        "pcount_v": float(pcount.get(vsid, 0)),
    }


def lemma_concr_fn(con):
    cache = {}
    def f(w):
        if w in cache: return cache[w]
        rows = con.execute(
            "SELECT sc.score FROM lemmas l JOIN synset_concreteness sc "
            "ON sc.synset_id=l.synset_id WHERE l.lemma=?", (w,)).fetchall()
        vals = [r[0] for r in rows]
        cache[w] = (sum(vals) / len(vals)) if vals else None
        return cache[w]
    return f


def load_pairs(con, D):
    lc = lemma_concr_fn(con)
    rows = []; cache = {}
    def resolve(w):
        if w not in cache: cache[w] = lookup_primary_synset(con, w)
        return cache[w]
    for path, key, label in [(APT, "metaphors", 1), (INAPT, "inapt_metaphors", 0)]:
        for line in Path(path).read_text().splitlines():
            if not line.strip(): continue
            d = json.loads(line); topic = d["topic"]; tsid = resolve(topic)
            ct = lc(topic)
            if not tsid: continue
            for m in d.get(key, []):
                v = m.get("vehicle")
                if not v: continue
                vsid = resolve(v)
                if not vsid: continue
                cv = lc(v)
                grad = (cv - ct) if (ct is not None and cv is not None) else None
                f = feats(tsid, vsid, grad, D)
                if f is None: continue
                rows.append({"topic": topic, "vehicle": v, "label": label,
                             "rt": m.get("inapt_reason_type", "apt"), **f})
    return rows


def auc1(y, x):
    try:
        a = roc_auc_score(y, x); return max(a, 1 - a)
    except Exception:
        return float("nan")


def main():
    con = sqlite3.connect(DB); D = load_db(con); rows = load_pairs(con, D); con.close()
    n_apt = sum(r["label"] for r in rows); n_in = len(rows) - n_apt
    out = {"n_resolved": len(rows), "n_apt": n_apt, "n_inapt": n_in}
    fnames = ["cos_dist","concr_gap_snap","concr_grad_lemma","shared_n","shared_idf",
              "type_new","type_union","poly_t","poly_v","pcount_t","pcount_v"]
    X = np.array([[r[f] for f in fnames] for r in rows], float)
    y = np.array([r["label"] for r in rows]); groups = np.array([r["topic"] for r in rows])
    out["single_feature_auc"] = {f: round(auc1(y, X[:, i]), 3) for i, f in enumerate(fnames)}

    # topic-grouped CV: AUC + out-of-fold predicted probs (for calibration/precision@k)
    gkf = GroupKFold(n_splits=5); aucs = []; oof = np.full(len(y), np.nan)
    coefs = []
    for tr, te in gkf.split(X, y, groups):
        clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
        clf.fit(X[tr], y[tr]); p = clf.predict_proba(X[te])[:, 1]; oof[te] = p
        try: aucs.append(roc_auc_score(y[te], p))
        except Exception: pass
        coefs.append(clf.named_steps["logisticregression"].coef_[0])
    aucs = np.array(aucs)
    out["grouped_cv_auc_mean"] = round(float(aucs.mean()), 3)
    out["grouped_cv_auc_std"] = round(float(aucs.std()), 3)
    out["grouped_cv_fold_aucs"] = [round(float(a), 3) for a in aucs]
    out["mean_abs_coef"] = {f: round(float(abs(np.mean([c[i] for c in coefs]))), 3)
                            for i, f in enumerate(fnames)}

    # precision@k using OOF scores: keep top-k fraction by score, report apt precision + recall
    order = np.argsort(-oof); ys = y[order]
    out["precision_at_topk"] = []
    base = n_apt / len(y)
    for frac in [0.1, 0.25, 0.5, 0.75, 1.0]:
        k = max(1, int(frac * len(ys))); kept = ys[:k]
        out["precision_at_topk"].append({
            "keep_frac": frac, "k": k,
            "apt_precision": round(float(kept.mean()), 3),
            "apt_recall": round(float(kept.sum() / n_apt), 3),
            "lift_over_base": round(float(kept.mean() / base), 3)})

    # calibration: 10 prob bins, empirical apt rate
    bins = np.linspace(0, 1, 11); out["calibration"] = []
    for i in range(10):
        m = (oof >= bins[i]) & (oof < bins[i + 1] if i < 9 else oof <= 1.0)
        if m.sum() == 0: continue
        out["calibration"].append({
            "bin": f"[{bins[i]:.1f},{bins[i+1]:.1f})", "n": int(m.sum()),
            "pred_mean": round(float(oof[m].mean()), 3),
            "empirical_apt": round(float(y[m].mean()), 3)})

    # dead-metaphor leakage at fixed apt recall thresholds on OOF score
    rt = np.array([r["rt"] for r in rows])
    dead_mask = (rt == "dead_metaphor"); apt_mask = (y == 1)
    out["dead_leakage_vs_apt_recall"] = []
    for thr_q in [0.5, 0.6, 0.7, 0.8, 0.9]:
        # choose score threshold to retain thr_q of apt
        apt_scores = np.sort(oof[apt_mask])
        cut = apt_scores[int((1 - thr_q) * len(apt_scores))]
        dead_kept = (oof[dead_mask] >= cut).mean() if dead_mask.sum() else None
        inapt_kept = (oof[(y == 0)] >= cut).mean()
        out["dead_leakage_vs_apt_recall"].append({
            "target_apt_recall": thr_q, "score_cut": round(float(cut), 3),
            "dead_kept_frac": round(float(dead_kept), 3) if dead_kept is not None else None,
            "all_inapt_kept_frac": round(float(inapt_kept), 3)})

    # per-inapt-class OOF AUC (apt vs that class)
    out["per_inapt_class_auc"] = {}
    for cls in sorted(set(rt[y == 0])):
        m = apt_mask | (rt == cls)
        try: out["per_inapt_class_auc"][cls] = round(float(roc_auc_score(y[m], oof[m])), 3)
        except Exception: pass

    print(json.dumps(out, indent=2))
    Path("docs/inbox/2026-06-03-context-free-edges/artifacts/hc_multivariate_result.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
