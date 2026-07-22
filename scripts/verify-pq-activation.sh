#!/usr/bin/env bash
set -euo pipefail

show_help() {
  cat <<'HELP'
Verify the compiled Chipcoin PQ activation height used by an installed package.

Environment:
  CHIPCOIN_ROOT       Optional project root to prepend to PYTHONPATH.
  CHIPCOIN_PYTHON     Python executable. Defaults to $CHIPCOIN_ROOT/.venv/bin/python or python3.
  CHIPCOIN_NETWORK    Network to verify. Default: testnet.
  EXPECTED_PQ_HEIGHT  Expected activation height. Default: 20000.
HELP
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi

ROOT="${CHIPCOIN_ROOT:-}"
NETWORK="${CHIPCOIN_NETWORK:-testnet}"
EXPECTED="${EXPECTED_PQ_HEIGHT:-20000}"

if [[ -n "$ROOT" && -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="${CHIPCOIN_PYTHON:-$ROOT/.venv/bin/python}"
else
  PYTHON_BIN="${CHIPCOIN_PYTHON:-python3}"
fi

if [[ -n "$ROOT" ]]; then
  export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
fi

"$PYTHON_BIN" - "$NETWORK" "$EXPECTED" <<'PY'
from __future__ import annotations

import sys

network = sys.argv[1]
expected = int(sys.argv[2])

try:
    import chipcoin
    from chipcoin.consensus.pq_activation import pq_support_activation_height
except Exception as exc:
    print(f"Status: ERROR")
    print(f"Reason: import failed: {exc}")
    raise SystemExit(3)

try:
    actual = pq_support_activation_height(network)
except Exception as exc:
    print(f"Status: ERROR")
    print(f"Reason: activation lookup failed: {exc}")
    raise SystemExit(3)

print(f"Python executable: {sys.executable}")
print(f"Chipcoin module: {getattr(chipcoin, '__file__', 'unknown')}")
print(f"Chipcoin version: {getattr(chipcoin, '__version__', 'unknown')}")
print(f"Network: {network}")
print(f"PQ activation height: {actual}")
print(f"Expected: {expected}")
if actual == expected:
    print("Status: PASS")
    raise SystemExit(0)
print("Status: FAIL")
raise SystemExit(1)
PY
