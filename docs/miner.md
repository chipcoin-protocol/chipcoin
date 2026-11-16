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
- `MINING_WORKER_COUNT`
- `MINING_TEMPLATE_REFRESH_SKEW_SECONDS`

## Wallet Requirement

The miner requires a wallet JSON file.

For a new Mainnet installation, use the wizard to generate or import the miner
wallet into the isolated Mainnet runtime. Back it up before mining. The wizard
does not start the miner. If using the native CLI instead, install its native
build dependencies first (see `docs/setup-wizard.md`) and create the wallet at
the path in `.env.mainnet`:

```bash
.venv/bin/chipcoin --network mainnet wallet-generate \
  --wallet-file /var/lib/chipcoin-mainnet-official/keys/miner-wallet.json
```

Show the payout address:

```bash
.venv/bin/chipcoin --network mainnet wallet-address \
  --wallet-file /var/lib/chipcoin-mainnet-official/keys/miner-wallet.json
```

## Start

```bash
docker compose --env-file .env.mainnet up --build miner
```

Detached:

```bash
docker compose --env-file .env.mainnet up -d --build miner
```

## Logs

```bash
docker compose --env-file .env.mainnet logs -f miner
```

## Notes

- The miner wallet is operationally used in the current public release.
- Rewards are paid to the address derived from `MINER_WALLET_FILE`.
- Reward redistribution can be done later with standard wallet transactions.
- The miner no longer keeps a local chain database or performs historical sync.
- `MINING_WORKER_COUNT` controls local mining process parallelism. The default
  is `1`; set it to the number of CPU cores you want one miner container to use.
- On Mainnet the miner uses the private in-stack node API `http://node:8080`.
  Explicit Testnet installs use `http://node:28081`.
- Do not mine through the public wallet-safe APIs; they are not miner endpoints.
- For a miner-only host, set `MINING_NODE_URLS` to a local/private full node API you operate or explicitly trust.
- Keep the runtime directory outside the repo; the default Mainnet path is
  `/var/lib/chipcoin-mainnet-official` on Linux.
- Remote miners trust their selected node endpoints for template quality and freshness.

See [Mining Architecture](mining-architecture.md).
