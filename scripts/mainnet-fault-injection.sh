#!/usr/bin/env bash
set -euo pipefail

ROOT="${REHEARSAL_ROOT:-/tmp/chipcoin-mainnet-docker-rehearsal}"
COMPOSE_FILE="docker/compose/docker-compose.mainnet-rehearsal.yml"
PROJECT="chipcoin-mainnet-rehearsal"
STATE_FILE="$ROOT/fault/state.json"
EVIDENCE="$ROOT/fault/evidence"
NETWORK_A="${PROJECT}_fault_a"
NETWORK_B="${PROJECT}_fault_b"
SHARED_NETWORK="${PROJECT}_rehearsal"
FAULT_LOCK="$ROOT/fault/session.lock"
SESSION_DIR="$ROOT/fault/session"
FAULT_MONITOR_META="$ROOT/fault/monitor-session.json"
FAULT_MONITOR_HEALTH="$ROOT/fault/monitor-health.json"
LEGACY_FAULT_MONITOR_UNIT="chipcoin-mainnet-fault-monitor.service"

compose() { REHEARSAL_ROOT="$ROOT" docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"; }
container() { compose ps -q "$1"; }
container_any() { compose ps -aq "$1"; }
phase() { python3 scripts/mainnet-fault-state.py --state-file "$STATE_FILE" show | jq -r '.phase // "NONE"'; }
transition() {
  python3 scripts/mainnet-fault-state.py --state-file "$STATE_FILE" transition "$1" --evidence "$2" >/dev/null
}
timestamp() { date -u +%Y%m%dT%H%M%SZ; }

write_lock() {
  mkdir -p "$ROOT/fault"
  local session_id="fault-$(timestamp)-$$"
  python3 scripts/mainnet-fault-session.py --lock-file "$FAULT_LOCK" create --session-id "$session_id" >/dev/null
}

release_lock() {
  local session_id
  session_id="$(fault_session_id)"
  fault_monitor_clean_assert
  python3 scripts/mainnet-fault-session.py --lock-file "$FAULT_LOCK" assert-id --session-id "$session_id" >/dev/null
  [[ ! -e "$FAULT_LOCK" ]] || mv "$FAULT_LOCK" "$EVIDENCE/released-lock-$(timestamp).json"
}

systemctl_user() { systemctl --user "$@"; }
systemd_run_user() { systemd-run --user "$@"; }

fault_session_id() { jq -er '.fault_session_id' "$FAULT_LOCK"; }
fault_session_immutable_assert() {
  python3 scripts/mainnet-fault-session.py --lock-file "$FAULT_LOCK" assert-id --session-id "$1" >/dev/null
}

fault_session_update() {
  local session_id="$1" changes="$2"
  python3 scripts/mainnet-fault-session.py --lock-file "$FAULT_LOCK" update \
    --session-id "$session_id" --changes-json "$changes" >/dev/null
}

fault_session_begin_recovery() {
  local session_id="$1" attempt_id="recovery-$(timestamp)-$$"
  python3 scripts/mainnet-fault-session.py --lock-file "$FAULT_LOCK" begin-recovery \
    --session-id "$session_id" --attempt-id "$attempt_id" >/dev/null
}

fault_monitor_unit_for_session() {
  printf 'chipcoin-mainnet-fault-monitor-%s.service\n' "$(printf '%s' "$1" | tr -c 'A-Za-z0-9_.-' '-')"
}

fault_monitor_property() {
  systemctl_user show "$1" --property="$2" --value 2>/dev/null || true
}

fault_monitor_loaded() { [[ "$(fault_monitor_property "$1" LoadState)" == "loaded" ]]; }
fault_monitor_active() { [[ "$(fault_monitor_property "$1" ActiveState)" == "active" ]]; }

fault_monitor_wait_inactive() {
  local unit="$1" timeout="${2:-30}" deadline state
  deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    state="$(fault_monitor_property "$unit" ActiveState)"
    [[ -z "$state" || "$state" == inactive || "$state" == failed ]] && return 0
    sleep 1
  done
  return 1
}

fault_monitor_cleanup_unit() {
  local unit="$1" active
  active="$(fault_monitor_property "$unit" ActiveState)"
  if [[ "$active" == active || "$active" == activating || "$active" == deactivating ]]; then
    systemctl_user stop "$unit"
  fi
  fault_monitor_wait_inactive "$unit" 30
  if ! systemctl_user reset-failed "$unit" >/dev/null 2>&1; then
    fault_monitor_loaded "$unit" && return 1
  fi
  [[ "$(fault_monitor_property "$unit" MainPID)" =~ ^(0)?$ ]]
}

fault_monitor_pre_start_cleanup() {
  local session_id="$1" old_session old_unit
  # Retire the pre-session fixed-name transient unit left by older harnesses.
  fault_monitor_cleanup_unit "$LEGACY_FAULT_MONITOR_UNIT"
  if [[ -f "$FAULT_MONITOR_META" ]]; then
    old_session="$(jq -er '.session_id' "$FAULT_MONITOR_META")"
    old_unit="$(jq -er '.unit_name' "$FAULT_MONITOR_META")"
    if fault_monitor_active "$old_unit"; then
      [[ "$old_session" == "$session_id" ]] || {
        echo "fault monitor belongs to another active session: $old_session" >&2
        return 1
      }
      fault_monitor_healthy "$session_id" || {
        echo "active fault monitor is not healthy for session $session_id" >&2
        return 1
      }
      return 0
    fi
    fault_monitor_cleanup_unit "$old_unit"
    rm -f "$FAULT_MONITOR_META" "$FAULT_MONITOR_HEALTH"
  fi
}

fault_monitor_healthy() {
  local session_id="$1" unit main_pid result health_session iteration
  [[ -f "$FAULT_MONITOR_META" && -f "$FAULT_MONITOR_HEALTH" ]] || return 1
  [[ "$(jq -r '.session_id' "$FAULT_MONITOR_META")" == "$session_id" ]] || return 1
  unit="$(jq -er '.unit_name' "$FAULT_MONITOR_META")"
  [[ "$(fault_monitor_property "$unit" LoadState)" == loaded ]]
  [[ "$(fault_monitor_property "$unit" ActiveState)" == active ]]
  [[ "$(fault_monitor_property "$unit" SubState)" == running ]]
  result="$(fault_monitor_property "$unit" Result)"
  [[ -z "$result" || "$result" == success ]]
  main_pid="$(fault_monitor_property "$unit" MainPID)"
  [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] && kill -0 "$main_pid" 2>/dev/null
  health_session="$(jq -er '.session_id' "$FAULT_MONITOR_HEALTH")"
  iteration="$(jq -er '.iteration' "$FAULT_MONITOR_HEALTH")"
  [[ "$health_session" == "$session_id" && "$iteration" -ge 1 ]]
  jq -e --arg session "$session_id" '.session_id==$session and .status=="PASS"' "$FAULT_MONITOR_HEALTH" >/dev/null
}

fault_monitor_wait_healthy() {
  local session_id="$1" timeout="${2:-30}" deadline
  deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    fault_monitor_healthy "$session_id" && return 0
    sleep 1
  done
  return 1
}

fault_monitor_clean_assert() {
  local unit
  if [[ -f "$FAULT_MONITOR_META" ]]; then
    unit="$(jq -er '.unit_name' "$FAULT_MONITOR_META")"
    ! fault_monitor_active "$unit" || return 1
  fi
  [[ ! -e "$FAULT_MONITOR_META" && ! -e "$FAULT_MONITOR_HEALTH" ]]
}

service_running() {
  local id
  id="$(container "$1")"
  [[ -n "$id" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$id")" == "true" ]]
}

container_networks() {
  local id
  id="$(container_any "$1")"
  [[ -n "$id" ]] || return 1
  docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{"\n"}}{{end}}' "$id" | sort
}

service_on_network() {
  container_networks "$1" | grep -Fxq "$2"
}

normalize_stopped_miner_network() {
  local miner="$1"
  service_running "$miner" && { echo "miner must be stopped before network normalization: $miner" >&2; return 2; }
  if [[ "$(container_networks "$miner" 2>/dev/null || true)" != "$SHARED_NETWORK" ]]; then
    compose rm -sf "$miner" >/dev/null
    compose create "$miner" >/dev/null
  fi
  service_on_network "$miner" "$SHARED_NETWORK"
  ! service_on_network "$miner" "$NETWORK_A"
  ! service_on_network "$miner" "$NETWORK_B"
}

normalize_shared_topology() {
  local service network id
  for service in node-a node-b node-c; do
    network_connect "$SHARED_NETWORK" "$service" "$service"
    id="$(container_any "$service")"
    for network in "$NETWORK_A" "$NETWORK_B"; do
      docker network disconnect "$network" "$id" >/dev/null 2>&1 || true
    done
  done
  normalize_stopped_miner_network miner-a
  normalize_stopped_miner_network miner-b
}

miner_expected_network() {
  local miner="$1" current
  current="$(phase)"
  case "$current" in
    PARTITION_ACTIVE|FORK_CONFIRMED|ORPHAN_TX_CONFIRMED|SCENARIO_A_TX_CONFIRMED|SCENARIO_A_B_WINNING|WINNING_BRANCH_CONFIRMED)
      [[ "$miner" == miner-a ]] && echo "$NETWORK_A" || echo "$NETWORK_B"
      ;;
    SCENARIO_B_PARTITION_ACTIVE|SCENARIO_B_FORK_CONFIRMED|SCENARIO_B_TX_A2_CONFIRMED|SCENARIO_B_TX_B2_CONFIRMED|SCENARIO_B_B_WINNING)
      [[ "$miner" == miner-a ]] && echo "$NETWORK_A" || echo "$NETWORK_B"
      ;;
    *) echo "$SHARED_NETWORK" ;;
  esac
}

miner_targets() {
  local miner="$1"
  local network="${2:-$(miner_expected_network "$1")}"
  if [[ "$network" == "$NETWORK_A" ]]; then
    [[ "$miner" == miner-a ]] || return 2
    echo "node-a"
  elif [[ "$network" == "$NETWORK_B" ]]; then
    [[ "$miner" == miner-b ]] || return 2
    echo "node-b node-c"
  elif [[ "$miner" == miner-a ]]; then
    echo "node-a node-c"
  else
    echo "node-b node-c"
  fi
}

miner_assert_operational() {
  local miner="$1" expected_network="${2:-$(miner_expected_network "$1")}" started_at="${3:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
  local target id found=0
  service_running "$miner" || { echo "miner container is not running: $miner" >&2; return 1; }
  service_on_network "$miner" "$expected_network" || {
    echo "miner is not attached to expected network: miner=$miner network=$expected_network" >&2
    return 1
  }
  id="$(container_any "$miner")"
  for target in $(miner_targets "$miner" "$expected_network"); do
    docker exec "$id" python3 - "$target" <<'PY' >/dev/null
import socket, sys
with socket.create_connection((sys.argv[1], 8080), timeout=5):
    pass
PY
  done
  for _ in $(seq 1 30); do
    if docker logs --since "$started_at" "$id" 2>&1 | grep -Fq "mining template acquired"; then found=1; break; fi
    sleep 1
  done
  (( found == 1 )) || { echo "miner did not acquire a template: $miner" >&2; return 1; }
  echo "MINER_OPERATIONAL_ON_EXPECTED_BRANCH miner=$miner network=$expected_network"
}

miner_control() {
  local action="$1" miner="$2" started_at expected_network
  [[ "$miner" == "miner-a" || "$miner" == "miner-b" ]] || { echo "invalid miner" >&2; return 2; }
  case "$action" in
    start)
      started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      expected_network="$(miner_expected_network "$miner")"
      compose up -d --no-deps "$miner" >/dev/null
      miner_assert_operational "$miner" "$expected_network" "$started_at"
      ;;
    stop) compose stop "$miner" >/dev/null; ! service_running "$miner" ;;
    status) service_running "$miner" && echo running || echo stopped ;;
    *) return 2 ;;
  esac
}

capture_peer_topology() {
  local output="$1"
  for node in node-a node-b node-c; do
    compose exec -T "$node" chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 status |
      jq --arg node "$node" '{node:$node,height,tip_hash,cumulative_work,peer_count,handshaken_peer_count,mempool_size}'
  done | jq -s . >"$output"
}

capture_baseline_current() {
  [[ "$(phase)" == "PARTITION_PREPARED" ]] || { echo "baseline-current requires PARTITION_PREPARED" >&2; return 2; }
  local dir="$EVIDENCE/fault-baseline-$(timestamp)"
  mkdir -p "$dir"
  capture_states "$dir/states.json" node-a node-b node-c || { echo "failed to capture node states" >&2; return 1; }
  assert_equal "$dir/states.json" || { echo "A/B/C are not convergent or SQLite integrity failed" >&2; return 1; }
  capture_peer_topology "$dir/peers.json"
  wallet_manifest "$dir/wallet-checksums.sha256"
  compose ps --format json >"$dir/containers.json"
  docker network inspect "$SHARED_NETWORK" "$NETWORK_A" "$NETWORK_B" >"$dir/networks.json"
  jq -n --arg created_at "$(date -Is)" --arg states "$dir/states.json" --arg peers "$dir/peers.json" \
    '{status:"PASS",created_at:$created_at,states:$states,peers:$peers}' >"$dir/manifest.json"
  transition PARTITION_PREPARED "$dir/manifest.json"
  printf '%s\n' "$dir"
}

active_path() {
  compose exec -T "$1" python3 - <<'PY'
import json, sqlite3
c=sqlite3.connect('/runtime/mainnet/node.sqlite3')
rows=c.execute("SELECT height, block_hash, cumulative_work FROM headers WHERE is_main_chain=1 ORDER BY height").fetchall()
print(json.dumps([{'height':h,'block_hash':bh,'cumulative_work':int(w)} for h,bh,w in rows],sort_keys=True))
PY
}

prepare_transactions() {
  [[ "$(phase)" == "BASELINE" || "$(phase)" == "PARTITION_PREPARED" || "$(phase)" == "FINAL_CONVERGENCE" || "$(phase)" == "SCENARIO_B_PREPARED" ]] || {
    echo "prepare-transactions requires BASELINE, PARTITION_PREPARED, FINAL_CONVERGENCE, or SCENARIO_B_PREPARED" >&2
    return 2
  }
  local address browser reward_a reward_b utxos txdir
  address="$(jq -r .address "$ROOT/secrets/miner-b.json")"
  browser="$(jq -r .address "$ROOT/secrets/browser-wallet.json")"
  reward_a="$(jq -r .address "$ROOT/secrets/reward-a-owner.json")"
  reward_b="$(jq -r .address "$ROOT/secrets/reward-b-owner.json")"
  txdir="$SESSION_DIR/transactions"
  if [[ -d "$txdir" ]] && find "$txdir" -mindepth 1 -print -quit | grep -q .; then
    mv "$txdir" "$EVIDENCE/transactions-archive-$(timestamp)"
  fi
  mkdir -p "$txdir"; chmod 700 "$txdir"
  # Selection uses only the public address; the key remains mounted read-only in miner-b.
  utxos="$(compose exec -T node-a python3 - "$address" <<'PY'
import json,sys
from pathlib import Path
from chipcoin.node.service import NodeService
s=NodeService.open_sqlite(Path('/runtime/mainnet/node.sqlite3'),network='mainnet')
print(json.dumps([r for r in s.utxo_diagnostics(sys.argv[1]) if r['mature']],sort_keys=True))
PY
)"
  [[ "$(jq length <<<"$utxos")" -ge 2 ]] || { echo "need two mature pre-partition UTXOs" >&2; return 1; }
  printf '%s\n' "$utxos" >"$txdir/selected-utxos.json"
  build_fault_tx tx-a 0 "$browser"
  build_fault_tx tx-a2 1 "$reward_a"
  build_fault_tx tx-b2 1 "$reward_b"
  [[ "$(jq -r .source.txid "$txdir/tx-a2/manifest.json")":"$(jq -r .source.vout "$txdir/tx-a2/manifest.json")" == "$(jq -r .source.txid "$txdir/tx-b2/manifest.json")":"$(jq -r .source.vout "$txdir/tx-b2/manifest.json")" ]]
  [[ "$(jq -r .txid "$txdir/tx-a2/manifest.json")" != "$(jq -r .txid "$txdir/tx-b2/manifest.json")" ]]
  jq -n --arg prepared_at "$(date -Is)" --arg dir "$txdir" '{status:"PASS",prepared_at:$prepared_at,directory:$dir}' >"$txdir/manifest.json"
  printf '%s\n' "$txdir/manifest.json"
}

build_fault_tx() {
  local label="$1" index="$2" destination="$3" txdir="$SESSION_DIR/transactions" row build
  build="$txdir/$label-built.json"
  row="$(jq -c --argjson i "$index" '.[$i]' "$txdir/selected-utxos.json")"
  compose exec -T miner-b python3 - --wallet-file /runtime/miner-wallet.json \
    --source-txid "$(jq -r .txid <<<"$row")" --source-vout "$(jq -r .vout <<<"$row")" \
    --source-value "$(jq -r .amount_chipbits <<<"$row")" --destination "$destination" --amount 100000000 --fee 1000 \
    <scripts/mainnet-pq-boundary-transaction.py >"$build"
  chmod 600 "$build"
  .venv/bin/python scripts/mainnet-fault-evidence.py transaction --source "$build" --output-dir "$txdir/$label" >/dev/null
}

submit_branch_tx() {
  local node="$1" label="$2" raw manifest txid
  manifest="$SESSION_DIR/transactions/$label/manifest.json"; raw="$(tr -d '\r\n' <"$SESSION_DIR/transactions/$label/transaction.raw.hex")"
  txid="$(jq -r .txid "$manifest")"
  compose exec -T "$node" chipcoin --network mainnet submit-raw-tx --node-url http://127.0.0.1:8080 "$raw" >"$SESSION_DIR/transactions/$label/submit.json"
  printf '%s\n' "$txid"
}

wait_tx_location() {
  local node="$1" txid="$2" expected="$3" timeout="${4:-1800}" deadline value
  deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    value="$(compose exec -T "$node" chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 tx "$txid" 2>/dev/null || true)"
    jq -e --arg expected "$expected" '.location==$expected' <<<"$value" >/dev/null 2>&1 && { printf '%s\n' "$value"; return; }
    if [[ "$expected" == mempool ]] && compose exec -T "$node" chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 mempool | jq -e --arg txid "$txid" 'any(.[];.txid==$txid)' >/dev/null; then printf '{"location":"mempool"}\n'; return; fi
    sleep 5
  done
  return 1
}

fork_checkpoint() {
  [[ -e "$FAULT_LOCK" ]] || { echo "fault lock missing" >&2; return 1; }
  local dir="$EVIDENCE/fork-$(timestamp)" session_id="$(fault_session_id)"; mkdir -p "$dir"
  active_path node-a >"$dir/path-a.json"; active_path node-b >"$dir/path-b.json"
  .venv/bin/python scripts/mainnet-fault-evidence.py fork --branch-a "$dir/path-a.json" --branch-b "$dir/path-b.json" --output "$dir/fork.json" >/dev/null
  capture_states "$dir/branch-states.json" node-a node-b node-c
  : >"$dir/orphan-candidates-a.jsonl"
  while read -r hash; do
    compose exec -T node-a chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 block --hash "$hash" |
      jq -c '{block_hash,height,coinbase_txid:.transactions[0].txid,coinbase_outputs:.transactions[0].outputs}' >>"$dir/orphan-candidates-a.jsonl"
  done < <(jq -r '.path_a[1:][].block_hash' "$dir/fork.json")
  if [[ "$(phase)" == "SCENARIO_B_PARTITION_ACTIVE" ]]; then
    fault_session_update "$session_id" '{"current_phase":"FORK_ACTIVE","last_completed_step":"FORK_CONFIRMED"}'
    transition SCENARIO_B_FORK_CONFIRMED "$dir/fork.json"
  else
    fault_session_update "$session_id" '{"current_phase":"FORK_ACTIVE","last_completed_step":"FORK_CONFIRMED"}'
    transition FORK_CONFIRMED "$dir/fork.json"
  fi
  printf '%s\n' "$dir/fork.json"
}

assert_orphan_coinbases_removed() {
  local candidates="$1" output="$2" txids
  txids="$(jq -s '[.[].coinbase_txid]' "$candidates")"
  compose exec -T node-a python3 - "$txids" <<'PY' >"$output"
import json,sys
from pathlib import Path
from chipcoin.node.service import NodeService
txids=set(json.loads(sys.argv[1]))
s=NodeService.open_sqlite(Path('/runtime/mainnet/node.sqlite3'),network='mainnet')
present=sorted({o.txid for o,e in s.chainstate.list_utxos() if o.txid in txids})
print(json.dumps({'orphan_coinbase_txids':sorted(txids),'utxo_txids_still_present':present,'pass':not present},sort_keys=True))
PY
  jq -e '.pass==true' "$output" >/dev/null
}

assert_transaction_utxos() {
  local absent_txid="$1" present_txid="$2" output="$3"
  compose exec -T node-a python3 - "$absent_txid" "$present_txid" <<'PY' >"$output"
import json,sys
from pathlib import Path
from chipcoin.node.service import NodeService
s=NodeService.open_sqlite(Path('/runtime/mainnet/node.sqlite3'),network='mainnet')
rows=[{'txid':o.txid,'vout':o.index,'value':int(e.output.value),'recipient':e.output.recipient} for o,e in s.chainstate.list_utxos() if o.txid in {sys.argv[1],sys.argv[2]}]
print(json.dumps({'absent_txid':sys.argv[1],'present_txid':sys.argv[2],'rows':rows},sort_keys=True))
PY
  jq -e --arg absent "$absent_txid" --arg present "$present_txid" 'all(.rows[];.txid!=$absent) and any(.rows[];.txid==$present)' "$output" >/dev/null
}

wait_b_winning() {
  local deadline=$((SECONDS+3600)) a b dir="$EVIDENCE/winning-$(timestamp)"; mkdir -p "$dir"
  while (( SECONDS < deadline )); do
    a="$(state_json node-a)"; b="$(state_json node-b)"
    if (( $(jq -r .cumulative_work <<<"$b") > $(jq -r .cumulative_work <<<"$a") )); then
      jq -n --argjson a "$a" --argjson b "$b" '{branch_a:$a,branch_b:$b,branch_b_winning:true}' >"$dir/work.json"
      if [[ "$(phase)" == "SCENARIO_B_TX_B2_CONFIRMED" ]]; then
        transition SCENARIO_B_B_WINNING "$dir/work.json"
      elif [[ "$(phase)" == "FORK_CONFIRMED" ]]; then
        transition WINNING_BRANCH_CONFIRMED "$dir/work.json"
      else
        transition SCENARIO_A_B_WINNING "$dir/work.json"
        transition WINNING_BRANCH_CONFIRMED "$dir/work.json"
      fi
      printf '%s\n' "$dir/work.json"; return
    fi
    sleep 10
  done
  return 1
}

checkpoint_reward_reorg_winner() {
  [[ "$(phase)" == "WINNING_BRANCH_CONFIRMED" ]] || {
    echo "reward-reorg-checkpoint requires WINNING_BRANCH_CONFIRMED" >&2
    return 2
  }
  local dir="$EVIDENCE/reward-reorg-winner-$(timestamp)"
  mkdir -p "$dir"
  [[ "$(miner_control status miner-a)" == stopped ]]
  [[ "$(miner_control status miner-b)" == stopped ]]
  capture_states "$dir/branch-states.json" node-a node-b node-c
  jq -e '
    (map(select(.node=="node-b" or .node=="node-c") |
      del(.node,.handshaken_peer_count,.mempool_size,.sync_phase,.sqlite)) | unique | length)==1 and
    ((map(select(.node=="node-b"))[0].cumulative_work) > (map(select(.node=="node-a"))[0].cumulative_work))
  ' "$dir/branch-states.json" >/dev/null
  capture_peer_topology "$dir/peers.json"
  jq -n --arg status PASS --arg captured_at "$(date -Is)" \
    --arg states "$dir/branch-states.json" --arg peers "$dir/peers.json" \
    '{status:$status,captured_at:$captured_at,canonical_candidate:"branch_b",states:$states,peers:$peers,miners_stopped:true}' \
    >"$dir/manifest.json"
  cp "$dir/branch-states.json" "$SESSION_DIR/reward-reorg-winning-branches.json"
  printf '%s\n' "$dir"
}

verify_reward_reorg() {
  [[ "$(phase)" == "RECONNECTING" ]] || {
    echo "reward-reorg-verify requires RECONNECTING" >&2
    return 2
  }
  local dir="$EVIDENCE/reward-reorg-verified-$(timestamp)" fork_file
  mkdir -p "$dir"
  [[ -f "$SESSION_DIR/reward-reorg-baseline.json" ]]
  [[ -f "$SESSION_DIR/reward-reorg-winning-branches.json" ]]
  wait_for_shared_peer_recovery 180
  wait_equal 1800 node-a node-b node-c
  capture_states "$dir/converged.json" node-a node-b node-c
  assert_equal "$dir/converged.json"
  jq -e --slurpfile winner "$SESSION_DIR/reward-reorg-winning-branches.json" '
    ($winner[0] | map(select(.node=="node-b"))[0]) as $b |
    all(.[];
      .height==$b.height and .tip_hash==$b.tip_hash and .cumulative_work==$b.cumulative_work and
      .supply==$b.supply and .utxo_count==$b.utxo_count and .utxo_hash==$b.utxo_hash and
      .balances_hash==$b.balances_hash and
      .reward_registry_count==$b.reward_registry_count and .reward_registry_hash==$b.reward_registry_hash and
      .reward_attestation_bundle_count==$b.reward_attestation_bundle_count and .reward_attestation_hash==$b.reward_attestation_hash and
      .reward_settlement_count==$b.reward_settlement_count and .reward_settlement_hash==$b.reward_settlement_hash and
      .reward_distributed_chipbits==$b.reward_distributed_chipbits)
  ' "$dir/converged.json" >/dev/null
  jq -e --slurpfile before "$SESSION_DIR/reward-reorg-baseline.json" '
    ($before[0][0]) as $base |
    all(.[];
      .reward_registry_count >= $base.reward_registry_count and
      .reward_settlement_count >= $base.reward_settlement_count and
      .reward_distributed_chipbits >= $base.reward_distributed_chipbits)
  ' "$dir/converged.json" >/dev/null
  fork_file="$(find "$EVIDENCE" -maxdepth 2 -path '*/fork.json' -type f | sort | tail -1)"
  [[ -n "$fork_file" ]]
  assert_orphan_coinbases_removed "$(dirname "$fork_file")/orphan-candidates-a.jsonl" "$dir/orphan-coinbases.json"
  jq -n --arg status PASS --arg verified_at "$(date -Is)" \
    --arg states "$dir/converged.json" --arg winner "$SESSION_DIR/reward-reorg-winning-branches.json" \
    '{status:$status,verified_at:$verified_at,canonical_branch:"branch_b",states:$states,winner_checkpoint:$winner,reward_state_matches_winning_branch:true,orphan_coinbases_removed:true}' \
    >"$dir/manifest.json"
  fault_session_update "$(fault_session_id)" '{"current_phase":"REORG_VALIDATING","last_completed_step":"REWARD_REORG_VALIDATED"}'
  transition REORG_COMPLETE "$dir/manifest.json"
  printf '%s\n' "$dir"
}

wait_branch_block() {
  local node="$1" start_height="$2" timeout="${3:-3600}" deadline state
  deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    state="$(state_json "$node")"
    if (( $(jq -r .height <<<"$state") > start_height )); then printf '%s\n' "$state"; return; fi
    sleep 10
  done
  return 1
}

tx_location() { compose exec -T "$1" chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 tx "$2" 2>/dev/null || true; }
mempool_has() { compose exec -T "$1" chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 mempool | jq -e --arg txid "$2" 'any(.[];.txid==$txid)' >/dev/null; }

confirm_scenario_a_tx() {
  [[ "$(phase)" == "FORK_CONFIRMED" ]] || return 2
  local txid dir="$EVIDENCE/scenario-a-tx-$(timestamp)"; mkdir -p "$dir"
  txid="$(jq -r .txid "$SESSION_DIR/transactions/tx-a/manifest.json")"
  wait_tx_location node-a "$txid" chain >"$dir/node-a.json"
  for node in node-b node-c; do
    ! mempool_has "$node" "$txid" || { echo "TX-A leaked to $node mempool" >&2; return 1; }
    ! jq -e '.location=="chain"' <<<"$(tx_location "$node" "$txid")" >/dev/null 2>&1 || { echo "TX-A leaked to $node chain" >&2; return 1; }
  done
  transition ORPHAN_TX_CONFIRMED "$dir/node-a.json"
  transition SCENARIO_A_TX_CONFIRMED "$dir/node-a.json"
}

prepare_scenario_b() {
  local current dir="$EVIDENCE/scenario-b-prepared-$(timestamp)"
  current="$(phase)"
  [[ "$current" == "BASELINE" || "$current" == "SCENARIO_A_COMPLETE" || "$current" == "FINAL_CONVERGENCE" ]] || {
    echo "scenario-b-prepare requires a clean BASELINE, SCENARIO_A_COMPLETE, or FINAL_CONVERGENCE" >&2
    return 2
  }
  mkdir -p "$dir"
  scenario_b_clean_state_precheck "$dir"
  prepare_transactions >/dev/null
  scenario_b_validate_transactions "$dir"
  transition SCENARIO_B_PREPARED "$dir/manifest.json"
  printf '%s\n' "$dir/manifest.json"
}

scenario_b_clean_state_precheck() {
  local dir="$1" service network
  [[ ! -e "$FAULT_LOCK" ]] || { echo "fault lock exists" >&2; return 1; }
  fault_monitor_clean_assert || { echo "residual fault monitor exists" >&2; return 1; }
  docker network inspect "$SHARED_NETWORK" >/dev/null 2>&1 || { echo "shared network missing" >&2; return 1; }
  for service in node-a node-b node-c miner-a miner-b; do
    service_running "$service" || { echo "service is not running: $service" >&2; return 1; }
    service_on_network "$service" "$SHARED_NETWORK" || { echo "service is not on shared network: $service" >&2; return 1; }
    for network in "$NETWORK_A" "$NETWORK_B"; do
      ! service_on_network "$service" "$network" || { echo "service has residual fault-network attachment: $service $network" >&2; return 1; }
    done
  done
  capture_states "$dir/states.json" node-a node-b node-c || { echo "failed to capture node states" >&2; return 1; }
  assert_equal "$dir/states.json" || { echo "A/B/C are not convergent or SQLite integrity failed" >&2; return 1; }
  jq -e 'all(.[]; (.mempool_size | type)=="number")' "$dir/states.json" >/dev/null || {
    echo "mempool state is unknown" >&2
    return 1
  }
  capture_peer_topology "$dir/peers.json" || { echo "failed to capture peer topology" >&2; return 1; }
  miner_assert_operational miner-a "$SHARED_NETWORK" || { echo "miner-a is not operational on shared topology" >&2; return 1; }
  miner_assert_operational miner-b "$SHARED_NETWORK" || { echo "miner-b is not operational on shared topology" >&2; return 1; }
  systemctl --user is-active --quiet chipcoin-mainnet-rehearsal-monitor.service || {
    echo "ordinary rehearsal monitor is not active" >&2
    return 1
  }
}

scenario_b_validate_transactions() {
  local dir="$1" txdir="$SESSION_DIR/transactions" a b source_address diagnostics
  scenario_b_transactions_unsubmitted || { echo "Scenario B transaction missing or already submitted" >&2; return 1; }
  a="$txdir/tx-a2/manifest.json"; b="$txdir/tx-b2/manifest.json"
  jq -e '
    .address_kind=="pq" and .signature_scheme_id==10 and .signature_scheme_name=="mldsa44" and
    (.txid|type)=="string" and (.source.txid|type)=="string" and (.source.vout|type)=="number" and
    (.inputs|length)==1 and .inputs[0].scheme_id==10 and (.outputs|length)>=1
  ' "$a" "$b" >/dev/null
  [[ "$(jq -r '.source.txid+":"+(.source.vout|tostring)' "$a")" == "$(jq -r '.source.txid+":"+(.source.vout|tostring)' "$b")" ]] || {
    echo "Scenario B transactions do not spend the same outpoint" >&2; return 1;
  }
  [[ "$(jq -r .txid "$a")" != "$(jq -r .txid "$b")" ]] || { echo "Scenario B TXIDs are identical" >&2; return 1; }
  [[ "$(jq -c .outputs "$a")" != "$(jq -c .outputs "$b")" ]] || { echo "Scenario B outputs are identical" >&2; return 1; }
  for label in tx-a2 tx-b2; do
    printf '%s  %s\n' "$(sha256sum "$txdir/$label/transaction.raw.hex" | cut -d' ' -f1)" "$label"
    [[ "$(sha256sum "$txdir/$label/transaction.raw.hex" | cut -d' ' -f1)" == "$(jq -r .raw_sha256 "$txdir/$label/manifest.json")" ]] || {
      echo "raw transaction hash mismatch: $label" >&2; return 1;
    }
  done >"$dir/raw-checksums.sha256"
  source_address="$(jq -r .source.address "$a")"
  diagnostics="$(compose exec -T node-a python3 - "$source_address" <<'PY'
import json,sys
from pathlib import Path
from chipcoin.node.service import NodeService
s=NodeService.open_sqlite(Path('/runtime/mainnet/node.sqlite3'),network='mainnet')
print(json.dumps(s.utxo_diagnostics(sys.argv[1]),sort_keys=True))
PY
)"
  printf '%s\n' "$diagnostics" >"$dir/source-utxos.json"
  jq -e --arg txid "$(jq -r .source.txid "$a")" --argjson vout "$(jq -r .source.vout "$a")" \
    'any(.[]; .txid==$txid and .vout==$vout and .status=="unspent" and .mature==true)' \
    "$dir/source-utxos.json" >/dev/null || { echo "selected Scenario B UTXO is not canonical, mature, and unspent" >&2; return 1; }
  jq -n --arg status PASS --arg prepared_at "$(date -Is)" --arg states "$dir/states.json" \
    --arg tx_a2 "$(jq -r .txid "$a")" --arg tx_b2 "$(jq -r .txid "$b")" \
    --arg source "$(jq -r '.source.txid+":"+(.source.vout|tostring)' "$a")" \
    '{status:$status,prepared_at:$prepared_at,states:$states,tx_a2:$tx_a2,tx_b2:$tx_b2,source_outpoint:$source,submitted:false}' >"$dir/manifest.json"
}

cancel_scenario_b_preparation() {
  [[ "$(phase)" == "SCENARIO_B_PREPARED" ]] || { echo "scenario-b-cancel-prepare requires SCENARIO_B_PREPARED" >&2; return 2; }
  local dir="$EVIDENCE/scenario-b-prepare-cancelled-$(timestamp)"
  mkdir -p "$dir"
  scenario_b_clean_state_precheck "$dir"
  jq -n --arg status PASS --arg cancelled_at "$(date -Is)" \
    '{status:$status,cancelled_at:$cancelled_at,fault_session_started:false}' >"$dir/manifest.json"
  transition BASELINE "$dir/manifest.json"
  printf '%s\n' "$dir/manifest.json"
}

network_is_internal() {
  [[ "$(docker network inspect -f '{{.Internal}}' "$1" 2>/dev/null)" == "true" ]]
}

scenario_b_transactions_unsubmitted() {
  local label
  for label in tx-a2 tx-b2; do
    [[ -f "$SESSION_DIR/transactions/$label/manifest.json" ]] || return 1
    [[ -f "$SESSION_DIR/transactions/$label/transaction.raw.hex" ]] || return 1
    [[ ! -e "$SESSION_DIR/transactions/$label/submit.json" ]] || return 1
  done
}

scenario_b_precheck() {
  local dir="$1" current service
  current="$(phase)"
  [[ "$current" == "FINAL_CONVERGENCE" || "$current" == "SCENARIO_B_PREPARED" ]] || {
    echo "scenario-b-activate requires FINAL_CONVERGENCE or SCENARIO_B_PREPARED" >&2
    return 2
  }
  [[ ! -e "$FAULT_LOCK" ]] || { echo "fault lock already exists" >&2; return 1; }
  docker network inspect "$SHARED_NETWORK" >/dev/null 2>&1 || { echo "shared network missing" >&2; return 1; }
  for service in node-a node-b node-c miner-a miner-b; do
    service_running "$service" || { echo "service is not running: $service" >&2; return 1; }
    service_on_network "$service" "$SHARED_NETWORK" || { echo "service is not on shared network: $service" >&2; return 1; }
  done
  capture_states "$dir/states.json" node-a node-b node-c
  assert_equal "$dir/states.json"
  assert_sqlite_ok "$dir/states.json"
  capture_peer_topology "$dir/peers.json"
  miner_assert_operational miner-a "$SHARED_NETWORK"
  miner_assert_operational miner-b "$SHARED_NETWORK"
  scenario_b_transactions_unsubmitted || { echo "Scenario B transaction missing or already submitted" >&2; return 1; }
  systemctl --user is-active --quiet chipcoin-mainnet-rehearsal-monitor.service || {
    echo "ordinary rehearsal monitor is not active" >&2
    return 1
  }
  # A pre-existing healthy fault monitor is safe to adopt during handoff. It
  # still runs global checks until the lock is acquired.
  jq -n --arg status PASS --arg phase "$current" '{status:$status,phase:$phase}' >"$dir/precheck.json"
}

scenario_b_create_networks() {
  local dir="$1" network session_id="$(fault_session_id)"
  for network in "$NETWORK_A" "$NETWORK_B"; do
    network_create "$network"
    network_is_internal "$network" || { echo "fault network is not internal: $network" >&2; return 1; }
  done
  docker network inspect "$NETWORK_A" "$NETWORK_B" >"$dir/networks-created.json"
  fault_session_update "$session_id" '{"topology_state":"FAULT_NETWORKS_CREATED","last_completed_step":"FAULT_NETWORKS_CREATED"}'
}

scenario_b_attach_branches() {
  local session_id="$(fault_session_id)"
  network_connect "$NETWORK_A" node-a node-a
  network_connect "$NETWORK_A" miner-a miner-a
  network_connect "$NETWORK_B" node-b node-b
  network_connect "$NETWORK_B" node-c node-c
  network_connect "$NETWORK_B" miner-b miner-b
  fault_session_update "$session_id" '{"topology_state":"DUAL_ATTACHED","last_completed_step":"FAULT_BRANCHES_ATTACHED"}'
}

scenario_b_verify_pre_cutover() {
  local service session_id="$(fault_session_id)"
  for service in node-a miner-a; do
    service_on_network "$service" "$NETWORK_A"
    ! service_on_network "$service" "$NETWORK_B"
    service_on_network "$service" "$SHARED_NETWORK"
  done
  for service in node-b node-c miner-b; do
    service_on_network "$service" "$NETWORK_B"
    ! service_on_network "$service" "$NETWORK_A"
    service_on_network "$service" "$SHARED_NETWORK"
  done
  miner_assert_operational miner-a "$NETWORK_A"
  miner_assert_operational miner-b "$NETWORK_B"
  fault_session_update "$session_id" '{"last_completed_step":"PRE_CUTOVER_VERIFIED"}'
}

ordinary_monitor_is_fault_aware() {
  [[ -e "$FAULT_LOCK" ]] || return 1
  REHEARSAL_ROOT="$ROOT" scripts/mainnet-rehearsal.sh check 2>&1 |
    grep -Fq 'EXPECTED_DIVERGENCE fault-session lock active; global invariant shutdown suppressed'
}

scenario_b_monitor_handoff() {
  local session_id="$(fault_session_id)"
  fault_monitor_start
  fault_monitor_healthy "$session_id"
  ordinary_monitor_is_fault_aware
}

scenario_b_disconnect_shared() {
  local dir="$1" service index=0 id session_id="$(fault_session_id)"
  fault_session_update "$session_id" '{"current_phase":"CUTOVER","topology_state":"CUTOVER_IN_PROGRESS","last_completed_step":"CUTOVER_STARTED"}'
  for service in node-a node-b node-c miner-a miner-b; do
    id="$(container_any "$service")"
    docker network disconnect "$SHARED_NETWORK" "$id"
    index=$((index + 1))
    docker inspect "$id" >"$dir/cutover-$index-$service.json"
    fault_session_update "$session_id" "{\"topology_state\":\"CUTOVER_IN_PROGRESS\",\"last_completed_step\":\"SHARED_DISCONNECTED_$service\"}"
  done
}

container_tcp_check() {
  local source="$1" target="$2" port="$3"
  compose exec -T "$source" python3 - "$target" "$port" <<'PY' >/dev/null
import socket, sys
with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=3):
    pass
PY
}

container_tcp_rejected() {
  ! container_tcp_check "$1" "$2" "$3" >/dev/null 2>&1
}

scenario_b_verify_partition() {
  local dir="$1" service session_id="$(fault_session_id)"
  for service in node-a miner-a; do
    service_on_network "$service" "$NETWORK_A"
    ! service_on_network "$service" "$NETWORK_B"
    ! service_on_network "$service" "$SHARED_NETWORK"
  done
  for service in node-b node-c miner-b; do
    service_on_network "$service" "$NETWORK_B"
    ! service_on_network "$service" "$NETWORK_A"
    ! service_on_network "$service" "$SHARED_NETWORK"
  done
  container_tcp_check miner-a node-a 8080
  container_tcp_check node-b node-c 8333
  container_tcp_check miner-b node-b 8080
  container_tcp_rejected node-a node-b 8333
  container_tcp_rejected node-a node-c 8333
  container_tcp_rejected node-b node-a 8333
  container_tcp_rejected node-c node-a 8333
  miner_assert_operational miner-a "$NETWORK_A"
  miner_assert_operational miner-b "$NETWORK_B"
  capture_peer_topology "$dir/partition-peers.json"
  jq -n '{status:"PASS",branch_a:["node-a","miner-a"],branch_b:["node-b","node-c","miner-b"],cross_branch_p2p:false}' >"$dir/partition-verified.json"
  fault_session_update "$session_id" '{"current_phase":"PARTITION_ACTIVE","topology_state":"PARTITION_ACTIVE","last_completed_step":"PARTITION_VERIFIED"}'
}

scenario_b_activation_completion_barrier() {
  local dir="$1" session_id="$2" expected_lifecycle_phase="${3:-SCENARIO_B_PARTITION_ACTIVE}"
  local persisted_phase persisted_topology persisted_step lifecycle_phase
  # No activation-owned background job may survive the completion barrier.
  wait
  fault_session_immutable_assert "$session_id"
  fault_monitor_healthy "$session_id"
  jq -e '.status=="PASS" and .cross_branch_p2p==false' "$dir/partition-verified.json" >/dev/null
  persisted_phase="$(jq -er .current_phase "$FAULT_LOCK")"
  persisted_topology="$(jq -er .topology_state "$FAULT_LOCK")"
  persisted_step="$(jq -er .last_completed_step "$FAULT_LOCK")"
  lifecycle_phase="$(phase)"
  [[ "$persisted_phase" == "PARTITION_ACTIVE" ]]
  [[ "$persisted_topology" == "PARTITION_ACTIVE" ]]
  [[ "$persisted_step" == "PARTITION_VERIFIED" ]]
  [[ "$lifecycle_phase" == "$expected_lifecycle_phase" ]]
  jq -n --arg status PASS --arg session_id "$session_id" --arg completed_at "$(date -Is)" \
    --arg current_phase "$persisted_phase" --arg topology_state "$persisted_topology" \
    --arg lifecycle_phase "$lifecycle_phase" \
    '{status:$status,session_id:$session_id,completed_at:$completed_at,current_phase:$current_phase,topology_state:$topology_state,lifecycle_phase:$lifecycle_phase,no_post_return_activation_transition:true}' \
    >"$dir/activation-complete.json"
  sync -f "$dir/activation-complete.json" "$FAULT_LOCK" "$STATE_FILE"
  # Reread after sync: EXIT 0 is forbidden unless persisted state still agrees.
  [[ "$(jq -er .current_phase "$FAULT_LOCK")" == "PARTITION_ACTIVE" ]]
  [[ "$(jq -er .topology_state "$FAULT_LOCK")" == "PARTITION_ACTIVE" ]]
  [[ "$(phase)" == "$expected_lifecycle_phase" ]]
}

prepare_reward_reorg() {
  local current dir="$EVIDENCE/reward-reorg-prepared-$(timestamp)"
  current="$(phase)"
  [[ "$current" == "FINAL_CONVERGENCE" ]] || {
    echo "reward-reorg-prepare requires FINAL_CONVERGENCE" >&2
    return 2
  }
  mkdir -p "$dir"
  scenario_b_clean_state_precheck "$dir"
  cp "$dir/states.json" "$SESSION_DIR/reward-reorg-baseline.json"
  wallet_manifest "$dir/wallet-checksums.sha256"
  jq -n --arg status PASS --arg prepared_at "$(date -Is)" \
    --arg states "$dir/states.json" --arg peers "$dir/peers.json" \
    '{status:$status,prepared_at:$prepared_at,mode:"reward_reorg",transactions_submitted:false,states:$states,peers:$peers}' \
    >"$dir/manifest.json"
  transition PARTITION_PREPARED "$dir/manifest.json"
  printf '%s\n' "$dir"
}

activate_reward_reorg() {
  local current dir="$EVIDENCE/reward-reorg-activation-$(timestamp)"
  current="$(phase)"
  if [[ "$current" == "PARTITION_ACTIVE" ]]; then
    mkdir -p "$dir-idempotent"
    [[ -e "$FAULT_LOCK" ]] && scenario_b_verify_partition "$dir-idempotent"
    echo "PARTITION_ACTIVE"
    return
  fi
  [[ "$current" == "PARTITION_PREPARED" ]] || {
    echo "reward-reorg-activate requires PARTITION_PREPARED" >&2
    return 2
  }
  mkdir -p "$dir"
  if [[ -e "$FAULT_LOCK" ]]; then
    echo "stale fault-session lock; run recover before activation" >&2
    return 2
  fi
  if ! scenario_b_clean_state_precheck "$dir"; then
    echo "reward reorg precheck failed; networking unchanged" >&2
    return 1
  fi
  write_lock
  if ! scenario_b_create_networks "$dir" ||
     ! scenario_b_attach_branches ||
     ! scenario_b_verify_pre_cutover ||
     ! scenario_b_monitor_handoff ||
     ! scenario_b_disconnect_shared "$dir" ||
     ! scenario_b_verify_partition "$dir" ||
     ! transition PARTITION_ACTIVE "$dir/partition-verified.json" ||
     ! scenario_b_activation_completion_barrier "$dir" "$(fault_session_id)" PARTITION_ACTIVE; then
    jq -n --arg failed_at "$(date -Is)" '{status:"FAIL",failed_at:$failed_at}' >"$dir/failure.json"
    scenario_b_activation_rollback "$dir" || true
    echo "reward reorg activation failed and rollback was attempted: $dir" >&2
    return 1
  fi
  capture_logs reward-reorg-partition-active
  echo "$dir"
}

scenario_b_activation_rollback() {
  local dir="$1" service network recovery_ok=true session_id
  session_id="$(fault_session_id)"
  fault_session_begin_recovery "$session_id" || true
  fault_monitor_stop || recovery_ok=false
  miner_control stop miner-a >/dev/null 2>&1 || true
  miner_control stop miner-b >/dev/null 2>&1 || true
  for service in node-a node-b node-c; do network_connect "$SHARED_NETWORK" "$service" "$service" || recovery_ok=false; done
  for service in miner-a miner-b; do network_connect "$SHARED_NETWORK" "$service" "$service" || recovery_ok=false; done
  for service in node-a node-b node-c miner-a miner-b; do
    for network in "$NETWORK_A" "$NETWORK_B"; do
      docker network disconnect "$network" "$(container_any "$service")" >/dev/null 2>&1 || true
    done
  done
  docker network rm "$NETWORK_A" "$NETWORK_B" >/dev/null 2>&1 || true
  wait_equal 1800 node-a node-b node-c || recovery_ok=false
  if [[ "$recovery_ok" == true ]]; then
    fault_session_update "$session_id" '{"current_phase":"FINAL_CONVERGENCE","recovery_state":"COMPLETE","topology_state":"SHARED","last_completed_step":"FINAL_CONVERGENCE_VERIFIED"}'
    transition FINAL_CONVERGENCE "$dir/rollback.json"
    miner_control start miner-a >/dev/null || recovery_ok=false
    miner_control start miner-b >/dev/null || recovery_ok=false
  fi
  jq -n --argjson pass "$recovery_ok" '{rollback_complete:$pass}' >"$dir/rollback.json"
  if [[ "$recovery_ok" != true ]]; then
    fault_session_update "$session_id" '{"current_phase":"RECOVERY_REQUIRED","recovery_state":"REQUIRED","last_completed_step":"RECOVERY_INCOMPLETE"}' || true
    transition RECOVERY_REQUIRED "$dir/rollback.json" || true
    return 1
  fi
  release_lock
}

activate_scenario_b() {
  local current dir="$EVIDENCE/scenario-b-activation-$(timestamp)"
  current="$(phase)"
  if [[ "$current" == "SCENARIO_B_PARTITION_ACTIVE" ]]; then
    mkdir -p "$dir-idempotent"
    [[ -e "$FAULT_LOCK" ]] && scenario_b_verify_partition "$dir-idempotent"
    echo "SCENARIO_B_PARTITION_ACTIVE"
    return
  fi
  mkdir -p "$dir"
  if [[ -e "$FAULT_LOCK" ]]; then
    jq -n '{status:"RECOVERY_REQUIRED",reason:"stale fault-session lock before Scenario B activation"}' >"$dir/recovery-required.json"
    transition RECOVERY_REQUIRED "$dir/recovery-required.json"
    echo "stale fault-session lock; run recover before activation" >&2
    return 2
  fi
  if ! scenario_b_precheck "$dir"; then
    echo "Scenario B precheck failed; networking unchanged" >&2
    return 1
  fi
  write_lock
  if ! scenario_b_create_networks "$dir" ||
     ! scenario_b_attach_branches ||
     ! scenario_b_verify_pre_cutover ||
     ! scenario_b_monitor_handoff ||
     ! scenario_b_disconnect_shared "$dir" ||
     ! scenario_b_verify_partition "$dir" ||
     ! transition SCENARIO_B_PARTITION_ACTIVE "$dir/partition-verified.json" ||
     ! scenario_b_activation_completion_barrier "$dir" "$(fault_session_id)"; then
    jq -n --arg failed_at "$(date -Is)" '{status:"FAIL",failed_at:$failed_at}' >"$dir/failure.json"
    scenario_b_activation_rollback "$dir" || true
    echo "Scenario B activation failed and rollback was attempted: $dir" >&2
    return 1
  fi
  capture_logs scenario-b-partition-active
  echo "$dir"
}

confirm_scenario_b_tx() {
  local side="$1" label node txid dir
  dir="$EVIDENCE/scenario-b-$side-$(timestamp)"; mkdir -p "$dir"
  if [[ "$side" == a ]]; then
    [[ "$(phase)" == "SCENARIO_B_FORK_CONFIRMED" ]] || return 2; label=tx-a2; node=node-a
  else
    [[ "$(phase)" == "SCENARIO_B_TX_A2_CONFIRMED" ]] || return 2; label=tx-b2; node=node-b
  fi
  txid="$(jq -r .txid "$SESSION_DIR/transactions/$label/manifest.json")"
  wait_tx_location "$node" "$txid" chain >"$dir/confirmed.json"
  if [[ "$side" == a ]]; then
    ! jq -e '.location=="chain"' <<<"$(tx_location node-b "$txid")" >/dev/null 2>&1
    ! jq -e '.location=="chain"' <<<"$(tx_location node-c "$txid")" >/dev/null 2>&1
    transition SCENARIO_B_TX_A2_CONFIRMED "$dir/confirmed.json"
  else
    ! jq -e '.location=="chain"' <<<"$(tx_location node-a "$txid")" >/dev/null 2>&1
    transition SCENARIO_B_TX_B2_CONFIRMED "$dir/confirmed.json"
  fi
}

verify_scenario_a_reorg() {
  [[ "$(phase)" == "RECONNECTING" ]] || return 2
  local txid fork_file manifest="$SESSION_DIR/transactions/tx-a/manifest.json" dir="$EVIDENCE/scenario-a-reorg-$(timestamp)"
  mkdir -p "$dir"; txid="$(jq -r .txid "$manifest")"
  wait_equal 1800 node-a node-b node-c
  capture_states "$dir/converged.json" node-a node-b node-c; assert_equal "$dir/converged.json"
  fork_file="$(find "$EVIDENCE" -maxdepth 2 -path '*/fork.json' -type f | sort | tail -1)"
  assert_orphan_coinbases_removed "$(dirname "$fork_file")/orphan-candidates-a.jsonl" "$dir/orphan-coinbases.json"
  transition REORG_COMPLETE "$dir/converged.json"
  for node in node-a node-b node-c; do
    ! jq -e '.location=="chain"' <<<"$(tx_location "$node" "$txid")" >/dev/null 2>&1 || return 1
  done
  found=0; for _ in $(seq 1 60); do mempool_has node-a "$txid" && { found=1; break; }; sleep 1; done
  (( found == 1 )) || { echo "TX-A did not reenter mempool" >&2; return 1; }
  jq -n --arg txid "$txid" '{status:"ORPHAN_TX_REENTERED_MEMPOOL",txid:$txid}' >"$dir/assertion.json"
  transition ORPHAN_TX_REENTERED_MEMPOOL "$dir/assertion.json"
}

reconfirm_scenario_a() {
  [[ "$(phase)" == "ORPHAN_TX_REENTERED_MEMPOOL" ]] || return 2
  local txid dir="$EVIDENCE/scenario-a-reconfirmed-$(timestamp)"; mkdir -p "$dir"
  txid="$(jq -r .txid "$SESSION_DIR/transactions/tx-a/manifest.json")"
  miner_control start miner-b
  wait_tx_location node-a "$txid" chain 3600 >"$dir/confirmed.json"
  miner_control stop miner-b
  for node in node-a node-b node-c; do jq -e '.location=="chain"' <<<"$(tx_location "$node" "$txid")" >/dev/null; done
  ! mempool_has node-a "$txid"; ! mempool_has node-b "$txid"; ! mempool_has node-c "$txid"
  jq -n --arg txid "$txid" '{status:"PASS",txid:$txid,canonical_confirmation_count:1}' >"$dir/assertion.json"
  transition SCENARIO_A_COMPLETE "$dir/assertion.json"
  miner_control start miner-a; miner_control start miner-b
}

verify_scenario_b_reorg() {
  [[ "$(phase)" == "SCENARIO_B_RECONNECTING" || "$(phase)" == "RECONNECTING" ]] || return 2
  local a b input_a input_b fork_file dir="$EVIDENCE/scenario-b-reorg-$(timestamp)"; mkdir -p "$dir"
  a="$(jq -r .txid "$SESSION_DIR/transactions/tx-a2/manifest.json")"; b="$(jq -r .txid "$SESSION_DIR/transactions/tx-b2/manifest.json")"
  input_a="$(jq -r '.source.txid+":"+(.source.vout|tostring)' "$SESSION_DIR/transactions/tx-a2/manifest.json")"
  input_b="$(jq -r '.source.txid+":"+(.source.vout|tostring)' "$SESSION_DIR/transactions/tx-b2/manifest.json")"
  [[ "$input_a" == "$input_b" ]] || return 1
  wait_equal 1800 node-a node-b node-c
  capture_states "$dir/converged.json" node-a node-b node-c; assert_equal "$dir/converged.json"
  fork_file="$(find "$EVIDENCE" -maxdepth 2 -path '*/fork.json' -type f | sort | tail -1)"
  assert_orphan_coinbases_removed "$(dirname "$fork_file")/orphan-candidates-a.jsonl" "$dir/orphan-coinbases.json"
  transition REORG_COMPLETE "$dir/converged.json"
  for node in node-a node-b node-c; do
    jq -e '.location=="chain"' <<<"$(tx_location "$node" "$b")" >/dev/null
    ! jq -e '.location=="chain"' <<<"$(tx_location "$node" "$a")" >/dev/null 2>&1
    ! mempool_has "$node" "$a"
  done
  assert_transaction_utxos "$a" "$b" "$dir/transaction-utxos.json"
  jq -n --arg orphan "$a" --arg canonical "$b" --arg outpoint "$input_a" '{status:"CONFLICTING_ORPHAN_TX_REJECTED",orphan_txid:$orphan,canonical_txid:$canonical,shared_outpoint:$outpoint}' >"$dir/assertion.json"
  transition CONFLICTING_ORPHAN_TX_REJECTED "$dir/assertion.json"
}

fault_monitor_start() {
  [[ -e "$FAULT_LOCK" ]] || return 2
  local session_id unit started_at expected_phase
  local -a run_env
  session_id="$(fault_session_id)"
  expected_phase="$(phase)"
  fault_session_update "$session_id" '{"current_phase":"MONITOR_STARTING","last_completed_step":"MONITOR_START_REQUESTED"}'
  fault_monitor_pre_start_cleanup "$session_id"
  if [[ -f "$FAULT_MONITOR_META" ]] && fault_monitor_healthy "$session_id"; then return 0; fi
  unit="$(fault_monitor_unit_for_session "$session_id")"
  started_at="$(date -Is)"
  fault_session_update "$session_id" "{\"monitor_unit\":\"$unit\",\"monitor_session_id\":\"$session_id\",\"last_completed_step\":\"MONITOR_UNIT_ASSIGNED\"}"
  rm -f "$FAULT_MONITOR_HEALTH"
  jq -n --arg session_id "$session_id" --arg unit_name "$unit" --arg started_at "$started_at" \
    --arg expected_phase "$expected_phase" \
    '{session_id:$session_id,unit_name:$unit_name,started_at:$started_at,expected_phase:$expected_phase,status:"STARTING"}' \
    >"$FAULT_MONITOR_META"
  run_env=(--setenv=REHEARSAL_ROOT="$ROOT" --setenv=FAULT_SESSION_ID="$session_id")
  [[ -z "${FAULT_MONITOR_SELF_TEST:-}" ]] || run_env+=(--setenv=FAULT_MONITOR_SELF_TEST="$FAULT_MONITOR_SELF_TEST")
  if ! systemd_run_user --unit="$unit" --property=WorkingDirectory="$PWD" \
    "${run_env[@]}" \
    /bin/bash "$PWD/scripts/mainnet-fault-injection.sh" monitor-loop "$session_id" >/dev/null; then
    fault_monitor_cleanup_unit "$unit" || true
    return 1
  fi
  if ! fault_monitor_wait_healthy "$session_id" 45; then
    fault_monitor_cleanup_unit "$unit" || true
    return 1
  fi
  jq --arg status ACTIVE --argjson main_pid "$(fault_monitor_property "$unit" MainPID)" \
    '.status=$status | .main_pid=$main_pid' "$FAULT_MONITOR_META" >"$FAULT_MONITOR_META.tmp"
  mv "$FAULT_MONITOR_META.tmp" "$FAULT_MONITOR_META"
  fault_session_update "$session_id" "{\"current_phase\":\"MONITOR_HEALTHY\",\"monitor_main_pid\":$(fault_monitor_property "$unit" MainPID),\"last_completed_step\":\"FAULT_MONITOR_HEALTHY\"}"
  echo "FAULT_MONITOR_HEALTHY session=$session_id unit=$unit"
}

fault_monitor_stop() {
  local current_session="" owner_session unit archive
  [[ -e "$FAULT_LOCK" ]] && current_session="$(fault_session_id)"
  fault_monitor_cleanup_unit "$LEGACY_FAULT_MONITOR_UNIT" || return 1
  if [[ ! -f "$FAULT_MONITOR_META" ]]; then
    rm -f "$FAULT_MONITOR_HEALTH"
    echo "FAULT_MONITOR_CLEAN"
    return 0
  fi
  owner_session="$(jq -er '.session_id' "$FAULT_MONITOR_META")"
  unit="$(jq -er '.unit_name' "$FAULT_MONITOR_META")"
  [[ -z "$current_session" || "$owner_session" == "$current_session" ]] || {
    echo "refusing to stop fault monitor owned by session $owner_session" >&2
    return 1
  }
  archive="$EVIDENCE/fault-monitor-$owner_session-$(timestamp).json"
  jq --arg stopped_at "$(date -Is)" --arg load_state "$(fault_monitor_property "$unit" LoadState)" \
    --arg active_state "$(fault_monitor_property "$unit" ActiveState)" \
    --arg sub_state "$(fault_monitor_property "$unit" SubState)" \
    --arg result "$(fault_monitor_property "$unit" Result)" \
    '. + {stopped_at:$stopped_at,last_load_state:$load_state,last_active_state:$active_state,last_sub_state:$sub_state,last_result:$result}' \
    "$FAULT_MONITOR_META" >"$archive"
  fault_monitor_cleanup_unit "$unit" || return 1
  rm -f "$FAULT_MONITOR_META" "$FAULT_MONITOR_HEALTH"
  fault_monitor_clean_assert
  if [[ -e "$FAULT_LOCK" ]]; then
    fault_session_update "$owner_session" '{"monitor_unit":null,"monitor_main_pid":null,"monitor_session_id":null,"last_completed_step":"FAULT_MONITOR_CLEAN"}'
  fi
  echo "FAULT_MONITOR_CLEAN session=$owner_session"
}

public_addresses() {
  local path name address
  for path in "$ROOT"/secrets/*.json; do
    [[ -f "$path" ]] || continue
    name="$(basename "$path" .json)"
    address="$(jq -r '.address // empty' "$path")"
    [[ -n "$address" ]] && printf '%s=%s\n' "$name" "$address"
  done
}

state_json() {
  local service="$1" args=() item
  while IFS= read -r item; do args+=(--address "$item"); done < <(public_addresses)
  compose exec -T "$service" python3 /app/scripts/mainnet-rehearsal-state.py \
    --data /runtime/mainnet/node.sqlite3 "${args[@]}"
}

capture_states() {
  local output="$1"; shift
  mkdir -p "$(dirname "$output")"
  for node in "$@"; do
    state_json "$node" | jq --arg node "$node" '. + {node:$node}'
  done | jq -s 'sort_by(.node)' >"$output"
}

capture_logs() {
  local label="$1"
  mkdir -p "$EVIDENCE/logs"
  compose logs --no-color node-a node-b node-c miner-a miner-b \
    >"$EVIDENCE/logs/${label}-$(timestamp).log" 2>&1 || true
}

assert_sqlite_ok() {
  local file="$1"
  jq -e 'all(.[]; .sqlite.quick_check == ["ok"] and .sqlite.foreign_key_check == [])' "$file" >/dev/null
}

assert_equal() {
  local file="$1"
  jq -e '([.[] | del(.node,.handshaken_peer_count,.mempool_size,.sync_phase,.sqlite)] | unique | length) == 1' "$file" >/dev/null &&
    assert_sqlite_ok "$file"
}

wallet_manifest() {
  local output="$1"
  for path in "$ROOT"/secrets/*.json; do
    [[ -f "$path" ]] || continue
    printf '%s  %s\n' "$(sha256sum "$path" | cut -d' ' -f1)" "$(basename "$path")"
  done | sort >"$output"
}

baseline() {
  local dir="$EVIDENCE/baseline-$(timestamp)"
  mkdir -p "$dir"
  capture_states "$dir/states.json" node-a node-b node-c
  assert_equal "$dir/states.json"
  wallet_manifest "$dir/wallet-checksums.sha256"
  compose ps --format json >"$dir/containers.json"
  docker network inspect "$SHARED_NETWORK" >"$dir/network.json"
  capture_logs baseline
  jq -n --arg created_at "$(date -Is)" --arg states "$dir/states.json" \
    --arg wallets "$dir/wallet-checksums.sha256" --arg network "$SHARED_NETWORK" \
    '{created_at:$created_at,states:$states,wallet_checksums:$wallets,network:$network}' >"$dir/manifest.json"
  # A baseline is an evidence checkpoint. It initializes an empty lifecycle,
  # but must not overwrite an existing lifecycle phase.
  if [[ "$(phase)" == "NONE" ]]; then
    transition BASELINE "$dir/manifest.json"
  fi
  printf '%s\n' "$dir"
}

wait_equal() {
  local timeout="$1"; shift
  local deadline=$((SECONDS + timeout)) temp="$ROOT/fault/current-states.json"
  while (( SECONDS < deadline )); do
    if capture_states "$temp" "$@" 2>/dev/null && assert_equal "$temp"; then return 0; fi
    sleep 5
  done
  return 1
}

restart_test() {
  [[ "$(phase)" == "BASELINE" || "$(phase)" == "RESTART_TEST" ]] || { echo "restart-test requires BASELINE" >&2; exit 2; }
  local dir="$EVIDENCE/restart-$(timestamp)" before_height started
  mkdir -p "$dir"
  capture_states "$dir/before.json" node-a node-b node-c
  assert_equal "$dir/before.json"
  wallet_manifest "$dir/wallet-checksums-before.sha256"
  before_height="$(jq -r '.[0].height' "$dir/before.json")"
  started="$(date +%s)"
  compose stop node-c >"$dir/stop.log" 2>&1
  compose ps --format json >"$dir/stopped-containers.json"
  compose up -d --no-deps node-c >"$dir/start.log" 2>&1
  if ! wait_equal 900 node-a node-b node-c; then
    capture_states "$dir/failed.json" node-a node-b node-c || true
    capture_logs restart-failed
    echo "node-c failed to converge" >&2
    exit 1
  fi
  capture_states "$dir/after.json" node-a node-b node-c
  assert_equal "$dir/after.json"
  wallet_manifest "$dir/wallet-checksums-after.sha256"
  cmp "$dir/wallet-checksums-before.sha256" "$dir/wallet-checksums-after.sha256"
  capture_logs restart-pass
  jq -n --argjson before_height "$before_height" --argjson after_height "$(jq -r '.[0].height' "$dir/after.json")" \
    --argjson duration_seconds "$(( $(date +%s) - started ))" \
    '{status:"PASS",node:"node-c",before_height:$before_height,after_height:$after_height,duration_seconds:$duration_seconds}' \
    >"$dir/report.json"
  transition RESTART_TEST "$dir/report.json"
  printf '%s\n' "$dir/report.json"
}

fullsync_test() {
  [[ "$(phase)" == "RESTART_TEST" || "$(phase)" == "FULLSYNC_TEST" ]] || { echo "fullsync-test requires RESTART_TEST" >&2; exit 2; }
  local runtime="$ROOT/runtime/node-fullsync" dir="$EVIDENCE/fullsync-$(timestamp)" started initial=-1 current=-1
  mkdir -p "$dir"
  if find "$runtime" -mindepth 1 -print -quit | grep -q .; then
    echo "node-fullsync runtime is not empty" >&2
    exit 1
  fi
  started="$(date +%s)"
  compose --profile recovery up -d --no-deps node-fullsync >"$dir/start.log" 2>&1
  while (( $(date +%s) - started < 1800 )); do
    if value="$(state_json node-fullsync 2>/dev/null)"; then
      current="$(jq -r '.height' <<<"$value")"
      (( initial < 0 )) && initial="$current"
      jq -nc --arg at "$(date -Is)" --argjson state "$value" '{at:$at,state:$state}' >>"$dir/progress.jsonl"
      if capture_states "$dir/current.json" node-a node-b node-c node-fullsync 2>/dev/null && assert_equal "$dir/current.json"; then
        break
      fi
    fi
    sleep 5
  done
  capture_states "$dir/final.json" node-a node-b node-c node-fullsync
  if ! assert_equal "$dir/final.json"; then
    capture_logs fullsync-failed
    exit 1
  fi
  compose logs --no-color node-fullsync >"$dir/node-fullsync.log" 2>&1 || true
  local retry_count error_count final_height duration_seconds
  retry_count="$(grep -Eic 'retry|reconnect' "$dir/node-fullsync.log" || true)"
  error_count="$(grep -Eic 'error|traceback|fatal|corrupt' "$dir/node-fullsync.log" || true)"
  final_height="$(jq -r '.[0].height' "$dir/final.json")"
  duration_seconds="$(( $(date +%s) - started ))"
  compose stop node-fullsync >"$dir/stop.log" 2>&1
  capture_logs fullsync-pass
  jq -n --arg initial_state "$([[ "$initial" == "null" || "$initial" == "-1" ]] && echo empty_chain || echo chain_present)" \
    --argjson initial_height "$([[ "$initial" == "-1" ]] && echo null || echo "$initial")" \
    --argjson final_height "$final_height" --argjson duration_seconds "$duration_seconds" \
    --argjson average_blocks_per_second "$(awk -v h="$final_height" -v s="$duration_seconds" 'BEGIN {printf "%.4f", (s > 0 ? h / s : 0)}')" \
    --argjson retry_log_matches "$retry_count" --argjson error_log_matches "$error_count" \
    '{status:"PASS",mode:"p2p_full_sync_from_genesis",initial_state:$initial_state,initial_height:$initial_height,final_height:$final_height,duration_seconds:$duration_seconds,average_blocks_per_second:$average_blocks_per_second,retry_log_matches:$retry_log_matches,error_log_matches:$error_log_matches}' \
    >"$dir/report.json"
  transition FULLSYNC_TEST "$dir/report.json"
  printf '%s\n' "$dir/report.json"
}

network_create() {
  docker network inspect "$1" >/dev/null 2>&1 || docker network create --internal "$1" >/dev/null
}

network_connect() {
  local network="$1" service="$2" alias="$3" id
  id="$(container_any "$service")"
  [[ -n "$id" ]] || { echo "container not found: $service" >&2; return 1; }
  docker network inspect "$network" --format '{{json .Containers}}' | jq -e --arg id "$id" 'has($id)' >/dev/null 2>&1 \
    || docker network connect --alias "$alias" "$network" "$id"
}

partition_prepare() {
  [[ "$(phase)" == "FULLSYNC_TEST" || "$(phase)" == "PARTITION_PREPARED" ]] || { echo "partition-prepare requires FULLSYNC_TEST" >&2; exit 2; }
  network_create "$NETWORK_A"; network_create "$NETWORK_B"
  network_connect "$NETWORK_A" node-a node-a
  network_connect "$NETWORK_A" miner-a miner-a
  network_connect "$NETWORK_B" node-b node-b
  network_connect "$NETWORK_B" node-c node-c
  network_connect "$NETWORK_B" miner-b miner-b
  transition PARTITION_PREPARED "$EVIDENCE/network-prepared-$(timestamp)"
}

partition_activate() {
  [[ "$(phase)" == "PARTITION_PREPARED" ]] || { echo "partition-activate requires PARTITION_PREPARED" >&2; exit 2; }
  write_lock
  transition PARTITION_ACTIVE "$EVIDENCE/partition-intent-$(timestamp)"
  fault_monitor_start
  for service in node-a node-b node-c miner-a miner-b; do
    docker network disconnect "$SHARED_NETWORK" "$(container "$service")"
  done
  capture_peer_topology "$EVIDENCE/partition-active-$(timestamp).json"
}

reconnect() {
  local service current="$(phase)" session_id="$(fault_session_id)"
  miner_control stop miner-a
  miner_control stop miner-b
  fault_session_update "$session_id" '{"current_phase":"RECONNECTING","topology_state":"RECONNECTING","last_completed_step":"RECONNECT_STARTED"}'
  if [[ "$current" == "SCENARIO_B_B_WINNING" ]]; then
    transition SCENARIO_B_RECONNECTING "$EVIDENCE/reconnect-intent-$(timestamp)"
  else
    transition RECONNECTING "$EVIDENCE/reconnect-intent-$(timestamp)"
  fi
  normalize_shared_topology
  capture_peer_topology "$EVIDENCE/reconnected-$(timestamp).json"
}

monitor_once() {
  local current output="$ROOT/fault/monitor-current.json"
  current="$(phase)"
  for service in node-a node-b node-c; do
    [[ "$(docker inspect -f '{{.State.Running}}' "$(container "$service")")" == "true" ]] || { echo "CONSENSUS_FAILURE process_down=$service"; return 1; }
  done
  case "$current" in
    PARTITION_ACTIVE|FORK_CONFIRMED|SCENARIO_B_PARTITION_ACTIVE|SCENARIO_B_FORK_CONFIRMED|SCENARIO_B_TX_A2_CONFIRMED)
      for service in miner-a miner-b; do
        service_running "$service" || { echo "CONSENSUS_FAILURE unexpected_miner_down=$service phase=$current"; return 1; }
      done
      ;;
  esac
  capture_states "$output" node-a node-b node-c
  assert_sqlite_ok "$output" || { echo "CONSENSUS_FAILURE sqlite_check"; return 1; }
  if [[ -e "$FAULT_LOCK" ]]; then
    jq -e '([.[] | select(.node == "node-b" or .node == "node-c") | del(.node,.handshaken_peer_count,.mempool_size,.sync_phase,.sqlite)] | unique | length) == 1' "$output" >/dev/null \
      || { echo "CONSENSUS_FAILURE branch_b_divergence"; return 1; }
    echo "EXPECTED_DIVERGENCE phase=$current"
  else
    assert_equal "$output" || { echo "CONSENSUS_FAILURE unexpected_global_divergence phase=$current"; return 1; }
    echo "PASS phase=$current"
  fi
}

wait_for_shared_peer_recovery() {
  local timeout="${1:-120}" deadline output="$ROOT/fault/shared-peer-recovery.json"
  local node status healthy
  deadline=$((SECONDS + timeout))
  mkdir -p "$ROOT/fault"
  while (( SECONDS < deadline )); do
    healthy=true
    : >"$output.tmp"
    for node in node-a node-b node-c; do
      status="$(compose exec -T "$node" chipcoin --network mainnet --data /runtime/mainnet/node.sqlite3 status)"
      jq --arg node "$node" '{node:$node,handshaken_peer_count,reconnect_tasks:(.runtime.reconnect_tasks // null),height,tip_hash,cumulative_work}' <<<"$status" >>"$output.tmp"
      (( $(jq -r '.handshaken_peer_count // 0' <<<"$status") > 0 )) || healthy=false
    done
    jq -s . "$output.tmp" >"$output"
    rm -f "$output.tmp"
    [[ "$healthy" == true ]] && return 0
    sleep 5
  done
  echo "shared network restored but one or more nodes have zero handshaken peers; controlled restart may be required" >&2
  return 1
}

fault_status() {
  local service
  python3 scripts/mainnet-fault-state.py --state-file "$STATE_FILE" show |
    jq --argjson lock "$([[ -e "$FAULT_LOCK" ]] && echo true || echo false)" '. + {fault_lock:$lock}'
  for service in node-a node-b node-c miner-a miner-b; do
    printf '%s=%s\n' "$service" "$(service_running "$service" && echo running || echo stopped)"
  done
  for network in "$SHARED_NETWORK" "$NETWORK_A" "$NETWORK_B"; do
    docker network inspect "$network" --format '{{.Name}} {{range .Containers}}{{.Name}} {{end}}' 2>/dev/null || true
  done
  for label in tx-a tx-a2 tx-b2; do
    if [[ -f "$SESSION_DIR/transactions/$label/manifest.json" ]]; then
      jq -c --arg label "$label" --argjson submitted "$([[ -f "$SESSION_DIR/transactions/$label/submit.json" ]] && echo true || echo false)" \
        '{label:$label,txid,source,destination,submitted:$submitted}' "$SESSION_DIR/transactions/$label/manifest.json"
    fi
  done
}

resume_session() {
  local current="$(phase)"
  fault_status
  case "$current" in
    PARTITION_PREPARED|FINAL_CONVERGENCE) echo "RESUME_SAFE phase=$current" ;;
    PARTITION_ACTIVE|FORK_CONFIRMED|ORPHAN_TX_CONFIRMED|SCENARIO_A_TX_CONFIRMED|SCENARIO_A_B_WINNING|WINNING_BRANCH_CONFIRMED|SCENARIO_B_PARTITION_ACTIVE|SCENARIO_B_TX_A2_CONFIRMED|SCENARIO_B_TX_B2_CONFIRMED|SCENARIO_B_B_WINNING)
      [[ -e "$FAULT_LOCK" ]] || { echo "AMBIGUOUS fault phase without lock" >&2; return 1; }
      echo "RESUME_REQUIRES_EXPLICIT_NEXT_STEP phase=$current"
      ;;
    RECONNECTING|SCENARIO_B_RECONNECTING|REORG_COMPLETE) echo "RESUME_RECOVERY_RECOMMENDED phase=$current" ;;
    *) echo "RESUME_UNSUPPORTED phase=$current" >&2; return 2 ;;
  esac
}

recover_session() {
  local service current="$(phase)" dir="$EVIDENCE/recovery-$(timestamp)" session_id
  mkdir -p "$dir"
  if [[ ! -e "$FAULT_LOCK" ]]; then
    [[ "$current" == "FINAL_CONVERGENCE" ]] || { echo "no active fault session to recover" >&2; return 2; }
    echo "NO_ACTIVE_FAULT_SESSION phase=$current"
    return 0
  fi
  session_id="$(fault_session_id)"
  python3 scripts/mainnet-fault-session.py --lock-file "$FAULT_LOCK" assert-id --session-id "$session_id" >/dev/null
  fault_session_begin_recovery "$session_id"
  if ! fault_monitor_stop; then
    miner_control stop miner-a || true; miner_control stop miner-b || true
    fault_session_update "$session_id" '{"current_phase":"RECOVERY_REQUIRED","recovery_state":"REQUIRED","last_completed_step":"FAULT_MONITOR_STOP_FAILED"}' || true
    return 1
  fi
  miner_control stop miner-a; miner_control stop miner-b
  capture_logs recovery-start
  if [[ "$current" == "FINAL_CONVERGENCE" ]]; then
    normalize_shared_topology
    wait_equal 1800 node-a node-b node-c
    capture_states "$dir/converged.json" node-a node-b node-c; assert_equal "$dir/converged.json"
    fault_session_update "$session_id" '{"current_phase":"FINAL_CONVERGENCE","recovery_state":"COMPLETE","topology_state":"SHARED","last_completed_step":"FINAL_CONVERGENCE_VERIFIED"}'
    release_lock
    miner_control start miner-a; miner_control start miner-b
    capture_logs recovery-complete
    echo "$dir/converged.json"
    return
  fi
  case "$current" in RECONNECTING|SCENARIO_B_RECONNECTING) ;; *) transition RECONNECTING "$dir/recovery-intent.json" ;; esac
  normalize_shared_topology
  if ! wait_for_shared_peer_recovery 120; then
    capture_peer_topology "$dir/no-peer-recovery.json" || true
    transition RECOVERY_REQUIRED "$dir/no-peer-recovery.json"
    return 1
  fi
  wait_equal 1800 node-a node-b node-c || { capture_states "$dir/divergent.json" node-a node-b node-c || true; return 1; }
  capture_states "$dir/converged.json" node-a node-b node-c; assert_equal "$dir/converged.json"
  transition REORG_COMPLETE "$dir/converged.json"
  transition FINAL_CONVERGENCE "$dir/converged.json"
  fault_session_update "$session_id" '{"current_phase":"FINAL_CONVERGENCE","recovery_state":"COMPLETE","topology_state":"SHARED","last_completed_step":"FINAL_CONVERGENCE_VERIFIED"}'
  release_lock
  miner_control start miner-a; miner_control start miner-b
  capture_logs recovery-complete
  echo "$dir/converged.json"
}

finalize_convergence() {
  [[ "$(phase)" == "REORG_COMPLETE" || "$(phase)" == "CONFLICTING_ORPHAN_TX_REJECTED" || "$(phase)" == "ORPHAN_TX_REENTERED_MEMPOOL" ]] || return 2
  local dir="$EVIDENCE/final-$(timestamp)" session_id="$(fault_session_id)"; mkdir -p "$dir"
  wait_equal 1800 node-a node-b node-c
  capture_states "$dir/states.json" node-a node-b node-c; assert_equal "$dir/states.json"
  transition FINAL_CONVERGENCE "$dir/states.json"
  fault_monitor_stop
  fault_session_update "$session_id" '{"current_phase":"FINAL_CONVERGENCE","recovery_state":"COMPLETE","topology_state":"SHARED","last_completed_step":"FINAL_CONVERGENCE_VERIFIED"}'
  release_lock
  miner_control start miner-a; miner_control start miner-b
  printf '%s\n' "$dir/states.json"
}

monitor_loop() {
  local session_id="${1:-${FAULT_SESSION_ID:-}}" iteration=0 current_session
  [[ -n "$session_id" ]] || { echo "fault monitor session id is required" >&2; return 2; }
  mkdir -p "$ROOT/fault"
  while :; do
    [[ -e "$FAULT_LOCK" ]] || { echo "fault monitor lock disappeared" >&2; return 1; }
    current_session="$(fault_session_id)"
    [[ "$current_session" == "$session_id" ]] || {
      echo "fault monitor session mismatch: expected=$session_id actual=$current_session" >&2
      return 1
    }
    if [[ "${FAULT_MONITOR_SELF_TEST:-}" != 1 ]] && ! monitor_once >>"$ROOT/fault/fault-monitor.log" 2>&1; then return 1; fi
    iteration=$((iteration + 1))
    jq -n --arg session_id "$session_id" --arg checked_at "$(date -Is)" --arg phase "$(phase)" \
      --argjson iteration "$iteration" --argjson monitor_pid "$$" \
      '{status:"PASS",session_id:$session_id,checked_at:$checked_at,phase:$phase,iteration:$iteration,monitor_pid:$monitor_pid}' \
      >"$FAULT_MONITOR_HEALTH.tmp"
    mv "$FAULT_MONITOR_HEALTH.tmp" "$FAULT_MONITOR_HEALTH"
    sleep "${FAULT_MONITOR_INTERVAL_SECONDS:-30}"
  done
}

crash_test() {
  [[ "${CONFIRM_SIGKILL_TEST:-}" == "YES" ]] || { echo "NOT_RUN: set CONFIRM_SIGKILL_TEST=YES for the separately scheduled crash test"; exit 2; }
  echo "crash test execution is intentionally reserved for a separate approved run" >&2
  exit 2
}

network_self_test() {
  local suffix="$$" net_a="chipcoin-fault-selftest-a-$$" net_b="chipcoin-fault-selftest-b-$$"
  local a1="chipcoin-fault-a1-$$" a2="chipcoin-fault-a2-$$" b1="chipcoin-fault-b1-$$"
  cleanup_self_test() {
    docker rm -f "${a1:-}" "${a2:-}" "${b1:-}" >/dev/null 2>&1 || true
    docker network rm "${net_a:-}" "${net_b:-}" >/dev/null 2>&1 || true
  }
  trap cleanup_self_test EXIT
  docker network create --internal "$net_a" >/dev/null
  docker network create --internal "$net_b" >/dev/null
  docker run -d --name "$a1" --network "$net_a" --network-alias peer-a1 alpine:3.20 sleep 60 >/dev/null
  docker run -d --name "$a2" --network "$net_a" --network-alias peer-a2 alpine:3.20 sleep 60 >/dev/null
  docker run -d --name "$b1" --network "$net_b" --network-alias peer-b1 alpine:3.20 sleep 60 >/dev/null
  docker exec "$a1" ping -c 1 -W 1 peer-a2 >/dev/null
  docker stop "$a2" >/dev/null
  [[ "$(docker inspect -f '{{.State.Running}}' "$a2")" == "false" ]]
  docker start "$a2" >/dev/null
  [[ "$(docker inspect -f '{{.State.Running}}' "$a2")" == "true" ]]
  docker exec "$a1" ping -c 1 -W 1 peer-a2 >/dev/null
  if docker exec "$a1" ping -c 1 -W 1 peer-b1 >/dev/null 2>&1; then
    echo "network self-test unexpectedly crossed isolated branches" >&2
    return 1
  fi
  cleanup_self_test
  trap - EXIT
  echo "PASS deterministic isolated network orchestration suffix=$suffix"
}

scenario_b_activation_self_test() {
  local suffix="$$" shared="chipcoin-sb-selftest-shared-$$" net_a="chipcoin-sb-selftest-a-$$" net_b="chipcoin-sb-selftest-b-$$"
  local node_a="chipcoin-sb-node-a-$$" miner_a="chipcoin-sb-miner-a-$$"
  local node_b="chipcoin-sb-node-b-$$" node_c="chipcoin-sb-node-c-$$" miner_b="chipcoin-sb-miner-b-$$"
  local service cycle session_id created_a=0 created_b=0
  cleanup_scenario_b_self_test() {
    fault_monitor_stop >/dev/null 2>&1 || true
    docker rm -f "$node_a" "$miner_a" "$node_b" "$node_c" "$miner_b" >/dev/null 2>&1 || true
    docker network rm "$shared" "$net_a" "$net_b" >/dev/null 2>&1 || true
  }
  trap cleanup_scenario_b_self_test EXIT
  rm -rf "$ROOT/fault" "$ROOT/activation-atomicity-complete.json"
  docker network create --internal "$shared" >/dev/null
  for service in "$node_a" "$miner_a" "$node_b" "$node_c" "$miner_b"; do
    docker run -d --name "$service" --network "$shared" alpine:3.20 sleep 600 >/dev/null
  done
  mkdir -p "$ROOT/fault/evidence" "$ROOT/fault/session"
  for cycle in $(seq 1 10); do
    net_a="chipcoin-sb-selftest-a-$cycle-$$"; net_b="chipcoin-sb-selftest-b-$cycle-$$"
    docker network create --internal "$net_a" >/dev/null; created_a=$((created_a + 1))
    docker network create --internal "$net_b" >/dev/null; created_b=$((created_b + 1))
    if [[ "$cycle" == 1 ]]; then transition BASELINE "selftest-$cycle"; else transition SCENARIO_B_PREPARED "selftest-$cycle"; fi
    [[ "$cycle" == 1 ]] && transition SCENARIO_B_PREPARED "selftest-$cycle"
    write_lock; session_id="$(fault_session_id)"
    FAULT_MONITOR_SELF_TEST=1 fault_monitor_start >/dev/null
    fault_monitor_healthy "$session_id"
    docker network connect --alias node-a "$net_a" "$node_a"
    docker network connect --alias miner-a "$net_a" "$miner_a"
    docker network connect --alias node-b "$net_b" "$node_b"
    docker network connect --alias node-c "$net_b" "$node_c"
    docker network connect --alias miner-b "$net_b" "$miner_b"
    docker exec "$miner_a" ping -c 1 -W 1 "$node_a" >/dev/null
    docker exec "$node_b" ping -c 1 -W 1 "$node_c" >/dev/null
    # fault_monitor_start persisted MONITOR_HEALTHY; begin cutover from that state.
    fault_session_update "$session_id" '{"current_phase":"CUTOVER","topology_state":"CUTOVER_IN_PROGRESS","last_completed_step":"CUTOVER_STARTED"}'
    for service in "$node_a" "$miner_a" "$node_b" "$node_c" "$miner_b"; do docker network disconnect "$shared" "$service"; done
    docker exec "$miner_a" ping -c 1 -W 1 node-a >/dev/null
    docker exec "$node_b" ping -c 1 -W 1 node-c >/dev/null
    ! docker exec "$node_a" ping -c 1 -W 1 node-b >/dev/null 2>&1
    ! docker exec "$node_b" ping -c 1 -W 1 node-a >/dev/null 2>&1
    fault_session_update "$session_id" '{"current_phase":"PARTITION_ACTIVE","topology_state":"PARTITION_ACTIVE","last_completed_step":"PARTITION_VERIFIED"}'
    transition SCENARIO_B_PARTITION_ACTIVE "selftest-$cycle"
    [[ "$(jq -r .current_phase "$FAULT_LOCK")" == PARTITION_ACTIVE ]]
    [[ "$(jq -r .topology_state "$FAULT_LOCK")" == PARTITION_ACTIVE ]]
    [[ "$(phase)" == SCENARIO_B_PARTITION_ACTIVE ]]
    for service in "$node_a" "$miner_a" "$node_b" "$node_c" "$miner_b"; do docker network connect "$shared" "$service"; done
    fault_session_begin_recovery "$session_id"
    fault_monitor_stop >/dev/null
    fault_session_update "$session_id" '{"current_phase":"FINAL_CONVERGENCE","recovery_state":"COMPLETE","topology_state":"SHARED","last_completed_step":"FINAL_CONVERGENCE_VERIFIED"}'
    transition RECONNECTING "selftest-$cycle"; transition REORG_COMPLETE "selftest-$cycle"; transition FINAL_CONVERGENCE "selftest-$cycle"
    release_lock
    for service in "$node_a" "$miner_a"; do docker network disconnect "$net_a" "$service"; done
    for service in "$node_b" "$node_c" "$miner_b"; do docker network disconnect "$net_b" "$service"; done
    docker network rm "$net_a" "$net_b" >/dev/null
    fault_monitor_clean_assert; [[ ! -e "$FAULT_LOCK" ]]
  done
  docker exec "$node_a" ping -c 1 -W 1 "$node_b" >/dev/null
  jq -n --arg status PASS --argjson cycles 10 --arg completed_at "$(date -Is)" \
    '{status:$status,cycles:$cycles,completed_at:$completed_at,no_post_return_activation_transition:true}' \
    >"$ROOT/activation-atomicity-complete.json"
  sync -f "$ROOT/activation-atomicity-complete.json"
  cleanup_scenario_b_self_test
  trap - EXIT
  echo "PASS Scenario B activation atomicity cycles=10 suffix=$suffix created_a=$created_a created_b=$created_b"
}

fault_monitor_consecutive_sessions_self_test() {
  local suffix="$$" test_root="/tmp/chipcoin-fault-monitor-selftest-$$"
  local shared="chipcoin-fault-monitor-shared-$$" a="chipcoin-fault-monitor-a-$$"
  local b="chipcoin-fault-monitor-b-$$" c="chipcoin-fault-monitor-c-$$"
  local old_root="$ROOT" old_state="$STATE_FILE" old_evidence="$EVIDENCE" old_lock="$FAULT_LOCK"
  local old_session="$SESSION_DIR" old_meta="$FAULT_MONITOR_META" old_health="$FAULT_MONITOR_HEALTH"
  cleanup_fault_monitor_self_test() {
    fault_monitor_stop >/dev/null 2>&1 || true
    docker rm -f "$a" "$b" "$c" >/dev/null 2>&1 || true
    docker network ls --format '{{.Name}}' | grep -E "^chipcoin-fault-monitor-(shared|[123]-(a|b))-$suffix$" |
      xargs -r docker network rm >/dev/null 2>&1 || true
    rm -rf "$test_root"
  }
  trap cleanup_fault_monitor_self_test EXIT
  ROOT="$test_root"; STATE_FILE="$ROOT/fault/state.json"; EVIDENCE="$ROOT/fault/evidence"
  FAULT_LOCK="$ROOT/fault/session.lock"; SESSION_DIR="$ROOT/fault/session"
  FAULT_MONITOR_META="$ROOT/fault/monitor-session.json"; FAULT_MONITOR_HEALTH="$ROOT/fault/monitor-health.json"
  mkdir -p "$EVIDENCE" "$SESSION_DIR"
  docker network create --internal "$shared" >/dev/null
  docker run -d --name "$a" --network "$shared" alpine:3.20 sleep 300 >/dev/null
  docker run -d --name "$b" --network "$shared" alpine:3.20 sleep 300 >/dev/null
  docker run -d --name "$c" --network "$shared" alpine:3.20 sleep 300 >/dev/null
  for number in 1 2 3; do
    local net_a="chipcoin-fault-monitor-$number-a-$suffix" net_b="chipcoin-fault-monitor-$number-b-$suffix"
    docker network create --internal "$net_a" >/dev/null
    docker network create --internal "$net_b" >/dev/null
    write_lock
    FAULT_MONITOR_SELF_TEST=1 fault_monitor_start >/dev/null
    fault_monitor_healthy "$(fault_session_id)"
    docker network connect "$net_a" "$a"
    docker network connect "$net_b" "$b"
    docker network connect "$net_b" "$c"
    docker network disconnect "$shared" "$a"
    docker network disconnect "$shared" "$b"
    docker network disconnect "$shared" "$c"
    docker network inspect "$net_a" --format '{{json .Containers}}' | jq -e --arg id "$(docker inspect -f '{{.Id}}' "$a")" 'has($id)' >/dev/null
    docker network inspect "$net_b" --format '{{json .Containers}}' | jq -e --arg bid "$(docker inspect -f '{{.Id}}' "$b")" --arg cid "$(docker inspect -f '{{.Id}}' "$c")" 'has($bid) and has($cid)' >/dev/null
    docker network connect "$shared" "$a"
    docker network connect "$shared" "$b"
    docker network connect "$shared" "$c"
    docker network disconnect "$net_a" "$a"
    docker network disconnect "$net_b" "$b"
    docker network disconnect "$net_b" "$c"
    fault_monitor_stop >/dev/null
    release_lock
    fault_monitor_clean_assert
    [[ ! -e "$FAULT_LOCK" ]]
    docker network rm "$net_a" "$net_b" >/dev/null
  done
  ! systemctl_user list-units --all --plain --no-legend 'chipcoin-mainnet-fault-monitor-*.service' |
    grep -Eq 'failed|running'
  [[ -z "$(pgrep -f "$test_root.*monitor-loop" || true)" ]]
  fault_monitor_clean_assert
  for name in "$a" "$b" "$c"; do
    docker inspect -f '{{range $network, $_ := .NetworkSettings.Networks}}{{$network}}{{"\n"}}{{end}}' "$name" | grep -Fxq "$shared"
  done
  printf 'PASS three consecutive fault-monitor sessions\n'
  trap - EXIT
  cleanup_fault_monitor_self_test
  ROOT="$old_root"; STATE_FILE="$old_state"; EVIDENCE="$old_evidence"; FAULT_LOCK="$old_lock"
  SESSION_DIR="$old_session"; FAULT_MONITOR_META="$old_meta"; FAULT_MONITOR_HEALTH="$old_health"
}

fault_session_crash_child() {
  local checkpoint="$1" test_root="$2" shared="$3" net_a="$4" net_b="$5" a="$6" b="$7" c="$8"
  local rank=0 session_id id
  case "$checkpoint" in
    BEFORE_MONITOR_START) rank=1 ;;
    AFTER_MONITOR_START) rank=2 ;;
    AFTER_HEALTH_HANDSHAKE) rank=3 ;;
    DURING_FAULT_NETWORK_ATTACH) rank=4 ;;
    AFTER_ATTACH) rank=5 ;;
    DURING_SHARED_DISCONNECT) rank=6 ;;
    IMMEDIATELY_AFTER_CUTOVER) rank=7 ;;
    BEFORE_FINAL_PARTITION_VERIFICATION) rank=8 ;;
    AFTER_VERIFICATION_BEFORE_PERSIST) rank=9 ;;
    AFTER_PERSIST_BEFORE_REREAD) rank=10 ;;
    AFTER_REREAD_BEFORE_RETURN) rank=11 ;;
    BEFORE_PARTITION_ACTIVE_MARKER) rank=9 ;;
    AFTER_PARTITION_ACTIVE) rank=13 ;;
    DURING_RECONNECT) rank=14 ;;
    DURING_MONITOR_STOP) rank=15 ;;
    DURING_CLEANUP) rank=16 ;;
    DURING_LOCK_RELEASE) rank=17 ;;
    *) return 2 ;;
  esac
  ROOT="$test_root"; STATE_FILE="$ROOT/fault/state.json"; EVIDENCE="$ROOT/fault/evidence"
  FAULT_LOCK="$ROOT/fault/session.lock"; SESSION_DIR="$ROOT/fault/session"
  FAULT_MONITOR_META="$ROOT/fault/monitor-session.json"; FAULT_MONITOR_HEALTH="$ROOT/fault/monitor-health.json"
  mkdir -p "$EVIDENCE" "$SESSION_DIR"
  write_lock; session_id="$(fault_session_id)"
  (( rank == 2 )) && fault_session_update "$session_id" '{"current_phase":"MONITOR_STARTING","last_completed_step":"MONITOR_START_REQUESTED"}'
  (( rank > 2 )) && FAULT_MONITOR_SELF_TEST=1 fault_monitor_start >/dev/null
  (( rank > 3 )) && docker network connect "$net_a" "$a"
  (( rank > 4 )) && { docker network connect "$net_b" "$b"; docker network connect "$net_b" "$c"; fault_session_update "$session_id" '{"topology_state":"DUAL_ATTACHED","last_completed_step":"FAULT_BRANCHES_ATTACHED"}'; }
  if (( rank > 5 )); then
    fault_session_update "$session_id" '{"current_phase":"CUTOVER","topology_state":"CUTOVER_IN_PROGRESS","last_completed_step":"CUTOVER_STARTED"}'
    docker network disconnect "$shared" "$a"
  fi
  if (( rank > 6 )); then
    docker network disconnect "$shared" "$b"; docker network disconnect "$shared" "$c"
    fault_session_update "$session_id" '{"topology_state":"PARTITIONED","last_completed_step":"CUTOVER_COMPLETE"}'
  fi
  (( rank > 9 )) && fault_session_update "$session_id" '{"current_phase":"PARTITION_ACTIVE","topology_state":"PARTITION_ACTIVE","last_completed_step":"PARTITION_VERIFIED"}'
  if (( rank > 13 )); then
    fault_session_update "$session_id" '{"current_phase":"RECONNECTING","topology_state":"RECONNECTING","last_completed_step":"RECONNECT_STARTED"}'
    docker network connect "$shared" "$a" 2>/dev/null || true
    docker network connect "$shared" "$b" 2>/dev/null || true
    docker network connect "$shared" "$c" 2>/dev/null || true
  fi
  (( rank > 14 )) && fault_session_begin_recovery "$session_id"
  (( rank > 15 )) && fault_monitor_stop >/dev/null
  (( rank > 16 )) && fault_session_update "$session_id" '{"current_phase":"FINAL_CONVERGENCE","recovery_state":"COMPLETE","topology_state":"SHARED","last_completed_step":"FINAL_CONVERGENCE_VERIFIED"}'
  jq -n --arg checkpoint "$checkpoint" --arg session_id "$session_id" '{checkpoint:$checkpoint,fault_session_id:$session_id}' >"$ROOT/fault/crash-ready.json"
  sleep 300
}

fault_session_crash_recovery_self_test() {
  local suffix="$$" base="/tmp/chipcoin-fault-crash-selftest-$$"
  local shared="chipcoin-fault-crash-shared-$$" a="chipcoin-fault-crash-a-$$"
  local b="chipcoin-fault-crash-b-$$" c="chipcoin-fault-crash-c-$$" checkpoint root net_a net_b child session_id
  local checkpoints=(BEFORE_MONITOR_START AFTER_MONITOR_START AFTER_HEALTH_HANDSHAKE DURING_FAULT_NETWORK_ATTACH AFTER_ATTACH DURING_SHARED_DISCONNECT IMMEDIATELY_AFTER_CUTOVER BEFORE_FINAL_PARTITION_VERIFICATION AFTER_VERIFICATION_BEFORE_PERSIST AFTER_PERSIST_BEFORE_REREAD AFTER_REREAD_BEFORE_RETURN BEFORE_PARTITION_ACTIVE_MARKER AFTER_PARTITION_ACTIVE DURING_RECONNECT DURING_MONITOR_STOP DURING_CLEANUP DURING_LOCK_RELEASE)
  cleanup_crash_self_test() {
    docker rm -f "$a" "$b" "$c" >/dev/null 2>&1 || true
    docker network ls --format '{{.Name}}' | grep -E "^chipcoin-fault-crash-.*-$suffix$" | xargs -r docker network rm >/dev/null 2>&1 || true
    rm -rf "$base"
  }
  trap cleanup_crash_self_test EXIT
  mkdir -p "$base"
  docker network create --internal "$shared" >/dev/null
  docker run -d --name "$a" --network "$shared" alpine:3.20 sleep 900 >/dev/null
  docker run -d --name "$b" --network "$shared" alpine:3.20 sleep 900 >/dev/null
  docker run -d --name "$c" --network "$shared" alpine:3.20 sleep 900 >/dev/null
  for checkpoint in "${checkpoints[@]}"; do
    root="$base/$checkpoint"; net_a="chipcoin-fault-crash-a-$checkpoint-$suffix"; net_b="chipcoin-fault-crash-b-$checkpoint-$suffix"
    mkdir -p "$root/fault/evidence"; docker network create --internal "$net_a" >/dev/null; docker network create --internal "$net_b" >/dev/null
    /bin/bash "$PWD/scripts/mainnet-fault-injection.sh" fault-session-crash-child "$checkpoint" "$root" "$shared" "$net_a" "$net_b" "$a" "$b" "$c" &
    child=$!
    for _ in $(seq 1 90); do [[ -f "$root/fault/crash-ready.json" ]] && break; sleep 1; done
    [[ -f "$root/fault/crash-ready.json" ]] || { kill -9 "$child" 2>/dev/null || true; return 1; }
    session_id="$(jq -er .fault_session_id "$root/fault/crash-ready.json")"
    kill -9 "$child"; wait "$child" 2>/dev/null || true
    ROOT="$root"; STATE_FILE="$ROOT/fault/state.json"; EVIDENCE="$ROOT/fault/evidence"
    FAULT_LOCK="$ROOT/fault/session.lock"; SESSION_DIR="$ROOT/fault/session"
    FAULT_MONITOR_META="$ROOT/fault/monitor-session.json"; FAULT_MONITOR_HEALTH="$ROOT/fault/monitor-health.json"
    [[ "$(fault_session_id)" == "$session_id" ]]
    fault_session_begin_recovery "$session_id"
    fault_monitor_stop >/dev/null
    docker network connect "$shared" "$a" 2>/dev/null || true
    docker network connect "$shared" "$b" 2>/dev/null || true
    docker network connect "$shared" "$c" 2>/dev/null || true
    docker network disconnect "$net_a" "$a" >/dev/null 2>&1 || true
    docker network disconnect "$net_b" "$b" >/dev/null 2>&1 || true
    docker network disconnect "$net_b" "$c" >/dev/null 2>&1 || true
    fault_session_update "$session_id" '{"current_phase":"FINAL_CONVERGENCE","recovery_state":"COMPLETE","topology_state":"SHARED","last_completed_step":"FINAL_CONVERGENCE_VERIFIED"}'
    release_lock
    [[ ! -e "$FAULT_LOCK" ]]; fault_monitor_clean_assert
    docker network rm "$net_a" "$net_b" >/dev/null
  done
  ! systemctl_user list-units --all --plain --no-legend 'chipcoin-mainnet-fault-monitor-*.service' | grep -Eq 'failed|running'
  [[ -z "$(pgrep -f "$base.*monitor-loop" || true)" ]]
  printf 'PASS orchestrator process-kill recovery checkpoints=%s\n' "${#checkpoints[@]}"
  trap - EXIT; cleanup_crash_self_test
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
case "${1:-}" in
  baseline) baseline ;;
  restart-test) restart_test ;;
  fullsync-test) fullsync_test ;;
  partition-prepare) partition_prepare ;;
  baseline-current) capture_baseline_current ;;
  prepare-transactions) prepare_transactions ;;
  partition-activate) partition_activate ;;
  fork-check) fork_checkpoint ;;
  scenario-a-confirm) confirm_scenario_a_tx ;;
  scenario-a-verify-reorg) verify_scenario_a_reorg ;;
  scenario-a-reconfirm) reconfirm_scenario_a ;;
  scenario-b-prepare) prepare_scenario_b ;;
  scenario-b-cancel-prepare) cancel_scenario_b_preparation ;;
  scenario-b-activate) activate_scenario_b ;;
  scenario-b-confirm) confirm_scenario_b_tx "${2:?a-or-b}" ;;
  scenario-b-verify-reorg) verify_scenario_b_reorg ;;
  reward-reorg-prepare) prepare_reward_reorg ;;
  reward-reorg-activate) activate_reward_reorg ;;
  reward-reorg-checkpoint) checkpoint_reward_reorg_winner ;;
  reward-reorg-verify) verify_reward_reorg ;;
  submit-tx) submit_branch_tx "${2:?node}" "${3:?label}" ;;
  wait-tx) wait_tx_location "${2:?node}" "${3:?txid}" "${4:?location}" "${5:-1800}" ;;
  miner-start) miner_control start "${2:?miner}" ;;
  miner-stop) miner_control stop "${2:?miner}" ;;
  miner-status) miner_control status "${2:?miner}" ;;
  miner-operational) miner_assert_operational "${2:?miner}" "${3:-$(miner_expected_network "${2:?miner}")}" "${4:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}" ;;
  wait-b-winning) wait_b_winning ;;
  wait-branch-block) wait_branch_block "${2:?node}" "${3:?start-height}" "${4:-3600}" ;;
  reconnect) reconnect ;;
  monitor-once) monitor_once ;;
  monitor-loop) monitor_loop ;;
  fault-monitor-start) fault_monitor_start ;;
  fault-monitor-stop) fault_monitor_stop ;;
  phase) phase ;;
  status) fault_status ;;
  resume) resume_session ;;
  recover) recover_session ;;
  finalize) finalize_convergence ;;
  crash-test) crash_test ;;
  network-self-test) network_self_test ;;
  scenario-b-activation-self-test) scenario_b_activation_self_test ;;
  fault-monitor-consecutive-self-test) fault_monitor_consecutive_sessions_self_test ;;
  fault-session-crash-child) shift; fault_session_crash_child "$@" ;;
  fault-session-crash-self-test) fault_session_crash_recovery_self_test ;;
  *) echo "usage: $0 {baseline|restart-test|fullsync-test|partition-prepare|baseline-current|prepare-transactions|partition-activate|fork-check|scenario-a-confirm|scenario-a-verify-reorg|scenario-a-reconfirm|scenario-b-prepare|scenario-b-cancel-prepare|scenario-b-activate|scenario-b-confirm a|b|scenario-b-verify-reorg|reward-reorg-prepare|reward-reorg-activate|reward-reorg-checkpoint|reward-reorg-verify|submit-tx NODE LABEL|wait-tx NODE TXID LOCATION|miner-start MINER|miner-stop MINER|miner-status MINER|miner-operational MINER [NETWORK] [SINCE]|wait-branch-block NODE HEIGHT|wait-b-winning|reconnect|monitor-once|monitor-loop|fault-monitor-start|fault-monitor-stop|phase|status|resume|recover|finalize|crash-test|network-self-test|scenario-b-activation-self-test|fault-monitor-consecutive-self-test|fault-session-crash-self-test}" >&2; exit 2 ;;
esac
fi
