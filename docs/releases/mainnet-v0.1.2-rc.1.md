# Chipcoin Mainnet 0.1.2 RC.1

Release identity: `mainnet-v0.1.2-rc.1`

This is the first Chipcoin mainnet/PQ software release candidate. It is a
software RC, not authorization for public launch.

## Mainnet Profile

- canonical mainnet genesis and network identity;
- CHCQ and ML-DSA-44 scheme 10 from genesis;
- transaction version 2 and fail-closed legacy rejection from genesis;
- 600-second target block time and 100-block coinbase maturity;
- cumulative-work chain selection;
- reward activation at height 1000 with 100-block epochs and two warmup epochs;
- signed snapshot bootstrap with enforced trusted-signer validation.

## Runtime Evidence

The release-candidate gate records real rehearsal evidence for restart,
full-sync, partition/reorg, conflicting spends, SIGKILL/WAL recovery, signed
snapshot restore and delta sync, exact maturity boundary, PQ transactions,
reward registration/attestation/settlement/payout/reorg safety, browser-wallet
runtime behavior, and final A-E convergence.

## Deployment Boundary

Public launch remains separately gated. Do not expose Vite/esbuild development
servers or ports. Public Explorer deployment must use only the static production
build. No mainnet faucet is supported.

The final release evidence manifest binds this identity to its Git commit,
dependency locks, browser artifact hashes, Docker image identifier and exported
image checksum.
