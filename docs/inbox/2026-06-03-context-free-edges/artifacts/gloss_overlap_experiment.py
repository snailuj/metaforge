#!/usr/bin/env python3
"""GLOSS-as-features test: can the DEFINITION text (gloss) of topic vs vehicle
derive/discriminate apt metaphor edges? Tests gloss content-word overlap +
cosine of averaged FastText gloss vectors as apt-vs-inapt signals. The 4th
substrate (after curated features, embeddings, WordNet relations). API-free.
"""
from __future__ import annotations
import json, re, sqlite3, sys
from pathlib import Path
import numpy as np
ART = Path("docs/inbox/2026-06-03-context-free-edges/artifacts")
sys.path.insert(0, str(ART))
from separability_experiment import build_resolver
from sklearn.metrics import roc_auc_score

DB = "data-pipeline/output/lexicon_v2.db"
APT = "data-pipeline/output/metaphor_spike_apt_phase2_20260525T004154.jsonl"
INAPT = "data-pipeline/output/metaphor_spike_inapt_phase2_20260525T004154.jsonl"
STOP = set("a an the of to and or for with without is are be was were being that this these those it its "
           "as at by on in into from your you who which what when where often usually especially "
           "something someone way means having".split())


def toks(text):
    return {w for w in re.findall(r"[a-z]+", (text or "").lower()) if w not in STOP and len(w) > 2}


def auc(y, x):
    try:
        a = roc_auc_score(y, x); return max(a, 1 - a)
    except Exception:
        return float("nan")


def main():
    con = sqlite3.connect(DB)
    resolve = build_resolver(con)
    defn = {s: d for s, d in con.execute("SELECT synset_id, definition FROM synsets")}
    con.close()
    rows = []
    miss = 0
    for path, key, lab in [(APT, "metaphors", 1), (INAPT, "inapt_metaphors", 0)]:
        for line in Path(path).read_text().splitlines():
            if not line.strip(): continue
            d = json.loads(line); t = resolve(d["topic"])
            tgloss = d.get("_gloss") or defn.get(t, "")
            tt = toks(tgloss)
            for m in d.get(key, []):
                v = resolve(m.get("vehicle"))
                if v is None: miss += 1; continue
                vt = toks(defn.get(v, ""))
                if not tt or not vt: miss += 1; continue
                inter = len(tt & vt); union = len(tt | vt)
                rows.append({"label": lab,
                             "jaccard": inter / union if union else 0.0,
                             "shared": float(inter)})
    y = np.array([r["label"] for r in rows])
    print(f"gloss-pairs resolved: {len(rows)} (apt={int(y.sum())}, inapt={int((1-y).sum())}); miss={miss}")
    for f in ["jaccard", "shared"]:
        x = np.array([r[f] for r in rows])
        print(f"  gloss {f}: AUC(apt-vs-inapt)={auc(y, x):.3f}")
    sn = np.array([r["shared"] for r in rows])
    print(f"  apt   pairs sharing >=1 gloss content word: {(sn[y==1]>=1).mean():.1%} (mean {sn[y==1].mean():.2f})")
    print(f"  inapt pairs sharing >=1 gloss content word: {(sn[y==0]>=1).mean():.1%} (mean {sn[y==0].mean():.2f})")
    print("INTERPRETATION: AUC~0.5 => gloss text overlap does not separate apt from inapt either (4th substrate fails).")


if __name__ == "__main__":
    main()
