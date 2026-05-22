# Join Testnet Fast

This runbook starts a fresh Chipcoin testnet node from the public signed
snapshot, then uses the public bootstrap service to connect and delta-sync to
the live testnet tip.

Use this path when you want faster onboarding than full sync from genesis.
Full sync remains supported.

## Public Endpoints

Snapshot manifest:

```text
https://chipcoinprotocol.com/downloads/snapshots/testnet/latest.manifest.json
```

Latest snapshot shortcut:

```text
https://chipcoinprotocol.com/downloads/snapshots/testnet/latest.snapshot
```

Bootstrap peers:

```text
https://bootstrap.chipcoinprotocol.com/v1/peers?network=testnet
```

Explorer status:

```text
https://explorer.chipcoinprotocol.com/api/testnet/v1/status
```

Wallet-safe API:

```text
https://testnet-api.chipcoinprotocol.com/v1/status
```

Trusted testnet snapshot signer:

```text
147ce2ece1046008f465cb471ffe6f6a12ebd3c63ba39d8fd4dc9cd290816b0c
```

Example validated snapshot anchor from the May 2026 public testnet candidate:

```text
height=1809
tip=0000111fc480cdeee7ff460d927ce33d0467eb28d14beb23eb1b89a7d93c042f
```

Always treat the manifest as authoritative for the current snapshot height,
tip hash, checksum, and signer set.

## Security Boundary

Expose only the testnet P2P port publicly:

```text
28444/tcp
```

Never expose the node HTTP API publicly:

```text
28081/tcp must stay bound to 127.0.0.1
```

The public explorer uses a readonly server-side proxy. Do not publish the raw
node HTTP listener.

Normal browser-wallet users can use `https://testnet-api.chipcoinprotocol.com`,
which is an allowlisted wallet-safe proxy for reads and `POST /v1/tx/submit`.
Operators can still point the wallet at local node HTTP, for example
`http://127.0.0.1:28081`.

## Prerequisites

- Linux host with Docker Compose or a local Python environment.
- `git`, `curl`, `jq`, and `sha256sum`.
- Inbound TCP `28444` open if the node should contribute public P2P capacity.
- No legacy Compose override that publishes devnet ports into the testnet stack.

Clone and enter the repository:

```bash
git clone https://github.com/chipcoin-protocol/chipcoin.git
cd chipcoin
```

If the repository already exists:

```bash
git pull origin main
```

## Quick Validation Of Public Services

```bash
curl -s https://chipcoinprotocol.com/downloads/snapshots/testnet/latest.manifest.json | jq
curl -s 'https://bootstrap.chipcoinprotocol.com/v1/peers?network=testnet' | jq
curl -s https://explorer.chipcoinprotocol.com/api/testnet/v1/status | jq
curl -s https://testnet-api.chipcoinprotocol.com/v1/status | jq
```

The manifest should contain `network: testnet`, a snapshot entry, a
`checksum_sha256`, and the trusted signer pubkey shown above.

## Wizard Path

The setup wizard supports snapshot bootstrap as an installation-time
optimization.

```bash
python3 scripts/setup/wizard.py
```

Choose:

- role: `Full node`
- network: `testnet`
- environment file: `.env`
- discovery: bootstrap seed service
- bootstrap URL: `https://bootstrap.chipcoinprotocol.com`
- node bootstrap: `snapshot` or `auto`
- manifest URL: `https://chipcoinprotocol.com/downloads/snapshots/testnet/latest.manifest.json`
- trust mode: `enforce` when you provide a trusted keys file, otherwise `warn`

For strict signature enforcement, create a trusted keys file:

```bash
mkdir -p /var/lib/chipcoin/config
printf '%s\n' 147ce2ece1046008f465cb471ffe6f6a12ebd3c63ba39d8fd4dc9cd290816b0c \
  > /var/lib/chipcoin/config/testnet-snapshot-trusted-keys.txt
```

When prompted, use that path as the trusted snapshot keys file.

Start the node after the wizard finishes:

```bash
docker compose -f docker-compose.yml up -d --build node
```

## Manual Docker Path

Use this path when you want explicit control over the snapshot import and
runtime configuration.

Create fresh runtime paths:

```bash
RUNTIME=/var/lib/chipcoin/testnet-fast
sudo mkdir -p "$RUNTIME"
sudo chown -R "$USER:$USER" "$RUNTIME"
touch "$RUNTIME/node.sqlite3"
```

Download and verify the public snapshot:

```bash
curl -fsSL https://chipcoinprotocol.com/downloads/snapshots/testnet/latest.manifest.json \
  -o "$RUNTIME/latest.manifest.json"

SNAPSHOT_URL="$(jq -r '.snapshots[0].snapshot_url' "$RUNTIME/latest.manifest.json")"
SNAPSHOT_SHA256="$(jq -r '.snapshots[0].checksum_sha256' "$RUNTIME/latest.manifest.json")"
SNAPSHOT_PUBKEY="$(jq -r '.snapshots[0].signer_pubkeys[0]' "$RUNTIME/latest.manifest.json")"

test "$SNAPSHOT_PUBKEY" = "147ce2ece1046008f465cb471ffe6f6a12ebd3c63ba39d8fd4dc9cd290816b0c"

curl -fsSL "$SNAPSHOT_URL" -o "$RUNTIME/testnet.snapshot"
printf '%s  %s\n' "$SNAPSHOT_SHA256" "$RUNTIME/testnet.snapshot" | sha256sum -c -
```

Import the snapshot with signature enforcement:

```bash
docker compose -f docker-compose.yml run --rm --no-deps \
  -v "$RUNTIME:/runtime-fast" \
  --entrypoint chipcoin node \
  --network testnet \
  --data /runtime-fast/node.sqlite3 \
  snapshot-import \
  --snapshot-file /runtime-fast/testnet.snapshot \
  --snapshot-reset \
  --snapshot-trust-mode enforce \
  --snapshot-trusted-key "$SNAPSHOT_PUBKEY"
```

Verify the imported database:

```bash
docker compose -f docker-compose.yml run --rm --no-deps \
  -v "$RUNTIME:/runtime-fast" \
  --entrypoint chipcoin node \
  --network testnet \
  --data /runtime-fast/node.sqlite3 \
  status \
  | jq '{network,height,tip_hash,sync_phase}'
```

Create `.env.testnet.fast`:

```bash
cat > .env.testnet.fast <<EOF
CHIPCOIN_NETWORK=testnet
COMPOSE_PROJECT_NAME=chipcoin-testnet-fast
CHIPCOIN_RUNTIME_DIR=$RUNTIME
NODE_DATA_PATH=$RUNTIME/node.sqlite3
NODE_LOG_LEVEL=INFO
NODE_P2P_BIND_PORT=28444
NODE_HTTP_BIND_PORT=28081
NODE_HTTP_PUBLISH_HOST=127.0.0.1
CHIPCOIN_HTTP_ALLOWED_ORIGINS=
CONNECT_INTERVAL_SECONDS=5.0
PING_INTERVAL_SECONDS=2.0
P2P_READ_TIMEOUT_SECONDS=15.0
P2P_WRITE_TIMEOUT_SECONDS=15.0
P2P_HANDSHAKE_TIMEOUT_SECONDS=5.0
MEMPOOL_RELAY_INTERVAL_SECONDS=1.0
SYNC_SCHEDULER_INTERVAL_SECONDS=1.0
PEER_RESOLUTION_CACHE_TTL_SECONDS=300
PEER_DISCOVERY_ENABLED=true
PEERBOOK_MAX_SIZE=1024
PEER_ADDR_MAX_PER_MESSAGE=250
PEER_ADDR_RELAY_LIMIT_PER_INTERVAL=250
PEER_ADDR_RELAY_INTERVAL_SECONDS=30
PEER_STALE_AFTER_SECONDS=604800
PEER_RETRY_BACKOFF_BASE_SECONDS=1
PEER_RETRY_BACKOFF_MAX_SECONDS=30
MAX_OUTBOUND_SESSIONS=8
MAX_INBOUND_SESSIONS=32
INBOUND_HANDSHAKE_RATE_LIMIT_PER_MINUTE=12
MIN_STABLE_SESSION_SECONDS=30
PEER_DISCOVERY_STARTUP_PREFER_PERSISTED=true
HEADERS_SYNC_ENABLED=true
HEADERS_MAX_PER_MESSAGE=2000
BLOCK_DOWNLOAD_WINDOW_SIZE=128
BLOCK_MAX_INFLIGHT_PER_PEER=16
BLOCK_REQUEST_TIMEOUT_SECONDS=15
HEADERS_SYNC_PARALLEL_PEERS=2
HEADERS_SYNC_START_HEIGHT_GAP_THRESHOLD=1
INITIAL_SYNC_CONSERVATIVE_DEFAULTS=true
BOOTSTRAP_PEER_LIMIT=4
BOOTSTRAP_ANNOUNCE_ENABLED=false
BOOTSTRAP_REFRESH_INTERVAL_SECONDS=60
PEER_MISBEHAVIOR_WARNING_THRESHOLD=25
PEER_MISBEHAVIOR_DISCONNECT_THRESHOLD=50
PEER_MISBEHAVIOR_BAN_THRESHOLD=100
PEER_MISBEHAVIOR_BAN_DURATION_SECONDS=1800
PEER_MISBEHAVIOR_DECAY_INTERVAL_SECONDS=300
PEER_MISBEHAVIOR_DECAY_STEP=5
REWARD_NODE_AUTO_NODE_ID=
REWARD_NODE_AUTO_OWNER_WALLET_FILE=
REWARD_NODE_AUTO_ATTEST_WALLET_FILE=
REWARD_NODE_AUTO_DECLARED_HOST=
REWARD_NODE_AUTO_DECLARED_PORT=
REWARD_NODE_AUTO_RENEW_ENABLED=false
REWARD_NODE_AUTO_ATTEST_ENABLED=false
REWARD_NODE_AUTO_POLL_INTERVAL_SECONDS=5.0
NODE_DIRECT_PEERS=
NODE_DIRECT_PEER=
NODE_BOOTSTRAP_URL=https://bootstrap.chipcoinprotocol.com
NODE_PUBLIC_HOST=
NODE_PUBLIC_P2P_PORT=28444
DIRECT_PEERS=
DIRECT_PEER=
BOOTSTRAP_URL=
MINER_LOG_LEVEL=INFO
MINER_WALLET_FILE=$RUNTIME/miner-wallet.json
MINING_MIN_INTERVAL_SECONDS=10.0
MINING_NODE_URLS=http://node:28081
MINING_MINER_ID=
MINING_POLLING_INTERVAL_SECONDS=2.0
MINING_REQUEST_TIMEOUT_SECONDS=10.0
MINING_NONCE_BATCH_SIZE=50000
MINING_TEMPLATE_REFRESH_SKEW_SECONDS=1
EOF
```

Start only the node:

```bash
docker compose -f docker-compose.yml --env-file .env.testnet.fast -p chipcoin-testnet-fast up -d --build node
```

Using `-f docker-compose.yml` is intentional: it avoids accidental loading of a
legacy `docker-compose.override.yml`.

## Verify The Join

Check local status:

```bash
curl -s http://127.0.0.1:28081/v1/status \
  | jq '{network,height,tip_hash,sync_phase,peer_count,handshaken_peer_count,operational_peer_count,operator_summary}'
```

Check peer health:

```bash
curl -s http://127.0.0.1:28081/v1/peers/summary | jq
```

Compare with explorer:

```bash
curl -s https://explorer.chipcoinprotocol.com/api/testnet/v1/status \
  | jq '{network,height,tip_hash,sync_phase}'
```

Inspect startup logs for bootstrap discovery and handshake:

```bash
docker compose -f docker-compose.yml --env-file .env.testnet.fast -p chipcoin-testnet-fast logs node \
  | grep -E 'bootstrap|attempting outbound|outbound TCP connected|peer handshake complete|sync phase'
```

A healthy fast join should show:

- imported height at or near the snapshot anchor
- `bootstrap_url=https://bootstrap.chipcoinprotocol.com`
- outbound connection to a public testnet peer
- at least one handshaken/operational peer
- local height equal to the explorer tip or progressing toward it
- no HTTP listener published publicly

Verify ports:

```bash
docker compose -f docker-compose.yml --env-file .env.testnet.fast -p chipcoin-testnet-fast ps
sudo ss -ltnp | grep -E ':28444|:28081'
```

Expected:

```text
127.0.0.1:28081
0.0.0.0:28444
[::]:28444
```

## Troubleshooting

### `docker-compose.override.yml` changes ports or services

Always use:

```bash
docker compose -f docker-compose.yml --env-file .env.testnet.fast -p chipcoin-testnet-fast ...
```

If an override exists from devnet work, inspect or rename it:

```bash
ls -la docker-compose*.yml
grep -R "8081\|18444\|container_name" docker-compose*.yml
mv docker-compose.override.yml docker-compose.override.yml.legacy
```

### P2P or HTTP port is occupied

Check listeners:

```bash
sudo ss -ltnp | grep -E ':28444|:28081'
```

Use non-conflicting ports for a temporary test node:

```dotenv
NODE_P2P_BIND_PORT=38444
NODE_PUBLIC_P2P_PORT=38444
NODE_HTTP_BIND_PORT=38081
NODE_HTTP_PUBLISH_HOST=127.0.0.1
MINING_NODE_URLS=http://node:38081
```

### Signature verification fails

Confirm the manifest signer:

```bash
jq -r '.snapshots[0].signer_pubkeys[0]' "$RUNTIME/latest.manifest.json"
```

It must match:

```text
147ce2ece1046008f465cb471ffe6f6a12ebd3c63ba39d8fd4dc9cd290816b0c
```

If it does not match, do not import in enforce mode. Re-fetch the manifest or
wait for the publisher to repair the manifest.

### Checksum verification fails

Delete the local snapshot and download it again:

```bash
rm -f "$RUNTIME/testnet.snapshot"
curl -fsSL "$SNAPSHOT_URL" -o "$RUNTIME/testnet.snapshot"
printf '%s  %s\n' "$SNAPSHOT_SHA256" "$RUNTIME/testnet.snapshot" | sha256sum -c -
```

Do not import a snapshot with a checksum mismatch.

### Bootstrap returns no peers

Check the service:

```bash
curl -s 'https://bootstrap.chipcoinprotocol.com/v1/peers?network=testnet' | jq
```

If it returns an empty list, the node can still start from the snapshot but may
not discover peers until bootstrap is repaired or a manual peer is temporarily
provided. Manual peers are not part of the clean fast-join path.

### Node syncs from genesis instead of snapshot

Check status:

```bash
curl -s http://127.0.0.1:28081/v1/status \
  | jq '{bootstrap_mode,snapshot_anchor_height,height,sync_phase}'
```

Expected after import:

```text
bootstrap_mode=snapshot
snapshot_anchor_height=<manifest snapshot_height>
sync_phase=snapshot_imported or synced
```

If height starts near zero, the node is using a different `NODE_DATA_PATH` than
the database you imported into.

### Peer backoff warnings

Inspect peer summary:

```bash
curl -s http://127.0.0.1:28081/v1/peers/summary \
  | jq '{backoff_peer_count,banned_peer_count,operational_peer_count,operator_summary}'
```

One stale or backoff peer can be explainable during early discovery. The node is
healthy when it has at least one operational peer, no active bans, and the
explorer tip matches or is being approached.

## Stop Or Remove The Node

```bash
docker compose -f docker-compose.yml --env-file .env.testnet.fast -p chipcoin-testnet-fast down
```

Remove local test data only if you no longer need the node:

```bash
rm -rf "$RUNTIME"
```
