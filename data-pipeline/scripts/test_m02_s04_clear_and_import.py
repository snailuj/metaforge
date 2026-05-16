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
    import_one_payload_safely,
)

# Local alias keeps the existing test bodies compact and intention-
# revealing — the tests are exercising the silent-leak-aware import
# path, not the helper's name.
_import_one_payload = import_one_payload_safely


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
    and `log.warning` must fire with the partial-import wording and the
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
        assert "Possible PARTIAL-IMPORT state" in msg
        # First positional arg after the format string is the payload path.
        assert call_args[1] == path
    finally:
        conn.close()


def test_import_one_payload_warns_when_populate_raises_after_inner_commit_with_dml():
    """Pin the DOMINANT silent-leak path that the in_transaction proxy missed.

    Round 4 gated the WARNING on `if not conn.in_transaction`. That works
    in the narrow case where populate raises BEFORE any DML, but the
    dominant production failure mode is: curate commits → populate issues
    an INSERT (sqlite3 auto-opens an implicit txn, so
    `conn.in_transaction == True` again) → populate then raises
    mid-execution. Under the Round 4 logic, the implicit-txn branch is
    taken, rollback only undoes the partial INSERT, and the WARNING never
    fires — the DELETEs and curate's writes leak silently.

    This test simulates that exact sequence:
      - `_delete_synset_rows_within_txn` is no-op'd,
      - `curate_properties` commits (closing the outer BEGIN),
      - `populate_synset_properties` executes a DML statement (opening
        an implicit txn — `conn.in_transaction` flips back to True) and
        THEN raises.

    The fix must surface the WARNING regardless of the implicit-txn
    state, by tracking partial-atomicity explicitly via a flag set after
    curate's inner commit.
    """
    conn = sqlite3.connect(":memory:")
    try:
        # Provide a target table for the DML inside the populate stub so
        # the INSERT genuinely opens an implicit transaction. Use a
        # throwaway schema; the helper itself is mocked, so we don't
        # need real synset_properties columns here.
        conn.executescript(
            "CREATE TABLE scratch (id TEXT);"
        )

        path = "/tmp/fake_payload_with_dml.json"
        data = {"synsets": [{"id": "s1"}], "config": {"model": "haiku"}}
        vectors = {}

        def _curate_commits(_conn, _data, _vectors):
            _conn.commit()

        def _populate_dml_then_raises(_conn, _data, _model):
            # First DML after curate's commit — sqlite3 auto-begins an
            # implicit transaction, so in_transaction flips back to True.
            _conn.execute("INSERT INTO scratch (id) VALUES (?)", ("dml-row",))
            assert _conn.in_transaction, (
                "precondition: implicit txn must be open after DML"
            )
            raise RuntimeError("simulated mid-populate failure")

        with mock.patch.object(mod, "_delete_synset_rows_within_txn",
                               lambda _c, _ids: None), \
             mock.patch.object(mod, "curate_properties", _curate_commits), \
             mock.patch.object(mod, "populate_synset_properties",
                               _populate_dml_then_raises), \
             mock.patch.object(mod, "populate_lemma_metadata",
                               lambda _c, _d: None), \
             mock.patch.object(mod, "log") as mock_log:
            with pytest.raises(RuntimeError,
                               match="simulated mid-populate failure"):
                _import_one_payload(conn, path, data, vectors)

        # The WARNING must fire even though the implicit txn was open at
        # the moment populate raised — the partial-atomicity gap is
        # determined by whether an inner commit has already happened,
        # not by the live in_transaction state.
        assert mock_log.warning.called, (
            "expected log.warning to fire on DML-then-raise after "
            "curate's inner commit"
        )
        call_args, _ = mock_log.warning.call_args
        msg = call_args[0]
        assert "Possible PARTIAL-IMPORT state" in msg
        assert call_args[1] == path

        # And the connection must be left in a clean state for any
        # subsequent payload — rollback of the partial INSERT should
        # have run on the way out.
        assert not conn.in_transaction, (
            "connection should be left out of any implicit txn so the "
            "next payload's BEGIN can run"
        )
        # Stronger: assert the partial INSERT was actually rolled back,
        # not merely that no transaction is open. `not in_transaction`
        # could also be satisfied by an inadvertent commit; the
        # row-level check pins the rollback semantics.
        remaining = conn.execute("SELECT COUNT(*) FROM scratch").fetchone()[0]
        assert remaining == 0, (
            f"partial DML row should have been rolled back; found {remaining}"
        )
    finally:
        conn.close()


def test_import_one_payload_warns_when_curate_raises_after_internal_commit_but_before_return():
    """OF1: post-commit-pre-return window in curate is now covered.

    Reproduces the topology of `enrich_pipeline.curate_properties`:
    `conn.commit()` at line 172 fires, then `print(...)` at line 173 may
    raise (BrokenPipeError on a closed stdout, OSError on ENOSPC) before
    `return` at line 174. The outer BEGIN's rollback cannot undo curate's
    commit; the WARNING must still fire so the operator sees the
    PARTIAL-IMPORT state.

    Pre-fix behaviour: `inner_commit_seen = True` was set AFTER curate
    returned, so any raise between curate's internal commit and the
    flag-set line was missed — silent leak.

    Post-fix behaviour: `inner_commit_seen = True` is set via try/finally
    around curate, so the flag is True even if curate raises after its
    internal commit. WARNING fires; original exception still propagates.
    """
    conn = sqlite3.connect(":memory:")
    try:
        path = "/tmp/fake_payload_curate_post_commit_raise.json"
        data = {"synsets": [{"id": "s1"}], "config": {"model": "haiku"}}
        vectors = {}

        def _curate_commits_then_raises(_conn, _data, _vectors):
            # Mirror curate_properties' tail: commit lands, then a later
            # statement raises. Models BrokenPipeError on closed stdout
            # during print(), or any future maintainer code added between
            # the commit and return.
            _conn.commit()
            raise BrokenPipeError("simulated stdout pipe closed after commit")

        with mock.patch.object(mod, "_delete_synset_rows_within_txn",
                               lambda _c, _ids: None), \
             mock.patch.object(mod, "curate_properties",
                               _curate_commits_then_raises), \
             mock.patch.object(mod, "populate_synset_properties",
                               lambda _c, _d, _m: None), \
             mock.patch.object(mod, "populate_lemma_metadata",
                               lambda _c, _d: None), \
             mock.patch.object(mod, "log") as mock_log:
            with pytest.raises(BrokenPipeError,
                               match="simulated stdout pipe closed"):
                _import_one_payload(conn, path, data, vectors)

        # The WARNING must fire — curate's internal commit has already
        # landed before the raise, so we are in PARTIAL-IMPORT state
        # even though `inner_commit_seen` was never assigned by the
        # post-curate `inner_commit_seen = True` statement.
        assert mock_log.warning.called, (
            "expected log.warning when curate raises after its internal "
            "commit but before returning"
        )
        call_args, _ = mock_log.warning.call_args
        msg = call_args[0]
        assert "Possible PARTIAL-IMPORT state" in msg
        assert call_args[1] == path
    finally:
        conn.close()


def test_import_one_payload_preserves_original_exception_when_rollback_fails_after_inner_commit():
    """OF2: rollback failure in the WARNING branch must not mask the original.

    The post-inner-commit cleanup runs `conn.rollback()` to clear any
    implicit-txn DML the failing populate may have started. If that
    rollback itself raises (e.g. `sqlite3.OperationalError: database is
    locked`), it must NOT replace the original populate failure via
    `__context__` chaining — that error is what the operator needs to
    see.

    Mock the connection wholesale so we can inject rollback failure
    without fighting real sqlite semantics.
    """
    path = "/tmp/fake_payload_rollback_fails.json"
    data = {"synsets": [{"id": "s1"}], "config": {"model": "haiku"}}
    vectors = {}

    fake_conn = mock.MagicMock(spec=sqlite3.Connection)
    # in_transaction is True so the rollback branch is entered.
    fake_conn.in_transaction = True
    fake_conn.rollback.side_effect = sqlite3.OperationalError(
        "database is locked"
    )

    def _curate_commits(_conn, _data, _vectors):
        # No-op — we only need inner_commit_seen to be True before
        # populate raises (set by Fix 2's try/finally).
        pass

    def _populate_raises(_conn, _data, _model):
        raise RuntimeError("original populate failure")

    with mock.patch.object(mod, "_delete_synset_rows_within_txn",
                           lambda _c, _ids: None), \
         mock.patch.object(mod, "curate_properties", _curate_commits), \
         mock.patch.object(mod, "populate_synset_properties",
                           _populate_raises), \
         mock.patch.object(mod, "populate_lemma_metadata",
                           lambda _c, _d: None), \
         mock.patch.object(mod, "log") as mock_log:
        with pytest.raises(RuntimeError, match="original populate failure"):
            _import_one_payload(fake_conn, path, data, vectors)

    # Both the PARTIAL-IMPORT WARNING and the rollback-failure WARNING
    # must fire — operator sees both signals.
    warnings = [c.args[0] for c in mock_log.warning.call_args_list]
    assert any("Possible PARTIAL-IMPORT state" in w for w in warnings), (
        f"expected the partial-import WARNING; got: {warnings}"
    )
    assert any("Rollback of post-inner-commit partial DML failed"
               in w for w in warnings), (
        f"expected the rollback-failed WARNING; got: {warnings}"
    )


def test_import_one_payload_preserves_original_exception_when_rollback_fails_pre_inner_commit():
    """OF2 symmetry: same protection on the pre-inner-commit branch.

    Post-Fix-2, `inner_commit_seen` is set via try/finally around
    curate_properties, so a raise from inside curate still toggles the
    flag to True. To exercise the *false* (pre-inner-commit) branch we
    must raise from `_delete_synset_rows_within_txn` BEFORE curate runs
    at all. The rollback in that branch must also be hardened against
    its own failure.
    """
    path = "/tmp/fake_payload_rollback_fails_pre_commit.json"
    data = {"synsets": [{"id": "s1"}], "config": {"model": "haiku"}}
    vectors = {}

    fake_conn = mock.MagicMock(spec=sqlite3.Connection)
    fake_conn.in_transaction = True
    fake_conn.rollback.side_effect = sqlite3.OperationalError(
        "database is locked"
    )

    def _delete_raises(_conn, _ids):
        raise RuntimeError("original delete failure before any commit")

    with mock.patch.object(mod, "_delete_synset_rows_within_txn",
                           _delete_raises), \
         mock.patch.object(mod, "curate_properties",
                           lambda _c, _d, _v: None), \
         mock.patch.object(mod, "populate_synset_properties",
                           lambda _c, _d, _m: None), \
         mock.patch.object(mod, "populate_lemma_metadata",
                           lambda _c, _d: None), \
         mock.patch.object(mod, "log") as mock_log:
        with pytest.raises(RuntimeError,
                           match="original delete failure before any commit"):
            _import_one_payload(fake_conn, path, data, vectors)

    # The rollback-failure WARNING must fire on this branch too.
    warnings = [c.args[0] for c in mock_log.warning.call_args_list]
    assert any("Rollback of pre-inner-commit DML failed"
               in w for w in warnings), (
        f"expected the rollback-failed WARNING on the pre-commit branch; "
        f"got: {warnings}"
    )
