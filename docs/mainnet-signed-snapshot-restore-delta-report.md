# Mainnet Signed Snapshot / Restore / Delta Report

Date: 2026-10-05

## Result

The official snapshot tooling exported canonical mainnet rehearsal state at
height 249, signed it through the protected `--private-key-file` path, restored
it into an empty Docker node, and synchronized a real ten-block delta over P2P.
The restored node then remained converged with node-a, node-b, and node-c
through a subsequent canonical block.

| Check | Result |
|---|---|
| Signed snapshot from real mainnet state | `PASS` |
| Trusted signature verification | `PASS` |
| Tamper and trust negative tests | `PASS` |
| Empty-runtime restore | `PASS` |
| Snapshot-point state equality | `PASS` |
| Real P2P delta sync | `PASS` |
| A/B/C/restore deterministic convergence | `PASS` |
| Post-convergence chain continuation | `PASS` |
| SQLite integrity | `PASS` |
| Private-key leakage scan | `PASS` |

## Snapshot

| Field | Value |
|---|---|
| Network | `mainnet` |
| Snapshot height | `249` |
| Snapshot block hash | `0000000c241482e41fdbb85ecb21334c887cf4225bc9f071fc2b043d1d81c2b4` |
| Genesis hash | `00000007f247394d7ddec57448af5a635aa53465ad06d8d5ede66f812cfe7cc6` |
| Cumulative work | `54781918500` |
| Materialized supply | `1250000000000` chipbits |
| UTXO count | `254` |
| UTXO hash | `9666b15e0c73b54e7852f85f93f53d326b74da0df5f464f6c65ddca2ae5fd35d` |
| Artifact size | `76718` bytes |
| Artifact SHA-256 | `a661390127d6b629811ace6c2960008a58c417e8760328e4f55c66ddca9b1e4a` |
| Logical checksum | `9b176170bea928d915176859bdc61cb664031134ab3e882ee33d7ce11afbb8e7` |
| Signer public key | `37fa9515a0e0065eeb2236ec14c8d94de1ab100dd63e664f30d95f7aeae3ffb1` |

The source database was frozen only for local export. A/B/C and both miners
continued operating throughout the test. The exported registry and settlement
sets were empty, which is the expected canonical state below reward activation.

## Signature And Trust

The signer received its private Ed25519 key only through a mode-0600 protected
file. Process command line, environment, stdout, stderr, logs, snapshot
metadata, generated evidence, and the final artifact contained no private key.
The temporary private-key file was removed after signing.

The trusted snapshot had one valid and trusted signature. Isolated negative
tests produced these expected fail-closed results:

| Negative test | Result | Rejection |
|---|---|---|
| Modified artifact | `PASS` | Compressed payload checksum mismatch |
| Modified signature | `PASS` | Invalid signature for canonical payload |
| Unsigned snapshot in enforce mode | `PASS` | Signature required |
| Untrusted signer | `PASS` | No valid trusted signature |
| Wrong network | `PASS` | Configured network mismatch |
| Altered genesis/header | `PASS` | Header proof-of-work validation failed |

## Restore And Delta Sync

The `node-snapshot-restore` runtime contained zero files before import. It was
initialized only from the mainnet configuration/genesis and the trusted signed
snapshot; no database copy, prior full sync, or second snapshot was used.

Immediately after import and before P2P sync, height, tip, cumulative work,
supply, UTXO count/hash, selected balances, reward state, and SQLite checks
matched the frozen source at height 249.

The canonical network was at height 259 when P2P sync began:

| Metric | Value |
|---|---:|
| Delta start height | 249 |
| Initial canonical height | 259 |
| Blocks applied | 10 |
| First-handshake latency | 41 ms |
| Initial convergence latency | 41 ms |

## Final Convergence

At height 268, node-a, node-b, node-c, and the restored node had the same
deterministic fingerprint:

| Field | Value |
|---|---|
| Height | `268` |
| Tip | `00000002dd9838b7e92c9746ab0bdb194bda376ba3120f5149cf65255c712d39` |
| Cumulative work | `58945344306` |
| Materialized supply | `1345000000000` chipbits |
| UTXO count | `273` |
| UTXO hash | `28c50784c0a34f5a0bc3917e79be1ab36febc30354dd67ea8e0928d67c3e4d25` |
| Mempool size | `0` |
| Reward registry count | `0` |
| Reward settlement count | `0` |
| SQLite quick check | `ok` on all four nodes |
| SQLite foreign-key check | no rows on all four nodes |

Block 268 was produced after the restored node first converged and extended
the canonical chain normally. The restored node subsequently observed block
269 before cleanup; its persisted database remained valid after reopening.

## Cleanup Note

Stopping both auxiliary containers (`node-fullsync`, used as the frozen export
source, and the temporary restored node) exceeded the Compose stop timeout and
ended with status 137. The source database passed SQLite integrity and exact
canonical fingerprint checks before export. The restore-node timeout occurred
after all restore, delta, continuation, and convergence assertions had passed;
a read-only reopening of that same runtime showed height 269 with clean SQLite
quick and foreign-key checks. The temporary restore container was removed while
its runtime, snapshot, logs, and evidence were preserved. These are recorded as
auxiliary-node shutdown warnings, not snapshot correctness or consensus
failures.

A/B/C and both miners remained running on the shared topology. The ordinary
monitor remained active and the fault lifecycle remained at
`FINAL_CONVERGENCE` with no active fault lock.

## Evidence

Primary evidence is under:

`/tmp/chipcoin-mainnet-docker-rehearsal/snapshot/evidence-mainnet-signed-20261005/`

Negative artifacts and results are under:

`/tmp/chipcoin-mainnet-docker-rehearsal/snapshot/negative-tests/`

The signed artifact is:

`/tmp/chipcoin-mainnet-docker-rehearsal/snapshot/rehearsal.snapshot`

## RC Gates

Promoted to `PASS`:

- `SNAP-NEG-001`
- `SNAP-NEG-002`
- `SNAP-RUN-001`
- `SNAP-RUN-002`
- `SNAP-RUN-003`
- `SNAP-RUN-004`

`SNAP-RUN-004` is supported by exact equality with A/B/C, whose canonical
state was built from genesis rather than from a snapshot, including cumulative
work, full supply data, deterministic UTXO hash, selected balances, reward
registry/settlement state, mempool, and SQLite integrity.

`SNAP-OPS-001` remains `NOT_RUN`: the explicit failed-snapshot fallback to a
fresh full sync was not exercised by this test.

```text
SIGNED_SNAPSHOT = PASS
TRUSTED_SNAPSHOT_VERIFICATION = PASS
SNAPSHOT_RESTORE = PASS
DELTA_SYNC = PASS
SNAPSHOT_DELTA_CONVERGENCE = PASS
SNAPSHOT_RC_BLOCKER = NO
```
