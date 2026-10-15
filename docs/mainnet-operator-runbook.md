# Mainnet Operator Runbook

Status: `DOCUMENTED`, pending runtime validation where identified.

This runbook covers the operational procedures required by `RUNBOOK-001`
through `RUNBOOK-005` in the mainnet release-candidate gate. It does not
authorize public deployment. Replace every value written as `<...>` with a
value from the signed RC release manifest or the site's approved secret store.

Never copy values from the rehearsal `.env.mainnet`: it contains rehearsal
paths and local-only settings. Never place a private key, seed, wallet JSON, or
credential in a command transcript, ticket, report, shell history, or general
runtime backup.

## Operating Principles

1. Fail closed on any network, genesis, release, image, configuration, or
   wallet-scheme mismatch.
2. Stop mining before investigating a possible consensus incident.
3. Preserve database, logs, configuration hashes, and fingerprints before
   changing or deleting state.
4. Never repair consensus state by editing SQLite, selecting a tip manually,
   deleting UTXOs, or copying a live peer's database.
5. Full sync from genesis is the default trust-minimized recovery path.
6. Mainnet snapshot bootstrap requires an authorized signature and trust mode
   `enforce`; an unsigned or untrusted snapshot is never accepted as fallback.
7. Reward owner and reward attestation wallets are separate files and keys.
8. The node database/runtime directory must not contain wallets or keys.
9. There is no mainnet faucet.

## Release Manifest

Before an RC is used operationally, publish an immutable, reviewed manifest
alongside the source tag. It must contain at least:

```json
{
  "version": "<semver>",
  "git_tag": "<signed-tag>",
  "git_commit": "<40-hex-commit>",
  "image": "<registry/repository>@sha256:<digest>",
  "supported_hosts": ["<os/architecture>"],
  "docker_engine": "<validated-version-range>",
  "docker_compose": "<validated-version-range>",
  "network": "mainnet",
  "chain_id": "<mainnet-chain-id>",
  "genesis_hash": "<canonical-genesis-hash>",
  "configuration_sha256": "<sha256-of-reviewed-env-with-secret-values-redacted>",
  "consensus": {
    "target_block_time_seconds": 600,
    "retarget_window_blocks": 1000,
    "initial_compact_target": "0x1d1399ad",
    "coinbase_maturity": 100,
    "halving_interval": 111000,
    "max_supply_chc": 11000000,
    "initial_miner_reward_chc": 50,
    "reward_epoch_blocks": 100,
    "reward_pool_chc": 50,
    "reward_activation_height": 1000,
    "reward_warmup_epochs": 2,
    "max_rewarded_nodes": 25,
    "pq_scheme": "mldsa44",
    "pq_scheme_id": 10,
    "pq_activation_height": 0,
    "reward_seed_version": 2,
    "special_signature_version": 2
  }
}
```

The manifest must not contain secret values. Record the hash of a normalized,
reviewed configuration where secrets are replaced by stable labels, not by
their hashes if those hashes would assist guessing low-entropy credentials.

## Support Matrix And Host Prerequisites

Only hosts listed in the RC manifest are supported. At minimum verify:

- dedicated Linux host or VM on a validated architecture;
- Docker Engine and Docker Compose v2 within the validated release range;
- UTC/NTP synchronization and correct host timezone reporting;
- enough persistent disk for database growth, snapshots, logs, and one full
  offline backup, with alerting well before disk-full;
- reliable memory and CPU consistent with soak-test measurements;
- separate persistent filesystems or backup policies for runtime, logs, and
  encrypted secret material;
- firewall default deny; P2P may be published only when approved, while the
  raw HTTP API remains bound to localhost or a controlled reverse proxy;
- operator access using named accounts, MFA where available, and auditable
  privilege escalation;
- no Docker daemon, source tree, environment file, or secret directory writable
  by untrusted users;
- system backup and cleanup jobs reviewed so they cannot remove active runtime.

Record versions without starting services:

```bash
uname -a
docker version
docker compose version
df -hT <runtime-parent> <log-parent> <backup-parent>
timedatectl status
```

Status: `DOCUMENTED`. Validate the final support matrix on RC images before
public launch.

## Directory And Permission Layout

Recommended logical separation:

```text
/opt/chipcoin/                         immutable checked-out RC source
/etc/chipcoin/mainnet.env              configuration, no private keys
/var/lib/chipcoin/mainnet/             read-write DB/runtime only
/var/log/chipcoin/mainnet/             logs/evidence
/var/lib/chipcoin-secrets/mainnet/     wallet files, not below runtime
/var/backups/chipcoin/mainnet/         ordinary encrypted operational backups
/var/backups/chipcoin-secrets/         separately controlled encrypted key backups
```

Requirements:

- runtime and log directories: owned by the service operator, not world writable;
- environment file: mode `0600` if it contains credentials, otherwise no broader
  than `0640` with a dedicated operator group;
- wallet files: mode `0600`, parent mode `0700`, mounted individually read-only;
- snapshot trusted public-key file: immutable/read-only to the service;
- snapshot signing private key: never stored on the node host;
- database parent directory: writable by the node because SQLite may create
  `-wal` and `-shm` files;
- no wallet directory mounted read-write into node or miner containers.

Verify paths without printing content:

```bash
namei -l /var/lib/chipcoin/mainnet
namei -l /var/lib/chipcoin-secrets/mainnet/miner-wallet.json
stat -c '%a %U:%G %n' /etc/chipcoin/mainnet.env \
  /var/lib/chipcoin-secrets/mainnet/*.json
```

## Release Verification Before Every Start

Run from the immutable source checkout:

```bash
set -euo pipefail
test "$(git rev-parse HEAD)" = '<expected-commit>'
test "$(git describe --tags --exact-match)" = '<expected-tag>'
git diff --quiet
git diff --cached --quiet
docker image inspect '<image>@sha256:<digest>' \
  --format '{{index .RepoDigests 0}}'
sha256sum /etc/chipcoin/mainnet.env
docker compose --env-file /etc/chipcoin/mainnet.env \
  -f docker-compose.yml config --format json > /tmp/chipcoin-mainnet-resolved-config.json
```

Review the resolved configuration, then remove the temporary copy. It must show:

- `CHIPCOIN_NETWORK=mainnet` and the expected chain ID;
- P2P port `8333` unless the signed release manifest explicitly says otherwise;
- HTTP API port `8080` bound only to the approved local/control interface;
- a unique mainnet database path, never a testnet path;
- `NODE_BOOTSTRAP_MODE=full` for the first node or a deliberately approved mode;
- no testnet bootstrap, seed, API, Explorer, snapshot, or DNS endpoint;
- snapshot trust mode `enforce` whenever snapshots are enabled;
- separate miner, reward owner, and reward attestation wallet source files;
- all wallet mounts read-only;
- reward owner and attestation target paths exactly
  `/runtime/reward-owner-wallet.json` and
  `/runtime/reward-attest-wallet.json` when automation is enabled.

Run the mandatory preflight:

```bash
scripts/mainnet-pq-preflight.sh \
  --compose-file docker-compose.yml \
  --env-file /etc/chipcoin/mainnet.env
```

Abort on any nonzero exit or any missing PASS. Record command exit status and
non-secret output in the release evidence directory.

For each wallet, use `wallet-address` and record only public metadata:

```bash
docker compose --env-file /etc/chipcoin/mainnet.env -f docker-compose.yml \
  run --rm --no-deps --entrypoint chipcoin miner \
  --network mainnet wallet-address --wallet-file /runtime/miner-wallet.json \
  | jq '{address,address_kind,scheme_id,scheme_name}'
```

Expected: `address_kind=pq`, `scheme_id=10`, `scheme_name=mldsa44`, and an
address beginning `CHCQ`. Apply the equivalent check to owner and attestation
mounts. Never use a command that prints private-key fields in an evidence log.

## First Node Startup

### Preparation

1. Complete host and release verification above.
2. Create an empty, dedicated runtime directory. Do not copy a rehearsal or
   testnet database.
3. Select full sync. For the first node, public bootstrap dependencies must be
   empty unless a separately approved private peer exists.
4. Confirm the configured genesis hash and consensus values against the signed
   RC manifest using the preflight/configuration report.
5. Confirm API publication is localhost-only. Do not expose the API merely to
   simplify initial diagnostics.
6. Keep the miner stopped until the node has initialized successfully and its
   network/genesis identity is verified.

### Start Node Only

```bash
docker compose --env-file /etc/chipcoin/mainnet.env \
  -f docker-compose.yml up -d --no-deps node
docker compose --env-file /etc/chipcoin/mainnet.env \
  -f docker-compose.yml ps node
docker compose --env-file /etc/chipcoin/mainnet.env \
  -f docker-compose.yml logs --no-color --tail=200 node \
  > /var/log/chipcoin/mainnet/first-start-node.log
```

### Verify Before Mining

```bash
curl --fail --silent --show-error http://127.0.0.1:8080/v1/status \
  | tee /var/log/chipcoin/mainnet/first-status.json \
  | jq '{network,height,tip_hash,cumulative_work,sync_phase,handshaken_peer_count}'
```

Required:

- API says `network=mainnet`;
- genesis/tip at initial height equals the manifest;
- cumulative work matches the canonical genesis state;
- no testnet chain, peer, snapshot anchor, or endpoint appears;
- health is stable and logs contain no fatal, consensus, database, wallet, or
  repeated restart error;
- peer count is explainable by the approved topology.

Only after independent verification may the miner be started:

```bash
docker compose --env-file /etc/chipcoin/mainnet.env \
  -f docker-compose.yml up -d --no-deps miner
```

### Abort Criteria

Stop miner first, then node, and preserve evidence if any occurs:

- release/tag/image/configuration mismatch;
- API reports a network other than mainnet or omits network identity;
- genesis hash or consensus parameter mismatch;
- wallet not CHCQ/ML-DSA-44 scheme 10 or a wallet mount is writable;
- testnet endpoint or database dependency;
- unexpected pre-existing height in a supposedly empty runtime;
- database integrity error, crash loop, disk-full, or unexplained tip/work mismatch;
- raw API unintentionally reachable from an unapproved interface.

Status: `DOCUMENTED`; first public node startup remains runtime validated only
when its separate launch checklist is executed.

## Joining Node

1. Verify release, image, configuration, network, genesis, wallet policy, and
   ports exactly as for the first node.
2. Start from an empty mainnet DB. Never copy another live node's DB.
3. Prefer full sync from genesis. Configure only approved mainnet peers.
4. Fail closed if a peer advertises a different network, genesis, chain ID, or
   incompatible protocol profile. Remove the peer from configuration and
   investigate; do not weaken validation.
5. Keep mining and reward automation disabled until convergence is confirmed.

Monitor:

```bash
watch -n 30 'curl -fsS http://127.0.0.1:8080/v1/status | jq \
  "{network,height,tip_hash,cumulative_work,sync_phase,handshaken_peer_count}"'
docker compose --env-file /etc/chipcoin/mainnet.env \
  -f docker-compose.yml logs --no-color --since=30m node \
  > /var/log/chipcoin/mainnet/join-sync.log
```

At completion compare against at least two independent healthy nodes:

- network and genesis;
- height, tip hash, cumulative work;
- total supply;
- deterministic UTXO hash/count;
- selected balances;
- reward registry, settlement, and payout state.

### Snapshot Option

Use only after the RC snapshot gates pass. Requirements:

- manifest network/genesis/height/tip/work match mainnet expectations;
- downloaded checksum matches the manifest;
- signer is in the pinned trusted public-key file;
- trust mode is `enforce`;
- destination DB is empty;
- wallet/secret scan of the artifact has passed;
- after import, delta sync converges to the same fingerprint as a full-sync node.

Any missing/invalid/untrusted signature, wrong network/genesis, checksum mismatch,
or import error aborts snapshot mode. Use a new empty DB for a subsequent full
sync; do not reuse a partially imported DB unless the implementation explicitly
and atomically guarantees rollback and that behavior has been runtime validated.

Status: `DOCUMENTED`; full-sync behavior has separate runtime evidence, while
the real mainnet snapshot path remains runtime pending.

## Backup Policy

### Backup Classes

| Class | Ordinary backup | Handling |
|---|---|---|
| Blockchain/runtime DB and snapshot metadata | Yes | Encrypted at rest; no wallet files. |
| Reviewed configuration | Yes | Redact credentials; retain normalized hash and sealed original separately. |
| Logs/evidence | Yes | Redact secrets; immutable retention for incidents/releases. |
| Miner wallet | No | Separate encrypted key backup under key-management policy. |
| Reward owner wallet | No | Separate encrypted key backup; distinct custody. |
| Reward attestation wallet | No | Separate encrypted key backup; distinct custody. |
| Snapshot signing private key | Never | Offline signing custody only. |
| Infrastructure credentials | No | Managed by the infrastructure secret store. |

Public snapshots must contain consensus state only. They must never contain
wallet files, seeds, private keys, environment files, logs, shell histories,
cloud credentials, SSH material, or backup archives.

### Safe Offline Database Backup

Prefer a controlled stop for a release or incident backup:

```bash
docker compose --env-file /etc/chipcoin/mainnet.env \
  -f docker-compose.yml stop miner
docker compose --env-file /etc/chipcoin/mainnet.env \
  -f docker-compose.yml stop node
```

Confirm the node process is stopped. SQLite WAL matters: never copy only the
main `.sqlite3` file while a live WAL connection exists. After clean shutdown,
verify whether `-wal`/`-shm` remain and preserve them with the DB if present.
Create the backup in a staging directory on the same protected filesystem,
then checksum and atomically rename the completed set into the backup catalog.

Example pattern, with site-specific paths supplied explicitly:

```bash
set -euo pipefail
umask 077
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
stage="/var/backups/chipcoin/mainnet/.stage-$stamp"
final="/var/backups/chipcoin/mainnet/db-$stamp"
mkdir -p "$stage"
cp --reflink=auto --preserve=mode,timestamps \
  <db-path> <db-path>-wal <db-path>-shm "$stage" 2>/dev/null || \
  cp --preserve=mode,timestamps <db-path> "$stage/"
sha256sum "$stage"/* > "$stage/SHA256SUMS"
sync "$stage"
mv "$stage" "$final"
```

Do not use the fallback copy pattern until the node is confirmed stopped. An
online backup is permitted only through SQLite's backup API in a separately
validated operational tool; filesystem copy of a live DB is not an online
backup procedure.

Restart and verify after backup:

```bash
docker compose --env-file /etc/chipcoin/mainnet.env \
  -f docker-compose.yml up -d node
docker compose --env-file /etc/chipcoin/mainnet.env \
  -f docker-compose.yml up -d miner
```

### Restore

1. Stop miner and node.
2. Preserve the failed/current DB and logs; do not overwrite the only evidence.
3. Restore into a new empty staging runtime with original ownership/modes.
4. Verify `SHA256SUMS` before use.
5. Run SQLite checks against the restored DB while no node process owns it:

```bash
python3 - <restored-db> <<'PY'
import sqlite3, sys
uri = f"file:{sys.argv[1]}?mode=ro"
db = sqlite3.connect(uri, uri=True)
print("quick_check", db.execute("PRAGMA quick_check").fetchall())
print("foreign_key_check", db.execute("PRAGMA foreign_key_check").fetchall())
PY
```

6. Point a reviewed mainnet configuration at the restored staging runtime.
7. Start node only, verify mainnet/genesis/tip/work/supply/UTXO/reward state,
   then allow P2P catch-up.
8. Compare final fingerprint with independent nodes before enabling mining.

Status: `DOCUMENTED`; backup and restore drills remain separately validated by
the release checklist.

## Corrupted Or Stuck Node

### Evidence First

Before changing state:

```bash
docker compose --env-file /etc/chipcoin/mainnet.env -f docker-compose.yml ps
docker compose --env-file /etc/chipcoin/mainnet.env -f docker-compose.yml \
  logs --no-color --since=2h node miner > <incident-dir>/services.log
curl -fsS http://127.0.0.1:8080/v1/status > <incident-dir>/status.json || true
df -hT > <incident-dir>/disk.txt
df -i > <incident-dir>/inodes.txt
sha256sum /etc/chipcoin/mainnet.env > <incident-dir>/config.sha256
git rev-parse HEAD > <incident-dir>/commit.txt
```

Do not collect wallet contents. Record only wallet file checksums and public
addresses where needed.

### Decision Table

| Symptom | First action | Recovery choice | Do not do |
|---|---|---|---|
| Node healthy but behind | Check peers, disk, clock, sync logs | Restart only after evidence; allow P2P catch-up | Do not replace DB merely because height is behind. |
| Peer starvation | Verify approved peers/DNS/firewall and network identity | Correct infrastructure/config, then P2P catch-up | Do not add unknown testnet/public peers. |
| Disk full/inodes exhausted | Stop miner, preserve logs, stop node safely | Add approved capacity, then restart and integrity-check | Do not delete DB/WAL or active evidence blindly. |
| Crash loop | Stop restart loop and miner; capture first failure | Fix host/config issue; restart same DB only if integrity passes | Do not repeatedly mutate permissions or recreate DB. |
| SQLite integrity failure | Stop miner/node; preserve DB/WAL/SHM and logs | Restore known-good backup, full sync, or trusted snapshot into a new DB | Never edit SQLite rows or run destructive repair on sole copy. |
| Apparent chain divergence | Stop mining; fingerprint independent nodes | Diagnose release/config/network; natural consensus recovery only when understood | Never set tip, copy UTXO state, or delete branch rows manually. |
| Stuck sync with valid DB | Compare peer protocol, tip/work and errors | Restart, then full sync if persistent and cause understood | Snapshot restore is not a generic cure for network mismatch. |

Use restart when process/host state is transient and DB integrity is good. Use
full sync when DB trust or integrity is lost, genesis replay is required, or no
trusted snapshot exists. Use snapshot restore only when its RC gates pass, the
signer is trusted, the artifact matches mainnet/genesis, and a faster bootstrap
is operationally justified.

## Emergency Procedures

### Safe Shutdown

```bash
docker compose --env-file /etc/chipcoin/mainnet.env -f docker-compose.yml stop miner
docker compose --env-file /etc/chipcoin/mainnet.env -f docker-compose.yml stop node
docker compose --env-file /etc/chipcoin/mainnet.env -f docker-compose.yml ps
```

Do not use `down -v`. Do not delete runtime, WAL, snapshots, or logs.

### Emergency Miner Stop

Stop every miner immediately while leaving independent full nodes available for
read-only diagnosis. Verify the miner processes are actually stopped. Do not
restart mining until incident command authorizes it.

### Possible Consensus Incident Or Accidental Fork

Default sequence:

1. Stop mining.
2. Preserve DB, WAL/SHM, logs, status, release/config hashes, peer topology,
   mempool, and deterministic state fingerprints.
3. Compare height, tip, cumulative work, supply, UTXO hash/count, balances,
   reward registry, settlement, and payout state across independent nodes.
4. Identify release commit/image, configuration, network/chain ID, genesis,
   peer sources, and the common ancestor/first divergent headers.
5. Isolate compromised infrastructure if needed, but do not modify chain data.
6. Determine whether normal cumulative-work selection can safely converge.
7. Do not reopen mining until cause and expected recovery are understood and
   documented.

Never manually edit DB/tip/UTXO, inject a chosen block, or copy another node's
database to force agreement.

### Compromised Bootstrap Node

- remove it from DNS/manifests/configuration and stop announcements;
- preserve logs and image/config evidence;
- notify operators through an authenticated channel;
- require nodes to use independently verified peers;
- verify it did not distribute wrong-network endpoints or snapshot metadata;
- rotate infrastructure credentials, not consensus keys, according to scope.

### Compromised Public API

- remove external routing or switch the reverse proxy to maintenance mode;
- keep P2P/node state untouched unless compromise reaches the node host;
- rotate API/TLS/infrastructure credentials;
- inspect access logs and verify wallet-safe endpoint boundaries;
- compare node fingerprints with independent nodes before restoring service.

### Evidence Preservation

Use a new incident directory with restrictive permissions. Record UTC times,
operators, commands, exit codes, hashes, release identity, and immutable copies
of non-secret logs. Never place wallet JSON, private keys, seed phrases, or raw
credentials in the incident bundle. Hash wallet files in place only when chain
of custody requires it.

## Key Management

### Common Rules

- Generate keys on a trusted, patched, access-controlled system with adequate
  entropy and no screen/session recording.
- Never paste keys into chat, tickets, command history, CI variables visible to
  untrusted jobs, or general logs.
- Maintain at least two encrypted, geographically separated backups for keys
  whose loss cannot be recovered on-chain.
- Test restoration using an isolated environment and verify only public address
  and scheme metadata.
- Record custody, backup version, public identifier, and checksum without
  recording the secret in the operational checklist.
- Rotation is not complete until old credentials are revoked or made unusable
  and every consumer has been verified on the new credential.

### Miner Wallet

- Generate/import an ML-DSA-44 mainnet wallet in a key ceremony.
- If using `wallet-generate`, redirect stdout to `/dev/null` because that command
  prints private-key material; retain the owner-only wallet file only:

  ```bash
  umask 077
  set +o history
  chipcoin --network mainnet wallet-generate \
    --scheme mldsa44 --wallet-file <miner-wallet-path> >/dev/null
  set -o history
  ```

- Verify with `wallet-address`; expected CHCQ, `pq`, scheme 10/mldsa44.
- Mount read-only into the miner; do not mount its directory.
- Rotation changes future coinbase destination. Preserve the old wallet until
  all old coinbase/UTXOs are mature and securely transferred under an approved
  transaction plan.
- On compromise, stop the miner, preserve evidence, replace the wallet, update
  the read-only mount, and move spendable funds only after incident review.

### Reward Owner

- Keep separate from miner and attestation keys.
- Use ML-DSA-44/CHCQ, owner-only storage, individual read-only mount.
- The owner authorizes reward-node control operations; use stricter custody and
  less frequent access than the attestation key.
- Before rotation, confirm the protocol supports an authenticated owner update
  preserving node identity. If not, do not improvise DB or transaction changes;
  follow the protocol-supported re-registration/recovery process.
- On compromise, disable reward automation, stop owner-signed operations,
  preserve evidence, and execute the protocol-supported revocation/rotation.

### Reward Attestation

- Generate separately from owner; never derive it from the same secret.
- Use ML-DSA-44 scheme 10 and mount only at
  `/runtime/reward-attest-wallet.json`, read-only.
- Because it signs frequently, monitor access and attestation anomalies.
- On compromise, disable auto-attestation immediately while preserving the
  owner key offline; rotate through the protocol-supported operation. Do not
  substitute the owner wallet as attestation wallet.

### Snapshot Signing Key

- Use a dedicated Ed25519 signing key held offline; it is not a consensus,
  miner, reward owner, or attestation key.
- Export only its public key into the trusted-key distribution.
- Store the raw 32-byte key as hex in a regular file owned by the signing user,
  with mode `0400` or `0600`. Group/other access and symbolic links are
  rejected. Keep the file outside the repository, runtime DB, snapshot output,
  evidence directory, backups, and Docker build context.
- Sign with `snapshot-sign --private-key-file /protected/path/key`; never place
  key material in argv, environment variables, shell substitutions, Docker
  command fields, or logs. The signer reads the protected file directly and
  emits only the snapshot path, derived public key, and signature count.
- Mount the protected file read-only when signing in a dedicated container. Do
  not bake it into an image or copy it into a container layer. Remove temporary
  ceremony copies using the approved secure-media procedure; do not delete the
  custody copy as routine cleanup.
- Hardware-backed signing may replace protected-file input in a later release,
  provided it preserves the existing signature and verifier format.
- On compromise: stop snapshot publication, remove the signer from trusted-key
  manifests/configuration, publish an authenticated revocation notice, rotate
  to a new offline key, and require operators to discard artifacts signed only
  by the compromised key.

### Infrastructure Credentials

- Store DNS, registry, TLS, cloud, backup, monitoring, and deployment
  credentials in the approved infrastructure secret manager.
- Scope each credential to one service and environment; testnet and mainnet
  credentials must be distinct.
- Rotate on staff/host/service changes and immediately after suspected exposure.
- Infrastructure credential compromise does not authorize changing consensus
  state; isolate the affected service and verify node fingerprints.

Status: `DOCUMENTED`; each production key ceremony and restore drill must be
recorded in the operator checklist without secret material.

## Runbook Gate Mapping

| RC gate | Documentation coverage | Runtime validation |
|---|---|---|
| `RUNBOOK-001` | Host/release verification, first node, joining node | Separate launch/full-sync gates |
| `RUNBOOK-002` | Backup, restore, full sync, trusted snapshot bootstrap | Backup drill and snapshot runtime gates |
| `RUNBOOK-003` | Corrupt DB, stuck node, peer starvation, divergence, disk-full, crash loop | Fault/sync/storage gates |
| `RUNBOOK-004` | Safe shutdown, miner stop, consensus incident, evidence collection | Incident exercise/fault gates |
| `RUNBOOK-005` | Miner, owner, attestation, snapshot signer, infrastructure compromise | Key ceremonies and recovery drills |

The five runbook gates require complete documentation and can be marked PASS
when this document is reviewed. That status does not promote any separate
runtime gate.
