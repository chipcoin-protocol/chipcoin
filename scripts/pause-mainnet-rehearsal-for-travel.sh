#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
SOURCE_ROOT="${REHEARSAL_ROOT:-/tmp/chipcoin-mainnet-docker-rehearsal}"
BACKUP_BASE="${REHEARSAL_BACKUP_ROOT:-$HOME/.local/share/chipcoin/mainnet-rehearsal-travel}"
COMPOSE_FILE="$REPO_ROOT/docker/compose/docker-compose.mainnet-rehearsal.yml"
PROJECT="chipcoin-mainnet-rehearsal"
MONITOR_UNIT="chipcoin-mainnet-rehearsal-monitor.service"
FAULT_LOCK="$SOURCE_ROOT/fault/session.lock"
EXPECTED_SERVICES=(miner-a miner-b node-a node-b node-c)
MODE="${1:-pause}"
AUXILIARY_TMP_PATHS=()
AUXILIARY_TMP_BYTES=0

case "$MODE" in
  pause|--check) ;;
  *)
    printf 'usage: %s [--check]\n' "$0" >&2
    exit 2
    ;;
esac

compose() {
  REHEARSAL_ROOT="$SOURCE_ROOT" docker compose \
    -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

container_running() {
  local service="$1" container_id
  container_id="$(compose ps -aq "$service")"
  [[ -n "$container_id" ]] || return 1
  [[ "$(docker inspect -f '{{.State.Running}}' "$container_id")" == "true" ]]
}

container_stopped() {
  local service="$1" container_id
  container_id="$(compose ps -aq "$service")"
  [[ -n "$container_id" ]] || return 1
  [[ "$(docker inspect -f '{{.State.Running}}' "$container_id")" == "false" ]]
}

capture_node_statuses() {
  local node
  for node in node-a node-b node-c; do
    compose exec -T "$node" \
      chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 status |
      jq --arg node "$node" '. + {node: $node}'
  done | jq -s .
}

capture_node_states() {
  local node
  for node in node-a node-b node-c; do
    compose exec -T "$node" python3 /app/scripts/mainnet-rehearsal-state.py \
      --data /runtime/mainnet/node.sqlite3 |
      jq --arg node "$node" '. + {node: $node}'
  done | jq -s .
}

assert_clean_runtime() {
  local actual expected service statuses states

  [[ -d "$SOURCE_ROOT" ]] || die "rehearsal root not found: $SOURCE_ROOT"
  [[ -f "$COMPOSE_FILE" ]] || die "compose file not found: $COMPOSE_FILE"
  [[ ! -e "$FAULT_LOCK" ]] || die "fault-session lock exists: $FAULT_LOCK"

  expected="$(printf '%s\n' "${EXPECTED_SERVICES[@]}" | sort)"
  actual="$(compose ps --services --status running | sort)"
  [[ "$actual" == "$expected" ]] || {
    printf 'Expected running services:\n%s\nActual running services:\n%s\n' \
      "$expected" "$actual" >&2
    die "unexpected Compose service set; no shutdown was attempted"
  }

  for service in "${EXPECTED_SERVICES[@]}"; do
    container_running "$service" || die "$service is not running"
  done

  systemctl --user is-active --quiet "$MONITOR_UNIT" ||
    die "ordinary monitor is not active: $MONITOR_UNIT"

  if systemctl --user list-units --all --plain --no-legend \
      'chipcoin-mainnet-fault-monitor-*.service' 2>/dev/null |
      awk '$3 == "active" || $4 == "running" {found=1} END {exit !found}'; then
    die "an active fault monitor exists"
  fi

  statuses="$(capture_node_statuses)"
  jq -e '
    length == 3 and
    ([.[] | [.height, .tip_hash, .cumulative_work]] | unique | length) == 1 and
    all(.[]; (.mempool_size // 0) == 0)
  ' <<<"$statuses" >/dev/null ||
    die "A/B/C are divergent or a mempool is not empty"

  states="$(capture_node_states)"
  jq -e '
    length == 3 and
    ([.[] | del(.node)] | unique | length) == 1 and
    all(.[]; (.sqlite.quick_check == ["ok"]) and
             ((.sqlite.foreign_key_check | length) == 0))
  ' <<<"$states" >/dev/null ||
    die "canonical fingerprints or SQLite checks differ across A/B/C"

  printf '%s\n' "$statuses"
}

require_command docker
require_command jq
require_command sha256sum
require_command systemctl
require_command cp

cd "$REPO_ROOT"

while IFS= read -r -d '' path; do
  [[ "$path" == "$SOURCE_ROOT" ]] && continue
  AUXILIARY_TMP_PATHS+=("$path")
  path_bytes="$(du -sb -- "$path" | awk '{print $1}')"
  AUXILIARY_TMP_BYTES=$((AUXILIARY_TMP_BYTES + path_bytes))
done < <(find /tmp -mindepth 1 -maxdepth 1 -name 'chipcoin-*' -print0 | sort -z)

printf 'Checking rehearsal before travel shutdown...\n'
statuses="$(assert_clean_runtime)"
printf '%s\n' "$statuses" | jq -r \
  '.[] | "\(.node): height=\(.height) tip=\(.tip_hash) work=\(.cumulative_work) mempool=\(.mempool_size // 0)"'

source_bytes="$(du -sb -- "$SOURCE_ROOT" | awk '{print $1}')"
printf 'Runtime size: %s bytes\n' "$source_bytes"
printf 'Additional /tmp/chipcoin-* paths: %s (%s bytes)\n' \
  "${#AUXILIARY_TMP_PATHS[@]}" "$AUXILIARY_TMP_BYTES"
printf '%s\n' "${AUXILIARY_TMP_PATHS[@]}"

if [[ "$MODE" == "--check" ]]; then
  available_bytes="$(df --output=avail -B1 "$HOME" | tail -n 1 | tr -d ' ')"
  required_bytes=$((source_bytes + AUXILIARY_TMP_BYTES + 268435456))
  (( available_bytes >= required_bytes )) ||
    die "insufficient persistent storage space"
  printf 'CHECK PASS: shutdown was not performed.\n'
  printf 'Persistent backup target: %s\n' "$BACKUP_BASE"
  exit 0
fi

mkdir -p -- "$BACKUP_BASE"
chmod 700 -- "$BACKUP_BASE"

available_bytes="$(df --output=avail -B1 "$BACKUP_BASE" | tail -n 1 | tr -d ' ')"
required_bytes=$((source_bytes + AUXILIARY_TMP_BYTES + 268435456))
(( available_bytes >= required_bytes )) ||
  die "insufficient space in $BACKUP_BASE (need runtime size plus 256 MiB)"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
stage="$BACKUP_BASE/.incomplete-$timestamp"
final="$BACKUP_BASE/rehearsal-$timestamp"
mkdir -m 700 -- "$stage" "$stage/evidence" "$stage/data" "$stage/auxiliary-tmp"

shutdown_started=false
on_error() {
  local rc=$?
  trap - ERR
  printf 'FAILED at %s (exit %s).\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rc" >&2
  if [[ "$shutdown_started" == true ]]; then
    printf 'Completing a best-effort safe stop; services will not be restarted automatically.\n' >&2
    compose stop -t 30 miner-a miner-b >/dev/null 2>&1 || true
    compose stop -t 90 node-a node-b node-c >/dev/null 2>&1 || true
  fi
  printf 'Incomplete evidence, if any: %s\n' "$stage" >&2
  exit "$rc"
}
trap on_error ERR

printf '%s\n' "$statuses" >"$stage/evidence/pre-stop-status.json"
capture_node_states >"$stage/evidence/pre-stop-state.json"
systemctl --user show "$MONITOR_UNIT" --no-pager \
  -p LoadState -p ActiveState -p SubState -p MainPID -p Result \
  >"$stage/evidence/monitor-before.txt"
compose ps --format json >"$stage/evidence/compose-before.json"
git rev-parse HEAD >"$stage/evidence/git-commit.txt"
git status --short >"$stage/evidence/git-status-short.txt"

shutdown_started=true
printf 'Stopping ordinary monitor...\n'
systemctl --user stop "$MONITOR_UNIT"
systemctl --user is-active --quiet "$MONITOR_UNIT" &&
  die "ordinary monitor remained active after stop"

printf 'Stopping miners...\n'
compose stop -t 30 miner-a miner-b
container_stopped miner-a || die "miner-a did not stop"
container_stopped miner-b || die "miner-b did not stop"

printf 'Stopping nodes cleanly...\n'
compose stop -t 120 node-a node-b node-c
container_stopped node-a || die "node-a did not stop"
container_stopped node-b || die "node-b did not stop"
container_stopped node-c || die "node-c did not stop"

compose ps --format json >"$stage/evidence/compose-after-stop.json"
systemctl --user show "$MONITOR_UNIT" --no-pager \
  -p LoadState -p ActiveState -p SubState -p MainPID -p Result \
  >"$stage/evidence/monitor-after.txt" || true

printf 'Copying the complete stopped runtime to persistent storage...\n'
cp -a --reflink=auto -- "$SOURCE_ROOT/." "$stage/data/"

printf 'Copying additional /tmp/chipcoin-* evidence and artifacts...\n'
for path in "${AUXILIARY_TMP_PATHS[@]}"; do
  cp -a --reflink=auto -- "$path" "$stage/auxiliary-tmp/"
done

cat >"$stage/MANIFEST.txt" <<EOF
backup_format=chipcoin-mainnet-rehearsal-travel-v1
created_utc=$timestamp
source_root=$SOURCE_ROOT
repository=$REPO_ROOT
compose_project=$PROJECT
monitor_unit=$MONITOR_UNIT
shutdown_order=monitor,miners,nodes
source_bytes=$source_bytes
auxiliary_tmp_path_count=${#AUXILIARY_TMP_PATHS[@]}
auxiliary_tmp_bytes=$AUXILIARY_TMP_BYTES
auxiliary_tmp_pattern=/tmp/chipcoin-*
original_runtime_deleted=no
EOF

printf '%s\n' "${AUXILIARY_TMP_PATHS[@]}" >"$stage/evidence/auxiliary-tmp-paths.txt"

printf 'Computing and verifying SHA-256 checksums...\n'
(
  cd "$stage"
  find data auxiliary-tmp evidence -type f -print0 | sort -z | xargs -0 sha256sum >SHA256SUMS
  sha256sum -c SHA256SUMS
) >"$stage/checksum-verification.log"

sync
mv -- "$stage" "$final"
(
  cd "$final"
  sha256sum -c SHA256SUMS >/dev/null
)

latest_tmp="$BACKUP_BASE/.LATEST.tmp"
printf '%s\n' "$(basename -- "$final")" >"$latest_tmp"
mv -f -- "$latest_tmp" "$BACKUP_BASE/LATEST"
sync

trap - ERR
printf '\nPAUSE COMPLETE\n'
printf 'All rehearsal containers are stopped; no Compose resources were removed.\n'
printf 'Persistent verified backup: %s\n' "$final"
printf 'Original /tmp runtime retained: %s\n' "$SOURCE_ROOT"
printf 'Additional /tmp/chipcoin-* paths retained under: %s/auxiliary-tmp\n' "$final"
printf 'It is now safe to shut down Tobia. Do not restart the rehearsal before restoring the runtime if /tmp was cleared.\n'
