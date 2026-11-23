# Block submission rollout and rollback

Status: NOT APPROVED, NOT DEPLOYED. The combined reward/wizard/pool candidate awaits an external end-to-end test. See [integrated readiness](MAINNET_INTEGRATED_RC_READINESS.md) and its [host-specific rollout plan](MAINNET_INTEGRATED_RC_ROLLOUT.md).

1. Freeze a candidate commit and reproducible image digest. Run full unit/integration suite and T1–T12. Verify deployed Mainnet source/config parity again, including genesis and network identity. Compare canonical vectors against an existing node in read-only mode.
2. Provide the candidate, [compatibility matrix](BLOCK_SUBMISSION_COMPATIBILITY.md), [API specification](BLOCK_SUBMISSION_SPEC.md), and [test plan](POOL_PRERELEASE_TEST_PLAN.md) to an external pool tester through an approved private channel. Record results, regressions, and the maintainer's explicit go/no-go decision outside the public repository.
3. If approved, take a verified backup of each node's configuration and image reference. Confirm the node is synced and capture height, tip, cumulative work, peer health, API responses, and mining submission counters. Upgrade one non-reference node first under an agreed maintenance window, then compare it with the reference node.
4. Monitor accepted blocks, duplicate submissions, legacy `unknown_or_expired_template`, invalid-block reasons, relay failures, API 500s, tip divergence, and side-branch storage. Stop rollout if consensus identity or tip diverges, accepted blocks disappear, validation rejects valid legacy jobs, or error rates rise unexpectedly.
5. Roll back by restoring the previous image/configuration and restarting only the approved node. The candidate has no schema migration or wallet-data change; do not delete the chain database, peerbook, or wallets. Verify height, tip, work and submission behavior after rollback.

No production command is executed by this document. Any deploy, image replacement, service restart, publication, or message to pool operators requires explicit authorization.
