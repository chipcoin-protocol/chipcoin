# Mandatory Testnet Upgrade: PQ Activation at Height 20000

## Summary

This release prepares the mandatory Chipcoin testnet consensus upgrade that
reschedules Post-Quantum support from height `30000` to height `20000`.

Affected network: `testnet` only. Devnet remains scheduled at height `30000`.

## What changes

- Testnet CHCQ output and transaction v2 wallet-spend activation height changes
  from `30000` to `20000`.
- The Python package version is bumped to `0.1.2` so node user agents and
  container builds can be distinguished from pre-upgrade software.
- Operational rollout scripts and verification commands are provided for
  preflight and post-deployment checks.

## What does not change

- No database migration is required.
- No wallet key migration is required.
- No address format changes.
- No transaction wire-format changes.
- No changes to transaction version, `sig_scheme_id`, sighash v2, domain
  separators, CHCQ address format, ML-DSA implementation, PoW, rewards, or P2P
  protocol.
- Browser wallet PQ signing and sending remain disabled.

## Who must upgrade

Upgrade before testnet height `20000`:

- bootstrap nodes;
- seed nodes;
- public API nodes;
- reward nodes;
- miner-connected full nodes;
- any standalone miner image that includes the Chipcoin Python package;
- snapshot-producing hosts and daily-report hosts that build from the node
  package.

Explorer, website, and browser wallet updates are operational/display updates,
not consensus-critical, but should be coordinated to avoid stale countdowns.

## Upgrade deadline

All consensus-participating testnet nodes should run the height-`20000` release
well before block `20000`. A minimum operator margin of 1000 blocks is
recommended; 100 blocks is the last safe operational checkpoint.

## Docker upgrade

Build the node/miner image from the release commit:

```bash
VERSION=0.1.2
REVISION=$(git rev-parse --short=12 HEAD)
CREATED=$(date -u +%Y-%m-%dT%H:%M:%SZ)

docker build --pull --no-cache \
  --label org.opencontainers.image.version="$VERSION" \
  --label org.opencontainers.image.revision="$REVISION" \
  --label org.opencontainers.image.created="$CREATED" \
  -t chipcoin-testnet-node:$VERSION \
  -f Dockerfile .
```

Verify the image before use:

```bash
docker run --rm chipcoin-testnet-node:0.1.2 \
  chipcoin verify-pq-activation --network testnet --expected-height 20000
```

Do not run `docker compose down -v`. Preserve all chain, wallet, and runtime
volumes.

## Source upgrade

```bash
git fetch --all --tags
git checkout <release-commit>
.venv/bin/python -m pip install -e .
.venv/bin/python -m chipcoin.tools.verify_pq_activation \
  --network testnet \
  --expected-height 20000
```

## Verification

Local package:

```bash
python -m chipcoin.tools.verify_pq_activation --network testnet --expected-height 20000
python -m chipcoin.tools.verify_pq_activation --network devnet --expected-height 30000
```

Server-installed package:

```bash
CHIPCOIN_ROOT=/opt/chipcoin \
CHIPCOIN_PYTHON=/opt/chipcoin/.venv/bin/python \
scripts/verify-pq-activation.sh
```

Preflight:

```bash
scripts/pq-height-20000-preflight.sh \
  --api-url https://testnet-api.chipcoinprotocol.com
```

Post-deployment:

```bash
scripts/pq-height-20000-postdeploy.sh \
  --compose-file docker-compose.yml \
  --node-service node \
  --miner-service miner \
  --api-url http://127.0.0.1:28081
```

## Compatibility warning

Old nodes configured for height `30000` may remain compatible before height
`20000` and while blocks contain only legacy transactions. They can diverge at
the first block between heights `20000` and `29999` that contains a CHCQ output
or transaction v2/ML-DSA spend.

Old nodes do not automatically realign at height `30000` if the active chain
history already contains PQ activity below `30000`.

## Rollback limitations

Before any PQ block below height `30000`, reverting to `30000` is possible only
through another coordinated release. After a PQ block at height `20000..29999`,
do not downgrade individual nodes. Treat the event as a consensus incident,
identify the canonical branch, and coordinate a second release or explicit
reorg plan.

## Operational checklist

- Build the release image.
- Verify activation height inside the image.
- Upgrade bootstrap/seed/API/reward/miner-connected nodes.
- Verify node logs and API status after each restart.
- Verify operational readiness status.
- Update explorer and website countdowns.
- Announce the mandatory testnet upgrade.
- Monitor heights `19999`, `20000`, first CHCQ output, and first CHCQ spend.
