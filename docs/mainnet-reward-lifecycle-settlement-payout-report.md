# Mainnet Reward Lifecycle / Settlement / Payout Report

Date: 2026-10-15

## Scope

This report closes only the runtime gates demonstrated by the uninterrupted
mainnet rehearsal: activation, warmup/eligibility, attestation and quorum,
settlement, payout accounting, and private Explorer visibility. It does not
claim restart persistence or reward-state reorg safety.

## Activation And Eligibility

The canonical chain crossed the configured activation boundary without a
parameter change:

| Height | Block hash | Observation |
|---:|---|---|
| 999 | `00000005661696b4853aba131227787561e41a60d89984ce2ff700c3019dd4c6` | Registry count 2, settlement count 0, no node-reward payout. |
| 1000 | `00000000e77e9d4bbc2bbba81074e03c0197b90a9bc94dd88589e1038631ca7e` | Both reward-node renewals were included; activation epoch began. |
| 1001 | `00000011d619b30d33fbc9391ac4c041a52ec5f50c8b766044f0013897c3ce14` | Both registered nodes were eligible from this height and production attestation traffic was included. |

Both nodes were registered at height 275, completed the configured two-epoch
warmup naturally, retained distinct ML-DSA-44 owner and attestation identities,
and used CHCQ payout addresses. Epochs 10 and 11 each assigned three candidate
windows to each node. All six checks per epoch passed final confirmation.

## Canonical Settlements

| Epoch | Settlement height | Settlement TXID | Payout per node | Distributed | Undistributed |
|---:|---:|---|---:|---:|---:|
| 10 | 1099 | `6e23a9b9927d6f374f2e736ca82b106bf215009f1a4ffb581f78e7d1f20761c4` | 25 CHC | 50 CHC | 0 CHC |
| 11 | 1199 | `48da772f54a818da6662420d7ef6f06233ee47cf08b13bf8eb572329fd439aa7` | 25 CHC | 50 CHC | 0 CHC |

The corresponding canonical blocks are
`000000057656b888c434141d016156dfbff32d648fea0366437617050475e26e`
and `0000000d9050c22f033e9c3660b5876701cbb5fb20efc8b5f85cf959780b28b0`.
Each block contains exactly one settlement transaction and exactly one payout
output for each registered reward node. Both settlements were produced in
`auto` mode and every reward entry has `final_confirmation_passed=true`.

## Accounting And Maturity

At the final comparison checkpoint, height 1220, all three nodes reported:

- materialized miner supply: `6105000000000` chipbits;
- materialized node-reward supply: `10000000000` chipbits;
- total materialized supply: `6115000000000` chipbits;
- two stored settlements and four reward entries;
- registry count 2 and total distributed rewards 100 CHC;
- UTXO count 1229 and UTXO hash
  `c9de0d07e5cdd0e6750e9d1457c7c80b939eddc57b5e324706ac774cd5ea4483`.

Each payout address held 51 CHC confirmed: 26 CHC spendable and 25 CHC
immature. The height-1099 reward output was mature while the height-1199 reward
output was still immature, matching canonical coinbase maturity. No duplicate
settlement, duplicate payout, ghost UTXO, or unexpected supply mutation was
observed.

## Explorer Validation

The production Chipcoin Central build was served privately against the live
mainnet rehearsal API. API assertions and a real Chromium rendering showed
epoch 11 as closed, two rewarded nodes, 50 CHC distributed, zero undistributed,
settlement height 1199, both CHCQ payout destinations, ML-DSA-44 labels, final
confirmation, and the exact 25 CHC payout for each node. The client also
verified both settlement TXIDs and the mature/immature payout distinction.

Evidence is retained under
`/tmp/chipcoin-mainnet-docker-rehearsal/reward-lifecycle-20261015/`, including
the API result, DOM capture, screenshot, epoch summaries, settlement records,
A/B/C fingerprints, and checksums. No public deployment was performed.

## Final Convergence

At height 1220, A/B/C agreed on:

- tip `00000012ce293e46ef202eb8927087d30aa8b042a8c60ba216a58a75c56e013a`;
- cumulative work `267554889954`;
- supply, UTXO count/hash, reward registry hash and settlement hash;
- both payout-address balances;
- empty mempool;
- SQLite `quick_check=ok` and empty `foreign_key_check`.

Both miners remained running and the ordinary rehearsal monitor continued to
record `MONITOR_PASS` consensus invariants.

## Gate Results

| Gate | Result |
|---|---|
| `REWARD-RUN-001` | PASS |
| `REWARD-RUN-003` | PASS |
| `REWARD-RUN-004` | PASS |
| `REWARD-RUN-005` | PASS |
| `EXP-INT-004` | PASS |
| `REWARD-RUN-006` | PENDING_HEIGHT |
| `REWARD-RUN-007` | PENDING_HEIGHT |

`MAINNET_RC_READY` remains false because other RC-blocking gates remain open.
