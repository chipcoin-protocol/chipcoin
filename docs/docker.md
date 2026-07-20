# Docker Runtime

This repository uses Docker Compose as the public runtime path for:

- `node`
- `miner`

The browser wallet is built separately and connects to the node HTTP API.

## Public Compose Files

- `docker-compose.yml`
  The canonical public configuration. It is environment-variable driven and contains no machine-specific paths.

- `docker-compose.override.yml`
  Optional local-only customization file. It is ignored by git and is applied automatically by `docker compose` when present.

## Runtime Layout

The recommended runtime layout keeps mutable state outside the repository.

Example:

- `/var/lib/chipcoin/data/node-testnet.sqlite3`
- `/var/lib/chipcoin/wallets/testnet-miner-wallet.json`
- `/var/lib/chipcoin/logs/node/`
- `/var/lib/chipcoin/logs/miner/`

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

Node and miner:

```bash
docker compose up --build node miner
```

Detached:

```bash
docker compose up -d --build node miner
```

Node only:

```bash
docker compose up --build node
```

Miner only:

```bash
docker compose up --build miner
```

## Stop

```bash
docker compose down
```

## Inspect

```bash
docker compose ps
docker compose logs -f node
docker compose logs -f miner
```

Memory and restart monitoring:

```bash
docker stats chipcoin-testnet-node-1
docker inspect chipcoin-testnet-node-1 --format '{{.RestartCount}}'
docker compose logs node | grep 'runtime memory metrics'
```

The node compose service uses `CHIPCOIN_MEMORY_LIMIT:-2g` as a configurable
guardrail. Validate the value in testnet before tightening it.

## Notes

- The node runtime currently does not use a wallet file.
- The miner runtime does use `MINER_WALLET_FILE`.
- The miner no longer keeps a local chain database.
- `MINING_WORKER_COUNT` can be raised above `1` to use multiple local CPU cores
  inside one miner container.
- The default Docker profile is public testnet.
- The default node HTTP API is published on `http://127.0.0.1:28081`; do not expose it directly to the internet unless you intentionally override `NODE_HTTP_PUBLISH_HOST`.
- Use public P2P `28444/tcp` and local-only HTTP `127.0.0.1:28081`; public firewall rules should expose only P2P.
- Testnet miner defaults should stay conservative (`MINING_MIN_INTERVAL_SECONDS=10.0`, `MINING_NONCE_BATCH_SIZE=50000`) for multi-node public runs.
- Devnet is still available via `.env.devnet.example` and uses P2P `18444/tcp` plus localhost HTTP `8081`.
- Local override files are for ports, extra bind mounts, and machine-specific behavior only. Keep secrets and runtime state out of the repository.
