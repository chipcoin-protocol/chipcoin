# Public Testnet Candidate

This page is the operator runbook for joining the current Chipcoin public
testnet candidate from the GitHub repository.

Devnet remains separate and available as a fallback environment.

## Testnet Parameters

- Network: `testnet`
- P2P public port: `28444/tcp`
- HTTP API port: `28081/tcp`
- HTTP publish host: `127.0.0.1`
- Default node database: `/var/lib/chipcoin/data/node-testnet.sqlite3`
- Default snapshot file: `/var/lib/chipcoin/data/node-testnet.snapshot`
- Default miner endpoint in Docker Compose: `http://node:28081`
- Conservative miner defaults: `MINING_MIN_INTERVAL_SECONDS=10.0`, `MINING_NONCE_BATCH_SIZE=50000`

Security boundary:

- expose only `28444/tcp` publicly
- do not expose `28081/tcp` publicly
- expose HTTP through a reverse proxy only if you intentionally operate a public API endpoint

## Generate `.env.testnet` With The Wizard

From the repository root:

```bash
python3 scripts/setup/wizard.py
```

Choose:

- setup mode: `quick` for standard public-testnet candidate defaults, or `custom` when you need explicit peers
- role: `Full node`, `Miner`, or `Reward node`
- network: `testnet`
- environment file: accept `.env.testnet`

For a full node or reward node, enter your public P2P host/IP if the node accepts
inbound internet connections. Use port `28444`.

The wizard can generate or import miner and reward-node wallet files. It does
not fund wallets. Reward-node registration and renewal require CHC on the
reward-node wallet.

## Run A Testnet Node

Start the node:

```bash
docker compose --env-file .env.testnet -p chipcoin-testnet up -d --build node
```

Verify ports:

```bash
sudo ss -ltnp | grep -E ':28444|:28081'
```

Expected:

```text
127.0.0.1:28081
0.0.0.0:28444
[::]:28444
```

Check sync:

```bash
curl -s http://127.0.0.1:28081/v1/status \
  | jq '{height, tip_hash, sync_phase, peer_count, handshaken_peer_count, operational_peer_count, operator_summary}'
```

Watch logs:

```bash
docker compose --env-file .env.testnet -p chipcoin-testnet logs -f node
```

## Run A Testnet Miner

The miner requires a wallet file configured by `MINER_WALLET_FILE`.

Start miner only after the node is synced:

```bash
docker compose --env-file .env.testnet -p chipcoin-testnet up -d --build miner
```

Inspect miner logs:

```bash
docker compose --env-file .env.testnet -p chipcoin-testnet logs miner --since 2m
```

The conservative testnet miner defaults are intentional. Do not lower
`MINING_MIN_INTERVAL_SECONDS` for public multi-node tests unless you are
explicitly stress-testing fork convergence.

## Register A Reward Node

A reward node is a full node plus an on-chain reward-node registration.

Generate or import a reward wallet with the wizard, or manually:

```bash
docker compose --env-file .env.testnet -p chipcoin-testnet exec node \
  chipcoin --network testnet wallet-generate \
  --wallet-file /var/lib/chipcoin/wallets/testnet-reward-node-wallet.json
```

Read wallet address and public key:

```bash
docker compose --env-file .env.testnet -p chipcoin-testnet exec node \
  chipcoin --network testnet wallet-address \
  --wallet-file /var/lib/chipcoin/wallets/testnet-reward-node-wallet.json
```

Fund the reward wallet before registration. Then register:

```bash
REWARD_NODE_ID="testnet-reward-node-example"
REWARD_WALLET="/var/lib/chipcoin/wallets/testnet-reward-node-wallet.json"
REWARD_ADDR="$(docker compose --env-file .env.testnet -p chipcoin-testnet exec -T node \
  chipcoin --network testnet wallet-address --wallet-file "$REWARD_WALLET" | jq -r .address)"
REWARD_PUBKEY="$(docker compose --env-file .env.testnet -p chipcoin-testnet exec -T node \
  chipcoin --network testnet wallet-address --wallet-file "$REWARD_WALLET" | jq -r .public_key_hex)"

docker compose --env-file .env.testnet -p chipcoin-testnet exec node \
  chipcoin --network testnet --data /runtime/node.sqlite3 register-reward-node \
  --wallet-file "$REWARD_WALLET" \
  --node-id "$REWARD_NODE_ID" \
  --payout-address "$REWARD_ADDR" \
  --node-pubkey-hex "$REWARD_PUBKEY" \
  --declared-host your-public-host.example \
  --declared-port 28444
```

Enable automation in `.env.testnet`:

```dotenv
REWARD_NODE_AUTO_NODE_ID=testnet-reward-node-example
REWARD_NODE_AUTO_OWNER_WALLET_FILE=/var/lib/chipcoin/wallets/testnet-reward-node-wallet.json
REWARD_NODE_AUTO_ATTEST_WALLET_FILE=/var/lib/chipcoin/wallets/testnet-reward-node-wallet.json
REWARD_NODE_AUTO_DECLARED_HOST=your-public-host.example
REWARD_NODE_AUTO_DECLARED_PORT=28444
REWARD_NODE_AUTO_RENEW_ENABLED=true
REWARD_NODE_AUTO_ATTEST_ENABLED=true
```

Restart node after changing `.env.testnet`:

```bash
docker compose --env-file .env.testnet -p chipcoin-testnet up -d --build node
```

Check reward-node status:

```bash
docker compose --env-file .env.testnet -p chipcoin-testnet exec node \
  chipcoin --network testnet --data /runtime/node.sqlite3 reward-node-status \
  --node-id "$REWARD_NODE_ID" \
  | jq '{node_id, active, eligibility_status, eligibility_reason, last_renewal_epoch, last_renewal_height}'
```

Check reward epochs:

```bash
docker compose --env-file .env.testnet -p chipcoin-testnet exec node \
  chipcoin --network testnet --data /runtime/node.sqlite3 reward-epoch-summary \
  --epoch-index 12 \
  | jq '{epoch_index, settlement_exists, settlement_status, rewarded_node_count, payout_totals, reward_entries}'
```

## Troubleshooting

### `docker-compose.override.yml` exposes devnet ports

Docker Compose automatically loads `docker-compose.override.yml`. If a legacy
override publishes `8081` or `18444`, it can make a testnet container expose
devnet ports.

Inspect:

```bash
ls -la docker-compose*.yml
grep -R "8081\|18444\|container_name" docker-compose*.yml
docker compose --env-file .env.testnet -p chipcoin-testnet config | grep -A20 'ports:'
```

Bypass the override:

```bash
docker compose -f docker-compose.yml --env-file .env.testnet -p chipcoin-testnet up -d --build node
```

Or rename it:

```bash
mv docker-compose.override.yml docker-compose.override.yml.legacy
```

### HTTP is bound publicly

Check listeners:

```bash
sudo ss -ltnp | grep -E ':28444|:28081'
```

If you see `0.0.0.0:28081`, set:

```dotenv
NODE_HTTP_PUBLISH_HOST=127.0.0.1
```

Restart:

```bash
docker compose --env-file .env.testnet -p chipcoin-testnet up -d --build node
```

### NAT or firewall blocks peers

Inbound peers require `28444/tcp` forwarded to the node host. Outbound-only nodes
can sync, but they do not help other peers dial back.

Check peer status:

```bash
curl -s http://127.0.0.1:28081/v1/peers/summary | jq
```

### Peer warnings

Check whether the node is actually synced before acting on warnings:

```bash
curl -s http://127.0.0.1:28081/v1/status \
  | jq '{height, tip_hash, sync_phase, operator_summary}'
```

If `sync_phase` is `synced`, the tip matches other nodes, and
`operator_summary.warnings` is empty, the node is healthy.

### Node behind old config

Regenerate `.env.testnet` with the wizard or verify these values:

```bash
grep -E '^(CHIPCOIN_NETWORK|NODE_P2P_BIND_PORT|NODE_HTTP_BIND_PORT|NODE_HTTP_PUBLISH_HOST|MINING_NODE_URLS|MINING_MIN_INTERVAL_SECONDS)=' .env.testnet
```

Expected:

```dotenv
CHIPCOIN_NETWORK=testnet
NODE_P2P_BIND_PORT=28444
NODE_HTTP_BIND_PORT=28081
NODE_HTTP_PUBLISH_HOST=127.0.0.1
MINING_NODE_URLS=http://node:28081
MINING_MIN_INTERVAL_SECONDS=10.0
```

### Compare height and tip across nodes

Run on each node:

```bash
curl -s http://127.0.0.1:28081/v1/status \
  | jq '{height, tip_hash, sync_phase, handshaken_peer_count, operational_peer_count, operator_summary}'
```
