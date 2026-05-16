"""M02-S04 — Patch the DB with the re-enriched emotion-cohort JSON and
re-run the downstream pipeline.

Workflow:
  1. Read the new enrichment JSON.
  2. DELETE existing rows for the 51 synset_ids from
       * synset_properties
       * enrichment
       * lemma_metadata (if present)
     The downstream tables (synset_properties_curated, vocab,
     clusters, antonyms) get fully rebuilt by the pipeline so we
     don't have to touch them.
  3. Call enrich_pipeline.run_pipeline(db, [new_json], fasttext) —
     does curate, populate, build_vocab, cluster_vocab, snap (at the
     default 0.7 threshold), antonyms.
  4. Print before/after row counts for verification.

After this completes, the next step is `run_sweep.py --config
m02_ortony_v3.yaml` to measure whether the renamed prompt's
enrichment moves the apt-cohort separation_score out of the noise
band.

Safe to interrupt before step 3 (no DB writes have been committed).
Step 3 is atomic per-file — the pipeline either succeeds or leaves
the DB partly updated. We have lexicon_v2.db.pre-resnap-0.48-backup
plus lexicon_v2.db.pre-m02-rebase-backup as fallbacks.
"""
import json
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from enrich_pipeline import run_pipeline
from utils import LEXICON_V2, FASTTEXT_VEC

REPO_ROOT = Path(__file__).resolve().parents[2]
NEW_JSON = REPO_ROOT / "data-pipeline" / "output" / "enrichment_emotion-sm_sonnet_v2_20260515.json"
DB_PATH = str(LEXICON_V2)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not NEW_JSON.is_file():
        raise FileNotFoundError(
            f"Enrichment JSON not found: {NEW_JSON}. Run "
            f"m02_s04_reenrich_emotion_cohort.py first."
        )

    with open(NEW_JSON) as f:
        payload = json.load(f)
    synset_ids = [s["id"] for s in payload.get("synsets", [])]
    print(f"Patching {len(synset_ids)} synsets from {NEW_JSON.name}")

    # --- Step 1: confirm with before-counts ---
    conn = sqlite3.connect(DB_PATH)
    try:
        placeholders = ",".join("?" for _ in synset_ids)
        before_sp = conn.execute(
            f"SELECT COUNT(*) FROM synset_properties WHERE synset_id IN ({placeholders})",
            synset_ids,
        ).fetchone()[0]
        before_enrichment = conn.execute(
            f"SELECT COUNT(*) FROM enrichment WHERE synset_id IN ({placeholders})",
            synset_ids,
        ).fetchone()[0]
        # lemma_metadata table may or may not exist
        has_lm = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='lemma_metadata'"
        ).fetchone()[0] > 0
        before_lm = 0
        if has_lm:
            before_lm = conn.execute(
                f"SELECT COUNT(*) FROM lemma_metadata WHERE synset_id IN ({placeholders})",
                synset_ids,
            ).fetchone()[0]
        print(f"Before: synset_properties={before_sp}, "
              f"enrichment={before_enrichment}, lemma_metadata={before_lm}")
    finally:
        conn.close()

    # --- Step 2: delete the 51 synsets' rows from the LLM-property tables ---
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("BEGIN")
        conn.execute(
            f"DELETE FROM synset_properties WHERE synset_id IN ({placeholders})",
            synset_ids,
        )
        conn.execute(
            f"DELETE FROM enrichment WHERE synset_id IN ({placeholders})",
            synset_ids,
        )
        if has_lm:
            conn.execute(
                f"DELETE FROM lemma_metadata WHERE synset_id IN ({placeholders})",
                synset_ids,
            )
        # synset_properties_curated will be wiped + rebuilt by the
        # pipeline's snap step, so no need to clear it here.
        conn.execute("COMMIT")
        print(f"Deleted old rows for {len(synset_ids)} synsets.")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    # --- Step 3: run the downstream pipeline on the new JSON ---
    print(f"\nCalling run_pipeline(db={DB_PATH}, enrichment=[new_json], "
          f"fasttext={FASTTEXT_VEC})")
    stats = run_pipeline(DB_PATH, [str(NEW_JSON)], str(FASTTEXT_VEC))
    print(f"\nPipeline stats: {stats}")

    # --- Step 4: confirm with after-counts ---
    conn = sqlite3.connect(DB_PATH)
    try:
        after_sp = conn.execute(
            f"SELECT COUNT(*) FROM synset_properties WHERE synset_id IN ({placeholders})",
            synset_ids,
        ).fetchone()[0]
        after_enrichment = conn.execute(
            f"SELECT COUNT(*) FROM enrichment WHERE synset_id IN ({placeholders})",
            synset_ids,
        ).fetchone()[0]
        after_spc = conn.execute(
            f"SELECT COUNT(*) FROM synset_properties_curated WHERE synset_id IN ({placeholders})",
            synset_ids,
        ).fetchone()[0]
        print(f"\nAfter: synset_properties={after_sp}, "
              f"enrichment={after_enrichment}, "
              f"synset_properties_curated={after_spc}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
