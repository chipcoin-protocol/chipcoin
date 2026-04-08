from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[2]
WIZARD_PATH = REPO_ROOT / "scripts" / "setup" / "wizard.py"


def load_wizard_module():
    spec = importlib.util.spec_from_file_location("chipcoin_setup_wizard", WIZARD_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quick_mode_same_host_defaults_node_remote_miner_local_http() -> None:
    wizard = load_wizard_module()
    env_values = dict(wizard.DEFAULTS)

    wizard._apply_setup_mode(env_values, "quick", "both")

    assert env_values["NODE_DIRECT_PEERS"] == "chipcoinprotocol.com:18444"
    assert env_values["MINING_NODE_URLS"] == "http://node:8081"
    assert env_values["DIRECT_PEERS"] == ""
    assert env_values["BOOTSTRAP_URL"] == ""


def test_quick_mode_miner_only_defaults_to_remote_peer() -> None:
    wizard = load_wizard_module()
    env_values = dict(wizard.DEFAULTS)

    wizard._apply_setup_mode(env_values, "quick", "miner")

    assert env_values["NODE_DIRECT_PEERS"] == "chipcoinprotocol.com:18444"
    assert env_values["MINING_NODE_URLS"] == "https://api.chipcoinprotocol.com"


def test_local_mode_same_host_keeps_node_isolated_and_miner_local_http() -> None:
    wizard = load_wizard_module()
    env_values = dict(wizard.DEFAULTS)

    wizard._apply_setup_mode(env_values, "local", "both")

    assert env_values["NODE_DIRECT_PEERS"] == ""
    assert env_values["NODE_BOOTSTRAP_URL"] == ""
    assert env_values["MINING_NODE_URLS"] == "http://node:8081"
    assert env_values["DIRECT_PEERS"] == ""


def test_env_examples_expose_service_specific_discovery_defaults() -> None:
    for env_path in [REPO_ROOT / ".env.example", REPO_ROOT / "config" / "env" / ".env.example"]:
        content = env_path.read_text(encoding="utf-8")
        assert "NODE_DIRECT_PEERS=" in content
        assert "NODE_BOOTSTRAP_URL=" in content
        assert "MINING_NODE_URLS=" in content


def test_prepare_runtime_files_skips_node_db_for_miner_only() -> None:
    wizard = load_wizard_module()
    with TemporaryDirectory() as tempdir:
        node_data_path = Path(tempdir) / "node-devnet.sqlite3"
        env_values = dict(wizard.DEFAULTS)
        env_values["NODE_DATA_PATH"] = str(node_data_path)

        wizard._prepare_runtime_files(env_values, role="miner")

        assert node_data_path.exists() is False


def test_prepare_runtime_files_creates_node_db_for_node_role() -> None:
    wizard = load_wizard_module()
    with TemporaryDirectory() as tempdir:
        node_data_path = Path(tempdir) / "node-devnet.sqlite3"
        env_values = dict(wizard.DEFAULTS)
        env_values["NODE_DATA_PATH"] = str(node_data_path)

        wizard._prepare_runtime_files(env_values, role="node")

        assert node_data_path.is_file()
