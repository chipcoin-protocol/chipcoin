# MAINNET FAULT HARNESS CRASH-RECOVERY VALIDATION REPORT

Date: 2026-10-04

## Result

The offline fault-harness recovery gate is **PASS**. These tests exercised only
ephemeral Docker resources and the harness process. No rehearsal node was
partitioned, restarted, killed, or given a transaction.

## Failure-Point Matrix

Each case persisted the original session ID, terminated the orchestrator
process, started recovery in a new invocation, restored normal topology,
stopped only the owned monitor, and removed all residual fault state.

| Checkpoint | Result |
|---|---|
| Before monitor start | PASS |
| After monitor start | PASS |
| After health handshake | PASS |
| During fault-network attach | PASS |
| After attach | PASS |
| During shared-network disconnect | PASS |
| Immediately after cutover | PASS |
| Before `PARTITION_ACTIVE` marker | PASS |
| After `PARTITION_ACTIVE` | PASS |
| During reconnect | PASS |
| During monitor stop | PASS |
| During cleanup | PASS |
| During lock release | PASS |

For every case:

- `fault_session_id` remained unchanged;
- `recovery_attempt_id` was separate;
- no foreign monitor was stopped;
- no monitor process, fault lock, or fault-network attachment remained;
- normal topology was restored without manual cleanup.

## Process-Kill Test

`fault-session-crash-self-test` launched a fresh harness child at each of the
13 checkpoints and sent `SIGKILL` to that orchestrator shell only. A new
invocation recovered exclusively from persisted state. Result: **13/13 PASS**.

This is not the node SIGKILL gate (`FAULT-RUN-013`), which remains `NOT_RUN`.

## Consecutive Sessions

`fault-monitor-consecutive-self-test` completed three sessions in one ephemeral
Docker environment without external cleanup:

1. activation -> monitor healthy -> partition -> recovery -> monitor clean;
2. activation -> monitor healthy -> partition -> recovery -> monitor clean;
3. activation -> monitor healthy -> partition -> recovery -> monitor clean.

Result: **3/3 PASS**. After session 3 there was no failed transient unit,
monitor process, fault lock, fault attachment, or session ownership residue.

## Regression And Docker Tests

| Test | Result |
|---|---|
| Script regression suite | PASS, 87 tests |
| Shell syntax | PASS |
| Immutable identity assertion | PASS |
| Invalid transition rejection | PASS |
| Docker deterministic network orchestration | PASS |
| Docker activation/cutover/rollback | PASS |
| Orchestrator process-kill recovery | PASS, 13 checkpoints |
| Three consecutive Docker sessions | PASS |
| `git diff --check` | PASS |

No manual cleanup was used to obtain these results.

## Rehearsal State

The final read-only check reported:

- phase `FINAL_CONVERGENCE`;
- node-a, node-b, node-c running;
- miner-a and miner-b running;
- normal shared network membership restored;
- ordinary monitor active;
- prepared Scenario B transactions remain `submitted=false`.

Fault networks may still exist as unused Docker network objects, but no
rehearsal container is attached to them. No fault lock or live fault monitor is
present.

## RC Tracking

- `FAULT-OPS-001`: PASS based on the immutable identity and offline recovery evidence above.
- `FAULT-OPS-002`: NOT_RUN; P2P zero-handshake/zero-reconnect reliability concern remains open.
- `CONS-RUN-005`: NOT_RUN.
- `FAULT-RUN-012`: NOT_RUN.
- `FAULT-RUN-013`: NOT_RUN.

The fault harness is ready as an RC component, but this does not make the whole
mainnet release candidate ready and does not authorize another Scenario B.

FAULT_HARNESS_RC_READY = YES
