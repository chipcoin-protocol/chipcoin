#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$REPO_ROOT"

if [[ ! -f .env ]]; then
  printf 'ERROR Missing .env in %s\n' "$REPO_ROOT" >&2
  exit 1
fi

set -a
. ./.env
set +a

services=("$@")
if [[ ${#services[@]} -eq 0 ]]; then
  services=(node miner)
fi

docker compose stop "${services[@]}" 2>/dev/null || true
docker compose rm -sf "${services[@]}" 2>/dev/null || true

if printf '%s\n' "${services[@]}" | grep -qx 'node'; then
  if [[ -z "${NODE_DATA_PATH:-}" ]]; then
    printf 'ERROR NODE_DATA_PATH is empty in .env\n' >&2
    exit 1
  fi
  mkdir -p "$(dirname -- "$NODE_DATA_PATH")"
  rm -f -- "$NODE_DATA_PATH"
  : > "$NODE_DATA_PATH"
  rm -f -- "${NODE_DATA_PATH}.snapshot.meta.json"
  if [[ -n "${NODE_SNAPSHOT_FILE:-}" ]]; then
    rm -f -- "$NODE_SNAPSHOT_FILE"
  fi
  printf 'INFO reset node chain state at %s\n' "$NODE_DATA_PATH"
fi

printf 'INFO reset complete for services: %s\n' "${services[*]}"
