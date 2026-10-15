# MAINNET FAULT MONITOR LIFECYCLE HARDENING REPORT

## Classification

- Fault monitor lifecycle hardening: **PASS**
- Consensus/node/P2P changes: **NONE**
- Scenario B execution: **NOT RUN**
- SIGKILL: **NOT RUN**

MemPalace was consulted before implementation. It did not contain a more
specific historical systemd lifecycle decision, so the implementation and the
preserved runtime evidence were used as the authoritative sources.

## Exact Systemd Root Cause

The previous monitor used one fixed transient unit name:
`chipcoin-mainnet-fault-monitor.service`.

The preserved state was:

| Property | Value |
|---|---|
| Unit | `chipcoin-mainnet-fault-monitor.service` |
| LoadState | `loaded` |
| ActiveState | `failed` |
| SubState | `failed` |
| Result | `exit-code` |
| ExecMainStatus | `1` |
| Transient | `yes` |

The sequence was:

1. A previous fault session created the fixed-name transient unit.
2. Its monitor loop returned status 1 during recovery and systemd retained the
   transient unit in the loaded/failed state.
3. The old stop path ignored errors and did not perform `reset-failed`, verify
   process exit, or remove session ownership metadata.
4. A later activation reused the same fixed name and had no session identity or
   completed-health-iteration handshake.
5. The activation could therefore progress without proving that a new monitor
   process owned and observed the current fault session.

## Implemented Lifecycle

The lifecycle is now explicit:

`ABSENT/CLEAN -> STARTING -> ACTIVE -> STOPPING -> CLEAN`

and recovery is:

`FAILED -> RESET/CLEAN -> STARTING`.

Each fault lock receives a unique session ID. Its monitor uses a session-specific
unit name and persists:

- session ID;
- unit name;
- start timestamp;
- expected phase;
- MainPID;
- latest successful health iteration.

An active monitor owned by another session is rejected. An inactive or failed
old unit is stopped where necessary, awaited, reset, checked for a zero MainPID,
and cleared before startup. The legacy fixed-name unit is also cleaned during
pre-start and stop for migration safety.

## FAULT_MONITOR_HEALTHY

Cutover is allowed only when all of these are true:

- metadata and health files exist;
- metadata session ID matches the current fault lock;
- systemd `LoadState=loaded`;
- `ActiveState=active`;
- `SubState=running`;
- `Result` is empty or `success`;
- MainPID is nonzero and alive;
- health session ID matches;
- at least one monitor iteration completed with `status=PASS`.

The monitor loop independently verifies the lock/session identity before every
iteration. A mismatch or missing lock terminates the process with failure.

## Cleanup Semantics

PASS and recovery paths now:

1. stop the session-owned monitor;
2. wait for inactive/failed terminal state;
3. reset failed state;
4. verify MainPID is zero;
5. archive monitor metadata;
6. remove monitor ownership and health files;
7. assert `FAULT_MONITOR_CLEAN`;
8. only then release the fault lock.

Stop errors are not ignored. Ownership metadata remains available when cleanup
fails, preventing the session from being presented as clean.

## Regression And Failure Injection

The regression suite covers:

- previous failed unit;
- previous inactive but loaded unit;
- active monitor owned by the same session;
- active monitor owned by another session;
- start returning before a healthy process exists;
- missing successful health iteration;
- stop failure with ownership evidence preserved;
- interrupted activation and rollback;
- lock/session mismatch;
- timeout/deadline initialization under `set -u`.

Results:

- `tests/scripts`: **60 PASS**
- shell syntax: **PASS**
- `git diff --check`: **PASS**
- deterministic Docker network self-test: **PASS**
- Docker activation/cutover/rollback self-test: **PASS**

## Two Consecutive Docker Sessions

The same ephemeral Docker environment completed, without external cleanup:

1. Session 1: normal topology, healthy monitor, partition, recovery, monitor
   clean, normal topology.
2. Session 2: the same full sequence with a new session ID and transient unit.

Final assertions after Session 2:

- no failed/running fault-monitor unit;
- no monitor process;
- no fault lock;
- no monitor ownership/health metadata;
- no fault-network attachment;
- all ephemeral containers returned to their shared network.

Result: **PASS**.

## Rehearsal State And Transaction Readiness

The real rehearsal was not partitioned during hardening. Final read-only check:

- phase: `FINAL_CONVERGENCE`;
- current height: 182;
- node-a/node-b/node-c: running and convergent;
- miner-a/miner-b: running on shared topology;
- ordinary monitor: active;
- fault lock: absent;
- session fault monitor: absent;
- TX-A2/TX-B2 submit artifacts: absent.

UTXO-Y remains present, mature and unspent:
`40544d3f6928ee126022dc08d8fa0507a7f333c62fa46584e918410a0cff7a39:0`.
The existing TX-A2/TX-B2 manifests therefore remain ready and were not rebuilt
or submitted.

## RC Tracking

- `FAULT-OPS-001`: **PASS** - monitor reusable across consecutive sessions.
- `CONS-RUN-005`: **NOT_RUN**.
- `FAULT-RUN-012`: **NOT_RUN**.
- P2P zero-handshake/zero-reconnect-task recovery concern: **OPEN**, separate
  operational/reliability concern and not a consensus failure.

`FAULT_HARNESS_STABLE = YES`

`READY_FOR_SCENARIO_B = YES`
