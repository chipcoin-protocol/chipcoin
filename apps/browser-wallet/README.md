# Chipcoin Browser Wallet

Target network:
- `devnet`
- `testnet`

Supported browsers:
- Chrome
- Firefox

CHCQ status:

| Status | Browser wallet behavior |
| --- | --- |
| Live now | CHCQ address recognition, CHCQ labels, transaction scheme visibility from API metadata, receive/address display badges, and CHCQ watch-only balance/history tracking |
| Scheduled | Testnet consensus activation at height `20000` for CHCQ outputs and v2 wallet spends |
| Not yet available | Browser-side ML-DSA signing, CHCQ wallet generation, CHCQ spending, and Send to CHCQ recipients |

Before activation, testnet consensus rejects CHCQ outputs and CHCQ spends. After
activation, the browser wallet will still block CHCQ sending until the full
ML-DSA browser signing path is implemented and verified against the node
consensus backend. Watch-only CHCQ tracking stores only public addresses and
optional local labels; it does not make CHCQ funds browser-spendable.

## Testnet Activation Rescheduled

Testnet CHCQ/v2 wallet-spend activation was rescheduled from height `30000` to
height `20000` after completion of the activation readiness suite, smoke
command, browser parity/interoperability work, dress rehearsal, operational
readiness dashboard, and PQ audit. This is a mandatory testnet consensus
upgrade for validating nodes before height `20000`. It does not change CHCQ
addresses, keys, signatures, transaction serialization, or browser wallet
send/signing behavior. Nodes that keep the old `30000` schedule can diverge at
the first block containing PQ activity below height `30000`.

Build commands:
- `npm run build:chrome`
- `npm run build:firefox`
- `npm run lint:firefox`
- `npm run package:firefox`
- `npm run package:firefox:sources`
- `npm run release:firefox`

Install:
- Chrome: build with `npm run build:chrome`, open `chrome://extensions`, enable Developer mode, then `Load unpacked` and select `apps/browser-wallet/dist/`
- Firefox: build with `npm run build:firefox`, open `about:debugging#/runtime/this-firefox`, click `Load Temporary Add-on...`, then select `apps/browser-wallet/dist/manifest.json`

Firefox normal install:
- Firefox Release/Beta requires Mozilla signing for normal `.xpi` installation.
- Build, lint, and package the Firefox extension:

```bash
npm run release:firefox
```

- Without AMO credentials this creates `build/browser-wallet/chipcoin-browser-wallet-firefox-unsigned.xpi`, useful only for test/dev installs.
- To create a normal installable self-distributed package, set AMO credentials and rerun:

```bash
AMO_JWT_ISSUER=... AMO_JWT_SECRET=... npm run release:firefox
```

- Upload the signed `.xpi` produced in `build/browser-wallet/` to the website downloads area.
- Mozilla Add-ons may request source code for generated/minified builds. Create
  the AMO source archive with:

```bash
npm run package:firefox:sources
```

- Upload `build/browser-wallet/chipcoin-browser-wallet-firefox-0.1.0-source.zip`
  to the source code field for the matching AMO version.
- The Firefox manifest uses the stable extension id `browser-wallet@chipcoinprotocol.com`; do not change it after public release or users will get a different wallet storage namespace.
- The Firefox release manifest intentionally limits host permissions to the public Chipcoin wallet APIs and local node endpoints. Arbitrary remote node APIs are not supported by the official Mozilla package unless they are added to the manifest and reviewed.
- Current `web-ext lint` may report `UNSAFE_VAR_ASSIGNMENT` warnings from React's bundled DOM runtime in `assets/messages-*.js`. The wallet source does not use `dangerouslySetInnerHTML`, direct `innerHTML`, `eval`, or dynamic code generation.

Connect to a node:
- Open `Settings`
- The first-run fallback default comes from `BROWSER_WALLET_DEFAULT_NODE_ENDPOINT` in the repo `.env`
- In `.env.example`, testnet defaults to the public wallet-safe API at `https://testnet-api.chipcoinprotocol.com`
- Devnet remains available as an explicit alternative and uses `https://api.chipcoinprotocol.com`
- Operators can override testnet to a local node API such as `http://127.0.0.1:28081`
- Do not use the readonly explorer API as a wallet endpoint
- Firefox official builds allow only the public Chipcoin wallet APIs plus `localhost`/`127.0.0.1` node APIs. Chrome/dev builds may be configured more broadly.
- After first run, the selected endpoint is persisted in extension storage
- If the node is remote, set `CHIPCOIN_HTTP_ALLOWED_ORIGINS` on the node to allow the wallet origin
- The wallet verifies `/v1/health` and `/v1/status` before saving a new endpoint
- The wallet rejects endpoints on the wrong network
- Overview and Settings show an explicit node-connection state for the currently saved endpoint

Common endpoint failures:
- invalid URL: the value is missing or malformed
- unreachable endpoint: the node is offline, the host/port is wrong, or the request timed out
- browser-blocked endpoint: CORS, HTTPS, or mixed-content rules may prevent the request
- stale saved endpoint: the endpoint stays saved, but the wallet reports it as unavailable until it responds again

Create, recover, or import:
- Fresh install opens onboarding automatically
- Choose `Create new wallet`, `Recover wallet`, or `Import private key`
- `Create new wallet` generates a local recovery phrase, requires you to acknowledge backup, then encrypts the wallet in extension storage
- `Recover wallet` recreates the same wallet deterministically from the saved recovery phrase
- `Import private key` remains available as a fallback path for advanced users

Export private key:
- Unlock the wallet
- Open `Backup`
- Read the warning, confirm it, and reveal the key only when needed
- Copy is user-triggered only

Export recovery phrase:
- Seed-based wallets can reveal the recovery phrase from `Backup`
- The phrase is shown only after explicit confirmation
- Private-key-imported wallets do not have a recovery phrase to export

Recover from seed phrase:
- Install or reload the extension
- Open onboarding
- Choose `Recover wallet`
- Paste the saved recovery phrase and set a new password

Recover from private key fallback:
- Install or reload the extension
- Open onboarding
- Choose `Import private key`
- Paste the private key hex and set a new password

Reset / remove:
- Open `Settings`
- Click `Remove wallet`
- This clears the encrypted wallet, the active session, submitted transaction cache, and the local wallet snapshot

Included in this milestone:
- local wallet creation and import
- seed-based wallet creation and deterministic recovery
- encrypted wallet storage
- background-owned unlock session
- Phase 2 API client wiring
- read-only address, balance, history, and node-health flows
- local transaction build, sign, serialize, and submit aligned with the current Chipcoin wallet primitives
- CHCQ address recognition for API/UI compatibility, while CHCQ sending and browser-side PQ signing remain disabled
- CHCQ labels for receive/address display and transaction metadata returned by the node API
- CHCQ watch-only balance/history tracking without keys or signing
- submitted transaction tracking and confirmation polling

Manual smoke test:
1. Build and load the extension in Chrome or Firefox
2. Create a wallet or import an existing private key
3. Confirm the wallet shows:
   - address
   - connected network `testnet`
   - balance data from your configured node API
4. Submit a small transaction to a known Chipcoin address
5. Check the returned txid through your node API or explorer tooling
6. Confirm the transaction later appears in confirmed history

Not included:
- multisig
- multiple accounts
- browser-side CHCQ wallet generation or PQ transaction signing
- CHCQ spending from watch-only addresses
- mainnet support

Storage model:
- wallet secrets stay in browser extension local storage only
- the stored secret is encrypted with the user password
- seed-based wallets store the encrypted recovery phrase and derive account `0` deterministically
- private-key-imported wallets store the encrypted private key directly

Current limitation:
- the recovery phrase format is Chipcoin-specific for now and is not advertised as BIP39-compatible
