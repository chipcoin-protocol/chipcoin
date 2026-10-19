"""Shared configuration entrypoints for node and service bootstrap."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import os

from .consensus.genesis import (
    CANONICAL_GENESIS_HASH,
    TEST_ONLY_GENESIS_HASH,
    TEST_ONLY_GENESIS_TIMESTAMP,
    GenesisNotFinalizedError,
)
from .consensus.network_identity import (
    DEVNET_CHAIN_ID,
    MAINNET_TEST_ONLY_CHAIN_ID,
    MAINNET_TEST_ONLY_P2P_MAGIC,
    PUBLIC_MAINNET_CHAIN_ID,
    PUBLIC_MAINNET_P2P_MAGIC,
    TESTNET_CHAIN_ID,
)
from .consensus.params import (
    ConsensusParams,
    DEVNET_PARAMS,
    MAINNET_PARAMS,
    MAINNET_TEST_ONLY_PARAMS,
    TESTNET_PARAMS,
)


@dataclass(frozen=True)
class NetworkConfig:
    """Runtime configuration for a specific Chipcoin network."""

    name: str
    magic: bytes
    default_p2p_port: int
    data_dir: Path
    default_data_file: str
    params: ConsensusParams
    chain_id: str
    canonical_genesis_hash: str | None = None
    canonical_genesis_timestamp: int | None = None
    genesis_finalized: bool = False
    bootstrap_seeds: tuple[str, ...] = ()


DEFAULT_NETWORK = "mainnet"

MAINNET_CONFIG = NetworkConfig(
    name="mainnet",
    magic=PUBLIC_MAINNET_P2P_MAGIC,
    default_p2p_port=8333,
    data_dir=Path("."),
    default_data_file="chipcoin.sqlite3",
    params=MAINNET_PARAMS,
    chain_id=PUBLIC_MAINNET_CHAIN_ID,
    canonical_genesis_hash=CANONICAL_GENESIS_HASH,
    genesis_finalized=CANONICAL_GENESIS_HASH is not None,
)

MAINNET_TEST_ONLY_CONFIG = NetworkConfig(
    name="mainnet-test-only",
    magic=MAINNET_TEST_ONLY_P2P_MAGIC,
    default_p2p_port=38333,
    data_dir=Path("."),
    default_data_file="chipcoin-mainnet-test-only.sqlite3",
    params=MAINNET_TEST_ONLY_PARAMS,
    chain_id=MAINNET_TEST_ONLY_CHAIN_ID,
    canonical_genesis_hash=TEST_ONLY_GENESIS_HASH,
    canonical_genesis_timestamp=TEST_ONLY_GENESIS_TIMESTAMP,
    genesis_finalized=TEST_ONLY_GENESIS_HASH is not None,
)

DEVNET_CONFIG = NetworkConfig(
    name="devnet",
    magic=bytes.fromhex("FAC3B6DA"),
    default_p2p_port=18444,
    data_dir=Path("."),
    default_data_file="chipcoin-devnet.sqlite3",
    params=DEVNET_PARAMS,
    chain_id=DEVNET_CHAIN_ID,
)

TESTNET_CONFIG = NetworkConfig(
    name="testnet",
    magic=bytes.fromhex("FAB4C0DE"),
    default_p2p_port=28444,
    data_dir=Path("."),
    default_data_file="chipcoin-testnet.sqlite3",
    params=TESTNET_PARAMS,
    chain_id=TESTNET_CHAIN_ID,
)

NETWORK_CONFIGS = {
    MAINNET_CONFIG.name: MAINNET_CONFIG,
    MAINNET_TEST_ONLY_CONFIG.name: MAINNET_TEST_ONLY_CONFIG,
    DEVNET_CONFIG.name: DEVNET_CONFIG,
    TESTNET_CONFIG.name: TESTNET_CONFIG,
}


def get_network_config(name: str) -> NetworkConfig:
    """Return the runtime config for a named network."""

    try:
        return NETWORK_CONFIGS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported network: {name}") from exc


def require_finalized_public_mainnet(name: str) -> None:
    """Prevent production startup until the canonical genesis is embedded."""

    config = get_network_config(name)
    if name == "mainnet" and (
        not config.genesis_finalized or config.canonical_genesis_hash is None
    ):
        raise GenesisNotFinalizedError(
            "public mainnet genesis is pending founder-approved timestamp and canonical finalization"
        )


TEST_ONLY_ACKNOWLEDGEMENT = "I_ACKNOWLEDGE_THIS_IS_NOT_PUBLIC_MAINNET"
TEST_ONLY_MARKER_TEXT = "TEST-ONLY PUBLIC MAINNET REHEARSAL IMAGE - NEVER DEPLOY"
TEST_ONLY_RUNTIME_MANIFEST_SCHEMA = 1
TEST_ONLY_RUNTIME_MANIFEST_PATH = Path(
    "/usr/share/chipcoin/test-only-runtime-manifest.json"
)


def consensus_params_fingerprint(params: ConsensusParams) -> str:
    """Return a stable digest covering every consensus parameter."""

    payload = json.dumps(
        asdict(params),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def expected_test_only_runtime_manifest(config: NetworkConfig) -> dict[str, object]:
    """Return the exact runtime identity embedded in a TEST-ONLY image."""

    return {
        "schema_version": TEST_ONLY_RUNTIME_MANIFEST_SCHEMA,
        "test_only": True,
        "network": config.name,
        "chain_id": config.chain_id,
        "p2p_magic_hex": config.magic.hex(),
        "genesis_hash": config.canonical_genesis_hash,
        "genesis_timestamp": config.canonical_genesis_timestamp,
        "genesis_bits": config.params.genesis_bits,
        "consensus_params_sha256": consensus_params_fingerprint(config.params),
        "public_mainnet_params_sha256": consensus_params_fingerprint(MAINNET_PARAMS),
    }


def require_startable_network(name: str) -> None:
    """Fail closed for pending public genesis and guarded TEST-ONLY startup."""

    require_finalized_public_mainnet(name)
    if name != MAINNET_TEST_ONLY_CONFIG.name:
        return
    config = get_network_config(name)
    if (
        not config.genesis_finalized
        or config.canonical_genesis_hash is None
        or config.canonical_genesis_timestamp is None
    ):
        raise GenesisNotFinalizedError("TEST-ONLY mainnet rehearsal genesis is not embedded")
    if os.environ.get("CHIPCOIN_ENABLE_TEST_ONLY_NETWORK") != TEST_ONLY_ACKNOWLEDGEMENT:
        raise PermissionError("TEST-ONLY network requires explicit acknowledgement")
    marker = Path(os.environ.get("CHIPCOIN_TEST_ONLY_MARKER_FILE", "/TEST-ONLY-NOT-PUBLIC"))
    if not marker.is_file() or marker.read_text(encoding="ascii").strip() != TEST_ONLY_MARKER_TEXT:
        raise PermissionError("TEST-ONLY network image marker is missing or invalid")
    manifest_path = Path(
        os.environ.get(
            "CHIPCOIN_TEST_ONLY_RUNTIME_MANIFEST",
            str(TEST_ONLY_RUNTIME_MANIFEST_PATH),
        )
    )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PermissionError("TEST-ONLY runtime manifest is missing or invalid") from exc
    expected = expected_test_only_runtime_manifest(config)
    if not isinstance(manifest, dict) or manifest != expected:
        raise PermissionError("TEST-ONLY runtime manifest does not match embedded identity")


def resolve_data_path(raw_path: str | Path, network: str) -> Path:
    """Return a network-aware SQLite path while preserving explicit paths."""

    path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
    config = get_network_config(network)
    if path.name == MAINNET_CONFIG.default_data_file and network != DEFAULT_NETWORK:
        return path.with_name(config.default_data_file)
    return path
