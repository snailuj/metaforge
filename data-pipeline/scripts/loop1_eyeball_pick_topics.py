#!/usr/bin/env python3
"""Pick 20 out-of-cohort property-enriched topics for loop-1 eyeball test.

Stratified by POS to test the noun-POS-preference change made in iter 2:
- 10 nominal (n)
- 4 verb (v)
- 4 adjective (a + s satellite)
- 2 adverb (r)

Exclusion set: Phase 2 spike + Lakoff + MUNCH cohort words. Any synset
whose lemma matches an excluded word (case-insensitive, lemma-stripped)
is dropped, regardless of POS — so "anger" the noun and "anger" the verb
both go.

Output: data-pipeline/output/loop1_eyeball_topics.json
"""

from __future__ import annotations

import json
import random
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data-pipeline" / "output" / "lexicon_v2.db"
OUT_PATH = REPO_ROOT / "data-pipeline" / "output" / "loop1_eyeball_topics.json"

PHASE2_TOPICS = REPO_ROOT / "data-pipeline" / "scripts" / "spike_2_topics.json"
LAKOFF_APT = REPO_ROOT / "data-pipeline" / "fixtures" / "lakoff_apt.jsonl"
LAKOFF_INAPT = REPO_ROOT / "data-pipeline" / "fixtures" / "lakoff_inapt.jsonl"
MUNCH_APT = REPO_ROOT / "data-pipeline" / "fixtures" / "munch_apt.jsonl"
MUNCH_INAPT = REPO_ROOT / "data-pipeline" / "fixtures" / "munch_inapt.jsonl"

SEED = 20260525
PER_POS_TARGETS = {"n": 10, "v": 4, "a_or_s": 4, "r": 2}


def load_excluded_words() -> set[str]:
    excluded: set[str] = set()
    with PHASE2_TOPICS.open() as f:
        data = json.load(f)
    for t in data["topics"]:
        excluded.add(t["word"].lower())
    for path in (LAKOFF_APT, LAKOFF_INAPT):
        with path.open() as f:
            for line in f:
                row = json.loads(line)
                excluded.add(row["topic"].lower())
    for path in (MUNCH_APT, MUNCH_INAPT):
        with path.open() as f:
            for line in f:
                row = json.loads(line)
                excluded.add(row["target"].lower())
    return excluded


def main() -> int:
    excluded = load_excluded_words()
    print(f"Exclusion set: {len(excluded)} words", file=sys.stderr)

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Candidates: synset has properties, has concreteness, has at least one
    # short lemma (so we have a queryable word for /forge/suggest), not in
    # the exclusion set.
    cur.execute(
        """
        SELECT s.synset_id, s.pos, s.definition, MIN(l.lemma) AS lemma
        FROM synsets s
        JOIN synset_properties sp ON sp.synset_id = s.synset_id
        JOIN synset_concreteness sc ON sc.synset_id = s.synset_id
        JOIN lemmas l ON l.synset_id = s.synset_id
        WHERE LENGTH(l.lemma) > 0
        GROUP BY s.synset_id, s.pos, s.definition
        """
    )
    rows = cur.fetchall()
    conn.close()

    # Bucket by POS group; collapse a + s (adjective + satellite).
    buckets: dict[str, list[tuple[str, str, str, str]]] = {
        "n": [],
        "v": [],
        "a_or_s": [],
        "r": [],
    }
    for synset_id, pos, gloss, lemma in rows:
        if lemma.lower() in excluded:
            continue
        key = "a_or_s" if pos in ("a", "s") else pos
        if key in buckets:
            buckets[key].append((synset_id, pos, gloss, lemma))

    for key, items in buckets.items():
        print(f"  {key}: {len(items)} candidates after exclusion", file=sys.stderr)

    rng = random.Random(SEED)
    picked = []
    for key, target in PER_POS_TARGETS.items():
        bucket = buckets[key]
        if len(bucket) < target:
            print(f"WARN: {key} has only {len(bucket)} candidates (want {target})", file=sys.stderr)
            target = len(bucket)
        sample = rng.sample(bucket, target)
        for synset_id, pos, gloss, lemma in sample:
            picked.append({
                "synset_id": synset_id,
                "pos": pos,
                "lemma": lemma,
                "gloss": gloss,
            })

    out = {
        "seed": SEED,
        "n_picked": len(picked),
        "exclusion_set_size": len(excluded),
        "per_pos_targets": PER_POS_TARGETS,
        "topics": picked,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"Wrote {len(picked)} topics to {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
