# Public Mainnet RC1 Gate Execution Plan

Status: prepared, not authorized for public deployment. The authoritative
matrix is `public-mainnet-rc-revalidation.json`; all 98 requirements remain
`NOT_RUN` until a frozen genesis and source identity exist. Historical and
TEST-ONLY results are references only.

## Preconditions

1. Approve one UTC timestamp and reproduce the canonical genesis independently.
2. Embed the reviewed block bytes/hash and pin the same identity in every client.
3. Freeze a clean source commit and signed-tag policy; build only from locked
   inputs and record immutable image and browser artifact digests.
4. Create a fresh isolated mainnet runtime. Never mount TEST-ONLY, testnet, or
   historical rehearsal databases, wallets, peerbooks, snapshots, or volumes.
5. Generate operational keys under the approved custody procedure; do not put
   them in Git, images, command lines, logs, or shared evidence.

## Gate record and promotion control

The source gate file provides each requirement's ID, description, category,
dependencies, blocking class, status and evidence-catalog references. The
derived matrix adds the required network/chain/genesis identity and prevents
inheritance of historical PASS. A static audit found all 98 RC requirements
have descriptions, dependency lists and nonempty evidence references. This is
adequate to inventory the gates, but it does not constitute an executable
per-gate runner: the matrix builder only resets statuses, and the phase table
below groups commands rather than evaluating every gate automatically.

For each future execution, preserve an immutable evidence record containing
at least: gate ID, exact source commit and tree identity, approved genesis
hash, command and environment, UTC start/end, exit status, observed result,
artifact/evidence paths and SHA-256 digests, dependency gate IDs, and reviewer.
Set `PASS` only when the gate's full description is demonstrated by its
referenced evidence on that exact identity. Use `FAIL` for a demonstrated
incorrect result, `BLOCKED` for an external prerequisite, and leave `NOT_RUN`
or `PENDING_HEIGHT` otherwise. Do not infer a gate status from a shared test
suite, a build, historical-chain evidence, or a different gate's evidence.
No per-gate statuses have been promoted by the pre-freeze checks in this
document.

The seven public-launch requirements are specified in
`docs/mainnet-public-launch-gate-preflight.md`; they are intentionally outside
the 98-entry RC matrix. Their runtime/deployment evidence requires separate
public-gate execution and authorization.

## Ordered execution

The operator records every command, exit status, artifact digest, timestamp,
and evidence path. A failed blocking gate stops its dependent phase.

| Phase | Gates | Canonical command/path | Promotion condition |
| --- | --- | --- | --- |
| 0. Matrix | all | `.venv/bin/python scripts/build-public-mainnet-rc-revalidation-matrix.py --source mainnet-release-gate.json --output public-mainnet-rc-revalidation.json` | Exactly 98 `NOT_RUN`; frozen chain ID/hash inserted only after approval. |
| 1. Genesis/config | `CONS-CFG-*`, `PQ-CFG-*`, `REWARD-CFG-001`, `SNAP-CFG-*`, `SEC-CONF-001` | `pytest -q tests/consensus/test_mainnet_profile.py tests/consensus/test_network_identity.py tests/consensus/test_public_mainnet_genesis.py tests/node/test_public_mainnet_genesis_storage.py tests/config/test_network_config.py` | Source constants, serialized genesis, startup, DB, P2P and snapshot identity agree. |
| 2. Consensus/security | source and negative gates | `pytest -q tests/consensus tests/wallet tests/node/test_transport_protocol.py tests/node/test_snapshots.py` followed by dependency and secret scans from the release runbook | No consensus/security failure; exceptions explicitly reviewed. |
| 3. Locked builds | `BW-BUILD-*`, `BW-NET-*`, `BW-SEC-*`, `SEC-REL-*`, `SEC-DEP-*`, `SEC-SECRET-*` | `npm ci && npm test` in `apps/browser-wallet`, then `apps/browser-wallet/build-all.sh`; canonical Docker build followed by image-label/digest and secret-layer checks | Named artifacts come from frozen commit/locks and carry the canonical identity. |
| 4. Height 0/1 | genesis and early runtime gates | Start the future canonical-chain rehearsal from an empty runtime using the reviewed production Compose profile; use its approved bounded orchestrator | A/B/C install identical genesis; supply/UTXO zero at h0; h1 coinbase/PQ/funded-v2 boundaries PASS. |
| 5. Transaction/maturity | `PQ-RUN-*`, `PQ-NEG-*`, `PQ-OPS-*`, `TX-RUN-*`, `CONS-RUN-003..005` | Production wallet/CLI, mempool and exact-height mining paths; negative artifacts only in isolated runtimes | h99/h100 candidate boundary, mature spends, multi-input PQ, fees and A/B/C state proven. |
| 6. Fault/sync | `CONS-RUN-002,006,007`, `FAULT-*` | Reviewed fault orchestrator: restart, empty-DB full sync, partition, competing work, reconnect, SIGKILL/WAL | Natural cumulative-work reorg and complete state convergence; SQLite checks PASS. |
| 7. Snapshot | `SNAP-NEG-*`, `SNAP-RUN-*`, `SNAP-OPS-001` | Snapshot CLI with offline test signer and enforce-mode trust anchor; isolated restore/full-sync fallback | Signed restore/delta equals full sync; invalid snapshot leaves no authoritative state. |
| 8. Rewards | `REWARD-RUN-001..007` | Exact-height canonical rehearsal through activation, renewals, attestations, settlements and maturity | Funded registrations/renewals, quorum, payout, restart and reward-state reorg PASS. |
| 9. Clients | `PQ-BW-*`, `BW-OPS-*`, `EXP-INT-*`, `TX-EXP-001` | Clean Chromium/Firefox profiles with named artifacts; private Chipcoin Central production build | Browser and Explorer reject missing/wrong identity and display canonical data. |
| 10. Final | `FINAL-RUN-001`, `RUNBOOK-*`, remaining `SEC-*` | Compare normal, reorg, restart, full-sync and snapshot nodes at one deterministic checkpoint | All five paths and DB fingerprints converge; all 98 matrix entries PASS. |

Commands in phases 4-10 intentionally name the production paths rather than
reusing `public-mainnet-test-only-rehearsal.sh`: the latter is identity-locked
to TEST-ONLY and must never be pointed at public mainnet. The canonical-chain
orchestrator/config can be finalized only after the genesis hash is approved.

## Seven public gates

These are subsequent deployment gates, not part of the 98-gate RC promotion.

| Gate | Required evidence / PASS condition | Operational owner | Authorization |
| --- | --- | --- | --- |
| `PUB-001` | Independent bootstrap/seed reachability, correct chain/genesis, DNS and P2P-only exposure, strict testnet separation | Infrastructure lead | Host provisioning, P2P exposure and DNS approval |
| `PUB-002` | TLS, default-deny firewall, private raw API, allowlisted proxy routes/CORS, rate/body limits and external port scan | Security + infrastructure | Certificates, firewall and public API routing |
| `EXP-PUB-001` | Public static Explorer reports canonical identity/data, fails closed, and has independent availability/identity probes | Explorer owner + SRE | Deployment, hostname, TLS and monitoring |
| `PUB-003` | Health/sync/work/supply/disk/reward alerts, tested delivery, encrypted secret-free backups, isolated restore drill | SRE / backup custodian | Alert recipients, credentials, retention and storage |
| `PUB-004` | Offline-signed canonical snapshot, approved trust anchor, immutable checksums/URLs, redundant download and clean restore+delta proof | Snapshot key custodians + release security | Signing ceremony, key publication and upload |
| `PUB-005` | Published endpoint/port/download documentation exactly matches production; clean install works; explicit no-mainnet-faucet statement | Release/docs owner + founder | Publication and announcement |
| `PUB-006` | Timed launch/rollback/emergency rehearsal with named owners and preserved chain state; final signed go/no-go record | Founder, release manager, incident commander | Production rehearsal, then separate launch approval |

The detailed normative criteria remain in
`docs/mainnet-public-launch-gate-preflight.md`. Public order is `PUB-001`,
`PUB-002`, `EXP-PUB-001`, `PUB-003`, `PUB-004`, `PUB-005`, `PUB-006`.
