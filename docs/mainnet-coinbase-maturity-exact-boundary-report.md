# Mainnet Coinbase Maturity Exact Boundary Report

Date: 2026-10-05

## Result

The exact mainnet coinbase maturity boundary was exercised in an isolated,
deterministic environment using the unchanged production `MAINNET_PARAMS` and
one ML-DSA-44 transaction. The live rehearsal was not modified or restarted.

```text
COINBASE_MATURITY_99_REJECT = PASS
COINBASE_MATURITY_100_ACCEPT = PASS
EXACT_MATURITY_BOUNDARY = PASS
CONSENSUS_BLOCKER = NO
```

## Production Validation Path

The test exercises the production paths rather than only testing arithmetic:

1. `NodeService.receive_transaction()` performs node mempool admission.
2. `MempoolManager.accept()` builds a `ValidationContext` through
   `NodeService._validation_context_for_view()`.
3. The node sets `ValidationContext.height` to `tip.height + 1`, the candidate
   block height.
4. `validate_transaction()` calls `validate_transaction_stateful()`.
5. `validate_transaction_stateful()` calls `is_coinbase_mature()` for the
   referenced production `UtxoEntry`.
6. `validate_block_stateful()` uses the same stateful transaction validator
   for non-coinbase transactions in a candidate block.

The consensus rule in `src/chipcoin/consensus/validation.py` is:

```text
spend_height - coinbase_origin_height >= params.coinbase_maturity
```

`MAINNET_PARAMS.coinbase_maturity` remained exactly `100`.

## Source Coinbase

| Field | Value |
|---|---|
| Origin height | `0` |
| TXID | `415875b0413b39f542248f0b3d6ab8d49999704d76c605297635bb747fadb74c` |
| Vout | `0` |
| Amount | `5000000000` chipbits |
| Owner | `CHCQCqkFfjA9SZRDdhdonCXxbUyjhBQTEEAvAtqc694huYm1N2BpBWPo` |
| Address kind | `pq` |
| Scheme | ML-DSA-44, scheme ID `10` |

## Boundary Transaction

| Field | Value |
|---|---|
| TXID | `5bc5c8d3863d5f9f36e3ce30929437c85931ce6b8d3ac2465fec3f0b0bd02f1c` |
| Raw SHA-256 | `6a71749be947601d789270b1847852d85db3c8a55ed93187e4cf97d1955f7dd3` |
| Raw size | `3920` bytes |
| Input | `415875b0413b39f542248f0b3d6ab8d49999704d76c605297635bb747fadb74c:0` |
| Destination | `CHCQCqjjfLrMEH26QRLjLUzw6dHapcjmEgGDnKfVmwWuqknjPSWUXa7a` |
| Amount | `100000000` chipbits |
| Change | `4899999000` chipbits |
| Fee | `1000` chipbits |
| Version | `2` |
| Signature scheme | ML-DSA-44, scheme ID `10` |

Exactly the same serialized transaction, TXID, input, outputs, fee, public key,
and signature were used at all candidate heights. Only the chain context and
therefore `ValidationContext.height` changed.

## Boundary Results

| Candidate height | Difference from origin | Direct consensus | Block stateful path | Node mempool path |
|---:|---:|---|---|---|
| 99 | 99 | `REJECT` | `REJECT` | `REJECT`, mempool remains empty |
| 100 | 100 | `ACCEPT` | `ACCEPT` | `ACCEPT`, mempool size becomes 1 |
| 101 | 101 | `ACCEPT` | not required | not required |

The exact rejection reason at candidate height 99 was:

```text
Coinbase output is not mature enough to spend.
```

The transaction passed stateless/PQ/network/ownership/signature validation up
to the maturity check. At height 100 the same transaction returned the expected
`1000` chipbit fee through direct consensus, block-stateful, and mempool paths.
This demonstrates explicitly:

```text
99 < 100  -> immature
100 >= 100 -> mature
```

## Mempool And Block Semantics

Mempool admission evaluates transactions for the next candidate block, using
`tip.height + 1`. Candidate-block validation receives that candidate height in
the same `ValidationContext.height` field and invokes the same stateful
maturity check. The test used isolated SQLite node services with tips 98 and 99
to produce candidate heights 99 and 100 without mining, changing consensus
parameters, or constructing a replacement transaction.

The block assertion calls the production stateful block path directly. PoW and
header serialization are orthogonal stateless checks and were not weakened or
mocked to obtain the maturity result.

## Regression

The following suites completed with `180 passed`:

- exact mainnet maturity boundary;
- consensus transaction/block validation;
- UTXO behavior;
- mainnet profile/configuration;
- node and mempool behavior in `test_local_node.py`.

Evidence:

`/tmp/chipcoin-mainnet-docker-rehearsal/maturity-boundary-exact/result.json`

Regression source:

`tests/consensus/test_mainnet_coinbase_maturity_boundary.py`

## Rehearsal Safety

After the isolated test, node-a, node-b, and node-c remained converged at
height 270 with the same tip and cumulative work. Both miners remained running,
the ordinary monitor was active, and no rehearsal runtime was changed or
restarted.

## RC Gate

`TX-RUN-002` is promoted from `NOT_RUN` to `PASS`. No other RC gate changes.
