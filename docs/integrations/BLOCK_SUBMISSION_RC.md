# Block submission release candidate: isolated evaluation

Status: this document records the earlier pool-only candidate. The later combined candidate remains local and requires its own external validation; see [integrated readiness](MAINNET_INTEGRATED_RC_READINESS.md). No production deployment or public release is implied.

## Changelog

- Adds complete serialized-block submission to the existing `POST /mining/submit-block` endpoint when `template_id` is omitted.
- Preserves the legacy `template_id` request contract and 15-second TTL. New mempool transactions no longer erase existing jobs. A 256-record cap bounds outstanding jobs; the oldest is evicted when the cap is exceeded.
- Reports full-block storage, active-chain inclusion, and validation state separately. Uses existing fork choice for side branches. Checks the actual ingest result and storage before reporting success.
- Recognizes active-chain retries as `already_accepted` and stored side branches as `known_side_branch`. A relay error after commit is returned with `relay_failed=true` rather than hiding the stored block.
- Adds isolated regression tests for mempool changes, TTL, invalid PoW/merkle/bits/coinbase, concurrent retries, side branches, reorgs, and post-commit response loss.

The implementation changes the API, service, and runtime only. It changes no consensus, genesis, reward, serialization, wallet, or database schema module.

Local test record on 2026-11-23: 79 pool/API/native-miner tests passed from the isolated source copy; four selected real-TCP runtime integration tests passed with local bind permission. The complete release gate remains open.

## Identify and reproduce the local candidate

The maintainer's local tag `pool-submit-rc1` resolves to the candidate commit. Verify the archive against the separately delivered `SHA256SUMS` file before using it. The archive includes only committed source; no production data or secrets are included.

```sh
git rev-parse pool-submit-rc1^{commit}
git archive --format=tar pool-submit-rc1 | gzip -n > chipcoin-pool-submit-rc1.tar.gz
sha256sum chipcoin-pool-submit-rc1.tar.gz
```

Build with the repository's pinned Dockerfile and `docker/requirements-build.lock` after unpacking the archive:

```sh
mkdir chipcoin-pool-submit-rc1
tar -xzf chipcoin-pool-submit-rc1.tar.gz -C chipcoin-pool-submit-rc1
cd chipcoin-pool-submit-rc1
docker build --build-arg SOURCE_DATE_EPOCH=1792069138 -t chipcoin:pool-submit-rc1 .
```

Do not run this image against an existing Mainnet volume. For isolated smoke testing with a fresh Devnet database, bind the HTTP API only to loopback and do not configure bootstrap or public P2P ports:

```sh
mkdir -m 700 data
docker run --rm --network none -v "$PWD/data:/data" chipcoin:pool-submit-rc1 \
  chipcoin --network devnet --data /data/devnet.sqlite3 run \
  --listen-host 127.0.0.1 --listen-port 0 --http-host 127.0.0.1 --http-port 8080 --run-seconds 30
```

The Docker command above runs inside a network-isolated container; its HTTP port is not published. For interactive API testing, use a private Docker network and explicit loopback port binding only after verifying the deployment's isolation. No instruction here uses production node volumes.

Devnet's CHCQ/v2 activation is height 30,000; early Devnet mining tests cannot establish Mainnet PQ compatibility. The separate policy test uses unchanged Mainnet parameters and synthetic test addresses, but does not prove a Mainnet block submission.

## Test command

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e . pytest
.venv/bin/pytest -q tests/integration/pool/test_block_submission.py tests/node/test_http_api.py tests/miner/test_worker.py tests/node/test_runtime_integration.py
```

Editable installation compiles the repository's native ML-DSA module and therefore requires a C compiler and Python development headers. The Docker build includes build tools only in the builder stage. Record the candidate commit, archive digest, image ID, test results, and operating system when sharing results.

## Open gate

This candidate is for isolated review. The complete T1–T12 matrix, real pool end-to-end tests, resource-limit review, Mainnet PQ vectors, and maintainer approval remain open. See [POOL_PRERELEASE_TEST_PLAN.md](POOL_PRERELEASE_TEST_PLAN.md) and [BLOCK_SUBMISSION_ROLLOUT.md](BLOCK_SUBMISSION_ROLLOUT.md).
