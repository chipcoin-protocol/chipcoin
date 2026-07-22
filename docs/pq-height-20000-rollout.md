# PQ Height 20000 Testnet Rollout Runbook

## Executive Summary

Chipcoin testnet Post-Quantum activation is scheduled at height `20000` in
release `0.1.2`. This is a mandatory testnet consensus upgrade. The release
does not change wire format, transaction serialization, CHCQ addresses, ML-DSA
keys/signatures, PoW, rewards, wallet key format, or browser wallet PQ feature
flags.

MemPalace was consulted for this rollout task. No project memory with a more
specific rollout decision was found, so this runbook follows the local source
tree and release instructions.

## Release Version

Python package and node user-agent version: `0.1.2`.

The browser wallet package remains `0.1.1` because the mandatory consensus
upgrade is in the Python node/miner/API package. Browser PQ signing and send
remain disabled.

## Images to Build

The repository uses one Dockerfile for both the `node` and `miner` compose
services. Any service built from this image includes the consensus code.

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

docker image inspect chipcoin-testnet-node:$VERSION \
  --format 'id={{.Id}} revision={{index .Config.Labels "org.opencontainers.image.revision"}} version={{index .Config.Labels "org.opencontainers.image.version"}}'

docker run --rm chipcoin-testnet-node:$VERSION \
  chipcoin verify-pq-activation --network testnet --expected-height 20000
```

Do not `docker push` from this preparation task.

## Compose Services and Volumes

Repository compose services:

- `node`: consensus-critical full node and HTTP API.
- `miner`: mining worker using templates from a node endpoint.

Persistent data is mounted through configured runtime/wallet bind paths:

- `CHIPCOIN_RUNTIME_DIR` for node state;
- `NODE_DATA_PATH` inside the runtime directory;
- `MINER_WALLET_FILE` mounted read-only into the miner container.

Never use `docker compose down -v` for this rollout. Do not delete databases,
wallets, or runtime directories.

## Component Matrix

| Component | Contains consensus | Update mandatory | Restart | Verification |
| --- | --- | --- | --- | --- |
| bootstrap node | yes | yes, consensus-critical | yes | `verify-pq-activation`, API status, peers |
| seed node | yes | yes, consensus-critical | yes | `verify-pq-activation`, public peer list |
| public API node | yes | yes, consensus-critical | yes | `/v1/status`, operational dashboard |
| reward node | yes | yes, consensus-critical | yes | activation verifier, reward status |
| miner-connected node | yes | yes, consensus-critical | yes | template and block submission checks |
| standalone miner | maybe, if image includes code | yes when built from this repo | yes | image version and connected node template |
| browser wallet | no consensus | display-only | release optional | build, PQ flag false |
| explorer | no consensus | display-only | deploy optional | countdown, badges, API consistency |
| website | no consensus | display-only | deploy optional | Post-Quantum pages updated |
| snapshot service | yes if producing snapshots | operational-critical | yes | package version, snapshot metadata |
| daily report | yes if imports package | operational-critical | restart/redeploy | activation height and ETA |
| operational dashboard | no consensus | operational-critical | redeploy if hosted | `activation_height=20000` |

## Safe Rollout Order

1. Back up server configuration.
2. Back up node database or create a coherent snapshot.
3. Pull the release commit.
4. Verify `git rev-parse --short HEAD`.
5. Run `scripts/pq-height-20000-preflight.sh --api-url <api-url>`.
6. Build the Docker image with version and revision labels.
7. Verify activation height inside the image.
8. Stop the target service in a controlled way, or use compose recreate.
9. Recreate without deleting volumes:

   ```bash
   docker compose up -d --build --force-recreate node
   docker compose up -d --build --force-recreate miner
   ```

10. Verify logs and health.
11. Run `scripts/pq-height-20000-postdeploy.sh`.
12. Verify API height, sync state, peers, and miner.
13. Move to the next host.

## Preflight Commands

```bash
python -m chipcoin.tools.verify_pq_activation \
  --network testnet \
  --expected-height 20000

python -m chipcoin.tools.verify_pq_activation \
  --network devnet \
  --expected-height 30000

scripts/pq-height-20000-preflight.sh \
  --api-url https://testnet-api.chipcoinprotocol.com
```

## Post-Deployment Commands

```bash
scripts/pq-height-20000-postdeploy.sh \
  --compose-file docker-compose.yml \
  --node-service node \
  --miner-service miner \
  --api-url http://127.0.0.1:28081

curl -s http://127.0.0.1:28081/v1/status | jq \
  '{height, sync_phase, handshaken_peer_count, operational_peer_count}'
```

## Server Verification

On a deployed host:

```bash
CHIPCOIN_ROOT=/opt/chipcoin \
CHIPCOIN_PYTHON=/opt/chipcoin/.venv/bin/python \
CHIPCOIN_NETWORK=testnet \
EXPECTED_PQ_HEIGHT=20000 \
/opt/chipcoin/scripts/verify-pq-activation.sh
```

The output must include:

```text
Network: testnet
PQ activation height: 20000
Expected: 20000
Status: PASS
```

## Monitoring Windows

Run the operational readiness dashboard and record outputs:

- immediately after deployment;
- 1000 blocks before activation;
- 100 blocks before activation;
- 10 blocks before activation;
- height `19999`;
- height `20000`;
- first 10 blocks after activation;
- first CHCQ output;
- first CHCQ spend;
- 100 blocks after activation.

Track:

- current height;
- blocks remaining;
- median block interval;
- estimated activation time;
- peer count;
- height spread;
- reorg depth;
- orphan/rejected blocks;
- mempool PQ transaction count;
- PQ verify count and failures;
- PQ block sigop cost;
- active miner IDs;
- reward node status;
- API/explorer consistency.

## First Public PQ Transaction Plan

Do not execute this during rollout preparation.

1. Wait until height `20000` is confirmed.
2. Verify all controlled nodes are synced.
3. Verify operational dashboard status.
4. Create a small CHC -> CHCQ output from a test wallet.
5. Wait for confirmations.
6. Verify API and explorer metadata.
7. Spend that CHCQ output to CHC or CHCQ.
8. Wait for confirmations.
9. Verify ML-DSA signature metadata.
10. Archive txid, block height, dashboard report, and logs.

## Chipcom Manual Checklist

- Confirm commit `e361ae4` or later is checked out.
- Confirm release commit contains `Prepare PQ height 20000 testnet rollout`.
- Run `scripts/pq-height-20000-preflight.sh`.
- Build image `chipcoin-testnet-node:0.1.2`.
- Verify image activation height.
- Back up `/opt/chipcoin` config and runtime path.
- Recreate `node` without deleting volumes.
- Recreate `miner` if it is built from the same repo image.
- Run postdeploy script.
- Confirm memory metrics are stable.
- Confirm `/v1/status` is synced.
- Confirm peers are operational.
- Confirm dashboard does not report a critical failure.
- Do not submit PQ transactions before height `20000`.

## External Components Pending

See `docs/pq-height-20000-external-services-checklist.md` for explorer,
website, daily report, dashboard, and snapshot-service checks.

## Residual Risks

- Peer software version distribution may be unavailable until user agents are
  surfaced in public diagnostics.
- An old miner-connected node can mine only legacy-compatible blocks but can
  reject the first PQ block below `30000`.
- Explorer or website countdowns can lag the consensus release if deployed
  separately.
- Public API may show old behavior until its host is upgraded.
