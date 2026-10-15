# MAINNET PQ LEGACY REJECTION REPORT

Date: 2026-10-06

## Scope

This report covers only `PQ-NEG-001`. MemPalace was consulted for the
established mainnet PQ-only and network-bound special-signature decisions.
No consensus, activation, wallet, P2P, reward, database, or rehearsal runtime
code was changed.

The negative artifacts existed only inside a temporary Docker container using
`--network none`. The container used the validated rehearsal node image
`sha256:720ea695c75fd9aee8637c2e5a1993c06858b55491c2a51d1a7d9093a168ee9d`,
the real `mainnet` profile, and unchanged `MAINNET_PARAMS`.

## Positive Controls

The isolated node replayed all 250 canonical blocks from the previously signed
mainnet snapshot, heights 0 through 249, through:

`NodeService.apply_block -> validate_block -> validate_block_stateful`.

This accepted 250 valid PQ/CHCQ coinbases with real mainnet proof of work. A
valid version-2 ML-DSA-44 scheme-10 transaction with CHCQ destination/change
was then decoded and accepted into the mempool. After all negative cases, a
second valid version-2 scheme-10 transaction was accepted. The two positive
TXIDs were:

- `9467448a756a2fd94f4d5b677c648f757f5a906d1dbeccdd16d082716b1f235f`
- `d1a8e68d965722915b3f8981b8511d7dba39b7773da0d24a95a474e53f7e06d2`

Mainnet PQ support resolved to activation height 0. The mandatory standard
transaction policy was `require_pq_standard_transactions=true`.

## Rejection Matrix

| CASE | EXPECTED | ACTUAL | REJECTION_REASON | PRODUCTION_PATH | STATE_MUTATION | RESULT |
|---|---|---|---|---|---|---|
| Legacy/non-CHCQ output | Reject | Reject | `Mainnet transaction outputs must use ML-DSA-44 CHCQ addresses.` | raw decode, mempool preflight, stateful transaction validation | None | PASS |
| Legacy transaction version 1 | Reject | Reject | `Mainnet standard transactions must use transaction version 2.` | raw decode, mempool preflight, stateful input validation | None | PASS |
| ECDSA scheme 0 input | Reject | Reject | `Mainnet standard transaction inputs must use ML-DSA-44 signatures.` | raw decode, mempool preflight, stateful input validation | None | PASS |
| Mixed ML-DSA-44/ECDSA inputs | Reject atomically | Reject atomically | `Mainnet standard transaction inputs must use ML-DSA-44 signatures.` | raw decode, multi-input mempool/stateful validation | None | PASS |
| Legacy/non-PQ coinbase | Reject | Reject | `Mainnet transaction outputs must use ML-DSA-44 CHCQ addresses.` | valid mainnet PoW, `NodeService.apply_block`, full stateless then stateful block validation | None | PASS |
| ECDSA reward owner | Reject | Reject | `Mainnet reward-node owner signatures must use ML-DSA-44.` | mempool preflight, special-node stateful validation | None | PASS |
| Legacy special signature v1 | Reject | Reject | `Mainnet reward-node owner signatures must use the network-bound v2 format.` | mempool preflight, special-node stateful validation | None | PASS |
| Legacy attestation identity | Reject | Reject | `Mainnet reward-node attestations must use ML-DSA-44.` | mempool preflight, special-node stateful validation | None | PASS |
| Legacy payout destination | Reject | Reject | `Mainnet reward-node payouts must use ML-DSA-44 CHCQ addresses.` | mempool preflight, special-node stateful validation | None | PASS |

All artifacts were structurally valid. None failed early due to malformed
encoding. The legacy coinbase candidate was mined at unchanged real mainnet
difficulty, so proof-of-work validation passed before the expected CHCQ policy
rejection.

For every negative case, the harness compared tip/work, complete UTXO state,
registry state, and mempool before and after. Every comparison was identical.
No rejected artifact created a UTXO, changed a balance or registry record,
entered the mempool, became canonical, or crashed the node.

## Integrity And Regressions

The final isolated fingerprint was:

- Height/tip: `249` / `0000000c241482e41fdbb85ecb21334c887cf4225bc9f071fc2b043d1d81c2b4`
- Cumulative work: `54781918500`
- UTXO count: `254`
- Registry count: `0`
- State SHA-256: `4bcbf98204a546841187750957433e1a9bb2eea4f9cd34506ded2af79a2c0cc7`
- SQLite quick/FK: `ok` / no rows

Relevant regressions:

- Consensus validation, node registry, mainnet profile, and mainnet PQ E2E:
  `62 passed`.
- Shell syntax: PASS.
- JSON validation: PASS.
- Temporary driver compilation: PASS.
- `git diff --check`: PASS.
- No dependency was added or changed.

The validation run completed before a temporary evidence-reporter field-name
error. The corrected reporter reopened the same isolated DB and verified both
positive mempool controls and SQLite integrity; this did not affect any
validation result. Evidence is retained at
`/tmp/chipcoin-mainnet-pq-neg-001-20261006`.

## Rehearsal Read-Only Status

No negative artifact was sent to the rehearsal. At the final read-only
checkpoint A/B/C were converged at height `328`, tip
`00000007e23902a0e04c405b878de9bccb04ba86d75d284119d055d23ba836bd`,
work `72093004746`, materialized supply `1645000000000` chipbits, and UTXO
count/hash `333` / `016d556023ed23ffeb2046d69a5780ff8adf87d1174cd0c491ddd963c7cdd5a0`.
Each node had two handshaken peers, an empty mempool, and PASS SQLite checks.
Both miners and the ordinary monitor were active.

The reward registry remained identical across A/B/C with two records and hash
`250181d631f01060457af722e0d794c0c5af7d173233338c522b849342526fbb`.
Both nodes remained `warming_up_until_height_400`, `active=false`; settlement
count and distributed rewards remained zero.

## Gate Result

Only `PQ-NEG-001` is promoted to `PASS`. RC counts become `82 PASS / 9 NOT_RUN /
7 PENDING_HEIGHT / 0 FAIL` out of 98 RC-blocking gates.

LEGACY_OUTPUT_REJECTED = PASS

LEGACY_TX_REJECTED = PASS

ECDSA_SCHEME_0_REJECTED = PASS

LEGACY_COINBASE_REJECTED = PASS

LEGACY_SPECIAL_SIGNATURE_REJECTED = PASS

FAIL_CLOSED_STATE = PASS

PQ_NEG_001 = PASS

PQ_CONSENSUS_BLOCKER = NO
