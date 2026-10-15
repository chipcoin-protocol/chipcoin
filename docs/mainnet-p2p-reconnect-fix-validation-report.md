# Mainnet P2P Reconnect Fix Validation Report

Date: 2026-10-04

## Decision

The minimum P2P reconnect fix is validated offline. It has not been deployed to
the active mainnet rehearsal. `FAULT-OPS-002` therefore remains `FAIL` until a
controlled rehearsal deployment and a real reconnect test pass without a node
restart.

MemPalace was consulted before implementation for the peer lifecycle,
reconnect/backoff state, and historical networking behavior.

## Root Cause

`protocol_error_class()` did not recognize `socket.gaierror` or several common
OS connectivity errors. Its fallback classified unknown errors as
`malformed_message`. The outbound failure path then:

1. treated temporary DNS failure as protocol misbehavior;
2. reduced peer reputation and increased misbehavior state;
3. selected extended backoff after repeated attempts, disconnects, or score
   degradation;
4. delayed a healthy peer for as long as 21,600 seconds after networking was
   restored.

The permanent connect loop remained alive. The historical
`reconnect_tasks=0` observation was ambiguous because that compatibility field
does not count the permanent `connect` task.

## Code Paths Modified

- `src/chipcoin/node/p2p/errors.py`
  - recognizes DNS resolution, refusal, unreachable host/network, and timeout
    failures as transport/connectivity errors;
  - preserves typed malformed, framing, checksum, invalid block, and invalid
    transaction classifications.
- `src/chipcoin/node/runtime.py`
  - connectivity failures no longer change reputation or misbehavior score;
  - connectivity retry remains bounded by existing configured backoff;
  - extended quarantine remains available for real protocol misbehavior;
  - successful handshake continues to reset attempts/backoff;
  - additive reconnect observability fields were added.
- `tests/node/test_local_node.py`
  - error-taxonomy, penalty, repeated-failure, and malformed-message tests.
- `tests/node/test_runtime_integration.py`
  - repeated DNS failure followed by autonomous resolution/handshake;
  - connection-loss recovery and observability assertions.
- `tests/node/test_runtime_p2p_lifecycle.py`
  - compatibility/additive metric assertions.
- `tests/scripts/mainnet-p2p-reconnect-docker.sh`
  - persistent Docker regression for DNS restoration and historical network
    attachment/cutover ordering.
- `docs/node.md`
  - transport penalty and reconnect metric semantics.

No consensus, chain selection, block/transaction validation, mempool, reward,
database schema, or mainnet parameter code was modified.

## Error Taxonomy

| Error | Before | After | Misbehavior penalty after fix |
|---|---|---|---|
| Temporary DNS/name resolution | `malformed_message` | `connection_failed` | No |
| Connection refused | `connection_failed` | `connection_failed` | No |
| Network/host unreachable | fallback `malformed_message` | `connection_failed` | No |
| Pre-handshake timeout | `timeout` | `timeout` | No |
| Typed malformed frame/payload | `malformed_message` | `malformed_message` | Yes |
| Checksum/framing/protocol violation | protocol-specific | unchanged | Yes where previously enforced |
| Invalid block/transaction | protocol-specific | unchanged | Yes |

The existing protocol protections were not weakened. Only failures attributable
to local/transport availability bypass reputation penalties.

## Backoff Behavior

Connectivity failures retain exponential retry and the existing configured
maximum, normally 30 seconds. They cannot enter the 300–21,600 second extended
quarantine solely because retry count or connectivity disconnect count grows.
This avoids busy-looping while permitting prompt autonomous recovery.

The extended backoff path remains available when the classified failure is
actual peer misbehavior. A successful handshake still resets
`reconnect_attempts=0` and `backoff_until=0`.

A 60-failure regression confirms temporary DNS failures remain bounded at the
configured 30-second ceiling with reputation `0`, no misbehavior score, and no
ban.

## Regression Results

| Validation | Result |
|---|---|
| DNS regression previously strict XFAIL | PASS |
| DNS failure has no malformed penalty | PASS |
| Connection refused has no malformed penalty | PASS |
| Network unreachable has no malformed penalty | PASS |
| Pre-handshake timeout has no malformed penalty | PASS |
| Actual malformed message remains penalized | PASS |
| Repeated DNS failure, retry, restore, handshake | PASS |
| Handshake resets retry/backoff | PASS |
| No node restart during reconnect | PASS |

The integration test performs three DNS failures, restores resolution, and
observes an autonomous handshake from the same runtime. No ban or misbehavior
score is created.

## Docker Validation

Image: `chipcoin-p2p-reconnect-fix`

Evidence: `/tmp/chipcoin-p2p-reconnect-261035554/report.tsv` and adjacent node
logs.

Results:

- DNS absent at node start, then restored: PASS;
- autonomous handshake without restart: PASS;
- malformed penalty derived from DNS: absent;
- historical sequence `shared -> fault attach -> shared disconnect -> shared
  reattach -> fault detach`: PASS in three consecutive cycles;
- reconnect durations: 2 seconds, 3 seconds, 2 seconds;
- at least one handshaken peer after every restoration: PASS;
- node containers/process identities retained: PASS.

The short container pause in each historical-sequence cycle forces the existing
TCP session to expire after Docker detaches the shared endpoint. It does not
restart either node.

## Observability And Compatibility

`reconnect_tasks` is retained unchanged for compatibility and is now explicitly
documented as counting only short-lived tasks in the `reconnect` category.
These additive fields distinguish the actual lifecycle:

- `connect_loops`;
- `active_connection_attempts`;
- `backed_off_peer_count`;
- `next_reconnect_at`.

They are emitted by the existing runtime metrics log/snapshot. Existing API
fields were not removed or changed, so Explorer, monitoring, and status clients
remain compatible. Harness tests confirm the existing interfaces still parse.

The error taxonomy and runtime path are network-agnostic. There is no mainnet
conditional behavior.

## Test Results

| Suite | Result |
|---|---|
| Targeted taxonomy/backoff tests | 9 PASS |
| Targeted DNS integration | 2 PASS |
| Complete node suite | 427 PASS |
| Mainnet profile and configuration suite | 45 PASS |
| Harness/script regression suite | 87 PASS |
| Docker reconnect regression | PASS, 3 historical cycles |
| `git diff --check` | PASS |
| Shell syntax | PASS |

The complete node suite covers existing testnet and mainnet node behavior. The
mainnet profile/configuration suite separately confirms that the P2P-only change
does not alter frozen consensus parameters.

## Deployment Gate

- Offline fix validation: PASS
- Deployed to active rehearsal: NO
- Real rehearsal reconnect after deployment: NOT_RUN
- `FAULT-OPS-002`: remains FAIL
- Scenario B: not restarted
- SIGKILL: not executed

P2P_FIX_VALIDATED = YES
