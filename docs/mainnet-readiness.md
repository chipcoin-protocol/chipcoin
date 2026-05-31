# Mainnet Readiness Notes

This file tracks technical reminders that must be resolved before any mainnet
genesis or public launch. These are not testnet operations notes.

## Consensus Rules

- Do not carry testnet-only historical activation rules into mainnet.
- Mainnet must start from genesis with the final target block time and retarget
  policy. There should be no two-phase `legacy_target_block_time_seconds`
  schedule for mainnet unless a real future hard fork requires it.
- The current testnet compatibility rule exists only to preserve the already
  mined testnet chain:
  - before height `4500`: `300s` target block time
  - from height `4500`: `600s` target block time
- Before mainnet, add a consensus sanity test asserting that `MAINNET_PARAMS`
  has no legacy block-time schedule:
  - `target_block_time_activation_height == 0`
  - `legacy_target_block_time_seconds is None`

## Snapshot Bootstrap

- Mainnet snapshots must be signed before publication.
- Mainnet nodes should use `--snapshot-trust-mode enforce` with known signer
  keys.
- Snapshot manifests should include accurate consensus metadata and signer
  pubkeys.
- Verify that importing a mainnet snapshot does not depend on testnet-only
  activation compatibility.

## Public Network Hygiene

- Publish only stable, reachable public peers.
- NAT/private nodes should not announce themselves as public peers.
- Keep peer identity alias handling, manual peer preservation, and public peer
  filtering covered by tests.

## Economics And Supply

- Re-check final mainnet emission schedule before genesis.
- Confirm expected time to max supply under the final `600s` block target.
- Confirm node reward epoch length and miner subsidy cadence are coherent with
  the target block time.

## Observability

- Keep server-side funnel metrics for downloads, snapshot bootstrap, public peer
  bootstrap, faucet usage, and wallet API usage.
- Avoid sending full wallet addresses to third-party analytics; use server logs
  or hashed/truncated identifiers where needed.
