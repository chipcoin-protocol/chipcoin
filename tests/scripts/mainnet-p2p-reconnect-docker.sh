#!/usr/bin/env bash
set -euo pipefail

IMAGE="${CHIPCOIN_P2P_TEST_IMAGE:-chipcoin-p2p-reconnect-fix}"
SUFFIX="${RANDOM}${RANDOM}"
ROOT="/tmp/chipcoin-p2p-reconnect-$SUFFIX"
SHARED="chipcoin-p2p-shared-$SUFFIX"
FAULT_A="chipcoin-p2p-fault-a-$SUFFIX"
FAULT_B="chipcoin-p2p-fault-b-$SUFFIX"
NODE_A="chipcoin-p2p-a-$SUFFIX"
NODE_B="chipcoin-p2p-b-$SUFFIX"
REPORT="$ROOT/report.tsv"

cleanup() {
  docker unpause "$NODE_A" >/dev/null 2>&1 || true
  docker unpause "$NODE_B" >/dev/null 2>&1 || true
  docker logs "$NODE_A" >"$ROOT/node-a.log" 2>&1 || true
  docker logs "$NODE_B" >"$ROOT/node-b.log" 2>&1 || true
  docker rm -f "$NODE_A" "$NODE_B" >/dev/null 2>&1 || true
  docker network rm "$FAULT_A" "$FAULT_B" "$SHARED" >/dev/null 2>&1 || true
}
trap cleanup EXIT

mkdir -p "$ROOT"
docker network create --internal "$SHARED" >/dev/null
docker network create --internal "$FAULT_A" >/dev/null
docker network create --internal "$FAULT_B" >/dev/null

run_node() {
  local name="$1" alias="$2" peer="$3"
  docker run -d --name "$name" --entrypoint /usr/local/bin/chipcoin-entrypoint \
    --network "$SHARED" --network-alias "$alias" \
    --tmpfs /runtime:rw,mode=1777 \
    -e CHIPCOIN_NETWORK=mainnet \
    -e NODE_DATA_PATH=/runtime/node.sqlite3 \
    -e NODE_LOG_LEVEL=INFO \
    -e NODE_P2P_BIND_PORT=8333 \
    -e NODE_HTTP_BIND_PORT=8080 \
    -e NODE_DIRECT_PEERS="$peer" \
    -e PEER_DISCOVERY_ENABLED=false \
    -e CONNECT_INTERVAL_SECONDS=0.5 \
    -e PING_INTERVAL_SECONDS=0.5 \
    -e P2P_READ_TIMEOUT_SECONDS=2 \
    -e P2P_WRITE_TIMEOUT_SECONDS=2 \
    -e PEER_RETRY_BACKOFF_BASE_SECONDS=1 \
    -e PEER_RETRY_BACKOFF_MAX_SECONDS=3 \
    -e MEMORY_METRICS_INTERVAL_SECONDS=1 \
    "$IMAGE" node >/dev/null
}

peer_count() {
  docker exec "$1" chipcoin --network mainnet --data /runtime/node.sqlite3 status 2>>"$ROOT/status-errors.log" \
    | jq -r '.handshaken_peer_count // 0' 2>>"$ROOT/status-errors.log"
}

wait_for_count() {
  local node="$1" expected="$2" timeout="$3" start now count
  start="$(date +%s)"
  while true; do
    count="$(peer_count "$node" 2>/dev/null || printf 0)"
    if [[ "$expected" == positive && "$count" -gt 0 ]]; then return 0; fi
    if [[ "$expected" == zero && "$count" -eq 0 ]]; then return 0; fi
    now="$(date +%s)"
    if (( now - start >= timeout )); then
      printf 'FAIL\ttimeout\tnode=%s\texpected=%s\tcount=%s\n' "$node" "$expected" "$count" >>"$REPORT"
      return 1
    fi
    sleep 1
  done
}

wait_for_log() {
  local node="$1" pattern="$2" timeout="$3" start
  start="$(date +%s)"
  until docker logs "$node" 2>&1 | grep -q "$pattern"; do
    if (( $(date +%s) - start >= timeout )); then
      printf 'FAIL\tmissing_log\tnode=%s\tpattern=%s\n' "$node" "$pattern" >>"$REPORT"
      return 1
    fi
    sleep 1
  done
}

assert_no_dns_malformed_penalty() {
  local node="$1"
  if docker logs "$node" 2>&1 | grep 'Temporary failure in name resolution' | grep -q 'malformed_message'; then
    printf 'FAIL\tdns_malformed_penalty\tnode=%s\n' "$node" >>"$REPORT"
    return 1
  fi
  printf 'PASS\tdns_no_malformed_penalty\tnode=%s\n' "$node" >>"$REPORT"
}

# DNS unavailable first, then restored. Node A must recover without restart.
run_node "$NODE_A" node-a node-b:8333
wait_for_log "$NODE_A" 'Temporary failure in name resolution' 30
run_node "$NODE_B" node-b node-a:8333
wait_for_count "$NODE_A" positive 30
assert_no_dns_malformed_penalty "$NODE_A"
printf 'PASS\tdns_restore_reconnect\tpeer_count=%s\n' "$(peer_count "$NODE_A")" >>"$REPORT"

# Match the fault harness ordering. A short process pause forces the old TCP
# session to expire while preserving both node containers and process identity.
for cycle in 1 2 3; do
  docker network connect --alias node-a "$FAULT_A" "$NODE_A"
  docker network connect --alias node-b "$FAULT_B" "$NODE_B"
  docker network disconnect "$SHARED" "$NODE_A"
  docker network disconnect "$SHARED" "$NODE_B"
  docker pause "$NODE_B" >/dev/null
  sleep 8
  docker unpause "$NODE_B" >/dev/null
  wait_for_count "$NODE_A" zero 30
  restored="$(date +%s)"
  docker network connect --alias node-a "$SHARED" "$NODE_A"
  docker network connect --alias node-b "$SHARED" "$NODE_B"
  docker network disconnect "$FAULT_A" "$NODE_A"
  docker network disconnect "$FAULT_B" "$NODE_B"
  wait_for_count "$NODE_A" positive 30
  reconnected="$(date +%s)"
  assert_no_dns_malformed_penalty "$NODE_A"
  assert_no_dns_malformed_penalty "$NODE_B"
  printf 'PASS\thistorical_cycle=%s\treconnect_seconds=%s\tpeer_count=%s\n' \
    "$cycle" "$((reconnected-restored))" "$(peer_count "$NODE_A")" >>"$REPORT"
done

printf 'PASS\tresult\treport=%s\n' "$REPORT"
cat "$REPORT"
