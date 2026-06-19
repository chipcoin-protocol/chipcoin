#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist-firefox"
ARTIFACTS_DIR="${REPO_ROOT}/build/browser-wallet"
UNSIGNED_XPI="${ARTIFACTS_DIR}/chipcoin-browser-wallet-firefox-unsigned.xpi"

cd "${SCRIPT_DIR}"

if [[ ! -f "${DIST_DIR}/manifest.json" ]]; then
  echo "Firefox build output not found: ${DIST_DIR}/manifest.json" >&2
  echo "Run: npm run build:firefox && mv dist dist-firefox" >&2
  exit 1
fi

mkdir -p "${ARTIFACTS_DIR}"
rm -f "${UNSIGNED_XPI}"

echo "[1/2] Packaging unsigned Firefox XPI..."
(
  cd "${DIST_DIR}"
  zip -qr "${UNSIGNED_XPI}" .
)

echo "Unsigned XPI: ${UNSIGNED_XPI}"
echo
echo "Note: Firefox Release/Beta requires Mozilla signing for normal installation."
echo "The unsigned XPI is useful for Developer Edition/Nightly or policy-controlled test installs only."

if [[ -n "${AMO_JWT_ISSUER:-}" && -n "${AMO_JWT_SECRET:-}" ]]; then
  if [[ ! -x "${SCRIPT_DIR}/node_modules/.bin/web-ext" ]]; then
    echo "AMO credentials are set, but web-ext is not installed in this package." >&2
    echo "Install dependencies with: npm install" >&2
    exit 1
  fi

  echo
  echo "[2/2] Signing Firefox XPI through AMO as unlisted..."
  npx web-ext sign \
    --source-dir "${DIST_DIR}" \
    --artifacts-dir "${ARTIFACTS_DIR}" \
    --channel unlisted \
    --api-key "${AMO_JWT_ISSUER}" \
    --api-secret "${AMO_JWT_SECRET}"
else
  echo
  echo "[2/2] Signing skipped."
  echo "To create an installable Firefox package, set AMO_JWT_ISSUER and AMO_JWT_SECRET, then rerun:"
  echo "  AMO_JWT_ISSUER=... AMO_JWT_SECRET=... npm run package:firefox"
fi
