# MAINNET SCENARIO B ACTIVATION FIX REPORT

Generated: 2026-10-04

## Root Cause

The previous `scenario-b-activate` implementation acquired the fault lock and
disconnected every rehearsal service from the shared network. It neither
created nor attached the Scenario B fault networks and did not perform the
monitor handoff. Starting from normal topology would therefore isolate
individual containers instead of creating Branch A and Branch B.

## Fix

Scenario B activation is now self-contained and ordered as follows:

1. verify phase, global A/B/C convergence, SQLite integrity, shared topology,
   running services, operational miners, monitor state, absent fault lock, and
   unsubmitted TX-A2/TX-B2;
2. idempotently create and validate internal `fault_a` and `fault_b` networks;
3. attach Branch A (`node-a`, `miner-a`) and Branch B (`node-b`, `node-c`,
   `miner-b`) while retaining the shared network;
4. verify exact membership and branch-specific miner targets before cutover;
5. acquire the fault lock, start/adopt the fault monitor, verify it is active,
   and verify ordinary-monitor fault awareness;
6. disconnect the shared network one service at a time, persisting a checkpoint
   after each disconnect;
7. verify Docker membership, branch-local reachability, cross-branch P2P
   rejection, and operational miners;
8. transition to `SCENARIO_B_PARTITION_ACTIVE` only after all checks pass.

Miner operational checks now use branch-specific targets. In particular,
`miner-a` requires `node-a` on Branch A rather than the shared-topology
fallback target `node-c`.

## Rollback

Any failure before the active-partition marker triggers a deterministic
rollback:

- stop miners;
- reconnect every service to the shared network;
- remove incomplete fault attachments and fault networks;
- stop the fault monitor;
- archive/release the fault lock;
- wait for A/B/C convergence;
- restore normal mining;
- return to `FINAL_CONVERGENCE`.

If convergence cannot be restored, the state machine records
`RECOVERY_REQUIRED`. A stale lock detected before activation also records
`RECOVERY_REQUIRED` without performing a cutover.

## Tests

The regression suite covers:

- activation with fault networks absent;
- existing/idempotent network creation and partial attachments;
- healthy fault monitor already running at handoff;
- interrupted activation with stale lock;
- repeated activation after `SCENARIO_B_PARTITION_ACTIVE`;
- failure during network creation;
- failure during branch attachment;
- failure during fault-monitor startup;
- failure during an intermediate shared-network disconnect;
- rollback to `FINAL_CONVERGENCE` for each injected failure.

Results:

- shell syntax: PASS;
- script test suite: PASS, 47 tests;
- diff whitespace validation: PASS;
- Docker activation/cutover/rollback self-test: PASS.

The Docker self-test used five temporary Alpine containers and three temporary
internal networks. It verified attach-before-cutover, branch-local
communication, cross-branch isolation, rollback to shared connectivity, and
cleanup. It did not use rehearsal containers or networks.

## Current Rehearsal State

| Node | Height | Tip | Cumulative work | UTXO count | UTXO hash | SQLite |
| --- | ---: | --- | ---: | ---: | --- | --- |
| node-a | 167 | `00000007ca9690d61cd9e86b7228359187929bfac1777a678f7da7f0ecd1a271` | 36813449232 | 170 | `165bf4f84a2942ace928ec058b512b8d0e17afbf10c02984a5826fc0c31d561e` | PASS |
| node-b | 167 | same | 36813449232 | 170 | same | PASS |
| node-c | 167 | same | 36813449232 | 170 | same | PASS |

- A/B/C convergence: PASS;
- mempool size: 0 on all nodes;
- ordinary monitor: active;
- fault monitor: inactive;
- fault lock: absent;
- real fault networks: absent;
- TX-A2 submitted: no;
- TX-B2 submitted: no;
- real Scenario B partition performed: no.

No consensus RC gate was changed. Scenario B remains `NOT_RUN`.

READY_FOR_SCENARIO_B
