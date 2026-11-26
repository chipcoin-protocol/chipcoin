"""Shared-connection read regression for the P2P runtime and HTTP worker."""

from __future__ import annotations

import threading
import sys
from pathlib import Path

from chipcoin.consensus.models import BlockHeader
from chipcoin.storage.db import LockedSQLiteConnection, initialize_database, sqlite_transaction
from chipcoin.storage.headers import SQLiteHeaderRepository


def _connection() -> LockedSQLiteConnection:
    import sqlite3

    connection = sqlite3.connect(":memory:", check_same_thread=False, factory=LockedSQLiteConnection)
    connection.execute("CREATE TABLE rows (value INTEGER)")
    connection.executemany("INSERT INTO rows VALUES (?)", [(1,), (2,), (3,)])
    connection.commit()
    return connection


def test_row_materialization_is_locked_against_concurrent_write():
    connection = _connection()
    entered = threading.Event()
    release = threading.Event()
    writer_done = threading.Event()
    errors: list[BaseException] = []
    read_values: list[int] = []

    def row_factory(_cursor, row):
        entered.set()
        if not release.wait(2):
            raise TimeoutError("reader was not released")
        return row[0]

    connection.row_factory = row_factory

    def reader():
        try:
            read_values.extend(connection.execute("SELECT value FROM rows ORDER BY value").fetchall())
        except BaseException as exc:
            errors.append(exc)

    def writer():
        try:
            with sqlite_transaction(connection):
                connection.execute("UPDATE rows SET value = 99 WHERE value = 3")
        except BaseException as exc:
            errors.append(exc)
        finally:
            writer_done.set()

    read_thread = threading.Thread(target=reader)
    write_thread = threading.Thread(target=writer)
    try:
        read_thread.start()
        assert entered.wait(2)
        write_thread.start()
        # The row factory runs during result materialization. A writer must
        # wait until the entire SELECT result has been copied under the lock.
        assert not writer_done.wait(0.05)
    finally:
        release.set()
        read_thread.join(timeout=2)
        write_thread.join(timeout=2)
        connection.close()
    assert not errors
    assert not read_thread.is_alive() and not write_thread.is_alive()
    assert read_values == [1, 2, 3]


def test_cursor_fetch_methods_and_iteration_keep_sqlite_semantics():
    connection = _connection()
    try:
        cursor = connection.execute("SELECT value FROM rows ORDER BY value")
        assert cursor.description[0][0] == "value"
        assert cursor.fetchone() == (1,)
        assert cursor.fetchmany(1) == [(2,)]
        assert list(cursor) == [(3,)]
        assert cursor.fetchall() == []
        assert connection.execute("SELECT value FROM rows ORDER BY value").fetchall() == [(1,), (2,), (3,)]
        assert connection.cursor().execute("SELECT value FROM rows LIMIT 1").fetchone() == (1,)
        with sqlite_transaction(connection):
            write_cursor = connection.execute("UPDATE rows SET value = value WHERE value = 1")
            assert write_cursor.rowcount == 1
        if sys.version_info >= (3, 14):
            try:
                connection.execute("SELECT value FROM rows").fetchmany(-1)
            except ValueError:
                pass
            else:
                raise AssertionError("Python 3.14 rejects negative fetchmany size")
        else:
            assert connection.execute("SELECT value FROM rows").fetchmany(-1) == [(1,), (2,), (3,)]
        connection.row_factory = lambda _cursor, _row: None
        assert list(connection.execute("SELECT value FROM rows LIMIT 1")) == [None]
    finally:
        connection.close()


def test_header_best_tip_and_path_reads_during_concurrent_inserts(tmp_path: Path):
    connection = initialize_database(tmp_path / "node.sqlite3")
    repository = SQLiteHeaderRepository(connection)
    genesis = BlockHeader(1, "00" * 32, "11" * 32, 1_700_000_000, 0x207FFFFF, 0)
    repository.put(genesis, height=0, cumulative_work=1, is_main_chain=True)
    errors: list[BaseException] = []

    def writer():
        try:
            parent = genesis.block_hash()
            for height in range(1, 65):
                header = BlockHeader(1, parent, "11" * 32, 1_700_000_000 + height, 0x207FFFFF, height)
                repository.put(header, height=height, cumulative_work=height + 1, is_main_chain=True)
                parent = header.block_hash()
        except BaseException as exc:
            errors.append(exc)

    def reader():
        try:
            for _ in range(128):
                best = repository.find_best_tip()
                assert best is not None
                assert repository.get_record(best.block_hash) is not None
                assert repository.path_to_root(best.block_hash)[0] == genesis.block_hash()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        assert all(not thread.is_alive() for thread in threads)
        assert not errors
        assert repository.find_best_tip().height == 64
    finally:
        connection.close()
