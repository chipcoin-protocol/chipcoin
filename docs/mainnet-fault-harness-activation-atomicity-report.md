# Mainnet Fault Harness Activation Atomicity Report

Date: 2026-10-05

## Root Cause

`scenario-b-activate` had no explicit completion barrier after cutover. The
activation invocation still had foreground partition verification work to do,
notably peer-topology collection, while an external observer treated the
yielded command result as completion. Persisted evidence proves the ordering:

- final shared-network disconnect persisted at 23:48:42 CEST;
- `partition-peers.json` and `partition-verified.json` persisted at 23:48:54;
- only then did the lifecycle enter `SCENARIO_B_PARTITION_ACTIVE`.

No harness background job or fault monitor wrote the activation transition.
The activation command was the writer, but its previous contract did not make
durable completion independently assertable by the caller.

## Lifecycle Writers

- `activate_scenario_b`: owns prepare, cutover, partition verification and the
  `SCENARIO_B_PARTITION_ACTIVE` transition.
- `monitor_loop`: observes health and writes only monitor-health evidence.
- recovery/finalization commands: own their explicit recovery transitions.
- `mainnet-fault-session.py` and `mainnet-fault-state.py`: serialize validated
  writes with atomic replacement and directory fsync.

The fault monitor does not complete activation transitions.

## Completion Contract

Exit 0 now requires all of the following before return:

- Docker topology and cross-branch P2P isolation verified;
- `partition-verified.json` reports PASS;
- fault monitor remains healthy for the immutable session ID;
- fault lock reads `current_phase=PARTITION_ACTIVE`;
- fault lock reads `topology_state=PARTITION_ACTIVE`;
- lifecycle state reads `SCENARIO_B_PARTITION_ACTIVE`;
- persisted files are fsynced and reread successfully;
- activation-owned shell jobs have completed.

Any failure enters the existing activation rollback path and returns non-zero.

## Validation

- Script regression suite: 102 PASS.
- Artificial delays across verification, persistence and reread: PASS.
- Immediate post-return persisted-state assertion: PASS.
- `NO_POST_RETURN_ACTIVATION_TRANSITION`: PASS.
- Ten consecutive Docker activation/recovery cycles: PASS.
- Process-kill recovery at 17 checkpoints: PASS.
- New barrier checkpoints before verification, before persistence, after
  persistence and after reread: PASS.
- Shell syntax and `git diff --check`: PASS.

## Rehearsal Safety

The live rehearsal was not partitioned during this hardening. It remains on
the shared topology in `FINAL_CONVERGENCE`, with normal mining, ordinary
monitoring, no fault lock and no submitted Scenario B transaction.

## RC Result

- `FAULT-OPS-001 = PASS`
- `FAULT-OPS-002 = PASS`
- `FAULT-OPS-003 = PASS`
- `CONS-RUN-005 = NOT_RUN`
- `FAULT-RUN-012 = NOT_RUN`

`ACTIVATION_ATOMICITY_VALIDATED = YES`
