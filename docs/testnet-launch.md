# Testnet Launch Notes

This is a historical Testnet launch note. New installations now select Mainnet
through the setup wizard; choose Testnet explicitly to use this network. Use
the Testnet operator runbook for current copy/paste setup commands:

- `docs/testnet.md`

Current boundaries:

- public P2P port: `28444/tcp`
- local-only HTTP API: `127.0.0.1:28081`
- devnet remains separate and available as fallback
- public firewall/router rules should expose only `28444/tcp`
- do not expose `28081/tcp` directly to the internet

Validated internal-to-public-candidate state:

- three real nodes synced on `chipcom`, `tobia`, and `tilt`
- reward nodes registered and auto-renewing
- consecutive reward epochs closed with all three reward nodes paid
- conservative testnet miner defaults are enabled in the repo

Public services still to define before a broader announcement:

- official bootstrap peers or seed service
- snapshot publisher and signer keys
- explorer endpoint
- faucet funding policy
- release tag and upgrade policy
