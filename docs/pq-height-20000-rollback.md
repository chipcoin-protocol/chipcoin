# PQ Height 20000 Rollback Procedure

The height `20000` change is a coordinated testnet consensus upgrade. Rollback
must also be coordinated.

## Before Any PQ Block Below 30000

If no block between heights `20000` and `29999` has included a CHCQ output,
transaction v2 wallet spend, or ML-DSA input:

1. Stop the rollout and do not upgrade additional hosts.
2. Identify the problem and prepare a corrective release.
3. If reverting to `30000`, ship a new coordinated release that restores the
   testnet activation height.
4. Restart upgraded nodes only after the corrective release is installed.
5. No database migration is required.
6. Verify all nodes agree on the same tip.
7. Re-run `pq-smoke`, `pq-dress-rehearsal`, and operational readiness.

Do not silently downgrade a subset of miners while other upgraded miners remain
online.

## After a PQ Block at Height 20000..29999

If the active chain contains PQ activity below old height `30000`:

1. Do not perform individual downgrades.
2. Declare a testnet consensus incident.
3. Preserve node databases and logs.
4. Identify the intended canonical branch.
5. If necessary, pause controlled miners to avoid extending a wrong branch.
6. Coordinate a second release with explicit consensus behavior.
7. Evaluate whether an explicit reorg is required.
8. Do not delete databases without backup.
9. Do not import snapshots from nodes whose branch is not confirmed canonical.
10. Communicate the state to node, reward-node, miner, explorer, and API
    operators.

Old nodes configured for `30000` will not automatically converge with a chain
that already contains PQ blocks below `30000`.
