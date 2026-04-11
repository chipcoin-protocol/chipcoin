# Bootstrap Seed Service

This service is intentionally small and separate from the Chipcoin v2 node.

## Role

- accept peer announces
- return bootstrap peers
- expose basic health status

## Limits

- not a consensus authority
- not a blockchain source of truth
- not a mandatory relay for peer traffic

## Runtime

Run it with:

```bash
python -m bootstrap_seed.app
```

Relevant environment variables:

- `BOOTSTRAP_BIND_HOST`
- `BOOTSTRAP_BIND_PORT`
- `BOOTSTRAP_DATABASE_PATH`
- `BOOTSTRAP_PEER_EXPIRY_SECONDS`
- `BOOTSTRAP_MAX_PEERS_PER_NETWORK`
- `BOOTSTRAP_MAX_PEERS_RESPONSE`
- `BOOTSTRAP_ALLOW_PRIVATE_ADDRESSES`

The service stores peer state in SQLite so announce data survives restarts.

## API

- `GET /v1/health`
- `GET /v1/peers?network=<network>&limit=<n>`
- `POST /v1/announce`

Announce payload fields:

- `host`
- `p2p_port`
- `network`
- `source`
- optional `software_version`
- optional `advertised_height`
- optional `node_id`
- optional `first_seen`
- optional `last_seen`

## Safety Defaults

- rejects malformed hosts and ports
- rejects loopback/private/reserved addresses by default
- applies TTL expiry to peer liveness
- caps returned peers per request
- caps stored peers per network

## Trust Model

- bootstrap is optional
- bootstrap results are hints only
- nodes must still validate peers, blocks, and chain state normally
