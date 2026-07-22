#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${CHIPCOIN_PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${CHIPCOIN_PYTHON:-python3}"
fi

API_URL=""
NETWORK="testnet"
EXPECTED_HEIGHT="20000"
SKIP_TESTS="false"
JSON="false"
WARNINGS=0
FAILURES=0

show_help() {
  cat <<'HELP'
Read-only preflight for the Chipcoin testnet PQ height 20000 rollout.

Options:
  --api-url URL           Optional API endpoint to probe.
  --network NAME          Network to verify. Default: testnet.
  --expected-height N     Expected PQ activation height. Default: 20000.
  --skip-tests            Skip the focused Python preflight tests.
  --json                  Emit compact JSON summary.
  -h, --help              Show this help.

Exit codes:
  0 PASS, 1 WARN, 2 FAIL, 3 command/configuration error.
HELP
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-url) API_URL="${2:?missing --api-url value}"; shift 2 ;;
    --network) NETWORK="${2:?missing --network value}"; shift 2 ;;
    --expected-height) EXPECTED_HEIGHT="${2:?missing --expected-height value}"; shift 2 ;;
    --skip-tests) SKIP_TESTS="true"; shift ;;
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

run_check() {
  local name="$1"
  shift
  if "$@" >/tmp/chipcoin-pq-preflight.out 2>&1; then
    record "PASS" "$name" "$(tail -1 /tmp/chipcoin-pq-preflight.out)"
  else
    record "FAIL" "$name" "$(tail -1 /tmp/chipcoin-pq-preflight.out)"
  fi
}

if git -C "$ROOT" merge-base --is-ancestor e361ae4 HEAD >/dev/null 2>&1; then
  record "PASS" "commit e361ae4" "present in history"
else
  record "FAIL" "commit e361ae4" "not present in current history"
fi

HEAD="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
record "PASS" "current HEAD" "$HEAD"

if [[ -n "$(git -C "$ROOT" status --short 2>/dev/null)" ]]; then
  record "WARN" "working tree" "not clean; review before release build"
else
  record "PASS" "working tree" "clean"
fi

run_check "testnet activation" env \
  CHIPCOIN_ROOT="$ROOT" \
  CHIPCOIN_PYTHON="$PYTHON_BIN" \
  CHIPCOIN_NETWORK="$NETWORK" \
  EXPECTED_PQ_HEIGHT="$EXPECTED_HEIGHT" \
  "$ROOT/scripts/verify-pq-activation.sh"

run_check "devnet activation" env \
  CHIPCOIN_ROOT="$ROOT" \
  CHIPCOIN_PYTHON="$PYTHON_BIN" \
  CHIPCOIN_NETWORK="devnet" \
  EXPECTED_PQ_HEIGHT="30000" \
  "$ROOT/scripts/verify-pq-activation.sh"

if grep -q "ENABLE_EXPERIMENTAL_BROWSER_MLDSA = false" "$ROOT/apps/browser-wallet/src/shared/constants.ts"; then
  record "PASS" "browser PQ flag" "false"
else
  record "FAIL" "browser PQ flag" "not false"
fi

if command -v docker >/dev/null 2>&1; then
  record "PASS" "docker" "$(docker --version 2>/dev/null || echo available)"
else
  record "WARN" "docker" "not found"
fi

if docker compose version >/dev/null 2>&1; then
  record "PASS" "docker compose" "$(docker compose version 2>/dev/null | head -1)"
else
  record "WARN" "docker compose" "not available"
fi

FREE_MB="$(df -Pm "$ROOT" | awk 'NR==2 {print $4}')"
if [[ "${FREE_MB:-0}" -ge 2048 ]]; then
  record "PASS" "disk space" "${FREE_MB}MB available"
else
  record "WARN" "disk space" "${FREE_MB:-unknown}MB available"
fi

if [[ -f "$ROOT/docker-compose.yml" ]]; then
  record "PASS" "compose file" "docker-compose.yml"
else
  record "FAIL" "compose file" "docker-compose.yml missing"
fi

if grep -q "volumes:" "$ROOT/docker-compose.yml"; then
  record "PASS" "compose volumes" "volumes declared; preserve them during rollout"
else
  record "WARN" "compose volumes" "no volumes declaration found"
fi

if [[ "$SKIP_TESTS" == "true" ]]; then
  record "WARN" "focused tests" "skipped by operator"
else
  run_check "focused tests" "$PYTHON_BIN" -m pytest tests/pq/test_pq_audit_report.py tests/pq/test_pq_smoke_command.py -q
fi

if [[ -n "$API_URL" ]]; then
  run_check "readiness API probe" "$PYTHON_BIN" -m chipcoin.tools.pq_operational_readiness --api-url "$API_URL" --compact
else
  record "WARN" "readiness API probe" "skipped; pass --api-url to probe a deployed node"
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
  printf '{"schema_version":1,"status":"%s","head":"%s","network":"%s","expected_height":%s,"warnings":%s,"failures":%s}\n' \
    "$STATUS" "$HEAD" "$NETWORK" "$EXPECTED_HEIGHT" "$WARNINGS" "$FAILURES"
else
  echo
  echo "Result: $STATUS"
fi

exit "$EXIT_CODE"
