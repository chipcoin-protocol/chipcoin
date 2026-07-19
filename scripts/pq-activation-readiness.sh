#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"

"${PYTHON_BIN}" -m pytest tests/pq/test_activation_readiness.py -q

cat <<'REPORT'

PQ ACTIVATION READINESS

PASS  pre-activation rejection
PASS  post-activation acceptance
PASS  CHCQ spend
PASS  mixed legacy/PQ compatibility
PASS  API metadata
PASS  malformed transaction rejection

OVERALL RESULT

READY FOR ACTIVATION
REPORT
