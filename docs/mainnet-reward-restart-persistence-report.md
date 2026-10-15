# Mainnet Reward Restart Persistence Report

Date: 2026-10-15

## Scope

This test verifies `REWARD-RUN-006` only. Node C was restarted in a controlled
manner using its existing runtime and SQLite database while nodes A/B and both
miners continued normally. No database copy, snapshot, resync, transaction,
partition, reorg, or consensus/configuration change was used.

## Baseline

At height 1220, A/B/C agreed on:

- tip `00000012ce293e46ef202eb8927087d30aa8b042a8c60ba216a58a75c56e013a`;
- cumulative work `267554889954`;
- reward registry count 2 and registry hash
  `4a704dfd1e4a648e6502bdde28d9fed55f539acc521b590ba92190b7e37cf9f7`;
- settlement count 2 and settlement hash
  `1efb27c64e761292b3b1684d74fffab26b3f8804c193f75c492ad1383f0f390e`;
- distributed node rewards `10000000000` chipbits;
- materialized supply `6115000000000` chipbits;
- UTXO count 1229 and UTXO hash
  `c9de0d07e5cdd0e6750e9d1457c7c80b939eddc57b5e324706ac774cd5ea4483`;
- identical reward-address balances and an empty mempool;
- SQLite `quick_check=ok` and empty `foreign_key_check`.

## Restart And Recovery

Only `node-c` was restarted through Docker Compose. The same container service,
runtime directory, database, image and wallet configuration were retained.
Node C restored a P2P handshake and matched A/B on height, tip and cumulative
work in 4 seconds. It required no full sync and no operator intervention.

Immediately after recovery, its reward registry, settlement history, payout
totals, payout balances, supply and UTXO fingerprints were byte-for-byte equal
to A/B. Wallet-file checksums were unchanged.

## Chain Continuation

Canonical block 1221:

- hash `00000006615faccb3603e99d95eb97a649aaecfc3e8e0357b5cb7d79c5b88d68`;
- previous hash `00000012ce293e46ef202eb8927087d30aa8b042a8c60ba216a58a75c56e013a`;
- cumulative work `267774017628`.

It directly extends the pre-restart tip. At the final checkpoint, height 1223,
A/B/C again agreed on tip
`000000088881d91448ee2d950f34a3de5239dc744b948c4a34f2e599fd4419c9`,
cumulative work `268212272976`, materialized supply `6130000000000`
chipbits, UTXO count 1232, and UTXO hash
`65d5601084ac9182bd4441bc1624ffca4203b20fe8692c3e0ecf4e896fa12d35`.

The reward registry and settlement hashes remained unchanged, distributed
rewards remained 100 CHC, both reward balances remained correct, each node had
two handshaken peers, all mempools were empty, and all SQLite checks passed.
The ordinary monitor remained active throughout.

## Evidence

Evidence, timestamps, container inspection, database metadata, wallet
checksums, recovery progress, fingerprints, continuation block and checksums
are retained at:

`/tmp/chipcoin-mainnet-docker-rehearsal/reward-restart-20261015/`

## Result

```text
REWARD_REGISTRY_PERSISTENCE = PASS
REWARD_SETTLEMENT_PERSISTENCE = PASS
REWARD_PAYOUT_PERSISTENCE = PASS
SAME_DB_RESTART = PASS
P2P_CATCH_UP = PASS
POST_RESTART_CONVERGENCE = PASS
SQLITE_INTEGRITY = PASS
REWARD_RUN_006 = PASS
REWARD_STATE_BLOCKER = NO
```
