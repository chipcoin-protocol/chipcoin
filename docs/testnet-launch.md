# Testnet Launch Notes

This page documents the current testnet boundary. Devnet remains active as the
fallback public environment until testnet operations and diagnostics are refined.

The repository now contains a separate `testnet` network profile with:

- public P2P port `28444`
- local-only HTTP port `28081`
- data file `chipcoin-testnet.sqlite3`
- distinct network magic bytes
- consensus params separate from devnet

The node HTTP API must remain bound to `127.0.0.1`; expose it externally only
through an intentional reverse proxy. Public firewall/router rules should expose
only the testnet P2P port `28444/tcp`.

No public testnet bootstrap peer, snapshot manifest, explorer, faucet, or
snapshot publisher is configured yet.

## Manual Local Dry-Run

Use the setup wizard from the repository root:

```bash
python3 scripts/setup/wizard.py
```

Choose:

- setup mode: `local` or `quick`
- role: `node` or `both`
- network: `testnet`
- bootstrap: `full`
- discovery: `isolated`, unless you are manually connecting to another testnet peer

The generated `.env` should keep testnet isolated:

```dotenv
CHIPCOIN_NETWORK=testnet
NODE_DATA_PATH=/var/lib/chipcoin/data/node-testnet.sqlite3
NODE_P2P_BIND_PORT=28444
NODE_HTTP_BIND_PORT=28081
NODE_HTTP_PUBLISH_HOST=127.0.0.1
NODE_DIRECT_PEERS=
NODE_BOOTSTRAP_URL=
NODE_SNAPSHOT_MANIFEST_URLS=
NODE_SNAPSHOT_FILE=/var/lib/chipcoin/data/node-testnet.snapshot
```

Start the node:

```bash
docker compose up --build node
```

Check status:

```bash
docker compose exec -T node chipcoin \
  --network testnet \
  --data /runtime/node.sqlite3 \
  status
```

For a node plus local miner dry-run, keep the miner pointed at the node service
inside the same Compose project:

```dotenv
MINING_NODE_URLS=http://node:28081
MINING_MIN_INTERVAL_SECONDS=10.0
MINING_NONCE_BATCH_SIZE=50000
```

These miner defaults are intentionally conservative for public multi-node
testnet operation. Avoid one-to-two-second block production in normal testnet
runs because it creates avoidable fork churn and slower convergence on weaker
nodes.

Then run:

```bash
docker compose up --build node miner
```

## Manual Peer Dry-Run

To connect two manually operated testnet nodes, configure each node with the
other node's explicit testnet P2P endpoint:

```dotenv
CHIPCOIN_NETWORK=testnet
NODE_P2P_BIND_PORT=28444
NODE_HTTP_BIND_PORT=28081
NODE_HTTP_PUBLISH_HOST=127.0.0.1
NODE_DIRECT_PEERS=other-testnet-host.example:28444
NODE_BOOTSTRAP_URL=
NODE_SNAPSHOT_MANIFEST_URLS=
```

Do not use devnet peers such as `chipcoinprotocol.com:18444`. Devnet and testnet
use different P2P magic bytes and will reject each other before handshake
completion.

## Expected Boundaries

For this dry-run phase:

- testnet starts from a separate database
- testnet full-syncs from genesis unless you provide your own compatible snapshot
- testnet has no official bootstrap service
- testnet has no official snapshot manifest
- testnet has no public faucet or explorer integration
- testnet addresses still use the current global `CHC` prefix

## Pre-Public Checklist

Before promoting this to a public testnet, define and document:

- official bootstrap peers
- snapshot publisher and signer keys
- explorer/API endpoint
- faucet funding policy
- public release tag and upgrade policy
- whether address prefixes remain shared or become network-specific
