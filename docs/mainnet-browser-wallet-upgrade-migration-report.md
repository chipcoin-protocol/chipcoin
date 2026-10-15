# Mainnet Browser Wallet Upgrade / Migration Report

Date: 2026-10-06

## Decision

`BW-OPS-002` is legitimately **not applicable** to the first mainnet/PQ
browser-wallet release. No supported predecessor release has a contract for
in-place migration into a mainnet ML-DSA-44/CHCQ wallet. No synthetic upgrade
profile was constructed and no migration behavior is claimed as runtime-tested.

The release-gate schema does not define a `NOT_APPLICABLE` status: its allowed
states are `PASS`, `FAIL`, `NOT_RUN`, `PENDING_HEIGHT`, and `BLOCKED`, while RC
readiness requires every RC-blocking requirement to be `PASS`. The gate's own
notes explicitly permit not-applicable closure with a documented rationale.
Accordingly, the machine-readable requirement is closed as `PASS` with
`NOT_APPLICABLE` stated in its notes and evidence. This means the applicability
decision passed; it does not mean an upgrade runtime test was executed.

MemPalace was consulted. It contained devnet/testnet browser-wallet build and
distribution guidance, but no mainnet/PQ predecessor or migration contract.

## Formal Gate Semantics

The requirement is: "Upgrade/migration preserves encrypted wallet and
network-scoped state where applicable." Its existing notes say to mark it not
applicable only with an explicit version/migration rationale. Therefore the
gate requires one of two defensible outcomes:

1. test a supported predecessor and its documented migration contract; or
2. prove that no such contract exists for this first mainnet/PQ release.

Development artifacts, stale build directories, and unsupported network state
do not create a migration contract.

## Predecessor Analysis

| Candidate | Evidence | Classification | Mainnet/PQ migration contract |
|---|---|---|---|
| Git tag `v0.1.1` (`871cdcf`) | Commit title is `Release candidate 0.1.1 for devnet`; embedded wallet package/manifest version is `0.1.0`; docs explicitly say `Not included: mainnet support` | Devnet release candidate | None |
| Browser wallet `0.1.1` AMO preparation (`e6b0b4d`) | Manifest describes a devnet/testnet wallet; documentation requires AMO signing before normal install | Development-network release preparation | None |
| Mozilla add-on/listing | `apps/browser-wallet/AMO_APPEAL.md` records permanent disablement and describes the product as devnet/testnet only | No currently supported predecessor distribution | None |
| Local `0.1.1` ZIP files | Devnet/testnet manifests; no signed Firefox XPI or mainnet scope establishes a supported upgrade source | Build/release artifacts, not a mainnet predecessor | None |
| Stale `dist-chrome` / `dist-firefox` | Named build outputs that caused the closed `BW-OPS-001` artifact incident | Stale development artifacts | None |
| Legacy devnet/testnet storage | Format-2 legacy/ECDSA wallet and development-network state | Explicitly non-mainnet state | Explicit mainnet refusal, not migration |

The first supported mainnet/PQ user path is therefore clean installation plus
explicit ML-DSA-44 wallet creation or PQ seed import. There is no supported
legacy-to-PQ key conversion, testnet-to-mainnet state reinterpretation, or
silent ECDSA fallback.

## Network-State Safety

Static production paths and already accepted `PQ-NEG-002` evidence establish:

- `DEFAULT_NETWORK` remains `testnet`; an upgrade cannot silently select
  mainnet merely because mainnet support exists;
- saved supported network selection is preserved by `loadSettings()`;
- legacy unscoped transaction/cache fallback is read only for `devnet`, never
  for mainnet or testnet;
- transaction, cache, and watch-only state use network-scoped keys;
- `updateNodeEndpoint()` rejects mainnet selection unless the stored wallet is
  `pq_seed`, with `Mainnet requires an ML-DSA-44 post-quantum wallet.`;
- endpoint identity is validated before settings are persisted;
- existing cross-network replay and state-isolation evidence shows no silent
  network switch or cross-network contamination.

Thus an old legacy wallet may remain recoverable only in its applicable
development context; it is not promoted or reinterpreted as a mainnet wallet.
An operator/user must explicitly create or import a PQ wallet for mainnet.

## Named Artifact Provenance

Only the canonically rebuilt, runtime-validated named artifacts were considered:

| Artifact | Tree SHA-256 |
|---|---|
| `apps/browser-wallet/dist-chrome` | `e21e975b13b555744ce3c6f473d0cc1370449411597e193c2b78beb55353a082` |
| `apps/browser-wallet/dist-firefox` | `adcbfd457cb7170ce1b3d1106655abc93d5e0dff131efd4c9912ca6441056bb6` |

Both hashes match the accepted `BW-OPS-001` remediation baseline. No artifact
was rebuilt or changed during this gate.

## Secret Hygiene

No browser profile, wallet, seed, password, or private key was created or
imported. The audit used Git metadata, manifests, documentation, source code,
artifact hashes, and previously sanitized evidence only. No secret material was
placed in argv, environment, logs, evidence, this report, or the repository.

## Rehearsal Read-Only State

A/B/C were converged at height `389`, tip
`0000000d09e5d3c319f6e0d01f1e008a0793457aa115649c78794fe3c1768106`,
and cumulative work `85459792860`. Each node had two handshaken peers, an empty
mempool, matching reward-registry hash
`250181d631f01060457af722e0d794c0c5af7d173233338c522b849342526fbb`,
and SQLite quick/FK checks passing. Both miners and the ordinary monitor were
active. The two reward nodes remained registered at height 275,
`active=false`, with warmup-complete epoch 4; settlement count and distributed
rewards remained zero. No rehearsal mutation or reward action occurred.

## Gate Result

The applicability requirement is closed with explicit evidence. The RC matrix
represents this closure as `PASS (NOT_APPLICABLE)` because `NOT_APPLICABLE` is
not an allowed machine status. RC-blocking counts become 86 `PASS`, 5
`NOT_RUN`, 7 `PENDING_HEIGHT`, and 0 `FAIL`.

```text
SUPPORTED_PREDECESSOR_EXISTS = NO
MIGRATION_CONTRACT_EXISTS = NO
LEGACY_STATE_AUTO_PROMOTED_TO_MAINNET = NO
NETWORK_STATE_SAFETY = PASS
NAMED_ARTIFACTS_UNCHANGED = YES
SECRET_HYGIENE = PASS
BW_OPS_002 = NOT_APPLICABLE
BROWSER_MIGRATION_BLOCKER = NO
RC_STATE = 86_PASS_5_NOT_RUN_7_PENDING_HEIGHT_0_FAIL
```
