# Mainnet Final A-E Convergence Report

Date: 2026-10-15

## Result

`FINAL-RUN-001 = PASS`.

The five independently exercised mainnet paths converged on one canonical
state and remained equal through the next canonical block:

| Path | Runtime | Provenance |
|---|---|---|
| A | `node-a` | Normally running rehearsal node. |
| B | `node-b` | Node that traversed the real partition/reorg scenarios. |
| C | `node-c` | Node recovered from controlled restart and SIGKILL/WAL tests. |
| D | `node-fullsync` | Preserved node originally synchronized from genesis exclusively over P2P. |
| E | `node-snapshot` | Preserved node restored from the trusted signed snapshot and delta-synchronized over P2P. |

All five ran image
`sha256:720ea695c75fd9aee8637c2e5a1993c06858b55491c2a51d1a7d9093a168ee9d`
for this comparison. D resumed at height 249 and E at height 269; neither DB
was copied, reset, or reimported. E's startup explicitly reported that snapshot
bootstrap was skipped because its restored database was already initialized.

## Convergence

The first exact A-E convergence was recorded at height 1234. After convergence,
the network mined block 1235 and all five nodes independently reached:

| Field | Final value |
|---|---|
| Height | `1235` |
| Tip | `00000011bfe1c3b716b600f8cdc5ce59248dc9c85af890f8297f26dcd3d052ca` |
| Cumulative work | `270841805064` |
| Materialized supply | `6190000000000` chipbits |
| UTXO count | `1244` |
| UTXO hash | `d50ba5f17fba1e4cea87ba4174c74c58b8b13a08ea56ef1c6330107de665011f` |
| Selected balances hash | `8a0e40748fb47abcc7a8f683a12863b70879600bddb47d422961a2ae08f66568` |
| Reward registry | count `2`, hash `4a704dfd1e4a648e6502bdde28d9fed55f539acc521b590ba92190b7e37cf9f7` |
| Attestation bundles | count `15`, hash `c1b369e9425de7dd453f3550c1b7339f820f51284770fa9100e8b5f564ab0bad` |
| Settlements | count `2`, hash `1efb27c64e761292b3b1684d74fffab26b3f8804c193f75c492ad1383f0f390e` |
| Distributed rewards | `10000000000` chipbits |
| Mempool | empty on A-E |
| SQLite quick/FK | `ok` / no violations on A-E |

The persisted comparison includes the full selected balance objects, not only
their aggregate hash. The continuation block demonstrates that D and E did not
merely reach a historical tip; they continued with the canonical chain.

## Operational Observation

The first attempt exposed a monitor-only defect: the ordinary monitor compared
`handshaken_peer_count` as a consensus invariant. A had two additional D/E
connections, so the monitor stopped A/B/C despite identical canonical state.
Evidence was preserved, A/B/C were restored from the same databases, and no
consensus or storage mismatch occurred. The monitor comparison now excludes
peer count, mempool size and sync phase while continuing to require peer health
and SQLite integrity. Regression result: `13 passed`.

After the successful comparison, D/E required the configured shutdown timeout
and exited with code 137. Both post-stop databases passed SQLite `quick_check`
and `foreign_key_check`; this is an auxiliary shutdown observation and does not
alter the already persisted A-E convergence result.

## Evidence

- `/tmp/chipcoin-mainnet-docker-rehearsal/final-a-e-20261015/first-five-way-convergence.json`
- `/tmp/chipcoin-mainnet-docker-rehearsal/final-a-e-20261015/post-block-five-way-convergence.json`
- `/tmp/chipcoin-mainnet-docker-rehearsal/final-a-e-20261015/provenance.json`
- `/tmp/chipcoin-mainnet-docker-rehearsal/final-a-e-20261015/aux-containers-started.txt`
- `/tmp/chipcoin-mainnet-docker-rehearsal/final-a-e-20261015/aux-containers-stopped.txt`
- `/tmp/chipcoin-mainnet-docker-rehearsal/final-a-e-20261015/monitor-false-positive-recovery/`

`MAINNET_RC_READY` remains false until the four release-finalization security
gates are completed.
