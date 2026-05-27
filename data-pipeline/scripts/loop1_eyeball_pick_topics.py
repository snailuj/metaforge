#!/usr/bin/env python3
"""Pick 20 out-of-cohort property-enriched topics for loop-1 eyeball test.

Stratified by POS to test the noun-POS-preference change made in iter 2:
- 10 nominal (n)
- 4 verb (v)
- 4 adjective (a + s satellite)
- 2 adverb (r)

Frequency filter: the topic's queryable lemma must rank in the top 10000
by Zipf frequency. The earlier unrestricted picker biased toward rare
lemmas (median ~50k by rank), which let the cascade win by surfacing
near-synonyms rather than cross-domain metaphors. Restricting to common
lemmas forces the test onto topics where sense divergence is the harder
problem.

Exclusion set: Phase 2 spike + Lakoff + MUNCH cohort words. Any synset
whose chosen lemma matches an excluded word (case-insensitive,
lemma-stripped) is dropped, regardless of POS.

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

SEED = 20260527
PER_POS_TARGETS = {"n": 10, "v": 4, "a_or_s": 4, "r": 2}
FREQ_RANK_CAP = 10_000  # top-N lemmas by Zipf frequency


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

    # Step 1: top-N lemmas by Zipf. lemma → zipf, lowercased.
    cur.execute(
        "SELECT lemma, zipf FROM frequencies "
        "WHERE zipf IS NOT NULL ORDER BY zipf DESC LIMIT ?",
        (FREQ_RANK_CAP,),
    )
    top_zipf: dict[str, float] = {}
    for lemma, zipf in cur.fetchall():
        top_zipf[lemma.lower()] = zipf

    # Step 2: all enriched (synset_id, pos, definition, lemma) rows.
    # Index lookups make this cheap; Python does the top-N filter and the
    # "pick highest-zipf lemma per synset" step, which is faster than
    # forcing SQLite to evaluate LOWER() on the join column.
    cur.execute(
        """
        SELECT s.synset_id, s.pos, s.definition, l.lemma
        FROM synsets s
        JOIN synset_properties sp ON sp.synset_id = s.synset_id
        JOIN synset_concreteness sc ON sc.synset_id = s.synset_id
        JOIN lemmas l ON l.synset_id = s.synset_id
        WHERE LENGTH(l.lemma) > 0
        """
    )
    raw = cur.fetchall()
    conn.close()

    # Per synset: pick the lemma with highest Zipf that's in the top-N set.
    # If no lemma is in the top-N set, drop the synset entirely.
    best: dict[str, tuple[str, str, str, str, float]] = {}
    for synset_id, pos, gloss, lemma in raw:
        zipf = top_zipf.get(lemma.lower())
        if zipf is None:
            continue
        cur_row = best.get(synset_id)
        if cur_row is None or zipf > cur_row[4]:
            best[synset_id] = (synset_id, pos, gloss, lemma, zipf)

    rows = list(best.values())
    print(f"  {len(rows)} synsets with at least one top-{FREQ_RANK_CAP} lemma",
          file=sys.stderr)

    # Bucket by POS group; collapse a + s (adjective + satellite).
    buckets: dict[str, list[tuple[str, str, str, str, float]]] = {
        "n": [],
        "v": [],
        "a_or_s": [],
        "r": [],
    }
    for synset_id, pos, gloss, lemma, zipf in rows:
        if lemma.lower() in excluded:
            continue
        key = "a_or_s" if pos in ("a", "s") else pos
        if key in buckets:
            buckets[key].append((synset_id, pos, gloss, lemma, zipf))

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
        for synset_id, pos, gloss, lemma, zipf in sample:
            picked.append({
                "synset_id": synset_id,
                "pos": pos,
                "lemma": lemma,
                "gloss": gloss,
                "zipf": zipf,
            })

    out = {
        "seed": SEED,
        "n_picked": len(picked),
        "exclusion_set_size": len(excluded),
        "per_pos_targets": PER_POS_TARGETS,
        "freq_rank_cap": FREQ_RANK_CAP,
        "topics": picked,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"Wrote {len(picked)} topics to {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
