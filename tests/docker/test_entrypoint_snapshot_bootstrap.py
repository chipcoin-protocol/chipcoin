from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = REPO_ROOT / "docker" / "entrypoint.sh"
TESTNET_GENESIS_BITS = 0x1F07FFFF
MAINNET_GENESIS_BITS = 0x207FFFFF


def _write_minimal_node_db(path: Path, *, tip_hash: str, height: int, genesis_bits: int) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE chain_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE headers (
                block_hash TEXT PRIMARY KEY,
                previous_block_hash TEXT NOT NULL,
                bits INTEGER NOT NULL,
                height INTEGER,
                cumulative_work INTEGER,
                is_main_chain INTEGER
            );
            CREATE TABLE blocks (block_hash TEXT PRIMARY KEY, raw_block BLOB NOT NULL);
            """
        )
        connection.execute("INSERT INTO chain_meta(key, value) VALUES('chain_tip_hash', ?)", (tip_hash,))
        connection.execute(
            """
            INSERT INTO headers(block_hash, previous_block_hash, bits, height, cumulative_work, is_main_chain)
            VALUES(?, ?, ?, 0, 1, 1)
            """,
            ("genesis", "00" * 32, genesis_bits),
        )
        if height == 0:
            connection.execute("UPDATE chain_meta SET value = 'genesis' WHERE key = 'chain_tip_hash'")
            connection.execute("INSERT INTO blocks(block_hash, raw_block) VALUES('genesis', X'00')")
        else:
            connection.execute(
                """
                INSERT INTO headers(block_hash, previous_block_hash, bits, height, cumulative_work, is_main_chain)
                VALUES(?, 'genesis', ?, ?, 2, 1)
                """,
                (tip_hash, genesis_bits, height),
            )
            connection.execute("INSERT INTO blocks(block_hash, raw_block) VALUES('genesis', X'00')")
            connection.execute("INSERT INTO blocks(block_hash, raw_block) VALUES(?, X'01')", (tip_hash,))
        connection.commit()
    finally:
        connection.close()


def _run_prepare(sqlite_path: Path, template_db: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    script = f"""
set -euo pipefail
source "{ENTRYPOINT}"
download_snapshot_file() {{
  : > "$2"
}}
chipcoin() {{
  cp "$VALID_DB_TEMPLATE" "$SQLITE_UNDER_TEST"
  printf '%s\\n' '{{"ok":true}}'
}}
prepare_snapshot_bootstrap_if_needed "$SQLITE_UNDER_TEST"
node_database_bootstrap_state "$SQLITE_UNDER_TEST"
"""
    env = {
        **os.environ,
        "CHIPCOIN_ENTRYPOINT_SOURCE_ONLY": "1",
        "CHIPCOIN_NETWORK": "testnet",
        "NODE_BOOTSTRAP_MODE": "snapshot",
        "NODE_SNAPSHOT_FILE": str(tmp_path / "node.snapshot"),
        "NODE_SNAPSHOT_SELECTED_URL": "https://example.invalid/snapshot",
        "NODE_SNAPSHOT_SELECTED_HEIGHT": "9",
        "NODE_SNAPSHOT_SELECTED_HASH": "restored-tip",
        "VALID_DB_TEMPLATE": str(template_db),
        "SQLITE_UNDER_TEST": str(sqlite_path),
        "PYTHONPATH": str(REPO_ROOT / "src"),
    }
    return subprocess.run(
        ["bash", "-lc", script],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _run_prepare_via_symlink(symlink_path: Path, target_path: Path, template_db: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    script = f"""
set -euo pipefail
source "{ENTRYPOINT}"
download_snapshot_file() {{
  : > "$2"
}}
chipcoin() {{
  cp "$VALID_DB_TEMPLATE" "$SQLITE_TARGET"
  printf '%s\\n' '{{"ok":true}}'
}}
prepare_snapshot_bootstrap_if_needed "$SQLITE_SYMLINK"
test -L "$SQLITE_SYMLINK"
node_database_bootstrap_state "$SQLITE_TARGET"
"""
    env = {
        **os.environ,
        "CHIPCOIN_ENTRYPOINT_SOURCE_ONLY": "1",
        "CHIPCOIN_NETWORK": "testnet",
        "NODE_BOOTSTRAP_MODE": "snapshot",
        "NODE_SNAPSHOT_FILE": str(tmp_path / "node.snapshot"),
        "NODE_SNAPSHOT_SELECTED_URL": "https://example.invalid/snapshot",
        "NODE_SNAPSHOT_SELECTED_HEIGHT": "9",
        "NODE_SNAPSHOT_SELECTED_HASH": "restored-tip",
        "VALID_DB_TEMPLATE": str(template_db),
        "SQLITE_SYMLINK": str(symlink_path),
        "SQLITE_TARGET": str(target_path),
        "PYTHONPATH": str(REPO_ROOT / "src"),
    }
    return subprocess.run(
        ["bash", "-lc", script],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_entrypoint_restores_snapshot_when_database_is_missing(tmp_path: Path) -> None:
    template_db = tmp_path / "restored.sqlite3"
    sqlite_path = tmp_path / "missing.sqlite3"
    _write_minimal_node_db(template_db, tip_hash="restored-tip", height=9, genesis_bits=TESTNET_GENESIS_BITS)

    result = _run_prepare(sqlite_path, template_db, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Snapshot bootstrap required" in result.stdout
    assert "Snapshot bootstrap imported" in result.stdout
    assert "initialized\tok\t9\trestored-tip" in result.stdout


def test_entrypoint_restores_snapshot_without_replacing_sqlite_symlink(tmp_path: Path) -> None:
    template_db = tmp_path / "restored.sqlite3"
    target_path = tmp_path / "configured.sqlite3"
    symlink_path = tmp_path / "runtime.sqlite3"
    symlink_path.symlink_to(target_path)
    _write_minimal_node_db(template_db, tip_hash="restored-tip", height=9, genesis_bits=TESTNET_GENESIS_BITS)

    result = _run_prepare_via_symlink(symlink_path, target_path, template_db, tmp_path)

    assert result.returncode == 0, result.stderr
    assert symlink_path.is_symlink()
    assert symlink_path.resolve(strict=False) == target_path
    assert "initialized\tok\t9\trestored-tip" in result.stdout


def test_entrypoint_restores_snapshot_when_database_is_zero_byte(tmp_path: Path) -> None:
    template_db = tmp_path / "restored.sqlite3"
    sqlite_path = tmp_path / "zero.sqlite3"
    sqlite_path.touch()
    _write_minimal_node_db(template_db, tip_hash="restored-tip", height=9, genesis_bits=TESTNET_GENESIS_BITS)

    result = _run_prepare(sqlite_path, template_db, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "reason=zero_byte" in result.stdout
    assert "initialized\tok\t9\trestored-tip" in result.stdout


def test_entrypoint_restores_snapshot_when_database_is_empty_sqlite(tmp_path: Path) -> None:
    template_db = tmp_path / "restored.sqlite3"
    sqlite_path = tmp_path / "empty.sqlite3"
    connection = sqlite3.connect(sqlite_path)
    connection.execute("CREATE TABLE unrelated(id INTEGER PRIMARY KEY)")
    connection.commit()
    connection.close()
    _write_minimal_node_db(template_db, tip_hash="restored-tip", height=9, genesis_bits=TESTNET_GENESIS_BITS)

    result = _run_prepare(sqlite_path, template_db, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "reason=schema_missing" in result.stdout
    assert "initialized\tok\t9\trestored-tip" in result.stdout


def test_entrypoint_does_not_overwrite_valid_database(tmp_path: Path) -> None:
    template_db = tmp_path / "restored.sqlite3"
    sqlite_path = tmp_path / "valid.sqlite3"
    _write_minimal_node_db(template_db, tip_hash="restored-tip", height=9, genesis_bits=TESTNET_GENESIS_BITS)
    _write_minimal_node_db(sqlite_path, tip_hash="existing-tip", height=7, genesis_bits=TESTNET_GENESIS_BITS)

    result = _run_prepare(sqlite_path, template_db, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "reason=node_database_already_initialized" in result.stdout
    assert "initialized\tok\t7\texisting-tip" in result.stdout


def test_entrypoint_refuses_wrong_network_database(tmp_path: Path) -> None:
    template_db = tmp_path / "restored.sqlite3"
    sqlite_path = tmp_path / "wrong-network.sqlite3"
    _write_minimal_node_db(template_db, tip_hash="restored-tip", height=9, genesis_bits=TESTNET_GENESIS_BITS)
    _write_minimal_node_db(sqlite_path, tip_hash="mainnet-tip", height=7, genesis_bits=MAINNET_GENESIS_BITS)

    result = _run_prepare(sqlite_path, template_db, tmp_path)

    assert result.returncode != 0
    assert "wrong-network database" in result.stderr
    assert "initialized\tok\t9\trestored-tip" not in result.stdout
