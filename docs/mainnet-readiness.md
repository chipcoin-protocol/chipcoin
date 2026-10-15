# Mainnet Readiness Notes

This file tracks technical reminders that must be resolved before any mainnet
genesis or public launch. These are not testnet operations notes.

See also `docs/security-hardening.md` for the security hardening tracker and
pre-mainnet risk register.

## Operational Roadmap

- Height `12000` reward-fee driver checkpoint:
  - verify that testnet switches from the historical registered reward-node
    count to `fee_reward_node_count`
  - compare `registered_reward_node_count`, `fee_reward_node_count`, and
    `active_reward_node_count` on all upgraded consensus nodes
  - confirm reward-node registration and renewal transactions are still
    accepted with the expected fees
- Height `12000` retarget checkpoint:
  - measure average and median block intervals after the retarget
  - confirm the new difficulty moves the chain closer to the `600s` target
  - keep tracking miner concentration and top miner share over rolling
    100-block windows
- Height `20000` PQ activation preparation:
  - keep all consensus-critical nodes on the height-`20000` PQ release
  - run preflight and postdeploy checks before activation
  - rehearse first CHCQ output, first CHCQ spend, mempool handling, mining, and
    explorer visibility before the live activation window
- Snapshot bootstrap hardening:
  - publish signed snapshots only for serious/public environments
  - use enforced trust mode for mainnet bootstrap paths
  - keep snapshot retry-loop protection and local bootstrap locks enabled
- Reward diagnostics:
  - expose why a reward node is active or inactive
  - expose why a node is rewarded or not rewarded in an epoch
  - show current fee, fee driver count, and expected post-activation fee driver
    behavior clearly in CLI/API/reporting
- Operator onboarding:
  - make the setup wizard production-grade for fresh nodes
  - include dependency checks, Docker setup, wallet creation/import, snapshot
    bootstrap, node/miner/reward-node setup, and a final verification summary
- Public reporting:
  - improve explorer and private reports with mining speed, expected retarget,
    PQ countdown, reward-node active/recent/stale state, and miner labels
- Security and network hardening:
  - keep raw node HTTP on localhost or behind a controlled reverse proxy
  - publish only stable reachable public peers
  - continue runtime, sync, mempool, and peer-misbehavior review before mainnet

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

### Frozen Mainnet Economic Profile

The following values are frozen for the mainnet genesis candidate:

- `600` second target block time with no legacy schedule
- `1,000` block retarget window
- initial compact target `0x1d1399ad`, calibrated from the three-miner public
  testnet hashrate to target approximately `390` seconds per block during the
  first retarget window
- `100` block reward epochs and coinbase maturity
- `111,000` block halving interval
- `11,000,000 CHC` hard maximum scheduled supply
- `50 CHC` initial miner subsidy per block
- `50 CHC` initial reward-node pool per epoch
- no treasury and no recovery or miner redistribution of undistributed node
  rewards
- reward-node activation at height `1,000`, two-epoch warmup, and at most `25`
  rewarded nodes per epoch
- adaptive registration and renewal fees driven by recently renewed reward
  nodes from genesis
- PQ transaction support, reward epoch seed v2, and special-node signature v2
  active from genesis
- only ML-DSA-44 CHCQ outputs and version-2 ML-DSA-44 standard spends are
  valid; legacy CHC outputs and secp256k1 wallet spends are not part of mainnet
- reward-node owner and attestation signatures use ML-DSA-44 (`scheme_id=10`)
  from genesis

The scheduled subsidy reaches the hard cap at height `643,297` and becomes zero
from height `643,298`. Node rewards that are not distributed remain permanently
unissued, so materialized circulating supply may finish below the hard maximum.
The initial target is intentionally faster than the steady-state `600` second
target; if launch hashrate remains comparable to the measured testnet hashrate,
the first retarget moves subsequent blocks toward `600` seconds.

## PQ Defaults For Mainnet

- Make the final mainnet PQ policy explicit and active from genesis:
  - accept CHCQ outputs and version-2 ML-DSA-44 spends from height `0`
  - do not carry the testnet height-`20000` activation exception into mainnet
  - add consensus tests that reject any mainnet configuration with a delayed or
    legacy PQ activation schedule
- Make PQ miner provisioning the production default:
  - have the setup wizard generate or import an ML-DSA-44 miner wallet by
    default for mainnet
  - mount the selected miner wallet read-only and verify its derived payout
    address before starting the miner
  - automated coverage now exercises PQ coinbase creation, maturity,
    multi-input spending, fees, restart persistence, multi-node acceptance,
    reorgs, and snapshot delta synchronization under the mainnet policy
  - do not expose a legacy-miner option on mainnet
- Make the browser wallet fully mainnet-ready for PQ operation:
  - create and import ML-DSA-44 wallets, encrypt seeds locally, lock/unlock, and
    recover deterministically in a separate browser profile
  - support PQ-to-PQ and multi-input PQ transactions with clear fee, maturity,
    rejection, mempool, and confirmation feedback; mainnet must reject legacy
    recipients
  - the network selector now includes mainnet, validates the endpoint-reported
    network, isolates network-scoped state, and refuses mainnet for legacy
    wallets
  - signed-login messages support the network-bound mainnet domain and
    ML-DSA-44 scheme `10`; legacy testnet login remains compatible
  - use the production mainnet wallet-safe API and correct explorer transaction
    links by default
  - complete Chrome and Firefox packaging, signing, update, backup, and recovery
    drills without losing extension storage
- Make CHCQ the default reward payout for new mainnet reward nodes:
  - provision separate control and payout wallets rather than assuming one
    wallet serves both roles
  - register the reward node with a CHCQ payout address and verify reward
    settlement, coinbase materialization, maturity, and spending end to end
  - display owner/attestation scheme and payout scheme separately in CLI, API,
    explorer, setup output, and operational reports
  - ensure the setup wizard funds and verifies the control wallet before
    registration and keeps all wallet files outside version control with
    owner-only permissions
- Resolve reward-node key lifecycle before genesis:
  - decide whether owner and attestation signatures remain ECDSA at launch or
    become scheme-aware and support ML-DSA-44
  - do not describe reward nodes as fully post-quantum while control or
    attestation signatures still require secp256k1
  - add an authenticated payout-update or key-rotation transaction so operators
    can move to a new CHCQ payout without abandoning the node id, registration
    history, warmup state, or eligibility
  - test unauthorized updates, duplicate keys, invalid CHCQ addresses, epoch
    boundaries, reorgs, snapshots, and mixed legacy/PQ reward registries
- Add a mainnet PQ release gate that proves, on multiple independent nodes:
  - identical chain tip and acceptance of the first PQ blocks
  - PQ miner coinbase payouts and reward-node CHCQ payouts
  - browser-created ML-DSA transactions mined and spendable after confirmation
  - zero unexpected PQ verification failures, rejects, orphan spikes, or
    consensus errors
  - reports and readiness tooling show PQ as active and browser ML-DSA signing
    as available, with no stale testnet-era messaging

Automated in-process coverage for the consensus/storage portion of this gate is
in `tests/node/test_mainnet_pq_end_to_end.py`. A final Docker rehearsal with
independent node, miner, reward-node, browser, API, and explorer processes is
still required before genesis.

Run the non-destructive Compose and wallet gate before that rehearsal:

```bash
scripts/mainnet-pq-preflight.sh \
  --compose-file docker-compose.yml \
  --env-file .env.mainnet
```

The setup wizard can now generate/import canonical ML-DSA-44 miner and reward
wallets for mainnet. Its mainnet profile intentionally starts with full sync
and no assumed public bootstrap or snapshot source.

## Snapshot Bootstrap

- Mainnet snapshots must be signed before publication.
- Mainnet nodes should use `--snapshot-trust-mode enforce` with known signer
  keys.
- Snapshot manifests should include accurate consensus metadata and signer
  pubkeys.
- Verify that importing a mainnet snapshot does not depend on testnet-only
  activation compatibility.
- Do not ship public mainnet snapshot bootstrap with implicit
  `--snapshot-trust-mode off`.
- Keep snapshot retry-loop protection enabled in Docker startup paths:
  - exponential backoff after failed manifest/download/import/validation
  - local bootstrap lock
  - local snapshot file reuse when checksum/metadata match

## Public Network Hygiene

- Publish only stable, reachable public peers.
- NAT/private nodes should not announce themselves as public peers.
- Keep peer identity alias handling, manual peer preservation, and public peer
  filtering covered by tests.
- Keep hard P2P frame-size limits in transport before reading peer-controlled
  payload lengths. The current cap is `8_000_000` bytes.

## Economics And Supply

- Re-check final mainnet emission schedule before genesis.
- Confirm expected time to max supply under the final `600s` block target.
- Confirm node reward epoch length and miner subsidy cadence are coherent with
  the target block time.

## Mempool Policy

- Replace count-only sizing with explicit byte or weight limits before mainnet.
  The current testnet policy caps transaction count and transaction size, but
  does not expose a direct total mempool byte budget.
- Treat duplicate `reward_attestation_bundle` submissions as an expected
  idempotency case, not generic peer failure. Before mainnet, make duplicate
  bundle handling cheap and observable:
  - classify duplicates by `(epoch, window, submitter)` in logs and reports
  - avoid heavy validation/relay work when an equivalent bundle is already
    staged
  - do not penalize or ban peers aggressively for low-volume duplicate bundle
    relay
  - alert only when duplicate volume is high enough to create CPU, bandwidth, or
    mempool pressure
- Define and test saturation behavior:
  - which transactions are evicted first
  - whether fee rate, age, or dependency structure drives eviction
  - how the node behaves when a peer floods near-limit transactions
- Expose operator metrics in status/API:
  - transaction count
  - estimated serialized bytes
  - estimated weight units
  - configured mempool limit
  - eviction count or pressure signal
- Add regression tests for mempool limits, TTL expiry, eviction ordering, and
  restart persistence under a full mempool.

## Observability

- Keep server-side funnel metrics for downloads, snapshot bootstrap, public peer
  bootstrap, faucet usage, and wallet API usage.
- Avoid sending full wallet addresses to third-party analytics; use server logs
  or hashed/truncated identifiers where needed.

## Security Hardening Before Mainnet

- Keep wallet CLI key handling covered by regression tests:
  - wallet files are written with owner-only permissions
  - `wallet-address` does not print `private_key_hex`
  - commands that intentionally print private keys warn on stderr
- Keep special node transaction signatures v2-only on mainnet; devnet/testnet
  activate v2 at height 11111, and legacy v1 compatibility must not be enabled
  for mainnet.
- Keep reward epoch seed v2 enabled from genesis on mainnet. Devnet/testnet
  retain v1 compatibility before epoch 112, but mainnet must not enable legacy
  single-closing-block seed derivation.
- Before mainnet launch, verify seed policy from a synced node with:
  `curl -fsS http://127.0.0.1:28081/v1/rewards/epoch | jq '.seed'`.
  Mainnet must report `seed_version: 2`, a
  `chipcoin:reward-epoch-seed:v2:mainnet` domain, and a multi-block seed
  window.
- Review runtime/sync/mempool paths under adversarial peers and high load.
# Release-Candidate Maturity Boundary Gate

The exact runtime boundary remains required before the release candidate:

- mainnet consensus parameters, including maturity and difficulty, must remain unchanged;
- one immutable raw transaction must be submitted at candidate height 99 and rejected;
- the identical bytes, TXID, and signature must be submitted at candidate height 100 and accepted;
- this is a separate isolated rehearsal requirement and must not be inferred from unit tests.

Current long-running rehearsal classification: `NOT_RUN / REQUIRED_BEFORE_RC`.
