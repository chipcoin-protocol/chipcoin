#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-check}"

NODE_NAME="${NODE_NAME:-$(hostname -s 2>/dev/null || hostname)}"
STATUS_URL="${STATUS_URL:-http://127.0.0.1:28081/v1/status}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-}"
COMPOSE_SERVICE="${COMPOSE_SERVICE:-node}"
LOG_SINCE="${LOG_SINCE:-10m}"
LOG_DIR="${LOG_DIR:-/var/log/chipcoin-node-monitor}"
MONITOR_LOG="${MONITOR_LOG:-${LOG_DIR}/${NODE_NAME}.jsonl}"
REPORT_SINCE="${REPORT_SINCE:-48h}"

REWARD_REGISTRY_PATTERN='register_reward_node transaction reuses an existing node_id|renew_reward_node transaction renewal_fee_chipbits does not match consensus fee schedule|reward_attestation_bundle submitter must be an active reward node'
VALIDATION_PATTERN='ContextualValidationError|contextual transaction validation failed|validation failed|sync scheduler loop failed'
INVALID_BLOCK_PATTERN='invalid block'
SNAPSHOT_RESTORE_PATTERN='Snapshot bootstrap (required|preparing|imported)'
SNAPSHOT_SKIP_PATTERN='Snapshot bootstrap skipped mode=.*node_database_already_initialized'

compose_cmd() {
  local args=(docker compose -f "$COMPOSE_FILE")
  if [[ -n "$COMPOSE_PROJECT" ]]; then
    args+=(-p "$COMPOSE_PROJECT")
  fi
  args+=("$@")
  "${args[@]}"
}

count_pattern() {
  local pattern="$1"
  local file="$2"
  grep -Eic "$pattern" "$file" 2>/dev/null || true
}

timestamp_iso8601() {
  date '+%Y-%m-%dT%H:%M:%S%z'
}

runtime_db_probe() {
  compose_cmd exec -T "$COMPOSE_SERVICE" sh -lc '
set -eu
configured="${NODE_DATA_PATH:-}"
runtime="/runtime/node.sqlite3"
runtime_is_symlink=false
runtime_link=""
runtime_resolved=""
runtime_inode=""
configured_inode=""
same_target=false
same_inode=false

if [ -L "$runtime" ]; then
  runtime_is_symlink=true
  runtime_link="$(readlink "$runtime")"
fi
if [ -e "$runtime" ]; then
  runtime_resolved="$(readlink -m "$runtime")"
  runtime_inode="$(stat -Lc "%d:%i" "$runtime")"
fi
if [ -n "$configured" ] && [ -e "$configured" ]; then
  configured_inode="$(stat -Lc "%d:%i" "$configured")"
fi
if [ -n "$configured" ] && [ -n "$runtime_resolved" ] && [ "$runtime_resolved" = "$configured" ]; then
  same_target=true
fi
if [ -n "$configured_inode" ] && [ -n "$runtime_inode" ] && [ "$configured_inode" = "$runtime_inode" ]; then
  same_inode=true
fi

configured="$configured" \
runtime="$runtime" \
runtime_is_symlink="$runtime_is_symlink" \
runtime_link="$runtime_link" \
runtime_resolved="$runtime_resolved" \
runtime_inode="$runtime_inode" \
configured_inode="$configured_inode" \
same_target="$same_target" \
same_inode="$same_inode" \
python3 - <<'"'"'PY'"'"'
import json
import os

print(json.dumps({
    "configured_path": os.environ["configured"],
    "runtime_path": os.environ["runtime"],
    "runtime_is_symlink": os.environ["runtime_is_symlink"] == "true",
    "runtime_link": os.environ["runtime_link"],
    "runtime_resolved": os.environ["runtime_resolved"],
    "runtime_inode": os.environ["runtime_inode"],
    "configured_inode": os.environ["configured_inode"],
    "same_target": os.environ["same_target"] == "true",
    "same_inode": os.environ["same_inode"] == "true",
}, separators=(",", ":")))
PY
' 2>/dev/null || jq -nc '{error:"db_probe_failed"}'
}

check_once() {
  mkdir -p "$LOG_DIR"
  local ts status logs_file db_probe
  ts="$(timestamp_iso8601)"
  logs_file="$(mktemp)"
  trap 'rm -f "$logs_file"' RETURN

  status="$(curl -fsS "$STATUS_URL")"
  compose_cmd logs --since "$LOG_SINCE" "$COMPOSE_SERVICE" >"$logs_file" 2>/dev/null || true
  db_probe="$(runtime_db_probe)"

  jq -nc \
    --arg ts "$ts" \
    --arg node "$NODE_NAME" \
    --arg status_url "$STATUS_URL" \
    --arg log_since "$LOG_SINCE" \
    --argjson status "$status" \
    --argjson db_probe "$db_probe" \
    --argjson invalid_block_count "$(count_pattern "$INVALID_BLOCK_PATTERN" "$logs_file")" \
    --argjson validation_failure_count "$(count_pattern "$VALIDATION_PATTERN" "$logs_file")" \
    --argjson reward_registry_error_count "$(count_pattern "$REWARD_REGISTRY_PATTERN" "$logs_file")" \
    --argjson snapshot_restore_attempt_count "$(count_pattern "$SNAPSHOT_RESTORE_PATTERN" "$logs_file")" \
    --argjson snapshot_initialized_skip_count "$(count_pattern "$SNAPSHOT_SKIP_PATTERN" "$logs_file")" \
    '{
      ts: $ts,
      node: $node,
      status_url: $status_url,
      log_since: $log_since,
      height: $status.height,
      best_header_height: $status.sync.best_header_height,
      validated_tip_height: $status.sync.validated_tip_height,
      best_minus_validated: (($status.sync.best_header_height // 0) - ($status.sync.validated_tip_height // 0)),
      sync_phase: $status.sync_phase,
      sync_mode: $status.sync.mode,
      missing_block_count: $status.sync.missing_block_count,
      queued_block_count: $status.sync.queued_block_count,
      inflight_block_count: $status.sync.inflight_block_count,
      peer_count: $status.handshaken_peer_count,
      operational_peer_count: $status.operational_peer_count,
      warnings: ($status.operator_summary.warnings // []),
      invalid_block_count: $invalid_block_count,
      validation_failure_count: $validation_failure_count,
      reward_registry_error_count: $reward_registry_error_count,
      snapshot_restore_attempt_count: $snapshot_restore_attempt_count,
      snapshot_initialized_skip_count: $snapshot_initialized_skip_count,
      db_path: $db_probe
    }' | tee -a "$MONITOR_LOG"
}

report() {
  if [[ ! -s "$MONITOR_LOG" ]]; then
    printf 'No monitor log found at %s\n' "$MONITOR_LOG" >&2
    exit 1
  fi

  jq -s '
    def nvl: . // 0;
    def max_of(path_expr): map(path_expr) | map(select(. != null)) | max;
    def sum_of(path_expr): map(path_expr // 0) | add;
    def unique_warnings: map(.warnings // []) | add | unique;

    {
      samples: length,
      first_ts: (.[0].ts // null),
      last_ts: (.[-1].ts // null),
      first_height: (.[0].height // null),
      last_height: (.[-1].height // null),
      max_height: max_of(.height),
      latest: .[-1],
      max_best_minus_validated: max_of(.best_minus_validated),
      max_missing_block_count: max_of(.missing_block_count),
      max_inflight_block_count: max_of(.inflight_block_count),
      min_peer_count: (map(.peer_count // 0) | min),
      warnings_seen: unique_warnings,
      invalid_block_count_total: sum_of(.invalid_block_count),
      validation_failure_count_total: sum_of(.validation_failure_count),
      reward_registry_error_count_total: sum_of(.reward_registry_error_count),
      snapshot_restore_attempt_count_total: sum_of(.snapshot_restore_attempt_count),
      db_path_failures: map(select((.db_path.same_target != true) or (.db_path.same_inode != true) or (.db_path.runtime_is_symlink != true))) | length,
      pass: (
        (sum_of(.invalid_block_count) == 0)
        and (sum_of(.validation_failure_count) == 0)
        and (sum_of(.reward_registry_error_count) == 0)
        and (sum_of(.snapshot_restore_attempt_count) == 0)
        and ((map(select((.db_path.same_target != true) or (.db_path.same_inode != true) or (.db_path.runtime_is_symlink != true))) | length) == 0)
        and ((.[-1].sync_phase // "") == "synced")
        and ((.[-1].missing_block_count // 0) == 0)
      )
    }' "$MONITOR_LOG"

  printf '\nRecent matching docker log lines since %s:\n' "$REPORT_SINCE"
  compose_cmd logs --since "$REPORT_SINCE" "$COMPOSE_SERVICE" 2>/dev/null \
    | grep -Ei "$REWARD_REGISTRY_PATTERN|$VALIDATION_PATTERN|$INVALID_BLOCK_PATTERN|$SNAPSHOT_RESTORE_PATTERN|$SNAPSHOT_SKIP_PATTERN" \
    || true
}

case "$MODE" in
  check)
    check_once
    ;;
  report)
    report
    ;;
  patterns)
    cat <<EOF
Reward-registry:
$REWARD_REGISTRY_PATTERN

Validation:
$VALIDATION_PATTERN

Invalid block:
$INVALID_BLOCK_PATTERN

Snapshot restore attempts:
$SNAPSHOT_RESTORE_PATTERN

Initialized DB skip:
$SNAPSHOT_SKIP_PATTERN
EOF
    ;;
  *)
    printf 'Usage: %s [check|report|patterns]\n' "$0" >&2
    exit 2
    ;;
esac
