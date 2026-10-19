# Public Mainnet RC1 Pre-Freeze Report

Date: 2026-10-19. Status: **pre-freeze preparation only; no genesis approval,
freeze, RC tag, publication, deployment, or launch**. MemPalace was consulted
first; it contains no later approved launch timestamp or decision. This report
uses current repository state and focused local evidence.

## Reproducible toolchain

`pyproject.toml` now pins the runtime dependency and optional tool sets;
`uv.lock` records the resolved transitive versions and registry hashes. A clean
CPython 3.12.3 environment was created outside the repository at
`/tmp/chipcoin-rc1-clean-venv` using `uv sync --locked --extra dev --extra
build`. Locked components:

| Component | Locked version |
|---|---:|
| CPython used for this build | 3.12.3 |
| cryptography | 46.0.6 |
| cffi / pycparser | 2.1.1 / 3.11 |
| pytest | 9.0.2 |
| setuptools / wheel | 68.1.2 / 0.42.0 |
| iniconfig / packaging / pluggy / Pygments | 2.3.1 / 26.3 / 1.7.0 / 2.21.0 |
| uv | 0.11.24 |
| Node / npm / Vite | 22.23.3 / 11.12.1 / 5.4.21 |

Hashes: `pyproject.toml` `b4e047bee3dbe668786401f2daf3f919dc235295ec75490dfcfb70da0aba8c69`;
`uv.lock` `6bb02013ec495b5839d16b9206b1cbd54e1a8fdabbfc42c4197173562de7b521`;
`setup.py` `8983a771e772aff4fdf5acefc47164e887e99fc238c9660492c9d5fd30677bb7`;
browser `package-lock.json` `c09dbc0f069434f32e61aa5a93eea1986488ec21dbe02dd8c086e0f7578cf7fb`.

Two Python wheels built from separate source copies matched byte-for-byte at
SHA-256 `50b57c28728d36b12c8a41ff36739402c51dfff8d492e9bf2e0f48db6429ace4`.
The controlled build used the base source commit epoch `1792069138` as
`SOURCE_DATE_EPOCH` and Linux source-prefix mapping in `setup.py`. The first
comparison exposed absolute build paths in ML-DSA native debug data and
different ZIP timestamps; both causes were removed for the passing pair.
Two separate Chrome builds have identical tree SHA-256
`0be6665d107e144c40973f0332ee98011c8814983e9b57df95bd6c1edd19286d`; two
Firefox builds have identical tree SHA-256
`4b2d68aae85973ba409037aaa7f991ef58806ab3c64d5c5af28498656544e253`. They
were produced to `/tmp/chipcoin-rc1-repro/`, not to the named production
artifact directories. The browser runs used the installed dependency tree
whose versions were checked against `package-lock.json`; a separate clean
`npm ci` install was not performed. Neither browser tree contains the current
candidate genesis hash.

This does **not** prove reproducibility of the final Docker image. `Dockerfile`
uses mutable `python:3.11-slim`, `apt-get update`, and unpinned OS package
inputs. A public RC image must pin a base-image digest and reproducible OS
build inputs before its image digest can be treated as traceable. No Docker
image was built or published here.

## Worktree and repository boundaries

The main repository is based on `63de78592f1bc577df579a53281fac5ed515e422`
and remains dirty: 59 tracked files modified and 89 untracked files at the
current inventory snapshot. It contains candidate consensus/client changes,
public-mainnet preparation, historical rehearsal tooling, and extensive
TEST-ONLY V3 infrastructure/evidence. The exhaustive path classification is
in `docs/public-mainnet-rc1-worktree-inventory.md`. No existing change was
discarded, staged, committed, pushed, or deployed.

The authoritative Explorer repository at
`/home/komarek/Documents/CODEX/chipcoin-central` is also dirty: base
`17a19e9e6f5d7b816e4854dd90baf1333085b066`, 12 tracked modifications and 2
untracked tests. Existing work adds mainnet/network identity behavior and
deployment configuration. Mainnet genesis is still `null`, and the Explorer
fails closed until configured. It was inspected but not changed or deployed.

Proposed future commit ordering, subject to review:

1. Protocol/network identity and consensus implementation with focused tests.
2. Node/miner/wallet/client integration and tests, with the Explorer committed
   separately in its authoritative repository.
3. Release/build tooling and runbooks, separated from TEST-ONLY operator
   experiments and archived evidence.
4. Only after timestamp approval: canonical genesis bytes/hash and all
   identity pins, with a separate review of every dependent artifact/config.
5. Deployment configuration and evidence manifest as separate release
   preparation commits; no deployment is implied by those commits.

This is a proposal, not a claim that the current dirty tree is commit-ready.

## Genesis candidate and identity consumers

The candidate remains only in
`/tmp/public-mainnet-genesis-proposal-20261019T080000Z/`; its source is the
earlier proposal document and the proposal manifest. It is **not approved**,
not embedded in production code, and not copied to public configuration.
Current recorded candidate values are timestamp `2026-10-19T08:00:00Z`, bits
`0x1d1399ad`, nonce `358646568`, hash
`000000049b99a576c7f281945b3a1faad26161bd828ee6a81e3772b2844565ce`, TXID /
Merkle root `6ec15ed32ddd62c6134b0c867c33f8fa72ba265b4551d327a57b63721cf34c77`,
and serialized-block SHA-256
`2a107f6aa36e1ff424aa3247dc4a1171069c890c79b1ef2dcf7af379bd2b045e`. The
exact timestamp is not a launch-time decision; no launch date exists, so
coherence with actual public exposure cannot yet be established. It was not
copied from TEST-ONLY.

The standard-library-only verifier independently reparses the serialized
block, confirms UTF-8 message and metadata, empty inputs/outputs, zero supply,
TXID, Merkle root, PoW, block hash, manifest, and SHA-256 checksums. The
production serializer independently generated the same bytes in prior
focused tests. The independent scan of every nonce below `358646568` completed
with two workers; `lowest_nonce=true`, and the metadata, no-input/output,
TXID, Merkle, PoW, block hash, manifest, and checksum checks all passed. The
scan used the new `--verify-lowest-nonce` mode. This establishes minimality
only for this candidate's timestamp and bits; it is not a second genesis build
on another host. Full result and artifact checksums are recorded in
`docs/releases/public-mainnet-genesis-candidate-verification.json`. Regardless,
this timestamp/hash remains unapproved.

Identity consumers already located and their state:

- Full node: `consensus/genesis.py`, `config.py`, and node startup/storage;
  public-mainnet constants remain pending and startup fails closed.
- P2P: `network_identity.py` and handshake codec/protocol bind chain ID and
  genesis; expected final hash is not yet embedded.
- Miner and CLI/reward signing: miner endpoint identity checks, CLI, wallet
  signer, and reward signature domains bind network/chain identity; recheck
  their final genesis/API values after approval.
- Snapshot bootstrap: snapshot metadata and trust checks include chain ID and
  genesis; final mainnet snapshot remains identity-dependent.
- Browser wallet: mainnet `canonicalGenesisHash` is `null`; runtime rejects
  mainnet use fail-closed. Current candidate hash is absent from the produced
  bundles.
- Explorer: separate dirty repository; mainnet `genesisHash` is `null` and
  identity comparison fails closed.
- Docker/operations: chipcom Compose/env examples, image labels, bootstrap
  peers, monitoring, and release manifests require the approved final hash.
  The candidate hash was not inserted into them.

Funded-v2 remains configured at activation height 0 for public mainnet, which
means mandatory from operational block 1. TEST-ONLY remains at 300 and
testnet's activation is unset; these were not changed in this task. No
activation behavior was re-audited or promoted here.

## Gate status

The matrix still contains exactly 98 RC requirements, all `NOT_RUN`; seven
public-launch gates are also `NOT_RUN`. Zero formal gate statuses were
promoted by this pre-freeze work. The focused local suite ran **41 tests,
41 passed**, covering genesis serialization/storage, identity, funded-v2
profile/validation, matrix generation, and nonce-minimality positive/negative
fixtures. The clean artifact/build checks are independent evidence and do not
count as RC gate PASS. No new-chain runtime gate was run.

The existing matrix classifies 30 as `SOURCE_REVALIDATION`, 5 as
`RELEASE_FINALIZATION`, and 63 as `ISOLATED_CHAIN_RUNTIME`. The first class is
potentially executable before the timestamp but has not been promoted by this
work; the latter two require clean source/artifact provenance or a finalized
identity and isolated canonical-chain runtime, respectively.

The source gate definitions provide each RC gate with a description,
dependencies, evidence-catalog references, category, blocker class, and status.
The derived matrix carries network/chain/hash identity and excludes historical
PASS. A per-gate automated execution/evidence adjudicator does not exist: the
matrix builder resets statuses and the runbook groups runtime commands by
phase. A safe future runner needs explicit command/evidence manifests and
must never infer PASS from a generic suite. This remains a preparation
blocker; no status was written back to either gate source.

## Remaining blockers and freeze procedure

Blocking items before RC1 freeze:

- Founder-approved UTC timestamp and an explicit launch-time policy.
- Completion and retained evidence of independent lower-nonce verification;
  then repeat genesis construction on a second clean host/toolchain/worker
  count and byte-compare block, manifest, and checksums.
- Review/freeze the dirty main and Explorer worktrees, separate historical
  and TEST-ONLY files from RC commits, and produce clean source identities.
- Pin Docker base image digest and OS build inputs; rebuild and record final
  node image digest after genesis approval.
- Build Chrome/Firefox named production artifacts after inserting the
  approved genesis; run clean-profile runtime checks against those exact
  artifacts. Build and validate Explorer against the same identity.
- Define per-gate executable evidence commands/records and run all 98 gates
  on a new isolated canonical chain; no historical or TEST-ONLY PASS carries
  over.
- Confirm the RC version/tag-signing, Explorer source owner, registry,
  distribution, snapshot key custody, and deployment approvals.

Freeze sequence once explicitly authorized: approve timestamp; mine in a new
empty candidate directory using the canonical builder and recorded toolchain;
independently reproduce and verify lowest nonce; review the exact block bytes
and checksums; pin all client/config/image identities in reviewed source;
create a clean source commit; build twice from clean locked environments;
compare artifacts and record digests; then execute the 98-gate plan. This
report does not perform the freeze.

**Decision:** `GENESIS_FREEZE_AUTHORIZED = NO`, `RC1_READY = NO`,
`PUBLIC_LAUNCH_READY = NO`.

## Resource usage

Token counters and session quota are not exposed to this report: `N/D`.
Focused tests: 41 passed. Other tool-call count and exact wall-clock duration:
`N/D`. The first wheel comparison was a useful failure that identified two
reproducibility inputs; no global test suite, live chain operation, reset,
commit, push, or deployment was run.
