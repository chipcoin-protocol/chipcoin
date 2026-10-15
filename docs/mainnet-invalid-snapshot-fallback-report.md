# Mainnet Invalid Snapshot Fallback Report

Date: 2026-10-06

## Result

The production Docker bootstrap path rejected a tampered mainnet snapshot,
adopted no snapshot chain state, selected full-sync fallback in the same
bootstrap invocation, and synchronized an empty node from genesis over P2P.
The fallback node matched node-a, node-b, and node-c deterministically and
then accepted the next canonical block.

| Check | Result |
|---|---|
| Invalid snapshot rejection | `PASS` |
| Rejection atomicity | `PASS` |
| Automatic full-sync fallback | `PASS` |
| P2P full sync from genesis | `PASS` |
| A/B/C/fallback convergence | `PASS` |
| SQLite integrity | `PASS` |
| Post-convergence chain continuation | `PASS` |

MemPalace was consulted before execution. Its recorded design decision matches
the implementation: `auto` mode falls back to `full` after any snapshot
bootstrap failure, while explicit `snapshot` mode fails closed.

## Production Path

`scripts/setup/wizard.py::_prepare_node_bootstrap` and
`docker/entrypoint.sh::prepare_snapshot_bootstrap_if_needed` define the
supported fallback behavior. In `auto` mode, a failed import removes the
candidate SQLite database and its WAL/SHM files before normal node startup
continues with `bootstrap_mode=full`. The production runtime then performs its
ordinary P2P sync. No alternate snapshot, database copy, fixture chain, UTXO
import, or manual chain-state operation was used.

## Isolated Environment

The temporary container `chipcoin-mainnet-snap-ops-001` used the same validated
mainnet node image as the rehearsal. It started with an empty dedicated runtime,
mainnet genesis/configuration, trust enforcement, and the production entrypoint.
It was initially attached only to an internal temporary Docker network so that
the post-rejection state could be inspected before any P2P block arrived. It was
then attached to the rehearsal shared network with node-a, node-b, and node-c
as canonical P2P sources. The temporary node had no miner and exposed no public
port.

The rehearsal baseline was converged at height 328:

| Field | Value |
|---|---|
| Tip | `00000007e23902a0e04c405b878de9bccb04ba86d75d284119d055d23ba836bd` |
| Cumulative work | `72093004746` |
| Materialized supply | `1645000000000` chipbits |
| UTXO count | `333` |
| UTXO hash | `016d556023ed23ffeb2046d69a5780ff8adf87d1174cd0c491ddd963c7cdd5a0` |
| Reward registry count | `2` |
| Registry hash | `250181d631f01060457af722e0d794c0c5af7d173233338c522b849342526fbb` |

## Invalid Artifact And Rejection

The test reused the existing modified-artifact negative case from the accepted
snapshot trust test:

| Field | Value |
|---|---|
| Artifact | `modified-artifact.snapshot` |
| SHA-256 | `4e72427928a0da8ae82ee69fad62defb24c1f8b45dbbd1a042329c37174059df` |
| Declared height | `249` |
| Declared block | `0000000c241482e41fdbb85ecb21334c887cf4225bc9f071fc2b043d1d81c2b4` |
| Expected rejection | Compressed payload checksum mismatch |
| Actual rejection | `snapshot compressed payload checksum mismatch` |

The entrypoint logged the failed import and `Falling back to full sync`, then
started the node with `bootstrap_mode=full`, no snapshot anchor, and no accepted
snapshot signer.

## Rejection Atomicity

Before P2P was enabled, the running node reported:

- height, tip, and cumulative work: `null`;
- materialized, minted, and circulating supply: `0`;
- snapshot anchor height/hash: `null`;
- `snapshot_signature_verified=false`;
- no accepted snapshot signer;
- empty mempool and no UTXO-derived supply;
- SQLite `quick_check=ok` and an empty foreign-key result.

The runtime contained only the rejected artifact/cache metadata, legitimate
empty full-sync SQLite/WAL/SHM files, and retry diagnostics. There was no restore
marker or authoritative state derived from the invalid snapshot.

## Full Sync And Convergence

After the shared network attachment, the unchanged process established three
handshakes and synchronized through the normal P2P path:

| Metric | Value |
|---|---:|
| First observed fallback height | `6` |
| Source height | `328` |
| First-handshake latency | `3 ms` |
| Full convergence latency | `29041 ms` |
| Converged height | `328` |

Progress evidence records intermediate heights 6, 47, 95, 263, and 302 before
height 328. At convergence, A/B/C and the fallback node had the same height,
tip, cumulative work, complete supply snapshot, UTXO count/hash, reward
registry/settlement state, balances hash, and mempool state. All four SQLite
checks returned `ok` with no foreign-key rows.

## Chain Continuation

The fallback node remained online until canonical block 329 arrived:

| Field | Value |
|---|---|
| Height | `329` |
| Block hash | `0000000eed6f989e8ba9a8c5e82c9800b1792ba69c417016cf74e1f52017fd4e` |
| Previous block hash | `00000007e23902a0e04c405b878de9bccb04ba86d75d284119d055d23ba836bd` |
| Cumulative work | `72312132420` |
| Coinbase TXID | `c161a14de00c465664804d5b6495d5fe8ee4966f72d00690bf70142463158a27` |
| Miner payout | `5000000000` chipbits |

The previous hash exactly matches the converged height-328 tip. A/B/C and the
fallback node again had the same canonical fingerprint at height 329:

| Field | Value |
|---|---|
| Materialized supply | `1650000000000` chipbits |
| UTXO count | `334` |
| UTXO hash | `57dff82ce1a6e768df8a3c9f279319c909dbf0b108537fc7e49cc909ff131073` |
| Reward registry count | `2` |
| Reward settlement count | `0` |
| Mempool size | `0` |

## Shutdown And Rehearsal Safety

The orderly `docker stop --time 60` command returned success after 60167 ms,
but the auxiliary container exit status was 137 (`OOMKilled=false`). This is a
temporary-node shutdown timeout, recorded separately from bootstrap correctness.
The stopped runtime returned SQLite `quick_check=ok` and no foreign-key rows;
DB, WAL, SHM, logs, checksums, and inspect output were preserved before the
temporary container and network were removed.

The rehearsal itself was never stopped, restarted, or written by the test.
After cleanup, A/B/C were converged at height 351 with tip
`0000000a8ed6dd8595e2e8185e2e868372150d8ebb423ba4b092e9ebfdbdca42`,
work `77132941248`, supply `1760000000000` chipbits, UTXO count 356, UTXO
hash `d71187a735cc764dc311a1d50b69af6be6efb034f27fecc12d26a5a48d454abb`,
registry count 2, no settlement, and clean SQLite checks. Both miners remained
running and the ordinary monitor was active.

## Evidence

Primary evidence is preserved under:

`/tmp/chipcoin-mainnet-snap-ops-001-20261006T073203Z/evidence/`

The dedicated stopped runtime, including DB/WAL/SHM evidence, is preserved
under:

`/tmp/chipcoin-mainnet-snap-ops-001-20261006T073203Z/runtime/`

## RC Gate

`SNAP-OPS-001` is promoted from `NOT_RUN` to `PASS`. No other gate is changed.

```text
INVALID_SNAPSHOT_REJECTED = PASS
PARTIAL_SNAPSHOT_STATE_ADOPTED = NO
FULL_SYNC_FALLBACK_TRIGGERED = PASS
P2P_FULL_SYNC = PASS
FINAL_CONVERGENCE = PASS
SQLITE_INTEGRITY = PASS
CHAIN_CONTINUATION = PASS
SNAP_OPS_001 = PASS
SNAPSHOT_RC_BLOCKER = NO
```
