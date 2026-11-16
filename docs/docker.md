# Docker Runtime

This repository uses Docker Compose as the public runtime path for:

- `node`
- `miner`

The browser wallet is built separately and connects to the node HTTP API.

From a fresh clone, `python3 scripts/setup/wizard.py` prepares a passive node
without host `pip`, a virtual environment, or GCC. `docker compose ... up --build`
compiles the native ML-DSA-44 extension inside the Docker builder. Host-side
CLI installation, wallet generation/import, and snapshot import require a C
compiler and Python development headers; see `docs/setup-wizard.md`.

## Public Compose Files

- `docker-compose.yml`
  The canonical public configuration. It is environment-variable driven and contains no machine-specific paths.

- `docker-compose.override.yml`
  Optional local-only customization file. It is ignored by git and is applied automatically by `docker compose` when present.

## Runtime Layout

The recommended runtime layout keeps mutable state outside the repository.

Mainnet example (the wizard's default):

- `/var/lib/chipcoin-mainnet-official/data/node.sqlite3`
- `/var/lib/chipcoin-mainnet-official/keys/miner-wallet.json`

Testnet and Devnet use separate paths. Do not reuse a database or wallet across networks.

Relevant `.env` keys:

- `CHIPCOIN_RUNTIME_DIR`
- `NODE_DATA_PATH`
- `MINER_WALLET_FILE`
- `MINING_NODE_URLS`
- `MINING_WORKER_COUNT`
- `CHIPCOIN_MEMORY_LIMIT`
- `MAX_PENDING_HANDSHAKES`
- `MAX_PENDING_HANDSHAKES_PER_IP`
- `MAX_PEER_ALIASES_PER_NODE_ID`
- `MEMORY_METRICS_INTERVAL_SECONDS`

## Start

New installation (Mainnet node only):

```bash
python3 scripts/setup/wizard.py
docker compose --env-file .env.mainnet up -d --build node
```

The wizard prints the correct environment file for a different network.
It does not start services. To use the manual Mainnet template, copy
`.env.mainnet.example` to `.env.mainnet` and prepare its runtime paths first.

After generating and backing up a miner wallet, start the miner explicitly:

```bash
docker compose --env-file .env.mainnet up -d --build miner
```

For status and logs:

```bash
docker compose --env-file .env.mainnet ps
docker compose --env-file .env.mainnet logs -f node
```

To stop a selected service:

```bash
docker compose --env-file .env.mainnet stop node
```

Use `--env-file .env` for explicitly selected Testnet and
`--env-file .env.devnet` for Devnet. Avoid `docker compose down` when another
network shares the project directory; always select the intended environment.

Memory and restart monitoring (Mainnet example):

```bash
docker compose --env-file .env.mainnet ps -q node | xargs -r docker stats --no-stream
docker compose --env-file .env.mainnet logs node | grep 'runtime memory metrics'
```

The node Compose service uses `CHIPCOIN_MEMORY_LIMIT:-2g` as a configurable
guardrail. Measure your own host before changing it.

## Notes

- The node runtime currently does not use a wallet file.
- The miner runtime does use `MINER_WALLET_FILE`.
- The miner no longer keeps a local chain database.
- `MINING_WORKER_COUNT` can be raised above `1` to use multiple local CPU cores
  inside one miner container.
- The same Compose file serves Mainnet, Testnet, and Devnet. Choose an explicit environment file; the wizard selects Mainnet for a new installation.
- The generic Compose default publishes both P2P and HTTP on loopback. Public testnet explicitly sets `NODE_P2P_PUBLISH_HOST=0.0.0.0` in its example profile; keep HTTP on `127.0.0.1:28081`.
- Public firewall rules should expose only the selected P2P port. Mainnet starts private on `127.0.0.1:8333`; an operator must explicitly set the P2P publish host to `0.0.0.0` before running a public peer.
- Testnet miner defaults should stay conservative (`MINING_MIN_INTERVAL_SECONDS=10.0`, `MINING_NONCE_BATCH_SIZE=50000`) for multi-node public runs.
- Devnet is still available via `.env.devnet.example` and uses P2P `18444/tcp` plus localhost HTTP `8081`.
- Mainnet: container HTTP `8080/tcp`, host `127.0.0.1:8080` by default; see `.env.mainnet.example`. Keep separate runtime data and wallet files.
- Local override files are for ports, extra bind mounts, and machine-specific behavior only. Keep secrets and runtime state out of the repository.
