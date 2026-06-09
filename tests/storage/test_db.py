from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from chipcoin.storage.db import LockedSQLiteConnection, SQLiteRuntimeConfig, _ensure_column, initialize_database, sqlite_config_from_env, sqlite_transaction


def test_initialize_database_creates_expected_tables() -> None:
    with TemporaryDirectory() as tempdir:
        database_path = Path(tempdir) / "chipcoin.sqlite3"
        connection = initialize_database(database_path)
        try:
            rows = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                ORDER BY name
                """
            ).fetchall()
        finally:
            connection.close()

    table_names = {row["name"] for row in rows}
    assert {"headers", "blocks", "utxos", "chain_meta"} <= table_names


def test_initialize_database_returns_sqlite_connection() -> None:
    with TemporaryDirectory() as tempdir:
        connection = initialize_database(Path(tempdir) / "chipcoin.sqlite3")
        try:
            assert isinstance(connection, sqlite3.Connection)
            assert isinstance(connection, LockedSQLiteConnection)
        finally:
            connection.close()


def test_initialize_database_adds_peer_misbehavior_columns() -> None:
    with TemporaryDirectory() as tempdir:
        connection = initialize_database(Path(tempdir) / "chipcoin.sqlite3")
        try:
            rows = connection.execute("PRAGMA table_info(peers)").fetchall()
        finally:
            connection.close()

    columns = {row["name"] for row in rows}
    assert {
        "source",
        "first_seen",
        "last_success",
        "last_failure",
        "failure_count",
        "success_count",
        "misbehavior_score",
        "misbehavior_last_updated_at",
        "ban_until",
        "last_penalty_reason",
        "last_penalty_at",
    } <= columns


def test_initialize_database_applies_sqlite_runtime_pragmas() -> None:
    with TemporaryDirectory() as tempdir:
        connection = initialize_database(
            Path(tempdir) / "chipcoin.sqlite3",
            config=SQLiteRuntimeConfig(
                journal_mode="WAL",
                synchronous="NORMAL",
                wal_autocheckpoint=4096,
                busy_timeout_ms=12000,
                cache_size=-64000,
                temp_store="MEMORY",
            ),
        )
        try:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
            wal_autocheckpoint = connection.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
            busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
            cache_size = connection.execute("PRAGMA cache_size").fetchone()[0]
            temp_store = connection.execute("PRAGMA temp_store").fetchone()[0]
        finally:
            connection.close()

    assert journal_mode == "wal"
    assert synchronous == 1
    assert wal_autocheckpoint == 4096
    assert busy_timeout == 12000
    assert cache_size == -64000
    assert temp_store == 2


def test_sqlite_safe_laptop_profile_uses_less_aggressive_sync(monkeypatch) -> None:
    monkeypatch.setenv("CHIPCOIN_SQLITE_PROFILE", "safe_laptop")

    config = sqlite_config_from_env()

    assert config.profile == "safe_laptop"
    assert config.synchronous == "NORMAL"
    assert config.wal_autocheckpoint > 1000
    assert config.io_throttle_ms > 0


def test_sqlite_transaction_reuses_outer_transaction() -> None:
    with TemporaryDirectory() as tempdir:
        connection = initialize_database(Path(tempdir) / "chipcoin.sqlite3")
        try:
            with sqlite_transaction(connection, phase="outer"):
                connection.execute("INSERT INTO chain_meta(key, value) VALUES('outer', '1')")
                with sqlite_transaction(connection, phase="inner"):
                    connection.execute("INSERT INTO chain_meta(key, value) VALUES('inner', '1')")
                assert connection.in_transaction is True
            assert connection.in_transaction is False
        finally:
            connection.close()


def test_ensure_column_ignores_duplicate_column_race() -> None:
    class _Cursor:
        def fetchall(self):
            return []

    class _Connection:
        def execute(self, statement: str):
            if statement.startswith("PRAGMA table_info("):
                return _Cursor()
            if statement.startswith("ALTER TABLE peers ADD COLUMN last_seen"):
                raise sqlite3.OperationalError("duplicate column name: last_seen")
            raise AssertionError(f"unexpected statement: {statement}")

    _ensure_column(_Connection(), table="peers", column="last_seen", definition="INTEGER")
