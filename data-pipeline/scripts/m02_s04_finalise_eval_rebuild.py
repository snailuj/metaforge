"""M02-S04 — Finalise the eval rebuild.

After both Haiku+SM enrichment runs completed (broad top-20k partial,
plus cohort priority), this script:

  1. Clear-and-imports each remaining JSON into the DB (DELETE old
     rows for the affected synsets, INSERT the Haiku+SM data).
  2. Runs the heavy post-import pipeline ONCE: lemma_embeddings →
     build_vocab → cluster_vocab → snap_properties → antonyms.

Done in a single Python process so FastText vectors load once (~17
min) and are reused across both phases. Doing the two phases as
separate processes would cost ~34 min in FastText loads alone.

Output of step 2 is what M02 sweep actually depends on:
  * `synset_properties_curated` — the snapped cohort
  * `vocab_clusters` — for ortony scoring fns
  * `property_antonyms` — for the ironic/complex tier (forge runtime)

Skips the broad JSON for clear-and-import because that was already
done in the earlier `m02_s04_clear_and_import.py` pass. (No-op
INSERT OR IGNORE would happen if we re-included it but waste cycles.)
"""
import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from enrich_pipeline import (
    curate_properties,
    populate_synset_properties,
    populate_lemma_metadata,
    store_lemma_embeddings,
    _ensure_v2_schema,
)
from build_vocab import build_and_store
from cluster_vocab import cluster_vocab
from snap_properties import snap_properties
from build_antonyms import build_antonym_table, build_cluster_antonym_table
from utils import LEXICON_V2, FASTTEXT_VEC, load_fasttext_vectors

from m02_s04_clear_and_import import _delete_synset_rows_within_txn


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(LEXICON_V2))
    parser.add_argument("--cohort-enrichment", required=True,
                        help="Cohort JSON to clear+import before rebuild")
    parser.add_argument("--fasttext", default=str(FASTTEXT_VEC))
    args = parser.parse_args()

    # Pre-flight validate
    with open(args.cohort_enrichment) as f:
        cohort_data = json.load(f)
    cohort_synset_ids = [s["id"] for s in cohort_data.get("synsets", [])]
    cohort_model = cohort_data.get("config", {}).get("model", "unknown")
    print(f"Cohort: {len(cohort_synset_ids)} synsets, model={cohort_model}")

    print(f"\nLoading FastText vectors from {args.fasttext} (~17 min)...")
    vectors = load_fasttext_vectors(args.fasttext)

    conn = sqlite3.connect(args.db)
    try:
        _ensure_v2_schema(conn)

        # --- Phase 1: clear + import cohort JSON ---
        # Wrap clear-and-import in a single explicit transaction so a
        # partial failure cannot leave the DB with rows DELETED but no
        # replacement IMPORTED. Mirrors the canonical pattern in
        # `m02_s04_clear_and_import.py`. Required by
        # `_delete_synset_rows_within_txn` (precondition assert).
        print(f"\n=== Phase 1: clear-and-import cohort ({len(cohort_synset_ids)} synsets) ===")
        conn.execute("BEGIN")
        try:
            _delete_synset_rows_within_txn(conn, cohort_synset_ids)
            n_curated = curate_properties(conn, cohort_data, vectors)
            n_links = populate_synset_properties(conn, cohort_data, cohort_model)
            n_lm = populate_lemma_metadata(conn, cohort_data)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        print(f"  Imported: {n_curated} new property_vocabulary rows, "
              f"{n_links} synset-property links, {n_lm} lemma_metadata rows")

        # --- Phase 2: lemma embeddings (full sweep, idempotent INSERT OR IGNORE) ---
        print("\n=== Phase 2: lemma embeddings ===")
        n_lemma_emb = store_lemma_embeddings(conn, vectors)
        print(f"  Stored {n_lemma_emb} lemma embeddings")

        # --- Phase 3: curated vocab + clustering ---
        print("\n=== Phase 3: build curated vocab + cluster ===")
        vocab_entries = build_and_store(conn)
        print(f"  Stored {vocab_entries} vocabulary entries")
        cluster_stats = cluster_vocab(conn)
        print(f"  Clustered into {cluster_stats.get('num_clusters', 0)} "
              f"clusters ({cluster_stats.get('singletons', 0)} singletons)")

        # --- Phase 4: snap properties (default threshold 0.7) ---
        print("\n=== Phase 4: snap properties (threshold 0.7) ===")
        snap_stats = snap_properties(conn)
        print(f"  Snap result: {snap_stats}")

        # --- Phase 5: antonym tables ---
        print("\n=== Phase 5: antonym tables ===")
        antonym_pairs = build_antonym_table(conn)
        cluster_antonym_pairs = build_cluster_antonym_table(conn)
        print(f"  Built {antonym_pairs} antonym pairs, "
              f"{cluster_antonym_pairs} cluster antonym pairs")

        print("\n=== Eval rebuild complete ===")
        print("Next step: data-pipeline/.venv/bin/python "
              "data-pipeline/scripts/run_sweep.py --config "
              "data-pipeline/sweeps/m02_ortony_v3.yaml --output ... --report ...")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
