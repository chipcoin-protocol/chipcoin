# MAINNET SCENARIO B HARNESS FIX / READINESS REPORT

Generated: 2026-10-04

## Harness Fixes

### Scenario B confirmation

`confirm_scenario_b_tx()` now initializes `side` before using it in the
evidence-directory path. A regression test invokes the exact code path under
`set -u` and rejects the previous `side: unbound variable` behavior.

### Compose compatibility

Stopped miner recreation now uses `docker compose create SERVICE`; the
unsupported `--no-deps` option was removed. A regression assertion prevents
its reintroduction.

### Fault monitor

The fault monitor failed because recovery intentionally stopped both miners
while `monitor_once()` unconditionally treated any stopped miner as a
consensus failure. Nodes remain mandatory in every phase. Miner liveness is
now mandatory only in phases where both miners are expected to be producing
branch work; stopped miners are accepted during reconnect/recovery and other
explicit miner-control phases.

### Shared-network peer recovery

Recovery now waits explicitly for nonzero handshaken peer counts after shared
network restoration. If Docker networking is restored but peers do not
handshake, it records evidence, transitions to `RECOVERY_REQUIRED`, and reports
that a controlled restart may be required. It does not modify peerbook state or
node code.

## Regression Results

- shell syntax: PASS;
- complete script suite: PASS, 51 tests;
- `side` unbound-variable regression: PASS;
- Compose compatibility regression: PASS;
- stopped-miner fault-monitor regression: PASS;
- zero-handshake shared-topology regression: PASS;
- activation failure-injection tests: PASS;
- reconnect/recover tests: PASS;
- Docker activation/cutover/rollback self-test: PASS;
- `git diff --check`: PASS.

## New Scenario B Baseline

A/B/C are converged on the shared topology. Ordinary monitoring is active,
the fault monitor is inactive, and the fault lock is absent.

The previous transaction evidence was archived. New conflicting transactions
were built and validated offline against the recovered canonical state. Neither
transaction has been submitted.

Shared UTXO-Y:

`40544d3f6928ee126022dc08d8fa0507a7f333c62fa46584e918410a0cff7a39:0`

- value: 5,000,000,000 chipbits;
- mature and unspent at preparation;
- source: PQ mainnet address;
- signature scheme: ML-DSA-44, scheme ID 10.

TX-A2:

- TXID: `7d3c4a35aed843788cfc03cddbbeae70c7b963306db89e901cb11f0b733a4122`;
- raw SHA-256: `de937f73cc5be5d8f5f21f61fa827dbddf8068a8ef91422ec725c20ceb43e0d2`;
- destination: reward-a owner CHCQ address;
- amount: 100,000,000 chipbits;
- change: 4,899,999,000 chipbits;
- fee: 1,000 chipbits.

TX-B2:

- TXID: `ad9abec59da2545296d8ea3d35bf340cb3008d908f46520bc17e10384ee49885`;
- raw SHA-256: `0cae2aa63646de708604bbaed2a3f44fdfbd878f98af613130f205286bc947fa`;
- destination: reward-b owner CHCQ address;
- amount: 100,000,000 chipbits;
- change: 4,899,999,000 chipbits;
- fee: 1,000 chipbits.

Both transactions independently validate against the current UTXO state,
spend the identical outpoint, have different TXIDs and outputs, and have no
submit artifact.

Scenario B consensus gates remain NOT_RUN. No consensus FAIL was recorded.

READY_FOR_SCENARIO_B
