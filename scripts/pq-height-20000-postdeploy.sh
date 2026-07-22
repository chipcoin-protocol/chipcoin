#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker-compose.yml"
NODE_SERVICE="node"
MINER_SERVICE=""
API_URL=""
EXPECTED_HEIGHT="20000"
LOG_LINES="200"
JSON="false"
WARNINGS=0
FAILURES=0

show_help() {
  cat <<'HELP'
Read-only post-deployment checks for the Chipcoin PQ height 20000 rollout.

Options:
  --compose-file PATH     Compose file. Default: docker-compose.yml.
  --node-service NAME     Node service. Default: node.
  --miner-service NAME    Optional miner service to verify.
  --api-url URL           Optional public/local API endpoint to probe.
  --expected-height N     Expected PQ activation height. Default: 20000.
  --log-lines N           Recent node log lines to inspect. Default: 200.
  --json                  Emit compact JSON summary.
  -h, --help              Show this help.

Exit codes:
  0 PASS, 1 WARN, 2 FAIL, 3 command/configuration error.
HELP
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --compose-file) COMPOSE_FILE="${2:?missing --compose-file value}"; shift 2 ;;
    --node-service) NODE_SERVICE="${2:?missing --node-service value}"; shift 2 ;;
    --miner-service) MINER_SERVICE="${2:?missing --miner-service value}"; shift 2 ;;
    --api-url) API_URL="${2:?missing --api-url value}"; shift 2 ;;
    --expected-height) EXPECTED_HEIGHT="${2:?missing --expected-height value}"; shift 2 ;;
    --log-lines) LOG_LINES="${2:?missing --log-lines value}"; shift 2 ;;
    --json) JSON="true"; shift ;;
    -h|--help) show_help; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 3 ;;
  esac
done

record() {
  local status="$1"
  local name="$2"
  local detail="$3"
  if [[ "$status" == "FAIL" ]]; then
    FAILURES=$((FAILURES + 1))
  elif [[ "$status" == "WARN" ]]; then
    WARNINGS=$((WARNINGS + 1))
  fi
  if [[ "$JSON" != "true" ]]; then
    printf '%-4s %s - %s\n' "$status" "$name" "$detail"
  fi
}

if ! command -v docker >/dev/null 2>&1; then
  record "FAIL" "docker" "not found"
else
  record "PASS" "docker" "$(docker --version 2>/dev/null || echo available)"
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  record "FAIL" "compose file" "$COMPOSE_FILE not found"
else
  record "PASS" "compose file" "$COMPOSE_FILE"
fi

NODE_CONTAINER="$(docker compose -f "$COMPOSE_FILE" ps -q "$NODE_SERVICE" 2>/dev/null || true)"
if [[ -z "$NODE_CONTAINER" ]]; then
  record "FAIL" "node container" "service $NODE_SERVICE not running or not found"
else
  RUNNING="$(docker inspect -f '{{.State.Running}}' "$NODE_CONTAINER" 2>/dev/null || echo false)"
  IMAGE="$(docker inspect -f '{{.Image}}' "$NODE_CONTAINER" 2>/dev/null || echo unknown)"
  record "$([[ "$RUNNING" == "true" ]] && echo PASS || echo FAIL)" "node container" "id=$NODE_CONTAINER image=$IMAGE running=$RUNNING"
fi

if [[ -n "$NODE_CONTAINER" ]]; then
  if docker compose -f "$COMPOSE_FILE" exec -T "$NODE_SERVICE" sh -lc "if command -v chipcoin >/dev/null 2>&1; then chipcoin verify-pq-activation --network testnet --expected-height $EXPECTED_HEIGHT; else python -m chipcoin.tools.verify_pq_activation --network testnet --expected-height $EXPECTED_HEIGHT; fi" >/tmp/chipcoin-pq-postdeploy-activation.out 2>&1; then
    record "PASS" "container activation" "$(tail -1 /tmp/chipcoin-pq-postdeploy-activation.out)"
  else
    record "FAIL" "container activation" "$(tail -1 /tmp/chipcoin-pq-postdeploy-activation.out)"
  fi

  if docker compose -f "$COMPOSE_FILE" logs --tail "$LOG_LINES" "$NODE_SERVICE" 2>/tmp/chipcoin-pq-postdeploy-logs.err \
      | grep -Eiq 'consensus error|invalid block|traceback|critical|fatal'; then
    record "FAIL" "recent node logs" "consensus/error pattern found"
  else
    record "PASS" "recent node logs" "no consensus/error pattern in last $LOG_LINES lines"
  fi
fi

if [[ -n "$MINER_SERVICE" ]]; then
  MINER_CONTAINER="$(docker compose -f "$COMPOSE_FILE" ps -q "$MINER_SERVICE" 2>/dev/null || true)"
  if [[ -z "$MINER_CONTAINER" ]]; then
    record "WARN" "miner container" "service $MINER_SERVICE not running or not found"
  else
    MINER_RUNNING="$(docker inspect -f '{{.State.Running}}' "$MINER_CONTAINER" 2>/dev/null || echo false)"
    record "$([[ "$MINER_RUNNING" == "true" ]] && echo PASS || echo WARN)" "miner container" "id=$MINER_CONTAINER running=$MINER_RUNNING"
  fi
else
  record "WARN" "miner container" "not configured; pass --miner-service if applicable"
fi

if [[ -n "$API_URL" ]]; then
  if python3 - "$API_URL" <<'PY' >/tmp/chipcoin-pq-postdeploy-api.out 2>&1
from __future__ import annotations

import json
import sys
import urllib.request

base = sys.argv[1].rstrip("/")
with urllib.request.urlopen(base + "/v1/status", timeout=10) as response:
    payload = json.load(response)
print(f"height={payload.get('height')} sync={payload.get('sync_phase')} peers={payload.get('operational_peer_count')}")
PY
  then
    record "PASS" "API status" "$(cat /tmp/chipcoin-pq-postdeploy-api.out)"
  else
    record "WARN" "API status" "$(tail -1 /tmp/chipcoin-pq-postdeploy-api.out)"
  fi
else
  record "WARN" "API status" "skipped; pass --api-url to probe"
fi

STATUS="PASS"
EXIT_CODE=0
if [[ "$FAILURES" -gt 0 ]]; then
  STATUS="FAIL"
  EXIT_CODE=2
elif [[ "$WARNINGS" -gt 0 ]]; then
  STATUS="WARN"
  EXIT_CODE=1
fi

if [[ "$JSON" == "true" ]]; then
  printf '{"schema_version":1,"status":"%s","compose_file":"%s","node_service":"%s","expected_height":%s,"warnings":%s,"failures":%s}\n' \
    "$STATUS" "$COMPOSE_FILE" "$NODE_SERVICE" "$EXPECTED_HEIGHT" "$WARNINGS" "$FAILURES"
else
  echo
  echo "Result: $STATUS"
fi

exit "$EXIT_CODE"
