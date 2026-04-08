# Miner

## Purpose

The Chipcoin miner is a separate runtime component that:

- requests ready-to-hash block templates from one or more nodes
- mutates nonce, extra nonce, and timestamp within node-issued limits
- submits solved blocks back to a node over HTTP

## Runtime Inputs

Relevant `.env` keys:

- `CHIPCOIN_RUNTIME_DIR`
- `CHIPCOIN_NETWORK`
- `MINER_LOG_LEVEL`
- `MINER_WALLET_FILE`
- `MINING_MIN_INTERVAL_SECONDS`
- `MINING_NODE_URLS`
- `MINING_MINER_ID`
- `MINING_POLLING_INTERVAL_SECONDS`
- `MINING_REQUEST_TIMEOUT_SECONDS`
- `MINING_NONCE_BATCH_SIZE`
- `MINING_TEMPLATE_REFRESH_SKEW_SECONDS`

## Wallet Requirement

The miner requires a wallet JSON file.

Example creation:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
sudo mkdir -p /var/lib/chipcoin/wallets
sudo chown -R "$USER:$USER" /var/lib/chipcoin
chipcoin wallet-generate --wallet-file /var/lib/chipcoin/wallets/chipcoin-wallet.json
```

Show the payout address:

```bash
chipcoin wallet-address --wallet-file /var/lib/chipcoin/wallets/chipcoin-wallet.json
```

## Start

```bash
docker compose up --build miner
```

Detached:

```bash
docker compose up -d --build miner
```

## Logs

```bash
docker compose logs -f miner
```

## Notes

- The miner wallet is operationally used in the current public release.
- Rewards are paid to the address derived from `MINER_WALLET_FILE`.
- Reward redistribution can be done later with standard wallet transactions.
- The miner no longer keeps a local chain database or performs historical sync.
- In the default Docker Compose stack, the miner points at `http://node:8081`.
- For a miner-only host, set `MINING_NODE_URLS=https://api.chipcoinprotocol.com`.
- The recommended runtime directory is outside the repo, for example `/var/lib/chipcoin` on a stable Linux host.
- Remote miners trust their selected node endpoints for template quality and freshness.

See [Mining Architecture](/home/komarek/Documents/CODEX/Chipcoin-v2/docs/mining-architecture.md).
