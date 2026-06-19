#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo "[1/5] Building Chrome extension..."
npm run build:chrome
rm -rf dist-chrome
mv dist dist-chrome

echo "[2/5] Building Firefox extension..."
npm run build:firefox
rm -rf dist-firefox
mv dist dist-firefox

echo "[3/5] Packaging Firefox XPI..."
./package-firefox.sh

echo "[4/5] Build outputs ready:"
echo "  Chrome : ${SCRIPT_DIR}/dist-chrome"
echo "  Firefox: ${SCRIPT_DIR}/dist-firefox"
echo "  Firefox unsigned XPI: ${SCRIPT_DIR}/../../build/browser-wallet/chipcoin-browser-wallet-firefox-unsigned.xpi"

echo "[5/5] Done."
