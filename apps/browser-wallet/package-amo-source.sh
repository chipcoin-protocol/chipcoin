#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ARTIFACTS_DIR="${REPO_ROOT}/build/browser-wallet"
PACKAGE_NAME="$(node -p "require('${SCRIPT_DIR}/package.json').name")"
PACKAGE_VERSION="$(node -p "require('${SCRIPT_DIR}/package.json').version")"
ARCHIVE_BASENAME="${PACKAGE_NAME}-firefox-${PACKAGE_VERSION}-source"
STAGING_DIR="${ARTIFACTS_DIR}/${ARCHIVE_BASENAME}"
ARCHIVE_PATH="${ARTIFACTS_DIR}/${ARCHIVE_BASENAME}.zip"
APP_STAGING_DIR="${STAGING_DIR}/apps/browser-wallet"

copy_required_file() {
  local source_path="$1"
  local target_path="${APP_STAGING_DIR}/${source_path}"

  if [[ ! -f "${SCRIPT_DIR}/${source_path}" ]]; then
    echo "Required source file missing: ${SCRIPT_DIR}/${source_path}" >&2
    exit 1
  fi

  mkdir -p "$(dirname "${target_path}")"
  cp "${SCRIPT_DIR}/${source_path}" "${target_path}"
}

copy_required_dir() {
  local source_path="$1"
  local target_path="${APP_STAGING_DIR}/${source_path}"

  if [[ ! -d "${SCRIPT_DIR}/${source_path}" ]]; then
    echo "Required source directory missing: ${SCRIPT_DIR}/${source_path}" >&2
    exit 1
  fi

  mkdir -p "$(dirname "${target_path}")"
  cp -R "${SCRIPT_DIR}/${source_path}" "${target_path}"
}

mkdir -p "${ARTIFACTS_DIR}"
rm -rf "${STAGING_DIR}" "${ARCHIVE_PATH}"
mkdir -p "${APP_STAGING_DIR}"

copy_required_file "package.json"
copy_required_file "package-lock.json"
copy_required_file "tsconfig.json"
copy_required_file "vite.config.ts"
copy_required_file "README.md"
copy_required_file "build-all.sh"
copy_required_file "package-firefox.sh"
copy_required_file "package-amo-source.sh"
copy_required_file "popup.html"
copy_required_file "settings.html"
copy_required_file "onboarding.html"

copy_required_dir "manifest"
copy_required_dir "public"
copy_required_dir "src"
copy_required_dir "tests"

cat > "${STAGING_DIR}/README.md" <<'README'
# Chipcoin Wallet Firefox Source Package

This archive contains the original source code for the Firefox version of
Chipcoin Wallet submitted to Mozilla Add-ons.

## Purpose

Mozilla Add-ons requires source code for extensions containing minified,
bundled, concatenated, or otherwise machine-generated JavaScript. The submitted
extension bundle is generated from the source files in this archive using Vite.

## Requirements

- Node.js 22.x
- npm

No vendored `node_modules` directory is included. Dependencies are installed
from the official npm registry using the included `package-lock.json`.

## Build Steps

From the archive root:

```bash
cd apps/browser-wallet
npm ci
npm run prepare:firefox
```

The generated Firefox extension output is written to:

```text
apps/browser-wallet/dist-firefox
```

The submitted `.xpi` is packaged from that `dist-firefox` directory.

To also run the Firefox package lint/package step:

```bash
npm run package:firefox
```

Without AMO credentials, this creates an unsigned XPI in:

```text
build/browser-wallet/chipcoin-browser-wallet-firefox-unsigned.xpi
```

## Notes for Reviewers

- The Firefox manifest source is `apps/browser-wallet/manifest/firefox.json`.
- The Vite Firefox build uses `--mode firefox`.
- The package intentionally excludes generated directories such as `dist`,
  `dist-firefox`, `dist-chrome`, `node_modules`, and repository build outputs.
- The wallet source does not use `eval`, dynamic code generation, direct
  `innerHTML`, or React `dangerouslySetInnerHTML`.
- The Firefox production bundle is built with a Preact-compatible runtime and
  is rewritten during Vite chunk rendering to avoid AMO `innerHTML` false
  positives from framework compatibility branches that the wallet does not use.
README

(
  cd "${ARTIFACTS_DIR}"
  zip -qr "${ARCHIVE_PATH}" "${ARCHIVE_BASENAME}"
)

echo "AMO source archive created:"
echo "  ${ARCHIVE_PATH}"
echo
echo "Upload this archive to the Mozilla Add-ons source code field for version ${PACKAGE_VERSION}."
