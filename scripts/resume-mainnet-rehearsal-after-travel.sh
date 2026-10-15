#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
RUNTIME_ROOT="${REHEARSAL_ROOT:-/tmp/chipcoin-mainnet-docker-rehearsal}"
BACKUP_BASE="${REHEARSAL_BACKUP_ROOT:-$HOME/.local/share/chipcoin/mainnet-rehearsal-travel}"
COMPOSE_FILE="$REPO_ROOT/docker/compose/docker-compose.mainnet-rehearsal.yml"
PROJECT="chipcoin-mainnet-rehearsal"
MONITOR_UNIT="chipcoin-mainnet-rehearsal-monitor.service"
MONITOR_RUNNER="$REPO_ROOT/scripts/run-mainnet-rehearsal-monitor-loop.sh"
FAULT_LOCK="$RUNTIME_ROOT/fault/session.lock"
NODES=(node-a node-b node-c)
MINERS=(miner-a miner-b)
RESTORED_RUNTIME=false

compose() {
  REHEARSAL_ROOT="$RUNTIME_ROOT" docker compose \
    -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

status_json() {
  local node="$1"
  compose exec -T "$node" \
    chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 status
}

state_json() {
  local node="$1"
  compose exec -T "$node" python3 /app/scripts/mainnet-rehearsal-state.py \
    --data /runtime/mainnet/node.sqlite3
}

container_running() {
  local service="$1" container_id
  container_id="$(compose ps -aq "$service")"
  [[ -n "$container_id" ]] || return 1
  [[ "$(docker inspect -f '{{.State.Running}}' "$container_id")" == "true" ]]
}

capture_states() {
  local node
  for node in "${NODES[@]}"; do
    state_json "$node" | jq --arg node "$node" '. + {node: $node}'
  done | jq -s .
}

capture_statuses() {
  local node
  for node in "${NODES[@]}"; do
    status_json "$node" | jq --arg node "$node" '. + {node: $node}'
  done | jq -s .
}

nodes_ready() {
  local statuses states

  statuses="$(capture_statuses 2>/dev/null)" || return 1
  jq -e '
    length == 3 and
    all(.[]; .network == "mainnet" and
             (.handshaken_peer_count // 0) >= 1 and
             .sync_phase == "idle") and
    ([.[] | [.height, .tip_hash, .cumulative_work]] | unique | length) == 1
  ' <<<"$statuses" >/dev/null || return 1

  states="$(capture_states 2>/dev/null)" || return 1
  jq -e '
    length == 3 and
    all(.[]; .sqlite.quick_check == ["ok"] and
             (.sqlite.foreign_key_check | length) == 0) and
    ([.[] | [
      .height,
      .tip_hash,
      .cumulative_work,
      .supply.materialized_supply_chipbits,
      .utxo_count,
      .utxo_hash,
      .reward_registry_count,
      .reward_registry_hash,
      .reward_settlement_count,
      .reward_settlement_hash
    ]] | unique | length) == 1
  ' <<<"$states" >/dev/null
}

wait_for_nodes() {
  local attempt
  for attempt in $(seq 1 60); do
    if nodes_ready; then
      return 0
    fi
    sleep 5
  done
  return 1
}

ensure_monitor_active() {
  local load_state attempt

  load_state="$(systemctl --user show "$MONITOR_UNIT" --property=LoadState --value 2>/dev/null || true)"
  if [[ -z "$load_state" || "$load_state" == "not-found" ]]; then
    [[ -x "$MONITOR_RUNNER" ]] || die "monitor runner is not executable: $MONITOR_RUNNER"
    systemd-run --user \
      --unit="$MONITOR_UNIT" \
      --description='Chipcoin isolated mainnet rehearsal milestone monitor' \
      --property=Type=simple \
      --collect \
      --setenv="REHEARSAL_ROOT=$RUNTIME_ROOT" \
      "$MONITOR_RUNNER" >/dev/null
  else
    systemctl --user reset-failed "$MONITOR_UNIT" >/dev/null 2>&1 || true
    systemctl --user start "$MONITOR_UNIT"
  fi

  for attempt in $(seq 1 20); do
    systemctl --user is-active --quiet "$MONITOR_UNIT" && return 0
    sleep 1
  done
  return 1
}

restore_runtime_if_needed() {
  local latest backup stage path destination required_bytes available_bytes

  if [[ -d "$RUNTIME_ROOT" ]]; then
    [[ -f "$RUNTIME_ROOT/runtime/node-a/node.sqlite3" ]] ||
      die "runtime root exists but node-a database is missing; refusing ambiguous restore"
    [[ -f "$RUNTIME_ROOT/runtime/node-b/node.sqlite3" ]] ||
      die "runtime root exists but node-b database is missing; refusing ambiguous restore"
    [[ -f "$RUNTIME_ROOT/runtime/node-c/node.sqlite3" ]] ||
      die "runtime root exists but node-c database is missing; refusing ambiguous restore"
    printf 'Existing rehearsal runtime found: %s\n' "$RUNTIME_ROOT"
    return 0
  fi

  [[ -f "$BACKUP_BASE/LATEST" ]] || die "backup pointer not found: $BACKUP_BASE/LATEST"
  latest="$(<"$BACKUP_BASE/LATEST")"
  [[ "$latest" =~ ^rehearsal-[0-9]{8}T[0-9]{6}Z$ ]] ||
    die "invalid backup name in LATEST: $latest"
  backup="$BACKUP_BASE/$latest"
  [[ -d "$backup/data" ]] || die "backup data directory not found: $backup/data"
  [[ -f "$backup/SHA256SUMS" ]] || die "backup checksum manifest not found"
  grep -qx 'backup_format=chipcoin-mainnet-rehearsal-travel-v1' "$backup/MANIFEST.txt" ||
    die "unsupported backup format"

  printf 'Verifying persistent backup: %s\n' "$backup"
  (cd "$backup" && sha256sum -c SHA256SUMS >/dev/null) ||
    die "backup checksum verification failed"

  required_bytes="$(du -sb -- "$backup/data" | awk '{print $1}')"
  available_bytes="$(df --output=avail -B1 /tmp | tail -n 1 | tr -d ' ')"
  (( available_bytes >= required_bytes + 268435456 )) ||
    die "insufficient /tmp space to restore rehearsal runtime"

  stage="${RUNTIME_ROOT}.restore-$BASHPID"
  [[ ! -e "$stage" ]] || die "restore staging path already exists: $stage"
  mkdir -m 700 -- "$stage"
  cp -a --reflink=auto -- "$backup/data/." "$stage/"
  mv -- "$stage" "$RUNTIME_ROOT"
  RESTORED_RUNTIME=true
  printf 'Runtime restored from: %s\n' "$backup"

  if [[ -d "$backup/auxiliary-tmp" ]]; then
    printf 'Restoring missing auxiliary /tmp/chipcoin-* evidence...\n'
    while IFS= read -r -d '' path; do
      destination="/tmp/$(basename -- "$path")"
      [[ -e "$destination" ]] || cp -a --reflink=auto -- "$path" /tmp/
    done < <(find "$backup/auxiliary-tmp" -mindepth 1 -maxdepth 1 -print0 | sort -z)
  fi
}

require_command cp
require_command docker
require_command jq
require_command sha256sum
require_command systemctl
require_command systemd-run

cd "$REPO_ROOT"
[[ -f "$COMPOSE_FILE" ]] || die "Compose file not found: $COMPOSE_FILE"

restore_runtime_if_needed
[[ ! -e "$FAULT_LOCK" ]] || die "fault-session lock exists: $FAULT_LOCK"
compose config >/dev/null

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
evidence="$RUNTIME_ROOT/travel-resume-$timestamp"
mkdir -m 700 -- "$evidence"

printf 'Starting node-a/node-b/node-c with their existing databases...\n'
compose up -d "${NODES[@]}"

printf 'Waiting for P2P handshakes, SQLite checks, and A/B/C convergence...\n'
if ! wait_for_nodes; then
  compose ps --format json >"$evidence/compose-failure.json" || true
  capture_statuses >"$evidence/status-failure.json" 2>&1 || true
  capture_states >"$evidence/state-failure.json" 2>&1 || true
  die "nodes did not converge within 300 seconds; miners and monitor were not started"
fi

capture_statuses >"$evidence/status-before-mining.json"
capture_states >"$evidence/state-before-mining.json"

printf 'Starting miner-a/miner-b...\n'
compose up -d "${MINERS[@]}"
for miner in "${MINERS[@]}"; do
  container_running "$miner" || die "$miner did not start"
done

printf 'Starting ordinary rehearsal monitor...\n'
ensure_monitor_active ||
  die "ordinary monitor did not become active"

sleep 5
wait_for_nodes || die "A/B/C lost convergence after mining resumed"

capture_statuses >"$evidence/final-status.json"
capture_states >"$evidence/final-state.json"
compose ps --format json >"$evidence/final-compose.json"
systemctl --user show "$MONITOR_UNIT" --no-pager \
  -p LoadState -p ActiveState -p SubState -p MainPID -p Result \
  >"$evidence/final-monitor.txt"

jq -r '
  .[0] |
  "RESUME COMPLETE height=\(.height) tip=\(.tip_hash) work=\(.cumulative_work)"
' "$evidence/final-status.json"
printf 'Runtime restored from backup: %s\n' "$RESTORED_RUNTIME"
printf 'Resume evidence: %s\n' "$evidence"
