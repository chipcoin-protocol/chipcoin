#!/usr/bin/env bash
set -euo pipefail

: "${SNAPSHOT_DATA:?Set the canonical mainnet SQLite path}"
: "${SNAPSHOT_OUTPUT_DIR:?Set the snapshot publication directory}"
: "${SNAPSHOT_PUBLIC_BASE_URL:?Set the public snapshot base URL}"
: "${SNAPSHOT_SIGNING_KEY_FILE:?Set the protected signing key file path}"
: "${SNAPSHOT_TRUSTED_SIGNER_PUBKEY:?Set the approved Ed25519 public key}"

chipcoin_bin="${CHIPCOIN_BIN:-chipcoin}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p -- "$SNAPSHOT_OUTPUT_DIR"
work_dir="$(mktemp -d -- "${TMPDIR:-/tmp}/chipcoin-rc1-snapshot.XXXXXXXX")"
trap 'rm -f -- "$work_dir/snapshot"; rmdir -- "$work_dir" 2>/dev/null || true' EXIT

"$chipcoin_bin" --network mainnet --data "$SNAPSHOT_DATA" snapshot-export \
  --snapshot-file "$work_dir/snapshot" --snapshot-format v2 >/dev/null
sign_result="$("$chipcoin_bin" snapshot-sign \
  --snapshot-file "$work_dir/snapshot" --private-key-file "$SNAPSHOT_SIGNING_KEY_FILE")"
signer_pubkey="$(SIGN_RESULT="$sign_result" python3 -c 'import json,os; print(json.loads(os.environ["SIGN_RESULT"])["signer_public_key_hex"])')"
if [[ "${signer_pubkey,,}" != "${SNAPSHOT_TRUSTED_SIGNER_PUBKEY,,}" ]]; then
  printf '%s\n' 'Snapshot signer differs from the approved public key.' >&2
  exit 1
fi
python3 "$script_dir/publish-rc1-snapshot.py" \
  --snapshot-file "$work_dir/snapshot" \
  --output-dir "$SNAPSHOT_OUTPUT_DIR" \
  --base-url "$SNAPSHOT_PUBLIC_BASE_URL" \
  --network mainnet \
  --trusted-signer-pubkey "$SNAPSHOT_TRUSTED_SIGNER_PUBKEY"
