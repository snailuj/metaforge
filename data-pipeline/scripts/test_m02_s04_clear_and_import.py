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

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from m02_s04_clear_and_import import _delete_synset_rows_within_txn


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
    """Helper proceeds when caller has issued BEGIN.

    With empty `synset_ids`, the helper short-circuits before any DML
    and never touches the (non-existent) tables — so this test pins the
    precondition without needing a fully built schema. The point is
    the assert no longer fires once `conn.in_transaction` is True.
    """
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("BEGIN")
        assert conn.in_transaction
        # Empty list → short-circuit return after the assert passes.
        _delete_synset_rows_within_txn(conn, [])
        # No exception raised; txn still owned by the caller.
        assert conn.in_transaction
        conn.rollback()
    finally:
        conn.close()
