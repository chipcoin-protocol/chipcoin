# Mainnet Reward Reorg Safety Report

Date: 2026-10-15

## Result

`REWARD-RUN-007 = PASS`.

The rehearsal executed a real reward-era partition and cumulative-work reorg
without submitting transactions. The test preserved the two canonical reward
registrations, 15 attestation bundles, two epoch settlements and 100 CHC of
distributed node rewards. Node A naturally abandoned its two-block branch and
adopted branch B. A/B/C then remained convergent through a new canonical block.

## Baseline

- Height: `1227`
- Tip: `00000008903942240078ed1d5c3630b16bc9202ec0ab1dc182eb4ba98feb4f8f`
- Cumulative work: `269088783672`
- Reward registry: `2`
- Reward registry hash: `4a704dfd1e4a648e6502bdde28d9fed55f539acc521b590ba92190b7e37cf9f7`
- Attestation bundles: `15`
- Attestation hash: `c1b369e9425de7dd453f3550c1b7339f820f51284770fa9100e8b5f564ab0bad`
- Settlements: `2`
- Settlement hash: `1efb27c64e761292b3b1684d74fffab26b3f8804c193f75c492ad1383f0f390e`
- Distributed rewards: `10000000000` chipbits (`100 CHC`)
- A/B/C fingerprint and SQLite checks: PASS

## Fork And Selection

- Common ancestor: height `1227`, hash `00000008903942240078ed1d5c3630b16bc9202ec0ab1dc182eb4ba98feb4f8f`
- First divergent A: height `1228`, hash `00000011cb6d971db6d815c32ac6306cc2ab1827320e36f1b6a6a7868d530a21`
- First divergent B: height `1228`, hash `00000000a3832a530d04521581317839b2ed306464b46cbe7612369ee6382afa`
- Final A branch: height `1229`, work `269527039020`
- Winning B branch: height `1230`, work `269746166694`
- B work advantage: `219127674`
- Reorg depth on A: `2`
- Natural P2P reconnect and cumulative-work selection: PASS

## Reward And Economic State

The post-reorg A/B/C fingerprint matched the pre-reconnect branch B fingerprint
for height, tip, work, supply, UTXO set, selected balances, reward registry,
attestation bundles, settlements and distributed rewards. Coinbase outputs from
the two orphaned A blocks were absent from the canonical UTXO set.

At canonical height `1230`:

- Materialized supply: `6165000000000` chipbits
- UTXO count: `1239`
- UTXO hash: `aa80049e5a1380bace663cedea1cc32c7ca67b747210819d0072d0cea09d6180`
- Reward registry/attestation/settlement hashes: unchanged and equal on A/B/C
- SQLite quick check and foreign-key check: PASS on A/B/C

## Chain Continuation

The normal miners resumed on the shared topology and produced canonical block
`1231`:

- Hash: `000000132d80a951809aab6abb170391c0afcbcaf3a6a4042f34b027e174dea7`
- Cumulative work: `269965294368`
- Materialized supply: `6170000000000` chipbits
- UTXO count: `1240`
- UTXO hash: `c4dc027b54a7721d5f28ea827431c54f1a17c5c67fd2665ee263a622d4d87f0f`
- A/B/C convergence and SQLite integrity: PASS

## Operational Observations

Two harness-only finalization issues were observed and preserved separately:

1. The detached progress command initially stopped on a malformed `jq`
   assertion after both miners were already safely stopped. The assertion was
   corrected; no node or chain state was modified.
2. The fault monitor observed `miner-a` stopped during the short interval before
   the lifecycle marker advanced from `FORK_CONFIRMED` to
   `WINNING_BRANCH_CONFIRMED`. The reorg evidence remained intact. Final lock
   cleanup used the existing idempotent recovery path after the reward and
   economic assertions had passed.

Neither issue changed node, P2P, consensus, reward, DB or chain-selection code.
The rehearsal ended in `FINAL_CONVERGENCE`, shared topology, no fault lock,
ordinary monitor active and both miners operational.

## Evidence

- `/tmp/chipcoin-mainnet-docker-rehearsal/fault/evidence/reward-reorg-prepared-20261015T073025Z`
- `/tmp/chipcoin-mainnet-docker-rehearsal/fault/evidence/reward-reorg-activation-20261015T073048Z`
- `/tmp/chipcoin-mainnet-docker-rehearsal/fault/evidence/fork-20261015T091051Z`
- `/tmp/chipcoin-mainnet-docker-rehearsal/fault/evidence/winning-20261015T091105Z`
- `/tmp/chipcoin-mainnet-docker-rehearsal/fault/evidence/reward-reorg-winner-20261015T115453Z`
- `/tmp/chipcoin-mainnet-docker-rehearsal/fault/evidence/reward-reorg-verified-20261015T115548Z`
- `/tmp/chipcoin-mainnet-docker-rehearsal/fault/reward-reorg-continuation`

REWARD_STATE_REORG_SAFETY = PASS

A_B_C_REWARD_STATE_CONVERGENCE = PASS

ORPHAN_COINBASE_ROLLBACK = PASS

CHAIN_CONTINUATION_AFTER_REORG = PASS

REWARD_RUN_007 = PASS

REWARD_CONSENSUS_BLOCKER = NO
