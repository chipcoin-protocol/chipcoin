# Node resilience RC1 — private testing plan

Source base: public `main` at `54d2987f00052a8f2c006512279ab286766d1b11`.
This candidate changes peerbook, header storage reads, P2P error isolation, and
sync-loop recovery. It does not change consensus, wire formats for valid messages,
chainwork, database schema, or mining submission rules. It is **not deployed**.

## Evidence and limits

The two operator logs cover 2026-11-24 20:55 through 2026-11-25 06:00 UTC.
The French-node excerpt starts mid-traceback, so it does not show when the bad
peer record was created. It contains 524 peer-sort `TypeError` lines, 485
endpoint-probe scheduling failures, 37 inbound callback failures, and 325 HTTP
500 responses. The Canadian-node log contains one fatal sync-scheduler task
failure at 23:37:28 UTC when `raw_header` was `None`. Its validated chain later
stopped at height 14499; an isolated header for 14500 arrived at 01:18:40; a
restart at 05:37 recovered through 14509. The logs support scheduler death as
the cause of the stall, but do not prove how the NULL header was originally
written. No original operator logs or endpoints are in this repository.
The last observed peer-sort error in the French-node excerpt is at 05:39:41.
The Canadian node applied block 14510 at 05:50:22 after the restart.
Between receipt of header 14500 and the restart, the Canadian node logged 317
issued templates at height 14500. This demonstrates why pool clients must
inspect sync state and parent tip; it does not prove when the node first learned
of every later remote block.

The install path contains `12e4dbc8974bd768`, and the affected Core files in
that published commit are byte-identical to the public base used here. A path
name alone is not a build attestation. An operator-provided package hash or
installed-file hashes would be needed to prove exact binary provenance.

## Root cause and correction

| Area | Confirmed mechanism | Correction | Residual uncertainty |
| --- | --- | --- | --- |
| Peerbook | `PeerManager.list_all()` sorted unvalidated `PeerInfo` fields. The network filter excludes `network=None` on a Mainnet call; the observed sort failure therefore requires another malformed sortable field, most plausibly host or port. | Validate new endpoint identities before storage; quarantine malformed legacy records in memory without deleting them; preserve their host bans; lock in-memory reads/writes and log only changes in malformed-record count. | The logs do not identify the exact malformed row or its insertion path. |
| Headers | A stored `raw_header=None` reached `deserialize_block_header()` from `find_best_tip()`. The current create-table statement has `NOT NULL`, but an older existing table is not rebuilt by `CREATE TABLE IF NOT EXISTS`. | Treat NULL as incomplete and other invalid payloads as corrupt; exclude both from best-tip and header advertisement; keep sync in a non-synced phase. Scan ordered candidates until a valid header is found, without the earlier 32-row cap. A broken active-chain locator requests headers from genesis so normal validated P2P ingest can replace the bad row. No database deletion or synthetic header is used. | A legacy schema, prior migration, or external writer could explain the NULL; the logs alone cannot distinguish these. |
| Scheduler | `_update_sync_status()` ran outside the scheduler's exception boundary, ending the task permanently after that NULL. | Keep status update within the per-iteration boundary, publish a non-synced phase after a failure, catch failures inside the fallback publication path, retry on the existing interval, and aggregate traceback logging to once per minute while failing. | Persistent storage corruption still needs operator diagnosis; retries alone cannot repair arbitrary database damage. |
| P2P sessions | A callback failure could leave the handshake session open. Malformed UTF-8 in `version` raised `UnicodeDecodeError`, outside the protocol error class. | Close only the affected session on callback/reader failures; convert invalid UTF-8 to `CodecError`. | No distinct `version` parsing failure was demonstrated in the supplied logs. |
| Block downloads | Timeout, release, and peer reassignment already exist in the scheduler and sync manager. | No rewrite. Scheduler continuity restores those mechanisms after a recoverable error. | Independent testing on the operator's two nodes remains pending. |

The `get-block-template` API is explicitly coded to build templates without a
sync prerequisite. This RC does not alter that public contract. Pools should
check `/v1/status` and the tip before using a template; any proposal to reject
templates from a degraded node requires a separate API compatibility decision.

## Isolated verification

Regression fixtures are synthetic. They cover malformed peers, unknown network
separation, retained host bans, concurrent enumeration, legacy nullable tables,
NULL/invalid headers, P2P header repair, scheduler retry, callback closure,
malformed `version`, and three local nodes converging on ten blocks without a
restart. The three-node test uses a private easy-target Mainnet *profile*, not
the public Mainnet. It checks height, hash, and cumulative work.

Run from a clean checkout of this candidate:

```bash
pytest -q tests/node tests/storage tests/consensus tests/miner tests/rewards tests/integration
```

The test command is local and uses disposable databases. It does not connect to
or write to public Mainnet. The extended Python 3.12 suite completed with
**748 PASS** on the original candidate and **752 PASS** after the final
release-gate corrections. Under Python 3.14.6,
the focused non-socket tests completed with **53 PASS, 28 SKIP** because local
TCP bind was restricted in the sandbox. Those 28 integration tests were
rerun outside that restriction and completed with **28 PASS**. Thus Python
3.14 has focused coverage, not a full-suite certification. The private
three-node recovery test passed in that integration set. A mixed-version
three-node loopback test also passed with the official v0.1.2 source as one
node and this RC as two nodes. It checked handshakes, ten-block catch-up,
matching hash/work, and P2P repair of a legacy NULL header. This does not
substitute for testing on the operator's hosts.
See `tests/integration/resilience/README.md` for the reproducible local command.
The final header-storage, scheduler-fallback and malformed-`version` focused
tests completed with **10 PASS** under Python 3.14.6.

Before the correction, synthetic tests reproduced the peer-sort `TypeError`,
the NULL-header deserialization failure, a raw UTF-8 decode error in `version`,
and a stranded handshake callback. After the correction, the same focused
tests pass. No source change was made to consensus, transaction validation,
mining submission, or the database schema. The only overlap with the earlier
pool-submission work is the `service.py` file; the changed functions here are
peer admission/observation, not block submission. The Docker-first wizard
files are untouched.

The Core process cannot attest the operator's exact installed bytes from a
path prefix alone. The old package should remain available for rollback.

## External operator test plan

1. Keep the current package and a coherent SQLite backup. Record the exact
   installed-file hashes, Python version, chain ID, genesis, height, tip hash,
   cumulative work, and peer count before changing either node.
2. Install this candidate on one **separate or scheduled test** node, never
   against a database simultaneously open by the old process. Do not reset the
   peerbook or resync the chain.
3. Observe `/v1/status`, `/v1/peers`, and `/v1/peers/summary`; verify no repeated
   500 responses, no lost sync-scheduler task, and no cross-network peers.
4. Verify a valid mining template only when the node is fully synchronized;
   compare its parent hash with the current network tip. Do not submit synthetic
   blocks to public Mainnet.
5. During a controlled private-network test, inject a nullable legacy header
   row and a malformed peer; verify header re-download, block catch-up, no
   restart, bounded traceback logging, and no lost ban state.
6. Observe each candidate node for **24–48 hours**, recording height/tip/work,
   status phase, missing blocks, in-flight requests, HTTP 500s, task failures,
   and peer counts. Compare with an independent healthy node.

Stop the trial if the node diverges in consensus, fails to catch up, reports
`synced` with known missing blocks, issues repeated 500s, or affects another
service. Roll back by stopping the candidate process, restoring the previous
package/configuration, and starting one process on the unchanged database.
No schema migration is introduced by this candidate. Restore the database
backup only if integrity checks show it is necessary; never run both versions
against the same SQLite file concurrently.
