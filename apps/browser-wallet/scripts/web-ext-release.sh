#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_EXT_BIN="${SCRIPT_DIR}/../node_modules/.bin/web-ext"
action="${1:-}"

case "${action}" in
  lint|sign) shift ;;
  *)
    echo "Release wrapper permits only web-ext lint or sign; Android/ADB commands are disabled." >&2
    exit 64
    ;;
esac

for arg in "$@"; do
  case "${arg,,}" in
    --android*|--adb*|--device*|--target*|--firefox-apk*)
      echo "Android/ADB-related web-ext options are disabled for release operations." >&2
      exit 64
      ;;
  esac
done

if [[ ! -x "${WEB_EXT_BIN}" ]]; then
  echo "web-ext is not installed; run npm ci in apps/browser-wallet." >&2
  exit 69
fi

unset ADB_SERVER_SOCKET ADB_SERVER_PORT ANDROID_ADB_SERVER_PORT ANDROID_SERIAL ANDROID_HOME ANDROID_SDK_ROOT
exec "${WEB_EXT_BIN}" "${action}" "$@"
