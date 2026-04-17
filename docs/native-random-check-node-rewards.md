# Native Random-Check Node Rewards

## Status

This document locks the native v1 direction for Chipcoin node rewards.

It supersedes earlier strategic assumptions that treated the manual payout stack as the product direction.

The current observer / batch / signing / preflight / manual submission tooling is now explicitly:

- experimental admin tooling
- devnet simulation infrastructure
- research and diagnostics support
- non-strategic

## Fixed Monetary Baseline

The following monetary policy remains fixed for this track:

- max supply: 11,000,000 CHC
- base unit: 1 CHC = 100,000,000 chipbits
- target block time: 5 minutes
- initial miner subsidy: 50 CHC per block
- initial node reward budget: 50 CHC per 100-block epoch
- halving interval: 111,000 blocks
- miner subsidy and node reward halve together
- no treasury
- hard cap clamp remains consensus-critical

## Node Types

### 1. Simple Full Node

A simple full node:

- can run from genesis
- does not need CHC to exist
- validates blocks
- relays transactions and blocks
- participates in network connectivity
- does not automatically receive node rewards

This preserves bootstrap openness and avoids forcing CHC ownership merely to run infrastructure.

### 2. Registered Reward Node

A registered reward node is a full node that has entered the on-chain reward registry.

It must have:

- node_id
- node public key
- payout address
- declared public host
- declared public port
- registration transaction
- registration fee
- renewal support
- reward eligibility lifecycle

Only registered reward nodes can receive protocol-native node rewards.

## Bootstrap Rules

Preferred bootstrap model:

- full nodes may run from genesis
- reward registry may be used as soon as an operator has CHC
- per-node warmup is the primary timing control
- a protocol-level activation height provides bootstrap safety

### NODE_REWARD_ACTIVATION_HEIGHT

Before activation height:

- full nodes run normally
- mining runs normally
- registry transactions may be allowed
- no node rewards are paid

From activation height onward:

- registered reward nodes that satisfy warmup and verification may receive epoch rewards

Default recommendation:

- keep a simple reward activation height
- rely primarily on per-node warmup, not a long global delay

## Registration Economics

v1 does not use staking.

Economic controls:

- registration fee
- renewal fee
- warmup delay
- anti-concentration rules
- random verification checks

Design goals:

- avoid free Sybil spam
- keep basic node operation free
- require CHC only for reward-registry participation
- avoid assuming every registered node must be profitable every epoch

## Epoch Model

- `EPOCH_LENGTH = 100` blocks
- `epoch_index = height // EPOCH_LENGTH`
- epoch-closing block height satisfies `(height + 1) % EPOCH_LENGTH == 0`

Each epoch has:

- a fixed node reward budget from the monetary schedule
- random candidate checks
- random verifier assignments
- attestation collection
- deterministic eligibility computation
- automatic on-chain settlement at epoch close

The node reward budget does not change dynamically based on node count.

## Reward Philosophy

The protocol must not inflate rewards to keep all nodes profitable.

Instead:

- epoch reward budget remains fixed
- verified nodes are derived through checks and rules
- if too many nodes qualify, only a deterministic capped subset is rewarded
- reward per winner stays meaningful
- no dust-style dilution

## Strategic Architecture

The chosen direction is protocol-native random-check settlement.

It uses:

- on-chain reward node registry
- deterministic pseudorandom candidate selection
- deterministic pseudorandom verifier committee selection
- compact signed verifier attestation carriage
- quorum-based pass/fail evaluation
- anti-concentration filters
- deterministic capped rewarded set if needed
- automatic on-chain epoch settlement

It explicitly does not use as the main model:

- miner inclusion proofs as the primary reward gate
- staking-backed VRF economics in v1
- observer-central manual payouts as end-state

## Verification Model

Raw network probing remains off-chain in execution.

Consensus and chain data should encode as much of the rest as possible:

- who should check whom
- which check window applies
- which signed attestation was produced
- what result was reported
- how quorum is evaluated
- how epoch eligibility is derived
- how settlement is computed

### Candidate Check Goals

Each check should verify at minimum:

- node reachable at declared endpoint
- correct protocol handshake
- correct network
- full-node behavior
- sync lag within threshold

Initial sync tolerance target:

- 4 to 5 blocks behind tip

## Reward-Node Registry Model

A registered reward node record must minimally include:

- node_id
- node public key
- payout address
- declared public host
- declared public port
- registration height
- last renewal height
- active / expired state

v1 recommendation:

- endpoint is declared in the registration metadata
- endpoint changes require an explicit renewal or update path
- consensus does not store raw probe logs
- consensus does need stable declared endpoint reference for check assignment and attestation consistency

## Epoch Seed

Use a seed that is fixed early enough to prevent late manipulation by settlement participants.

Recommended v1:

- `epoch_seed = H(previous_epoch_closing_block_hash || epoch_index || "reward-epoch-v1")`

Where:

- `previous_epoch_closing_block_hash` is the closing block hash of epoch `epoch_index - 1`

Reason:

- known before the current epoch starts
- stable across the epoch
- easy to test
- avoids using same-epoch settlement block data

## Active Reward-Node Set For Assignment

For epoch `E`, the assignment pool is the set of registry entries such that:

- registration valid and not expired at epoch start
- warmup completed by epoch start
- endpoint metadata present
- node not otherwise registry-disqualified

This pool is ordered deterministically by:

- `(node_id, payout_address)`

### Warmup

Use per-node warmup:

- `WARMUP_EPOCHS = 2`

A node becomes reward-eligible no earlier than:

- `current_epoch >= registration_epoch + WARMUP_EPOCHS`

## Candidate Selection

The v1 baseline must be stronger than one successful check.

Locked baseline:

- `TARGET_CHECKS_PER_EPOCH = 3`
- `MIN_PASSED_CHECKS_PER_EPOCH = 2`
- per-check quorum = `2 of 3`

To keep volume bounded:

- `CHECK_WINDOWS_PER_EPOCH = 10`
- each check window spans `10` blocks

Candidate assignment uses:

- `epoch_seed`
- `check_window_index`
- `candidate_node_id`

Recommended v1 behavior:

- each active reward node is assigned exactly `3` deterministic check windows per epoch if registry size permits
- assignments are derived from deterministic ranking, not from miner discretion

### Tiny-Registry Fallback

If the active reward-node set is too small to satisfy full baseline assumptions:

- devnet may enable a parameter-gated fallback
- fallback must be explicit in consensus params and diagnostics
- fallback is not the default baseline

Suggested fallback only if explicitly enabled:

- `MIN_ASSIGNED_CHECKS = 2`
- `MIN_PASSED_CHECKS = 2`
- reduced verifier committee only if 3 distinct verifiers cannot exist

## Verifier Selection

For each `(epoch_index, check_window_index, candidate_node_id)`:

- derive verifier ranking from:
  - `H(epoch_seed || check_window_index || candidate_node_id || verifier_node_id)`

Take the top-ranked distinct verifier nodes subject to:

- verifier != candidate
- verifier active and warmup-complete at epoch start
- verifier registry-valid
- verifier not otherwise disqualified

Recommended v1:

- `VERIFIER_COMMITTEE_SIZE = 3`
- `VERIFIER_QUORUM = 2`

If fewer than 3 valid verifiers exist:

- the check is marked insufficient committee
- it does not count as passed
- reduced-committee fallback must be explicit and parameter-gated

## Attestation Carriage Model

v1 should not default to one ordinary transaction per attestation.

Preferred v1 carriage model:

- a compact special transaction carrying multiple attestations:
  - `reward_attestation_bundle`

### `reward_attestation_bundle`

Purpose:

- compact carriage of many verifier attestations in one transaction

Consensus-visible fields:

- `kind = reward_attestation_bundle`
- `epoch_index`
- `bundle_window_index`
- `bundle_submitter_node_id`
- `attestation_count`
- `attestations_root`
- `attestations_payload`

Each attestation entry contains:

- `epoch_index`
- `check_window_index`
- `candidate_node_id`
- `verifier_node_id`
- `result_code`
- `observed_sync_gap`
- `endpoint_commitment`
- `concentration_key`
- `signature`

### Bundle Rules

These rules are locked for v1 and must be explicit in consensus params:

- `MAX_ATTESTATION_BUNDLES_PER_BLOCK`
- `MAX_ATTESTATIONS_PER_BUNDLE`
- `MAX_ATTESTATIONS_PER_VERIFIER_PER_WINDOW`

Baseline recommendation:

- keep all three tightly bounded on devnet
- choose values small enough to keep blocks and validation easy to inspect

Duplicate handling:

- duplicate attestations for the same:
  - `epoch_index`
  - `check_window_index`
  - `candidate_node_id`
  - `verifier_node_id`
  are invalid
- duplicates inside one bundle are invalid
- duplicates across bundles in the same active chain view are invalid
- verifier over-emission beyond the per-window cap is invalid

## Attestation Semantics

Recommended v1 result codes:

- `pass`
- `unreachable`
- `wrong_network`
- `handshake_failed`
- `sync_lag_exceeded`
- `malformed_endpoint`
- `internal_verifier_error`

v1 should prefer explicit signatures and explicit attestation records.
Do not use BLS aggregation in v1.

## Quorum Rules

For one candidate check:

- committee size: 3
- quorum required: 2 matching valid attestations

Suggested pass rule:

- candidate passes a check if at least 2 valid verifier attestations report `pass`
- candidate fails a check if at least 2 valid verifier attestations report the same disqualifying failure class
- otherwise the check is inconclusive and does not count as passed

Inconclusive checks do not count as passes.

## Final Availability Confirmation

Final availability confirmation must come from deterministically assigned checks only.

It must not be an ad hoc extra ping.

### Locked v1 Rule

- final confirmation window = last `10` blocks of the epoch
- that is, block heights:
  - `epoch_end_height - 9` through `epoch_end_height`

A candidate passes final availability confirmation only if:

- it has at least 1 assigned check in the final confirmation window
- that final-window check reaches pass quorum `2 of 3`
- observed sync gap is within threshold
- endpoint commitment matches the current registry endpoint declaration

If a candidate has no valid final-window pass:

- it is not rewardable at settlement, even if earlier checks passed

## Epoch Eligibility Rules

A registered reward node becomes epoch-settlement-eligible only if all are true:

- reward activation height has been reached
- registration is valid and unexpired
- warmup has completed
- at least 3 checks were assigned in the epoch, unless explicit tiny-registry fallback is enabled
- at least 2 checks passed
- each counted pass had quorum `2 of 3`
- final-window confirmation passed
- anti-concentration filtering did not remove it

## Anti-Concentration

These are the primary v1 anti-Sybil controls, alongside fees and warmup.

Minimum rules:

- max 1 rewarded node per public IPv4 per epoch
- optional subnet cap later
- registration fee
- renewal fee
- warmup

Important:

- IP is not identity
- concentration_key is a coarse anti-concentration filter, not identity proof

### Concentration Key Encoding

Preferred v1:

- `concentration_key = H(epoch_index || normalized_public_ipv4 || "reward-ip-v1")`

Optional subnet key:

- `subnet_key = H(epoch_index || ipv4_/24 || "reward-subnet-v1")`

Attestations carry:

- `concentration_key`
- optional `subnet_key`

Settlement validates anti-concentration conflicts from these keys, not from raw logs.

### Deterministic Conflict Resolution

After verified nodes are derived:

- group by `concentration_key`
- only one node per concentration group may remain rewardable

Tie-break order inside a concentration group is locked to:

1. highest `passed_check_count`
2. lowest `median_observed_sync_gap`
3. lowest deterministic hash rank:
   - `H(epoch_seed || node_id || payout_address)`

There is no vague scoring term in v1.

If subnet filtering is enabled:

- apply the same tie-break order within subnet groups after IPv4-group filtering

## Reward Allocation

At epoch close:

1. derive `verified_nodes`
2. apply anti-concentration filtering
3. apply final availability confirmation
4. if resulting count is zero:
   - node reward is not minted for that epoch
5. if count is small enough:
   - pay all equally
6. if count is too large:
   - select a deterministic pseudorandom subset
   - split equally among that subset

### Dilution Control

Preferred v1:

- fixed epoch budget
- capped rewarded set

Use:

- `MAX_REWARDED_NODES_PER_EPOCH`

Not:

- dynamic inflation
- dynamic reward-budget expansion
- rollover by default

Subset selection rule:

- deterministic pseudorandom ranking derived from `epoch_seed` and `node_id`
- reward the top `N` after filtering

## Reward Non-Assignment Policy

Preferred default:

- if no nodes qualify, node reward is not minted for that epoch

Do not use rollover in v1.

## Settlement Transaction

Settlement is automatic and on-chain.

Preferred v1:

- explicit special settlement transaction:
  - `reward_settle_epoch`

### `reward_settle_epoch`

Purpose:

- finalize the verified reward-node set for one epoch
- drive epoch-closing node reward settlement

Consensus-visible fields:

- `kind = reward_settle_epoch`
- `epoch_index`
- `epoch_start_height`
- `epoch_end_height`
- `epoch_seed`
- `policy_version`
- `candidate_summary_root`
- `verified_nodes_root`
- `rewarded_nodes_root`
- `rewarded_node_count`
- `distributed_node_reward_chipbits`
- `undistributed_node_reward_chipbits`
- `reward_entries`

Each reward entry contains:

- `node_id`
- `payout_address`
- `reward_chipbits`
- `selection_rank`
- `concentration_key`
- `final_confirmation_passed`

Rules:

- only valid on epoch-closing heights
- exactly one valid settlement per epoch
- must match deterministic candidate/verifier assignment rules
- must satisfy quorum rules
- must satisfy anti-concentration rules
- must satisfy subset-selection rules if verified set exceeds cap
- if no nodes qualify, settlement may still exist with zero entries and full undistributed reward

Coinbase outputs must match settlement result exactly.

## Disputes

v1 disputes should be narrow and objective.

Allowed dispute grounds:

- invalid attestation signature
- invalid verifier selection for epoch seed
- invalid candidate assignment
- malformed quorum record
- duplicate attestation misuse
- invalid registry membership reference
- invalid anti-concentration derivation
- invalid settlement computation

Not in v1:

- subjective network-condition disputes
- broad challenge games around ambiguous connectivity

## Bootstrap Market Reality

CHC access for reward-node registration is accepted as a bootstrap constraint, but it is not the main design center.

Operational position:

- simple node operation must remain possible without CHC
- only reward-registry participation requires CHC
- devnet uses faucet
- informal early acquisition channels are acceptable bootstrap reality

## UX / Wizard Implications

The product should support:

- simple full node mode
- miner mode
- reward-node registration mode once wallet has CHC
- simple single-wallet path for beginners
- advanced split-wallet path later

The wizard must never imply that CHC is required merely to run a normal node.

## v1 Design Bias

v1 should favor:

- compact attestation carriage over one-attestation-per-tx
- simple signatures over BLS
- explicit attestations over heavy aggregation
- deterministic subset selection
- compact but debuggable structures
- narrow dispute scope
- strong testability
- chain-reset friendliness on devnet

## Summary

Strategic target:

- simple full nodes free from genesis
- optional registered reward nodes
- 100-block epochs
- fixed epoch reward budget
- pseudorandom checks
- pseudorandom verifier committees
- compact signed attestation bundles
- quorum-based verification
- anti-concentration filters
- deterministic capped rewarded set if needed
- automatic on-chain settlement
- no staking
- manual payout stack frozen as non-strategic tooling
