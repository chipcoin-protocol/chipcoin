# Bootstrap Seed Service

## Purpose

The bootstrap seed service is a separate optional component used only for initial peer discovery. It is not part of consensus and must remain operationally independent from the core node.

Operators should treat bootstrap as:

- optional
- secondary to a healthy persisted peerbook
- useful for first contact only

## What It Does

- accepts peer announces and refresh heartbeats
- returns recent live peers for one network
- helps new nodes seed their initial peerbook

## What It Does Not Do

- validate blocks
- choose the best chain
- relay normal P2P traffic
- act as an authority for consensus truth

## Deployment

The service is Docker-friendly and intentionally lightweight.

Example container environment:

- `BOOTSTRAP_BIND_HOST=0.0.0.0`
- `BOOTSTRAP_BIND_PORT=8080`
- `BOOTSTRAP_DATABASE_PATH=/data/bootstrap-seed.sqlite3`
- `BOOTSTRAP_PEER_EXPIRY_SECONDS=300`
- `BOOTSTRAP_MAX_PEERS_PER_NETWORK=1024`
- `BOOTSTRAP_MAX_PEERS_RESPONSE=64`
- `BOOTSTRAP_ALLOW_PRIVATE_ADDRESSES=false`

Example run command:

```bash
python -m bootstrap_seed.app
```

Example Docker service:

```yaml
services:
  bootstrap:
    build:
      context: ./services/bootstrap-seed
    command: ["python", "-m", "bootstrap_seed.app"]
    environment:
      BOOTSTRAP_BIND_HOST: 0.0.0.0
      BOOTSTRAP_BIND_PORT: 8080
      BOOTSTRAP_DATABASE_PATH: /data/bootstrap-seed.sqlite3
    ports:
      - "28080:8080"
    volumes:
      - bootstrap_seed_data:/data
```

## API

- `GET /v1/health`
- `GET /v1/peers?network=<name>&limit=<n>`
- `POST /v1/announce`

## Peer Record Shape

Returned peer fields:

- `host`
- `p2p_port`
- `network`
- `first_seen`
- `last_seen`
- `source`
- optional `software_version`
- optional `advertised_height`
- optional `node_id`

## Liveness Model

- every announce updates `last_seen`
- records older than `BOOTSTRAP_PEER_EXPIRY_SECONDS` are treated as inactive
- expiry pruning happens lazily on reads and writes
- the default TTL is `300` seconds

## Node Lifecycle

When bootstrap discovery is configured, a node may:

- fetch peers at startup
- refresh peers periodically afterward
- announce its public P2P host and port to one or more bootstrap URLs

Bootstrap downtime must not break node startup. Nodes continue with:

- manually configured peers
- persisted peerbook entries
- inbound peers if available

## Safety Defaults

- malformed payloads are rejected
- hosts and ports are validated strictly
- loopback/private/reserved addresses are rejected by default
- peers returned per request are capped
- stored peers per network are capped

Private-address override:

- the default is `BOOTSTRAP_ALLOW_PRIVATE_ADDRESSES=false`
- set `BOOTSTRAP_ALLOW_PRIVATE_ADDRESSES=true` only for lab or private-network deployments where private peer addresses are expected

## Security Notes

- bootstrap data is untrusted input
- discovered peers are hints, not trusted truth
- peer validation and chain validation still happen inside the node
- if you need private-address bootstrap for lab networks, set `BOOTSTRAP_ALLOW_PRIVATE_ADDRESSES=true`
