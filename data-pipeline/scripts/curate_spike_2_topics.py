"""Curate the Phase 2 anchor-topic set (~200 topics).

The cohort is composed of:

- Phase 1b's 20 hand-curated anchor topics (Lakoff classics + concrete
  metaphor-rich + compound/rare + emotion/state). These provide a
  trusted spine and let us compare Phase 2 results against Phase 1b
  on the same words.
- ~180 programmatically sampled noun synsets drawn from the lexicon
  by frequency × concreteness tier. We stratify across three
  concreteness bands (abstract / mid / concrete) and pull from the
  common+unusual rarity tiers so the cohort spans a real range of
  metaphor-eligible anchors rather than collapsing to high-frequency
  abstractions.

Gloss strategy: take WordNet's `synsets.definition`, truncate at the
first semicolon or to ≤14 words. Phase 2's Haiku prompt only needs a
tight disambiguating clause; full Claude-summarised glosses are a
later (separate) artefact.

Topic constraints (avoid breakage downstream):

- Single-word lemma only (the property snap path doesn't handle
  multi-word phrases; concept resolution would fail).
- Lower-cased ASCII letters only — strips out proper nouns, hyphenated
  compounds, and unicode rarities.
- Lemma must resolve to a primary synset via lookup_primary_synset
  (otherwise scoring would always return unresolved).
- Skip lemmas already in the Phase 1b spine to avoid duplicates.
- Skip the 3 gold-example topics (love, knowledge, fear) — they're in
  Haiku's few-shot context, so including them in the test cohort
  would inflate quality artificially.

Usage::

    python data-pipeline/scripts/curate_spike_2_topics.py \\
        --db data-pipeline/output/lexicon_v2.db \\
        --output data-pipeline/scripts/spike_2_topics.json \\
        --target-sample 180

The output is committed to git so Phase 2 is reproducible without
re-querying the DB.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate_aptness import lookup_primary_synset
from metaphor_spike_1b import TOPICS as PHASE_1B_TOPICS

log = logging.getLogger(__name__)


GOLD_EXAMPLE_WORDS = {"love", "knowledge", "fear"}

# Concreteness bands (Brysbaert scale roughly 1-5). Cover the spread so
# the cohort isn't dominated by either extreme.
_BANDS: list[tuple[str, float, float, int]] = [
    ("abstract", 1.0, 2.6, 60),
    ("mid",      2.6, 3.8, 60),
    ("concrete", 3.8, 5.0, 60),
]

# Random seed for reproducibility — same DB + same seed → same cohort.
_RANDOM_SEED = 20260525


_SAFE_LEMMA_RE = re.compile(r"^[a-z]+$")


def _truncate_gloss(definition: str, max_words: int = 14) -> str:
    """Cut a WordNet definition down to a tight one-clause gloss.

    Strategy: take everything up to the first semicolon (WordNet
    convention for sense separators), then cap at max_words words.
    """
    first_clause = definition.split(";", 1)[0].strip()
    words = first_clause.split()
    if len(words) <= max_words:
        return first_clause
    return " ".join(words[:max_words])


def _sample_band(
    conn: sqlite3.Connection,
    band_name: str,
    c_lo: float,
    c_hi: float,
    target: int,
    exclude: set[str],
    rng: random.Random,
) -> list[dict[str, str]]:
    """Sample up to `target` noun-synset topics from one concreteness band.

    Query oversamples by 3x then filters in Python so we have enough
    candidates after eliminating multi-word, proper-noun, and
    unresolvable lemmas.
    """
    over = target * 4
    rows = conn.execute(
        """
        SELECT s.synset_id, s.definition, l.lemma, sc.score, f.zipf
        FROM synsets s
        JOIN synset_concreteness sc ON sc.synset_id = s.synset_id
        JOIN lemmas l ON l.synset_id = s.synset_id
        JOIN frequencies f ON f.lemma = l.lemma
        WHERE s.pos = 'n'
          AND sc.score >= ?
          AND sc.score <  ?
          AND f.rarity IN ('common', 'unusual')
          AND f.zipf IS NOT NULL
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (c_lo, c_hi, over * 5),
    ).fetchall()

    picked: list[dict[str, str]] = []
    seen: set[str] = set()
    for synset_id, definition, lemma, conc, zipf in rows:
        if len(picked) >= target:
            break
        lemma_l = lemma.lower()
        if lemma_l in exclude or lemma_l in seen:
            continue
        if not _SAFE_LEMMA_RE.match(lemma_l):
            continue
        # Lemma must resolve via the primary-synset path Phase 2 will
        # use at scoring time — otherwise the topic is dead on arrival.
        sid_resolved = lookup_primary_synset(conn, lemma_l)
        if sid_resolved is None:
            continue
        gloss = _truncate_gloss(definition or "")
        if not gloss:
            continue
        picked.append({
            "word": lemma_l,
            "gloss": gloss,
            "synset_id": synset_id,
            "concreteness": round(conc, 3),
            "zipf": round(zipf, 3),
            "band": band_name,
        })
        seen.add(lemma_l)

    # rng kept for future deterministic shuffling — RANDOM() in SQL is
    # already shuffled, so we don't need to re-shuffle here.
    _ = rng
    return picked


def curate(db: Path, output: Path, target_sample: int) -> None:
    """Write the Phase 2 topic list to disk."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")

    rng = random.Random(_RANDOM_SEED)

    # Re-balance per-band targets to honour the caller-specified total.
    band_targets = []
    base = target_sample // len(_BANDS)
    remainder = target_sample - base * len(_BANDS)
    for i, (name, lo, hi, _) in enumerate(_BANDS):
        t = base + (1 if i < remainder else 0)
        band_targets.append((name, lo, hi, t))

    seed_words = {t["word"] for t in PHASE_1B_TOPICS} | GOLD_EXAMPLE_WORDS

    sampled: list[dict] = []
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        for name, lo, hi, t in band_targets:
            band = _sample_band(conn, name, lo, hi, t, seed_words | {s["word"] for s in sampled}, rng)
            log.info("band=%s target=%d picked=%d", name, t, len(band))
            sampled.extend(band)

    # Compose the final cohort: hand-curated Phase 1b spine first,
    # sampled tail after. Tag each entry with its source so Phase 2
    # reports can break out spine vs sample if needed.
    cohort: list[dict] = []
    for t in PHASE_1B_TOPICS:
        cohort.append({
            "word": t["word"],
            "gloss": t["gloss"],
            "source": "phase_1b_spine",
        })
    for s in sampled:
        cohort.append({
            "word": s["word"],
            "gloss": s["gloss"],
            "synset_id": s["synset_id"],
            "concreteness": s["concreteness"],
            "zipf": s["zipf"],
            "band": s["band"],
            "source": "sampled",
        })

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "2",
        "n_total": len(cohort),
        "n_spine": len(PHASE_1B_TOPICS),
        "n_sampled": len(sampled),
        "random_seed": _RANDOM_SEED,
        "topics": cohort,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("wrote %s — %d topics (%d spine + %d sampled)",
             output, len(cohort), len(PHASE_1B_TOPICS), len(sampled))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--db", type=Path,
        default=Path(__file__).resolve().parent.parent / "output" / "lexicon_v2.db",
    )
    ap.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parent / "spike_2_topics.json",
    )
    ap.add_argument(
        "--target-sample", type=int, default=180,
        help="Number of topics to sample from the DB on top of the 20-topic spine.",
    )
    args = ap.parse_args(argv)
    curate(args.db, args.output, args.target_sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
