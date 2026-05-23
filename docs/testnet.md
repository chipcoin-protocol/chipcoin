# Public Testnet Candidate

This page is the operator runbook for joining the current Chipcoin public
testnet candidate from the GitHub repository.

Devnet remains separate and available as a fallback environment.

For the fastest fresh-node onboarding path, use `docs/testnet-fast-join.md`.

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
- expose HTTP through a reverse proxy only if you intentionally operate an allowlisted public API endpoint

Public HTTP service split:

- `https://explorer.chipcoinprotocol.com` is readonly explorer UI/API.
- `https://bootstrap.chipcoinprotocol.com` is P2P peer discovery only.
- `https://testnet-api.chipcoinprotocol.com` is the public wallet-safe API for testnet.
- raw node HTTP stays bound to localhost/private interfaces.

The wallet-safe API pattern is network-extensible. Future mainnet should use a
separate hostname and the same allowlist model rather than exposing raw node
HTTP.

## Generate `.env` With The Wizard

From the repository root:

```bash
python3 scripts/setup/wizard.py
```

Choose:

- setup mode: `quick` for standard public-testnet candidate defaults, or `custom` when you need explicit peers
- role: `Full node`, `Miner`, or `Reward node`
- network: `testnet`
- environment file: accept `.env`

For a full node or reward node, enter your public P2P host/IP if the node accepts
inbound internet connections. Use port `28444`.

The wizard can generate or import miner and reward-node wallet files. It does
not fund wallets. Reward-node registration and renewal require CHC on the
reward-node wallet.

## Run A Testnet Node

Start the node:

```bash
docker compose up -d --build node
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
docker compose logs -f node
```

## Optional Testnet Snapshot Bootstrap

Full sync from genesis remains supported. A testnet snapshot is an optional
onboarding shortcut for operators who trust the published snapshot source.

Official Phase 1 manifest target:

```text
https://chipcoinprotocol.com/downloads/snapshots/testnet/latest.manifest.json
```

To opt in during wizard setup, choose `snapshot` or `auto` bootstrap and use
that manifest URL. The wizard downloads the snapshot, checks the file SHA-256
from the manifest, imports it into `NODE_DATA_PATH`, and then the node delta
syncs from the snapshot anchor to the live tip.

Manual restore into a fresh local database:

```bash
curl -fsSL https://chipcoinprotocol.com/downloads/snapshots/testnet/latest.manifest.json \
  -o /tmp/chipcoin-testnet-latest.manifest.json
SNAPSHOT_URL="$(jq -r '.snapshots[0].snapshot_url' /tmp/chipcoin-testnet-latest.manifest.json)"
SNAPSHOT_SHA256="$(jq -r '.snapshots[0].checksum_sha256' /tmp/chipcoin-testnet-latest.manifest.json)"
curl -fsSL "$SNAPSHOT_URL" -o /tmp/chipcoin-testnet.snapshot
printf '%s  %s\n' "$SNAPSHOT_SHA256" /tmp/chipcoin-testnet.snapshot | sha256sum -c -
chipcoin --network testnet --data /var/lib/chipcoin/data/node-testnet.sqlite3 \
  snapshot-import --snapshot-file /tmp/chipcoin-testnet.snapshot --snapshot-reset
```

Verify after restore and node start:

```bash
curl -s http://127.0.0.1:28081/v1/status \
  | jq '{network,height,tip_hash,sync_phase}'
curl -s https://explorer.chipcoinprotocol.com/api/testnet/v1/status \
  | jq '{network,height,tip_hash,sync_phase}'
```

Safety notes:

- keep `28081/tcp` bound to `127.0.0.1`
- do not publish node HTTP directly
- snapshots do not change consensus and are not required for joining testnet
- a network mismatch is rejected during import
- Phase 1 requires SHA-256 file checksum verification
- chipcom publishes signed snapshots; consumers may still use checksum-only
  restore or enforce the known Ed25519 signer explicitly

## Publish A Testnet Snapshot

This is operator-driven Phase 1 publishing. Do not run it from an unsynced node.
The current chipcom production model uses a signed testnet publisher script
plus a systemd timer. The old devnet publisher is legacy and should stay
disabled unless an operator intentionally resumes devnet publishing.

Expected active chipcom units:

```text
chipcoin-testnet-snapshot.service
chipcoin-testnet-snapshot.timer
```

Legacy devnet units, if still present, should be disabled:

```text
chipcoin-snapshot.service
chipcoin-snapshot.timer
```

The testnet publisher writes:

```text
/var/www/chipcoin-central/website/downloads/snapshots/testnet/latest.manifest.json
/var/www/chipcoin-central/website/downloads/snapshots/testnet/latest.snapshot
```

Both publishers sign snapshots with the configured local Ed25519 snapshot key
and copy the signed snapshot out of the node container with `docker compose cp`.
Do not rely on an implicit `/snapshots` bind mount.

The expected testnet service settings are:

```bash
NETWORK="testnet"
BASE_URL="https://chipcoinprotocol.com/downloads/snapshots/testnet"
COMPOSE_CMD="docker compose"
STATUS_URL="http://127.0.0.1:28081/v1/status"
```

Manual fallback host CLI flow:

```bash
CHIPCOIN_NETWORK=testnet \
CHIPCOIN_DATA=/var/lib/chipcoin/data/node-testnet.sqlite3 \
SNAPSHOT_OUTPUT_DIR=/tmp/chipcoin-testnet-snapshot \
SNAPSHOT_SOURCE_NODE=chipcom \
SNAPSHOT_SIGNING_KEY_FILE=/home/komarek/.config/chipcoin/snapshot_signing.key \
scripts/ops/build-testnet-snapshot.sh
```

If no signing key is configured, the same script still builds a checksum-only
manifest suitable for manual testing:

```bash
CHIPCOIN_NETWORK=testnet \
CHIPCOIN_DATA=/var/lib/chipcoin/data/node-testnet.sqlite3 \
SNAPSHOT_OUTPUT_DIR=/tmp/chipcoin-testnet-snapshot \
SNAPSHOT_SOURCE_NODE=chipcom \
scripts/ops/build-testnet-snapshot.sh
```

Systemd verification on chipcom:

```bash
systemctl list-timers | grep chipcoin
systemctl status chipcoin-testnet-snapshot.timer --no-pager
systemctl status chipcoin-testnet-snapshot.service --no-pager
journalctl -u chipcoin-testnet-snapshot.service -n 80 --no-pager
```

Public verification:

```bash
curl -fsS https://chipcoinprotocol.com/downloads/snapshots/testnet/latest.manifest.json \
  | jq '.snapshots[0] | {network,snapshot_height,snapshot_block_hash,checksum_sha256,signer_pubkeys,snapshot_url}'
curl -fsSI https://chipcoinprotocol.com/downloads/snapshots/testnet/latest.snapshot
```

Keep these public files:

- `latest.snapshot`
- `latest.manifest.json`
- `archive/chipcoin-testnet-<timestamp>-<height>.snapshot`
- `archive/chipcoin-testnet-<timestamp>-<height>.manifest.json`

Manifest schema for Phase 1:

```json
{
  "network": "testnet",
  "height": 1801,
  "tip_hash": "00002087b2dfc6ee2d89c013e9a78f8b26454f9372882f2d61de604b04522847",
  "created_at": 1778788432,
  "file_name": "testnet-snapshot-height-1801.snapshot",
  "snapshot_url": "https://chipcoinprotocol.com/downloads/snapshots/testnet/testnet-snapshot-height-1801.snapshot",
  "sha256": "<file_sha256>",
  "checksum_sha256": "<file_sha256>",
  "size_bytes": 123456,
  "source_node": "chipcom",
  "format_version": 2,
  "snapshots": [
    {
      "network": "testnet",
      "snapshot_url": "https://chipcoinprotocol.com/downloads/snapshots/testnet/testnet-snapshot-height-1801.snapshot",
      "format_version": 2,
      "snapshot_height": 1801,
      "snapshot_block_hash": "00002087b2dfc6ee2d89c013e9a78f8b26454f9372882f2d61de604b04522847",
      "created_at": 1778788432,
      "checksum_sha256": "<file_sha256>",
      "file_name": "testnet-snapshot-height-1801.snapshot",
      "size_bytes": 123456,
      "source_node": "chipcom",
      "signer_pubkeys": [
        "147ce2ece1046008f465cb471ffe6f6a12ebd3c63ba39d8fd4dc9cd290816b0c"
      ],
      "snapshot_trust_mode": "signed"
    }
  ]
}
```

The top-level fields are for humans/operators. The `snapshots[]` entry is the
wizard-compatible schema.

## Run A Testnet Miner

The miner requires a wallet file configured by `MINER_WALLET_FILE`.

Start miner only after the node is synced:

```bash
docker compose up -d --build miner
```

Inspect miner logs:

```bash
docker compose logs miner --since 2m
```

The conservative testnet miner defaults are intentional. Do not lower
`MINING_MIN_INTERVAL_SECONDS` for public multi-node tests unless you are
explicitly stress-testing fork convergence.

## Register A Reward Node

A reward node is a full node plus an on-chain reward-node registration.

Generate or import a reward wallet with the wizard, or manually:

```bash
docker compose exec node \
  chipcoin --network testnet wallet-generate \
  --wallet-file /var/lib/chipcoin/wallets/testnet-reward-node-wallet.json
```

Read wallet address and public key:

```bash
docker compose exec node \
  chipcoin --network testnet wallet-address \
  --wallet-file /var/lib/chipcoin/wallets/testnet-reward-node-wallet.json
```

Fund the reward wallet before registration. Then register:

The setup wizard prints the exact registration command at the end of a
reward-node setup. Prefer that generated command because it includes the
wallet-specific `--node-pubkey-hex`, node id, declared host, and declared port.

Funding note: the public faucet may be limited to one small claim per day. If it
grants `1 CHC/day`, the first claim covers the initial registration target and a
later claim or another funded testnet wallet should be used for renewal buffer.

```bash
REWARD_NODE_ID="testnet-reward-node-example"
REWARD_WALLET="/var/lib/chipcoin/wallets/testnet-reward-node-wallet.json"
REWARD_ADDR="$(docker compose exec -T node \
  chipcoin --network testnet wallet-address --wallet-file "$REWARD_WALLET" | jq -r .address)"
REWARD_PUBKEY="$(docker compose exec -T node \
  chipcoin --network testnet wallet-address --wallet-file "$REWARD_WALLET" | jq -r .public_key_hex)"

docker compose exec node \
  chipcoin --network testnet --data /runtime/node.sqlite3 register-reward-node \
  --wallet-file "$REWARD_WALLET" \
  --node-id "$REWARD_NODE_ID" \
  --payout-address "$REWARD_ADDR" \
  --node-pubkey-hex "$REWARD_PUBKEY" \
  --declared-host your-public-host.example \
  --declared-port 28444
```

Enable automation in `.env`:

```dotenv
REWARD_NODE_AUTO_NODE_ID=testnet-reward-node-example
REWARD_NODE_AUTO_OWNER_WALLET_FILE=/var/lib/chipcoin/wallets/testnet-reward-node-wallet.json
REWARD_NODE_AUTO_ATTEST_WALLET_FILE=/var/lib/chipcoin/wallets/testnet-reward-node-wallet.json
REWARD_NODE_AUTO_DECLARED_HOST=your-public-host.example
REWARD_NODE_AUTO_DECLARED_PORT=28444
REWARD_NODE_AUTO_RENEW_ENABLED=true
REWARD_NODE_AUTO_ATTEST_ENABLED=true
```

Restart node after changing `.env`:

```bash
docker compose up -d --build node
```

Check reward-node status:

```bash
docker compose exec node \
  chipcoin --network testnet --data /runtime/node.sqlite3 reward-node-status \
  --node-id "$REWARD_NODE_ID" \
  | jq '{node_id, active, eligibility_status, eligibility_reason, last_renewal_epoch, last_renewal_height}'
```

Check reward epochs:

```bash
docker compose exec node \
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
docker compose config | grep -A20 'ports:'
```

Bypass the override:

```bash
docker compose -f docker-compose.yml up -d --build node
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
docker compose up -d --build node
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

Regenerate `.env` with the wizard or verify these values:

```bash
grep -E '^(CHIPCOIN_NETWORK|NODE_P2P_BIND_PORT|NODE_HTTP_BIND_PORT|NODE_HTTP_PUBLISH_HOST|MINING_NODE_URLS|MINING_MIN_INTERVAL_SECONDS)=' .env
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
