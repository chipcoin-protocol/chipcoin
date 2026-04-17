# Native Reward Prototype Phase Close

## Scope

This document closes the current native reward prototype phase.

The prototype now covers:

- reward-node registration and renewal
- deterministic candidate and verifier assignment
- persisted attestation bundles
- deterministic epoch settlement derivation
- automatic epoch-closing settlement inclusion
- real coinbase payout outputs for rewarded nodes
- local snapshot export/import preservation of native reward state
- CLI-first diagnostics for settlement and payout inspection

This phase does not yet cover:

- dispute flow
- verifier slashing or staking
- production-grade anti-concentration identity proofs
- broader runtime/API productization

## Current Native Reward Model

The current prototype model is:

- fixed node reward budget per epoch from consensus monetary policy
- reward epochs close on deterministic epoch-closing heights
- active reward-node registry records form the candidate pool
- candidate windows and verifier committees are deterministic from the epoch seed
- eligibility is derived from persisted valid attestations only
- final rewarded set is filtered by concentration key and reward cap
- automatic settlement occurs on the closing block
- coinbase outputs are derived exactly from settlement `reward_entries`

### Prototype Eligibility Rule

A reward node is currently rewarded only if:

- it is active in the reward registry at settlement time
- it has enough passed assigned windows for the epoch
- the final assigned window also passes
- valid pass attestations meet quorum for the relevant windows
- it survives concentration filtering
- it survives any rewarded-set cap

### Prototype Payout Rule

Settlement computes:

- `rewarded_node_count`
- `distributed_node_reward_chipbits`
- `undistributed_node_reward_chipbits`
- `reward_entries`

Allocation is:

- equal split among rewarded nodes
- deterministic remainder to lower `selection_rank`
- zero distributed reward when no nodes qualify

## Automatic Settlement Flow

The normal local happy path is now:

1. register reward nodes
2. mine registration block
3. inspect assignments if desired
4. submit attestation bundles
5. mine attestation persistence block(s)
6. mine up to the epoch-closing boundary
7. node service auto-builds a settlement when the closing block is assembled
8. mining includes that settlement in the closing block
9. coinbase payout outputs are derived from that included settlement
10. settlement and payouts are inspectable after block acceptance

### Precedence

- manual settlement transaction in mempool for the exact closing epoch takes precedence
- otherwise settlement is auto-generated
- already-settled epochs do not auto-generate again
- invalid manual settlements are rejected, not silently relaxed

## Diagnostics Available

The prototype now exposes:

- `reward-epoch-seed`
  - deterministic epoch seed and boundary data
- `reward-assignments`
  - candidate windows and verifier committees
- `reward-attestations`
  - persisted attestation bundles
- `reward-settlement-preview`
  - deterministic preview payload for an epoch
- `reward-settlement-report`
  - detailed report with:
    - rewarded ranking
    - non-reward reasons
    - failed windows
    - concentration exclusions
    - settlement accounting summary
- `reward-settlements`
  - persisted settlements with `submission_mode`
- `block --height ...`
  - materialized `node_reward_payouts`
- `utxos --address ...`
  - rewarded output presence
- `balance --address ...`
  - resulting rewarded balance
- `reward-history --address ...`
  - reward accounting over time

## Known Prototype Limitations

- no dispute process yet
- no challenge/appeal path for bad attestations
- anti-concentration is still a coarse heuristic keyed by declared concentration input
- endpoint truth is only as strong as attestation validity in the current prototype
- local mining path is solid; broader runtime automation remains intentionally narrow
- manual settlement override still exists for testing and fault injection
- settlement diagnostics are detailed, but not yet exposed through a richer runtime API

## Reliability Notes

Current hardening in this phase includes:

- deterministic settlement regeneration for the same epoch state
- no duplicate auto-settlement for already-settled epochs
- no double inclusion of manual and auto settlement in one closing block
- snapshot restore mid-cycle preserving native reward state
- multi-epoch automatic reward operation across consecutive epochs
- block-output validation against settlement accounting

## Next Milestone Options

The next milestone should stay narrow.

Recommended options:

1. dispute-phase prototype
   - objective invalidity only
   - malformed settlement, wrong assignments, bad signatures, duplicate attestation misuse

2. richer runtime/API inspection
   - if operator visibility becomes the bottleneck before disputes

3. stronger concentration input handling
   - only if current prototype evidence shows concentration ambiguity is the next real blocker

The recommended next step is:

- dispute-phase prototype on top of the now-stable automatic settlement path
