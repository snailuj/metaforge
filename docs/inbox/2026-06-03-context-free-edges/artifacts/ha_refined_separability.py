#!/usr/bin/env python3
"""H-A refined — distance-gated, feature-anchored derivation: SEPARABILITY HARNESS.

Mission artifact. Scores the labelled spike cohort (apt vs inapt) with the
*corrected* H-A matching function and reports separation (ROC-AUC + operating
points), so we can decide whether selective-match-at-distance beats the
pointwise-overlap family that M02 already failed.

NO API CALLS. Pure SQL + Python over existing data:
  - synset_centroids        (300d FastText)  -> cross-domain distance
  - synset_properties_curated x vocab_clusters.dominant_type -> typed feature overlap
  - synset_concreteness     -> Lakoff concreteness gradient (vehicle - topic)
Cohort: data-pipeline/output/metaphor_spike_{apt,inapt}_phase2_*.jsonl

Run:
  python3 ha_refined_separability.py \
      --db data-pipeline/output/lexicon_v2.db \
      --apt  data-pipeline/output/metaphor_spike_apt_phase2_20260525T004154.jsonl \
      --inapt data-pipeline/output/metaphor_spike_inapt_phase2_20260525T004154.jsonl \
      --bootstrap 1000 -o ha_refined_result.json

Design notes / confronting M02:
  * M02 killed pointwise property-OVERLAP as a *scorer*. This harness tests
    whether a DIFFERENT objective (distance + concreteness gradient + selective
    cross-type feature presence) separates apt from inapt. It reports each leg's
    AUC separately so the steelman is falsifiable leg-by-leg.
  * Sense-snapping (F4/C13) is the dominant validity threat. We compute the
    concreteness gradient TWO ways: (a) best-sense snap, (b) lemma-mean
    (sense-agnostic) — and report both so the headline is robust to snap noise.
"""
from __future__ import annotations
import argparse, json, math, sqlite3, struct, statistics, random
from collections import Counter, defaultdict
from pathlib import Path


def vec(b: bytes):
    return list(struct.unpack(f"<{len(b)//4}f", b))


class Substrate:
    def __init__(self, db: str):
        self.con = sqlite3.connect(db)
        self._cent = {}
        self._clu = {}
        self._concr = {}

    def synsets_for(self, w):
        return [r[0] for r in self.con.execute(
            "SELECT synset_id FROM lemmas WHERE lemma=?", (w,))]

    def centroid(self, s):
        if s not in self._cent:
            r = self.con.execute(
                "SELECT centroid FROM synset_centroids WHERE synset_id=?", (s,)).fetchone()
            self._cent[s] = vec(r[0]) if r else None
        return self._cent[s]

    def clusters(self, s):
        """cluster_id -> dominant_type for this synset's curated clusters."""
        if s not in self._clu:
            rows = self.con.execute(
                "SELECT spc.cluster_id, vc.dominant_type FROM synset_properties_curated spc "
                "JOIN vocab_clusters vc ON vc.cluster_id=spc.cluster_id WHERE spc.synset_id=?",
                (s,)).fetchall()
            self._clu[s] = {r[0]: r[1] for r in rows}
        return self._clu[s]

    def concr(self, s):
        if s not in self._concr:
            r = self.con.execute(
                "SELECT score FROM synset_concreteness WHERE synset_id=?", (s,)).fetchone()
            self._concr[s] = r[0] if r else None
        return self._concr[s]

    def pick_synset(self, w, gloss=None):
        """Naive WSD: prefer a sense with BOTH centroid and curated clusters.
        TODO(orchestrator, optional): replace with gloss-cosine WSD using the
        topic _gloss field. Measured: lemma-mean concreteness already removes
        most snap sensitivity, so this is a secondary refinement."""
        sids = self.synsets_for(w)
        for s in sids:
            if self.centroid(s) and self.clusters(s):
                return s
        for s in sids:
            if self.centroid(s):
                return s
        return sids[0] if sids else None

    def lemma_concr(self, w):
        vals = [self.concr(s) for s in self.synsets_for(w)]
        vals = [v for v in vals if v is not None]
        return statistics.mean(vals) if vals else None


def cos(a, b):
    da = math.sqrt(sum(x * x for x in a)); db = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (da * db) if da and db else 0.0


def feats(sub: Substrate, t, v):
    ts = sub.pick_synset(t); vs = sub.pick_synset(v)
    if not ts or not vs:
        return None
    ct = sub.centroid(ts); cv = sub.centroid(vs)
    dist = (1 - cos(ct, cv)) if (ct and cv) else None
    ct_clu = sub.clusters(ts); vc_clu = sub.clusters(vs)
    shared = set(ct_clu) & set(vc_clu)
    tdom = Counter(x for x in ct_clu.values() if x).most_common(1)
    tdom = tdom[0][0] if tdom else None
    cross_type = len([c for c in shared if vc_clu.get(c) != tdom])
    grad_snap = (sub.concr(vs) - sub.concr(ts)) if (
        sub.concr(vs) is not None and sub.concr(ts) is not None) else None
    tg = sub.lemma_concr(t); vg = sub.lemma_concr(v)
    grad_lemma = (vg - tg) if (tg is not None and vg is not None) else None
    return dict(dist=dist, n_shared=len(shared), cross_type=cross_type,
                grad_snap=grad_snap, grad_lemma=grad_lemma)


def auc(pos, neg):
    pos = [p for p in pos if p is not None]; neg = [n for n in neg if n is not None]
    if not pos or not neg:
        return None
    allv = sorted([(s, 1) for s in pos] + [(s, 0) for s in neg])
    ranks = [0] * len(allv); i = 0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        r = (i + 1 + j) / 2
        for k in range(i, j):
            ranks[k] = r
        i = j
    R = sum(ranks[k] for k in range(len(allv)) if allv[k][1] == 1)
    n1, n2 = len(pos), len(neg)
    return (R - n1 * (n1 + 1) / 2) / (n1 * n2)


def boot_ci(pos, neg, n, seed=0):
    pos = [p for p in pos if p is not None]; neg = [x for x in neg if x is not None]
    random.seed(seed); out = []
    for _ in range(n):
        pa = [random.choice(pos) for _ in pos]; pi = [random.choice(neg) for _ in neg]
        a = auc(pa, pi)
        if a is not None:
            out.append(a)
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data-pipeline/output/lexicon_v2.db")
    ap.add_argument("--apt", required=True)
    ap.add_argument("--inapt", required=True)
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    sub = Substrate(args.db)
    apt = [json.loads(l) for l in open(args.apt)]
    inapt = [json.loads(l) for l in open(args.inapt)]

    A, I = [], []  # feature dicts + reason_type
    for r in apt:
        for m in r.get("metaphors", []):
            f = feats(sub, r["topic"], m["vehicle"])
            if f:
                f["rt"] = "apt"; A.append(f)
    for r in inapt:
        for m in r.get("inapt_metaphors", []):
            f = feats(sub, r["topic"], m["vehicle"])
            if f:
                f["rt"] = m.get("inapt_reason_type"); I.append(f)

    legs = {
        "cos_dist": lambda f: f["dist"],
        "concr_grad_snap": lambda f: f["grad_snap"],
        "concr_grad_lemma": lambda f: f["grad_lemma"],
        "cross_type_shared": lambda f: f["cross_type"],
        "neg_shared_curated": lambda f: -f["n_shared"],
        "dist_plus_0.15grad": lambda f: (f["dist"] or 0) + 0.15 * (f["grad_lemma"] or 0),
    }
    result = {"n_apt": len(A), "n_inapt": len(I), "legs": {}, "operating_points": [],
              "per_inapt_class": {}}
    for name, fn in legs.items():
        pos = [fn(f) for f in A]; neg = [fn(f) for f in I]
        a = auc(pos, neg)
        ci = boot_ci(pos, neg, args.bootstrap) if a is not None else None
        result["legs"][name] = {"auc": a, "ci95": ci}

    # operating points for the surviving gate (lemma concreteness gradient)
    Ag = [f["grad_lemma"] for f in A if f["grad_lemma"] is not None]
    Ig = [f["grad_lemma"] for f in I if f["grad_lemma"] is not None]
    base = len(Ag) / (len(Ag) + len(Ig))
    for thr in [0.0, 0.3, 0.5, 0.7, 1.0, 1.5]:
        ak = sum(g >= thr for g in Ag); ik = sum(g >= thr for g in Ig)
        result["operating_points"].append(dict(
            thr=thr, apt_kept=ak, inapt_kept=ik,
            precision=ak / (ak + ik) if (ak + ik) else None,
            apt_recall=ak / len(Ag)))
    result["base_rate"] = base

    # per inapt reason-type, AUC of lemma gradient (apt vs that class)
    by = defaultdict(list)
    for f in I:
        by[f["rt"]].append(f["grad_lemma"])
    for rt, gs in by.items():
        result["per_inapt_class"][rt] = {"n": len(gs), "auc_grad": auc(Ag, gs)}

    text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
