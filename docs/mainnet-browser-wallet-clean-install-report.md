# Mainnet Browser Wallet Clean Install Report

Date: 2026-10-06

## Decision

The production Firefox extension completed the full clean-profile workflow.
The initial Chromium run then exposed stale named artifacts: source and a fresh
diagnostic build contained the current mainnet/PQ flow, while
`apps/browser-wallet/dist-chrome` did not.

The named Chrome and Firefox artifacts were subsequently regenerated through
the canonical `apps/browser-wallet/build-all.sh` path without changing source
code. The new Chrome tree is byte-identical to the diagnostic build, and the
new Firefox tree is byte-identical to the artifact already validated in
Firefox. Chromium `153.0.8010.52 for Linux Mint` loaded the regenerated named
Chrome artifact and passed clean install, mainnet PQ creation, complete restart
persistence, network switching, API identity fail-closed checks, and secret
hygiene. `BW-OPS-001` is therefore `PASS`.

MemPalace was consulted before execution. It confirmed the intended temporary
Firefox loading path, encrypted extension-local storage, stable extension ID,
and create/import first-use behavior. It contained no prior mainnet
clean-profile runtime evidence.

## Artifact Identity

Pre-build provenance and immutable copies of both stale named artifacts are
stored under `/tmp/chipcoin-mainnet-bw-ops-001-remediation-20261006/prebuild`.
The canonical rebuild did not change the relevant source tree.

| Field | Value |
|---|---|
| Source commit | `586160840a568eb64a1d4aa2b1c909805386cb2c` |
| Source description | `v0.1.1-195-g5861608-dirty` |
| Package version | `0.1.2` |
| Manifest version | `3` |
| Package-lock SHA-256 | `c09dbc0f069434f32e61aa5a93eea1986488ec21dbe02dd8c086e0f7578cf7fb` |
| Relevant source-tree SHA-256, before/after | `32f04029b3bc5a7e586c1abd9632d6a2b641cd55f3eb9c1c78ea2f19090a04f5` |
| Old named Chrome tree SHA-256 | `0df1d0a1a1ff83c289116317bdaa3fb40d0e91c3d31b10da7d14c6419fa2dbcf` |
| New named Chrome tree SHA-256 | `e21e975b13b555744ce3c6f473d0cc1370449411597e193c2b78beb55353a082` |
| Diagnostic Chrome tree SHA-256 | `e21e975b13b555744ce3c6f473d0cc1370449411597e193c2b78beb55353a082` |
| Old named Firefox tree SHA-256 | `0f986a78246768a235f8bab5d93f1a97ae14fd5352dc9f456786ceadb9ccef56` |
| New named Firefox tree SHA-256 | `adcbfd457cb7170ce1b3d1106655abc93d5e0dff131efd4c9912ca6441056bb6` |
| Previously validated Firefox tree SHA-256 | `adcbfd457cb7170ce1b3d1106655abc93d5e0dff131efd4c9912ca6441056bb6` |
| Chrome production build | `PASS` |
| Firefox production build | `PASS` |

The dirty-worktree state is already owned by the later release-freeze gates;
it is recorded here to identify the exact artifacts and is not reclassified by
this operational gate.

## Firefox Clean Profiles

Firefox `156.0.1` loaded the production artifact through `web-ext`. WebDriver
BiDi controlled the real extension pages with Firefox's explicit system-access
automation flag. Two independent profile directories were created with mode
`0700`; both contained zero entries before Firefox installation. No previous
wallet, local storage, network selection, login session, or cache existed.

Temporary extension UUIDs were resolved from each running clean profile. This
is necessary because Firefox assigns a new internal `moz-extension` UUID when
the same stable extension ID is temporarily loaded. It does not alter extension
storage semantics.

## Mainnet PQ Wallet Creation

The first profile used the visible onboarding `Create PQ wallet` path, set a
password, selected mainnet, and saved a local production-equivalent API
endpoint. Runtime state showed:

| Field | Value |
|---|---|
| Wallet type | `pq_seed` |
| Address | `CHCQCqkHDByobAuVbScBFgugGsmwgPVJv7wvhwT5MSWNDRGZPkCJ6BHP` |
| Public-key size | `1312` bytes |
| Wallet format | `3` |
| Account index | `0` |
| Selected network | `mainnet` |
| Connected API network | `mainnet` |

The `pq_seed` route uses the production ML-DSA-44 backend and scheme ID 10;
the resulting address is CHCQ. No legacy/ECDSA wallet was created or used.

## Persistence And Functional Smoke

Firefox was fully stopped and restarted with the same initialized profile. The
wallet reappeared locked, then unlocked through the normal popup UI. Address,
public-key hash, wallet type, format, account index, mainnet selection, and API
endpoint were unchanged. No accidental wallet regeneration occurred.

The post-restart popup displayed the CHCQ receive address, Mainnet indicator,
connected mainnet status, API endpoint, height, and balance. The clean-profile
flow therefore covered unlock/use, address rendering, network indicator, API
connection, and balance query. Signed login is not part of normal startup; its
production modules remained covered by the nine signed-login regressions in
the same test run.

## PQ Import

A second independent profile used the visible `Import PQ seed` onboarding path.
The 32-byte seed was generated in process memory and was never passed through
argv or environment. Runtime state showed:

| Field | Value |
|---|---|
| Wallet type | `pq_seed` |
| Address | `CHCQCqkGnFAozuoF3bWxDyEZF1GyJRANZo6FbW57iwLc9xwznC2mK58M` |
| Public-key size | `1312` bytes |
| Wallet format | `3` |
| Selected network | `mainnet` |

After a complete Firefox restart, unlock recovered the same address and
public-key hash. The protected profile was removed after validation.

## Network And API Safety

The created wallet completed this real UI sequence:

```text
mainnet balance 111
-> testnet balance 222
-> mainnet balance 111
```

The original CHCQ address and mainnet state were recovered after switching
back. Distinct mock values prove that data was loaded from the correct
network-scoped cache rather than merely relabelled.

Using the production API client and settings UI:

- a testnet API selected as mainnet was rejected with `Wrong network. Expected mainnet, got testnet.`;
- an API omitting `status.network` was rejected with `Wrong network. Expected mainnet, got undefined.`;
- both rejections left the prior mainnet network and endpoint unchanged;
- there was no silent network switch, wallet mutation, or transaction submit.

The isolated local API received 49 read-only GET requests. No funds or
transactions were sent to the rehearsal.

## Secret Hygiene

The import seed and generated passwords were held only in harness/browser
memory and encrypted extension storage during the test. Targeted scans found
no seed in:

- process command lines;
- process environments;
- browser/web-ext logs;
- generated evidence;
- the repository;
- unprotected temporary files.

Both browser profiles were mode `0700`, no plaintext seed was found even in
the protected import profile, and both profiles were removed after the restart
checks. No screenshots were taken. Evidence contains only public addresses,
public-key hashes/lengths, sanitized state, artifact hashes, and request paths.

## Initial Chromium Runtime Failure

The operator installed Chromium manually before the resumed test. Runtime
identity was:

```text
Chromium 153.0.8010.52 for Linux Mint
```

The test created a new empty profile at mode `0700`, loaded only
`apps/browser-wallet/dist-chrome` with `--disable-extensions-except` and
`--load-extension`, and observed extension ID
`cfhlpekkjlockfnfdhfmnpbpcijpdjec`. The Manifest V3 service worker was active,
the popup page loaded with title `Chipcoin Wallet`, and no critical startup
failure was observed.

The visible clean-profile popup contained these setup controls:

```text
Create
Recover
Import key
Create wallet
```

Static inspection of the exact packaged JavaScript independently found no
`Create PQ`, `Import PQ`, `Create PQ wallet`, or PQ setup copy. The current
tracked `SetupWallet.tsx` source does contain those controls, establishing that
the designated `dist-chrome` artifact is stale or otherwise inconsistent with
the PQ-capable source. The test stopped before entering a password, generating
a wallet, changing network state, or contacting the rehearsal.

Consequently extension startup passed, but mainnet PQ creation, persistence,
network switching, and API identity smoke could not be completed through this
artifact. They are recorded as failures of the aggregate gate rather than
inferred from Firefox evidence.

That result is retained as root-cause evidence and is superseded only by the
controlled canonical rebuild and clean-profile rerun below.

## Canonical Rebuild And Chromium Retest

`apps/browser-wallet/build-all.sh` regenerated both named artifact directories
and packaged downloads. `web-ext` reported zero errors, warnings, and notices.
Static checks on the new Chrome artifact found mainnet selection, `Create PQ
wallet`, `Import PQ seed`, `wallet:createPq`, the current mainnet API,
ML-DSA-44, CHCQ, Manifest V3, and the module service worker. Recursive diffs
against the diagnostic Chrome tree and validated Firefox tree were empty.

A new mode-`0700` Chromium profile contained zero entries before startup. The
runtime loaded only `apps/browser-wallet/dist-chrome`, observed extension ID
`cfhlpekkjlockfnfdhfmnpbpcijpdjec`, and confirmed an active Manifest V3 service
worker with no critical startup errors. The production onboarding page created
a `pq_seed` wallet with a 1312-byte ML-DSA-44 public key, scheme ID 10, and CHCQ
address. No legacy/ECDSA fallback was used.

Chromium was completely stopped and no profile process remained. Reopening the
same profile recovered the same CHCQ address and public-key hash in locked
state, then unlocked it normally. The runtime sequence
`mainnet (balance 111) -> testnet (balance 222) -> mainnet (balance 111)`
recovered the original wallet and mainnet state without contamination.

The correct mainnet API identity was accepted. A testnet identity selected as
mainnet and an API with missing `status.network` were both rejected while the
prior mainnet endpoint remained unchanged. All 35 API requests were read-only;
no mutation request occurred.

The generated password appeared in neither argv, process environment, browser
logs, evidence, repository files, nor plaintext profile data. The protected
profile was removed after testing. The public runtime result is retained at
`/tmp/chipcoin-mainnet-bw-ops-001-remediation-20261006/runtime/`.

## Regressions

| Check | Result |
|---|---|
| Browser wallet unit suites | `89/89 PASS` across 15 files |
| TypeScript `tsc --noEmit` | `PASS` |
| Chrome production build | `PASS` |
| Firefox production build | `PASS` |
| Firefox ML-DSA runtime | `PASS` |
| Production bundle ML-DSA presence | `PASS` |
| Production bundle `unsafe-eval` | absent |
| Canonical `build-all.sh` | `PASS` |
| New Chrome vs diagnostic tree | byte-identical |
| New Firefox vs validated tree | byte-identical |
| Chromium named-artifact runtime | `PASS` |

No application or browser-wallet source file was changed by the remediation.
The release-finalization procedure must bind source/commit to the canonical
build, named artifact hashes, and the exact runtime-validated artifacts. This
evidence belongs to the existing SEC-REL finalization gates; no new gate was
created.

## Rehearsal Safety

The rehearsal was observed read-only after the Chromium retest. A/B/C were
converged at height 389, tip
`0000000d09e5d3c319f6e0d01f1e008a0793457aa115649c78794fe3c1768106`,
and cumulative work `85459792860`. All three reported reward registry count 2
and registry hash
`250181d631f01060457af722e0d794c0c5af7d173233338c522b849342526fbb`.
Both reward nodes remained inactive with warmup-complete epoch 4;
settlement count remained zero. SQLite quick/FK checks passed, both miners were
running, and `chipcoin-mainnet-rehearsal-monitor.service` was active. No
transaction or mutable operation was sent to the rehearsal.

## Evidence And Gate

Sanitized evidence and immutable artifact copies are under:

`/tmp/chipcoin-mainnet-bw-ops-001-20261006/`

Rebuild provenance, stale artifact copies, deterministic comparisons, and the
successful Chromium result are under:

`/tmp/chipcoin-mainnet-bw-ops-001-remediation-20261006/`

Firefox satisfies every behavioral assertion in `BW-OPS-001`; its rebuilt
artifact is byte-identical to the validated copy. Chromium passed the same
required clean-profile properties using the rebuilt named artifact. The RC
gate is now `PASS`. RC-blocking counts are 85 `PASS`, 6 `NOT_RUN`, 7
`PENDING_HEIGHT`, and 0 `FAIL`.

```text
CHROMIUM_VERSION = 153.0.8010.52
SOURCE_CODE_CHANGED = NO
NAMED_ARTIFACTS_REBUILT = PASS
NEW_CHROME_TREE_HASH = e21e975b13b555744ce3c6f473d0cc1370449411597e193c2b78beb55353a082
CHROME_MATCHES_DIAGNOSTIC_BUILD = YES
NEW_FIREFOX_TREE_HASH = adcbfd457cb7170ce1b3d1106655abc93d5e0dff131efd4c9912ca6441056bb6
FIREFOX_MATCHES_VALIDATED_ARTIFACT = YES
FIREFOX_RETEST_REQUIRED = NO
CHROMIUM_NAMED_ARTIFACT_LOADED = PASS
CHROMIUM_CLEAN_INSTALL = PASS
CHROMIUM_EXTENSION_STARTUP = PASS
CHROMIUM_MAINNET_PQ_CREATE = PASS
CHROMIUM_PERSISTENCE = PASS
CHROMIUM_NETWORK_SWITCH = PASS
CHROMIUM_API_IDENTITY = PASS
SECRET_HYGIENE = PASS
BW_OPS_001 = PASS
BROWSER_RC_BLOCKER = NO
RC_STATE = 85_PASS_6_NOT_RUN_7_PENDING_HEIGHT_0_FAIL
```
