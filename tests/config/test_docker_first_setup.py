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
