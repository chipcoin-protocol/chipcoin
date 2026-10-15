#!/usr/bin/env bash
set -euo pipefail

ROOT="${REHEARSAL_ROOT:-/tmp/chipcoin-mainnet-docker-rehearsal}"
COMPOSE_FILE="docker/compose/docker-compose.mainnet-rehearsal.yml"
PROJECT="chipcoin-mainnet-rehearsal"
OUT="$ROOT/maturity-pq"
RAW="$OUT/transaction.raw.hex"
MANIFEST="$OUT/transaction-manifest.json"
EXPECTED_TXID="234011c56a21dc12c2917245c67e081ac8198405bd4ea52347314e27253735cf"
SOURCE_TXID="a1533fe392056d7052b15868cd06d3424d65ed39613219d1af2c6cf7cb1c0d23"
SOURCE_VOUT=0
SOURCE_ADDRESS="CHCQCqkLGiYRsrsrrnJZLC1Xwrq3AEHwKTHGEZ4mg8HLgwo9zRN3KHNG"
DESTINATION="CHCQCqiwih5HyVzieodVeHj4L9YBWx3mQ62ktz1SFhuc85TSnofyTV3F"

compose() { REHEARSAL_ROOT="$ROOT" docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"; }
height() { compose exec -T node-a chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 status | jq -r '.height // -1'; }
verify_payload() { .venv/bin/python scripts/mainnet-pq-verify-persisted-transaction.py --raw "$RAW" --manifest "$MANIFEST"; }
fail() { echo "$(date -Is) FAIL $*"; printf 'FAIL\n' >"$OUT/result"; exit 1; }

state() {
  local node="$1"
  compose exec -T "$node" python3 /app/scripts/mainnet-rehearsal-state.py \
    --data /runtime/mainnet/node.sqlite3 --address "source=$SOURCE_ADDRESS" --address "destination=$DESTINATION"
}

tx_in_mempool() {
  compose exec -T "$1" chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 mempool |
    jq -e --arg txid "$EXPECTED_TXID" 'any(.[]; .txid == $txid)' >/dev/null
}

outpoint() {
  compose exec -T node-a python3 - "$SOURCE_ADDRESS" "$SOURCE_TXID" "$SOURCE_VOUT" <<'PY'
import json, sys
from pathlib import Path
from chipcoin.node.service import NodeService
s = NodeService.open_sqlite(Path('/runtime/mainnet/node.sqlite3'), network='mainnet')
rows = s.utxo_diagnostics(sys.argv[1])
source_txid, source_vout = sys.argv[2], int(sys.argv[3])
print(json.dumps(next((r for r in rows if r.get('txid') == source_txid and r.get('vout') == source_vout), None), sort_keys=True))
PY
}

mkdir -p "$OUT"
chmod 700 "$OUT"
exec >>"$OUT/watcher.log" 2>&1
echo "$(date -Is) watcher-v2 started; persisted payload only"
verify_payload >"$OUT/startup-payload-verification.json" || fail "persisted payload verification"
[[ "$(jq -r .expected_txid "$MANIFEST")" == "$EXPECTED_TXID" ]] || fail "expected TXID mismatch"

while (( $(height) < 98 )); do sleep 15; done
observed="$(height)"
(( observed == 98 )) || fail "missed premature boundary expected_tip=98 actual=$observed"

for node in node-a node-b node-c; do state "$node"; done | jq -s . >"$OUT/pre-submit-baseline.json"
outpoint >"$OUT/pre-submit-outpoint.json"
jq -e '.mature == false' "$OUT/pre-submit-outpoint.json" >/dev/null || fail "source outpoint unexpectedly mature at tip 98"
verify_payload >"$OUT/pre-premature-payload-verification.json" || fail "payload changed before premature submit"
raw="$(tr -d '\r\n' <"$RAW")"

set +e
compose exec -T node-a chipcoin --network mainnet submit-raw-tx --node-url http://127.0.0.1:8080 "$raw" \
  >"$OUT/premature-submit.stdout" 2>"$OUT/premature-submit.stderr"
rc=$?
set -e
http_status="$(grep -Eo 'HTTP [0-9]{3}' "$OUT/premature-submit.stderr" | tail -1 | awk '{print $2}' || true)"
reason="$(tr '\n' ' ' <"$OUT/premature-submit.stderr" | sed 's/[[:space:]]\+/ /g')"
jq -n --argjson tip "$observed" --arg txid "$EXPECTED_TXID" --arg hash "$(jq -r .raw_sha256 "$MANIFEST")" \
  --arg status "$http_status" --arg reason "$reason" --arg stdout "$(cat "$OUT/premature-submit.stdout")" \
  --arg stderr "$(cat "$OUT/premature-submit.stderr")" --argjson rc "$rc" \
  '{tip:$tip,candidate_block_height:($tip+1),txid:$txid,raw_payload_sha256:$hash,http_status:$status,rejection_reason:$reason,stdout:$stdout,stderr:$stderr,exit_code:$rc}' \
  >"$OUT/PREMATURE_REJECTION_REPORT.json"
(( rc != 0 )) || { printf 'BLOCKER\n' >"$OUT/result"; fail "premature transaction accepted"; }

for node in node-a node-b node-c; do
  ! tx_in_mempool "$node" || fail "premature transaction present in $node mempool"
done
outpoint >"$OUT/post-rejection-outpoint.json"
jq -e '.mature == false' "$OUT/post-rejection-outpoint.json" >/dev/null || fail "source maturity changed after rejection"
for node in node-a node-b node-c; do state "$node"; done | jq -s . >"$OUT/post-rejection-states.json"
echo "$(date -Is) PASS premature rejection recorded"

while (( $(height) < 99 )); do sleep 5; done
observed="$(height)"
(( observed == 99 )) || fail "missed mature boundary expected_tip=99 actual=$observed"
verify_payload >"$OUT/pre-mature-payload-verification.json" || fail "payload differs from immutable manifest"
raw="$(tr -d '\r\n' <"$RAW")"

set +e
compose exec -T node-a chipcoin --network mainnet submit-raw-tx --node-url http://127.0.0.1:8080 "$raw" \
  >"$OUT/mature-submit.stdout" 2>"$OUT/mature-submit.stderr"
rc=$?
set -e
(( rc == 0 )) || fail "mature transaction rejected; evidence preserved"
jq -n --argjson tip "$observed" --arg txid "$EXPECTED_TXID" --arg hash "$(jq -r .raw_sha256 "$MANIFEST")" \
  '{status:"MEMPOOL_ACCEPTED",tip:$tip,candidate_block_height:($tip+1),txid:$txid,raw_payload_sha256:$hash}' >"$OUT/MEMPOOL_ACCEPTED.json"

for node in node-a node-b node-c; do
  found=0
  for _ in $(seq 1 30); do tx_in_mempool "$node" && { found=1; break; }; sleep 1; done
  (( found == 1 )) || fail "mempool propagation failed node=$node"
done

confirmed=""
for _ in $(seq 1 720); do
  confirmed="$(compose exec -T node-a chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 tx "$EXPECTED_TXID" 2>/dev/null || true)"
  jq -e '.location == "chain"' <<<"$confirmed" >/dev/null 2>&1 && break
  sleep 5
done
jq -e '.location == "chain"' <<<"$confirmed" >/dev/null 2>&1 || fail "transaction not confirmed"
printf '%s\n' "$confirmed" >"$OUT/confirmed-transaction.json"
block_hash="$(jq -r .block_hash <<<"$confirmed")"
block_height="$(jq -r '.height // .block_height' <<<"$confirmed")"
compose exec -T node-a chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 block --hash "$block_hash" >"$OUT/confirmed-block.json"
jq -e --arg txid "$EXPECTED_TXID" --arg dst "$DESTINATION" --arg src "$SOURCE_ADDRESS" '
  .transactions[] | select(.txid==$txid) |
  (.inputs|length)==1 and .inputs[0].sig_scheme_id==10 and
  (.outputs|length)==2 and
  any(.outputs[]; .recipient==$dst and .value==100000000) and
  any(.outputs[]; .recipient==$src and .value==4899999000)' "$OUT/confirmed-block.json" >/dev/null || fail "confirmed transaction structure mismatch"

for node in node-a node-b node-c; do state "$node"; done | jq -s . >"$OUT/final-states.json"
jq -e '([.[] | del(.node,.peer_count,.process)] | unique | length)==1' "$OUT/final-states.json" >/dev/null || fail "A/B/C final state divergence"
jq -n --argjson height "$block_height" --arg hash "$block_hash" --arg txid "$EXPECTED_TXID" \
  '{status:"BLOCK_CONFIRMED",block_height:$height,block_hash:$hash,txid:$txid,amount_chipbits:100000000,change_chipbits:4899999000,fee_chipbits:1000,scheme_id:10}' \
  >"$OUT/BLOCK_CONFIRMED.json"
printf 'PASS\n' >"$OUT/result"
echo "$(date -Is) PASS maturity/PQ boundary complete"
