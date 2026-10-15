# MAINNET SCENARIO B RECOVERY REPORT

Generated: 2026-10-04

## Classification

- Scenario B: FAIL / not completed;
- harness operational blocker: yes;
- consensus/state blocker: no evidence;
- rehearsal recovery: PASS.

## Root Cause

The Scenario B checkpoint command failed before TX-A2 confirmation because
`confirm_scenario_b_tx()` referenced `side` while declaring and initializing it
in the same Bash `local` statement under `set -u`.

The first recovery attempt also exposed an unsupported
`docker compose create --no-deps` invocation. The installed Compose version
supports `create`, but not that option.

## Node-A P2P Diagnosis

Docker topology was correct after reconnect:

- node-a was running and attached to the shared network;
- aliases and DNS resolution for node-a/node-b/node-c were correct;
- TCP port 8333 was reachable in both directions;
- node-a nevertheless reported zero handshaken peers and zero reconnect tasks.

The persisted peerbook showed the canonical outbound `node-c:8333` peer in
backoff for approximately 5,700 seconds after 72 failed reconnect attempts
during intentional isolation. The latest error was temporary DNS resolution
failure. The runtime had no active reconnect task while that backoff remained.

## Controlled Restart

Restart required: YES.

Only node-a was restarted. Its existing database/runtime was retained. No
database, tip, mempool, block, or peer record was edited. Miners remained
stopped during restart and convergence.

After restart, node-a rebuilt its live peer scheduling and completed a
handshake. Node-b and node-c then naturally adopted node-a's branch because its
cumulative work was greater:

- branch A work: 38128215276;
- branch B/C work: 37909087602.

The canonical branch was therefore selected by cumulative work, not height
alone.

## TX-A2

TX-B2 was never submitted. This was not a conflicting-spend execution.

TX-A2 was accepted only into node-a's mempool before the harness failure. It
propagated naturally after shared connectivity was restored. Following normal
mining it was confirmed once at height 174 in block:

`00000002145d0591d9a7e3cffb920107d6c5d17238f822b237d738fbcce71bf8`

TX-A2 was not manually resubmitted or removed.

## Final State

| Field | node-a | node-b | node-c |
| --- | --- | --- | --- |
| Height | 179 | 179 | 179 |
| Tip | `0000000bcb419d613f429e536147862563055b1bdd68e8f37c09df62e20e6786` | same | same |
| Cumulative work | 39442981320 | 39442981320 | 39442981320 |
| Supply | 900000000000 | 900000000000 | 900000000000 |
| UTXO count | 183 | 183 | 183 |
| UTXO hash | `508ca6ed63a13ffd5b674db3bb9078bab5028183c377f09c7c3486265a2b7654` | same | same |
| Mempool | 0 | 0 | 0 |
| SQLite quick_check | PASS | PASS | PASS |
| SQLite foreign_key_check | PASS | PASS | PASS |

- reward registry state: identical;
- fault lock: released;
- fault monitor: inactive;
- ordinary monitor: active and no longer suppressed;
- shared topology: restored;
- miner-a/miner-b: operational on shared topology;
- post-recovery block and continuing A/B/C convergence: PASS.

Evidence is preserved under
`/tmp/chipcoin-mainnet-docker-rehearsal/fault/evidence/`, including the frozen
failure state, P2P diagnosis, monitor journals, Docker inspection, database
checksums, restart evidence, and final fingerprints.
