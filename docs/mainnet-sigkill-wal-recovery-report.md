# MAINNET SIGKILL / WAL / RECOVERY REPORT

Date: 2026-10-05. MemPalace was consulted before execution. Runtime evidence is
preserved under `/tmp/chipcoin-mainnet-docker-rehearsal/sigkill-node-c-20261005`.

## Baseline And Crash

The target was `node-c`. Node-a, node-b and both miners remained running on the
shared network. The ordinary monitor was active, no fault lock or fault monitor
existed, and empty Scenario B fault networks were removed during precheck.

At height 224, A/B/C shared:

- tip `00000012b60ea4b496991604761a36d769c1ee015156c8b66d93581d31c2a440`;
- cumulative work `49303726650`;
- materialized supply `1125000000000` chipbits;
- 229 UTXOs, hash `eca71a371edbf7ace8a074c54969b4511daae339ce17bfbb07a1c40efd423804`;
- empty mempool and equal balance, registry and settlement hashes;
- SQLite `quick_check=[ok]` and empty `foreign_key_check`.

Node-c ran image
`sha256:720ea695c75fd9aee8637c2e5a1993c06858b55491c2a51d1a7d9093a168ee9d`.
SQLite journal mode was `wal`. Before the crash, the DB was 430080 bytes, WAL
4140632 bytes and SHM 32768 bytes.

The exact command was `docker kill --signal KILL
chipcoin-mainnet-rehearsal-node-c-1`. Kill request timestamp:
`2026-10-05T09:16:27.511783070Z`; Docker returned at
`2026-10-05T09:16:27.600211276Z`. Node-c exited 137, was not OOM-killed, and
remained down. DB/WAL/SHM metadata and SHA-256 values were unchanged from the
post-kill checkpoint through the pre-restart checkpoint; no repair, copy,
VACUUM, snapshot or resync was performed.

## Same-DB Recovery

A/B advanced from 224 through 227 while node-c was down, a real three-block
catch-up requirement. Node-c was restarted at
`2026-10-05T09:35:55.548112565Z` with `docker start`, preserving the same
container ID, image, bind sources, runtime and database.

- First successful handshake latency: 2808 ms.
- Full A/B/C convergence latency: 4212 ms.
- Recovery height: 227.
- Recovery tip: `0000000cb46c697d1d327bf69bbda0e5efe0c41b9dc468601b0c45cf90f34003`.
- Work: `49961109672`.
- Supply: `1140000000000` chipbits.
- UTXO count/hash: 232 / `d7bc03154c9ee251903cd0648ee6bbcea42f014dc84643d6199fc303443b523f`.

SQLite opened normally, WAL operation resumed, P2P established two handshakes,
and the node caught up without corruption, duplicate state or a DB replacement.
A/B/C fingerprints, mempools, balances, registry and settlement state matched.
Wallet checksums before and after were identical.

## Post-Recovery Continuation

With node-c online, canonical block 228 was received and applied without reorg:

- block `0000000a065c7d702e51e6446e0f778b01581378f5c7622cc64ba82dcf88dab9`;
- previous `0000000cb46c697d1d327bf69bbda0e5efe0c41b9dc468601b0c45cf90f34003`;
- cumulative work `50180237346`;
- coinbase `5da2a7581ca99b1f13fd14572e6bd600147f75cda2d763001e3d84ea71ad4263`;
- 5000000000 chipbits paid to miner-b.

Final A/B/C state was identical: supply `1145000000000` chipbits, 233 UTXOs,
UTXO hash `ac48e0cdd1abca158c593aa355e413834c2de1a6776f56807d00484290c2fcf3`,
empty mempool, equal balance/reward state, SQLite quick check `ok`, and empty
foreign-key check.

## Runner False Failure

The autonomous runner emitted `FAIL_PRESERVE_EVIDENCE line=102` only after all
runtime assertions and final evidence had completed. Its final check compared
Docker's `Mounts` arrays with order-sensitive JSON equality. Docker returned
the same two mounts in reverse order after restart. Container ID, image, mount
sources, destinations, read/write flags and modes all matched.

This is an operational assertion defect in the one-shot runner, not a storage,
node, consensus or recovery failure. No rerun is required. The transient failed
unit can be reset after evidence preservation; the rehearsal itself remained
healthy throughout final inspection.

## RC Gate Decision

- `FAULT-RUN-013`: `NOT_RUN -> PASS`.
- `FAULT-RUN-014`: `NOT_RUN -> PASS`.
- RC counts: 71 PASS / 19 NOT_RUN / 8 PENDING_HEIGHT / 0 FAIL / 98 total.

SIGKILL_RECOVERY = PASS

SQLITE_WAL_INTEGRITY = PASS

POST_CRASH_CONVERGENCE = PASS

STORAGE_RECOVERY_BLOCKER = NO
