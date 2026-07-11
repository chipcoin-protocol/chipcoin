# Browser Wallet

## Purpose

The Chipcoin browser wallet is a minimal Chrome and Firefox extension for Chipcoin development networks.

Post-quantum CHCQ signing is intentionally not enabled in the browser wallet
yet. The extension recognizes CHCQ addresses for validation/API compatibility,
but it blocks CHCQ recipients in the Send flow and does not generate CHCQ wallet
keys or v2 PQ spends. Browser-generated CHCQ signatures must verify against the
node consensus backend before CHCQ sending is exposed in the extension.

When CHCQ support is later added, the browser wallet must warn that deterministic
ML-DSA signing is experimental testnet functionality and is not a substitute for
hardware-isolated key storage or a clean signing device.

It currently supports:

- wallet creation
- wallet recovery from a saved recovery phrase
- private key import
- encrypted local persistence
- address display
- balance and history loading from the node HTTP API
- local transaction build, sign, and broadcast
- CHCQ address recognition for testnet API compatibility, with CHCQ sending
  disabled until browser PQ signing is complete
- network switching between `devnet` and the public `testnet` candidate

## Prerequisites

- Node.js 20+
- npm

## Install Dependencies

```bash
cd apps/browser-wallet
npm install
```

## Build

Chrome:

```bash
npm run build:chrome
```

Firefox:

```bash
npm run build:firefox
```

Firefox release candidate with Mozilla lint:

```bash
npm run release:firefox
```

Both:

```bash
./build-all.sh
```

Outputs:

- `dist-chrome`
- `dist-firefox`
- `build/browser-wallet/chipcoin-browser-wallet-firefox-unsigned.xpi`

## Load In Browser

Chrome:

1. Open `chrome://extensions`
2. Enable Developer mode
3. Click `Load unpacked`
4. Select `apps/browser-wallet/dist-chrome`

Firefox:

1. Open `about:debugging#/runtime/this-firefox`
2. Click `Load Temporary Add-on...`
3. Select `apps/browser-wallet/dist-firefox/manifest.json`

## Firefox Normal Installable Package

Firefox Release and Beta require Mozilla signing before an `.xpi` can be
installed normally from a file or website. The repository can build the package,
but a normal installable Firefox artifact must be signed through AMO as an
unlisted extension.

Build and package:

```bash
cd apps/browser-wallet
npm run release:firefox
```

Without AMO credentials, this creates:

```text
build/browser-wallet/chipcoin-browser-wallet-firefox-unsigned.xpi
```

That unsigned package is not suitable for normal Firefox Release/Beta users.
To produce the self-distributed signed package:

```bash
AMO_JWT_ISSUER=... AMO_JWT_SECRET=... npm run release:firefox
```

The signed `.xpi` emitted by `web-ext sign --channel unlisted` can then be
hosted as the public Firefox wallet download.

The Firefox manifest uses the stable extension id `browser-wallet@chipcoinprotocol.com`.
Do not change this id after public release, because Firefox uses it as part of
the extension identity and storage namespace.

The Firefox release manifest intentionally uses narrow host permissions:

- `https://testnet-api.chipcoinprotocol.com/*`
- `https://api.chipcoinprotocol.com/*`
- `http://127.0.0.1/*`
- `http://localhost/*`

This keeps the official Mozilla package review-friendly. Arbitrary remote node
APIs are not supported by the Firefox release package unless they are added to
the manifest and reviewed.

`web-ext lint` may report `UNSAFE_VAR_ASSIGNMENT` warnings from React's bundled
DOM runtime in `assets/messages-*.js`. The wallet source does not use
`dangerouslySetInnerHTML`, direct `innerHTML`, `eval`, or dynamic code
generation; treat those warnings as AMO review notes rather than wallet source
findings.

## First Use

Open the popup and choose one of:

- `Create`
- `Recover`
- `Import key`

Behavior:

- `Create` generates a local Chipcoin recovery phrase, asks you to confirm backup, then encrypts the wallet in extension storage
- `Recover` restores the same wallet deterministically from that recovery phrase
- `Import key` remains available as a fallback for advanced users using raw private key hex

## Networks

Supported networks:

- Testnet public candidate: default endpoint `https://testnet-api.chipcoinprotocol.com`
- Devnet: explicit legacy/development endpoint `https://api.chipcoinprotocol.com`

The testnet default is a public wallet-safe API. It exposes only wallet reads
and transaction submission, not raw node internals. Operators can still override
the endpoint to a local/private node API, for example `http://127.0.0.1:28081`.

Never expose node HTTP `28081` publicly. Expose P2P `28444` only when operating a public testnet peer.

Do not use `https://explorer.chipcoinprotocol.com/api/testnet` as a wallet endpoint. The explorer proxy is readonly and is not suitable for `POST /v1/tx/submit` or other wallet send operations.

The Chrome/dev manifest remains broad enough for arbitrary operator endpoints.
The Firefox release manifest is narrower for AMO review and supports the public
Chipcoin wallet APIs plus local node endpoints only. Some browsers may still
show or require host permission approval when the extension is installed or
updated.

## Connect To A Node

The browser wallet uses a fallback endpoint from the repository `.env` at build time:

- `BROWSER_WALLET_DEFAULT_NODE_ENDPOINT`

In `.env.example`, that fallback is set to the public wallet-safe testnet API:

- `https://testnet-api.chipcoinprotocol.com`

Public testnet endpoints are provided for convenience and may change or become unavailable.

To use a different node or switch network:

1. Open the wallet popup
2. Go to `Settings`
3. Choose `Devnet` or `Testnet`
4. Confirm or change the Node API URL
5. Save

Behavior:

- the fallback default is used on first run only
- the user's chosen endpoint is persisted afterward
- manual override in the UI remains available at any time, but Firefox release builds can only reach hosts allowed by the Firefox manifest
- the wallet verifies both `/v1/health` and `/v1/status` before saving a new endpoint
- the wallet rejects endpoints on the wrong network
- submitted transaction state and wallet data cache are stored under network-scoped keys
- the Overview and Settings screens now show an explicit connection state and message for the saved endpoint
- the Send screen blocks transaction submission when the connected node reports the wrong network

If the node is remote, allow the wallet origin through `CHIPCOIN_HTTP_ALLOWED_ORIGINS`.

## Testnet Wallet Endpoints

Recommended public setup for normal users:

1. Open the browser wallet Settings screen.
2. Select `Testnet`.
3. Use the default `Public Testnet API` endpoint:

```text
https://testnet-api.chipcoinprotocol.com
```

Operator/local-node setup:

1. Join testnet with a local node using the fast-join runbook.
2. Keep HTTP local-only, for example `127.0.0.1:28081`.
3. Open the browser wallet Settings screen.
4. Select `Testnet`.
5. Use `http://127.0.0.1:28081` as the Node API URL.
6. Save and confirm Overview shows active network `Testnet` and connected network `testnet`.

Verification commands:

```bash
curl -s https://bootstrap.chipcoinprotocol.com/v1/peers?network=testnet | jq
curl -s https://explorer.chipcoinprotocol.com/api/testnet/v1/status | jq
curl -s https://testnet-api.chipcoinprotocol.com/v1/status | jq
curl -s http://127.0.0.1:28081/v1/status | jq
```

The explorer command is for status comparison only. Do not configure the wallet to use the explorer API as its node endpoint.

Public service boundaries:

- `explorer.chipcoinprotocol.com` is readonly explorer API and UI.
- `bootstrap.chipcoinprotocol.com` is P2P peer discovery only.
- `testnet-api.chipcoinprotocol.com` is the wallet-safe testnet API.
- local node HTTP remains private/operator-only.

## Endpoint Failure Modes

The wallet now distinguishes these common cases more explicitly:

- invalid endpoint
  - the URL is missing or malformed
- unreachable endpoint
  - the node is offline, the host/port is wrong, or the request timed out
- browser-blocked endpoint
  - the browser may block the request because of CORS, HTTPS, or mixed-content rules
- wrong network
  - the endpoint answered, but not on the expected network
- readonly explorer proxy
  - the wallet endpoint was pointed at an explorer/API proxy that cannot submit transactions
- blocked public wallet API path
  - `testnet-api.chipcoinprotocol.com` only exposes allowlisted wallet-safe paths
- stale saved endpoint
  - the wallet keeps the saved endpoint, but Overview and Settings show that it is currently unreachable

The browser cannot always distinguish a pure network outage from a CORS or mixed-content block. In those cases the wallet says so directly instead of pretending the error is more specific than it really is.

## HTTP / HTTPS / CORS Reality

Practical rules:

- use a full `http://` or `https://` URL
- if the wallet is loaded on an `https://` extension/page context and the node is only reachable over insecure HTTP in a way the browser treats as mixed content, the request may be blocked
- if the node is remote, `CHIPCOIN_HTTP_ALLOWED_ORIGINS` must allow the browser wallet origin
- if the node returns non-JSON or an unexpected proxy/login page, the wallet now reports that as an invalid node API response

When the endpoint is saved but unreachable, the wallet does not silently invent a healthy connection. It shows the last known endpoint and marks the node connection as unavailable until refresh succeeds again.

## When The Node Endpoint Moves

If you move the node API to a different host or port:

1. open the wallet popup
2. go to `Settings`
3. replace the saved Node API URL
4. save and confirm the wallet reports a connected node state again

If the old endpoint is still saved, the wallet stays usable locally but address/balance/history refresh will reflect the saved endpoint until you update it.

Stable API endpoints currently relied on by the wallet:

- `GET /v1/health`
- `GET /v1/status`
- `GET /v1/tip`
- `GET /v1/address/<address>`
- `GET /v1/address/<address>/utxos`
- `GET /v1/address/<address>/history`
- `GET /v1/tx/<txid>`
- `POST /v1/tx/submit`

The wallet expects JSON errors in the form:

- `{"error": {"code": "<stable_code>", "message": "<human_message>"}}`

## Storage Model

The wallet stores secrets only in browser extension local storage.

High-level model:

- the secret payload is encrypted locally with the user password
- seed-based wallets store the encrypted recovery phrase and derive account `0` deterministically
- private-key imports store the encrypted private key directly
- no remote backup or cloud sync is implemented
- wallet identity is shared across devnet and testnet; runtime cache and submitted transaction tracking are network-scoped
- switching networks never reuses cached history or submitted transaction state from the other network
- legacy devnet-only cache keys are read only as devnet fallback data, then newly refreshed data is written to devnet-scoped keys

The current recovery phrase format is Chipcoin-specific and is not documented as BIP39-compatible.

## Backup And Recovery

Recommended flow:

1. create a wallet
2. write down the recovery phrase
3. confirm it before continuing
4. keep the password and recovery phrase separate

Recovery flow:

1. reinstall or reload the extension
2. choose `Recover`
3. paste the saved recovery phrase
4. set a new local password

Fallback flow:

1. choose `Import key`
2. paste the raw private key hex
3. set a new local password

## Known Limits

- the current recovery phrase is not BIP39-compatible
- single-account flow only in this phase
- no multisig
- no multiple accounts UI yet
- no mainnet target in this public release
