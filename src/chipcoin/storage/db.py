"""Database bootstrap and connection helpers."""

from __future__ import annotations

from pathlib import Path
import sqlite3


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


def create_connection(path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with row access by column name."""

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def initialize_database(path: Path) -> sqlite3.Connection:
    """Create the initial storage schema if it does not exist."""

    connection = create_connection(path)
    with connection:
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
