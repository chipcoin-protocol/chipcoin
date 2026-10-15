# Mainnet P2P Reconnect Reliability Report

Date: 2026-10-04

## Scope And Decision

This audit covers `FAULT-OPS-002`: recovery of outbound P2P connectivity after
a temporary network partition without restarting the node. MemPalace was
consulted for the peer lifecycle, persisted peer fields, and reconnect/backoff
configuration before the code and retained runtime evidence were analyzed.

Result: **FAIL / RC BLOCKER**. The permanent connect loop remains alive, but a
temporary DNS failure is classified as peer `malformed_message` misbehavior.
Repeated transport failures can therefore lower the peer score, ban the peer,
and select extended retry delays up to six hours. The historical controlled
restart cleared the in-memory delay and caused immediate recovery; it did not
repair consensus state.

No node, consensus, P2P, database, or rehearsal configuration was changed by
this audit.

## Static Audit

The outbound lifecycle is:

1. `NodeRuntime.start()` creates one long-lived `_connect_loop()` task in the
   `connect` task category.
2. `_connect_loop()` periodically obtains desired outbound peers, skips active,
   banned, or backoff-delayed peers, and calls `_connect_outbound()`.
3. A successful handshake resets `reconnect_attempts` and `backoff_until`.
4. A failed dial calls `_register_peer_failure()`, which classifies the error,
   persists retry state, and may apply peer-misbehavior penalties.
5. Normal exponential backoff is capped by the configured 30 seconds. Extended
   backoff starts at 20 attempts, 20 disconnects, or score `<= -100`; it starts
   at 300 seconds and is capped at 21,600 seconds (six hours).

There is no maximum retry count and the connect loop does not intentionally
terminate after repeated failures. However, `protocol_error_class()` maps an
unrecognized `socket.gaierror`, including `Temporary failure in name
resolution`, to `malformed_message`. `_should_penalize_as_misbehavior()` then
treats that transport failure as hostile peer behavior. This mixes network
availability with protocol misconduct and selects the extended backoff path.

The runtime metric named `reconnect_tasks` counts tasks in the `reconnect`
category. The permanent dialer is in the `connect` category. Consequently,
`reconnect_tasks=0` does not prove that reconnect scheduling has stopped. It is
an observability mismatch; the historical node still had its connect loop but
the peer was deferred by persisted/in-memory backoff.

## Historical Evidence

Preserved evidence was read from:

- `/tmp/chipcoin-mainnet-docker-rehearsal/fault/evidence/logs/recovery-start-20261004T144634Z.log`
- `/tmp/chipcoin-mainnet-docker-rehearsal/fault/scenario-b-recovery-freeze-20261004T145731Z/`

The logs show repeated entries equivalent to:

```text
event=malformed_message
last_error=[Errno -3] Temporary failure in name resolution
```

Attempts became progressively separated by approximately 5, 10, 20, 40, and
80 minutes. The peer reached score `-100` with 57 reconnect attempts, selecting
extended backoff. At the recovery freeze, node A had zero handshaken peers,
while B/C were connected and their SQLite checks were clean. Runtime metrics
still reported six tracked tasks, which is consistent with a live background
connect loop; `reconnect_tasks=0` was the category mismatch described above.

The event that prevented prompt reconnection was therefore not cancellation of
the dialer. Docker DNS became unavailable during isolation, DNS errors were
penalized as malformed peer traffic, and the resulting score/attempt history
deferred the next dial after shared connectivity returned. A controlled restart
was required for immediate recovery in that incident. Without a restart, a
retry could be delayed for as long as six hours.

## Regression Results

Targeted host integration tests completed as follows:

| Test | Result | Observation |
|---|---|---|
| Peer initially unreachable, then available | PASS | Autonomous handshake without restart. |
| Established peer lost, then restored | PASS | Autonomous handshake in the short-backoff case. |
| Total loss with two peers, peers restored | PASS | At least one handshake recovered; permanent `connect` task remained alive while `reconnect_tasks` remained zero. |
| DNS failure is transport failure, not misbehavior | XFAIL (strict) | Reproduces the defect: `socket.gaierror` is currently classified as `malformed_message`. |

The three reconnect integration tests passed in 62.05 seconds. The strict
expected-failure test is intentionally not a PASS: it is the executable
regression specification for the node fix that has not been authorized.

Coverage of the requested cases:

| Case | Result |
|---|---|
| A. Temporarily unreachable peer returns | PASS, short backoff |
| B. Established connection, loss, restore | PASS, short backoff |
| C. DNS/IP endpoint changes | BUG CONFIRMED for DNS failure classification |
| D. Multiple retry/backoff attempts | PARTIAL: retries continue, but extended delay is unsafe |
| E. Reconnect task terminates/cancels | PASS: permanent connect loop remained alive |
| F. Zero peers plus zero reconnect tasks | EXPLAINED: metric omits the `connect` loop and can coexist with backoff |
| G. Peer returns after normal backoff | PASS |
| H. Two peers return after total loss | PASS for autonomous recovery to at least one handshake; another peer may remain deferred |

## Docker Reproduction

The isolated Docker test uses independent node containers and reproduces the
same shared-network to fault-network attachment sequence without touching the
mainnet rehearsal. It established the initial handshake and reproduced DNS
failures being logged and scored as `malformed_message`.

Docker endpoint disconnect did not tear down the already established TCP flow
in that test environment, so the exact zero-peer transition was not completed:
the session remained visible while outbound DNS retries failed. This is a
limitation of that ephemeral disconnect mechanism, not evidence of correct node
behavior. The preserved rehearsal evidence supplies the actual zero-peer case
and the Docker run independently confirms the faulty DNS classification.

No node restart was used in the ephemeral test. All temporary containers and
networks were removed by its cleanup trap.

## Root Cause And Action

Root cause classification: **peer-manager lifecycle/reliability bug**, with an
additional observability defect. It is not expected configuration, a consensus
failure, or solely an harness network-restoration issue.

Minimum proposed node fix, not applied:

1. Classify `socket.gaierror`, DNS lookup failures, `ENETUNREACH`, and
   `EHOSTUNREACH` as transport `connection_failed` errors.
2. Never apply peer-misbehavior score or bans to local DNS/network availability
   failures.
3. Keep transport retry delay bounded by the configured connection backoff;
   reserve extended penalties for authenticated protocol misconduct.
4. Expose connect-loop health, next retry time, and backoff reason separately
   from `reconnect_tasks`.
5. Make the strict DNS regression pass and add a Docker test that forcibly
   closes established sessions before restoring connectivity.

The node can remain healthy with zero peers and no immediately scheduled dial
for up to six hours after connectivity returns. That violates the mainnet RC
reconnect requirement. `FAULT-OPS-002` must remain failed until the node change
is separately approved, implemented, and validated.

## RC State

- `FAULT-OPS-001`: PASS
- `FAULT-OPS-002`: FAIL
- `CONS-RUN-005`: NOT_RUN
- `FAULT-RUN-012`: NOT_RUN
- Restart required for the historical immediate recovery: YES
- Node bug demonstrated: YES
- Consensus/state blocker demonstrated: NO

P2P_RC_BLOCKER_CONFIRMED
