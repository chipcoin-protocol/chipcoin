#!/usr/bin/env bash
set -euo pipefail

CHIPCOIN_BIN="${CHIPCOIN_BIN:-chipcoin}"
CHIPCOIN_NETWORK="${CHIPCOIN_NETWORK:-testnet}"
CHIPCOIN_DATA="${CHIPCOIN_DATA:-/var/lib/chipcoin/data/node-testnet.sqlite3}"
SNAPSHOT_FORMAT="${SNAPSHOT_FORMAT:-v2}"
SNAPSHOT_OUTPUT_DIR="${SNAPSHOT_OUTPUT_DIR:-build/snapshots/testnet}"
SNAPSHOT_PUBLIC_BASE_URL="${SNAPSHOT_PUBLIC_BASE_URL:-https://chipcoinprotocol.com/downloads/snapshots/testnet}"
SNAPSHOT_SOURCE_NODE="${SNAPSHOT_SOURCE_NODE:-$(hostname -f 2>/dev/null || hostname)}"
SNAPSHOT_REQUIRE_SYNCED="${SNAPSHOT_REQUIRE_SYNCED:-true}"
SNAPSHOT_SIGNING_KEY_FILE="${SNAPSHOT_SIGNING_KEY_FILE:-}"
SNAPSHOT_SIGNING_PRIVATE_KEY_HEX="${SNAPSHOT_SIGNING_PRIVATE_KEY_HEX:-}"
SNAPSHOT_TRUST_MODE="${SNAPSHOT_TRUST_MODE:-}"

die() {
  printf 'ERROR %s\n' "$*" >&2
  exit 1
}

if [[ "$CHIPCOIN_NETWORK" != "testnet" ]]; then
  die "This Phase 1 publisher is testnet-only. Set CHIPCOIN_NETWORK=testnet."
fi

if [[ "$SNAPSHOT_FORMAT" != "v2" ]]; then
  die "Only v2 snapshots are supported by this publisher."
fi

command -v python3 >/dev/null 2>&1 || die "python3 is required."
command -v sha256sum >/dev/null 2>&1 || die "sha256sum is required."
command -v stat >/dev/null 2>&1 || die "stat is required."

mkdir -p "$SNAPSHOT_OUTPUT_DIR"

status_json="$("$CHIPCOIN_BIN" --network "$CHIPCOIN_NETWORK" --data "$CHIPCOIN_DATA" status)"
status_check="$(
  STATUS_JSON="$status_json" SNAPSHOT_REQUIRE_SYNCED="$SNAPSHOT_REQUIRE_SYNCED" python3 - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["STATUS_JSON"])
network = payload.get("network")
height = payload.get("height")
tip_hash = payload.get("tip_hash")
sync_phase = payload.get("sync_phase")
require_synced = os.environ.get("SNAPSHOT_REQUIRE_SYNCED", "true").lower() in {"1", "true", "yes"}

if network != "testnet":
    raise SystemExit(f"unexpected node network: {network!r}")
if not isinstance(height, int) or height < 0:
    raise SystemExit("node status did not include a valid height")
if not isinstance(tip_hash, str) or len(tip_hash) != 64:
    raise SystemExit("node status did not include a valid tip_hash")
if require_synced and sync_phase != "synced":
    raise SystemExit(f"node is not synced: sync_phase={sync_phase!r}")

sys.stdout.write(f"{height} {tip_hash} {sync_phase}")
PY
)"

read -r height tip_hash sync_phase <<<"$status_check"
snapshot_name="testnet-snapshot-height-${height}.snapshot"
snapshot_path="${SNAPSHOT_OUTPUT_DIR}/${snapshot_name}"
metadata_path="$(mktemp)"

"$CHIPCOIN_BIN" --network "$CHIPCOIN_NETWORK" --data "$CHIPCOIN_DATA" snapshot-export \
  --snapshot-file "$snapshot_path" \
  --snapshot-format "$SNAPSHOT_FORMAT" \
  > "$metadata_path"

signer_pubkey=""
if [[ -n "$SNAPSHOT_SIGNING_PRIVATE_KEY_HEX" || -n "$SNAPSHOT_SIGNING_KEY_FILE" ]]; then
  if [[ -n "$SNAPSHOT_SIGNING_PRIVATE_KEY_HEX" && -n "$SNAPSHOT_SIGNING_KEY_FILE" ]]; then
    die "Set only one of SNAPSHOT_SIGNING_PRIVATE_KEY_HEX or SNAPSHOT_SIGNING_KEY_FILE."
  fi
  if [[ -n "$SNAPSHOT_SIGNING_KEY_FILE" ]]; then
    [[ -f "$SNAPSHOT_SIGNING_KEY_FILE" ]] || die "Signing key file not found: $SNAPSHOT_SIGNING_KEY_FILE"
    SNAPSHOT_SIGNING_PRIVATE_KEY_HEX="$(tr -d '\n\r ' < "$SNAPSHOT_SIGNING_KEY_FILE")"
  fi
  [[ -n "$SNAPSHOT_SIGNING_PRIVATE_KEY_HEX" ]] || die "Snapshot signing private key is empty."
  sign_json="$("$CHIPCOIN_BIN" snapshot-sign \
    --snapshot-file "$snapshot_path" \
    --private-key-hex "$SNAPSHOT_SIGNING_PRIVATE_KEY_HEX")"
  signer_pubkey="$(
    SIGN_JSON="$sign_json" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["SIGN_JSON"])
print(payload.get("signer_public_key_hex", ""))
PY
  )"
  [[ -n "$signer_pubkey" ]] || die "Snapshot signing did not return a signer public key."
fi

sha256="$(sha256sum "$snapshot_path" | awk '{print $1}')"
size_bytes="$(stat -c '%s' "$snapshot_path")"
manifest_path="${SNAPSHOT_OUTPUT_DIR}/latest.manifest.json"
versioned_manifest_path="${SNAPSHOT_OUTPUT_DIR}/testnet-snapshot-height-${height}.manifest.json"

METADATA_PATH="$metadata_path" \
MANIFEST_PATH="$manifest_path" \
VERSIONED_MANIFEST_PATH="$versioned_manifest_path" \
SNAPSHOT_NAME="$snapshot_name" \
SNAPSHOT_PUBLIC_BASE_URL="$SNAPSHOT_PUBLIC_BASE_URL" \
SNAPSHOT_SOURCE_NODE="$SNAPSHOT_SOURCE_NODE" \
SNAPSHOT_SHA256="$sha256" \
SNAPSHOT_SIZE_BYTES="$size_bytes" \
SNAPSHOT_SIGNER_PUBKEY="$signer_pubkey" \
SNAPSHOT_TRUST_MODE="$SNAPSHOT_TRUST_MODE" \
STATUS_HEIGHT="$height" \
STATUS_TIP_HASH="$tip_hash" \
STATUS_SYNC_PHASE="$sync_phase" \
python3 - <<'PY'
import json
import os
from pathlib import Path

metadata = json.loads(Path(os.environ["METADATA_PATH"]).read_text(encoding="utf-8"))
height = int(metadata["snapshot_height"])
tip_hash = str(metadata["snapshot_block_hash"])
status_height = int(os.environ["STATUS_HEIGHT"])
status_tip_hash = os.environ["STATUS_TIP_HASH"]

if height != status_height:
    raise SystemExit(f"exported snapshot height {height} did not match status height {status_height}")
if tip_hash != status_tip_hash:
    raise SystemExit("exported snapshot tip hash did not match status tip hash")
if metadata.get("network") != "testnet":
    raise SystemExit(f"exported snapshot has wrong network: {metadata.get('network')!r}")

snapshot_name = os.environ["SNAPSHOT_NAME"]
base_url = os.environ["SNAPSHOT_PUBLIC_BASE_URL"].rstrip("/")
snapshot_url = f"{base_url}/{snapshot_name}"
sha256 = os.environ["SNAPSHOT_SHA256"]
size_bytes = int(os.environ["SNAPSHOT_SIZE_BYTES"])
source_node = os.environ["SNAPSHOT_SOURCE_NODE"]
created_at = int(metadata["created_at"])
format_version = int(metadata["format_version"])
signer_pubkey = os.environ["SNAPSHOT_SIGNER_PUBKEY"]
trust_mode = os.environ["SNAPSHOT_TRUST_MODE"] or ("signed" if signer_pubkey else "checksum")

entry = {
    "network": "testnet",
    "snapshot_url": snapshot_url,
    "format_version": format_version,
    "snapshot_height": height,
    "snapshot_block_hash": tip_hash,
    "created_at": created_at,
    "checksum_sha256": sha256,
    "file_name": snapshot_name,
    "size_bytes": size_bytes,
    "source_node": source_node,
    "snapshot_trust_mode": trust_mode,
}
if signer_pubkey:
    entry["signer_pubkeys"] = [signer_pubkey]
manifest = {
    "network": "testnet",
    "height": height,
    "tip_hash": tip_hash,
    "created_at": created_at,
    "file_name": snapshot_name,
    "snapshot_url": snapshot_url,
    "sha256": sha256,
    "checksum_sha256": sha256,
    "size_bytes": size_bytes,
    "source_node": source_node,
    "format_version": format_version,
    "snapshot_trust_mode": trust_mode,
    "snapshots": [entry],
}
if signer_pubkey:
    manifest["signer_pubkeys"] = [signer_pubkey]

for path_name in ("MANIFEST_PATH", "VERSIONED_MANIFEST_PATH"):
    path = Path(os.environ[path_name])
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(
    json.dumps(
        {
            "network": "testnet",
            "height": height,
            "tip_hash": tip_hash,
            "sync_phase": os.environ["STATUS_SYNC_PHASE"],
            "snapshot_file": snapshot_name,
            "manifest_file": Path(os.environ["MANIFEST_PATH"]).name,
            "sha256": sha256,
            "size_bytes": size_bytes,
        },
        indent=2,
        sort_keys=True,
    )
)
PY

rm -f "$metadata_path"
