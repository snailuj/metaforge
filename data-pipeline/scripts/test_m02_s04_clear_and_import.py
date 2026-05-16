"""Tests for `m02_s04_clear_and_import` — pin the transaction-boundary contract.

The `_delete_synset_rows_within_txn` helper enforces an
`if not conn.in_transaction: raise RuntimeError(...)` precondition so
that DELETEs never leak past an implicit auto-commit. A real `raise`
(rather than an `assert`) survives `python -O` / `PYTHONOPTIMIZE=1`,
which strips assertions. These tests pin the contract: calling the
helper outside a txn raises `RuntimeError`; calling it inside a txn
proceeds and actually deletes rows.
"""
import sqlite3
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import m02_s04_clear_and_import as mod
from m02_s04_clear_and_import import (
    _delete_synset_rows_within_txn,
    _import_one_payload,
)


def test_delete_synset_rows_within_txn_requires_explicit_transaction():
    """Helper must refuse to run when caller has not opened a txn.

    `sqlite3.connect(":memory:")` returns a connection in autocommit
    mode (no implicit txn), so `conn.in_transaction` is False until a
    DML statement or explicit BEGIN. Calling the helper here must raise
    `RuntimeError` immediately — before any DELETE runs. `RuntimeError`
    (rather than `AssertionError`) is chosen deliberately so the guard
    survives `python -O` / `PYTHONOPTIMIZE=1`.
    """
    conn = sqlite3.connect(":memory:")
    try:
        # Sanity check: no implicit txn open.
        assert not conn.in_transaction
        with pytest.raises(RuntimeError, match="explicit transaction"):
            _delete_synset_rows_within_txn(conn, ["synset-1"])
    finally:
        conn.close()


def test_delete_synset_rows_within_txn_accepts_explicit_transaction():
    """Helper proceeds and deletes rows when caller has issued BEGIN.

    Builds minimal `synset_properties`, `enrichment`, and
    `lemma_metadata` tables, inserts rows under three known synset_ids,
    then calls the helper inside an explicit txn targeting two of them.
    Asserts the targeted rows are gone (visible inside the txn) and
    that the third synset's rows survive. After commit, the deletions
    persist — proving the DELETE-inside-txn path actually runs end to
    end, not just that the precondition check passes.
    """
    conn = sqlite3.connect(":memory:")
    try:
        # Minimal schemas — only the columns the helper touches.
        conn.executescript(
            """
            CREATE TABLE synset_properties (synset_id TEXT, text TEXT);
            CREATE TABLE enrichment (synset_id TEXT, payload TEXT);
            CREATE TABLE lemma_metadata (synset_id TEXT, lemma TEXT);
            """
        )
        conn.executemany(
            "INSERT INTO synset_properties (synset_id, text) VALUES (?, ?)",
            [("s1", "p1"), ("s2", "p2"), ("s3", "p3")],
        )
        conn.executemany(
            "INSERT INTO enrichment (synset_id, payload) VALUES (?, ?)",
            [("s1", "e1"), ("s2", "e2"), ("s3", "e3")],
        )
        conn.executemany(
            "INSERT INTO lemma_metadata (synset_id, lemma) VALUES (?, ?)",
            [("s1", "l1"), ("s2", "l2"), ("s3", "l3")],
        )
        conn.commit()
        # Sanity: starting from autocommit/closed state.
        assert not conn.in_transaction

        conn.execute("BEGIN")
        assert conn.in_transaction
        _delete_synset_rows_within_txn(conn, ["s1", "s2"])

        # Visible inside the still-open txn: s1, s2 gone; s3 survives.
        for table in ("synset_properties", "enrichment", "lemma_metadata"):
            remaining = [
                row[0]
                for row in conn.execute(
                    f"SELECT synset_id FROM {table} ORDER BY synset_id"
                )
            ]
            assert remaining == ["s3"], f"{table} unexpected: {remaining}"

        conn.commit()
        # And persists after commit.
        for table in ("synset_properties", "enrichment", "lemma_metadata"):
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE synset_id IN ('s1', 's2')"
            ).fetchone()[0]
            assert count == 0, f"{table} still has deleted rows after commit"
    finally:
        conn.close()


def test_import_one_payload_warns_when_rollback_impossible_after_inner_commit():
    """Silent-leak surface: when an inner populate_* commits and a later
    populate_* then raises, the outer rollback path has nothing to roll
    back. That partial-import state was previously silent; the helper
    must now log a WARNING naming the payload before re-raising.

    We simulate the sequence by:
      - stubbing `_delete_synset_rows_within_txn` to a no-op,
      - stubbing `curate_properties` to issue `conn.commit()` (closing
        the outer txn),
      - stubbing `populate_synset_properties` to raise RuntimeError.

    The original RuntimeError must propagate (no exception swallowing),
    and `log.warning` must fire with "Rollback not possible" and the
    payload path.
    """
    conn = sqlite3.connect(":memory:")
    try:
        path = "/tmp/fake_payload.json"
        data = {"synsets": [{"id": "s1"}], "config": {"model": "haiku"}}
        vectors = {}

        def _curate_commits(_conn, _data, _vectors):
            _conn.commit()

        def _populate_raises(_conn, _data, _model):
            raise RuntimeError("simulated populate failure")

        with mock.patch.object(mod, "_delete_synset_rows_within_txn",
                               lambda _c, _ids: None), \
             mock.patch.object(mod, "curate_properties", _curate_commits), \
             mock.patch.object(mod, "populate_synset_properties",
                               _populate_raises), \
             mock.patch.object(mod, "populate_lemma_metadata",
                               lambda _c, _d: None), \
             mock.patch.object(mod, "log") as mock_log:
            with pytest.raises(RuntimeError,
                               match="simulated populate failure"):
                _import_one_payload(conn, path, data, vectors)

        # Exactly one WARNING, naming the payload and the rollback gap.
        assert mock_log.warning.called, "expected log.warning on silent-leak"
        call_args, _ = mock_log.warning.call_args
        msg = call_args[0]
        assert "Rollback not possible" in msg
        # First positional arg after the format string is the payload path.
        assert call_args[1] == path
    finally:
        conn.close()
