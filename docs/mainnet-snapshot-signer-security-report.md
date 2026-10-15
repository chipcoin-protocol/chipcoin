# Mainnet Snapshot Signer Security Report

Date: 2026-10-05

## Scope

This report closes only `SEC-SNAP-KEY-001`. It does not claim that a real
mainnet rehearsal snapshot, restore, or delta sync has been executed.

MemPalace was consulted before the implementation audit. The code audit then
traced the signer from the operator publisher through the CLI and into the
Ed25519 snapshot implementation.

## Original Vulnerability

`snapshot-sign` required `--private-key-hex`. The testnet publisher accepted
the same secret in `SNAPSHOT_SIGNING_PRIVATE_KEY_HEX`, or read a key file into
that shell variable, and interpolated it into the child command line. The
private key was consequently observable in child argv and `/proc/<pid>/cmdline`
and could also be retained by shell/process telemetry. Snapshot signing itself
correctly emitted only public signature material; the defect was the transport
of the private key into the signer.

## Threat Model

The protected inputs include argv, process listings, environment variables,
shell history, stdout/stderr, logs, Docker command metadata, snapshot metadata,
test evidence, temporary files, and Git changes. The signing key remains
operator-owned secret material and must be readable only by the signer account.
The snapshot artifact, signature, and trusted public-key behavior remain public.

## Fix

- `snapshot-sign` now requires `--private-key-file`; the private key value is no
  longer a supported CLI argument.
- The file is opened read-only with close-on-exec and no-follow semantics.
- `fstat` requires a regular file owned by the current user, owner-readable,
  and inaccessible to group/other users. Modes such as `0644` and symlinks are
  rejected before parsing key material.
- The publisher passes only the protected path. It no longer reads the key into
  a shell variable and rejects the legacy private-key environment variable.
- The key path is operator supplied, outside Git/runtime/snapshot/evidence and
  Docker build contexts. No dependency, snapshot format, checksum, signature,
  trust-anchor, restore, delta-sync, consensus, or reward behavior changed.

## Validation

### Leakage and process inspection

An actual subprocess signed an isolated snapshot using a recognizable runtime
canary key. While the process was alive, `/proc/<pid>/cmdline` and
`/proc/<pid>/environ` were inspected. The canary was absent. It was also absent
from captured stdout/stderr, command evidence, generated snapshot bytes, every
other temporary artifact, and the repository diff. The subprocess used
`shell=False`, so no secret-bearing shell command existed. The supported
publisher command contains only `--private-key-file` and the path; no Docker
signer command embeds key material.

Result: **PASS**.

### Permissions

- Protected regular file, mode `0600`: **PASS**.
- Group/other-readable modes `0604`, `0640`, `0644`: **rejected**.
- Symbolic-link key input: **rejected**.
- Errors contain no key material: **PASS**.

### Signing and trust

- Deterministic canonical snapshot signing and public-key verification:
  **PASS**.
- Enforced import with the authorized public key: **PASS**.
- Altered artifact: **rejected**.
- Altered signature: **rejected**.
- Untrusted signer: **rejected fail-closed**.
- Unsigned artifact under enforce mode: **rejected fail-closed**.
- Existing v1/v2 format and verifier compatibility: **PASS**.

### Regression results

The distinct relevant suites completed as follows:

| Suite | Result |
|---|---:|
| Snapshot signer leakage/security | 3 PASS |
| Snapshot implementation/trust | 23 PASS |
| CLI | 82 PASS |
| Runtime integration, including snapshot delta bootstrap | 26 PASS |
| **Total** | **134 PASS** |

Additional checks:

- `bash -n scripts/ops/build-testnet-snapshot.sh`: **PASS**.
- RC/operator JSON validation: **PASS**.
- `git diff --check`: **PASS**.
- Dependency manifests changed: **NO**; no dependency vulnerability was
  introduced.
- Snapshot private key argv references in supported snapshot paths: **NONE**.

## Rehearsal Status

No snapshot, restore, delta sync, fault injection, node restart, DB mutation, or
consensus/reward change was performed on the live rehearsal. A status-only
check showed node-a/node-b/node-c converged at height 244, tip
`0000000d54d2e7cd63ae56012c37075419b2dc9e3f4d40c0a990d568a7dd00a7`,
cumulative work `53686280130`, and mempool size zero.

## RC Decision

`SEC-SNAP-KEY-001` is promoted from `NOT_RUN` to `PASS`. RC-blocking counts are
now 72 `PASS`, 18 `NOT_RUN`, 8 `PENDING_HEIGHT`, 0 `FAIL`, 0 `BLOCKED` (98
total). All real snapshot production/restore/delta gates remain unchanged.

```text
SEC_SNAP_KEY_001 = PASS
PRIVATE_KEY_ARGV_EXPOSURE = NO
SECRET_LEAKAGE_DETECTED = NO
SNAPSHOT_SIGNER_READY = YES
```
