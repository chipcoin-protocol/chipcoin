from pathlib import Path

from dataclasses import replace
import json

import pytest

from chipcoin.config import (
    DEVNET_CONFIG,
    MAINNET_CONFIG,
    MAINNET_TEST_ONLY_CONFIG,
    NETWORK_CONFIGS,
    TEST_ONLY_ACKNOWLEDGEMENT,
    TEST_ONLY_MARKER_TEXT,
    TESTNET_CONFIG,
    expected_test_only_runtime_manifest,
    get_network_config,
    require_startable_network,
    resolve_data_path,
)
from chipcoin.consensus.genesis import GenesisNotFinalizedError
from chipcoin.consensus.params import DEVNET_PARAMS, MAINNET_PARAMS, MAINNET_TEST_ONLY_PARAMS, TESTNET_PARAMS
from chipcoin.node.service import NodeService


def test_get_network_config_supports_testnet() -> None:
    config = get_network_config("testnet")

    assert config is TESTNET_CONFIG
    assert config.name == "testnet"
    assert config.default_p2p_port == 28444
    assert config.default_data_file == "chipcoin-testnet.sqlite3"
    assert config.params is TESTNET_PARAMS
    assert config.params.max_money_chipbits == MAINNET_PARAMS.max_money_chipbits
    assert config.params.target_block_time_seconds == MAINNET_PARAMS.target_block_time_seconds
    assert config.params.target_block_time_seconds == 600
    assert (
        DEVNET_PARAMS.node_reward_activation_height
        < config.params.node_reward_activation_height
        < MAINNET_PARAMS.node_reward_activation_height
    )
    assert (
        DEVNET_PARAMS.difficulty_adjustment_window
        < config.params.difficulty_adjustment_window
        < MAINNET_PARAMS.difficulty_adjustment_window
    )


def test_mainnet_test_only_changes_only_approved_test_only_parameters() -> None:
    assert MAINNET_TEST_ONLY_CONFIG.params is MAINNET_TEST_ONLY_PARAMS
    assert MAINNET_TEST_ONLY_PARAMS.genesis_bits == 0x207FFFFF
    assert {
        key: value
        for key, value in MAINNET_TEST_ONLY_PARAMS.__dict__.items()
        if key not in {"genesis_bits", "funded_reward_node_activation_height"}
    } == {
        key: value
        for key, value in MAINNET_PARAMS.__dict__.items()
        if key not in {"genesis_bits", "funded_reward_node_activation_height"}
    }
    assert MAINNET_TEST_ONLY_PARAMS.funded_reward_node_activation_height == 300
    assert MAINNET_PARAMS.funded_reward_node_activation_height == 0


def test_public_mainnet_configuration_is_bound_to_canonical_identity() -> None:
    from chipcoin.consensus.genesis import CANONICAL_GENESIS_HASH, CANONICAL_GENESIS_TIMESTAMP

    assert MAINNET_CONFIG.chain_id == "chipcoin-mainnet-1"
    assert MAINNET_CONFIG.magic.hex() == "c0897c0d"
    assert MAINNET_CONFIG.canonical_genesis_hash == CANONICAL_GENESIS_HASH
    assert MAINNET_CONFIG.canonical_genesis_timestamp == CANONICAL_GENESIS_TIMESTAMP
    assert MAINNET_CONFIG.genesis_finalized is True
    require_startable_network("mainnet")


def test_public_mainnet_rejects_runtime_identity_override(monkeypatch) -> None:
    from dataclasses import replace

    monkeypatch.setitem(NETWORK_CONFIGS, "mainnet", replace(MAINNET_CONFIG, canonical_genesis_hash="ff" * 32))
    with pytest.raises(GenesisNotFinalizedError, match="canonical identity"):
        require_startable_network("mainnet")


def _install_startable_test_only_config(monkeypatch, tmp_path):
    config = replace(
        MAINNET_TEST_ONLY_CONFIG,
        canonical_genesis_hash="11" * 32,
        canonical_genesis_timestamp=1_700_000_000,
        genesis_finalized=True,
    )
    monkeypatch.setitem(NETWORK_CONFIGS, config.name, config)
    marker = tmp_path / "TEST-ONLY-NOT-PUBLIC"
    marker.write_text(TEST_ONLY_MARKER_TEXT + "\n", encoding="ascii")
    manifest = tmp_path / "runtime-manifest.json"
    manifest.write_text(
        json.dumps(expected_test_only_runtime_manifest(config)),
        encoding="utf-8",
    )
    return config, marker, manifest


def test_test_only_profile_cannot_start_from_environment_alone(monkeypatch) -> None:
    monkeypatch.setenv("CHIPCOIN_ENABLE_TEST_ONLY_NETWORK", TEST_ONLY_ACKNOWLEDGEMENT)
    with pytest.raises(GenesisNotFinalizedError, match="genesis is not embedded"):
        require_startable_network("mainnet-test-only")


def test_test_only_node_service_fails_before_creating_database(monkeypatch, tmp_path) -> None:
    database = tmp_path / "must-not-exist.sqlite3"
    monkeypatch.setenv("CHIPCOIN_ENABLE_TEST_ONLY_NETWORK", TEST_ONLY_ACKNOWLEDGEMENT)

    with pytest.raises(GenesisNotFinalizedError, match="genesis is not embedded"):
        NodeService.open_sqlite(database, network="mainnet-test-only")

    assert not database.exists()


def test_test_only_profile_requires_image_marker_and_runtime_manifest(monkeypatch, tmp_path) -> None:
    _, marker, manifest = _install_startable_test_only_config(monkeypatch, tmp_path)
    monkeypatch.setenv("CHIPCOIN_ENABLE_TEST_ONLY_NETWORK", TEST_ONLY_ACKNOWLEDGEMENT)
    monkeypatch.setenv("CHIPCOIN_TEST_ONLY_MARKER_FILE", str(marker))
    monkeypatch.setenv("CHIPCOIN_TEST_ONLY_RUNTIME_MANIFEST", str(manifest))

    require_startable_network("mainnet-test-only")


def test_test_only_profile_rejects_missing_acknowledgement(monkeypatch, tmp_path) -> None:
    _install_startable_test_only_config(monkeypatch, tmp_path)

    with pytest.raises(PermissionError, match="explicit acknowledgement"):
        require_startable_network("mainnet-test-only")


def test_test_only_profile_rejects_missing_image_marker(monkeypatch, tmp_path) -> None:
    _, _, manifest = _install_startable_test_only_config(monkeypatch, tmp_path)
    monkeypatch.setenv("CHIPCOIN_ENABLE_TEST_ONLY_NETWORK", TEST_ONLY_ACKNOWLEDGEMENT)
    monkeypatch.setenv("CHIPCOIN_TEST_ONLY_MARKER_FILE", str(tmp_path / "missing-marker"))
    monkeypatch.setenv("CHIPCOIN_TEST_ONLY_RUNTIME_MANIFEST", str(manifest))

    with pytest.raises(PermissionError, match="marker is missing or invalid"):
        require_startable_network("mainnet-test-only")


def test_test_only_profile_rejects_missing_runtime_manifest(monkeypatch, tmp_path) -> None:
    _, marker, _ = _install_startable_test_only_config(monkeypatch, tmp_path)
    monkeypatch.setenv("CHIPCOIN_ENABLE_TEST_ONLY_NETWORK", TEST_ONLY_ACKNOWLEDGEMENT)
    monkeypatch.setenv("CHIPCOIN_TEST_ONLY_MARKER_FILE", str(marker))
    monkeypatch.setenv(
        "CHIPCOIN_TEST_ONLY_RUNTIME_MANIFEST",
        str(tmp_path / "missing-manifest.json"),
    )

    with pytest.raises(PermissionError, match="manifest is missing or invalid"):
        require_startable_network("mainnet-test-only")


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("chain_id", "chipcoin-mainnet-1"),
        ("p2p_magic_hex", "c0897c0d"),
        ("genesis_hash", "22" * 32),
        ("genesis_bits", MAINNET_PARAMS.genesis_bits),
        ("consensus_params_sha256", "00" * 32),
        ("public_mainnet_params_sha256", "00" * 32),
        ("test_only", False),
    ],
)
def test_test_only_startup_rejects_incoherent_runtime_manifest(
    monkeypatch,
    tmp_path,
    field,
    invalid_value,
) -> None:
    _, marker, manifest = _install_startable_test_only_config(monkeypatch, tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload[field] = invalid_value
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("CHIPCOIN_ENABLE_TEST_ONLY_NETWORK", TEST_ONLY_ACKNOWLEDGEMENT)
    monkeypatch.setenv("CHIPCOIN_TEST_ONLY_MARKER_FILE", str(marker))
    monkeypatch.setenv("CHIPCOIN_TEST_ONLY_RUNTIME_MANIFEST", str(manifest))

    with pytest.raises(PermissionError, match="does not match embedded identity"):
        require_startable_network("mainnet-test-only")


def test_network_magic_bytes_are_unique() -> None:
    magic_values = [config.magic for config in NETWORK_CONFIGS.values()]

    assert len(magic_values) == len(set(magic_values))
    assert TESTNET_CONFIG.magic not in {MAINNET_CONFIG.magic, DEVNET_CONFIG.magic}


def test_network_p2p_ports_are_unique() -> None:
    ports = [config.default_p2p_port for config in NETWORK_CONFIGS.values()]

    assert len(ports) == len(set(ports))
    assert TESTNET_CONFIG.default_p2p_port not in {
        MAINNET_CONFIG.default_p2p_port,
        DEVNET_CONFIG.default_p2p_port,
    }


def test_resolve_data_path_uses_testnet_default_database() -> None:
    assert resolve_data_path(Path("chipcoin.sqlite3"), "testnet") == Path(
        "chipcoin-testnet.sqlite3"
    )
    assert resolve_data_path(Path("/tmp/custom.sqlite3"), "testnet") == Path("/tmp/custom.sqlite3")


def test_node_service_initializes_empty_testnet_chain(tmp_path) -> None:
    service = NodeService.open_sqlite(tmp_path / "node.sqlite3", network="testnet")

    status = service.status()
    supply = service.supply_snapshot()

    assert service.network == "testnet"
    assert service.params is TESTNET_PARAMS
    assert service.chain_tip() is None
    assert status["network"] == "testnet"
    assert status["height"] is None
    assert status["network_magic_hex"] == TESTNET_CONFIG.magic.hex()
    assert status["current_bits"] == TESTNET_PARAMS.genesis_bits
    assert supply["network"] == "testnet"
    assert supply["height"] is None
