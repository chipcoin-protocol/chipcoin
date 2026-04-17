# Devnet Node Rewards

## Goal

This document defines the phased `devnet` node reward experiment for `Chipcoin-v2`.
The implementation must remain simple, auditable, and reversible.

The priority is validating eligibility and abuse resistance before introducing protocol-native node payouts.

## Reward Shape

- Consensus schedule:
  - node reward budget exists every `100` blocks
  - initial budget is `50 CHC` per epoch
  - the budget halves with the miner subsidy every `111,000` blocks
- Early rollout:
  - observer logic is non-consensus
  - Phase 1 has no payouts
  - Phase 2 pays from a dedicated devnet reward wallet
  - Phase 3 may later move to protocol-native payouts after validation

## Phases

### Phase 1

Observer only.

- no payouts
- no claim flow
- no consensus dependency on observer output
- track who would qualify
- track who would be rejected
- track exact rejection reasons
- emit hypothetical epoch payout batches for review only

### Phase 2

Operator-approved batched payouts.

- use the same eligibility engine from Phase 1
- use a dedicated devnet reward wallet
- equal split among eligible nodes
- no public claiming flow
- manual approval gate remains
- still non-consensus

### Phase 3

Optional future protocol-native payouts.

This phase is out of scope for the first implementation. It is only a promotion target after devnet evidence is strong enough.

## Eligibility Baseline

A node can only be eligible if all required checks pass.

Required:

- `registered_on_chain`
- `registration_valid`
- `stable_identity`
- `correct_network`
- `not_banned`
- `passes_concentration_caps`
- `warmup_completed`
- `valid_protocol_handshake`
- `reachable >= 75` times out of `100` observations in the epoch

Registration alone is never sufficient.

## Observation Window

- Epoch length: `100` blocks
- Baseline observation cadence for the first implementation: `1 sample per block-equivalent event window`, stored as `100` epoch observations

The first implementation may collect observations on a wall-clock cadence and map them into the active epoch, but the output ledger must always report decisions per chain epoch.

## Observer Inputs

The observer should reuse current repo surfaces wherever possible.

### Current chain and runtime inputs

- node registry diagnostics
  - existing source: `chipcoin node-registry`
- node status diagnostics
  - existing source: `chipcoin status`
  - existing HTTP source: `GET /v1/status`
- peer summary
  - existing source: `chipcoin peer-summary`
- peer list and detail
  - existing sources: `chipcoin list-peers`, `chipcoin peer-detail`
- reward history and reward summaries
  - existing sources: `chipcoin reward-history`, `chipcoin reward-summary`, `chipcoin top-nodes`

### Observer-owned inputs

- observer config file
- optional static inventory file mapping `node_id -> host/port/operator_label`
- optional fingerprint metadata for concentration analysis

## Per-Node Observation Fields

The observer must track these fields per node:

- `identity`
- `host`
- `port`
- `first_seen`
- `last_success`
- `success_count`
- `failure_count`
- `consecutive_failures`
- `handshake_ok`
- `network_ok`
- `registration_status`
- `warmup_status`
- `concentration_status`
- `final_eligible`
- `rejection_reason`

The stored representation may include richer metrics, but these fields must be available in reports.

## Rejection Codes

Use stable string codes only.

- `unreachable`
- `protocol_handshake_failed`
- `wrong_network`
- `expired_registration`
- `insufficient_observation`
- `warmup_not_satisfied`
- `banned`
- `ip_concentration_cap`
- `subnet_concentration_cap`
- `fingerprint_concentration_cap`
- `observer_error`
- `no_eligible_nodes`

The observer may store details JSON alongside the primary code, but the primary code set must stay stable.

## Anti-Sybil Defaults

These are non-consensus and configurable.

Initial configurable caps:

- maximum rewarded nodes per public IPv4
- maximum rewarded nodes per `/24` subnet
- optional fingerprint cap
- minimum warmup age before first eligibility

The first implementation should treat these as soft caps in reports and hard excludes in Phase 2 payout proposals.

## Phase 1 Outputs

Phase 1 must produce:

- per-epoch eligibility report
- per-node decision list
- rejection reason summary
- concentration report
- hypothetical payout batch

Phase 1 does not move funds.

## Phase 2 Payout Rules

Payouts are batched and operator-approved.

Suggested initial rule:

- reward pool for the closed epoch is split equally among all eligible nodes
- split is in integer base units
- deterministic remainder handling:
  - sort eligible nodes by `(node_id, payout_address)`
  - distribute one extra base unit to the first `remainder` entries

If zero eligible nodes exist:

- no payout batch entries are created with positive amount
- the epoch’s consensus node reward remains unminted
- the observer emits a `no_eligible_nodes` summary for that epoch

## Operator Artifacts

### Epoch summary

Required fields:

- `epoch_index`
- `start_height`
- `end_height`
- `policy_version`
- `registered_nodes`
- `observed_nodes`
- `eligible_nodes`
- `rejected_nodes`
- `top_rejection_codes`
- `concentration_flags`

### Dry-run payout batch

Required fields:

- `batch_id`
- `epoch_index`
- `reward_pool_base_units`
- `eligible_node_count`
- `entries[]`

Each entry:

- `node_id`
- `payout_address`
- `amount_base_units`
- `decision`
- `reason_code`

### Executed payout batch

Adds:

- `approved_at`
- `executed_at`
- `wallet_label`
- `txid`

## Operator Commands

The first implementation should add observer-specific commands without destabilizing the existing main CLI.

Required command set:

- monetary policy summary
- supply summary
- current epoch summary
- eligible nodes list
- rejected nodes with reason codes
- concentration report
- reward history
- payout dry-run
- payout execute (Phase 2 only)

The preferred implementation path is a separate observer entrypoint first, not overloading the existing node CLI.

## Promotion Path

The promotion path remains:

1. observer-only
2. batched devnet payouts
3. possible future protocol-native payouts

Promotion to protocol-native payouts should only happen if:

- eligibility results are stable across multiple epochs
- concentration controls are effective
- the rewarded set improves actual devnet resilience
- manual intervention is rare
- audits of reward decisions remain straightforward

## Minimal First Implementation

The first implementation should avoid:

- consensus dependency on observer output
- public claim paths
- dynamic governance of reward parameters
- over-engineered operator workflows

The minimal useful result is:

- consensus math updated to the new monetary policy
- supply counters exposed via API
- observer database and sampling scaffold
- epoch reports and dry-run batches

That is enough to validate the hard problem before productionizing payouts.
