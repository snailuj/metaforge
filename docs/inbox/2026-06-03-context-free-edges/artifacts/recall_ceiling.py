#!/usr/bin/env python3
"""RED-TEAM the near-zero recall finding across granularities.

Is shared-feature overlap of apt pairs near-zero because of clustering
granularity (df-cap / curated-vs-raw), or is it fundamental? Measures, for apt
and inapt spike pairs, the fraction sharing >=1 feature at FOUR granularities:
  1. curated cluster, df-cap 200   (mega-clusters dropped)
  2. curated cluster, NO cap       (all clusters incl. mega)
  3. raw property_id               (synset_properties exact property match)
  4. raw property TEXT token       (looser: any shared content word in props)
Plus the deepest test:
  5. Haiku-claimed shared_feature present in BOTH synsets' raw property texts
     (does the static enrichment independently reconstruct the metaphor's own
      stated shared features?)
"""
from __future__ import annotations
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

DB = "data-pipeline/output/lexicon_v2.db"
APT = "data-pipeline/output/metaphor_spike_apt_phase2_20260525T004154.jsonl"
INAPT = "data-pipeline/output/metaphor_spike_inapt_phase2_20260525T004154.jsonl"
DF_CAP = 200
STOP = set("a an the of to and or for with without is are be being can will "
           "that this these those it its as at by on in into from your you".split())


def build_resolver(con):
    pos = {sid: p for sid, p in con.execute("SELECT synset_id, pos FROM synsets")}
    best = {}
    for sid, lemma, p, poly in con.execute(
        "SELECT synset_id, lemma, pos, polysemy FROM property_vocab_curated"):
        k = lemma.strip().lower(); rank = (0 if p == 'n' else 1, poly)
        if k not in best or rank < best[k][0]: best[k] = (rank, sid)
    curated = {k: v[1] for k, v in best.items()}
    lem = {}
    for lemma, sid in con.execute("SELECT lemma, synset_id FROM lemmas"):
        k = lemma.strip().lower(); n = pos.get(sid) == 'n'
        if k not in lem or (n and pos.get(lem[k]) != 'n'): lem[k] = sid
    def resolve(w):
        if not w: return None
        k = w.strip().lower()
        if k in curated: return curated[k]
        if k in lem: return lem[k]
        for suf in ("s","es","ing","ed"):
            if k.endswith(suf):
                b = k[:-len(suf)]
                if b in curated: return curated[b]
                if b in lem: return lem[b]
        return None
    return resolve


def main():
    con = sqlite3.connect(DB)
    resolve = build_resolver(con)
    # curated clusters
    syn2cl = defaultdict(set); cl_df = defaultdict(int)
    for sid, cid in con.execute("SELECT synset_id, cluster_id FROM synset_properties_curated"):
        syn2cl[sid].add(cid); cl_df[cid] += 1
    # raw properties
    pid_text = {pid: t for pid, t in con.execute("SELECT property_id, text FROM property_vocabulary")}
    syn2pid = defaultdict(set); syn2tok = defaultdict(set)
    for sid, pid in con.execute("SELECT synset_id, property_id FROM synset_properties"):
        syn2pid[sid].add(pid)
        t = pid_text.get(pid, "")
        for w in t.lower().replace("/", " ").replace("-", " ").split():
            if w not in STOP and len(w) > 2: syn2tok[sid].add(w)
    con.close()

    def metrics(path, key):
        out = {"n":0, "c_cap":0, "c_all":0, "raw_pid":0, "raw_tok":0,
               "haiku_feat_in_both":0, "haiku_feat_total":0, "haiku_pairs":0}
        for line in Path(path).read_text().splitlines():
            if not line.strip(): continue
            d = json.loads(line); tsid = resolve(d["topic"])
            if not tsid: continue
            for m in d.get(key, []):
                vsid = resolve(m.get("vehicle"))
                if not vsid: continue
                out["n"] += 1
                tc, vc = syn2cl.get(tsid, set()), syn2cl.get(vsid, set())
                tc_cap = {c for c in tc if cl_df[c] <= DF_CAP}
                vc_cap = {c for c in vc if cl_df[c] <= DF_CAP}
                if tc_cap & vc_cap: out["c_cap"] += 1
                if tc & vc: out["c_all"] += 1
                if syn2pid.get(tsid, set()) & syn2pid.get(vsid, set()): out["raw_pid"] += 1
                if syn2tok.get(tsid, set()) & syn2tok.get(vsid, set()): out["raw_tok"] += 1
                # Haiku-claimed shared features present in BOTH synsets' prop tokens?
                feats = m.get("shared_features", [])
                if feats:
                    out["haiku_pairs"] += 1
                    ttok, vtok = syn2tok.get(tsid, set()), syn2tok.get(vsid, set())
                    for sf in feats:
                        concept = (sf.get("concept") if isinstance(sf, dict) else str(sf)) or ""
                        out["haiku_feat_total"] += 1
                        cwords = {w for w in concept.lower().split() if w not in STOP and len(w) > 2}
                        if cwords and (cwords & ttok) and (cwords & vtok):
                            out["haiku_feat_in_both"] += 1
        return out

    for tag, path, key in [("APT", APT, "metaphors"), ("INAPT", INAPT, "inapt_metaphors")]:
        o = metrics(path, key); n = max(o["n"], 1)
        print(f"\n=== {tag} (n={o['n']} resolved pairs) — fraction sharing >=1 feature ===")
        print(f"  curated cluster, df-cap {DF_CAP}: {o['c_cap']/n:.2%}")
        print(f"  curated cluster, NO cap        : {o['c_all']/n:.2%}")
        print(f"  raw property_id exact          : {o['raw_pid']/n:.2%}")
        print(f"  raw property TEXT token        : {o['raw_tok']/n:.2%}")
        if o["haiku_feat_total"]:
            print(f"  Haiku-claimed shared feature present in BOTH synsets' props: "
                  f"{o['haiku_feat_in_both']}/{o['haiku_feat_total']} = "
                  f"{o['haiku_feat_in_both']/o['haiku_feat_total']:.2%} of claimed features")


if __name__ == "__main__":
    main()
