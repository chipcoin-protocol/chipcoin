"""Database bootstrap and connection helpers."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import sqlite3
import threading
import time


logger = logging.getLogger(__name__)
_WRITE_METRICS: dict[int, "SQLiteWriteMetrics"] = {}


class LockedSQLiteConnection(sqlite3.Connection):
    """SQLite connection serialized for safe cross-thread node access."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._chipcoin_lock = threading.RLock()

    def execute(self, *args, **kwargs):
        with self._chipcoin_lock:
            return super().execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        with self._chipcoin_lock:
            return super().executemany(*args, **kwargs)

    def executescript(self, *args, **kwargs):
        with self._chipcoin_lock:
            return super().executescript(*args, **kwargs)

    def commit(self) -> None:
        with self._chipcoin_lock:
            return super().commit()

    def rollback(self) -> None:
        with self._chipcoin_lock:
            return super().rollback()


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS headers (
        block_hash TEXT PRIMARY KEY,
        previous_block_hash TEXT NOT NULL,
        merkle_root TEXT NOT NULL,
        version INTEGER NOT NULL,
        timestamp INTEGER NOT NULL,
        bits INTEGER NOT NULL,
        nonce INTEGER NOT NULL,
        height INTEGER,
        cumulative_work TEXT,
        is_main_chain INTEGER NOT NULL DEFAULT 0,
        raw_header BLOB NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_headers_previous_block_hash
    ON headers(previous_block_hash)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_headers_height_main_chain
    ON headers(height, is_main_chain)
    """,
    """
    CREATE TABLE IF NOT EXISTS blocks (
        block_hash TEXT PRIMARY KEY,
        raw_block BLOB NOT NULL,
        FOREIGN KEY(block_hash) REFERENCES headers(block_hash)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS utxos (
        txid TEXT NOT NULL,
        output_index INTEGER NOT NULL,
        value INTEGER NOT NULL,
        recipient TEXT NOT NULL,
        height INTEGER NOT NULL,
        is_coinbase INTEGER NOT NULL,
        PRIMARY KEY(txid, output_index)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chain_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mempool_transactions (
        txid TEXT PRIMARY KEY,
        raw_transaction BLOB NOT NULL,
        fee INTEGER NOT NULL,
        added_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS peers (
        host TEXT NOT NULL,
        port INTEGER NOT NULL,
        network TEXT NOT NULL,
        PRIMARY KEY(host, port, network)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS node_registry (
        node_id TEXT PRIMARY KEY,
        payout_address TEXT NOT NULL,
        owner_pubkey TEXT NOT NULL UNIQUE,
        registered_height INTEGER NOT NULL,
        last_renewed_height INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reward_attestation_bundles (
        txid TEXT PRIMARY KEY,
        block_height INTEGER NOT NULL,
        epoch_index INTEGER NOT NULL,
        bundle_window_index INTEGER NOT NULL,
        bundle_submitter_node_id TEXT NOT NULL,
        attestation_count INTEGER NOT NULL,
        attestations_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_reward_attestation_bundles_epoch_window
    ON reward_attestation_bundles(epoch_index, bundle_window_index)
    """,
    """
    CREATE TABLE IF NOT EXISTS reward_attestation_entries (
        txid TEXT NOT NULL,
        bundle_position INTEGER NOT NULL,
        epoch_index INTEGER NOT NULL,
        check_window_index INTEGER NOT NULL,
        candidate_node_id TEXT NOT NULL,
        verifier_node_id TEXT NOT NULL,
        result_code TEXT NOT NULL,
        observed_sync_gap INTEGER NOT NULL,
        endpoint_commitment TEXT NOT NULL,
        concentration_key TEXT NOT NULL,
        signature_hex TEXT NOT NULL,
        PRIMARY KEY(txid, bundle_position),
        FOREIGN KEY(txid) REFERENCES reward_attestation_bundles(txid)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_reward_attestation_entries_identity
    ON reward_attestation_entries(epoch_index, check_window_index, candidate_node_id, verifier_node_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS epoch_settlements (
        txid TEXT PRIMARY KEY,
        block_height INTEGER NOT NULL,
        epoch_index INTEGER NOT NULL,
        epoch_start_height INTEGER NOT NULL,
        epoch_end_height INTEGER NOT NULL,
        epoch_seed_hex TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        submission_mode TEXT NOT NULL DEFAULT 'manual',
        candidate_summary_root TEXT NOT NULL,
        verified_nodes_root TEXT NOT NULL,
        rewarded_nodes_root TEXT NOT NULL,
        rewarded_node_count INTEGER NOT NULL,
        distributed_node_reward_chipbits INTEGER NOT NULL,
        undistributed_node_reward_chipbits INTEGER NOT NULL,
        reward_entries_json TEXT NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_epoch_settlements_epoch_index
    ON epoch_settlements(epoch_index)
    """,
    """
    CREATE TABLE IF NOT EXISTS epoch_settlement_entries (
        txid TEXT NOT NULL,
        selection_rank INTEGER NOT NULL,
        node_id TEXT NOT NULL,
        payout_address TEXT NOT NULL,
        reward_chipbits INTEGER NOT NULL,
        concentration_key TEXT NOT NULL,
        final_confirmation_passed INTEGER NOT NULL,
        PRIMARY KEY(txid, selection_rank),
        FOREIGN KEY(txid) REFERENCES epoch_settlements(txid)
    )
    """,
)


@dataclass(frozen=True)
class SQLiteRuntimeConfig:
    """SQLite durability and write-behaviour knobs for node storage."""

    journal_mode: str = "WAL"
    synchronous: str = "FULL"
    wal_autocheckpoint: int = 1000
    busy_timeout_ms: int = 30000
    cache_size: int = -20000
    temp_store: str = "MEMORY"
    batch_size: int = 250
    checkpoint_interval: int = 1000
    io_throttle_ms: int = 0
    profile: str = "default"


class SQLiteWriteMetrics:
    """Low-overhead transaction metrics for diagnosing write storms."""

    def __init__(self, *, log_interval_seconds: float = 60.0) -> None:
        self.log_interval_seconds = log_interval_seconds
        self.transaction_count = 0
        self.total_transaction_seconds = 0.0
        self._last_log_at = time.monotonic()

    def record_transaction(self, *, duration_seconds: float, phase: str | None = None) -> None:
        self.transaction_count += 1
        self.total_transaction_seconds += duration_seconds
        now = time.monotonic()
        if now - self._last_log_at < self.log_interval_seconds:
            return
        elapsed = max(now - self._last_log_at, 0.001)
        average_ms = (self.total_transaction_seconds / max(self.transaction_count, 1)) * 1000.0
        logger.info(
            "sqlite write metrics phase=%s transactions=%s tx_per_sec=%.2f avg_transaction_ms=%.2f",
            phase or "unknown",
            self.transaction_count,
            self.transaction_count / elapsed,
            average_ms,
        )
        self.transaction_count = 0
        self.total_transaction_seconds = 0.0
        self._last_log_at = now


def sqlite_config_from_env() -> SQLiteRuntimeConfig:
    """Build SQLite runtime configuration from environment variables."""

    profile = os.getenv("CHIPCOIN_SQLITE_PROFILE", "default").strip().lower() or "default"
    safe_laptop = profile in {"safe_laptop", "laptop", "weak_ssd"} or _parse_bool_env(os.getenv("CHIPCOIN_SQLITE_SAFE_LAPTOP"))
    default_sync = "NORMAL" if safe_laptop else "FULL"
    default_wal_autocheckpoint = 4000 if safe_laptop else 1000
    default_batch_size = 500 if safe_laptop else 250
    default_io_throttle_ms = 5 if safe_laptop else 0
    return SQLiteRuntimeConfig(
        journal_mode=_normalize_journal_mode(os.getenv("CHIPCOIN_SQLITE_JOURNAL_MODE", "WAL")),
        synchronous=_normalize_sync_mode(os.getenv("CHIPCOIN_SQLITE_SYNC_MODE", default_sync)),
        wal_autocheckpoint=max(0, _int_env("CHIPCOIN_SQLITE_WAL_AUTOCHECKPOINT", default_wal_autocheckpoint)),
        busy_timeout_ms=max(0, _int_env("CHIPCOIN_SQLITE_BUSY_TIMEOUT_MS", 30000)),
        cache_size=_int_env("CHIPCOIN_SQLITE_CACHE_SIZE", -20000),
        temp_store=_normalize_temp_store(os.getenv("CHIPCOIN_SQLITE_TEMP_STORE", "MEMORY")),
        batch_size=max(1, _int_env("CHIPCOIN_SQLITE_BATCH_SIZE", default_batch_size)),
        checkpoint_interval=max(0, _int_env("CHIPCOIN_SQLITE_CHECKPOINT_INTERVAL", default_wal_autocheckpoint)),
        io_throttle_ms=max(0, _int_env("CHIPCOIN_IO_THROTTLE_MS", default_io_throttle_ms)),
        profile="safe_laptop" if safe_laptop else profile,
    )


def create_connection(path: Path, *, config: SQLiteRuntimeConfig | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with row access by column name."""

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False, timeout=30.0, factory=LockedSQLiteConnection)
    connection.row_factory = sqlite3.Row
    apply_sqlite_pragmas(connection, config or sqlite_config_from_env())
    _WRITE_METRICS[id(connection)] = SQLiteWriteMetrics()
    return connection


def initialize_database(path: Path, *, config: SQLiteRuntimeConfig | None = None) -> sqlite3.Connection:
    """Create the initial storage schema if it does not exist."""

    runtime_config = config or sqlite_config_from_env()
    connection = create_connection(path, config=runtime_config)
    with sqlite_transaction(connection, phase="schema"):
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        _ensure_column(connection, table="peers", column="direction", definition="TEXT")
        _ensure_column(connection, table="peers", column="source", definition="TEXT")
        _ensure_column(connection, table="peers", column="first_seen", definition="INTEGER")
        _ensure_column(connection, table="peers", column="last_seen", definition="INTEGER")
        _ensure_column(connection, table="peers", column="last_success", definition="INTEGER")
        _ensure_column(connection, table="peers", column="last_failure", definition="INTEGER")
        _ensure_column(connection, table="peers", column="failure_count", definition="INTEGER")
        _ensure_column(connection, table="peers", column="success_count", definition="INTEGER")
        _ensure_column(connection, table="peers", column="handshake_complete", definition="INTEGER")
        _ensure_column(connection, table="peers", column="last_known_height", definition="INTEGER")
        _ensure_column(connection, table="peers", column="node_id", definition="TEXT")
        _ensure_column(connection, table="peers", column="score", definition="INTEGER")
        _ensure_column(connection, table="peers", column="reconnect_attempts", definition="INTEGER")
        _ensure_column(connection, table="peers", column="backoff_until", definition="INTEGER")
        _ensure_column(connection, table="peers", column="last_error", definition="TEXT")
        _ensure_column(connection, table="peers", column="last_error_at", definition="INTEGER")
        _ensure_column(connection, table="peers", column="protocol_error_class", definition="TEXT")
        _ensure_column(connection, table="peers", column="disconnect_count", definition="INTEGER")
        _ensure_column(connection, table="peers", column="session_started_at", definition="INTEGER")
        _ensure_column(connection, table="peers", column="misbehavior_score", definition="INTEGER")
        _ensure_column(connection, table="peers", column="misbehavior_last_updated_at", definition="INTEGER")
        _ensure_column(connection, table="peers", column="ban_until", definition="INTEGER")
        _ensure_column(connection, table="peers", column="last_penalty_reason", definition="TEXT")
        _ensure_column(connection, table="peers", column="last_penalty_at", definition="INTEGER")
        _ensure_column(connection, table="node_registry", column="node_pubkey", definition="TEXT")
        _ensure_column(connection, table="node_registry", column="declared_host", definition="TEXT")
        _ensure_column(connection, table="node_registry", column="declared_port", definition="INTEGER")
        _ensure_column(connection, table="node_registry", column="reward_registration", definition="INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, table="epoch_settlements", column="submission_mode", definition="TEXT NOT NULL DEFAULT 'manual'")
    return connection


def apply_sqlite_pragmas(connection: sqlite3.Connection, config: SQLiteRuntimeConfig) -> None:
    """Apply SQLite knobs before node repositories start using the connection."""

    connection.execute(f"PRAGMA busy_timeout = {int(config.busy_timeout_ms)}")
    connection.execute(f"PRAGMA journal_mode = {config.journal_mode}")
    connection.execute(f"PRAGMA synchronous = {config.synchronous}")
    connection.execute(f"PRAGMA wal_autocheckpoint = {int(config.wal_autocheckpoint)}")
    connection.execute(f"PRAGMA cache_size = {int(config.cache_size)}")
    connection.execute(f"PRAGMA temp_store = {config.temp_store}")


@contextmanager
def sqlite_transaction(connection: sqlite3.Connection, *, phase: str | None = None):
    """Open one write transaction, reusing an outer transaction when present."""

    lock = getattr(connection, "_chipcoin_lock", None)
    if lock is None:
        lock = _NullLock()
    with lock:
        if connection.in_transaction:
            yield
            return
        started_at = time.monotonic()
        try:
            with connection:
                yield
        finally:
            metrics = _WRITE_METRICS.get(id(connection))
            if metrics is not None:
                metrics.record_transaction(duration_seconds=time.monotonic() - started_at, phase=phase)


def checkpoint_wal(connection: sqlite3.Connection, *, mode: str = "PASSIVE", phase: str | None = None) -> None:
    """Run and log a WAL checkpoint for controlled maintenance paths."""

    started_at = time.monotonic()
    rows = connection.execute(f"PRAGMA wal_checkpoint({mode})").fetchall()
    logger.info(
        "sqlite wal checkpoint phase=%s mode=%s duration_ms=%.2f result=%s",
        phase or "unknown",
        mode,
        (time.monotonic() - started_at) * 1000.0,
        [tuple(row) for row in rows],
    )


def _ensure_column(connection: sqlite3.Connection, *, table: str, column: str, definition: str) -> None:
    """Add a column to an existing SQLite table when missing."""

    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    existing_columns = {row["name"] for row in rows}
    if column in existing_columns:
        return
    try:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError as exc:
        # Two local processes can initialize the same database concurrently
        # during container startup. Treat duplicate-column races as success.
        if f"duplicate column name: {column}" not in str(exc).lower():
            raise


def _normalize_sync_mode(value: str) -> str:
    normalized = (value or "FULL").strip().upper()
    if normalized in {"FULL", "NORMAL", "OFF"}:
        return normalized
    raise ValueError("CHIPCOIN_SQLITE_SYNC_MODE must be one of: full, normal, off")


def _normalize_journal_mode(value: str) -> str:
    normalized = (value or "WAL").strip().upper()
    if normalized in {"WAL", "DELETE", "TRUNCATE", "PERSIST", "MEMORY", "OFF"}:
        return normalized
    raise ValueError("CHIPCOIN_SQLITE_JOURNAL_MODE must be one of: wal, delete, truncate, persist, memory, off")


def _normalize_temp_store(value: str) -> str:
    normalized = (value or "MEMORY").strip().upper()
    if normalized in {"DEFAULT", "FILE", "MEMORY"}:
        return normalized
    raise ValueError("CHIPCOIN_SQLITE_TEMP_STORE must be one of: default, file, memory")


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _parse_bool_env(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class _NullLock:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, traceback):
        return False
