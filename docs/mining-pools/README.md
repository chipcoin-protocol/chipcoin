# Chipcoin Mining Pool Integration Handbook v1.3

**Reference Core:** [Mainnet v0.1.2](https://github.com/chipcoin-protocol/chipcoin/releases/tag/mainnet-v0.1.2), tag target `12e4dbc8974bd76885e30e6dacdf1b7be898e126`. The vectors were generated at ancestor `4c0984e65de31a50db7558d468167d513769bb20` and are verified unchanged against the release Core. The published Docker archive is AMD64; other architectures require a separately verified native build from the tagged source. This handbook is published separately from the immutable v0.1.2 tag. See [release alignment and evidence](RELEASE_ALIGNMENT.md).

Chipcoin is an independent SHA-256d proof-of-work chain. The 80-byte header, canonical transactions and block format, big-endian digest comparison, CHCQ addresses, ML-DSA-44 signatures, and deterministic reward-node settlement are defined by this Core. A pool distributes work and accounts for shares; the Core issues templates and validates submitted blocks. Chipcoin does not include an official Stratum server or a pool accounting engine.

## Start here

1. Read the [operational guide](INTEGRATION_GUIDE.md) and [template contract](BLOCK_TEMPLATES.md).
2. Implement [canonical block submission](BLOCK_SUBMISSION.md) and [coinbase rules](COINBASE_AND_PAYOUTS.md) before distributing work.
3. Validate [CHCQ payout addresses](PQ_ADDRESSES.md) and run the [machine-readable vectors](TEST_VECTORS.md).
4. Treat [Stratum translation](STRATUM_REFERENCE.md) as pool-specific, use the [wire-vector evidence checklist](STRATUM_VECTOR_REQUEST.md) before claiming interoperability, and keep [troubleshooting](TROUBLESHOOTING.md) nearby.

The [original integration specification](../integrations/BLOCK_SUBMISSION_SPEC.md), [compatibility matrix](../integrations/BLOCK_SUBMISSION_COMPATIBILITY.md), and [pre-release test plan](../integrations/POOL_PRERELEASE_TEST_PLAN.md) describe the RC development history. This handbook describes the tagged release; use the matrix in [release alignment](RELEASE_ALIGNMENT.md) when comparing them.

## Isolated quick start

Prerequisites: Git, Docker with Compose v2, `curl`, `jq`, and a free loopback port `18081`. Use a **separate clean checkout** of the tagged Core as the build context. The example has no bootstrap URL, peers, P2P publication, or Mainnet volume. Docker stores its disposable database in the named volume `chipcoin-pool-handbook-devnet_pool_lab_data`, which survives container removal. The early Devnet height is below CHCQ activation; use the legacy payout address in [the vector fixture](test-vectors/v1.json) only for this isolated test. Never use that address for real payouts.

```sh
git clone https://github.com/chipcoin-protocol/chipcoin.git chipcoin-handbook
git clone https://github.com/chipcoin-protocol/chipcoin.git chipcoin-core-v0.1.2
git -C chipcoin-core-v0.1.2 checkout mainnet-v0.1.2
test "$(git -C chipcoin-core-v0.1.2 rev-parse HEAD)" = 12e4dbc8974bd76885e30e6dacdf1b7be898e126
cd chipcoin-handbook
export CHIPCOIN_CORE_CONTEXT="$(cd ../chipcoin-core-v0.1.2 && pwd)"
docker compose -f docs/mining-pools/examples/compose.devnet.yml up -d --build
curl -fsS http://127.0.0.1:18081/v1/status | jq '{network,chain_id,height,tip_hash,sync_phase}'
```

The Core tag and handbook live at different commits. `CHIPCOIN_CORE_CONTEXT` makes the example build the **tagged Core** while reading the handbook and smoke script from current `main`. Check that `docs/mining-pools/` exists in the handbook checkout before starting; do not point the build at an operational node checkout with private configuration.

Request a template using a **public test address**, obtained from the vector file:

```sh
PAYOUT=$(jq -r '.isolated_devnet_example.miner_address' docs/mining-pools/test-vectors/v1.json)
curl -fsS -H 'Content-Type: application/json' \
  -d "$(jq -n --arg a "$PAYOUT" '{payout_address:$a,miner_id:"pool-lab",template_mode:"full_block"}')" \
  http://127.0.0.1:18081/mining/get-block-template | jq '{template_id,height,bits,target,template_expiry,transactions,coinbase_tx}'
```

This request **does not mine or submit a block**. The included [smoke client](examples/smoke_devnet.py) performs the missing steps against the isolated node: serializes coinbase and returned transactions, recalculates the Merkle root, searches a nonce, submits complete bytes, queries the hash, and retries the identical block. It runs inside the tagged Core image built above, so no host Python installation is required:

```sh
docker compose -f docs/mining-pools/examples/compose.devnet.yml run --rm smoke
```

Expect JSON with `submission:"accepted"`, `on_active_chain:true`, and `retry:"already_accepted"`. The executable [pool regression](../../tests/integration/pool/test_block_submission.py) covers additional mempool/fork cases with temporary databases. The [vector verifier](test-vectors/verify.py) independently checks a solved synthetic Devnet block. Do not submit the fixture's already-solved block to a network with a different tip or timestamp.

After your pool builds a live candidate, send `{"serialized_block":"<complete hex>"}` to `POST /mining/submit-block`, then query `GET /v1/block?hash=<returned hash>` and require `on_active_chain:true` before crediting network confirmation. Retry the **same bytes** after a timeout. Stop the lab with `docker compose -f docs/mining-pools/examples/compose.devnet.yml down`; this retains the named volume. Back it up or remove it separately only when you no longer need it. Never run this Compose file against a production project or wallet.

## Operational boundary

Bind the mining API to loopback or a private network with operator-controlled access. This release API has no built-in pool identity authentication or per-client rate limiter. Separate pool wallets and chain state by network; protect ML-DSA-44 wallet material, minimize request logging, back up persistent data consistently, and monitor tip/hash, template errors, accepted blocks, and reorgs. Never publish the mining API through an unauthenticated Internet proxy. See [operational details](INTEGRATION_GUIDE.md).

The Core release is public and has been deployed on Mainnet nodes as recorded in [release alignment](RELEASE_ALIGNMENT.md). [Crypto Connection](https://crypto-connection.net) and its operator Julien provided implementation details and test results for their Miningcore Chipcoin module v6.1; the backend source and the reported Stratum vector have not been independently inspected. Those details describe one pool, not an official Chipcoin Stratum standard. See the [v1.3 changelog](CHANGELOG.md) and [Stratum reference](STRATUM_REFERENCE.md).
