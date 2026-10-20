#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist-firefox"
ARTIFACTS_DIR="${REPO_ROOT}/build/browser-wallet"
UNSIGNED_XPI="${ARTIFACTS_DIR}/chipcoin-browser-wallet-firefox-unsigned.xpi"
WEB_EXT_BIN="${SCRIPT_DIR}/node_modules/.bin/web-ext"
WEB_EXT_RELEASE="${SCRIPT_DIR}/scripts/web-ext-release.sh"
SIGN_CONFIG_DIR=""

cleanup_sign_config() {
  if [[ -n "${SIGN_CONFIG_DIR}" ]]; then
    rm -rf -- "${SIGN_CONFIG_DIR}"
  fi
}
trap cleanup_sign_config EXIT
trap 'cleanup_sign_config; exit 129' HUP
trap 'cleanup_sign_config; exit 130' INT
trap 'cleanup_sign_config; exit 143' TERM

cd "${SCRIPT_DIR}"

if [[ ! -f "${DIST_DIR}/manifest.json" ]]; then
  echo "Firefox build output not found: ${DIST_DIR}/manifest.json" >&2
  echo "Run: npm run build:firefox && mv dist dist-firefox" >&2
  exit 1
fi

mkdir -p "${ARTIFACTS_DIR}"
rm -f "${UNSIGNED_XPI}"

if [[ ! -x "${WEB_EXT_BIN}" || ! -x "${WEB_EXT_RELEASE}" ]]; then
  echo "web-ext is not installed in this package." >&2
  echo "Install dependencies with: npm ci" >&2
  exit 1
fi

echo "[1/3] Linting Firefox extension with web-ext..."
"${WEB_EXT_RELEASE}" lint --source-dir "${DIST_DIR}"

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
  SIGN_CONFIG_DIR="$(mktemp -d)"
  chmod 700 "${SIGN_CONFIG_DIR}"
  amo_jwt_secret="${AMO_JWT_SECRET}"
  unset AMO_JWT_SECRET
  printf '%s' "${amo_jwt_secret}" | node "${SCRIPT_DIR}/scripts/create-web-ext-sign-config.mjs" "${SIGN_CONFIG_DIR}/web-ext.config.cjs"
  unset amo_jwt_secret
  "${WEB_EXT_RELEASE}" sign \
    --config "${SIGN_CONFIG_DIR}/web-ext.config.cjs" \
    --no-config-discovery \
    --source-dir "${DIST_DIR}" \
    --artifacts-dir "${ARTIFACTS_DIR}" \
    --channel unlisted \
    --api-key "${AMO_JWT_ISSUER}"
else
  echo
  echo "[3/3] Signing skipped."
  echo "To create an installable Firefox package, set AMO_JWT_ISSUER and AMO_JWT_SECRET, then rerun:"
  echo "  AMO_JWT_ISSUER=... AMO_JWT_SECRET=... npm run release:firefox"
fi
