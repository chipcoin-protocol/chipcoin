# Browser ML-DSA-44 Feasibility

The browser wallet now has an experimental, internal ML-DSA-44 backend for
interoperability testing only. It does not enable CHCQ wallet generation, CHCQ
private-key import, CHCQ persistent storage, Send to CHCQ, or CHCQ spending.

## Backend

The preferred long-term target remains compiling the same vendored
`mldsa-native` C backend used by the node into WebAssembly. This environment did
not provide `emcc`, `clang`, or `wasm-ld`, so the spike uses
`@noble/post-quantum` as a browser feasibility backend.

Reasons for this choice:

- supports ML-DSA-44 / FIPS 204;
- MIT licensed;
- local package dependency, no CDN or remote code loading;
- no WebAssembly asset and no CSP change;
- works in headless tests and extension builds;
- deterministic key generation matches the Python `mldsa-native` backend;
- `ml_dsa44.internal.sign/verify` matches Chipcoin's raw 32-byte digest signing
  path byte-for-byte when `extraEntropy: false` is used.

The public FIPS wrapper in `@noble/post-quantum` formats messages before
signing. Chipcoin signs the v2 transaction digest directly, so browser code must
use the internal/raw-message mode for parity with the node.

## Feature Flag

`ENABLE_EXPERIMENTAL_BROWSER_MLDSA` defaults to `false`.

Tests opt in explicitly through `createExperimentalMlDsa44Backend({ enabled:
true })`. The default extension runtime does not import or initialize the
backend from wallet send paths.

## Files

- `apps/browser-wallet/src/crypto/mldsa44.ts`
- `apps/browser-wallet/tests/fixtures/mldsa44-browser-vector-1.json`
- `apps/browser-wallet/tests/unit/mldsa44.test.ts`
- `apps/browser-wallet/scripts/mldsa44-browser-sign-vector.mjs`
- `tests/wallet/test_mldsa44_browser_interop.py`

## Security Notes

- No private keys, seeds, or signatures are logged by the runtime backend.
- The frozen private key in the fixture is deterministic test-only material.
- The backend validates exact message, key, and signature lengths and throws
  typed errors for structural failures.
- No persistent PQ key storage is implemented.
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

## Preliminary Performance

`benchmarkMlDsa44Backend()` provides a lightweight test-only measurement of
initialization, key generation, signing, and verification. It uses small
iteration counts and has no timing thresholds, because CI machines and browsers
vary widely.

The current spike has no WASM size. The installed package footprint is local
development dependency data; production bundle size should remain unchanged
while the backend is not imported by extension entry points.

## Does Not Validate

- browser WASM signing;
- secure persistent PQ key storage;
- browser recovery phrase derivation for PQ keys;
- public-testnet networking;
- global chain-wide PQ statistics;
- production-load DoS resistance;
- the real height-30000 activation event itself.
