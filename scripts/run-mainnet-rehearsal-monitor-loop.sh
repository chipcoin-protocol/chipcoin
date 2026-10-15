#!/usr/bin/env bash
set -u

umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
ROOT="${REHEARSAL_ROOT:-/tmp/chipcoin-mainnet-docker-rehearsal}"
INTERVAL_SECONDS="${MONITOR_INTERVAL_SECONDS:-60}"
RETRY_SECONDS="${MONITOR_RETRY_SECONDS:-10}"
FAILURE_THRESHOLD="${MONITOR_FAILURE_THRESHOLD:-3}"
COMPOSE_FILE="$REPO_ROOT/docker/compose/docker-compose.mainnet-rehearsal.yml"
PROJECT="chipcoin-mainnet-rehearsal"
LOG_FILE="$ROOT/logs/milestone-monitor.log"
PID_FILE="$ROOT/milestone-monitor.pid"
LOCK_FILE="$ROOT/milestone-monitor.lock"

if ! [[ "$INTERVAL_SECONDS" =~ ^[0-9]+$ ]] || (( INTERVAL_SECONDS < 5 )); then
  printf 'Invalid monitor interval: %s\n' "$INTERVAL_SECONDS" >&2
  exit 2
fi
if ! [[ "$RETRY_SECONDS" =~ ^[0-9]+$ ]] || (( RETRY_SECONDS < 1 )); then
  printf 'Invalid monitor retry interval: %s\n' "$RETRY_SECONDS" >&2
  exit 2
fi
if ! [[ "$FAILURE_THRESHOLD" =~ ^[0-9]+$ ]] || (( FAILURE_THRESHOLD < 2 )); then
  printf 'Invalid monitor failure threshold: %s\n' "$FAILURE_THRESHOLD" >&2
  exit 2
fi

mkdir -p "$ROOT/logs"
exec 9>"$LOCK_FILE"
flock -n 9 || {
  printf 'Another rehearsal monitor already owns %s\n' "$LOCK_FILE" >&2
  exit 1
}

printf '%s\n' "$BASHPID" >"$PID_FILE"
cleanup() {
  rm -f -- "$PID_FILE"
}
trap cleanup EXIT INT TERM

compose() {
  REHEARSAL_ROOT="$ROOT" docker compose \
    -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
}

cd "$REPO_ROOT"
printf '%s MONITOR_START pid=%s interval=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)" "$BASHPID" "$INTERVAL_SECONDS" >>"$LOG_FILE"

while true; do
  if REHEARSAL_ROOT="$ROOT" "$SCRIPT_DIR/mainnet-rehearsal.sh" check >>"$LOG_FILE" 2>&1; then
    printf '%s MONITOR_PASS\n' "$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)" >>"$LOG_FILE"
  else
    failure_count=1
    printf '%s MONITOR_RECHECK attempt=%s/%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)" "$failure_count" "$FAILURE_THRESHOLD" >>"$LOG_FILE"
    while (( failure_count < FAILURE_THRESHOLD )); do
      sleep "$RETRY_SECONDS"
      if REHEARSAL_ROOT="$ROOT" "$SCRIPT_DIR/mainnet-rehearsal.sh" check >>"$LOG_FILE" 2>&1; then
        printf '%s MONITOR_TRANSIENT_RECOVERED attempts=%s\n' \
          "$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)" "$failure_count" >>"$LOG_FILE"
        failure_count=0
        break
      fi
      failure_count=$((failure_count + 1))
      printf '%s MONITOR_RECHECK attempt=%s/%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)" "$failure_count" "$FAILURE_THRESHOLD" >>"$LOG_FILE"
    done

    if (( failure_count >= FAILURE_THRESHOLD )); then
      printf '%s MONITOR_FAIL_PERSISTENT stopping rehearsal\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)" >>"$LOG_FILE"
      compose stop -t 30 miner-a miner-b >>"$LOG_FILE" 2>&1 || true
      compose stop -t 120 node-a node-b node-c >>"$LOG_FILE" 2>&1 || true
      exit 1
    fi
  fi
  sleep "$INTERVAL_SECONDS"
done
