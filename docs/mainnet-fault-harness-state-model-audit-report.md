# MAINNET FAULT HARNESS STATE-MODEL AUDIT REPORT

Date: 2026-10-04

Scope: offline harness refactor only. No rehearsal partition, transaction submit,
node restart, node SIGKILL, consensus change, or P2P implementation change was
performed.

## Root Cause

The failed cleanup followed this identity sequence:

1. `original_session_id` was written to the fault lock.
2. The transient monitor was started and owned by that identity.
3. `recover_session()` called the old lock-creation path.
4. That path replaced the lock with a new session ID.
5. Monitor ownership still referenced `original_session_id`.
6. Ownership-aware monitor stop correctly refused a foreign-session stop.

The safety check was correct; the recovery identity mutation was not. Phase,
command invocation, monitor process, and fault-session identity had been mixed
inside mutable shell state.

## Identity Inventory

| Responsibility | Function/component |
|---|---|
| Create identity | `write_lock()` -> `mainnet-fault-session.py create` |
| Read identity | `fault_session_id()` |
| Update lock | `fault_session_update()` |
| Start recovery | `fault_session_begin_recovery()` |
| Monitor ownership | `fault_monitor_pre_start_cleanup()`, `fault_monitor_start()`, `fault_monitor_healthy()`, `fault_monitor_stop()` |
| Activation rollback | `scenario_b_activation_rollback()` |
| Explicit recovery | `recover_session()` |
| Normalization | `normalize_shared_topology()`, `reconnect()` |
| Final cleanup | `finalize_convergence()`, `release_lock()` |

The audit also found identity-sensitive state in systemd unit names, PIDs,
timestamps, phase markers, and shell command invocations. These are now stored
as attributes of a session; none can replace its identity.

## Versioned Lock

`scripts/mainnet-fault-session.py` owns atomic lock creation and updates. Schema
version 1 requires:

- `fault_session_id`: immutable identity;
- `created_at` and `updated_at`;
- `current_phase`;
- `monitor_unit`, `monitor_main_pid`, `monitor_session_id`;
- `recovery_state` and optional `recovery_attempt_id`;
- `topology_state`;
- `last_completed_step`.

Updates require the expected identity. An attempted replacement raises
`FAULT_SESSION_ID_IMMUTABLE`. Recovery creates a separate
`recovery_attempt_id` and preserves `fault_session_id`. Writes use atomic file
replacement.

## State Machine

`NORMAL` is represented by no active fault lock and normal shared topology.
The persisted fault-session states are:

| State | Required resources | Monitor | Topology/miners | Recovery entry |
|---|---|---|---|---|
| `PREPARING` | lock | absent | shared; miners may run | restore shared, clean staged resources |
| `MONITOR_STARTING` | lock, unit identity | starting | shared | stop owned unit, restore shared |
| `MONITOR_HEALTHY` | lock, live owned monitor | healthy | shared | stop owned unit, restore shared |
| `CUTOVER` | lock, healthy monitor | healthy | checkpointed partial cutover; miners controlled | stop miners, restore shared |
| `PARTITION_ACTIVE` | lock, healthy monitor | healthy | fault branches isolated | stop miners, reconnect shared |
| `FORK_ACTIVE` | lock, branch evidence | healthy | divergent branches | stop miners, reconnect shared |
| `RECONNECTING` | lock | healthy until cleanup | shared restoration in progress; miners stopped | continue normalization |
| `REORG_VALIDATING` | lock | healthy | shared; miners stopped | preserve evidence, normalize |
| `RECOVERING` | original lock, recovery attempt | owned monitor stopping | miners stopped; shared restoration | resume same recovery idempotently |
| `FINAL_CONVERGENCE` | lock until cleanup | clean | shared and converged | verify cleanup, release lock |
| `RECOVERY_REQUIRED` | lock and evidence | ownership-dependent | unknown/partial; miners stopped | explicit recovery on original ID |

Allowed transitions are encoded in `TRANSITIONS`; invalid transitions fail.
No function infers a fault identity from a phase.

## Recovery Semantics

`recover_session(existing_session_id)` now:

1. loads and asserts the original lock identity;
2. records a distinct recovery attempt;
3. stops only the monitor owned by the original session;
4. stops miners where necessary;
5. restores shared topology;
6. verifies P2P/topology and convergence;
7. restores ordinary monitoring;
8. removes fault resources;
9. records `FINAL_CONVERGENCE`;
10. releases the lock only after monitor cleanup is proven.

It does not create or overwrite a session identity. Repeated recovery is
idempotent; an already-clean `FINAL_CONVERGENCE` state reports no active fault
session.

## Crash Consistency

Important operations follow `action -> verification -> persisted checkpoint`.
Network creation, branch attachment, monitor health, each shared-network
disconnect, partition confirmation, reconnect, monitor cleanup, convergence,
and lock release are checkpointed. A replacement process needs only the lock
and observed Docker/systemd state; it does not depend on variables from the
dead shell.

## Residual Risks

- Scenario B consensus behavior remains `NOT_RUN`; harness tests cannot replace it.
- Node SIGKILL recovery remains `NOT_RUN`.
- `FAULT-OPS-002` remains open: shared network and TCP can be healthy while a
  node has zero handshakes and zero reconnect tasks until restart. This is a
  separate P2P reliability concern, not fixed in this refactor.
- Runtime evidence under `/tmp` still requires secure archival before RC.
