# Mainnet Release-Candidate Gate

This document defines the deterministic release gate for the Chipcoin mainnet
software release candidate. The machine-readable source of truth is
[`mainnet-release-gate.json`](mainnet-release-gate.json). Requirement IDs,
statuses, dependencies, evidence references, and blocking classes in that file
are normative.

Generated from evidence available through 2026-10-15, including the accepted
fault/recovery, snapshot/restore/delta, PQ negative-runtime, real reward
lifecycle, and final A-E convergence reports.

## Decision

```text
MAINNET_RC_READY = FALSE
PUBLIC_LAUNCH_READY = FALSE
```

`MAINNET_RC_READY` becomes `TRUE` only when every `RC_BLOCKING` requirement is
`PASS`, `FINAL-RUN-001` is `PASS`, and no unresolved consensus or
production-reachable security blocker exists. A `FAIL`, `NOT_RUN`,
`PENDING_HEIGHT`, or `BLOCKED` value on any RC-blocking requirement makes the
result `FALSE`.

`PUBLIC_LAUNCH_READY` additionally requires every `PUBLIC_LAUNCH_BLOCKING`
requirement to be `PASS`. Public deployment is deliberately separate from the
software RC.

No readiness percentage may override these Boolean rules.

## Status Vocabulary

| Status | Meaning |
|---|---|
| `PASS` | The required evidence exists for the exact gate described. |
| `FAIL` | The observed result is incorrect or an explicit release condition is unmet. |
| `NOT_RUN` | The required runtime test or release operation has not been completed. |
| `PENDING_HEIGHT` | The real consensus height prerequisite has not been reached. |
| `BLOCKED` | An external prerequisite prevents execution. |

Code inspection, unit tests, fixtures, or in-process tests never satisfy a gate
whose description explicitly requires Docker, browser, multi-process, or live
mainnet-rehearsal evidence.

## Current Counts

### RC-blocking

| Status | Count |
|---|---:|
| `PASS` | 94 |
| `FAIL` | 0 |
| `NOT_RUN` | 4 |
| `PENDING_HEIGHT` | 0 |
| `BLOCKED` | 0 |
| **Total** | **98** |

### Public-launch-only

| Status | Count |
|---|---:|
| `NOT_RUN` | 7 |
| **Total** | **7** |

Counts are reproducible with:

```bash
jq '[.requirements[] | select(.blocking == "RC_BLOCKING")] | group_by(.status) | map({status: .[0].status, count: length})' mainnet-release-gate.json
```

## Evidence Policy

Evidence paths and accepted historical reports are catalogued in
`mainnet-release-gate.json`. The principal persisted artifacts are:

- mainnet PQ preflight: accepted complete PASS, but no standalone report artifact retained;
- isolated mainnet legacy-rejection evidence under `/tmp/chipcoin-mainnet-pq-neg-001-20261006/`;
- height 1/10/100 milestone manifests under `/tmp/chipcoin-mainnet-docker-rehearsal/milestones/`;
- maturity/PQ report at `/tmp/chipcoin-mainnet-docker-rehearsal/maturity-pq/MAINNET_MATURITY_PQ_TRANSACTION_REPORT.md`;
- controlled restart and full-sync reports under `/tmp/chipcoin-mainnet-docker-rehearsal/fault/evidence/`;
- fault harness readiness report at `/tmp/chipcoin-mainnet-docker-rehearsal/fault/MAINNET_FAULT_HARNESS_READINESS_REPORT.md`;
- fault-monitor lifecycle hardening report at `docs/mainnet-fault-monitor-lifecycle-hardening-report.md`;
- immutable fault-session audit and crash-recovery validation at `docs/mainnet-fault-harness-state-model-audit-report.md` and `docs/mainnet-fault-harness-crash-recovery-validation-report.md`;
- P2P reconnect audit and historical evidence analysis at `docs/mainnet-p2p-reconnect-reliability-report.md`;
- controlled P2P fix deployment and live reconnect validation at `docs/mainnet-p2p-reconnect-live-validation-report.md`;
- signed snapshot, trust, restore, and delta evidence at `docs/mainnet-signed-snapshot-restore-delta-report.md` and `/tmp/chipcoin-mainnet-docker-rehearsal/snapshot/evidence-mainnet-signed-20261005/`;
- invalid-snapshot rejection, integrated full-sync fallback, and continuation evidence at `docs/mainnet-invalid-snapshot-fallback-report.md` and `/tmp/chipcoin-mainnet-snap-ops-001-20261006T073203Z/`;
- exact mainnet coinbase-maturity boundary evidence at `docs/mainnet-coinbase-maturity-exact-boundary-report.md` and `/tmp/chipcoin-mainnet-docker-rehearsal/maturity-boundary-exact/result.json`;
- real reward activation, attestation, settlement, payout and Explorer evidence at `docs/mainnet-reward-lifecycle-settlement-payout-report.md` and `/tmp/chipcoin-mainnet-docker-rehearsal/reward-lifecycle-20261015/`;
- reward-state same-DB restart persistence and canonical continuation evidence at `docs/mainnet-reward-restart-persistence-report.md` and `/tmp/chipcoin-mainnet-docker-rehearsal/reward-restart-20261015/`;
- final A-E convergence and continuation evidence at `docs/mainnet-final-a-e-convergence-report.md` and `/tmp/chipcoin-mainnet-docker-rehearsal/final-a-e-20261015/`;
- accepted private Chipcoin Central security and Explorer E2E reports from the separate repository.

Before tagging the RC, evidence currently held only in `/tmp` must be copied to
an immutable release evidence archive. This copy must not include wallets,
seeds, private keys, or runtime databases unless explicitly required and
handled under a separate secure retention policy.

## Verification Layers

The matrix deliberately separates:

- `*-CFG-*`: consensus/configuration/code verification;
- `*-RUN-*`: real runtime behavior;
- `*-NEG-*`: explicit negative runtime rejection;
- `*-OPS-*`: operational and packaging behavior;
- public infrastructure gates, which do not block creation of the software RC.

Examples:

- `CONS-CFG-008` proves that maturity is configured as 100 blocks.
- `TX-RUN-001` proves a positive mature spend at a later height.
- `TX-RUN-002` separately requires the exact 99-reject/100-accept boundary
  using the same raw transaction. The first two do not satisfy the third.
- `SNAP-CFG-001/002` cover implementation support; they do not satisfy the
  real snapshot restore gates.

## Current Pass Summary

The evidence currently supports these major results:

- deterministic mainnet profile, network identity, economics, 600-second target,
  initial target, 100-block maturity, 111,000-block halving, and 11M cap;
- PQ-only mainnet configuration from genesis, CHCQ, scheme 10, PQ coinbase,
  PQ miner/owner/attestation wallet provisioning and read-only secret mounts;
- one real mature CHCQ-to-CHCQ ML-DSA-44 transaction, mempool propagation,
  block inclusion, fee/change, UTXO transition, balances, and A/B/C convergence;
- the exact unchanged-transaction maturity boundary: candidate height 99 is
  rejected as immature and candidate height 100 is accepted through production
  consensus, block-stateful, and node mempool validation paths;
- controlled restart/P2P catch-up and empty-DB full sync from genesis;
- Chrome/Firefox production builds, network separation/fail-closed logic,
  ML-DSA transaction/login signing, and endpoint/permission audits;
- private Chipcoin Central network separation and real PQ transaction display;
- Scenario A partition isolation, real fork, cumulative-work selection,
  orphan block/coinbase/supply/UTXO rollback, valid orphan TX mempool re-entry,
  unique canonical reconfirmation, A/B/C convergence, and SQLite integrity;
- a signed snapshot from canonical rehearsal state, fail-closed trust/tamper
  checks, empty-node restore, real P2P delta sync, deterministic state equality,
  and post-convergence chain continuation;
- dependency risk review with residual Vite/esbuild exposure classified as
  build/development-only. No development server may be public.

## Remaining RC Blockers

The following list is complete for every RC-blocking requirement whose status
is not `PASS`.

### Consensus, PQ, And Transactions

| ID | Status | Requirement |
|---|---|---|
| `PQ-RUN-003` | `PASS` | Real two-input ML-DSA-44/scheme-10 transaction confirmed exactly once at height 278 with correct UTXO and fee accounting. |
| `PQ-NEG-001` | `PASS` | Isolated Docker mainnet runtime rejected legacy/ECDSA output, transaction v1, scheme-0 and mixed inputs, legacy coinbase, special-signature v1/ECDSA, legacy attestation identity, and legacy payout without state mutation. |
| `PQ-NEG-002` | `PASS` | Docker and browser production paths reject unchanged signed-login and transaction artifacts across mainnet/testnet domains; endpoint mismatch and persisted-state isolation pass. |

### Fault And Recovery

| ID | Status | Requirement |
|---|---|---|

Scenario A, Scenario B, and SIGKILL/WAL recovery are closed as **PASS**. Scenario B evidence is in
[the closure report](docs/mainnet-scenario-b-closure-report.md):
`CONS-RUN-005` and `FAULT-RUN-012` are **PASS**, including continuation at 219.
The [SIGKILL/WAL report](docs/mainnet-sigkill-wal-recovery-report.md) closes
`FAULT-RUN-013` and the final post-fault SQLite gate `FAULT-RUN-014`. The
post-scenario finalize lock-transition issue is tracked separately in the
Scenario B report; the existing recovery restored operation.

`FAULT-OPS-001` is now **PASS**. Recovery preserves the original immutable
fault-session identity, all 17 interruption points recovered after an actual
orchestrator-process kill, and three consecutive ephemeral Docker sessions
completed without manual cleanup. `FAULT-OPS-002` is now **PASS** after the
minimal fix was deployed C/B/A and tested on the live rehearsal. Isolated
node-c retained a visible permanent connect loop, applied bounded connectivity
backoff without malformed/reputation penalties, and reconnected in 913 ms
without restart. A/B/C then converged with clean SQLite checks.

`FAULT-OPS-003` is **PASS**. Scenario activation now owns a synchronous
completion barrier: verified partition evidence, immutable session ownership,
fault-monitor health, fault-lock phase/topology, and lifecycle phase are
persisted, fsynced, and reread before exit 0. Artificial-delay regressions,
ten consecutive ephemeral Docker activation/recovery cycles, and the expanded
17-checkpoint process-kill suite completed without delayed transitions or
manual cleanup.

### Snapshot

| ID | Status | Requirement |
|---|---|---|
| `SNAP-OPS-001` | `PASS` | Failed snapshot safely falls back to full sync. |

`SNAP-NEG-001`, `SNAP-NEG-002`, and `SNAP-RUN-001..004` are now **PASS**.
The signed canonical snapshot at height 249 restored into an empty Docker node,
applied a real ten-block P2P delta, matched A/B/C deterministically at height
268, and continued onto a subsequent canonical block. Separately, the
production `auto` bootstrap rejected a checksum-tampered snapshot without
adopting state, full-synced an empty node from genesis over P2P to A/B/C at
height 328, and remained converged through canonical block 329.

### Reward Lifecycle And Explorer

| ID | Status | Requirement |
|---|---|---|
| `REWARD-RUN-001` | `PASS` | Canonical 999/1000/1001 evidence proves activation, renewal and first eligibility/attestation behavior. |
| `REWARD-RUN-002` | `PASS` | Two real pre-activation registrations confirmed at height 275 with distinct ML-DSA-44 owner/attestation identities and CHCQ payouts. |
| `REWARD-RUN-003` | `PASS` | Two-epoch warmup, eligibility, ML-DSA attestations, committee assignments and final quorum passed in epochs 10 and 11. |
| `REWARD-RUN-004` | `PASS` | Canonical settlements at 1099 and 1199 paid 25 CHC to each CHCQ recipient per epoch. |
| `REWARD-RUN-005` | `PASS` | Single payouts, correct maturity, supply/UTXO accounting and A/B/C equality verified. |
| `REWARD-RUN-006` | `PASS` | Registry, settlement and payout state survived a controlled node-c same-DB restart and remained convergent through height 1223. |
| `REWARD-RUN-007` | `PASS` | A real reward-era fork from height 1227 selected B by cumulative work; orphan coinbases rolled back and registry, attestations, settlements, payouts, supply and UTXO state converged through block 1231. |
| `EXP-INT-004` | `PASS` | Private production Explorer and Chromium E2E display the real settlement and payouts. |

No epoch, activation, maturity, or difficulty may be shortened to close these
gates.

### Final Convergence

| ID | Status | Requirement |
|---|---|---|
| `FINAL-RUN-001` | `PASS` | A normal, B reorg, C restart/SIGKILL recovery, D genesis full-sync, and E signed snapshot+delta converged exactly at height 1234 and remained equal through canonical block 1235. |

The comparison must include height, tip hash, cumulative work, supply, UTXO
count and deterministic hash, selected balances, reward registry, settlement,
and payout history/state. Height equality alone is insufficient.

### Browser Wallet

| ID | Status | Requirement |
|---|---|---|
| `BW-OPS-001` | `PASS` | Canonically rebuilt named Chrome/Firefox artifacts match their validated references; Firefox clean create/import and Chromium 153 clean mainnet PQ create, restart persistence, network isolation, API fail-closed, and secret hygiene all pass. |
| `BW-OPS-002` | `PASS (N/A)` | No supported mainnet/PQ predecessor or migration contract exists for this first mainnet release. Devnet/testnet and stale artifacts are not migration sources; legacy wallets cannot be silently promoted to mainnet. |

### Release Integrity And Security

| ID | Status | Requirement |
|---|---|---|
| `SEC-REL-001` | `NOT_RUN` | Immutable RC version and Git commit/tag. |
| `SEC-REL-002` | `NOT_RUN` | Verify clean/inventoried working tree when the RC freeze actually begins. |
| `SEC-REL-004` | `NOT_RUN` | Record immutable Docker image digests. |
| `SEC-REL-005` | `NOT_RUN` | Produce traceable/reproducible final build evidence. |
| `SEC-SNAP-KEY-001` | `PASS` | Protected-file signer input removes snapshot private material from argv/environment; process, output, artifact, permission, compatibility, tamper, and trust tests pass. |

The deferred Vite/esbuild major upgrade is not independently blocking while
the residual issue remains build/development-only, production deployment is
static, and no Vite/esbuild development port is exposed.

`SEC-SNAP-KEY-001` is supported by
`docs/mainnet-snapshot-signer-security-report.md`. Snapshot signing now reads an
owner-only protected regular file directly, rejects unsafe modes and symlinks,
and retains the existing snapshot signature/verifier format. Canary tests prove
the key is absent from argv, process environment, captured output, command
evidence, snapshot output, temporary artifacts, and repository changes.

### Runbooks

`RUNBOOK-001` through `RUNBOOK-005` are now `PASS` as documentation gates,
using `docs/mainnet-operator-runbook.md` and
`mainnet-operator-checklist.json`. Runtime validation remains separate wherever
another gate explicitly requires it.

## Critical Path

Close blockers in this order:

1. Execute Scenario B and final fault integrity
   checks. Execute SIGKILL separately from partition tests.
2. Complete remaining transaction/negative gates: exact 99/100 boundary,
   multi-input PQ, legacy rejection, and cross-network replay rejection.
3. Produce a real signed mainnet rehearsal snapshot; run all trust-negative
   cases, empty-node restore, delta sync, fallback, and state equality.
4. Continue the unaccelerated soak through activation, warmup, settlement, and
   payout; validate reward persistence/reorg safety and Explorer display.
5. Execute final A-E convergence after reward and snapshot paths exist.
6. Complete packaged-browser clean-install and migration drills.
7. Execute and record the operational checklist during RC validation without
   treating documentation as runtime evidence.
8. Freeze the RC source: inventory/resolve the working tree, choose immutable
   version/tag, build pinned images, record digests, and archive traceable
   evidence.
9. Evaluate `MAINNET_RC_READY` mechanically. Begin public infrastructure work
    only after it becomes `TRUE`.

## Browser Wallet Gate

RC requires both production packages, network-scoped state, fail-closed API
network validation, no legacy mainnet signing, ML-DSA transaction and login
signing, permission/endpoint audits, no hardcoded testnet dependency, and
clean-install/migration evidence. Current build, cryptographic/network, and
clean-install tests pass. Migration is explicitly not applicable because this
is the first supported mainnet/PQ browser-wallet release and no supported
predecessor contract exists. Release finalization must bind source/commit to
the canonical build, named artifact hashes, and the exact runtime-validated
artifacts.

## Chipcoin Central Explorer Gate

Chipcoin Central is separate from consensus software. RC requires private
integration validation, not public deployment. Network verification,
fail-closed behavior, MAINNET labeling, blocks, coinbase, CHCQ, PQ transaction,
fee, maturity, UTXO, balances, and real reward settlement/payout display have
accepted evidence.

Public Explorer deployment belongs to `PUBLIC_LAUNCH_READY`.

## Snapshot Gate

The implementation-level snapshot tests do not satisfy runtime gates. The RC
must archive evidence of deterministic metadata bound to mainnet/genesis,
height/tip/work, checksum, authorized signature, enforced trust anchor,
negative trust/network cases, atomic production, secret exclusion, empty-node
restore, delta sync, equality with full sync, and fallback to full sync.

## Reward Gate

The reward gate uses real mainnet parameters: activation 1000, 100-block epochs,
two warmup epochs, no acceleration, ML-DSA owner/attestation, CHCQ payout, real
committee/quorum/eligibility/settlement, exact payout accounting, no duplicate
payout, persistence, applicable reorg safety, and A/B/C equality.

## Runbook Gate

Each procedure must indicate whether it is merely `DOCUMENTED` or also
`RUNTIME_VALIDATED`. Documentation is sufficient only for the runbook gate;
runtime behavior must satisfy its own dedicated gate.

## Post-RC / Public Launch Ready

These requirements do not block creation of the software RC, but all block
public launch:

| ID | Status | Requirement |
|---|---|---|
| `EXP-PUB-001` | `NOT_RUN` | Public mainnet Explorer deployment and monitoring. |
| `PUB-001` | `NOT_RUN` | Public bootstrap/seed, DNS, and port separation. |
| `PUB-002` | `NOT_RUN` | TLS, firewall, API exposure and rate limiting. |
| `PUB-003` | `NOT_RUN` | Monitoring, alerting, and backups. |
| `PUB-004` | `NOT_RUN` | Signed initial snapshot distribution and downloads. |
| `PUB-005` | `NOT_RUN` | Public docs/endpoints and explicit absence of mainnet faucet. |
| `PUB-006` | `NOT_RUN` | Launch sequence, rollback, and emergency rehearsal. |

No mainnet service should be made public while this section remains incomplete.

## Machine Validation

The following expression is the canonical RC decision:

```bash
jq -e '
  ([.requirements[] | select(.blocking == "RC_BLOCKING" and .status != "PASS")] | length) == 0
  and (.requirements[] | select(.id == "FINAL-RUN-001") | .status == "PASS")
' mainnet-release-gate.json
```

The public-launch decision additionally requires:

```bash
jq -e '
  ([.requirements[] | select(.blocking == "RC_BLOCKING" and .status != "PASS")] | length) == 0
  and ([.requirements[] | select(.blocking == "PUBLIC_LAUNCH_BLOCKING" and .status != "PASS")] | length) == 0
' mainnet-release-gate.json
```

Both expressions currently return false.
