#!/usr/bin/env python3
"""H-B harness: embedding ANN band recall + apt-vs-inapt enrichment (API-FREE).

Measures the make-or-break number for approach H-B (ANN candidate-gen + Haiku
verify): for each spike topic, snap to synset(s), rank ALL synset_centroids by
cosine, and check at what band size b the topic's GOLD apt vehicles appear, vs
its GOLD inapt vehicles. If apt vehicles sit deep / no deeper than inapt, the
band cannot be a high-precision candidate proposer and the verify step inherits
a hostile (inapt-enriched) candidate set.

Pure numpy + sqlite. Reproducible:
    python3 docs/inbox/2026-06-03-context-free-edges/artifacts/hb_band_recall.py

Inputs (existing data, no generation):
  - data-pipeline/output/lexicon_v2.db : synset_centroids (81,185 x 300 FastText),
    lemmas (lemma->synset), synsets
  - metaphor_spike_apt_phase2_*.jsonl  : 200 topics x ~6 gold apt vehicles
  - metaphor_spike_inapt_phase2_*.jsonl: 200 topics x 3 gold inapt vehicles

Outputs: band recall/enrichment table (stdout JSON) + per-topic apt min-ranks
(/tmp/hb_band_recall_per_topic.json) for percentile / bootstrap analysis.
"""
import sqlite3, json, sys, glob
import numpy as np

DB = "data-pipeline/output/lexicon_v2.db"
APT = sorted(glob.glob("data-pipeline/output/metaphor_spike_apt_phase2_*.jsonl"))[-1]
INAPT = sorted(glob.glob("data-pipeline/output/metaphor_spike_inapt_phase2_*.jsonl"))[-1]
BANDS = [10, 25, 50, 100, 200, 500, 1000]


def main():
    con = sqlite3.connect(DB)
    sids, vecs = [], []
    for sid, blob in con.execute("SELECT synset_id, centroid FROM synset_centroids"):
        sids.append(sid)
        vecs.append(np.frombuffer(blob, dtype=np.float32))
    M = np.vstack(vecs)
    idx_of = {s: i for i, s in enumerate(sids)}
    norms = np.linalg.norm(M, axis=1, keepdims=True); norms[norms == 0] = 1
    Mn = M / norms
    sys.stderr.write(f"loaded {M.shape[0]} centroids dim {M.shape[1]}\n")

    def lemma_synsets(lemma):
        rows = con.execute("SELECT synset_id FROM lemmas WHERE lemma=?", (lemma.lower(),)).fetchall()
        return [r[0] for r in rows if r[0] in idx_of]

    apt = [json.loads(l) for l in open(APT)]
    inapt = {json.loads(l)["topic"]: json.loads(l) for l in open(INAPT)}

    res = {pol: {b: {"apt_hit": 0, "apt_total": 0, "inapt_hit": 0, "inapt_total": 0}
                 for b in BANDS} for pol in ["first", "union"]}
    per_topic, skipped = [], 0

    for rec in apt:
        topic = rec["topic"]
        tsyn = lemma_synsets(topic)
        if not tsyn:
            skipped += 1; continue
        apt_veh = {m["vehicle"]: set(lemma_synsets(m["vehicle"])) for m in rec["metaphors"]}
        apt_veh = {v: s for v, s in apt_veh.items() if s}
        inapt_veh = {}
        if topic in inapt:
            inapt_veh = {m["vehicle"]: set(lemma_synsets(m["vehicle"])) for m in inapt[topic]["inapt_metaphors"]}
            inapt_veh = {v: s for v, s in inapt_veh.items() if s}

        for pol in ["first", "union"]:
            seeds = ([sorted(tsyn, key=lambda s: (len(s), s))[0]] if pol == "first" else tsyn)
            seed_idx = [idx_of[s] for s in seeds]
            best = (Mn @ Mn[seed_idx].T).max(axis=1)
            order = np.argsort(-best)
            topic_idx = set(idx_of[s] for s in tsyn)
            ranked = [sids[i] for i in order if i not in topic_idx]
            rankpos = {s: p for p, s in enumerate(ranked)}
            for b in BANDS:
                band = set(ranked[:b])
                for v, vs in apt_veh.items():
                    res[pol][b]["apt_total"] += 1
                    if vs & band:
                        res[pol][b]["apt_hit"] += 1
                for v, vs in inapt_veh.items():
                    res[pol][b]["inapt_total"] += 1
                    if vs & band:
                        res[pol][b]["inapt_hit"] += 1
            if pol == "union":
                mr = [(v, min((rankpos[s] for s in vs if s in rankpos), default=None))
                      for v, vs in apt_veh.items()]
                per_topic.append({"topic": topic, "apt_min_ranks": mr})

    sys.stderr.write(f"topics skipped (unsnappable): {skipped}\n")
    print(json.dumps({"n_topics": len(apt) - skipped, "bands": BANDS, "results": res}, indent=2))
    json.dump(per_topic, open("/tmp/hb_band_recall_per_topic.json", "w"), indent=1)


if __name__ == "__main__":
    main()
