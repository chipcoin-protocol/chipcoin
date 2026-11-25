from pathlib import Path
from tempfile import TemporaryDirectory

from chipcoin.consensus.merkle import merkle_root
from chipcoin.consensus.models import Block, BlockHeader, Transaction, TxOutput
from chipcoin.storage.db import initialize_database
from chipcoin.storage.headers import SQLiteHeaderRepository


def _block(previous_block_hash: str, *, timestamp: int, nonce: int) -> Block:
    transaction = Transaction(
        version=1,
        inputs=(),
        outputs=(TxOutput(value=50, recipient="CHCminer"),),
        metadata={"coinbase": "true"},
    )
    return Block(
        header=BlockHeader(
            version=1,
            previous_block_hash=previous_block_hash,
            merkle_root=merkle_root([transaction.txid()]),
            timestamp=timestamp,
            bits=0x207FFFFF,
            nonce=nonce,
        ),
        transactions=(transaction,),
    )


def test_find_best_tip_orders_large_cumulative_work_as_full_precision_integer() -> None:
    with TemporaryDirectory() as tempdir:
        connection = initialize_database(Path(tempdir) / "chipcoin.sqlite3")
        try:
            repository = SQLiteHeaderRepository(connection)
            genesis = _block("00" * 32, timestamp=1_700_000_000, nonce=1)
            branch_a = _block(genesis.block_hash(), timestamp=1_700_000_001, nonce=2)
            branch_b = _block(genesis.block_hash(), timestamp=1_700_000_002, nonce=3)

            repository.put(genesis.header, height=0, cumulative_work=2**63 - 1, is_main_chain=True)
            repository.put(branch_a.header, height=1, cumulative_work=2**63 + 5, is_main_chain=False)
            repository.put(branch_b.header, height=1, cumulative_work=10**30, is_main_chain=False)

            best_tip = repository.find_best_tip()

            assert best_tip is not None
            assert best_tip.block_hash == branch_b.block_hash()
        finally:
            connection.close()


def test_find_best_tip_skips_legacy_null_header_without_losing_valid_tip() -> None:
    with TemporaryDirectory() as tempdir:
        connection = initialize_database(Path(tempdir) / "chipcoin.sqlite3")
        try:
            repository = SQLiteHeaderRepository(connection)
            genesis = _block("00" * 32, timestamp=1_700_000_000, nonce=1)
            repository.put(genesis.header, height=0, cumulative_work=1, is_main_chain=True)
            candidate = _block(genesis.block_hash(), timestamp=1_700_000_001, nonce=2)
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("PRAGMA ignore_check_constraints = ON")
            # A current schema rejects NULL; a legacy table can still contain it.
            connection.execute("ALTER TABLE headers RENAME TO headers_current")
            connection.execute(
                "CREATE TABLE headers (block_hash TEXT PRIMARY KEY, previous_block_hash TEXT, "
                "merkle_root TEXT, version INTEGER, timestamp INTEGER, bits INTEGER, nonce INTEGER, "
                "height INTEGER, cumulative_work TEXT, is_main_chain INTEGER, raw_header BLOB)"
            )
            connection.execute(
                "INSERT INTO headers SELECT * FROM headers_current"
            )
            connection.execute("DROP TABLE headers_current")
            connection.execute(
                "INSERT INTO headers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (candidate.block_hash(), genesis.block_hash(), candidate.header.merkle_root,
                 candidate.header.version, candidate.header.timestamp, candidate.header.bits,
                 candidate.header.nonce, 1, "2", 0, None),
            )
            assert repository.find_best_tip().block_hash == genesis.block_hash()
            assert repository.incomplete_best_header_seen
            assert repository.get_record(candidate.block_hash()) is None
            repository.put(candidate.header, height=1, cumulative_work=2)
            assert repository.find_best_tip().block_hash == candidate.block_hash()
            assert not repository.incomplete_best_header_seen
        finally:
            connection.close()


def test_malformed_header_is_not_advertised_or_selected() -> None:
    with TemporaryDirectory() as tempdir:
        connection = initialize_database(Path(tempdir) / "node.sqlite3")
        try:
            repository = SQLiteHeaderRepository(connection)
            genesis = _block("00" * 32, timestamp=1_700_000_000, nonce=1)
            candidate = _block(genesis.block_hash(), timestamp=1_700_000_001, nonce=2)
            repository.put(genesis.header, height=0, cumulative_work=1, is_main_chain=True)
            repository.put(candidate.header, height=1, cumulative_work=2, is_main_chain=True)
            connection.execute("UPDATE headers SET raw_header=? WHERE block_hash=?", (b"", candidate.block_hash()))
            assert repository.get_record(candidate.block_hash()) is None
            assert repository.find_best_tip().block_hash == genesis.block_hash()
            assert repository.incomplete_best_header_seen
            assert repository.get_headers_after((genesis.block_hash(),), "00" * 32) == ()
        finally:
            connection.close()
