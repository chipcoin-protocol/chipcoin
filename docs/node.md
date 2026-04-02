# Node

## Purpose

The Chipcoin node maintains chain state, validates blocks and transactions, exposes the HTTP API, and participates in the P2P network.

The current public release does not use a node wallet file at runtime.

## Runtime Inputs

Relevant `.env` keys:

- `CHIPCOIN_RUNTIME_DIR`
- `CHIPCOIN_NETWORK`
- `NODE_DATA_PATH`
- `NODE_LOG_LEVEL`
- `NODE_P2P_BIND_PORT`
- `NODE_HTTP_BIND_PORT`
- `CHIPCOIN_HTTP_ALLOWED_ORIGINS`
- `DIRECT_PEER`
- `BOOTSTRAP_URL`
- `PEER_DISCOVERY_ENABLED`
- `PEERBOOK_MAX_SIZE`
- `PEER_ADDR_MAX_PER_MESSAGE`
- `PEER_ADDR_RELAY_LIMIT_PER_INTERVAL`
- `PEER_ADDR_RELAY_INTERVAL_SECONDS`
- `PEER_STALE_AFTER_SECONDS`
- `PEER_RETRY_BACKOFF_BASE_SECONDS`
- `PEER_RETRY_BACKOFF_MAX_SECONDS`
- `PEER_DISCOVERY_STARTUP_PREFER_PERSISTED`
- `HEADERS_SYNC_ENABLED`
- `HEADERS_MAX_PER_MESSAGE`
- `BLOCK_DOWNLOAD_WINDOW_SIZE`
- `BLOCK_MAX_INFLIGHT_PER_PEER`
- `BLOCK_REQUEST_TIMEOUT_SECONDS`
- `HEADERS_SYNC_PARALLEL_PEERS`
- `HEADERS_SYNC_START_HEIGHT_GAP_THRESHOLD`
- `PEER_MISBEHAVIOR_WARNING_THRESHOLD`
- `PEER_MISBEHAVIOR_DISCONNECT_THRESHOLD`
- `PEER_MISBEHAVIOR_BAN_THRESHOLD`
- `PEER_MISBEHAVIOR_BAN_DURATION_SECONDS`
- `PEER_MISBEHAVIOR_DECAY_INTERVAL_SECONDS`
- `PEER_MISBEHAVIOR_DECAY_STEP`

## Start

```bash
docker compose up --build node
```

Detached:

```bash
docker compose up -d --build node
```

## Stop

```bash
docker compose stop node
```

or:

```bash
docker compose down
```

## Logs

```bash
docker compose logs -f node
```

## HTTP API

Default local URL:

- `http://127.0.0.1:8081`

Useful endpoints:

- `GET /v1/status`
- `GET /v1/peers`
- `GET /v1/blocks`
- `GET /v1/block?height=<height>`
- `GET /v1/block?hash=<hash>`
- `GET /v1/tx/<txid>`
- `GET /v1/address/<address>`
- `GET /v1/address/<address>/utxos`
- `GET /v1/address/<address>/history`
- `GET /v1/mempool`
- `GET /v1/peers/summary`

`GET /v1/status` now includes a `sync` snapshot with:

- validated tip height/hash
- best known header height/hash
- current sync mode
- in-flight block request count
- header peers
- block peers
- stalled peers
- download window position

`GET /v1/peers` and `GET /v1/peers/summary` include peer misbehavior and temporary-ban diagnostics.

## Peer Discovery

Chipcoin uses bounded `getaddr` / `addr` discovery plus a persistent SQLite peerbook.

Peer source classes:

- `manual`: explicitly configured peers such as `DIRECT_PEER` or `chipcoin add-peer`
- `seed`: bootstrap-derived or local-seeding fallback peers
- `discovered`: peers learned from network gossip or successful inbound/outbound observations

Peer states exposed through diagnostics:

- `manual`
- `seed`
- `discovered`
- `good`
- `questionable`
- `banned`

Stored peer metadata now includes:

- source
- first/last seen timestamps
- last success / last failure
- success / failure counters
- reconnect backoff state
- temporary ban state
- misbehavior score
- quality score

Startup discovery order:

1. load persisted peers from the peerbook
2. prefer healthy persisted peers when available
3. fall back to explicit manual or seed peers when needed
4. continue learning through bounded `addr` gossip

Operational limits:

- incoming `addr` payloads are capped
- relayed peer batches are capped
- peer relay is rate-limited per session
- stale discovered peers are expired automatically
- the peerbook is trimmed to a bounded maximum size
- banned peers are excluded from relay and outbound selection

Useful operator checks:

```bash
chipcoin --data /path/to/node.sqlite3 list-peers
chipcoin --data /path/to/node.sqlite3 peer-summary
curl http://127.0.0.1:8081/v1/peers
curl http://127.0.0.1:8081/v1/peers/summary
```

Look for:

- `source`
- `peer_state`
- `success_count`
- `failure_count`
- `ban_until`
- `backoff_until`

## Headers-First Sync

Chipcoin now performs initial synchronization in two stages:

1. header sync
2. bounded multi-peer block download

Operational behavior:

- the node requests `headers` from one or more suitable peers
- headers are validated as far as possible before any block body is requested
- the node tracks the strongest known header tip separately from the validated chain tip
- once headers reveal missing blocks, the runtime opens a bounded download window
- block requests are spread across multiple healthy peers
- each peer has its own in-flight request cap
- stalled block requests are expired and reassigned
- consistently stalling peers are penalized and can be dropped

Relevant `.env` knobs:

- `HEADERS_SYNC_ENABLED`
- `HEADERS_MAX_PER_MESSAGE`
- `BLOCK_DOWNLOAD_WINDOW_SIZE`
- `BLOCK_MAX_INFLIGHT_PER_PEER`
- `BLOCK_REQUEST_TIMEOUT_SECONDS`
- `HEADERS_SYNC_PARALLEL_PEERS`
- `HEADERS_SYNC_START_HEIGHT_GAP_THRESHOLD`

The defaults are intentionally conservative and should work for small devnet operators without tuning.

Useful operator checks:

```bash
chipcoin --data /path/to/node.sqlite3 status
curl http://127.0.0.1:8081/v1/status
docker compose logs -f node
```

Look for:

- `sync.mode`
- `sync.validated_tip_height`
- `sync.best_header_height`
- `sync.inflight_block_count`
- `sync.block_peers`
- `sync.stalled_peers`

Typical runtime log lines:

- `headers received ...`
- `sync scheduled block downloads ...`
- `sync block request stalled ... action=reassign`
- `sync complete ...`

## Peer Misbehavior Policy

The node tracks peer misbehavior separately from consensus validity.

Default policy:

- warn when a peer reaches score `25`
- disconnect when a peer reaches score `50`
- temporarily ban when a peer reaches score `100`
- temporary bans expire after `1800` seconds
- scores decay by `5` every `300` seconds without new violations

Typical penalty events include:

- malformed or undecodable messages
- handshake failures
- repeated timeout or stall behavior
- oversized `headers` / `inv` / `getdata` / `addr` messages
- invalid blocks or transactions relayed by a peer

Operator surfaces:

- `chipcoin peer-summary`
- `GET /v1/peers`
- `GET /v1/peers/summary`
- runtime logs with `peer misbehavior ... action=...`

## Public Reachability

Public peer reachability is strongly recommended for healthy mesh behavior on the public devnet.

Required for public peer reachability:

- `TCP 18444` for the node P2P listener

Optional operator interfaces:

- `TCP 8081` for the HTTP API
- `TCP 4173` for an explorer, if you run one

Nodes that do not expose `TCP 18444` can still make outbound connections and sync normally, but they contribute less to peer discovery and network resilience because other peers cannot reliably initiate sessions back to them.

Operational guidance:

- set `NODE_P2P_BIND_PORT=18444`
- allow `TCP 18444` through the host firewall
- if the node sits behind NAT, forward external `TCP 18444` to the machine running the node
- for home routers, prefer a stable local LAN IP for the node host before configuring port forwarding
- verify that the endpoint other peers learn is your real public host and port

Basic validation:

- confirm the node is listening locally on `0.0.0.0:18444` or the intended bind address
- test `TCP 18444` from an external machine or network, not only from localhost
- confirm peers can connect inbound after router and firewall changes

## Notes

- `DIRECT_PEER` can be used for explicit peering.
- Leave both `DIRECT_PEER` and `BOOTSTRAP_URL` empty for an isolated node.
- Public browser wallet access may require `CHIPCOIN_HTTP_ALLOWED_ORIGINS` to include the wallet origin.
- The recommended runtime directory is outside the repo, for example `/home/komarek/Chipcoin-runtime`.
