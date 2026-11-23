#!/usr/bin/env python3
"""Phase 1 setup wizard for the public Chipcoin runtime."""

from __future__ import annotations

import getpass
import hashlib
import ipaddress
import json
import os
import re
import shlex
import socket
import shutil
import subprocess
import sys
import time
import tempfile
from pathlib import Path
from typing import NamedTuple
from urllib import error, request
from urllib.parse import parse_qsl, urlsplit

IN_SETUP_CONTAINER = os.environ.get("CHIPCOIN_SETUP_IN_CONTAINER") == "1"
REPO_ROOT = Path(os.environ.get("CHIPCOIN_SETUP_REPO_ROOT", Path(__file__).resolve().parents[2]))
SRC_ROOT = REPO_ROOT / "src"
if not IN_SETUP_CONTAINER and str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from chipcoin.config import MAINNET_CONFIG, get_network_config  # noqa: E402
from chipcoin.consensus.genesis import GENESIS_MESSAGE, canonical_genesis_block  # noqa: E402


ENV_PATH = REPO_ROOT / ".env"
ENV_EXAMPLE_PATH = REPO_ROOT / "config" / "env" / ".env.example"
SETUP_STORAGE_BASE = os.environ.get("CHIPCOIN_SETUP_STORAGE_BASE", "").strip()
if SETUP_STORAGE_BASE and not Path(SETUP_STORAGE_BASE).is_absolute():
    raise SystemExit("CHIPCOIN_SETUP_STORAGE_BASE must be absolute.")
RUNTIME_ROOT = Path("/var/lib/chipcoin")
MAINNET_RUNTIME_ROOT = Path(SETUP_STORAGE_BASE) / "mainnet" if SETUP_STORAGE_BASE else Path("/var/lib/chipcoin-mainnet-official")
NODE_DATA_PATH = str(RUNTIME_ROOT / "data" / "node-devnet.sqlite3")
NODE_SNAPSHOT_PATH = str(RUNTIME_ROOT / "data" / "node-devnet.snapshot")
TESTNET_NODE_DATA_PATH = str(RUNTIME_ROOT / "data" / "node-testnet.sqlite3")
TESTNET_NODE_SNAPSHOT_PATH = str(RUNTIME_ROOT / "data" / "node-testnet.snapshot")
MAINNET_NODE_DATA_PATH = str(MAINNET_RUNTIME_ROOT / "data" / "node.sqlite3")
MAINNET_NODE_SNAPSHOT_PATH = str(MAINNET_RUNTIME_ROOT / "data" / "node-mainnet.snapshot")
WALLET_PATH = str(RUNTIME_ROOT / "wallets" / "chipcoin-wallet.json")
REWARD_WALLET_PATH = str(RUNTIME_ROOT / "wallets" / "reward-node-wallet.json")
PUBLIC_DEVNET_NODE_ENDPOINT = "https://api.chipcoinprotocol.com"
PUBLIC_DEVNET_BOOTSTRAP_PEER = "chipcoinprotocol.com:18444"
PUBLIC_DEVNET_BOOTSTRAP_URL = "https://bootstrap.chipcoinprotocol.com"
PUBLIC_DEVNET_EXPLORER_URL = "https://explorer.chipcoinprotocol.com"
PUBLIC_DEVNET_SNAPSHOT_MANIFEST_URL = "https://chipcoinprotocol.com/downloads/snapshots/devnet/latest.manifest.json"
PUBLIC_TESTNET_WALLET_API_ENDPOINT = "https://testnet-api.chipcoinprotocol.com"
PUBLIC_TESTNET_BOOTSTRAP_PEER = "chipcoinprotocol.com:28444"
PUBLIC_TESTNET_BOOTSTRAP_URL = "https://bootstrap.chipcoinprotocol.com"
PUBLIC_TESTNET_EXPLORER_URL = "https://explorer.chipcoinprotocol.com/api/testnet"
PUBLIC_TESTNET_SNAPSHOT_MANIFEST_URL = "https://chipcoinprotocol.com/downloads/snapshots/testnet/latest.manifest.json"
PUBLIC_MAINNET_BOOTSTRAP_URL = "https://mainnet-bootstrap.chipcoinprotocol.com"
PUBLIC_MAINNET_SNAPSHOT_MANIFEST_URL = "https://chipcoinprotocol.com/downloads/snapshots/mainnet/latest.manifest.json"
MAINNET_SNAPSHOT_SIGNER_KEY_HEX = "d3cb77ba741ec9f71ac2aca4f49878d428ff588c46200dbeede225baa451b031"
MAINNET_SNAPSHOT_TRUSTED_KEYS_FILE = str(MAINNET_RUNTIME_ROOT / ("runtime" if SETUP_STORAGE_BASE else "snapshots") / "trusted-signers.txt")
TESTNET_LOCAL_NODE_ENDPOINT = "http://127.0.0.1:28081"
PUBLIC_MAINNET_WALLET_API_ENDPOINT = "https://mainnet-api.chipcoinprotocol.com"
MAINNET_LOCAL_NODE_ENDPOINT = "http://127.0.0.1:8080"
PUBLIC_IP_DETECT_URLS = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
)
SNAPSHOT_STALE_WARNING_SECONDS = 6 * 60 * 60
SNAPSHOT_LARGE_DELTA_WARNING_SECONDS = 24 * 60 * 60
COMPOSE_FILE_PATH = REPO_ROOT / "docker-compose.yml"
DEFAULTS = {
    "CHIPCOIN_NETWORK": "mainnet",
    "COMPOSE_PROJECT_NAME": "chipcoin-mainnet",
    "CHIPCOIN_RUNTIME_DIR": str(MAINNET_RUNTIME_ROOT),
    "CHIPCOIN_RUNTIME_HOST_DIR": str(MAINNET_RUNTIME_ROOT),
    "CHIPCOIN_RUNTIME_UID": "",
    "CHIPCOIN_RUNTIME_COMPAT_HOST_DIR": "",
    "DEFAULT_NODE_ENDPOINT": PUBLIC_MAINNET_WALLET_API_ENDPOINT,
    "DEFAULT_BOOTSTRAP_PEER": "",
    "DEFAULT_EXPLORER_URL": "https://explorer.chipcoinprotocol.com/api/mainnet",
    "NODE_DATA_PATH": MAINNET_NODE_DATA_PATH,
    "NODE_BOOTSTRAP_MODE": "full",
    "NODE_SNAPSHOT_MANIFEST_URLS": "",
    "NODE_SNAPSHOT_FILE": MAINNET_NODE_SNAPSHOT_PATH,
    "NODE_SNAPSHOT_TRUST_MODE": "enforce",
    "NODE_SNAPSHOT_TRUSTED_KEYS_FILE": "",
    "NODE_SNAPSHOT_SELECTED_URL": "",
    "NODE_SNAPSHOT_SELECTED_HEIGHT": "",
    "NODE_SNAPSHOT_SELECTED_HASH": "",
    "NODE_LOG_LEVEL": "INFO",
    "NODE_P2P_BIND_PORT": "8333",
    "NODE_P2P_PUBLISH_HOST": "127.0.0.1",
    "NODE_HTTP_BIND_PORT": "8080",
    "NODE_HTTP_PUBLISH_PORT": "8080",
    "CHIPCOIN_HTTP_ALLOWED_ORIGINS": "",
    "MINER_LOG_LEVEL": "INFO",
    "MINER_WALLET_FILE": str(MAINNET_RUNTIME_ROOT / "keys" / "miner-wallet.json"),
    "REWARD_NODE_AUTO_NODE_ID": "",
    "REWARD_NODE_AUTO_OWNER_WALLET_FILE": "",
    "REWARD_NODE_AUTO_ATTEST_WALLET_FILE": "",
    "REWARD_NODE_OWNER_WALLET_SOURCE": "",
    "REWARD_NODE_ATTEST_WALLET_SOURCE": "",
    "REWARD_NODE_AUTO_DECLARED_HOST": "",
    "REWARD_NODE_AUTO_DECLARED_PORT": "",
    "REWARD_NODE_AUTO_RENEW_ENABLED": "true",
    "REWARD_NODE_AUTO_ATTEST_ENABLED": "true",
    "REWARD_NODE_AUTO_POLL_INTERVAL_SECONDS": "5.0",
    "MINING_MIN_INTERVAL_SECONDS": "10.0",
    "MINING_NODE_URLS": "http://node:8080",
    "MINING_MAX_ACCEPTED_BLOCKS": "",
    "MINING_MINER_ID": "",
    "MINING_POLLING_INTERVAL_SECONDS": "2.0",
    "MINING_REQUEST_TIMEOUT_SECONDS": "10.0",
    "MINING_NONCE_BATCH_SIZE": "50000",
    "MINING_WORKER_COUNT": "1",
    "MINING_TEMPLATE_REFRESH_SKEW_SECONDS": "1",
    "BROWSER_WALLET_DEFAULT_NODE_ENDPOINT": PUBLIC_MAINNET_WALLET_API_ENDPOINT,
    "NODE_DIRECT_PEERS": "",
    "NODE_DIRECT_PEER": "",
    "NODE_BOOTSTRAP_URL": PUBLIC_MAINNET_BOOTSTRAP_URL,
    "NODE_PUBLIC_HOST": "",
    "NODE_PUBLIC_P2P_PORT": "8333",
    "DIRECT_PEERS": "",
    "DIRECT_PEER": "",
    "BOOTSTRAP_URL": "",
    "BOOTSTRAP_PEER_LIMIT": "4",
    "BOOTSTRAP_ANNOUNCE_ENABLED": "false",
    "BOOTSTRAP_REFRESH_INTERVAL_SECONDS": "60",
    "INITIAL_SYNC_CONSERVATIVE_DEFAULTS": "true",
}


class SnapshotManifestEntry(NamedTuple):
    """One downloadable snapshot advertised by a manifest."""

    manifest_url: str
    network: str
    snapshot_url: str
    format_version: int
    snapshot_height: int
    snapshot_block_hash: str
    created_at: int
    checksum_sha256: str
    signer_pubkeys: tuple[str, ...] = ()


_TRACK_NEW_FILES = False
_NEW_FILES: list[tuple[Path, int]] = []


def _remember_new_file(path: Path) -> None:
    if _TRACK_NEW_FILES:
        _NEW_FILES.append((path, path.stat().st_ino))


def main() -> int:
    """Roll back newly written setup artifacts if a step fails."""
    global _TRACK_NEW_FILES
    _TRACK_NEW_FILES = True
    _NEW_FILES.clear()
    completed = False
    try:
        result = _run_wizard()
        completed = True
        return result
    finally:
        _TRACK_NEW_FILES = False
        if not completed:
            for path, inode in reversed(_NEW_FILES):
                try:
                    if path.stat().st_ino == inode:
                        path.unlink()
                except FileNotFoundError:
                    pass
        _NEW_FILES.clear()


def _require_verified_mainnet_core() -> None:
    """Fail closed if this source tree is not the verified Mainnet Core."""
    if (MAINNET_CONFIG.chain_id != "chipcoin-mainnet-1"
        or MAINNET_CONFIG.params.genesis_bits != 0x1E0537E7
        or MAINNET_CONFIG.canonical_genesis_hash != "00000238ef41c47992581c18fad544b4e24ecf1e79e7ffed629a215def4a337f"
        or canonical_genesis_block().block_hash() != MAINNET_CONFIG.canonical_genesis_hash
        or GENESIS_MESSAGE != "Die Welt ist alles, was der Fall ist."):
        _die("Mainnet Core identity mismatch: expected frozen Core 0.1.2, Wittgenstein genesis and bits 0x1e0537e7.")


def _snapshot_metadata_path(node_data_path: Path) -> Path:
    """Return the audit metadata file stored next to the node DB."""

    return node_data_path.with_suffix(node_data_path.suffix + ".snapshot.meta.json")


def _run_wizard() -> int:
    print("Chipcoin Setup Wizard")
    _check_prerequisites()
    setup_mode = _ask_choice(
        "Select setup mode",
        {
            "quick": "Quick start (use Mainnet defaults)",
            "custom": "Custom configuration",
            "local": "Local/self-hosted",
        },
        "quick",
    )
    selected_role = _ask_choice(
        "What do you want to run?",
        {
            "node": "Full node",
            "miner": "Miner",
            "reward-node": "Reward node",
            "both": "Full node + miner",
        },
        "node",
    )
    role = "node" if selected_role == "reward-node" else selected_role
    network = _ask_choice(
        "Which network do you want to use?",
        {
            "mainnet": "Mainnet (ML-DSA-44 only)",
            "devnet": "Devnet",
            "testnet": "Public testnet candidate",
        },
        "mainnet",
    )
    if network == "mainnet":
        _require_verified_mainnet_core()
    if SETUP_STORAGE_BASE:
        _prepare_storage_root(Path(SETUP_STORAGE_BASE) / network)
    env_path = _ask_env_path(network)
    runtime_mode = _ask_choice("How should services run?", {"foreground": "Foreground", "background": "Background"}, "foreground")
    _print_public_reachability_note(network=network)
    bootstrap_notes: list[str] = []

    miner_wallet_path: Path | None = None
    miner_wallet_address: str | None = None
    reward_wallet_path: Path | None = None
    reward_wallet_address: str | None = None
    reward_wallet_public_key_hex: str | None = None
    reward_node_enabled = False
    if role in {"miner", "both"}:
        wallet_mode = _ask_choice(
            "How should the miner wallet be handled?",
            {"generate": "Generate new wallet", "import": "Import existing private key"},
            "generate",
        )
        miner_wallet_path = _wallet_path(network, "miner-wallet.json")
        miner_wallet_address, _miner_wallet_public_key_hex = _handle_wallet(wallet_mode, miner_wallet_path, network=network)

    env_values = dict(DEFAULTS)
    _apply_network_defaults(env_values, network)
    _apply_setup_mode(env_values, setup_mode, role, network=network)
    if role in {"miner", "both"}:
        _configure_miner_workers(env_values)
    if role in {"node", "both"}:
        _configure_node_discovery(env_values, setup_mode=setup_mode)
        _configure_node_bootstrap(env_values, setup_mode=setup_mode)
        reward_node_enabled = selected_role == "reward-node"
        if not reward_node_enabled:
            reward_node_enabled = _ask_choice(
                "How should this node participate?",
                {
                    "passive": "Passive full node only",
                    "reward": "Reward node that registers for protocol rewards",
                },
                "passive",
            ) == "reward"
        if reward_node_enabled:
            reward_wallet_path, reward_wallet_address, reward_wallet_public_key_hex = _configure_reward_node(
                env_values,
                setup_mode=setup_mode,
                network=network,
            )
    _preflight_validate(env_values, role=role)
    existing_database = Path(env_values["NODE_DATA_PATH"]).exists() if role in {"node", "both"} else False
    _prepare_runtime_files(env_values, role=role)
    if role in {"node", "both"}:
        if existing_database and env_values["NODE_BOOTSTRAP_MODE"] != "full":
            _die("Existing node database found. Snapshot import would replace it; select full bootstrap or use a new storage root.")
        bootstrap_notes = _prepare_node_bootstrap(env_values, network=network)

    _write_env(env_values, env_path)
    _write_setup_result(env_path, role, network)
    _print_success(
        selected_role,
        network,
        runtime_mode,
        env_path,
        miner_wallet_path,
        miner_wallet_address,
        reward_wallet_path,
        reward_wallet_address,
        reward_wallet_public_key_hex,
        reward_node_enabled,
        setup_mode,
        env_values,
        bootstrap_notes=bootstrap_notes,
    )
    return 0


def _check_prerequisites() -> None:
    if not IN_SETUP_CONTAINER and shutil.which("docker") is None:
        _die("Docker is not installed or not available in PATH.")
    if not IN_SETUP_CONTAINER:
        try:
            subprocess.run(["docker", "compose", "version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.CalledProcessError):
            _die("Docker Compose is not available.")
    if not ENV_EXAMPLE_PATH.exists():
        _die(f"Missing environment template: {ENV_EXAMPLE_PATH}")


def _ask_choice(prompt: str, options: dict[str, str], default: str) -> str:
    keys = list(options)
    while True:
        print(prompt)
        for key in keys:
            suffix = " (default)" if key == default else ""
            print(f"  - {key}: {options[key]}{suffix}")
        answer = input("> ").strip().lower()
        if not answer:
            return default
        if answer in options:
            return answer
        print("Invalid selection. Please choose one of the listed options.")


def _ask_env_path(network: str) -> Path:
    default_names = {
        "testnet": ".env",
        "devnet": ".env.devnet",
        "mainnet": ".env.mainnet",
    }
    if network not in default_names:
        _die("Unsupported network for environment file selection.")
    default_path = (Path(SETUP_STORAGE_BASE) / network / "config" / ".env") if SETUP_STORAGE_BASE else REPO_ROOT / default_names[network]
    answer = input(f"Where should the environment file be written? [{default_path}]: ").strip()
    path = Path(answer) if answer else default_path
    if not path.is_absolute():
        path = REPO_ROOT / path
    if IN_SETUP_CONTAINER and not path.is_relative_to(Path(SETUP_STORAGE_BASE) / network):
        _die("Choose an environment file inside the selected persistent network storage directory.")
    return path


def _prepare_storage_root(root: Path) -> None:
    if root.is_symlink():
        _die(f"Storage directory must not be a symbolic link: {root}")
    for child in (root, root / "wallets", root / "wallets" / "miner", root / "wallets" / "reward", root / "chain", root / "runtime", root / "config"):
        if child.is_symlink():
            _die(f"Storage directory must not be a symbolic link: {child}")
        existed = child.exists()
        child.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not child.is_dir() or not os.access(child, os.W_OK):
            _die(f"Storage directory is not writable: {child}")
        if existed:
            if child.stat().st_mode & 0o077:
                _die(f"Storage directory permissions are too broad: {child}. Restrict them explicitly before setup.")
        else:
            child.chmod(0o700)


def _write_setup_result(env_path: Path, role: str, network: str) -> None:
    if not IN_SETUP_CONTAINER:
        return
    result_path = Path(os.environ["CHIPCOIN_SETUP_RESULT_PATH"])
    _atomic_new_file(result_path, (str(env_path) + "\n").encode())


def _parse_peer_list(value: str) -> list[str]:
    peers: list[str] = []
    for candidate in re.split(r"[\s,]+", value.strip()):
        if not candidate:
            continue
        host, sep, port = candidate.rpartition(":")
        if not sep or not host or "@" in host or not port.isdigit():
            raise ValueError("Expected host:port entries separated by commas or spaces.")
        if candidate not in peers:
            peers.append(candidate)
    return peers


def _ask_direct_peers(prompt: str, default: str) -> str:
    while True:
        answer = input(f"{prompt} [{default}]: ").strip()
        if not answer:
            return default
        try:
            peers = _parse_peer_list(answer)
        except ValueError as exc:
            print(f"Invalid peer format. {exc}")
            continue
        if peers:
            return ",".join(peers)
        print("Enter at least one host:port entry or leave the field empty.")


def _ask_http_url(prompt: str, default: str) -> str:
    while True:
        answer = input(f"{prompt} [{default}]: ").strip()
        if not answer:
            return default
        if answer.startswith(("http://", "https://")) and not _url_contains_credentials(answer):
            return answer
        if answer.startswith(("http://", "https://")):
            print("URLs containing credentials are not accepted.")
            continue
        print("Invalid URL. Expected http://host or https://host.")


def _ask_required_mining_url() -> str:
    while True:
        answer = input("Enter a mining node API URL reachable from the miner container (http(s)://host:port): ").strip()
        if answer.startswith(("http://", "https://")) and not _url_contains_credentials(answer):
            parsed = urlsplit(answer)
            if parsed.hostname not in {"localhost", "127.0.0.1", "::1", "node"}:
                return answer
        print("Use a reachable node API URL. Container localhost and 'node' are unavailable for a miner-only installation.")


def _ask_optional_http_urls(prompt: str, default: str) -> str:
    while True:
        answer = input(f"{prompt} [{default}]: ").strip()
        if not answer:
            return default
        try:
            urls = _parse_http_urls(answer)
        except ValueError as exc:
            print(f"Invalid URL list. {exc}")
            continue
        if urls:
            return ",".join(urls)
        print("Enter at least one http:// or https:// URL or leave the field empty.")


def _ask_host(prompt: str, default: str) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        answer = input(f"{prompt}{suffix}: ").strip()
        if not answer:
            if default:
                return default
            print("Host must not be empty.")
            continue
        if _looks_public_host(answer):
            return answer
        print("Invalid public host. Use a real public DNS name or public IP address, not localhost or a private address.")


def _ask_nonempty_host(prompt: str, default: str) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        answer = input(f"{prompt}{suffix}: ").strip()
        if not answer:
            if default:
                return default
            print("Host must not be empty.")
            continue
        if any(character.isspace() for character in answer):
            print("Host must not contain whitespace.")
            continue
        return answer


def _ask_port(prompt: str, default: str) -> str:
    while True:
        answer = input(f"{prompt} [{default}]: ").strip()
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= 65535:
            return answer
        print("Invalid port. Expected an integer between 1 and 65535.")


def _detect_cpu_core_count() -> int:
    """Return the best local CPU core count hint for miner worker selection."""

    detected = os.cpu_count()
    if detected is None or detected < 1:
        return 1
    return detected


def _ask_miner_worker_count(*, detected_cores: int, default: str = "1") -> str:
    """Ask how many local mining worker processes should be used."""

    max_workers = max(1, detected_cores)
    while True:
        answer = input(
            "How many CPU cores should the miner use? "
            f"Detected {max_workers}. [{default}]: "
        ).strip()
        candidate = default if not answer else answer
        if candidate.isdigit() and 1 <= int(candidate) <= max_workers:
            return str(int(candidate))
        print(f"Invalid worker count. Enter an integer between 1 and {max_workers}.")


def _configure_miner_workers(env_values: dict[str, str]) -> None:
    """Configure local miner process parallelism."""

    env_values["MINING_WORKER_COUNT"] = _ask_miner_worker_count(
        detected_cores=_detect_cpu_core_count(),
        default=env_values.get("MINING_WORKER_COUNT", "1"),
    )


def _looks_public_host(host: str) -> bool:
    candidate = host.strip()
    if not candidate or any(character.isspace() for character in candidate):
        return False
    lowered = candidate.lower()
    if lowered == "localhost" or lowered.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return True
    return address.is_global


def _default_public_host(env_values: dict[str, str]) -> str:
    """Return only an explicitly known public host for this local install."""

    configured = env_values.get("NODE_PUBLIC_HOST", "").strip()
    if configured and _looks_public_host(configured):
        return configured
    detected = _detect_public_ip()
    if detected:
        return detected
    return ""


def _detect_public_ip() -> str:
    """Return one best-effort detected public IP address for this host."""

    for url in PUBLIC_IP_DETECT_URLS:
        try:
            with request.urlopen(url, timeout=3) as response:
                candidate = response.read().decode("utf-8").strip()
        except Exception:  # noqa: BLE001
            continue
        if _looks_public_host(candidate):
            return candidate
    return ""


def _ask_optional_peer(prompt: str, default: str) -> str:
    while True:
        answer = input(f"{prompt} [{default}]: ").strip()
        if not answer:
            return default
        host, sep, port = answer.rpartition(":")
        if sep and host and "@" not in host and port.isdigit():
            return answer
        print("Invalid peer format. Expected host:port.")


def _parse_http_urls(value: str) -> list[str]:
    urls: list[str] = []
    for candidate in re.split(r"[\s,]+", value.strip()):
        if not candidate:
            continue
        if not candidate.startswith(("http://", "https://")):
            raise ValueError("expected http:// or https:// URLs separated by commas or spaces")
        if _url_contains_credentials(candidate):
            raise ValueError("URLs containing credentials are not accepted")
        normalized = candidate.rstrip("/")
        if normalized not in urls:
            urls.append(normalized)
    return urls


def _url_contains_credentials(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return True
    sensitive_query_names = {"access_token", "api_key", "apikey", "auth", "authorization", "password", "secret", "token"}
    return bool(
        parsed.username
        or parsed.password
        or any(name.lower() in sensitive_query_names for name, _ in parse_qsl(parsed.query, keep_blank_values=True))
    )


def _should_offer_runtime_sudo(path: Path) -> bool:
    return path.is_absolute() and Path("/var/lib") in path.parents


def _ensure_runtime_parent(path: Path, label: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return
    except PermissionError as exc:
        if not _should_offer_runtime_sudo(path):
            _die(
                f"Cannot create {label.lower()} directory {path.parent}. "
                f"Original error: {exc}"
            )
        _prepare_runtime_with_sudo(path.parent, label, exc)


def _prepare_runtime_with_sudo(target_parent: Path, label: str, original_error: PermissionError) -> None:
    runtime_root = MAINNET_RUNTIME_ROOT if target_parent.is_relative_to(MAINNET_RUNTIME_ROOT) else RUNTIME_ROOT
    if runtime_root.exists():
        _die(f"Existing runtime directory is not writable: {runtime_root}. Refusing to change ownership of existing chain or wallet data.")
    print()
    print(
        f"{label} needs a writable runtime directory under {runtime_root}, "
        f"but the current user cannot create {target_parent}."
    )
    answer = input("Prepare the runtime directory with sudo now? [y/N]: ").strip().lower()
    if answer in {"y", "yes"}:
        user = getpass.getuser()
        group = _primary_group_name()
        mkdir_args = ["sudo", "install", "-d", "-m", "700", "-o", user, "-g", group,
                      str(runtime_root), str(runtime_root / "data"), str(runtime_root / "keys"),
                      str(runtime_root / "wallets"), str(runtime_root / "logs")]
        try:
            subprocess.run(mkdir_args, check=True)
            target_parent.mkdir(parents=True, exist_ok=True)
            return
        except (OSError, subprocess.CalledProcessError) as exc:
            _die(
                f"Failed to prepare runtime directory with sudo. "
                f"Tried: {' '.join(mkdir_args)}. "
                f"Original error: {original_error}. Sudo step error: {exc}"
            )
    _die(
        f"Cannot continue without a writable runtime directory for {label.lower()}. "
        f"Prepare a new isolated directory under {runtime_root} without changing ownership of existing data. "
        f"Original error: {original_error}"
    )


def _primary_group_name() -> str:
    try:
        import grp

        return grp.getgrgid(os.getgid()).gr_name
    except Exception:  # noqa: BLE001
        return getpass.getuser()


def _default_reward_node_id() -> str:
    raw = os.environ.get("CHIPCOIN_SETUP_HOST_NAME", socket.gethostname()).strip().lower()
    normalized = re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")
    if not normalized:
        normalized = "local"
    return f"reward-node-{normalized}"


def _ask_reward_node_id(default: str) -> str:
    while True:
        answer = input(f"Enter reward node id [{default}]: ").strip()
        if not answer:
            answer = default
        if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{1,127}", answer):
            return answer
        print("Invalid node id. Use 2-128 characters from letters, digits, dot, underscore, or dash.")


def _format_chipbits_as_chc(value: int) -> str:
    from chipcoin.consensus.economics import CHCBITS_PER_CHC

    major, minor = divmod(int(value), CHCBITS_PER_CHC)
    text = f"{major}.{minor:08d}".rstrip("0").rstrip(".")
    return text if text else "0"


def _reward_fee_guidance(network: str) -> tuple[str, str, str]:
    try:
        from chipcoin.consensus.economics import register_reward_node_fee_chipbits, renew_reward_node_fee_chipbits
    except ImportError:
        _die("Reward-node setup needs the host Python package. On Ubuntu install build-essential python3-dev python3-venv, then create a venv and run: .venv/bin/python -m pip install -e .")

    params = get_network_config(network).params
    register_fee = register_reward_node_fee_chipbits(registered_reward_node_count=0, params=params)
    renew_fee = renew_reward_node_fee_chipbits(registered_reward_node_count=0, params=params)
    suggested = register_fee + (2 * renew_fee)
    return (
        _format_chipbits_as_chc(register_fee),
        _format_chipbits_as_chc(renew_fee),
        _format_chipbits_as_chc(suggested),
    )


def _default_reward_registration_peer(env_values: dict[str, str]) -> str:
    if SETUP_STORAGE_BASE:
        # `compose run` has its own network namespace; loopback is not the running node.
        return f"node:{env_values.get('NODE_P2P_BIND_PORT', '18444')}"
    peers = [item.strip() for item in env_values.get("NODE_DIRECT_PEERS", "").split(",") if item.strip()]
    if peers:
        return peers[0]
    bootstrap_peer = env_values.get("DEFAULT_BOOTSTRAP_PEER", "").strip()
    if bootstrap_peer:
        return bootstrap_peer
    return f"127.0.0.1:{env_values.get('NODE_P2P_BIND_PORT', '18444')}"


def _configure_reward_node(env_values: dict[str, str], *, setup_mode: str, network: str = "testnet") -> tuple[Path, str, str]:
    reward_wallet_mode = _ask_choice(
        "How should the reward-node wallet be handled?",
        {"generate": "Generate new wallet", "import": "Import existing private key"},
        "generate",
    )
    reward_wallet_path = _wallet_path(network, "reward-owner-wallet.json")
    _prepare_wallet_path(reward_wallet_path)
    reward_wallet_address, reward_wallet_public_key_hex = _handle_wallet(reward_wallet_mode, reward_wallet_path, network=network)
    env_values["REWARD_NODE_AUTO_NODE_ID"] = _ask_reward_node_id(_default_reward_node_id())
    default_declared_host = (
        env_values.get("NODE_PUBLIC_HOST", "").strip()
        or (_default_public_host(env_values) if setup_mode != "local" else "127.0.0.1")
    )
    env_values["REWARD_NODE_AUTO_DECLARED_HOST"] = _ask_nonempty_host(
        "Enter the reward-node declared host",
        default_declared_host,
    )
    env_values["REWARD_NODE_AUTO_DECLARED_PORT"] = _ask_port(
        "Enter the reward-node declared port",
        env_values.get("NODE_PUBLIC_P2P_PORT", "") or env_values.get("NODE_P2P_BIND_PORT", "18444"),
    )
    env_values["REWARD_NODE_OWNER_WALLET_SOURCE"] = str(reward_wallet_path)
    env_values["REWARD_NODE_ATTEST_WALLET_SOURCE"] = str(reward_wallet_path)
    env_values["REWARD_NODE_AUTO_OWNER_WALLET_FILE"] = "/runtime/reward-owner-wallet.json"
    env_values["REWARD_NODE_AUTO_ATTEST_WALLET_FILE"] = "/runtime/reward-attest-wallet.json"
    env_values["REWARD_NODE_AUTO_RENEW_ENABLED"] = "true"
    env_values["REWARD_NODE_AUTO_ATTEST_ENABLED"] = "true"
    return reward_wallet_path, reward_wallet_address, reward_wallet_public_key_hex


def _apply_network_defaults(env_values: dict[str, str], network: str) -> None:
    """Apply network-specific local paths and safe endpoint defaults."""

    env_values["CHIPCOIN_NETWORK"] = network
    env_values["MINER_WALLET_FILE"] = str(_wallet_path(network, "miner-wallet.json"))
    if network == "mainnet":
        env_values["COMPOSE_PROJECT_NAME"] = "chipcoin-mainnet"
        env_values["CHIPCOIN_RUNTIME_DIR"] = str(MAINNET_RUNTIME_ROOT)
        env_values["CHIPCOIN_RUNTIME_HOST_DIR"] = str(MAINNET_RUNTIME_ROOT)
        env_values["NODE_DATA_PATH"] = MAINNET_NODE_DATA_PATH
        env_values["NODE_SNAPSHOT_FILE"] = MAINNET_NODE_SNAPSHOT_PATH
        env_values["NODE_BOOTSTRAP_MODE"] = "full"
        env_values["NODE_SNAPSHOT_MANIFEST_URLS"] = PUBLIC_MAINNET_SNAPSHOT_MANIFEST_URL
        env_values["NODE_SNAPSHOT_TRUST_MODE"] = "enforce"
        env_values["NODE_SNAPSHOT_TRUSTED_KEYS_FILE"] = MAINNET_SNAPSHOT_TRUSTED_KEYS_FILE
        env_values["NODE_P2P_BIND_PORT"] = "8333"
        env_values["NODE_P2P_PUBLISH_HOST"] = "127.0.0.1"
        env_values["NODE_PUBLIC_P2P_PORT"] = "8333"
        env_values["NODE_HTTP_BIND_PORT"] = "8080"
        env_values["NODE_HTTP_PUBLISH_PORT"] = "8080"
        env_values["MINING_NODE_URLS"] = "http://node:8080"
        env_values["DEFAULT_BOOTSTRAP_PEER"] = ""
        env_values["NODE_BOOTSTRAP_URL"] = PUBLIC_MAINNET_BOOTSTRAP_URL
        env_values["DEFAULT_NODE_ENDPOINT"] = PUBLIC_MAINNET_WALLET_API_ENDPOINT
        env_values["DEFAULT_EXPLORER_URL"] = "https://explorer.chipcoinprotocol.com/api/mainnet"
        env_values["BROWSER_WALLET_DEFAULT_NODE_ENDPOINT"] = PUBLIC_MAINNET_WALLET_API_ENDPOINT
        env_values["MINING_MIN_INTERVAL_SECONDS"] = "10.0"
        env_values["MINING_NONCE_BATCH_SIZE"] = "50000"
        _apply_new_storage(env_values, network)
        return
    if network == "devnet":
        env_values["COMPOSE_PROJECT_NAME"] = "chipcoin-devnet"
        env_values["CHIPCOIN_RUNTIME_DIR"] = str(RUNTIME_ROOT)
        env_values["CHIPCOIN_RUNTIME_HOST_DIR"] = str(RUNTIME_ROOT)
        env_values["NODE_DATA_PATH"] = NODE_DATA_PATH
        env_values["NODE_SNAPSHOT_FILE"] = NODE_SNAPSHOT_PATH
        env_values["NODE_BOOTSTRAP_MODE"] = "auto"
        env_values["NODE_SNAPSHOT_TRUST_MODE"] = "warn"
        env_values["NODE_P2P_BIND_PORT"] = "18444"
        env_values["NODE_P2P_PUBLISH_HOST"] = "0.0.0.0"
        env_values["NODE_PUBLIC_P2P_PORT"] = "18444"
        env_values["NODE_HTTP_BIND_PORT"] = "8081"
        env_values["NODE_HTTP_PUBLISH_PORT"] = "8081"
        env_values["NODE_SNAPSHOT_MANIFEST_URLS"] = PUBLIC_DEVNET_SNAPSHOT_MANIFEST_URL
        env_values["DEFAULT_BOOTSTRAP_PEER"] = PUBLIC_DEVNET_BOOTSTRAP_PEER
        env_values["NODE_BOOTSTRAP_URL"] = PUBLIC_DEVNET_BOOTSTRAP_URL
        env_values["DEFAULT_NODE_ENDPOINT"] = PUBLIC_DEVNET_NODE_ENDPOINT
        env_values["DEFAULT_EXPLORER_URL"] = PUBLIC_DEVNET_EXPLORER_URL
        env_values["BROWSER_WALLET_DEFAULT_NODE_ENDPOINT"] = PUBLIC_DEVNET_NODE_ENDPOINT
        env_values["MINING_MIN_INTERVAL_SECONDS"] = "1.0"
        env_values["MINING_NONCE_BATCH_SIZE"] = "250000"
        _apply_new_storage(env_values, network)
        return
    if network == "testnet":
        env_values["COMPOSE_PROJECT_NAME"] = "chipcoin-testnet"
        env_values["CHIPCOIN_RUNTIME_DIR"] = str(RUNTIME_ROOT)
        env_values["CHIPCOIN_RUNTIME_HOST_DIR"] = str(RUNTIME_ROOT)
        env_values["NODE_DATA_PATH"] = TESTNET_NODE_DATA_PATH
        env_values["NODE_SNAPSHOT_FILE"] = TESTNET_NODE_SNAPSHOT_PATH
        env_values["NODE_BOOTSTRAP_MODE"] = "auto"
        env_values["NODE_SNAPSHOT_TRUST_MODE"] = "warn"
        env_values["NODE_P2P_BIND_PORT"] = "28444"
        env_values["NODE_P2P_PUBLISH_HOST"] = "0.0.0.0"
        env_values["NODE_PUBLIC_P2P_PORT"] = "28444"
        env_values["NODE_HTTP_BIND_PORT"] = "28081"
        env_values["NODE_HTTP_PUBLISH_PORT"] = "28081"
        env_values["NODE_SNAPSHOT_MANIFEST_URLS"] = PUBLIC_TESTNET_SNAPSHOT_MANIFEST_URL
        env_values["DEFAULT_BOOTSTRAP_PEER"] = PUBLIC_TESTNET_BOOTSTRAP_PEER
        env_values["NODE_BOOTSTRAP_URL"] = PUBLIC_TESTNET_BOOTSTRAP_URL
        env_values["DEFAULT_NODE_ENDPOINT"] = PUBLIC_TESTNET_WALLET_API_ENDPOINT
        env_values["DEFAULT_EXPLORER_URL"] = PUBLIC_TESTNET_EXPLORER_URL
        env_values["BROWSER_WALLET_DEFAULT_NODE_ENDPOINT"] = PUBLIC_TESTNET_WALLET_API_ENDPOINT
        env_values["MINING_MIN_INTERVAL_SECONDS"] = "10.0"
        env_values["MINING_NONCE_BATCH_SIZE"] = "50000"
        _apply_new_storage(env_values, network)
        return
    _die(f"Unsupported network selection: {network}")


def _apply_new_storage(env_values: dict[str, str], network: str) -> None:
    if not SETUP_STORAGE_BASE:
        return
    root = Path(SETUP_STORAGE_BASE) / network
    env_values["CHIPCOIN_RUNTIME_DIR"] = str(root)
    env_values["CHIPCOIN_RUNTIME_HOST_DIR"] = str(root)
    env_values["CHIPCOIN_RUNTIME_UID"] = f"{os.getuid()}:{os.getgid()}"
    env_values["CHIPCOIN_RUNTIME_COMPAT_HOST_DIR"] = str(root / "runtime")
    env_values["NODE_DATA_PATH"] = str(root / "chain" / "node.sqlite3")
    env_values["NODE_SNAPSHOT_FILE"] = str(root / "chain" / "node.snapshot")
    env_values["MINER_WALLET_FILE"] = str(_wallet_path(network, "miner-wallet.json"))
    if network == "mainnet":
        env_values["NODE_SNAPSHOT_TRUSTED_KEYS_FILE"] = MAINNET_SNAPSHOT_TRUSTED_KEYS_FILE


def _public_node_endpoint_for_network(network: str) -> str:
    if network == "mainnet":
        return MAINNET_LOCAL_NODE_ENDPOINT
    return PUBLIC_DEVNET_NODE_ENDPOINT if network == "devnet" else TESTNET_LOCAL_NODE_ENDPOINT


def _wallet_endpoint_for_network(network: str) -> str:
    if network == "mainnet":
        return PUBLIC_MAINNET_WALLET_API_ENDPOINT
    return PUBLIC_DEVNET_NODE_ENDPOINT if network == "devnet" else PUBLIC_TESTNET_WALLET_API_ENDPOINT


def _wallet_path(network: str, name: str) -> Path:
    if SETUP_STORAGE_BASE:
        kind = "miner" if name == "miner-wallet.json" else "reward"
        return Path(SETUP_STORAGE_BASE) / network / "wallets" / kind / name
    if network == "mainnet":
        return MAINNET_RUNTIME_ROOT / "keys" / name
    if network == "testnet":
        return Path(WALLET_PATH if name == "miner-wallet.json" else REWARD_WALLET_PATH)
    if network == "devnet":
        return RUNTIME_ROOT / "wallets" / "devnet" / name
    _die(f"Unsupported wallet network: {network}")


def _same_compose_node_endpoint(env_values: dict[str, str]) -> str:
    return f"http://node:{env_values.get('NODE_HTTP_BIND_PORT', '8081')}"


def _local_node_endpoint(env_values: dict[str, str]) -> str:
    port = env_values.get("NODE_HTTP_PUBLISH_PORT") or env_values.get("NODE_HTTP_BIND_PORT", "8081")
    return f"http://127.0.0.1:{port}"


def _apply_setup_mode(env_values: dict[str, str], setup_mode: str, role: str, *, network: str = "devnet") -> None:
    public_or_local_endpoint = _public_node_endpoint_for_network(network)
    miner_node_default = public_or_local_endpoint if role == "miner" else _same_compose_node_endpoint(env_values)

    if setup_mode == "quick":
        env_values["DEFAULT_NODE_ENDPOINT"] = public_or_local_endpoint
        env_values["BROWSER_WALLET_DEFAULT_NODE_ENDPOINT"] = _wallet_endpoint_for_network(network)
        env_values["NODE_DIRECT_PEERS"] = ""
        env_values["NODE_DIRECT_PEER"] = ""
        env_values["MINING_NODE_URLS"] = _ask_required_mining_url() if role == "miner" and SETUP_STORAGE_BASE else miner_node_default
        env_values["DIRECT_PEERS"] = ""
        env_values["DIRECT_PEER"] = ""
        env_values["BOOTSTRAP_URL"] = ""
        return

    if setup_mode == "custom":
        node_endpoint = _ask_http_url("Enter node endpoint", public_or_local_endpoint)
        explorer_url = _ask_http_url("Enter explorer URL", env_values.get("DEFAULT_EXPLORER_URL", ""))
        mining_node_urls = _ask_http_url(
            "Enter miner node endpoint",
            node_endpoint if role == "miner" else _same_compose_node_endpoint(env_values),
        )
        env_values["DEFAULT_NODE_ENDPOINT"] = node_endpoint
        env_values["DEFAULT_EXPLORER_URL"] = explorer_url
        env_values["BROWSER_WALLET_DEFAULT_NODE_ENDPOINT"] = node_endpoint
        env_values["NODE_DIRECT_PEERS"] = ""
        env_values["NODE_DIRECT_PEER"] = ""
        env_values["MINING_NODE_URLS"] = mining_node_urls
        env_values["DIRECT_PEERS"] = ""
        env_values["DIRECT_PEER"] = ""
        env_values["BOOTSTRAP_URL"] = ""
        return

    env_values["DEFAULT_NODE_ENDPOINT"] = _local_node_endpoint(env_values)
    env_values["DEFAULT_BOOTSTRAP_PEER"] = ""
    env_values["DEFAULT_EXPLORER_URL"] = ""
    env_values["BROWSER_WALLET_DEFAULT_NODE_ENDPOINT"] = _local_node_endpoint(env_values)
    env_values["NODE_DIRECT_PEERS"] = ""
    env_values["NODE_DIRECT_PEER"] = ""
    env_values["NODE_BOOTSTRAP_URL"] = ""
    env_values["MINING_NODE_URLS"] = (_ask_required_mining_url() if SETUP_STORAGE_BASE else _local_node_endpoint(env_values)) if role == "miner" else _same_compose_node_endpoint(env_values)
    env_values["DIRECT_PEERS"] = ""
    env_values["DIRECT_PEER"] = ""
    env_values["BOOTSTRAP_URL"] = ""


def _configure_node_discovery(env_values: dict[str, str], *, setup_mode: str) -> None:
    """Prompt for node peer discovery and optional bootstrap announce settings."""

    has_bootstrap_defaults = bool(env_values.get("NODE_BOOTSTRAP_URL", "").strip() or env_values.get("DEFAULT_BOOTSTRAP_PEER", "").strip())
    default_discovery = "isolated" if setup_mode == "local" or not has_bootstrap_defaults else "bootstrap"
    default_bootstrap_url = env_values.get("NODE_BOOTSTRAP_URL", "")
    default_startup_peer = env_values.get("DEFAULT_BOOTSTRAP_PEER", "")
    discovery_mode = _ask_choice(
        "How should the node find its first peers?",
        {
            "bootstrap": "Bootstrap seed service",
            "manual": "Manual startup peer list",
            "isolated": "Start isolated",
        },
        default_discovery,
    )

    env_values["NODE_DIRECT_PEERS"] = ""
    env_values["NODE_DIRECT_PEER"] = ""
    env_values["NODE_BOOTSTRAP_URL"] = ""

    if discovery_mode == "bootstrap":
        env_values["NODE_BOOTSTRAP_URL"] = _ask_http_url(
            "Enter bootstrap seed URL",
            default_bootstrap_url,
        )
    elif discovery_mode == "manual":
        env_values["NODE_DIRECT_PEERS"] = _ask_direct_peers(
            "Enter startup peer(s)",
            default_startup_peer,
        )

    publicly_reachable = _ask_choice(
        "Will this node accept inbound public P2P connections?",
        {
            "no": "No",
            "yes": "Yes, announce this node to the bootstrap seed",
        },
        "no" if setup_mode == "local" else "no",
    )

    env_values["BOOTSTRAP_ANNOUNCE_ENABLED"] = "false"
    env_values["NODE_PUBLIC_HOST"] = ""
    env_values["NODE_PUBLIC_P2P_PORT"] = env_values.get("NODE_P2P_BIND_PORT", "18444")

    if publicly_reachable == "yes":
        env_values["BOOTSTRAP_ANNOUNCE_ENABLED"] = "true"
        env_values["NODE_PUBLIC_HOST"] = _ask_host(
            "Enter the public P2P host for this node (for example node.example.com or a public IP)",
            _default_public_host(env_values),
        )
        env_values["NODE_PUBLIC_P2P_PORT"] = _ask_port(
            "Enter the public P2P port for this node",
            env_values.get("NODE_P2P_BIND_PORT", "18444"),
        )


def _configure_node_bootstrap(env_values: dict[str, str], *, setup_mode: str) -> None:
    """Prompt for node bootstrap settings."""

    has_snapshot_manifest = bool(env_values.get("NODE_SNAPSHOT_MANIFEST_URLS", "").strip())
    default_mode = "full" if env_values.get("CHIPCOIN_NETWORK") == "mainnet" or setup_mode == "local" or not has_snapshot_manifest else "auto"
    bootstrap_mode = _ask_choice(
        "How should the node bootstrap?",
        {
            "full": "Full sync from genesis",
            "snapshot": "Snapshot bootstrap only",
            "auto": "Prefer snapshot, fall back to full sync",
        },
        default_mode,
    )
    env_values["NODE_BOOTSTRAP_MODE"] = bootstrap_mode
    if bootstrap_mode == "full":
        env_values["NODE_SNAPSHOT_MANIFEST_URLS"] = ""
        env_values["NODE_SNAPSHOT_TRUST_MODE"] = "off"
        env_values["NODE_SNAPSHOT_TRUSTED_KEYS_FILE"] = ""
        return

    default_manifest_urls = env_values.get("NODE_SNAPSHOT_MANIFEST_URLS", "")
    env_values["NODE_SNAPSHOT_MANIFEST_URLS"] = _ask_optional_http_urls(
        "Enter snapshot manifest URL(s)",
        default_manifest_urls,
    )
    env_values["NODE_SNAPSHOT_TRUST_MODE"] = _ask_choice(
        "How should snapshot trust be handled?",
        {
            "off": "Do not verify signatures",
            "warn": "Warn on weak/untrusted snapshots but continue",
            "enforce": "Require a valid trusted snapshot signature",
        },
        "enforce" if env_values.get("CHIPCOIN_NETWORK") == "mainnet" else "warn",
    )
    trusted_keys_file = input(
        f"Enter trusted snapshot signer keys file [{env_values['NODE_SNAPSHOT_TRUSTED_KEYS_FILE']}]: "
    ).strip()
    if trusted_keys_file:
        env_values["NODE_SNAPSHOT_TRUSTED_KEYS_FILE"] = trusted_keys_file
    if env_values.get("CHIPCOIN_NETWORK") == "mainnet":
        if env_values["NODE_SNAPSHOT_TRUST_MODE"] != "enforce":
            _die("Mainnet snapshot bootstrap requires trusted signature enforcement.")
        key_path = Path(env_values["NODE_SNAPSHOT_TRUSTED_KEYS_FILE"])
        if key_path == Path(MAINNET_SNAPSHOT_TRUSTED_KEYS_FILE):
            _ensure_runtime_parent(key_path, "Snapshot trust")
            if not key_path.exists():
                _atomic_new_file(key_path, (MAINNET_SNAPSHOT_SIGNER_KEY_HEX + "\n").encode())
            elif key_path.read_text(encoding="utf-8").strip() != MAINNET_SNAPSHOT_SIGNER_KEY_HEX:
                _die(f"Mainnet snapshot trust key differs from the approved signer: {key_path}")


def _print_public_reachability_note(*, network: str = "devnet") -> None:
    default_port = get_network_config(network).default_p2p_port
    default_http_port = {"mainnet": "8080", "testnet": "28081"}.get(network, "8081")
    print()
    print("Public reachability note:")
    print("  - outbound-only nodes can still connect and sync")
    print("  - publicly reachable nodes are strongly preferred for network health")
    print(f"  - when possible, open and forward TCP {default_port} for the node P2P listener")
    print(f"  - keep HTTP TCP {default_http_port} bound to 127.0.0.1 unless you intentionally reverse-proxy it")
    print("  - for clean installs, prefer multiple startup peers when available")
    print()


def _prepare_wallet_path(wallet_path: Path) -> None:
    _ensure_runtime_parent(wallet_path, "Wallet")
    if wallet_path.is_symlink():
        _die(f"Wallet path must not be a symbolic link: {wallet_path}")


def _check_pq_backend() -> None:
    """Check the pinned native backend against the consensus test vector."""
    try:
        from chipcoin.crypto.pq.mldsa import derive_mldsa44_keypair, mldsa44_backend_info, sign_mldsa44, verify_mldsa44
        info = mldsa44_backend_info()
        seed = bytes(range(32))  # Public test vector; never written to a wallet.
        digest = bytes.fromhex("00" * 31 + "01")
        private, public = derive_mldsa44_keypair(seed)
        signature = sign_mldsa44(seed, digest)
        if (info.get("backend") != "mldsa-native"
            or info.get("upstream_commit") != "9b0ee84f4cf399043eca59eca4e5f8531ca1d61b"
            or info.get("scheme") != "ML-DSA-44"
            or hashlib.sha256(private).hexdigest() != "04bf6b9f579166a627961dfc5c3bf9717df868db88863856356c4668c8b56b0b"
            or hashlib.sha256(public).hexdigest() != "9f107644c1084526af3bc8098680b05499a2325a644e388fb4f970e058d19d46"
            or hashlib.sha256(signature).hexdigest() != "1fad42d544aac40d1c38ac277fad988b5eb675459cd4f3f83d477b613c1b4eb4"
            or not verify_mldsa44(public, digest, signature)):
            raise ValueError("backend test vector mismatch")
    except Exception:  # noqa: BLE001 - never print private material or backend traceback
        _die("ML-DSA-44 backend check failed. Docker setup: rebuild with ./setup.sh. Host Python: create .venv, install this checkout with .venv/bin/python -m pip install -e ., then rerun with .venv/bin/python scripts/setup/wizard.py.")


def _atomic_new_file(path: Path, data: bytes) -> None:
    """Create a private file without exposing partial contents or replacing an existing file."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".chipcoin-setup-", dir=path.parent)
    linked = False
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        linked = True
        _remember_new_file(path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError:
        _die(f"Existing file left unchanged: {path}")
    except OSError:
        if linked:
            path.unlink(missing_ok=True)
        _die(f"Could not safely save {path}; check free space and permissions. Existing files were not changed.")
    finally:
        os.unlink(temporary)


def _handle_wallet(wallet_mode: str, wallet_path: Path, *, network: str = "testnet") -> tuple[str, str]:
    _prepare_wallet_path(wallet_path)
    require_pq = network == "mainnet"
    if wallet_path.exists():
        try:
            if not wallet_path.is_file() or wallet_path.stat().st_mode & 0o077:
                raise ValueError("wallet permissions must be private")
            payload = json.loads(wallet_path.read_text(encoding="utf-8"))
            from chipcoin.crypto.addresses import parse_address
            from chipcoin.wallet.signer import wallet_key_from_mldsa44_seed, wallet_key_from_private_key
            from chipcoin.crypto.keys import parse_private_key_hex
            if require_pq:
                _check_pq_backend()
                key = wallet_key_from_mldsa44_seed(bytes.fromhex(payload["private_seed_hex"]))
            else:
                key = wallet_key_from_private_key(parse_private_key_hex(payload["private_key_hex"]))
            if (payload["address"] != key.address
                or payload["public_key_hex"] != key.public_key.hex()
                or payload["scheme_id"] != key.scheme_id
                or payload["scheme_name"] != key.scheme_name
                or payload["address_kind"] != key.address_kind
                or not parse_address(key.address)):
                raise ValueError("wallet identity mismatch")
        except Exception:  # noqa: BLE001
            _die(f"Existing wallet cannot be safely reused: {wallet_path}. It was not changed.")
        print(f"Reusing existing wallet at {wallet_path}; identity unchanged.")
        return key.address, key.public_key.hex()
    if require_pq:
        _check_pq_backend()
    try:
        from chipcoin.crypto.keys import parse_private_key_hex
        from chipcoin.wallet.signer import generate_wallet_key, wallet_key_from_mldsa44_seed, wallet_key_from_private_key
    except ImportError:
        _die("Wallet setup needs the host Python package. On Ubuntu install build-essential python3-dev python3-venv, then create a venv and run: .venv/bin/python -m pip install -e .")

    if wallet_mode == "generate":
        wallet_key = generate_wallet_key(scheme="mldsa44" if require_pq else "secp256k1")
    else:
        private_key_hex = getpass.getpass("Enter ML-DSA seed hex: " if require_pq else "Enter private key hex: ").strip()
        if not private_key_hex:
            _die("Key material must not be empty.")
        try:
            wallet_key = (
                wallet_key_from_mldsa44_seed(bytes.fromhex(private_key_hex))
                if require_pq
                else wallet_key_from_private_key(parse_private_key_hex(private_key_hex))
            )
        except Exception:  # noqa: BLE001
            _die("Invalid wallet key material.")

    payload = {
        "scheme_id": wallet_key.scheme_id,
        "scheme_name": wallet_key.scheme_name,
        "address_kind": wallet_key.address_kind,
        "public_key_hex": wallet_key.public_key.hex(),
        "address": wallet_key.address,
        "compressed": wallet_key.compressed,
    }
    if wallet_key.private_seed is not None:
        payload["private_seed_hex"] = wallet_key.private_seed.hex()
    else:
        payload["private_key_hex"] = wallet_key.private_key.hex()
    encoded_wallet = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    _atomic_new_file(wallet_path, encoded_wallet.encode("utf-8"))
    return wallet_key.address, wallet_key.public_key.hex()


def _prepare_sqlite_file(path: Path, label: str) -> None:
    _ensure_runtime_parent(path, label)
    if path.exists() and path.is_dir():
        _die(f"{label} path points to a directory, but a writable SQLite file is required: {path}")
    try:
        if not path.exists():
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
            os.close(fd)
            _remember_new_file(path)
    except PermissionError as exc:
        _die(
            f"{label} file is not writable: {path}. "
            "The runtime directory may need to be prepared or re-owned first. "
            f"Original error: {exc}"
        )
    if not path.is_file():
        _die(f"{label} path is not a regular file: {path}")
    if path.is_symlink():
        _die(f"{label} path must not be a symbolic link: {path}")
    if not os.access(path, os.W_OK):
        _die(f"{label} file is not writable: {path}")


def _reset_sqlite_file(path: Path, label: str) -> None:
    _ensure_runtime_parent(path, label)
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    _remember_new_file(path)


def _write_snapshot_metadata_file(node_data_path: Path, metadata: dict[str, object]) -> None:
    """Persist a small audit/debug record next to the node DB."""

    metadata_path = _snapshot_metadata_path(node_data_path)
    _atomic_new_file(metadata_path, (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode())


def _remove_snapshot_metadata_file(node_data_path: Path) -> None:
    """Remove the snapshot audit/debug record when bootstrap is reset."""

    metadata_path = _snapshot_metadata_path(node_data_path)
    if metadata_path.exists() and metadata_path.is_file():
        metadata_path.unlink()


def _prepare_runtime_files(env_values: dict[str, str], *, role: str) -> None:
    if role in {"node", "both"}:
        _prepare_sqlite_file(Path(env_values["NODE_DATA_PATH"]), "Node data")


def _preflight_validate(env_values: dict[str, str], *, role: str) -> None:
    """Validate the generated install contract before writing .env."""

    if not COMPOSE_FILE_PATH.exists():
        _die(f"Expected Docker Compose file is missing: {COMPOSE_FILE_PATH}")
    if role not in {"node", "miner", "both"}:
        _die(f"Unsupported role selection: {role}")
    if role in {"node", "both"}:
        node_data_path = Path(env_values["NODE_DATA_PATH"])
        _ensure_runtime_parent(node_data_path, "Node data")
        announce_enabled = env_values.get("BOOTSTRAP_ANNOUNCE_ENABLED", "false")
        if announce_enabled not in {"true", "false", "1", "0"}:
            _die("BOOTSTRAP_ANNOUNCE_ENABLED must be true or false.")
        if announce_enabled in {"true", "1"}:
            bootstrap_url = env_values.get("NODE_BOOTSTRAP_URL", "").strip() or env_values.get("BOOTSTRAP_URL", "").strip()
            if not bootstrap_url:
                _die("Bootstrap announce requires NODE_BOOTSTRAP_URL or BOOTSTRAP_URL.")
            if not env_values.get("NODE_PUBLIC_HOST", "").strip():
                _die("Bootstrap announce requires NODE_PUBLIC_HOST.")
            if not _looks_public_host(env_values["NODE_PUBLIC_HOST"]):
                _die(f"NODE_PUBLIC_HOST is not a public host: {env_values['NODE_PUBLIC_HOST']}")
            public_port = env_values.get("NODE_PUBLIC_P2P_PORT", "").strip()
            if not public_port.isdigit() or not (1 <= int(public_port) <= 65535):
                _die(f"NODE_PUBLIC_P2P_PORT must be a valid TCP port: {public_port}")
        bootstrap_mode = env_values.get("NODE_BOOTSTRAP_MODE", "full")
        if bootstrap_mode not in {"full", "snapshot", "auto"}:
            _die(f"Unsupported node bootstrap mode: {bootstrap_mode}")
        if bootstrap_mode in {"snapshot", "auto"}:
            try:
                _parse_http_urls(env_values.get("NODE_SNAPSHOT_MANIFEST_URLS", ""))
            except ValueError as exc:
                _die(f"Snapshot manifest URL list is invalid: {exc}")
            snapshot_path = Path(env_values["NODE_SNAPSHOT_FILE"])
            _ensure_runtime_parent(snapshot_path, "Snapshot cache")
            trusted_keys_file = env_values.get("NODE_SNAPSHOT_TRUSTED_KEYS_FILE", "").strip()
            trust_mode = env_values.get("NODE_SNAPSHOT_TRUST_MODE", "off")
            if trust_mode == "enforce" and not trusted_keys_file:
                _die("Snapshot trust mode 'enforce' requires NODE_SNAPSHOT_TRUSTED_KEYS_FILE.")
            if trusted_keys_file and not Path(trusted_keys_file).exists():
                _die(f"Snapshot trusted keys file does not exist: {trusted_keys_file}")
        reward_node_id = env_values.get("REWARD_NODE_AUTO_NODE_ID", "").strip()
        if reward_node_id:
            owner_wallet_path = env_values.get("REWARD_NODE_OWNER_WALLET_SOURCE", "").strip()
            attest_wallet_path = env_values.get("REWARD_NODE_ATTEST_WALLET_SOURCE", "").strip() or owner_wallet_path
            if not owner_wallet_path:
                _die("Reward-node mode requires REWARD_NODE_OWNER_WALLET_SOURCE.")
            if not Path(owner_wallet_path).exists():
                _die(f"Reward-node owner wallet file does not exist: {owner_wallet_path}")
            if not attest_wallet_path:
                _die("Reward-node mode requires REWARD_NODE_AUTO_ATTEST_WALLET_FILE or owner wallet fallback.")
            if not Path(attest_wallet_path).exists():
                _die(f"Reward-node attestation wallet file does not exist: {attest_wallet_path}")
            declared_host = env_values.get("REWARD_NODE_AUTO_DECLARED_HOST", "").strip()
            if not declared_host:
                _die("Reward-node mode requires REWARD_NODE_AUTO_DECLARED_HOST.")
            declared_port = env_values.get("REWARD_NODE_AUTO_DECLARED_PORT", "").strip()
            if not declared_port.isdigit() or not (1 <= int(declared_port) <= 65535):
                _die(f"REWARD_NODE_AUTO_DECLARED_PORT must be a valid TCP port: {declared_port}")
    if role in {"miner", "both"} and not env_values.get("MINING_NODE_URLS", "").strip():
        _die("Miner mode requires at least one mining node endpoint.")
    if role in {"miner", "both"}:
        worker_count = env_values.get("MINING_WORKER_COUNT", "1").strip()
        if not worker_count.isdigit() or int(worker_count) < 1:
            _die(f"MINING_WORKER_COUNT must be a positive integer: {worker_count}")


def _prepare_node_bootstrap(env_values: dict[str, str], *, network: str) -> list[str]:
    """Prepare full-sync or snapshot bootstrap assets for the node."""

    notes: list[str] = []
    bootstrap_mode = env_values.get("NODE_BOOTSTRAP_MODE", "full")
    if bootstrap_mode == "full":
        notes.append("Node bootstrap mode: full sync from genesis.")
        return notes

    snapshot_file = Path(env_values["NODE_SNAPSHOT_FILE"])
    if snapshot_file.exists() or snapshot_file.is_symlink():
        _die(f"Existing snapshot cache left unchanged: {snapshot_file}. Use a new storage root or review it explicitly.")

    try:
        from chipcoin.interfaces.cli import _load_snapshot_trusted_keys
        from chipcoin.node.service import NodeService
    except ImportError:
        _die("Snapshot import needs the host Python package. On Ubuntu install build-essential python3-dev python3-venv, then create a venv and run: .venv/bin/python -m pip install -e .")

    manifest_urls_raw = env_values.get("NODE_SNAPSHOT_MANIFEST_URLS", "")
    try:
        manifest_urls = _parse_http_urls(manifest_urls_raw)
    except ValueError as exc:
        if bootstrap_mode == "auto":
            env_values["NODE_BOOTSTRAP_MODE"] = "full"
            notes.append(f"Snapshot bootstrap skipped: {exc}. Falling back to full sync.")
            return notes
        _die(f"Snapshot bootstrap configuration is invalid: {exc}")

    if not manifest_urls:
        if bootstrap_mode == "auto":
            env_values["NODE_BOOTSTRAP_MODE"] = "full"
            notes.append("Snapshot bootstrap skipped: no manifest URLs configured. Falling back to full sync.")
            return notes
        _die("Snapshot bootstrap requires at least one manifest URL.")

    try:
        trusted_keys = _load_snapshot_trusted_keys(
            [],
            [env_values["NODE_SNAPSHOT_TRUSTED_KEYS_FILE"]] if env_values.get("NODE_SNAPSHOT_TRUSTED_KEYS_FILE") else [],
        )
        manifest_entry = _select_latest_compatible_snapshot(manifest_urls, network=network)
        notes.append(f"Manifest source used: {manifest_entry.manifest_url}")
        notes.extend(_snapshot_entry_warnings(manifest_entry))
        snapshot_path = Path(env_values["NODE_SNAPSHOT_FILE"])
        _ensure_runtime_parent(snapshot_path, "Snapshot cache")
        _download_snapshot_file(manifest_entry.snapshot_url, snapshot_path)
        if _file_sha256(snapshot_path) != manifest_entry.checksum_sha256:
            raise ValueError("downloaded snapshot file checksum does not match the selected manifest entry")
        node_data_path = Path(env_values["NODE_DATA_PATH"])
        _reset_sqlite_file(node_data_path, "Node data")
        service = NodeService.open_sqlite(node_data_path, network=network)
        metadata = service.import_snapshot_file(
            snapshot_path,
            reset_existing=True,
            trust_mode=env_values.get("NODE_SNAPSHOT_TRUST_MODE", "off"),
            trusted_keys=trusted_keys,
        )
        warnings = metadata.get("warnings", [])
        if isinstance(warnings, list):
            for warning in warnings:
                notes.append(
                    f"WARNING {warning}; snapshot import continued only because trust mode is "
                    f"{env_values.get('NODE_SNAPSHOT_TRUST_MODE', 'off')}."
                )
        _write_snapshot_metadata_file(
            node_data_path,
            {
                "bootstrap_mode": "snapshot",
                "manifest_url": manifest_entry.manifest_url,
                "snapshot_url": manifest_entry.snapshot_url,
                "snapshot_height": manifest_entry.snapshot_height,
                "snapshot_block_hash": manifest_entry.snapshot_block_hash,
                "snapshot_file": str(snapshot_path),
                "node_data_path": str(node_data_path),
                "snapshot_trust_mode": env_values.get("NODE_SNAPSHOT_TRUST_MODE", "off"),
                "accepted_snapshot_signer_pubkeys": metadata.get("accepted_signer_pubkeys", []),
                "warnings": metadata.get("warnings", []),
            },
        )
        env_values["NODE_BOOTSTRAP_MODE"] = "snapshot"
        env_values["NODE_SNAPSHOT_SELECTED_URL"] = manifest_entry.snapshot_url
        env_values["NODE_SNAPSHOT_SELECTED_HEIGHT"] = str(manifest_entry.snapshot_height)
        env_values["NODE_SNAPSHOT_SELECTED_HASH"] = manifest_entry.snapshot_block_hash
        notes.append(
            f"Snapshot selected: {manifest_entry.snapshot_url} "
            f"(height {manifest_entry.snapshot_height} hash {manifest_entry.snapshot_block_hash})."
        )
        notes.append(f"Node database prepared at {env_values['NODE_DATA_PATH']}.")
        return notes
    except Exception as exc:  # noqa: BLE001
        _reset_sqlite_file(Path(env_values["NODE_DATA_PATH"]), "Node data")
        _remove_snapshot_metadata_file(Path(env_values["NODE_DATA_PATH"]))
        snapshot_file = Path(env_values["NODE_SNAPSHOT_FILE"])
        if snapshot_file.exists() and snapshot_file.is_file():
            snapshot_file.unlink()
        if bootstrap_mode == "auto":
            env_values["NODE_BOOTSTRAP_MODE"] = "full"
            env_values["NODE_SNAPSHOT_SELECTED_URL"] = ""
            env_values["NODE_SNAPSHOT_SELECTED_HEIGHT"] = ""
            env_values["NODE_SNAPSHOT_SELECTED_HASH"] = ""
            notes.append(f"Snapshot bootstrap failed: {exc}. Falling back to full sync.")
            return notes
        _die(f"Snapshot bootstrap failed: {exc}")


def _snapshot_entry_warnings(entry: SnapshotManifestEntry) -> list[str]:
    warnings: list[str] = []
    age_seconds = max(0, int(time.time()) - entry.created_at)
    if age_seconds >= SNAPSHOT_STALE_WARNING_SECONDS:
        warnings.append(
            f"WARNING selected snapshot is {age_seconds} seconds old but still valid."
        )
    if age_seconds >= SNAPSHOT_LARGE_DELTA_WARNING_SECONDS:
        warnings.append(
            "WARNING selected snapshot is old enough that the node may need a large post-anchor delta sync."
        )
    return warnings


def _fetch_json_from_url(url: str) -> object:
    with request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_snapshot_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".chipcoin-snapshot-", dir=destination.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as output, request.urlopen(url, timeout=60) as response:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, destination, follow_symlinks=False)
        _remember_new_file(destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _parse_snapshot_manifest(payload: object, *, manifest_url: str) -> list[SnapshotManifestEntry]:
    if isinstance(payload, dict):
        raw_entries = payload.get("snapshots", [])
    elif isinstance(payload, list):
        raw_entries = payload
    else:
        raise ValueError(f"Unsupported snapshot manifest format from {manifest_url}")
    if not isinstance(raw_entries, list):
        raise ValueError(f"Snapshot manifest entries must be a list: {manifest_url}")

    entries: list[SnapshotManifestEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise ValueError(f"Snapshot manifest entry must be an object: {manifest_url}")
        raw_signers = raw_entry.get("signer_pubkeys", [])
        if isinstance(raw_signers, list):
            signer_pubkeys = tuple(str(value) for value in raw_signers if str(value))
        else:
            signer_pubkeys = ()
        checksum = raw_entry.get("checksum_sha256", raw_entry.get("checksum"))
        entries.append(
            SnapshotManifestEntry(
                manifest_url=manifest_url,
                network=str(raw_entry["network"]),
                snapshot_url=str(raw_entry["snapshot_url"]),
                format_version=int(raw_entry["format_version"]),
                snapshot_height=int(raw_entry["snapshot_height"]),
                snapshot_block_hash=str(raw_entry["snapshot_block_hash"]),
                created_at=int(raw_entry["created_at"]),
                checksum_sha256=str(checksum),
                signer_pubkeys=signer_pubkeys,
            )
        )
    return entries


def _select_latest_compatible_snapshot(manifest_urls: list[str], *, network: str) -> SnapshotManifestEntry:
    errors: list[str] = []
    for manifest_url in manifest_urls:
        try:
            payload = _fetch_json_from_url(manifest_url)
            entries = _parse_snapshot_manifest(payload, manifest_url=manifest_url)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{manifest_url}: {exc}")
            continue
        compatible = [
            entry
            for entry in entries
            if entry.network == network and entry.format_version in {1, 2, 3}
        ]
        if compatible:
            compatible.sort(key=lambda entry: (entry.snapshot_height, entry.created_at, entry.format_version), reverse=True)
            return compatible[0]
        errors.append(f"{manifest_url}: no compatible snapshot entries were found")
    details = "; ".join(errors) if errors else "no compatible snapshot entries were found"
    raise ValueError(f"snapshot source unavailable or incompatible: {details}")


def _write_env(values: dict[str, str], env_path: Path) -> None:
    lines = [f"{key}={values[key]}" for key in DEFAULTS]
    encoded = ("\n".join(lines) + "\n").encode("utf-8")
    if env_path.exists():
        if env_path.read_bytes() != encoded:
            _die(f"Existing settings left unchanged: {env_path}. Use a new storage root or edit explicitly after backup.")
        print(f"Reusing identical settings at {env_path}.")
        return
    _atomic_new_file(env_path, encoded)


def _print_success(
    role: str,
    network: str,
    runtime_mode: str,
    env_path: Path,
    miner_wallet_path: Path | None,
    miner_wallet_address: str | None,
    reward_wallet_path: Path | None,
    reward_wallet_address: str | None,
    reward_wallet_public_key_hex: str | None,
    reward_node_enabled: bool,
    setup_mode: str,
    env_values: dict[str, str],
    bootstrap_notes: list[str],
) -> None:
    service_role = "node" if role == "reward-node" else role
    command_suffix = {"node": "node", "miner": "miner", "both": "node miner"}[service_role]
    host_repo = Path(os.environ.get("CHIPCOIN_SETUP_HOST_REPO", str(REPO_ROOT)))
    env_file_arg = f"--env-file {shlex.quote(str(env_path))}"
    compose_base = f"docker compose {env_file_arg} -f {shlex.quote(str(host_repo / 'docker-compose.yml'))}"
    if SETUP_STORAGE_BASE:
        compose_base += f" -f {shlex.quote(str(host_repo / 'docker-compose.setup-runtime.yml'))}"
    compose_up_background = f"{compose_base} up -d {command_suffix}".strip()

    print()
    print("Setup completed successfully.")
    print(f"Role: {role}")
    print(f"Network: {network}")
    print(f"Environment file: {env_path}")
    if miner_wallet_path is not None and miner_wallet_address is not None:
        print(f"Miner wallet file: {miner_wallet_path}")
        print(f"Miner wallet address: {miner_wallet_address}")
    else:
        print("Miner wallet: not configured")
    if (
        reward_node_enabled
        and reward_wallet_path is not None
        and reward_wallet_address is not None
        and reward_wallet_public_key_hex is not None
    ):
        register_fee, renew_fee, suggested_total = _reward_fee_guidance(network)
        print(f"Reward-node wallet file: {reward_wallet_path}")
        print(f"Reward-node payout address: {reward_wallet_address}")
        print(f"Reward-node id: {env_values['REWARD_NODE_AUTO_NODE_ID']}")
        print(f"Reward-node declared host: {env_values['REWARD_NODE_AUTO_DECLARED_HOST']}")
        print(f"Reward-node declared port: {env_values['REWARD_NODE_AUTO_DECLARED_PORT']}")
        print(
            "Reward-node funding guidance: "
            f"registration currently starts at {register_fee} CHC, "
            f"renewal at {renew_fee} CHC, and you should provision at least {suggested_total} CHC."
        )
        if network == "testnet":
            print(
                "Testnet faucet note: the public faucet is rate-limited. "
                "If it grants 1 CHC/day, the first claim covers the initial registration target; "
                "claim again later or use another funded testnet wallet for renewal buffer."
            )
        elif network == "devnet":
            print("Devnet note: use the legacy devnet faucet or another devnet funding source before attempting registration.")
    else:
        print("Reward-node mode: passive full node")
    print(f"Runtime directory: {env_values['CHIPCOIN_RUNTIME_DIR']}")
    if service_role in {"node", "both"}:
        print(f"Node database: {env_values['NODE_DATA_PATH']}")
        print(f"Snapshot metadata file: {_snapshot_metadata_path(Path(env_values['NODE_DATA_PATH']))}")
        if env_values["NODE_BOOTSTRAP_URL"]:
            print(f"Node bootstrap seed URL: {env_values['NODE_BOOTSTRAP_URL']}")
        else:
            print("Node bootstrap seed URL: none")
        print(f"Bootstrap announce enabled: {env_values.get('BOOTSTRAP_ANNOUNCE_ENABLED', 'false')}")
        if env_values.get("BOOTSTRAP_ANNOUNCE_ENABLED") == "true":
            print(f"Announced public host: {env_values['NODE_PUBLIC_HOST']}")
            print(f"Announced public P2P port: {env_values['NODE_PUBLIC_P2P_PORT']}")
    print(f"Setup mode: {setup_mode}")
    print(f"Default node endpoint: {env_values['DEFAULT_NODE_ENDPOINT']}")
    if service_role in {"node", "both"}:
        print(f"Node bootstrap mode: {env_values['NODE_BOOTSTRAP_MODE']}")
        if env_values["NODE_BOOTSTRAP_MODE"] == "snapshot":
            print(f"Snapshot manifest URL(s): {env_values['NODE_SNAPSHOT_MANIFEST_URLS']}")
            print(f"Snapshot cache file: {env_values['NODE_SNAPSHOT_FILE']}")
            print(f"Snapshot trust mode: {env_values['NODE_SNAPSHOT_TRUST_MODE']}")
            if env_values["NODE_SNAPSHOT_SELECTED_URL"]:
                print(f"Selected snapshot URL: {env_values['NODE_SNAPSHOT_SELECTED_URL']}")
                print(f"Selected snapshot height: {env_values['NODE_SNAPSHOT_SELECTED_HEIGHT']}")
                print(f"Selected snapshot hash: {env_values['NODE_SNAPSHOT_SELECTED_HASH']}")
    if service_role in {"miner", "both"}:
        print(f"Miner node endpoint(s): {env_values['MINING_NODE_URLS']}")
    if env_values["DEFAULT_BOOTSTRAP_PEER"]:
        print(f"Default bootstrap peer: {env_values['DEFAULT_BOOTSTRAP_PEER']}")
    else:
        print("Default bootstrap peer: none")
    if env_values["DIRECT_PEERS"]:
        print(f"Startup peers: {env_values['DIRECT_PEERS']}")
    elif env_values["DIRECT_PEER"]:
        print(f"Startup peer (legacy): {env_values['DIRECT_PEER']}")
    else:
        print("Startup peers: none")
    if env_values["DEFAULT_EXPLORER_URL"]:
        print(f"Default explorer URL: {env_values['DEFAULT_EXPLORER_URL']}")
    else:
        print("Default explorer URL: none")
    if bootstrap_notes:
        print()
        print("Bootstrap notes:")
        for note in bootstrap_notes:
            print(f"  - {note}")
    if (
        reward_node_enabled
        and reward_wallet_path is not None
        and reward_wallet_address is not None
        and reward_wallet_public_key_hex is not None
    ):
        registration_peer = _default_reward_registration_peer(env_values)
        print()
        print("Reward-node registration command (run after the reward-node wallet is funded):")
        print(
            f"  {compose_base} run --rm --no-deps --entrypoint chipcoin "
            f"-v {shlex.quote(env_values['NODE_DATA_PATH'] + ':/runtime/node.sqlite3')} "
            f"-v {shlex.quote(str(reward_wallet_path) + ':/runtime/reward-node-wallet.json:ro')} "
            "node "
            f"--network {network} --data /runtime/node.sqlite3 "
            "register-reward-node "
            "--wallet-file /runtime/reward-node-wallet.json "
            f"--node-id {env_values['REWARD_NODE_AUTO_NODE_ID']} "
            f"--payout-address {reward_wallet_address} "
            f"--node-pubkey-hex {reward_wallet_public_key_hex} "
            f"--declared-host {env_values['REWARD_NODE_AUTO_DECLARED_HOST']} "
            f"--declared-port {env_values['REWARD_NODE_AUTO_DECLARED_PORT']} "
            f"--connect {registration_peer}"
        )
    print()
    print("Next commands:")
    print(f"  {compose_base} build {command_suffix}")
    print(f"  {compose_up_background}")
    if service_role in {"node", "both"}:
        print(f"  curl -fsS 'http://127.0.0.1:{env_values['NODE_HTTP_PUBLISH_PORT']}/v1/status'")
    if service_role in {"node", "both"}:
        print(f"  {compose_base} logs -f node")
    if service_role in {"miner", "both"}:
        print(f"  {compose_base} logs -f miner")
    print(f"  {compose_base} ps")
    print(f"  {compose_base} down")
    print()
    print("What to inspect:")
    if service_role in {"node", "both"} and env_values["NODE_BOOTSTRAP_MODE"] == "full":
        print("  - On first start, the node should log bootstrap_mode=full and begin syncing from genesis.")
    elif service_role in {"node", "both"}:
        print("  - On first start, the node should log bootstrap_mode=snapshot and start near the snapshot anchor height.")
        print("  - If the remote tip is higher than the anchor, only the post-anchor delta should sync.")


def _die(message: str) -> None:
    print(f"ERROR {message}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
