"""M02-S04 — Import enrichment JSON(s) into DB WITHOUT running snap.

Why this exists: the full `enrich_pipeline.run_pipeline` does
  curate_properties → populate_synset_properties → populate_lemma_metadata
  → store_lemma_embeddings → build_and_store (vocab) → cluster_vocab
  → snap_properties → build_antonym_table

The first four steps are cheap "JSON → DB tables" import.
The last four are heavy: vocab+cluster takes ~30 min, snap takes ~20
min on the current DB. We want to defer those until AFTER all
enrichment runs (broad + cohort) have landed — running the heavy
pipeline once at the end is much faster than once per import.

This script does the first four (the LLM-data import) and stops.
After all JSONs are loaded, run `enrich_pipeline.run_pipeline` on
the full list — but because populate_* uses INSERT OR IGNORE, the
already-imported rows are idempotently skipped on the second pass.

FastText is still needed (curate_properties embeds new property
texts) — that's the ~17-min vocab load. No way around it for new
texts that aren't yet in property_vocabulary.

Usage:
  data-pipeline/.venv/bin/python data-pipeline/scripts/m02_s04_import_only.py \\
      --enrichment data-pipeline/output/enrichment_top20k_haiku-sm_v2_20260515.json
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
from utils import LEXICON_V2, FASTTEXT_VEC, load_fasttext_vectors


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(LEXICON_V2),
                        help="Path to lexicon DB")
    parser.add_argument("--enrichment", required=True, nargs="+",
                        help="One or more enrichment JSON files")
    parser.add_argument("--fasttext", default=str(FASTTEXT_VEC),
                        help="FastText .vec path")
    parser.add_argument("--skip-lemma-embeddings", action="store_true",
                        help="Skip the per-lemma embedding store step "
                             "(saves a few minutes; safe if lemma_embeddings "
                             "is already populated and unchanged)")
    args = parser.parse_args()

    # Pre-flight validate JSONs before touching the DB or FastText.
    for path in args.enrichment:
        try:
            with open(path) as f:
                json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            raise ValueError(f"Invalid enrichment file {path}: {e}") from e

    print(f"Loading FastText vectors from {args.fasttext} (~17 min)...")
    vectors = load_fasttext_vectors(args.fasttext)

    print(f"\nImporting {len(args.enrichment)} JSON(s) into {args.db}:")
    for path in args.enrichment:
        print(f"  {path}")

    conn = sqlite3.connect(args.db)
    try:
        _ensure_v2_schema(conn)

        for path in args.enrichment:
            print(f"\n--- Processing: {path} ---")
            with open(path) as f:
                data = json.load(f)
            model_used = data.get("config", {}).get("model", "unknown")
            n_props = curate_properties(conn, data, vectors)
            n_links = populate_synset_properties(conn, data, model_used)
            n_lm = populate_lemma_metadata(conn, data)
            print(f"  Imported: {n_props} new property_vocabulary rows, "
                  f"{n_links} synset-property links, {n_lm} lemma_metadata rows")

        if not args.skip_lemma_embeddings:
            print("\nStoring lemma embeddings (covers all lemmas, "
                  "not just the imported ones)...")
            n_lemma_emb = store_lemma_embeddings(conn, vectors)
            print(f"  Stored {n_lemma_emb} lemma embeddings")
        else:
            print("\nSkipping lemma embeddings store (--skip-lemma-embeddings)")

        # Important: NOT running build_vocab, cluster_vocab, snap_properties,
        # or antonyms. Those happen later via run_pipeline once all enrichment
        # runs are complete.
        print("\nImport-only complete. DB tables `synset_properties`, "
              "`enrichment`, `property_vocabulary`, `lemma_metadata`"
              " populated. Downstream tables (synset_properties_curated,"
              " property_vocab_curated, vocab_clusters, etc.) are "
              "STALE and need a full `run_pipeline` to refresh.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
