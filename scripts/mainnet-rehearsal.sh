#!/usr/bin/env bash
set -euo pipefail

ROOT="${REHEARSAL_ROOT:-/tmp/chipcoin-mainnet-docker-rehearsal}"
COMPOSE_FILE="docker/compose/docker-compose.mainnet-rehearsal.yml"
PROJECT="chipcoin-mainnet-rehearsal"
MILESTONES=(1 10 100 200 500 999 1000 1099 1100)
FAULT_LOCK="$ROOT/fault/session.lock"

compose() {
  REHEARSAL_ROOT="$ROOT" docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
}

prepare_dirs() {
  mkdir -p "$ROOT"/{secrets,logs,milestones,snapshot}
  for node in node-a node-b node-c node-fullsync node-snapshot; do
    mkdir -p "$ROOT/runtime/$node"
  done
  chmod 700 "$ROOT/secrets"
}

wallet() {
  local name="$1" path="$ROOT/secrets/$1.json"
  [[ -s "$path" ]] && return
  .venv/bin/chipcoin --network mainnet wallet-generate --scheme mldsa44 --wallet-file "$path" \
    >/dev/null 2>/dev/null
  chmod 600 "$path"
}

provision() {
  prepare_dirs
  for name in miner-a miner-b reward-a-owner reward-a-attest reward-b-owner reward-b-attest browser-wallet; do
    wallet "$name"
  done
  npm run build --prefix apps/browser-wallet >"$ROOT/logs/browser-wallet-build.log" 2>&1
  compose config >/dev/null
}

status_json() {
  local service="$1"
  compose exec -T "$service" chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 status
}

state_json() {
  local service="$1"
  compose exec -T "$service" python3 /app/scripts/mainnet-rehearsal-state.py --data /runtime/mainnet/node.sqlite3
}

status() {
  for node in node-a node-b node-c; do
    printf '%s\t' "$node"
    status_json "$node" | jq -c '{height,tip_hash,cumulative_work,mempool_size,handshaken_peer_count,sync_phase}'
  done
}

check_invariants() {
  local expected="" current node
  for node in "$@"; do
    current="$(state_json "$node")"
    jq -e '
      .handshaken_peer_count >= 1 and
      .sqlite.quick_check == ["ok"] and
      .sqlite.foreign_key_check == []
    ' <<<"$current" >/dev/null || {
      printf 'FAIL node health/integrity at %s\n' "$node" >&2
      return 1
    }
    current="$(jq -cS '
      del(
        .handshaken_peer_count,
        .mempool_size,
        .sync_phase,
        .sqlite
      )
    ' <<<"$current")"
    if [[ -z "$expected" ]]; then
      expected="$current"
    elif [[ "$current" != "$expected" ]]; then
      printf 'FAIL consensus invariant divergence at %s\n' "$node" >&2
      diff -u <(jq -S . <<<"$expected") <(jq -S . <<<"$current") >&2 || true
      return 1
    fi
  done
  printf 'PASS consensus invariants %s\n' "$*"
}

record_milestones() {
  local height milestone output
  if [[ -e "$FAULT_LOCK" ]]; then
    printf 'EXPECTED_DIVERGENCE fault-session lock active; milestone recording suppressed\n'
    return 0
  fi
  height="$(status_json node-a | jq -r '.height // -1')"
  for milestone in "${MILESTONES[@]}"; do
    output="$ROOT/milestones/height-$milestone.json"
    if (( height >= milestone )) && [[ ! -e "$output" ]]; then
      for node in node-a node-b node-c; do state_json "$node"; done \
        | jq -s --argjson milestone "$milestone" '{milestone:$milestone,nodes:.}' >"$output"
      jq -e '([.nodes[] | [.height,.tip_hash,.cumulative_work,.utxo_hash,.reward_registry_hash]] | unique | length) == 1' "$output" >/dev/null
    fi
  done
}

case "${1:-}" in
  provision) provision ;;
  start)
    provision
    compose up -d --build node-a node-b node-c miner-a miner-b
    ;;
  status) status; record_milestones ;;
  stop) compose stop ;;
  restart) compose restart node-a node-b node-c miner-a miner-b ;;
  logs) compose logs --tail="${2:-200}" ;;
  check)
    if [[ -e "$FAULT_LOCK" ]]; then
      printf 'EXPECTED_DIVERGENCE fault-session lock active; global invariant shutdown suppressed\n'
      exit 0
    fi
    check_invariants node-a node-b node-c
    record_milestones
    ;;
  fullsync) compose --profile recovery up -d node-fullsync ;;
  snapshot-node) compose --profile recovery up -d node-snapshot ;;
  down) compose down ;;
  *)
    echo "usage: $0 {provision|start|status|stop|restart|logs [N]|check|fullsync|snapshot-node|down}" >&2
    exit 2
    ;;
esac
