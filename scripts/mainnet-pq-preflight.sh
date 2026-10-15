#!/usr/bin/env bash
set -euo pipefail

compose_file="docker-compose.yml"
env_file=".env"
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
wallet_parser="$script_dir/mainnet_preflight_wallet_json.py"

while (($#)); do
  case "$1" in
    --compose-file) compose_file="$2"; shift 2 ;;
    --env-file) env_file="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }
pass() { printf 'PASS %s\n' "$*"; }

command -v docker >/dev/null || fail "docker is not installed"
command -v jq >/dev/null || fail "jq is not installed"
[[ -f "$compose_file" ]] || fail "compose file not found: $compose_file"
[[ -f "$env_file" ]] || fail "environment file not found: $env_file"

config="$(docker compose --env-file "$env_file" -f "$compose_file" config --format json)"
network="$(jq -r '.services.node.environment.CHIPCOIN_NETWORK // empty' <<<"$config")"
[[ "$network" == "mainnet" ]] || fail "resolved node network is '$network', expected mainnet"
pass "network - mainnet"

runtime_source="$(jq -r '.services.node.volumes[]? | select(.target == "/runtime/mainnet") | .source' <<<"$config")"
[[ -d "$runtime_source" ]] || fail "mainnet runtime mount is missing"
case "$(realpath "$runtime_source")/" in
  */secrets/*|*/wallets/*) fail "runtime mount contains a secret directory: $runtime_source" ;;
esac
pass "runtime separation - $runtime_source is the only read-write node data mount"

check_wallet_mount() {
  local service="$1" target="$2" label="$3" source readonly wallet checksum_before checksum_after
  local stdout_file stderr_file command_status probe_status
  source="$(jq -r --arg service "$service" --arg target "$target" '
    .services[$service].volumes[]?
    | select(.target == $target)
    | .source
  ' <<<"$config" | head -n1)"
  readonly="$(jq -r --arg service "$service" --arg target "$target" '
    .services[$service].volumes[]?
    | select(.target == $target)
    | .read_only
  ' <<<"$config" | head -n1)"
  [[ -n "$source" && "$source" != "null" ]] || fail "$label mount is missing ($target)"
  [[ -f "$source" ]] || fail "$label source does not exist: $source"
  [[ "$readonly" == "true" ]] || fail "$label mount is not read-only: $source"

  stdout_file="$(mktemp)"
  stderr_file="$(mktemp)"
  set +e
  docker compose --env-file "$env_file" -f "$compose_file" run --rm --no-deps \
    --entrypoint chipcoin "$service" --network mainnet wallet-address --wallet-file "$target" \
    >"$stdout_file" 2>"$stderr_file"
  command_status=$?
  set -e
  if ! wallet="$(python3 "$wallet_parser" \
      --stdout-file "$stdout_file" \
      --stderr-file "$stderr_file" \
      --exit-code "$command_status" \
      --label "$label")"; then
    rm -f "$stdout_file" "$stderr_file"
    exit 1
  fi
  rm -f "$stdout_file" "$stderr_file"
  case "$(realpath "$source")" in
    "$(realpath "$runtime_source")"/*) fail "$label is stored below the read-write runtime directory" ;;
  esac
  checksum_before="$(sha256sum "$source" | awk '{print $1}')"
  set +e
  docker compose --env-file "$env_file" -f "$compose_file" run --rm --no-deps \
    --entrypoint sh "$service" -lc \
    'test -r "$1" || exit 42
     if printf x >>"$1" 2>/dev/null; then exit 41; fi
     if rm -f "$1" 2>/dev/null; then exit 43; fi' sh "$target" \
    >/dev/null 2>/dev/null
  probe_status=$?
  set -e
  case "$probe_status" in
    0) ;;
    41) fail "$label mount is writable: $target" ;;
    42) fail "$label cannot be read in the container: $target" ;;
    43) fail "$label can be deleted from the container: $target" ;;
    *) fail "$label read-only mutation probe failed (exit $probe_status)" ;;
  esac
  checksum_after="$(sha256sum "$source" | awk '{print $1}')"
  [[ "$checksum_before" == "$checksum_after" ]] || fail "$label changed during read-only probe"
  pass "$label - $(jq -r .address <<<"$wallet") source=$source read_only=true"
}

check_wallet_mount miner /runtime/miner-wallet.json "miner wallet"

owner_target="$(jq -r '.services.node.environment.REWARD_NODE_AUTO_OWNER_WALLET_FILE // empty' <<<"$config")"
attest_target="$(jq -r '.services.node.environment.REWARD_NODE_AUTO_ATTEST_WALLET_FILE // empty' <<<"$config")"
if [[ -n "$owner_target" ]]; then
  check_wallet_mount node "$owner_target" "reward owner wallet"
  [[ -n "$attest_target" ]] || fail "reward attestation wallet is not configured"
  check_wallet_mount node "$attest_target" "reward attestation wallet"
else
  pass "reward automation - disabled"
fi

for source in \
  "$(jq -r '.services.miner.volumes[] | select(.target == "/runtime/miner-wallet.json") | .source' <<<"$config")" \
  "$(jq -r '.services.node.volumes[] | select(.target == "/runtime/reward-owner-wallet.json") | .source' <<<"$config")" \
  "$(jq -r '.services.node.volumes[] | select(.target == "/runtime/reward-attest-wallet.json") | .source' <<<"$config")"; do
  [[ "$(realpath "$source")" != "$PWD"/* ]] || git check-ignore -q "$source" || fail "wallet source is not ignored by Git: $source"
done
pass "secret hygiene - wallets are outside runtime and repository"

pass "compose validation - mainnet PQ preflight complete"
