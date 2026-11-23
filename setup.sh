#!/bin/sh
# Docker-first public setup. This script does not invoke host Python or start services.
set -eu

fail() { printf 'Setup: %s\n' "$*" >&2; exit 1; }

[ -t 0 ] && [ -t 1 ] || fail 'Run ./setup.sh from an interactive terminal.'
command -v git >/dev/null 2>&1 || fail 'Git is required.'
command -v docker >/dev/null 2>&1 || fail 'Docker Engine or Docker Desktop is required.'
docker info >/dev/null 2>&1 || fail 'Docker daemon is unavailable. Start Docker and check access.'
docker compose version >/dev/null 2>&1 || fail 'Docker Compose v2 is required.'

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
[ -f "$script_dir/Dockerfile" ] && [ -f "$script_dir/Dockerfile.setup" ] && [ -f "$script_dir/scripts/setup/wizard.py" ] && [ -f "$script_dir/docker-compose.yml" ] && [ -f "$script_dir/docker-compose.setup-runtime.yml" ] || fail 'Incomplete Chipcoin checkout.'
repo=$(git -C "$script_dir" rev-parse --show-toplevel 2>/dev/null) || fail 'Use a Git checkout of Chipcoin.'
[ "$repo" = "$script_dir" ] || fail 'Run this script from its Chipcoin checkout.'
git -C "$repo" diff --quiet HEAD -- .dockerignore Dockerfile Dockerfile.setup setup.sh scripts/setup src vendor docker docker-compose.yml docker-compose.setup-runtime.yml || fail 'Checkout has uncommitted setup or Core changes; use a clean, reviewable checkout.'
[ -z "$(git -C "$repo" ls-files --others --exclude-standard -- Dockerfile.setup setup.sh scripts/setup src vendor docker docker-compose.setup-runtime.yml)" ] || fail 'Checkout contains untracked setup or Core files; use a clean checkout.'

case "$(uname -s):$(uname -m)" in
  Linux:x86_64|Darwin:x86_64) platform=linux/amd64 ;;
  Linux:aarch64|Linux:arm64|Darwin:arm64) platform=linux/arm64 ;;
  *) fail 'Supported hosts: Linux x86_64/AArch64 and macOS Intel/Apple Silicon.' ;;
esac
docker_arch=$(docker info --format '{{.Architecture}}' 2>/dev/null) || fail 'Cannot inspect Docker architecture.'
case "$platform:$docker_arch" in
  linux/amd64:x86_64|linux/amd64:amd64|linux/arm64:aarch64|linux/arm64:arm64) ;;
  *) fail "Docker architecture $docker_arch does not match host target $platform; refusing emulation." ;;
esac

case "$(uname -s)" in
  Darwin) default_storage="$HOME/Library/Application Support/Chipcoin" ;;
  *) default_storage="${XDG_DATA_HOME:-$HOME/.local/share}/chipcoin" ;;
esac
printf 'Persistent storage base [%s]: ' "$default_storage"
IFS= read -r storage_answer || fail 'No storage selection received.'
storage=${storage_answer:-$default_storage}
case "$storage" in /*) ;; *) fail 'Storage path must be absolute.' ;; esac
[ ! -L "$storage" ] || fail 'Storage base must not be a symbolic link.'
if [ ! -d "$storage" ]; then
  (umask 077; mkdir -p -- "$storage") || fail "Cannot create $storage. Choose a writable user-owned path or provision it explicitly."
fi
[ -w "$storage" ] || fail "Storage base is not writable: $storage"
storage=$(CDPATH= cd -- "$storage" && pwd -P)
result_path="$storage/.chipcoin-setup-result-$$.json"
[ ! -e "$result_path" ] || fail 'Setup result path already exists; retry.'
trap 'rm -f -- "$result_path"' EXIT HUP INT TERM

revision=$(git -C "$repo" rev-parse --short=12 HEAD)
full_revision=$(git -C "$repo" rev-parse HEAD)
core_image="chipcoin-setup-core:$revision-$docker_arch"
setup_image="chipcoin-setup:$revision-$docker_arch"
printf 'Building pinned Chipcoin Core for %s from commit %s...\n' "$platform" "$revision"
docker build --pull --platform "$platform" --label "org.opencontainers.image.revision=$full_revision" -f "$repo/Dockerfile" -t "$core_image" "$repo" || fail 'Core image build failed. Check Docker/network access and try again.'
docker build --platform "$platform" --label "org.opencontainers.image.revision=$full_revision" -f "$repo/Dockerfile.setup" --build-arg "CORE_IMAGE=$core_image" -t "$setup_image" "$repo" || fail 'Setup image build failed.'
core_revision=$(docker image inspect "$core_image" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}') || fail 'Cannot inspect Core image provenance.'
setup_revision=$(docker image inspect "$setup_image" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}') || fail 'Cannot inspect setup image provenance.'
[ "$core_revision" = "$full_revision" ] && [ "$setup_revision" = "$full_revision" ] || fail 'Image revision does not match this checkout.'
image_arch=$(docker image inspect "$setup_image" --format '{{.Architecture}}') || fail 'Cannot inspect setup image.'
case "$platform:$image_arch" in
  linux/amd64:amd64|linux/arm64:arm64) ;;
  *) fail 'Built setup image has the wrong architecture.' ;;
esac

uid=$(id -u)
gid=$(id -g)
docker run --rm --interactive --tty --init --platform "$platform" --user "$uid:$gid" \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$repo,target=/workspace,readonly" \
  --mount "type=bind,source=$storage,target=$storage" \
  --env CHIPCOIN_SETUP_IN_CONTAINER=1 \
  --env CHIPCOIN_SETUP_REPO_ROOT=/workspace \
  --env "CHIPCOIN_SETUP_HOST_REPO=$repo" \
  --env "CHIPCOIN_SETUP_HOST_NAME=$(hostname)" \
  --env "CHIPCOIN_SETUP_STORAGE_BASE=$storage" \
  --env "CHIPCOIN_SETUP_RESULT_PATH=$result_path" \
  "$setup_image" || fail 'Wizard did not complete; existing wallets and settings were not replaced.'

[ -s "$result_path" ] || fail 'Wizard did not write a completion record.'
IFS= read -r env_path < "$result_path" || fail 'Cannot read setup completion record.'
[ -n "$env_path" ] && [ -f "$env_path" ] || fail 'Generated environment file is missing.'
docker compose --env-file "$env_path" -f "$repo/docker-compose.yml" -f "$repo/docker-compose.setup-runtime.yml" config --quiet || fail 'Generated Docker Compose configuration is invalid.'
printf '\nCompose configuration verified. Services have not been started. Follow the commands printed above.\n'
