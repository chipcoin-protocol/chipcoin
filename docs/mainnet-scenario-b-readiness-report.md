# MAINNET SCENARIO B READINESS REPORT

Generated: 2026-10-04

## Scope

This report covers the operational harness fixes and non-destructive readiness
checks requested after completion of Mainnet Partition/Reorg Scenario A. No
Scenario B partition, transaction submission, or SIGKILL was performed.

## Scenario A RC Gate Update

The accepted Scenario A evidence is recorded as `E-FAULT-A`. The following
runtime gates are PASS:

- partition isolation and real fork;
- cumulative-work chain selection and reorg;
- orphan block and orphan coinbase rollback;
- supply reconciliation and UTXO rollback;
- valid orphan transaction mempool re-entry;
- canonical reconfirmation of the same transaction;
- post-reorg A/B/C convergence;
- SQLite integrity for Scenario A.

Scenario B, SIGKILL, snapshot, reward lifecycle, and unrelated gates retain
their previous states.

RC-blocking gate counts after this update:

| State | Count |
| --- | ---: |
| PASS | 64 |
| FAIL | 0 |
| NOT_RUN | 23 |
| PENDING_HEIGHT | 8 |
| BLOCKED | 0 |
| Total | 95 |

`MAINNET_RC_READY` remains `FALSE`.

## Harness Fixes

### Reconnect and recovery

`reconnect` and `recover` now normalize nodes and miners onto the shared
rehearsal network without assuming that miner containers are running. A stopped
miner on a fault network is recreated as a stopped container on the expected
shared network without restarting or modifying node databases.

Repeated reconnect/recover normalization leaves the same intended topology.

### Miner operational verification

A miner is operational only when all checks pass:

- container is running;
- expected Docker network is attached;
- configured node target is reachable;
- a fresh mining-template acquisition is observed.

Successful verification emits `MINER_OPERATIONAL_ON_EXPECTED_BRANCH`.

## Regression Tests

| Test | Result |
| --- | --- |
| reconnect with miners already stopped | PASS |
| running miner attached to wrong fault network is rejected | PASS |
| stopped miner network normalization is idempotent | PASS |
| reconnect is idempotent | PASS |
| recover is idempotent at final convergence | PASS |
| shell syntax | PASS |
| script test suite | PASS, 40 tests |
| ephemeral Docker network orchestration self-test | PASS |

No real partition was created by these tests.

## Rehearsal Preflight

Observed shared-chain state:

| Field | node-a | node-b | node-c |
| --- | --- | --- | --- |
| Height | 166 | 166 | 166 |
| Tip | `0000000e39e7a144ebfe43f41d67a0dca9206d6e2d16cbaccf8bc13954f86090` | same | same |
| Cumulative work | 36594321558 | 36594321558 | 36594321558 |
| Mempool size | 0 | 0 | 0 |
| UTXO count | 169 | 169 | 169 |
| UTXO hash | `45e7646016a1742fced043fc524d15397de1aa3650805c89424ab51d73e412a0` | same | same |
| SQLite quick_check | PASS | PASS | PASS |
| SQLite foreign_key_check | PASS | PASS | PASS |

Additional checks:

- shared topology: PASS;
- miner-a operational on shared rehearsal network: PASS;
- miner-b operational on shared rehearsal network: PASS;
- fault-session lock absent: PASS;
- ordinary monitor active: PASS;
- fault monitor inactive: PASS;
- fault networks absent/not in use: PASS;
- mature unspent UTXO available for Scenario B: PASS.

## Prepared Conflicting Transactions

The transactions were validated offline against the same pre-partition UTXO
state. They were not submitted to any node and no submit evidence file exists.

Shared source outpoint:

`050891849c3faf5ce1f2e9fdc03bf244157a3e3a8a28612596eab8a78fab4485:0`

- source value: 5,000,000,000 chipbits;
- coinbase origin height: 3;
- state: mature and unspent;
- signature scheme: ML-DSA-44, scheme ID 10;
- no automatic wallet/miner spending path was identified for this outpoint.

### TX-A2

- TXID: `0d60dbfed9aa59e654464de91de0357320ae1873ec42097c4b5a7bf6bb2fb5f7`
- destination: `CHCQCqjWLptxDkCEymFxGrUkuM1VYb32zbqsK5vdsD2zKsPKHU8V2YfH`
- amount: 100,000,000 chipbits;
- change: 4,899,999,000 chipbits;
- fee: 1,000 chipbits;
- raw SHA-256: `7060684b15095f684ad66206c6b81a6eaa09da32ca8e0d969db782c902fa1dad`.

### TX-B2

- TXID: `a14b2e289d5415baf1ed693629130d3acb84c744f75e077b224dc038df58a6f9`
- destination: `CHCQCqj5EnPD6QUSTukN8oV4FHSBBtU1JHCDaAYVCNFwK7rRg95wzcNw`
- amount: 100,000,000 chipbits;
- change: 4,899,999,000 chipbits;
- fee: 1,000 chipbits;
- raw SHA-256: `12bf6154b4dbec1ca5b16fd5f15e6382883bc1d821dd815ddf388d6e4c8721b6`.

Checks: same input PASS; different TXIDs PASS; different outputs PASS;
individual pre-partition validation PASS; no submission PASS.

## Scenario B Acceptance

The complete acceptance contract is recorded in
`docs/mainnet-scenario-b-acceptance.md`. In summary, Branch A must confirm TX-A2
and Branch B must confirm conflicting TX-B2. Branch B must win naturally by
greater cumulative work. After reconnect, TX-B2 must remain canonical while
TX-A2 must be absent from both the canonical chain and mempool, with no double
spend, ghost output, supply discrepancy, orphan coinbase residue, or A/B/C
state divergence.

`CONFLICTING_ORPHAN_TX_REJECTED` may be recorded only after all of those runtime
assertions pass.

## Decision

READY_FOR_SCENARIO_B
