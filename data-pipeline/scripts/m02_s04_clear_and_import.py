"""M02-S04 — DELETE-then-IMPORT one or more enrichment JSONs.

The `enrich_pipeline.populate_*` functions use INSERT OR IGNORE so a
synset that already has rows in synset_properties keeps them. For a
clean Haiku+SM rebuild we want the new data to *replace* the old
(Sonnet+physical) data on the affected synsets — so we DELETE the
old rows for each synset in the JSON before importing.

Downstream tables (synset_properties_curated, vocab, clusters,
antonyms) are NOT touched here — they will be rebuilt by a full
pipeline pass after all imports are done. Avoids running snap twice.

Transactional safety
--------------------
Each payload's clear-and-import runs inside its own explicit
transaction (`BEGIN ... COMMIT`) with `ROLLBACK` on any exception, so a
partial failure cannot leave a given synset with rows DELETED but no
replacement IMPORTED. The per-payload boundary is the honest model
here: `enrich_pipeline.curate_properties / populate_synset_properties /
populate_lemma_metadata` each issue their own `conn.commit()` at the
end of their run, so wrapping the whole multi-payload loop in a single
outer transaction was a fiction — the outer txn would collapse on
iteration 1 and `_delete_synset_rows_within_txn`'s precondition would
fire on iteration 2.

With per-payload BEGIN/COMMIT we still guarantee that *if a populate_*
step raises before its internal commit, the DELETEs (and any work
since the last internal commit) roll back* — the dominant failure
mode (LLM-shape mismatch, schema drift, OOM during embedding lookups).
For true end-to-end atomicity within a single payload, the inner
functions would need their commits hoisted out — a refactor beyond
this script's scope.

Cross-payload atomicity is intentionally not provided: later payloads
in a multi-payload run are independent clear-and-import operations
applied in order. If payload N fails, payloads 0..N-1 remain committed
and the operator re-runs from payload N.

This script does NOT snapshot the database. Operators running it against
production data should snapshot first; the sibling
`m02_s04_patch_and_repipeline.py` shows the backup-file pattern.

Usage (one JSON):
  data-pipeline/.venv/bin/python data-pipeline/scripts/m02_s04_clear_and_import.py \\
    --enrichment data-pipeline/output/enrichment_top20k_haiku-sm_v2_20260515.json

Usage (multiple, processed in order — later JSONs win on overlap):
  data-pipeline/.venv/bin/python data-pipeline/scripts/m02_s04_clear_and_import.py \\
    --enrichment broad.json cohort.json
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
    _ensure_v2_schema,
)
from utils import LEXICON_V2, FASTTEXT_VEC, load_fasttext_vectors


def _delete_synset_rows_within_txn(conn, synset_ids):
    """Wipe the LLM-data rows for the given synset_ids.

    Touches synset_properties, enrichment, lemma_metadata only.
    Downstream curated/vocab/cluster/antonym tables get fully rebuilt
    by a later run_pipeline pass and don't need surgical handling.

    The leading underscore + `_within_txn` suffix mark this as a
    transaction-internal helper: it issues unflushed DELETEs and relies
    on the caller's `BEGIN ... COMMIT` boundary to persist or roll them
    back atomically with subsequent import work. The precondition assert
    below surfaces a contract violation immediately rather than letting
    the DELETEs leak at the next auto-commit boundary.
    """
    assert conn.in_transaction, (
        "_delete_synset_rows_within_txn must be called inside an explicit "
        "transaction (BEGIN ... COMMIT) — the caller owns the txn boundary."
    )
    if not synset_ids:
        return
    ph = ",".join("?" for _ in synset_ids)
    n_sp = conn.execute(
        f"DELETE FROM synset_properties WHERE synset_id IN ({ph})",
        synset_ids,
    ).rowcount
    n_e = conn.execute(
        f"DELETE FROM enrichment WHERE synset_id IN ({ph})",
        synset_ids,
    ).rowcount
    # lemma_metadata may not exist on older schemas
    has_lm = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='lemma_metadata'"
    ).fetchone()[0] > 0
    n_lm = 0
    if has_lm:
        n_lm = conn.execute(
            f"DELETE FROM lemma_metadata WHERE synset_id IN ({ph})",
            synset_ids,
        ).rowcount
    print(f"  Deleted: {n_sp} synset_properties, {n_e} enrichment, "
          f"{n_lm} lemma_metadata rows for {len(synset_ids)} synsets.")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(LEXICON_V2))
    parser.add_argument("--enrichment", required=True, nargs="+",
                        help="One or more enrichment JSON files")
    parser.add_argument("--fasttext", default=str(FASTTEXT_VEC))
    args = parser.parse_args()

    # Pre-flight: validate every JSON before touching anything.
    payloads = []
    for path in args.enrichment:
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            raise ValueError(f"Invalid enrichment file {path}: {e}") from e
        payloads.append((path, data))

    print(f"Loading FastText vectors from {args.fasttext} (~17 min)...")
    vectors = load_fasttext_vectors(args.fasttext)

    conn = sqlite3.connect(args.db)
    try:
        _ensure_v2_schema(conn)
        # Per-payload BEGIN/COMMIT. The inner enrich_pipeline.populate_*
        # helpers each commit internally, so a single outer transaction
        # cannot span multiple payloads — it would collapse on iteration
        # 1 and trip the precondition assert in
        # `_delete_synset_rows_within_txn` on iteration 2. See module
        # docstring for the full transactional-safety rationale.
        for path, data in payloads:
            synset_ids = [s["id"] for s in data.get("synsets", [])]
            model_used = data.get("config", {}).get("model", "unknown")
            print(f"\n--- {path} ({len(synset_ids)} synsets, "
                  f"model={model_used}) ---")
            conn.execute("BEGIN")
            try:
                _delete_synset_rows_within_txn(conn, synset_ids)
                print("  Re-curating + populating...")
                curate_properties(conn, data, vectors)
                populate_synset_properties(conn, data, model_used)
                populate_lemma_metadata(conn, data)
                # If the populate_* helpers' internal commits already
                # closed the txn, this commit is a no-op; if they did
                # not (e.g. a future refactor hoists their commits
                # out), this preserves atomicity for the payload.
                if conn.in_transaction:
                    conn.commit()
            except Exception:
                # Re-raise with original traceback intact (bare `raise`
                # inside the except block; never `raise e` — that would
                # lose context). Only roll back if we still hold the
                # txn; if an inner commit already landed, there is
                # nothing to roll back and calling rollback() would
                # raise OperationalError, masking the original error.
                if conn.in_transaction:
                    conn.rollback()
                raise

        print("\nImport complete. Downstream tables "
              "(synset_properties_curated, vocab_clusters, "
              "property_antonyms) are STALE — run "
              "`enrich_pipeline.run_pipeline` to rebuild.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
