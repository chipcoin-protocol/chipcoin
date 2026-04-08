# Mining Architecture

## Roles

Chipcoin now separates mining into two roles:

- full node
  - validates the full chain
  - owns the UTXO set, mempool, and reorg handling
  - builds miner-facing block templates
  - validates submitted solved blocks
- miner worker
  - does not run P2P sync
  - does not keep a local chain database
  - fetches templates from one or more nodes
  - hashes, submits, and refreshes on tip changes or expiry

## Mining API

The node exposes a miner-facing HTTP API:

- `GET /mining/status`
- `POST /mining/get-block-template`
- `POST /mining/submit-block`

The node remains authoritative for:

- current best tip
- difficulty/target
- transaction selection
- reward distribution
- block validation and acceptance

## Trust Model

A remote miner trusts the selected node operationally for:

- template freshness
- mempool transaction selection
- reward output construction
- accurate stale-template signaling

That trust is explicit. The miner performs lightweight sanity checks through shared serialization and PoW code, but it does not revalidate full chain state.

## Template Lifecycle

1. Miner requests `/mining/status`
2. Miner requests `/mining/get-block-template`
3. Miner rebuilds the coinbase locally with `extra_nonce` updates and hashes
4. Miner submits a solved block with `/mining/submit-block`
5. Miner immediately requests a fresh template

Templates become stale when:

- the node tip changes
- the template TTL expires
- the node rejects submission as stale

## Failover

The miner accepts multiple node URLs.

- it prefers the first healthy endpoint
- if that endpoint stops responding, it tries the next one
- startup time no longer depends on historical chain height

