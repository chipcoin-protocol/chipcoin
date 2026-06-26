#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist-firefox"
ARTIFACTS_DIR="${REPO_ROOT}/build/browser-wallet"
UNSIGNED_XPI="${ARTIFACTS_DIR}/chipcoin-browser-wallet-firefox-unsigned.xpi"
WEB_EXT_BIN="${SCRIPT_DIR}/node_modules/.bin/web-ext"

cd "${SCRIPT_DIR}"

if [[ ! -f "${DIST_DIR}/manifest.json" ]]; then
  echo "Firefox build output not found: ${DIST_DIR}/manifest.json" >&2
  echo "Run: npm run build:firefox && mv dist dist-firefox" >&2
  exit 1
fi

mkdir -p "${ARTIFACTS_DIR}"
rm -f "${UNSIGNED_XPI}"

if [[ ! -x "${WEB_EXT_BIN}" ]]; then
  echo "web-ext is not installed in this package." >&2
  echo "Install dependencies with: npm ci" >&2
  exit 1
fi

echo "[1/3] Linting Firefox extension with web-ext..."
"${WEB_EXT_BIN}" lint --source-dir "${DIST_DIR}"

echo
echo "[2/3] Packaging unsigned Firefox XPI..."
(
  cd "${DIST_DIR}"
  zip -qr "${UNSIGNED_XPI}" .
)

echo "Unsigned XPI: ${UNSIGNED_XPI}"
echo
echo "Note: Firefox Release/Beta requires Mozilla signing for normal installation."
echo "The unsigned XPI is useful for Developer Edition/Nightly or policy-controlled test installs only."

if [[ -n "${AMO_JWT_ISSUER:-}" && -n "${AMO_JWT_SECRET:-}" ]]; then
  echo
  echo "[3/3] Signing Firefox XPI through AMO as unlisted..."
  "${WEB_EXT_BIN}" sign \
    --source-dir "${DIST_DIR}" \
    --artifacts-dir "${ARTIFACTS_DIR}" \
    --channel unlisted \
    --api-key "${AMO_JWT_ISSUER}" \
    --api-secret "${AMO_JWT_SECRET}"
else
  echo
  echo "[3/3] Signing skipped."
  echo "To create an installable Firefox package, set AMO_JWT_ISSUER and AMO_JWT_SECRET, then rerun:"
  echo "  AMO_JWT_ISSUER=... AMO_JWT_SECRET=... npm run release:firefox"
fi
