# MAINNET PARTITION / REORG - SCENARIO B FINAL REPORT

## Classification

- Scenario result: **FAIL / NOT COMPLETED**
- Harness/operational blocker: **YES**
- Consensus/state blocker: **NO EVIDENCE**
- Rehearsal validity: **PRESERVED AND RESTORED TO NORMAL CONVERGENCE**

MemPalace was consulted before execution for the expected cumulative-work and
mempool reconciliation behavior.

## Results

| Check | Result | Evidence / note |
|---|---|---|
| Baseline | PASS | A/B/C converged at height 180, tip `00000005dc9017092ed3f9568aa202410fa38d5d9bb9a6be1b62ab24b276fd6e`, work `39662108994`; UTXO-Y present and mature. |
| Partition activation | FAIL | Activation reached the isolated attachments, but the fault monitor transient unit remained in failed state. The run was recovered immediately. |
| Isolation | NOT_RUN | No stable monitored Scenario B session was established. |
| Fork | NOT_RUN | No fork was intentionally awaited after the activation failure. |
| TX-A2 isolated confirmation | NOT_RUN | TX-A2 was not submitted. |
| TX-B2 isolated confirmation | NOT_RUN | TX-B2 was not submitted. |
| Same-input conflict | NOT_RUN | Manifests prove the same input offline, but the runtime conflict was not exercised. |
| B cumulative-work winner | NOT_RUN | No Scenario B branches were mined. |
| Reconnect | PASS | Validated recovery restored all nodes and miners to the shared network. |
| Natural reorg | NOT_RUN | No Scenario B fork existed. |
| TX-B2 canonical preservation | NOT_RUN | TX-B2 was not submitted. |
| TX-A2 orphan rollback | NOT_RUN | TX-A2 was not submitted. |
| `CONFLICTING_ORPHAN_TX_REJECTED` | NOT_RUN | Consensus assertion not exercised. |
| Orphan coinbase rollback | NOT_RUN | No Scenario B orphan blocks were produced. |
| Supply reconciliation | NOT_RUN | Scenario assertion not exercised. |
| UTXO reconciliation | NOT_RUN | Scenario assertion not exercised. |
| No double spend | NOT_RUN | Scenario assertion not exercised. |
| No ghost outputs | NOT_RUN | Scenario assertion not exercised. |
| Pre-mining convergence | NOT_RUN | Scenario did not reach the reorg stage. |
| Post-reorg continuation | NOT_RUN | Scenario did not reach the reorg stage. |
| Final convergence | PASS (recovery only) | Recovery returned the existing chain to `FINAL_CONVERGENCE`; this is not a Scenario B consensus PASS. |
| SQLite integrity | PASS | Harness monitor check passed after recovery. |

## Baseline Transaction Evidence

- UTXO-Y: `40544d3f6928ee126022dc08d8fa0507a7f333c62fa46584e918410a0cff7a39:0`
- UTXO-Y origin: coinbase at height 5, value `5000000000` chipbits
- TX-A2: `7d3c4a35aed843788cfc03cddbbeae70c7b963306db89e901cb11f0b733a4122`
- TX-A2 raw SHA-256: `de937f73cc5be5d8f5f21f61fa827dbddf8068a8ef91422ec725c20ceb43e0d2`
- TX-B2: `ad9abec59da2545296d8ea3d35bf340cb3008d908f46520bc17e10384ee49885`
- TX-B2 raw SHA-256: `0cae2aa63646de708604bbaed2a3f44fdfbd878f98af613130f205286bc947fa`
- Submit artifacts: none

## Operational Failure

The existing transient unit `chipcoin-mainnet-fault-monitor.service` was still
loaded in the systemd user manager with result `failed`. The activation path did
not establish a healthy fault monitor for the new session. Because an active
fault monitor is mandatory, the execution was aborted and the validated
recovery path was used before any transaction submission.

The recovery restored:

- shared Docker topology for node-a/node-b/node-c and both miners;
- A/B/C convergence;
- no fault-session lock;
- fault monitor inactive with its previous failed state cleared;
- ordinary monitor active;
- normal mining resumed;
- TX-A2 and TX-B2 still unsubmitted.

## Open RC Reliability Concern

Keep the previously observed P2P recovery behavior open as a separate RC
operational/reliability concern: a node can be attached to a reachable shared
network with working Docker DNS/TCP while reporting zero handshaken peers and
zero reconnect tasks, and may require a controlled restart. This is not
classified as a consensus failure.

## RC Gate Impact

No Scenario B consensus gate was changed to PASS. `CONS-RUN-005` and
`FAULT-RUN-012` remain `NOT_RUN`.
