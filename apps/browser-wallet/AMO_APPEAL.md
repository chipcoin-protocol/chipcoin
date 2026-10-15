# Mozilla Add-ons Appeal: Chipcoin Wallet
## Context
Chipcoin Wallet is the official browser wallet for the open-source Chipcoin project.
The extension is intended for Chipcoin development networks only, currently devnet and testnet. It is not a Bitcoin wallet, Ethereum wallet, fiat wallet, exchange wallet,
trading product, investment product, or general-purpose cryptocurrency wallet.
Chipcoin testnet coins have no monetary value. They are used only for testing wallet, node, faucet, explorer, and testnet transaction functionality.
## Reason for Appeal
The add-on was disabled under the “Deceptive or misleading” acceptable use policy.
We believe this was a misunderstanding caused by insufficient listing clarity. The extension name “Chipcoin Wallet” may not have made it clear enough that this is an officia
wallet for the Chipcoin devnet/testnet ecosystem and not a wallet for unrelated assets or financial activity.
We are requesting review because the extension does not impersonate another product, does not claim support for third-party cryptocurrencies, does not offer trading or
investment functionality, and does not handle real-money assets.
## What the Extension Does
Chipcoin Wallet allows users to:
- create a local Chipcoin testnet wallet;
- recover a local Chipcoin testnet wallet from a recovery phrase;
- view a Chipcoin testnet address;
- query testnet balance and transaction history from a configured Chipcoin node API;
- build and sign Chipcoin testnet transactions locally;
- submit signed Chipcoin testnet transactions to a configured Chipcoin node API.
Private keys and recovery phrases are handled locally by the extension.
## What the Extension Does Not Do
Chipcoin Wallet does not:
- support Bitcoin, Ethereum, fiat currency, or third-party assets;
- provide exchange, swap, trading, staking, lending, or investment services;
- claim that testnet coins have monetary value;
- collect analytics or tracking data;
- transmit private keys or recovery phrases to any server;
- ask users to deposit real funds;
- impersonate another wallet, exchange, or financial service.
## Security and Privacy Model
Wallet secrets are stored locally in browser extension storage and encrypted with the user’s password.
Private keys and recovery phrases are never transmitted to Chipcoin servers.
The extension connects only to configured Chipcoin node API endpoints to read network state, balances, UTXOs, transaction history, and to submit already-signed transactions.
The extension declares no data collection in the Firefox manifest.
Host permissions have been reduced to official Chipcoin development network APIs and local node endpoints.
## Review-Friendly Listing Text We Intend To Use
Name:
Chipcoin Testnet Wallet
Summary:
Official browser wallet for the Chipcoin devnet/testnet. Testnet coins have no monetary value.
Description:
Chipcoin Testnet Wallet is the official browser wallet for the open-source Chipcoin development networks.
It supports Chipcoin devnet and testnet only. It is not a Bitcoin, Ethereum, fiat, exchange, trading, investment, or general-purpose cryptocurrency wallet. Testnet coins hav
no monetary value.
The wallet can create or recover a local Chipcoin testnet wallet, show the testnet address, read balances and transaction history from a configured Chipcoin node API, build
and sign transactions locally, and submit signed transactions to the configured node.
Private keys and recovery phrases are stored only in the browser extension’s local storage, encrypted with the user’s password. They are not transmitted to Chipcoin servers.
This extension is intended for Chipcoin testnet users, developers, and node operators.
Privacy Policy:
Chipcoin Testnet Wallet does not collect, sell, or share personal data.
The extension stores wallet data locally in browser extension storage. Private keys and recovery phrases are encrypted locally with the user’s password and are never sent to
Chipcoin servers.
The extension connects only to the configured Chipcoin node API in order to read network status, balances, UTXOs, transaction history, and to submit signed transactions.
Requests may include the user’s Chipcoin testnet address or signed transaction data.
No analytics, tracking, advertising, or third-party telemetry are included.
## Reviewer Testing Notes
To test the extension:
1. Install the extension.
2. Choose “Create new wallet”.
3. Confirm the recovery phrase backup.
4. Set a password.
5. The wallet opens on the public Chipcoin testnet endpoint.
6. The generated address is a Chipcoin testnet address.
7. Balance and transaction history are read from the Chipcoin testnet API.
8. Any transaction signing is performed locally before submission.
No real funds or third-party assets are involved.
## Source Code
The project is open source:
https://github.com/chipcoin-protocol/chipcoin
Browser wallet source:
https://github.com/chipcoin-protocol/chipcoin/tree/main/apps/browser-wallet
## Requested Outcome
We respectfully request that Mozilla reconsider the permanent disablement.
If the issue is naming or listing clarity, we are willing to rename the extension to “Chipcoin Testnet Wallet” and update the public listing, summary, description, privacy
policy, reviewer notes, and screenshots to make the testnet-only scope explicit.
If Mozilla identified a specific behavior or code path that appears deceptive or misleading, please provide details so we can correct it.
