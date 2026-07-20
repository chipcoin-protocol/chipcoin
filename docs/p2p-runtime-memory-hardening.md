# P2P Runtime Memory Hardening

This note documents the P2P runtime memory hardening added after a public
testnet node reached multi-GB RSS during prolonged handshake/reconnect churn.

## Finding

The audit did not identify one proven append-only leak that alone explains the
OOM. It did identify a concrete unbounded pressure mode:

- inbound sessions are inserted into `NodeRuntime._sessions` before handshake
  completion;
- each accepted session owns a runtime session task plus protocol reader and
  temporary handshake wait tasks;
- `max_inbound_sessions` bounds total open inbound sessions, but there was no
  separate concurrent pending-handshake limit per source IP;
- one source IP using many ephemeral ports could consume the pending handshake
  budget until timeout, repeatedly creating task and stream pressure;
- if a session task was cancelled outside the normal runtime shutdown path, the
  session was removed from `_sessions` but the transport was not explicitly
  closed on that cancellation path.

The normal add/remove path is:

- add: `_handle_inbound_connection()` creates `PeerProtocol`, stores it in
  `_sessions`, then spawns `_run_session()`;
- timeout/read EOF/protocol error: `PeerProtocol.start()` or `_reader_loop()`
  calls `close()`, then `_run_session()` reaches `finally`;
- remove: `_run_session()` calls `_drop_session()`, which removes `_sessions`,
  releases sync requests, updates peer observation, removes node-id session
  indexes, and updates sync status;
- shutdown: `NodeRuntime.stop()` closes sessions, cancels tracked tasks, awaits
  them with `gather(..., return_exceptions=True)`, and clears runtime maps.

## Mitigation

The runtime now adds explicit bounds and cleanup:

- `MAX_PENDING_HANDSHAKES`: global concurrent pending-handshake cap;
- `MAX_PENDING_HANDSHAKES_PER_IP`: concurrent pending-handshake cap per source
  IP;
- limits are checked before creating a `PeerProtocol` or spawning a session
  task;
- inbound handshake attempt buckets are pruned even when a host never reconnects;
- session task cancellation explicitly closes the session before removing it;
- protocol handshake wait tasks are cancelled and awaited;
- runtime task tracking consumes/logs task exceptions and removes category state;
- peer aliases are pruned per `node_id` without removing configured, canonical,
  or currently connected endpoints.

## Metrics

Every `MEMORY_METRICS_INTERVAL_SECONDS` seconds, unless set to `0`, the runtime
logs a structured line:

```text
runtime memory metrics rss_mb=118.42 asyncio_tasks=16 sessions_total=5 sessions_handshaken=5 pending_handshakes=0 inbound_pending=0 outbound_pending=0 tracked_tasks=5 reconnect_tasks=0 peerbook_entries=117 aliases_total=3 queue_sizes={'pending_outbound_peers': 0, 'recent_peer_txids': 42, 'relayed_mempool_txids': 0, 'peer_resolution_cache': 9} inbound_sessions=1 outbound_sessions=4 sessions_created=82 sessions_closed=77
```

`aliases_total` counts extra peerbook entries that share the same `node_id`
beyond the first record.

Optional allocation growth diagnostics can be enabled with:

```bash
TRACEMALLOC_ENABLED=true
TRACEMALLOC_TOP_LIMIT=5
```

This is disabled by default because it adds diagnostic overhead.

## Operational Defaults

Recommended starting values for public testnet:

```env
MAX_INBOUND_SESSIONS=32
MAX_PENDING_HANDSHAKES=32
MAX_PENDING_HANDSHAKES_PER_IP=4
MAX_PEER_ALIASES_PER_NODE_ID=4
MEMORY_METRICS_INTERVAL_SECONDS=60
TRACEMALLOC_ENABLED=false
CHIPCOIN_MEMORY_LIMIT=2g
```

`CHIPCOIN_MEMORY_LIMIT` is a Docker guardrail, not a fix by itself. Validate the
value in testnet telemetry before tightening it.

## Monitoring

Useful commands:

```bash
docker stats chipcoin-testnet-node-1
docker inspect chipcoin-testnet-node-1 --format '{{.RestartCount}}'
docker compose logs node | grep 'runtime memory metrics'
docker compose ps
```

Watch for sustained growth in:

- `pending_handshakes`;
- `tracked_tasks`;
- `sessions_total - sessions_handshaken`;
- `peerbook_entries`;
- `aliases_total`;
- Docker restart count.

## Limitations

This hardening bounds known P2P runtime structures and adds diagnostics. It does
not prove that every possible allocator growth path is eliminated. If RSS still
grows while counters remain stable, enable tracemalloc temporarily and compare
the logged growth sites.
