# Mainnet P2P Reconnect Live Validation Report

Date: 2026-10-04

## Result

- P2P live validation: **PASS**
- `FAULT-OPS-002`: **PASS**
- Restart required: **NO**
- Scenario B executed: **NO**
- SIGKILL executed: **NO**

MemPalace was consulted for the operational lifecycle before deployment. All
runtime evidence is stored under:

`/tmp/chipcoin-mainnet-docker-rehearsal/fault/evidence/p2p-live-20261004T211744Z/`

## Pre-Deployment Baseline

Accepted checkpoint:

`/tmp/chipcoin-mainnet-docker-rehearsal/fault/evidence/baseline-20261004T211744Z/`

| Field | A/B/C value |
|---|---|
| Height | 191 |
| Tip | `00000005693cb991d3592676a2f2fb9775cb27e3e740bf25a01d6d81db952a13` |
| Cumulative work | 42072513408 |
| Materialized supply | 960000000000 chipbits |
| UTXO count | 195 |
| UTXO hash | `8ab6dd7d1fb05d9d1a2c6a2caf2591a9e6977d793c786f8410acd65c324d5318` |
| Mempool | 0 |
| Handshaken peers per node | 2 |
| Reward registry hash | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| SQLite quick/FK | `ok` / empty |

Selected wallet balances and all seven wallet checksums were captured. The
same checksums matched after deployment and live validation.

## Build And Scope

- Git commit: `586160840a568eb64a1d4aa2b1c909805386cb2c`
- P2P diff SHA-256: `aaa0b08d08c8a51fab3ad7a185755be3d16d571f5b4fea9d9c34f630693bfc13`
- Dependency manifest SHA-256: `5c3992124063f85c84e5ac25cb85404543d0da93abc3b0c6eac6cf12c169af81`
- Image ID: `sha256:720ea695c75fd9aee8637c2e5a1993c06858b55491c2a51d1a7d9093a168ee9d`
- Registry digest: not available; image was built and used locally only.

A complete installed-package checksum comparison between the old rehearsal
image and the new image found exactly two changed Python files:

- `chipcoin/node/p2p/errors.py`
- `chipcoin/node/runtime.py`

No unrelated runtime module entered the deployment.

## Rolling Deployment

The nodes were recreated individually using the same runtime directories and
databases, without DB copy, resync from zero, tip manipulation, wallet change,
or simultaneous outage:

| Step | Result | Image | Recovery |
|---|---|---|---|
| node-c | PASS | `sha256:720ea6...ee9d` | Two P2P handshakes, converged |
| node-b | PASS | `sha256:720ea6...ee9d` | Two P2P handshakes, converged |
| node-a | PASS | `sha256:720ea6...ee9d` | Two P2P handshakes, converged |

After every step the global monitor check returned PASS. The miners remained
running throughout.

The new runtime metrics were present immediately after each node start:

- `connect_loops=1`;
- `active_connection_attempts` reflected startup dialing;
- `backed_off_peer_count=0` after successful connection;
- `next_reconnect_at=None` after successful connection.

## Live Connectivity Test

Target: `node-c`, which does not host either miner.

Method:

1. Attach node-c to a dedicated internal validation network.
2. Disconnect node-c from the shared rehearsal network.
3. Briefly pause and resume the same container process so established TCP
   sessions expire; the node was not restarted and its DB was untouched.
4. Keep node-a, node-b, miner-a, and miner-b on the shared topology.
5. Restore node-c to the shared network and remove the validation attachment.

The ordinary milestone monitor was frozen with systemd during this intentional
single-node isolation because height 200 was approaching. It was thawed after
global convergence and remained active/running. No fault lock, Scenario B
partition, or two-miner branch split was created.

## Peer State And Metrics

### Before

- handshaken peers: 2;
- node-a/node-b score: 3;
- misbehavior score: null;
- penalty reason: null;
- reconnect attempts: 0;
- backoff: 0.

### During isolation

- handshaken peers: 0;
- `connect_loops=1`;
- `active_connection_attempts=0` at the sampled instant;
- `backed_off_peer_count=2`;
- `next_reconnect_at=1791149120`;
- configured peers classified `connection_failed`;
- reconnect attempts observed: node-a 3, node-b 5;
- node-a/node-b reputation score remained 3;
- misbehavior score remained null;
- penalty reason remained null;
- no DNS/connectivity log combined with `malformed_message`.

This directly resolves the historical observability ambiguity: although
`reconnect_tasks=0`, the permanent `connect_loops=1`, explicit backed-off peer
count, and next retry timestamp proved that autonomous reconnect activity was
still scheduled.

### After restoration

- first handshake latency: **913 ms** from network restoration;
- restart required: NO;
- final handshaken peers: 2;
- reconnect attempts: 0 for both configured peers;
- backoff: 0 for both configured peers;
- backed-off peer count: 0;
- peer scores increased normally to 4 after successful handshakes;
- misbehavior score and penalty reason remained null;
- peer health: `ok`.

## Final Convergence

| Field | A/B/C value |
|---|---|
| Height | 193 |
| Tip | `00000006a3c6a6ac3bbb1af348e4c6b32d3f5f88af9ce53fac37a83ba6c2bb93` |
| Cumulative work | 42510768756 |
| Materialized supply | 970000000000 chipbits |
| UTXO count | 197 |
| UTXO hash | `8ceb616af95af0736f40959c404a148c0a77a02726cf920122c22810b2c1303a` |
| Mempool | 0 |
| Handshaken peers per node | 2 |
| Reward registry hash | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| SQLite quick/FK | `ok` / empty |

Both miners are running on the shared network. All nodes use the same new image,
the temporary validation network was removed, the ordinary monitor is active,
and wallet checksums are unchanged.

## RC Decision

The live rehearsal demonstrates autonomous recovery after real connectivity and
name-resolution loss without restart, malformed penalty, long isolation,
database inconsistency, or consensus divergence.

`FAULT-OPS-002`: **FAIL -> PASS**

`CONS-RUN-005` and `FAULT-RUN-012` remain `NOT_RUN`.

P2P_LIVE_VALIDATION = PASS

FAULT_OPS_002 = PASS
