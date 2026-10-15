# MAINNET PARTITION / REORG - SCENARIO B DEFINITIVE REPORT

## Classification

- Scenario B: **FAIL / NOT COMPLETED**
- Harness/operational blocker: **YES**
- Consensus/state blocker: **NO EVIDENCE**
- Rehearsal validity: **PRESERVED AND RESTORED**
- TX-A2 submitted: **NO**
- TX-B2 submitted: **NO**
- SIGKILL executed: **NO**

MemPalace was consulted before execution for the expected conflicting-spend,
cumulative-work and mempool reconciliation behavior.

## Result Matrix

| Check | Result | Evidence |
|---|---|---|
| Baseline | PASS | A/B/C converged at height 182. |
| Fault monitor health | PASS | Session-owned unit active/running, MainPID `3274922`, iteration 1 PASS. |
| Partition activation | FAIL | Cutover occurred, but the orchestrator was terminated before persisting `SCENARIO_B_PARTITION_ACTIVE`. |
| Isolation | NOT_RUN | No completed isolation checkpoint/state transition. |
| Real fork | NOT_RUN | No branch production was awaited. |
| TX-A2 isolated confirmation | NOT_RUN | TX-A2 was not submitted. |
| TX-B2 isolated confirmation | NOT_RUN | TX-B2 was not submitted. |
| Same-input conflict | NOT_RUN | Manifests match, but runtime conflict was not exercised. |
| B cumulative-work winner | NOT_RUN | No Scenario B branches were mined. |
| Reconnect | PASS | Recovery restored shared Docker topology. |
| Natural reorg | NOT_RUN | No Scenario B fork existed. |
| TX-B2 canonical preservation | NOT_RUN | TX-B2 was not submitted. |
| TX-A2 orphan rollback | NOT_RUN | TX-A2 was not submitted. |
| `CONFLICTING_ORPHAN_TX_REJECTED` | NOT_RUN | Required runtime state was not reached. |
| Orphan coinbase rollback | NOT_RUN | No Scenario B orphan blocks existed. |
| Supply reconciliation | NOT_RUN | Scenario assertion not exercised. |
| UTXO reconciliation | NOT_RUN | Scenario assertion not exercised. |
| No double spend | NOT_RUN | Scenario assertion not exercised. |
| No ghost outputs | NOT_RUN | Scenario assertion not exercised. |
| Pre-mining convergence | NOT_RUN | Scenario did not reach post-reorg checks. |
| Chain continuation | NOT_RUN | Scenario did not reach post-reorg mining. |
| Final convergence | PASS (recovery only) | A/B/C restored to one fingerprint; not a Scenario B consensus PASS. |
| SQLite integrity | PASS | quick_check `ok`; foreign_key_check empty on A/B/C. |
| Fault monitor cleanup | PASS (manual recovery) | Unit/process/metadata/health/lock removed after preserving evidence. |

## Baseline

- Height: `182`
- Tip: `0000000d815dad33af9a8215f1c886d116f14a8f34d32c83d0768a4e4832c3ad`
- Cumulative work: `40100364342`
- Materialized supply: `915000000000` chipbits
- UTXO count: `186`
- UTXO hash: `54ac76ce815ea1d90ac4dad88c96c73331ec4f6d62fedb856b7dbfb7231b4f7e`
- Mempool: `0`
- Handshaken peers: `2` per node
- UTXO-Y: `40544d3f6928ee126022dc08d8fa0507a7f333c62fa46584e918410a0cff7a39:0`, present, mature, unspent

## Monitor Evidence

- Session ID: `fault-20261004T185557Z-3271815`
- Unit: `chipcoin-mainnet-fault-monitor-fault-20261004T185557Z-3271815.service`
- MainPID: `3274922`
- Unit state: loaded, active, running
- Health: iteration `1`, status `PASS`, matching session ID

The execution command was terminated by the external command runner after the
health handshake and network cutover but before the activation function could
persist its final phase marker. Under the fail-fast policy, no transaction was
submitted and recovery began immediately.

## Recovery Finding

`recover_session()` called `write_lock()` before monitor cleanup. This replaced
the original lock session ID with a new recovery session ID. The hardened stop
correctly refused to stop a monitor owned by the original session. Evidence for
both identities and the monitor journal was preserved before an explicit
ownership-preserving operational cleanup.

This is an operational harness defect. No node, consensus, P2P, mempool, reorg,
database or transaction logic was modified.

## Final Recovered State

- Height: `184`
- Tip: `00000002d9e5fedde66bc2e59fedc9964e9ac4d48274fad1ef19d48929476d20`
- Cumulative work: `40538619690`
- Materialized supply: `925000000000` chipbits
- UTXO count: `188`
- UTXO hash: `21b60bd86010569514b0099faf7d3d83e31848353c0e73ca3ec911e6324304ba`
- Mempool: `0`
- Handshaken peers: `2` per node
- SQLite: quick_check `ok`, foreign_key_check empty
- Shared topology: restored for all nodes and miners
- Ordinary monitor: active
- Fault units/processes/lock/ownership: absent

## Values Not Produced

Because execution stopped before fork and transaction submission, there is no
Scenario B common ancestor, divergent branch tip/work, TX-A2 block, TX-B2 block,
winning work margin, natural reorg, or conflicting-orphan result.

## RC Impact

- `CONS-RUN-005`: `NOT_RUN`
- `FAULT-RUN-012`: `NOT_RUN`
- `FAULT-OPS-001`: `FAIL`
- P2P zero-handshake/zero-reconnect concern: remains open and was not observed
  during this attempt.
