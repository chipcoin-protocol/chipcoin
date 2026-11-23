"""Regression checks for the public installer boundary and private setup artifacts."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def wizard(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CHIPCOIN_SETUP_IN_CONTAINER", "1")
    monkeypatch.setenv("CHIPCOIN_SETUP_REPO_ROOT", str(ROOT))
    monkeypatch.setenv("CHIPCOIN_SETUP_STORAGE_BASE", str(tmp_path))
    spec = importlib.util.spec_from_file_location("isolated_setup_wizard", ROOT / "scripts/setup/wizard.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_network_roots_are_separate_and_mainnet_is_pq(monkeypatch, tmp_path):
    w = wizard(monkeypatch, tmp_path)
    paths = set()
    for network in ("mainnet", "testnet", "devnet"):
        values = dict(w.DEFAULTS)
        w._apply_network_defaults(values, network)
        wallet = w._wallet_path(network, "miner-wallet.json")
        assert wallet.is_relative_to(tmp_path / network)
        assert Path(values["NODE_DATA_PATH"]).is_relative_to(tmp_path / network / "chain")
        assert Path(values["CHIPCOIN_RUNTIME_HOST_DIR"]) == tmp_path / network
        paths.add(str(wallet))
    assert len(paths) == 3
    w._check_pq_backend()


def test_atomic_wallet_create_and_reuse_without_overwrite(monkeypatch, tmp_path):
    w = wizard(monkeypatch, tmp_path)
    w._prepare_storage_root(tmp_path / "mainnet")
    path = w._wallet_path("mainnet", "miner-wallet.json")
    address, public = w._handle_wallet("generate", path, network="mainnet")
    first = path.read_bytes()
    assert json.loads(first)["scheme_name"] == "mldsa44"
    assert os.stat(path).st_mode & 0o077 == 0
    assert w._handle_wallet("generate", path, network="mainnet") == (address, public)
    assert path.read_bytes() == first
    with pytest.raises(SystemExit):
        w._atomic_new_file(path, b"new secret")
    assert path.read_bytes() == first
    assert not list(path.parent.glob(".chipcoin-setup-*"))


def test_malformed_existing_wallet_is_not_replaced(monkeypatch, tmp_path):
    w = wizard(monkeypatch, tmp_path)
    w._prepare_storage_root(tmp_path / "mainnet")
    path = w._wallet_path("mainnet", "reward-owner-wallet.json")
    path.write_text("invalid", encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(SystemExit):
        w._handle_wallet("generate", path, network="mainnet")
    assert path.read_text() == "invalid"


def test_backend_preflight_fails_closed(monkeypatch, tmp_path):
    w = wizard(monkeypatch, tmp_path)
    import chipcoin.crypto.pq.mldsa as mldsa

    monkeypatch.setattr(mldsa, "mldsa44_backend_info", lambda: (_ for _ in ()).throw(RuntimeError("missing")))
    with pytest.raises(SystemExit):
        w._check_pq_backend()
    assert not list(tmp_path.rglob("*.json"))


def test_env_file_is_private_and_idempotent(monkeypatch, tmp_path):
    w = wizard(monkeypatch, tmp_path)
    root = tmp_path / "mainnet"
    w._prepare_storage_root(root)
    values = dict(w.DEFAULTS)
    w._apply_network_defaults(values, "mainnet")
    path = root / "config" / ".env"
    w._write_env(values, path)
    before = path.read_bytes()
    w._write_env(values, path)
    assert path.read_bytes() == before
    assert os.stat(path).st_mode & 0o077 == 0
    values["MINING_WORKER_COUNT"] = "9"
    with pytest.raises(SystemExit):
        w._write_env(values, path)
    assert path.read_bytes() == before


def test_registration_uses_compose_dns_not_container_loopback(monkeypatch, tmp_path):
    w = wizard(monkeypatch, tmp_path)
    assert w._default_reward_registration_peer({"NODE_P2P_BIND_PORT": "8333"}) == "node:8333"


def test_miner_only_requires_container_reachable_url(monkeypatch, tmp_path):
    w = wizard(monkeypatch, tmp_path)
    answers = iter(["http://127.0.0.1:8080", "http://node:8080", "http://", "http://miner-node.example.com:8080"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    assert w._ask_required_mining_url() == "http://miner-node.example.com:8080"


def test_failed_wizard_removes_only_new_files(monkeypatch, tmp_path):
    w = wizard(monkeypatch, tmp_path)
    existing = tmp_path / "existing-wallet.json"
    existing.write_text("keep", encoding="utf-8")
    new_wallet = tmp_path / "new-wallet.json"

    def fail_after_wallet():
        w._atomic_new_file(new_wallet, b"private-test-material")
        raise RuntimeError("later validation failed")

    monkeypatch.setattr(w, "_run_wizard", fail_after_wallet)
    with pytest.raises(RuntimeError):
        w.main()
    assert not new_wallet.exists()
    assert existing.read_text(encoding="utf-8") == "keep"
    assert not list(tmp_path.glob(".chipcoin-setup-*"))


def test_new_chain_db_private_and_no_existing_snapshot_overwrite(monkeypatch, tmp_path):
    w = wizard(monkeypatch, tmp_path)
    root = tmp_path / "mainnet"
    w._prepare_storage_root(root)
    database = root / "chain" / "node.sqlite3"
    w._prepare_sqlite_file(database, "Node data")
    assert os.stat(database).st_mode & 0o077 == 0
    snapshot = root / "chain" / "node.snapshot"
    snapshot.write_text("preserve", encoding="utf-8")
    values = dict(w.DEFAULTS)
    w._apply_network_defaults(values, "mainnet")
    values["NODE_BOOTSTRAP_MODE"] = "snapshot"
    with pytest.raises(SystemExit):
        w._prepare_node_bootstrap(values, network="mainnet")
    assert snapshot.read_text(encoding="utf-8") == "preserve"


def test_persistent_wizard_reward_wallet_renews_with_immature_coinbase_after_restart(monkeypatch, tmp_path):
    """A wizard-created PQ identity is usable by the Core across a DB reopen."""

    import asyncio
    from dataclasses import replace

    from chipcoin.consensus.genesis import mine_genesis
    from chipcoin.consensus.models import OutPoint
    from chipcoin.consensus.network_identity import PUBLIC_MAINNET_CHAIN_ID
    from chipcoin.node.runtime import NodeRuntime, RewardNodeAutomationConfig, _load_wallet_key
    from chipcoin.node.service import NodeService
    from tests.helpers import put_wallet_utxo
    from tests.node.test_mainnet_pq_end_to_end import MAINNET_PQ_TEST_PARAMS, _mine, _register_reward_node, _wallet

    w = wizard(monkeypatch, tmp_path)
    root = tmp_path / "mainnet"
    w._prepare_storage_root(root)
    w._check_pq_backend()
    wallet_path = w._wallet_path("mainnet", "reward-owner-wallet.json")
    address, _ = w._handle_wallet("generate", wallet_path, network="mainnet")
    owner = _load_wallet_key(wallet_path)
    assert owner.address == address and owner.scheme_name == "mldsa44"
    assert os.stat(wallet_path).st_mode & 0o077 == 0

    params = replace(MAINNET_PQ_TEST_PARAMS, coinbase_maturity=100)
    database = root / "chain" / "node.sqlite3"

    def open_service():
        service = NodeService.open_sqlite(database, network="mainnet", params=params,
                                          time_provider=lambda: 1_800_000_000)
        service.install_or_verify_genesis(mine_genesis(timestamp=1_799_999_999, bits=params.genesis_bits),
                                          chain_id=PUBLIC_MAINNET_CHAIN_ID)
        return service

    def make_runtime(service):
        return NodeRuntime(service=service, reward_automation=RewardNodeAutomationConfig(
            node_id="wizard-reward", owner_wallet_path=wallet_path, attest_wallet_path=wallet_path,
            auto_renew_enabled=True, auto_attest_enabled=True,
        ))

    service = open_service()
    miner = _wallet(1)
    put_wallet_utxo(service, OutPoint(txid="ab" * 32, index=0), value=300_000_000,
                    owner=owner, is_coinbase=False)
    _register_reward_node(service, wallet=owner, node_id="wizard-reward", port=19001)
    for _ in range(9):
        _mine(service, miner.address)
    put_wallet_utxo(service, OutPoint(txid="cd" * 32, index=0), value=1,
                    owner=owner, height=9, is_coinbase=True)
    asyncio.run(make_runtime(service)._run_reward_automation_once())
    renewal = next(tx for tx in service.list_mempool_transactions()
                   if tx.metadata.get("kind") == "renew_reward_node")
    assert OutPoint(txid="cd" * 32, index=0) not in {item.previous_output for item in renewal.inputs}
    _mine(service, miner.address)
    assert service.get_registered_node("wizard-reward").last_renewed_height == 10
    service.connection.close()

    restarted = open_service()
    for _ in range(9):
        _mine(restarted, miner.address)
    put_wallet_utxo(restarted, OutPoint(txid="ef" * 32, index=0), value=1,
                    owner=owner, height=19, is_coinbase=True)
    asyncio.run(make_runtime(restarted)._run_reward_automation_once())
    next_renewal = next(tx for tx in restarted.list_mempool_transactions()
                       if tx.metadata.get("kind") == "renew_reward_node"
                       and tx.metadata.get("renewal_epoch") == "2")
    assert OutPoint(txid="ef" * 32, index=0) not in {item.previous_output for item in next_renewal.inputs}
