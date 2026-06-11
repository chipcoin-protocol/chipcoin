#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_SCRIPT="${SCRIPT_DIR}/testnet-node-monitor.sh"

if [[ ! -x "$MONITOR_SCRIPT" ]]; then
  printf 'Monitor script not found or not executable: %s\n' "$MONITOR_SCRIPT" >&2
  exit 1
fi

default_name="$(hostname -s 2>/dev/null || hostname)"
read -r -p "Machine name [${default_name}]: " node_name
node_name="${node_name:-$default_name}"

read -r -p "Status URL [http://127.0.0.1:28081/v1/status]: " status_url
status_url="${status_url:-http://127.0.0.1:28081/v1/status}"

read -r -p "Compose file [docker-compose.yml]: " compose_file
compose_file="${compose_file:-docker-compose.yml}"

read -r -p "Compose project, empty for default []: " compose_project

read -r -p "Interval seconds [600]: " interval_seconds
interval_seconds="${interval_seconds:-600}"
if ! [[ "$interval_seconds" =~ ^[0-9]+$ ]] || [[ "$interval_seconds" -le 0 ]]; then
  printf 'Invalid interval: %s\n' "$interval_seconds" >&2
  exit 1
fi

log_dir="${LOG_DIR:-/var/log/chipcoin-node-monitor}"
monitor_log="${MONITOR_LOG:-${log_dir}/${node_name}.jsonl}"

printf '\nMonitoring node=%s every %s seconds\n' "$node_name" "$interval_seconds"
printf 'Log file: %s\n' "$monitor_log"
printf 'Press Ctrl-C to stop.\n\n'

while true; do
  sample="$(
    NODE_NAME="$node_name" \
    STATUS_URL="$status_url" \
    COMPOSE_FILE="$compose_file" \
    COMPOSE_PROJECT="$compose_project" \
    LOG_SINCE="${LOG_SINCE:-10m}" \
    LOG_DIR="$log_dir" \
    MONITOR_LOG="$monitor_log" \
    "$MONITOR_SCRIPT" check
  )"

  if command -v jq >/dev/null 2>&1; then
    printf '%s\n' "$sample" | jq .
  else
    printf '%s\n' "$sample"
  fi

  sleep "$interval_seconds"
done
