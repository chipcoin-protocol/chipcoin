# Native Rewards Consensus Test Plan

## Status

This document defines the consensus-first test plan for the native random-check node rewards track.

It must be completed before broad implementation patches expand beyond:

- params
- payload model
- assignment helpers

## Fixed Baseline

Tests must preserve the current monetary baseline:

- max supply: 11,000,000 CHC
- initial miner subsidy: 50 CHC per block
- initial node reward budget: 50 CHC per 100-block epoch
- halving interval: 111,000 blocks
- hard cap clamp remains consensus-critical

## Locked Native v1 Assumptions

The following are fixed for initial native v1 tests:

- `EPOCH_LENGTH = 100`
- `TARGET_CHECKS_PER_EPOCH = 3`
- `MIN_PASSED_CHECKS_PER_EPOCH = 2`
- verifier committee size `3`
- verifier quorum `2`
- final confirmation window = last `10` blocks of the epoch
- final confirmation must come from deterministically assigned checks only
- `concentration_key` is a coarse anti-concentration filter, not identity proof
- fixed epoch reward budget
- deterministic capped rewarded set if verified set exceeds cap
- no rollover by default

## Test Groups

### 1. Params And Monetary Gating

Target files:

- `tests/consensus/test_economics.py`
- new activation-height tests if needed

Coverage:

- reward activation height disables node reward settlement before activation
- node reward remains zero on non-epoch blocks
- scheduled node epoch reward remains correct on epoch-closing blocks
- hard-cap clamp still correct when settlement exists
- zero issuance after cap still correct
- undistributed node reward does not become miner subsidy

### 2. Reward-Node Registry Lifecycle

Target files:

- `tests/consensus/test_node_registry.py`

Coverage:

- `register_reward_node` with endpoint fields accepted
- duplicate `node_id` rejected
- duplicate node public key rejected
- invalid payout address rejected
- invalid endpoint metadata rejected
- registration fee enforcement
- `renew_reward_node` fee enforcement
- endpoint refresh on renewal
- expiry handling
- warmup epoch derivation from registration height
- simple full node operation unaffected by reward-node registration economics

### 3. Epoch Seed And Assignment

New target file:

- `tests/consensus/test_reward_assignment.py`

Coverage:

- epoch seed reproducibility
- epoch seed changes across epochs
- candidate selection reproducibility
- verifier committee reproducibility
- committee excludes candidate itself
- deterministic assignment ordering
- tiny-registry fallback only triggers behind explicit params
- default baseline requires full 3-check model

### 4. Attestation Bundle Validation

New target file:

- `tests/consensus/test_reward_attestations.py`

Coverage:

- valid `reward_attestation_bundle` accepted
- invalid attestation signature rejected
- wrong epoch index rejected
- wrong check window rejected
- wrong candidate/verifier assignment rejected
- duplicate attestation inside one bundle rejected
- duplicate attestation across bundles rejected
- `MAX_ATTESTATIONS_PER_BUNDLE` enforced
- `MAX_ATTESTATION_BUNDLES_PER_BLOCK` enforced
- `MAX_ATTESTATIONS_PER_VERIFIER_PER_WINDOW` enforced
- malformed concentration key rejected
- malformed endpoint commitment rejected

### 5. Quorum And Eligibility

New target file:

- `tests/consensus/test_reward_eligibility.py`

Coverage:

- 3 assigned checks with 2 passed satisfies baseline
- 3 assigned checks with 1 passed fails
- inconclusive checks do not count as passed
- quorum 2 of 3 required per check
- final confirmation requires assigned final-window pass
- missing final-window pass blocks settlement eligibility
- warmup incomplete blocks eligibility
- expired registration blocks eligibility

### 6. Anti-Concentration

New target file:

- `tests/consensus/test_reward_concentration.py`

Coverage:

- verified nodes grouped by `concentration_key`
- only one node per concentration group survives
- deterministic tie-break:
  1. highest `passed_check_count`
  2. lowest `median_observed_sync_gap`
  3. lowest deterministic hash rank
- tie-break reproducibility
- optional subnet-cap path, if implemented, follows deterministic second-stage filtering

### 7. Settlement Validation

New target file:

- `tests/consensus/test_epoch_settlement.py`

Coverage:

- valid `reward_settle_epoch` accepted on epoch-closing block
- settlement on non-epoch block rejected
- settlement before activation height cannot mint node reward
- zero-qualified settlement valid with zero reward entries
- rewarded set must be subset of verified set
- deterministic equal split validated
- deterministic remainder handling validated
- if verified set exceeds cap, deterministic subset selection validated
- distributed + undistributed reward equals scheduled epoch reward
- invalid selection rank or ordering rejected
- invalid final confirmation marker rejected

### 8. Block Validation

Target file:

- `tests/consensus/test_validation.py`

Coverage:

- epoch-closing block with valid settlement and matching node outputs accepted
- node reward outputs on non-epoch blocks rejected
- node reward outputs without settlement rejected
- absent settlement with zero node reward outputs accepted
- invalid settlement blocks the whole block
- duplicated attestation use in same active chain view rejected
- cap clamp still holds when settlement is present

### 9. Mining / Node Integration

Target files:

- node/mining or node/service integration tests

Coverage:

- epoch-closing template includes node reward outputs only with valid settlement input
- no valid settlement means no node reward outputs
- diagnostics expose:
  - epoch seed
  - assigned checks
  - verified nodes
  - filtered nodes
  - rewarded subset
  - undistributed reward

## Implementation Order

Consensus-first order:

1. params
2. payload model
3. assignment helpers
4. stateless validation
5. stateful eligibility and concentration
6. settlement validation
7. mining/service consumption
8. diagnostics

## First Patch Set Scope

The first implementation patch set should be limited to:

- consensus params for new native reward controls
- reward-node transaction / payload kinds
- epoch seed and assignment helper logic

It should not yet include:

- broad settlement validation
- mining/service integration
- diagnostics expansion
- observer stack expansion

## Exit Criteria Before Broader Implementation

Before moving past the first patch set, the repo should have:

- frozen transaction / payload model
- frozen assignment rules
- frozen anti-concentration conflict rules
- frozen final confirmation rule
- consensus test skeletons or concrete tests for the above
