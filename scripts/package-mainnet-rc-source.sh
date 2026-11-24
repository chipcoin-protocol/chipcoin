#!/usr/bin/env bash
# Create a reproducible source archive for isolated RC builds and tests.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'Usage: %s OUTPUT.tar.gz\n' "$0" >&2
  exit 2
fi

destination=$1
if [[ "$destination" != /* ]]; then
  printf 'Use an absolute output path.\n' >&2
  exit 2
fi
repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"
if [[ -n $(git status --porcelain --untracked-files=no) ]]; then
  printf 'Tracked worktree is not clean; commit changes before packaging.\n' >&2
  exit 1
fi
if [[ -e "$destination" ]]; then
  printf 'Archive already exists: %s\n' "$destination" >&2
  exit 1
fi
trap 'rm -f -- "$destination"' ERR

# Include the browser code and its two public, test-only vectors required by
# tests/wallet. No local .env, wallet, database, or untracked file is archived.
git archive --format=tar HEAD \
  Dockerfile Dockerfile.setup MANIFEST.in README.md \
  docker-compose.setup-runtime.yml docker-compose.yml \
  docker pyproject.toml scripts setup.py setup.sh src tests vendor \
  apps/browser-wallet | gzip -n > "$destination"

tar -xOzf "$destination" apps/browser-wallet/tests/fixtures/mldsa44-browser-vector-1.json >/dev/null
tar -xOzf "$destination" apps/browser-wallet/tests/fixtures/pq-vector-1.json >/dev/null
trap - ERR
printf 'Source archive: %s\n' "$destination"
