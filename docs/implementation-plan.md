# Implementation Plan

## Objective

Ship the new `devnet` monetary and node reward baseline in the lowest-risk sequence:

1. consensus math
2. supply API
3. observer scaffold
4. payout tooling
5. tests and chain reset

The implementation should preserve reversibility in the observer and payout layers while accepting a deliberate `devnet` consensus reset.

## Current Repo Anchors

The existing repo already contains reusable anchors:

- consensus parameters:
  - `src/chipcoin/consensus/params.py`
- monetary policy helpers:
  - `src/chipcoin/consensus/economics.py`
- current on-chain node reward selection:
  - `src/chipcoin/consensus/nodes.py`
- block assembly and reward outputs:
  - `src/chipcoin/node/mining.py`
- block validation and subsidy checks:
  - `src/chipcoin/consensus/validation.py`
- operator-facing status and supply diagnostics:
  - `src/chipcoin/node/service.py`
- HTTP API:
  - `src/chipcoin/interfaces/http_api.py`
- CLI:
  - `src/chipcoin/interfaces/cli.py`
- node registry persistence:
  - `src/chipcoin/storage/node_registry.py`

The new work should build on these paths instead of inventing a parallel architecture.

## Phase A: Consensus Math

### Scope

Update the chain economics to the new devnet baseline.

### Required changes

- replace the old ratio-based node reward model with:
  - miner subsidy per block
  - node reward per `100`-block epoch
- implement hard-cap clamp at `11,000,000 CHC`
- implement zero issuance after cap
- define deterministic clamp order
- define the consensus-visible node epoch reward schedule independent of observer eligibility

### Deliverables

- updated consensus params
- updated economics helpers
- updated reward schedule tests

### Risk management

- keep the first version pure and explicit
- do not optimize prematurely
- prefer straightforward total-issuance math over compact but opaque formulas

## Phase B: Supply API

### Scope

Expose deterministic, reorg-safe supply counters through the service, CLI, and HTTP API.

### Required counters

- `max_supply`
- `minted_supply`
- `miner_minted_supply`
- `node_minted_supply`
- `burned_supply`
- `immature_supply`
- `circulating_supply`
- `remaining_supply`

### Deliverables

- internal supply snapshot helper in `NodeService`
- `GET /v1/supply`
- reduced supply summary in `/v1/status`
- CLI command for supply summary
- updated HTTP and CLI tests

### Risk management

- derive from active-chain state first
- only add caching/indexing later if needed

## Phase C: Observer Scaffold

### Scope

Add a non-consensus observer service that samples registered nodes and computes epoch eligibility decisions.

### Required outputs

- observed node table
- epoch table
- per-node per-epoch stats
- rejection reason codes
- eligibility reports
- concentration reports
- dry-run payout proposals

### Deliverables

- observer schema
- config loader
- sampler loop
- epoch close command
- report commands

### Risk management

- keep observer state outside consensus storage
- keep anti-Sybil thresholds configurable
- do not feed observer decisions back into consensus

## Phase D: Payout Tooling

### Scope

Add Phase 2 batched devnet payouts from a dedicated reward wallet.

### Required behavior

- build deterministic payout batch
- equal split in base units
- deterministic remainder assignment
- operator approval step
- execution step
- ledger recording of the batch and txid

### Deliverables

- dry-run batch command
- approve-batch command
- execute-batch command
- payout ledger tables

### Risk management

- keep a manual approval gate
- no public claim flow
- no automatic execution from observer close logic

## Phase E: Tests and Reset

### Scope

Finalize test coverage, confirm API behavior, and prepare devnet reset.

### Required work

- consensus math tests
- supply accounting tests
- observer unit tests
- payout batch tests
- update docs and reset checklist
- reset devnet chain data after consensus changes land

### Deliverables

- passing targeted tests
- updated docs
- clean reset instructions

## File-Level Code Map

### Files that must change

Consensus and mining:

- `src/chipcoin/consensus/params.py`
  - replace current devnet constants
  - likely extend `ConsensusParams` to represent epoch reward explicitly
- `src/chipcoin/consensus/economics.py`
  - remove ratio-driven node reward calculation
  - add explicit epoch reward schedule
  - add cap clamp helpers
  - add miner/node minted accounting helpers
- `src/chipcoin/consensus/nodes.py`
  - replace per-block winner selection with epoch-oriented split helper
  - preserve registration primitives
- `src/chipcoin/consensus/validation.py`
  - update coinbase and issuance validation to the new schedule
- `src/chipcoin/node/mining.py`
  - update block template construction to use the new miner issuance path
  - if protocol-native node payouts stay disabled initially, ensure no stale per-block node outputs remain

Node service and APIs:

- `src/chipcoin/node/service.py`
  - replace old economy summary assumptions
  - implement full supply snapshot
  - expose `/v1/status` reduced supply summary inputs
  - update reward-related diagnostics to the new epoch baseline
- `src/chipcoin/interfaces/http_api.py`
  - add `GET /v1/supply`
  - add reduced supply fields to status output if formatting is done there
- `src/chipcoin/interfaces/cli.py`
  - add monetary policy summary command
  - add supply summary command
  - add observer-related command stubs or separate dispatch integration

Tests:

- `tests/consensus/test_economics.py`
- `tests/consensus/test_node_rewards.py`
- `tests/node/test_http_api.py`
- `tests/node/test_cli.py`

### New files to add

Docs:

- `docs/monetary-policy.md`
- `docs/devnet-node-rewards.md`
- `docs/implementation-plan.md`

Observer module:

- `src/chipcoin/rewards/__init__.py`
- `src/chipcoin/rewards/config.py`
- `src/chipcoin/rewards/models.py`
- `src/chipcoin/rewards/schema.py`
- `src/chipcoin/rewards/store.py`
- `src/chipcoin/rewards/observer.py`
- `src/chipcoin/rewards/eligibility.py`
- `src/chipcoin/rewards/concentration.py`
- `src/chipcoin/rewards/reporting.py`
- `src/chipcoin/rewards/payouts.py`
- `src/chipcoin/interfaces/reward_observer_cli.py`

Tests for observer and payouts:

- `tests/rewards/test_eligibility.py`
- `tests/rewards/test_concentration.py`
- `tests/rewards/test_store.py`
- `tests/rewards/test_reporting.py`
- `tests/rewards/test_payouts.py`

Optional fixture/config examples:

- `config/reward-observer.devnet.example.json`

### Files likely to need schema/storage changes

- `src/chipcoin/storage/node_registry.py`
  - only if current registry persistence lacks fields required by the observer bridge
- `src/chipcoin/storage/headers.py`
  - likely unchanged for first implementation
- `src/chipcoin/storage/chainstate.py`
  - likely unchanged if supply accounting is derived from active UTXOs and active-chain blocks

### Files that can likely remain untouched in the first implementation

- `src/chipcoin/node/runtime.py`
  - except if status payload plumbing needs tiny additions
- `src/chipcoin/node/sync.py`
- snapshot pipeline files
- browser wallet frontend
- explorer frontend
- bootstrap seed service
- miner worker orchestration outside template interpretation

### Exact uncertainty to resolve during implementation

- `src/chipcoin/node/mining.py` and `src/chipcoin/consensus/validation.py` need a close read to confirm whether the current block coinbase builder assumes per-block node reward outputs in all cases
- `src/chipcoin/node/service.py` already has `economy_summary()` and `supply_diagnostics()`; these need to be inspected line-by-line before deciding whether to evolve or replace them
- current node registry persistence may or may not already expose enough fields for observer warmup logic without schema changes

## Lowest-Risk Implementation Sequence

### Phase A: Consensus math

Order:

1. update `ConsensusParams` in `src/chipcoin/consensus/params.py`
2. rewrite subsidy helpers in `src/chipcoin/consensus/economics.py`
3. update node epoch reward helper in `src/chipcoin/consensus/nodes.py`
4. update validation rules in `src/chipcoin/consensus/validation.py`
5. update mining template logic in `src/chipcoin/node/mining.py`
6. update consensus tests

Stop point:

- consensus tests pass with new monetary schedule

### Phase B: Supply API

Order:

1. refactor/add supply snapshot helpers in `src/chipcoin/node/service.py`
2. add `/v1/supply` in `src/chipcoin/interfaces/http_api.py`
3. add reduced status supply summary
4. add CLI command(s) in `src/chipcoin/interfaces/cli.py`
5. update HTTP/CLI tests

Stop point:

- `/v1/supply` and CLI supply summary are stable on devnet

### Phase C: Observer scaffold

Order:

1. add reward observer package under `src/chipcoin/rewards/`
2. add SQLite schema and store
3. add config loader
4. add sampling logic against current node registry and status surfaces
5. add epoch close logic
6. add report outputs
7. add rejection codes and concentration logic
8. add tests for observer core

Stop point:

- observer can run Phase 1 end-to-end with no payouts

### Phase D: Payout tooling

Order:

1. add dry-run batch builder
2. add deterministic equal-split + remainder logic
3. add approval state
4. add execute path from dedicated wallet
5. add payout ledger persistence
6. add payout tests

Stop point:

- Phase 2 can produce and execute an auditable batch, but only after manual approval

### Phase E: Tests and reset

Order:

1. run targeted consensus tests
2. run service/API tests
3. run observer tests
4. run payout tests
5. update reset and rollout notes
6. reset devnet chain data

Stop point:

- repo is internally consistent with the new baseline and ready for devnet restart
