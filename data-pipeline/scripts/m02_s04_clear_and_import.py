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

log = logging.getLogger(__name__)


def _delete_synset_rows_within_txn(conn, synset_ids):
    """Wipe the LLM-data rows for the given synset_ids.

    Touches synset_properties, enrichment, lemma_metadata only.
    Downstream curated/vocab/cluster/antonym tables get fully rebuilt
    by a later run_pipeline pass and don't need surgical handling.

    The leading underscore + `_within_txn` suffix mark this as a
    transaction-internal helper: it issues unflushed DELETEs and relies
    on the caller's `BEGIN ... COMMIT` boundary to persist or roll them
    back atomically with subsequent import work. The precondition raise
    below surfaces a contract violation immediately rather than letting
    the DELETEs leak at the next auto-commit boundary. We use a real
    `raise RuntimeError` (not `assert`) so the guard survives
    `python -O` / `PYTHONOPTIMIZE=1`, which strips assertions.
    """
    if not conn.in_transaction:
        raise RuntimeError(
            "_delete_synset_rows_within_txn must be called inside an "
            "explicit transaction (caller forgot conn.execute('BEGIN'); "
            "without BEGIN the DELETEs run in autocommit and leak)"
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


def import_one_payload_safely(conn, path, data, vectors):
    """Clear-and-import a single enrichment payload inside its own txn.

    Public helper — also consumed by `m02_s04_finalise_eval_rebuild.py`
    Phase 1 so the silent-leak-aware pattern lives in one place. Both
    scripts share the same `BEGIN → _delete → curate → populate →
    COMMIT` flow with identical partial-atomicity hazards; the helper
    is the single source of truth.

    Contract:
      - Caller must have already invoked `_ensure_v2_schema(conn)`.
      - `data` is a parsed enrichment-JSON dict with `synsets` and
        `config.model` keys (model defaults to "unknown" if missing).
      - `vectors` is the loaded FastText mapping.

    Failure modes the helper surfaces (via `log.warning`):
      - PARTIAL-IMPORT state when an inner commit fires and a later
        step raises (`curate_properties` commits internally; if a
        subsequent populate raises, DELETEs and curate writes are
        already persisted).
      - Rollback-of-rollback failures (e.g. `database is locked`)
        without masking the original exception.
    """
    synset_ids = [s["id"] for s in data.get("synsets", [])]
    model_used = data.get("config", {}).get("model", "unknown")
    print(f"\n--- {path} ({len(synset_ids)} synsets, "
          f"model={model_used}) ---")
    conn.execute("BEGIN")
    # Track partial-atomicity explicitly rather than relying on
    # `conn.in_transaction`. sqlite3.Connection auto-opens an implicit
    # transaction on the first DML after a commit, so once any inner
    # helper has committed, in_transaction toggles back to True on the
    # next INSERT — making it an unreliable signal for "has an inner
    # commit already happened?". This flag is the honest answer.
    inner_commit_seen = False
    try:
        _delete_synset_rows_within_txn(conn, synset_ids)
        print("  Re-curating + populating...")
        try:
            curate_properties(conn, data, vectors)
        finally:
            # Pessimistic: curate_properties commits internally at
            # enrich_pipeline.py:172 BEFORE its print()+return tail. If
            # anything raises between that commit and our resumption —
            # print() raising BrokenPipeError on a closed stdout pipe,
            # OSError on ENOSPC, or future maintainer code added
            # between the commit and the return — we MUST treat the
            # inner commit as having fired. False positive (WARNING
            # fires when curate raised BEFORE its commit) is operator
            # confusion; false negative (silent leak when curate raised
            # AFTER its commit) is data corruption. Bias toward false
            # positive. populate_synset_properties and
            # populate_lemma_metadata also commit internally, so this
            # flag is correct for the whole post-curate window.
            inner_commit_seen = True
        populate_synset_properties(conn, data, model_used)
        populate_lemma_metadata(conn, data)
        # If the populate_* helpers' internal commits already
        # closed the txn, this commit is a no-op; if they did
        # not (e.g. a future refactor hoists their commits
        # out), this preserves atomicity for the payload.
        if conn.in_transaction:
            conn.commit()
    except Exception as original_exc:
        # Re-raise with original traceback intact (bare `raise`
        # inside the except block; never `raise e` — that would
        # lose context). Each rollback below is wrapped in its own
        # try/except so a failing rollback (e.g.
        # `sqlite3.OperationalError: database is locked`) cannot
        # replace the original failure via `__context__` chaining —
        # the original is what the operator needs to see.
        #
        # We bind the outer exception as `original_exc` so the
        # rollback-failure WARNINGs below can name it inline. The
        # propagating traceback carries it via `__context__`, but an
        # operator reading the WARNING line alone (no traceback) cannot
        # tell what triggered the rollback attempt otherwise.
        if inner_commit_seen:
            # An inner commit has already fired — DELETEs and curate's
            # writes are persisted; populate_* may also be partially
            # persisted. Surface the silent-leak state to the operator.
            # Then still attempt rollback of any implicit-txn DML that
            # sqlite3 auto-opened after the inner commit (e.g. a
            # partial INSERT from populate_synset_properties) so the
            # connection is left clean for subsequent payloads.
            log.warning(
                "Possible PARTIAL-IMPORT state for payload %s — "
                "curate_properties may have committed before the failure "
                "point (try/finally pessimistically assumes it did). If "
                "curate's commit DID fire, DELETEs and curated vocab "
                "writes are persisted and rollback below only undoes "
                "post-curate partial DML. If curate raised BEFORE its "
                "commit, the outer BEGIN's rollback restored a clean "
                "state and this WARNING is a benign false positive. "
                "Operator should verify with SELECT against the affected "
                "synsets before restoring from snapshot. See module "
                "docstring for partial-atomicity caveat.",
                path,
            )
            if conn.in_transaction:
                try:
                    conn.rollback()
                except sqlite3.Error as rb_err:
                    # Log but DO NOT re-raise — the outer bare `raise`
                    # must propagate the original failure. The
                    # connection may now be in an inconsistent state;
                    # operator should restart from snapshot.
                    log.warning(
                        "Rollback of post-inner-commit partial DML "
                        "failed for payload %s: %s: %s. Original "
                        "failure that triggered rollback: %s: %s. "
                        "Connection may be in an inconsistent state — "
                        "operator should restart from snapshot.",
                        path,
                        type(rb_err).__name__, rb_err,
                        type(original_exc).__name__, original_exc,
                    )
        else:
            # No inner commit yet — the outer BEGIN's rollback undoes
            # everything (DELETEs from `_delete_synset_rows_within_txn`
            # and anything else issued under the BEGIN).
            if conn.in_transaction:
                try:
                    conn.rollback()
                except sqlite3.Error as rb_err:
                    # Same protection as above: a failing rollback
                    # must not mask the original exception.
                    log.warning(
                        "Rollback of pre-inner-commit DML failed for "
                        "payload %s: %s: %s. Original failure that "
                        "triggered rollback: %s: %s. Outer BEGIN may "
                        "have left uncommitted DELETEs visible to "
                        "subsequent operations on this connection.",
                        path,
                        type(rb_err).__name__, rb_err,
                        type(original_exc).__name__, original_exc,
                    )
        raise


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
        # 1 and trip the precondition raise in
        # `_delete_synset_rows_within_txn` on iteration 2. See module
        # docstring for the full transactional-safety rationale.
        for path, data in payloads:
            import_one_payload_safely(conn, path, data, vectors)

        print("\nImport complete. Downstream tables "
              "(synset_properties_curated, vocab_clusters, "
              "property_antonyms) are STALE — run "
              "`enrich_pipeline.run_pipeline` to rebuild.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
