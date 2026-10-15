from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_maturity_watch_uses_real_boundary_without_consensus_overrides() -> None:
    text = (ROOT / "scripts/mainnet-maturity-pq-watch.sh").read_text()
    assert "observed == 98" in text
    assert "observed == 99" in text
    assert "SOURCE_TXID=\"a1533fe392056d7052b15868cd06d3424d65ed39613219d1af2c6cf7cb1c0d23\"" in text
    assert "transaction.raw.hex" in text
    assert "PREMATURE_REJECTION_REPORT.json" in text
    assert "MEMPOOL_ACCEPTED.json" in text
    assert "BLOCK_CONFIRMED.json" in text
    assert "mainnet-pq-boundary-transaction.py" not in text
    assert "miner-wallet" not in text
    assert "partition" not in text.lower()
    assert "SIGKILL" not in text


def test_persisted_transaction_verifier_checks_public_evidence() -> None:
    text = (ROOT / "scripts/mainnet-pq-verify-persisted-transaction.py").read_text()
    assert "deserialize_transaction" in text
    assert '"raw_sha256"' in text
    assert '"signature_sha256"' in text
    assert '"public_key_sha256"' in text


def test_outpoint_diagnostics_uses_address_then_matches_exact_outpoint() -> None:
    text = (ROOT / "scripts/mainnet-maturity-pq-watch.sh").read_text()
    assert 'python3 - "$SOURCE_ADDRESS" "$SOURCE_TXID" "$SOURCE_VOUT"' in text
    assert "s.utxo_diagnostics(sys.argv[1])" in text
    assert "source_txid, source_vout = sys.argv[2], int(sys.argv[3])" in text
    assert "r.get('txid') == source_txid and r.get('vout') == source_vout" in text
    assert "r.get('output_index')" not in text


def test_boundary_builder_requires_one_explicit_source() -> None:
    text = (ROOT / "scripts/mainnet-pq-boundary-transaction.py").read_text()
    assert "SpendCandidate(" in text
    assert 'network="mainnet"' in text
    assert '"signature_scheme_id"' in text
