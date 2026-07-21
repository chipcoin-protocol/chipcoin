# Browser ML-DSA-44 Feasibility

The browser wallet now has an experimental, internal ML-DSA-44 backend for
interoperability testing only. It does not enable CHCQ wallet generation, CHCQ
private-key import, CHCQ persistent storage, Send to CHCQ, or CHCQ spending.

## Backend

The preferred long-term target remains compiling the same vendored
`mldsa-native` C backend used by the node into WebAssembly. This environment did
not provide `emcc`, `clang`, or `wasm-ld`, so the spike uses
`@noble/post-quantum` as a browser feasibility backend. The package is pinned
to exact version `0.6.1` in `apps/browser-wallet/package.json` and
`package-lock.json`.

Reasons for this choice:

- supports ML-DSA-44 / FIPS 204;
- MIT licensed;
- local package dependency, no CDN or remote code loading;
- no WebAssembly asset and no CSP change;
- works in headless tests and extension builds;
- deterministic key generation matches the Python `mldsa-native` backend;
- `ml_dsa44.internal.sign/verify` matches Chipcoin's raw 32-byte digest signing
  path byte-for-byte when `extraEntropy: false` is used.

The adapter imports only `@noble/post-quantum/ml-dsa.js`. No other wallet file
may import Noble ML-DSA directly.

The public FIPS wrapper in `@noble/post-quantum` formats messages before
signing. Chipcoin calculates the transaction signing payload first, including
the v2 network domain separator, hashes it to a 32-byte signing digest, and
then signs that digest directly. Browser code must therefore use the
internal/raw-message mode for parity with the node:

```text
ml_dsa44.internal.sign(digest, privateKey, { extraEntropy: false })
ml_dsa44.internal.verify(signature, digest, publicKey)
```

This internal Noble API is intentionally isolated behind
`apps/browser-wallet/src/crypto/mldsa44.ts`, whose public methods are named
`signDigest` and `verifyDigest` to avoid confusing raw digest signing with
application message signing.

## Feature Flag

`ENABLE_EXPERIMENTAL_BROWSER_MLDSA` defaults to `false`.

Tests opt in explicitly through `createExperimentalMlDsa44Backend({ enabled:
true })`. The default extension runtime does not import or initialize the
backend from wallet send paths.

## Files

- `apps/browser-wallet/src/crypto/mldsa44.ts`
- `apps/browser-wallet/tests/fixtures/mldsa44-browser-vector-1.json`
- `apps/browser-wallet/tests/unit/mldsa44.test.ts`
- `apps/browser-wallet/scripts/mldsa44-browser-sign-vector.ts`
- `apps/browser-wallet/scripts/inspect-mldsa44-bundle.mjs`
- `apps/browser-wallet/scripts/run-mldsa44-browser-test.mjs`
- `apps/browser-wallet/tests/browser/mldsa44_browser_harness.ts`
- `tests/wallet/test_mldsa44_browser_interop.py`

## Security Notes

- No private keys, seeds, or signatures are logged by the runtime backend.
- The frozen private key in the fixture is deterministic test-only material.
- The backend validates exact message, key, and signature lengths and throws
  typed errors for structural failures.
- Best-effort zeroization is used for local benchmark buffers. JavaScript does
  not guarantee complete memory erasure because engines may copy or move typed
  arrays internally.
- No persistent PQ key storage is implemented.
- The backend does not use `localStorage`, `sessionStorage`, IndexedDB, or
  structured clone for private keys.
- No migration, recovery phrase mapping, backup, import, or Send UI is enabled.
- No worker is used yet. The API is asynchronous so a later worker-backed
  implementation can keep keygen/signing off the main thread.

## CSP And Build

The spike adds no `.wasm` file. It uses bundled JavaScript from
`@noble/post-quantum`, so Manifest V3 does not need `unsafe-eval`,
`wasm-unsafe-eval`, remote script permission, or a CDN.

Because the experimental backend is not imported by the production UI or
background entry points, Vite can keep it out of the Chrome and Firefox bundles
until the feature is explicitly wired in.

`npm run test:mldsa:bundle` inspects the built extension and fails if the
production bundle contains Noble ML-DSA references, unexpected `.wasm` assets,
Node runtime imports, CDN references, `eval`, `unsafe-eval`, or
`wasm-unsafe-eval`.

## Validation

The tests verify:

- initialization and repeated initialization;
- deterministic key generation from the Python fixture seed;
- exact public key, private key, and signature lengths;
- browser signature byte parity with Python `mldsa-native`;
- browser verification of a Python signature;
- Python verification of a browser-produced signature through a Node runner;
- rejection of altered signature, altered message, and wrong public key;
- typed errors for invalid lengths and disabled feature state.
- internal API presence, required function names, and exact Noble length
  constants;
- bundle exclusion while the feature flag is false.

## Browser Harness

`npm run test:mldsa:browser:firefox` builds a dedicated browser harness and
attempts to run it in Firefox headless through WebDriver BiDi. The harness runs
under a restrictive page CSP and verifies deterministic key generation,
`signDigest`, `verifyDigest`, the frozen Python signature, altered signature
rejection, altered digest rejection, wrong-public-key rejection, and lightweight
browser timings.

`npm run test:mldsa:browser:chromium` runs the same harness in Chrome or
Chromium headless through the Chrome DevTools Protocol. The dedicated GitHub
Actions job `browser-pq-chromium` runs this path on `ubuntu-latest` with
`npm ci`, unit tests, extension builds, bundle inspection, and the Chromium
harness. If a local machine does not have a Chromium/Chrome binary installed,
the script reports that condition explicitly instead of simulating a pass.

## Preliminary Performance

`benchmarkMlDsa44Backend()` provides a lightweight test-only measurement of
initialization, key generation, signing, and verification. It uses small
iteration counts and has no timing thresholds, because CI machines and browsers
vary widely.

The current spike has no WASM size. The installed package footprint is local
development dependency data; production bundle size should remain unchanged
while the backend is not imported by extension entry points.

Local measurements on 2026-07-21 are for orientation only.

Node.js `22.23.1`, 10 iterations:

```text
init: 0.001 ms
deterministic keygen average: 3.442 ms
signDigest average: 2.676 ms
verifyDigest average: 1.623 ms
10 signatures: 22.229 ms
10 verifications: 13.589 ms
```

Firefox `152.0.6` headless, WebDriver BiDi harness, 3 average iterations:

```text
init: 0 ms
deterministic keygen average: 2.333 ms
signDigest average: 5.333 ms
verifyDigest average: 3.333 ms
10 signatures: 50 ms
10 verifications: 29 ms
```

Browser timing fields are emitted by the browser harness when Firefox or
Chromium automation is available.

Chromium timing should be recorded from the `browser-pq-chromium` job output or
from a local machine with Chrome/Chromium installed by running:

```bash
cd apps/browser-wallet
npm run test:mldsa:browser:chromium
```

## Upgrade Procedure For @noble/post-quantum

1. Change the exact `@noble/post-quantum` version in `package.json`.
2. Reinstall with `npm install`.
3. Confirm the lockfile pins the intended version and license metadata.
4. Run `npm test`.
5. Run `npm run test:mldsa:bundle`.
6. Run the Firefox browser harness locally where available.
7. Run the Chromium browser harness locally or through the `browser-pq-chromium`
   GitHub Actions job.
8. Run Python/browser interop tests from the repository root.
9. Run Chrome and Firefox extension builds.
10. Inspect bundle and CSP output.
11. Reject the upgrade unless vector signatures and lengths remain unchanged or
    an explicit cryptographic review approves the difference.

The main breaking-change risk is Noble changing or removing the internal raw
digest API. Tests intentionally fail if `ml_dsa44.internal.sign`,
`ml_dsa44.internal.verify`, fixed lengths, or frozen vector outputs change.

## Does Not Validate

- browser WASM signing;
- secure persistent PQ key storage;
- browser recovery phrase derivation for PQ keys;
- public-testnet networking;
- global chain-wide PQ statistics;
- production-load DoS resistance;
- the real height-30000 activation event itself.
