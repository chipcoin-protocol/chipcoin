from pathlib import Path

from chipcoin.config import (
    DEVNET_CONFIG,
    MAINNET_CONFIG,
    NETWORK_CONFIGS,
    TESTNET_CONFIG,
    get_network_config,
    resolve_data_path,
)
from chipcoin.consensus.params import DEVNET_PARAMS, MAINNET_PARAMS, TESTNET_PARAMS
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
