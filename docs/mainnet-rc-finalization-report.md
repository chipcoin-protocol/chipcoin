# Mainnet Release-Candidate Finalization Report

Date: 2026-10-15

## Decision

- `MAINNET_RC_READY = TRUE`
- `PUBLIC_LAUNCH_READY = FALSE`
- RC identity: `mainnet-v0.1.2-rc.1`
- source commit: `698816e15e4397dd2f5bba320b88ca5dd3e28830`
- annotated tag object: `b70fc5d00fc64b0156d74d022924429a51a15c20`
- tag signature: annotated, not cryptographically signed

The software release candidate is frozen and traceable. This decision does not
authorize public deployment. Public infrastructure remains governed by the
separate `PUBLIC_LAUNCH_BLOCKING` requirements.

## Source Freeze

The functional RC tree was inventoried and committed before tagging. The tag
`mainnet-v0.1.2-rc.1` resolves to commit
`698816e15e4397dd2f5bba320b88ca5dd3e28830`. `git status --porcelain` was empty
after the commit and tag. The release image was built from a clean `git archive`
of that tag rather than from the mutable working directory.

The source archive is preserved at
`/tmp/chipcoin-mainnet-rc-v0.1.2-rc.1/source.tar` with SHA-256:

```text
2b4381c3c27a2233695b7977be0477fa1c2bf908ec6c49ee33c6465fa244d9dc
```

Release evidence documentation and gate-state updates are intentionally
recorded after the source tag. They do not change the source represented by the
tag or the image built from it.

## Docker Image

- local tag: `chipcoin-mainnet-node:0.1.2-rc.1`
- immutable image ID: `sha256:25f3dca52fabad5f7b818e17132e994ef6d3ee5f6f169427d9533002eac1e3eb`
- architecture: `linux/amd64`
- image size: `150989911` bytes
- exported image tar: `/tmp/chipcoin-mainnet-rc-v0.1.2-rc.1/chipcoin-mainnet-node-0.1.2-rc.1.tar`
- exported tar SHA-256: `cdcb917a9151c9854ee78554d1d39e882d6116f291535abbb05d0f35a8c49cb5`
- resolved base image: `python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce`

OCI labels bind the image to version `0.1.2-rc.1`, source tag
`mainnet-v0.1.2-rc.1`, and source revision
`698816e15e4397dd2f5bba320b88ca5dd3e28830`. A registry `RepoDigest` does not
exist before publication; the content-addressed local image ID and exported tar
checksum are the immutable pre-publication identifiers. Publication must retain
the image ID and record the resulting registry digest.

Image smoke checks passed:

- `chipcoin --help` starts successfully;
- installed package version is `0.1.2`;
- `pip check` reports no broken requirements;
- no compiler, wheel directory, `setuptools`, or `wheel` remains in runtime;
- no wallet, seed, key, PEM, or `.env` file was found in runtime paths.

## Browser Artifacts And Locks

- Chrome named artifact tree SHA-256: `e21e975b13b555744ce3c6f473d0cc1370449411597e193c2b78beb55353a082`
- Firefox named artifact tree SHA-256: `adcbfd457cb7170ce1b3d1106655abc93d5e0dff131efd4c9912ca6441056bb6`
- browser `package-lock.json` SHA-256: `c09dbc0f069434f32e61aa5a93eea1986488ec21dbe02dd8c086e0f7578cf7fb`

The named artifacts are the same artifacts already runtime-validated by the
clean-profile browser gate. `npm ci`, 89 browser tests, TypeScript typecheck,
Chrome/Firefox production builds, and web-extension lint all passed.
Production-only `npm audit` reports zero vulnerabilities. The accepted
Vite/esbuild finding remains restricted to build/development tooling and no
development server is part of the release deployment.

## Build Traceability

The build is traceable from:

1. immutable Git tag and commit;
2. archived source checksum;
3. browser dependency lock checksum;
4. Dockerfile and consensus/configuration file checksums;
5. resolved base-image digest;
6. OCI revision/version labels;
7. final image ID and exported-image checksum;
8. complete build log and image inspection under
   `/tmp/chipcoin-mainnet-rc-v0.1.2-rc.1`.

The Python project currently specifies compatible dependency ranges rather than
a fully pinned lock. Therefore this report claims traceability of the frozen
artifact, not guaranteed future byte-for-byte reproducibility. The exact image
and tar are content-addressed and retained as release evidence.

## Verification

- Python suite: `842 passed`
- fault-harness suite: `109 passed`
- browser suite: `89 passed`
- browser typecheck/build/lint: PASS
- Python dependency consistency: PASS
- browser production dependency audit: 0 vulnerabilities
- shell syntax, JSON validation, and `git diff --check`: PASS
- tracked-secret and runtime-image secret scans: PASS

Build host/toolchain evidence:

- Docker client/server `29.1.3`
- Docker Compose `2.40.3`
- Python host `3.12.3`; image Python `3.11.17`
- Node `22.23.3`; npm `11.12.1`
- Linux `7.0.0-34-generic` `x86_64`

## Gate Results

| Gate | Result | Evidence |
|---|---|---|
| `SEC-REL-001` | `PASS` | Immutable version, source commit, and annotated tag recorded. |
| `SEC-REL-002` | `PASS` | Frozen source tree inventoried and clean at tag creation. |
| `SEC-REL-004` | `PASS` | Immutable image ID and exported-image checksum recorded. |
| `SEC-REL-005` | `PASS` | Commit-to-source-archive-to-image traceability is complete. |

Final RC counts are `98 PASS / 0 FAIL / 0 NOT_RUN / 0 PENDING_HEIGHT /
0 BLOCKED`. Public-launch-only counts remain `7 NOT_RUN`.
