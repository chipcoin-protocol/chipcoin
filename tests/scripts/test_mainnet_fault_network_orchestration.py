from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
HARNESS = ROOT / "scripts/mainnet-fault-injection.sh"


def run_shell(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "{HARNESS}"\n{script}'],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_network_connect_uses_stopped_container_id() -> None:
    result = run_shell(
        r'''
container() { return 0; }
container_any() { echo stopped-container-id; }
docker() {
  if [[ "$1 $2" == "network inspect" ]]; then echo '{}'; return 0; fi
  [[ "$*" == "network connect --alias miner-a expected stopped-container-id" ]]
}
network_connect expected miner-a miner-a
'''
    )
    assert result.returncode == 0, result.stderr


def test_running_miner_on_wrong_fault_network_is_not_operational() -> None:
    result = run_shell(
        r'''
service_running() { return 0; }
service_on_network() { return 1; }
if miner_assert_operational miner-b chipcoin-mainnet-rehearsal_rehearsal now; then
  exit 1
fi
'''
    )
    assert result.returncode == 0, result.stderr


def test_stopped_miner_normalization_is_idempotent() -> None:
    result = run_shell(
        r'''
state=fault
calls=0
service_running() { return 1; }
container_networks() { [[ "$state" == shared ]] && echo "$SHARED_NETWORK" || echo "$NETWORK_B"; }
service_on_network() { container_networks "$1" | grep -Fxq "$2"; }
compose() {
  case "$1" in
    rm) calls=$((calls + 1)) ;;
    create) state=shared ;;
  esac
}
normalize_stopped_miner_network miner-b
normalize_stopped_miner_network miner-b
[[ "$calls" -eq 1 && "$state" == shared ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_reconnect_is_idempotent_with_stopped_miners() -> None:
    result = run_shell(
        r'''
stops=0
normalizations=0
phase() { echo RECONNECTING; }
fault_session_id() { echo fault-fixed; }
fault_session_update() { :; }
miner_control() { [[ "$1" == stop ]] && stops=$((stops + 1)); }
transition() { :; }
normalize_shared_topology() { normalizations=$((normalizations + 1)); }
capture_peer_topology() { :; }
timestamp() { echo fixed; }
reconnect
reconnect
[[ "$stops" -eq 4 && "$normalizations" -eq 2 ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_recover_final_convergence_is_idempotent() -> None:
    result = run_shell(
        r'''
starts=0
normalizations=0
phase() { echo FINAL_CONVERGENCE; }
    miner_control() { if [[ "$1" == start ]]; then starts=$((starts + 1)); fi; return 0; }
capture_logs() { :; }
normalize_shared_topology() { normalizations=$((normalizations + 1)); }
wait_equal() { :; }
capture_states() { printf '[]\n' > "$1"; }
assert_equal() { :; }
fault_monitor_stop() { :; }
release_lock() { :; }
timestamp() { echo fixed; }
    recover_session >/dev/null
    recover_session >/dev/null
    [[ "$starts" -eq 0 && "$normalizations" -eq 0 ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_recovery_uses_existing_immutable_session_identity() -> None:
    result = run_shell(
        r'''
ROOT="$(mktemp -d)"; EVIDENCE="$ROOT/evidence"; FAULT_LOCK="$ROOT/lock"; mkdir -p "$EVIDENCE"
touch "$FAULT_LOCK"
sequence=""
phase() { echo FINAL_CONVERGENCE; }
fault_session_id() { echo original-session; }
fault_session_begin_recovery() { [[ "$1" == original-session ]]; sequence="$sequence recovery-start"; }
fault_monitor_stop() { sequence="$sequence monitor-stop"; }
miner_control() { sequence="$sequence $1-$2"; }
capture_logs() { :; }
normalize_shared_topology() { sequence="$sequence topology"; }
wait_equal() { :; }
capture_states() { printf '[]\n' > "$1"; }
assert_equal() { :; }
fault_session_update() { [[ "$1" == original-session ]]; sequence="$sequence state-final"; }
release_lock() { sequence="$sequence lock-release"; rm -f "$FAULT_LOCK"; }
timestamp() { echo fixed; }
python3() { :; }
write_lock() { echo "identity replacement forbidden" >&2; return 1; }
recover_session >/dev/null
[[ "$sequence" == " recovery-start monitor-stop stop-miner-a stop-miner-b topology state-final lock-release start-miner-a start-miner-b" ]]
[[ ! -e "$FAULT_LOCK" ]]
'''
    )
    assert result.returncode == 0, result.stderr


def activation_fixture(failure: str = "none") -> str:
    return rf'''
tmp="$(mktemp -d)"
ROOT="$tmp"; EVIDENCE="$tmp/evidence"; SESSION_DIR="$tmp/session"
FAULT_LOCK="$tmp/session.lock"; STATE_FILE="$tmp/state.json"
mkdir -p "$EVIDENCE" "$SESSION_DIR/transactions/tx-a2" "$SESSION_DIR/transactions/tx-b2"
touch "$SESSION_DIR/transactions/tx-a2/manifest.json" "$SESSION_DIR/transactions/tx-a2/transaction.raw.hex"
touch "$SESSION_DIR/transactions/tx-b2/manifest.json" "$SESSION_DIR/transactions/tx-b2/transaction.raw.hex"
phase_value=FINAL_CONVERGENCE
created=0; attached=0; monitor_started=0; disconnected=0; rolled_back=0; transitioned=0
phase() {{ echo "$phase_value"; }}
scenario_b_precheck() {{ return 0; }}
scenario_b_create_networks() {{ created=$((created + 1)); [[ "{failure}" != create ]]; }}
scenario_b_attach_branches() {{ attached=$((attached + 1)); [[ "{failure}" != attach ]]; }}
scenario_b_verify_pre_cutover() {{ return 0; }}
scenario_b_monitor_handoff() {{ monitor_started=$((monitor_started + 1)); [[ "{failure}" != monitor ]]; }}
scenario_b_disconnect_shared() {{ disconnected=$((disconnected + 1)); [[ "{failure}" != disconnect ]]; }}
scenario_b_verify_partition() {{ return 0; }}
scenario_b_activation_completion_barrier() {{ [[ "{failure}" != barrier ]]; }}
scenario_b_activation_rollback() {{ rolled_back=$((rolled_back + 1)); phase_value=FINAL_CONVERGENCE; }}
transition() {{ transitioned=$((transitioned + 1)); phase_value="$1"; }}
capture_logs() {{ :; }}
timestamp() {{ echo fixed; }}
'''


def test_scenario_b_activation_builds_topology_before_cutover() -> None:
    result = run_shell(
        activation_fixture()
        + r'''
activate_scenario_b >/dev/null
[[ "$created:$attached:$monitor_started:$disconnected:$transitioned:$phase_value" == "1:1:1:1:1:SCENARIO_B_PARTITION_ACTIVE" ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_reward_reorg_prepare_does_not_prepare_or_submit_transactions() -> None:
    result = run_shell(
        r'''
tmp="$(mktemp -d)"; ROOT="$tmp"; EVIDENCE="$tmp/evidence"; SESSION_DIR="$tmp/session"
mkdir -p "$EVIDENCE" "$SESSION_DIR"
phase() { echo FINAL_CONVERGENCE; }
scenario_b_clean_state_precheck() { printf '[]\n' > "$1/states.json"; printf '[]\n' > "$1/peers.json"; }
wallet_manifest() { : > "$1"; }
prepare_transactions() { echo unexpected >&2; return 1; }
transition() { [[ "$1" == PARTITION_PREPARED ]]; }
timestamp() { echo fixed; }
prepare_reward_reorg >/dev/null
[[ -f "$SESSION_DIR/reward-reorg-baseline.json" ]]
[[ ! -e "$SESSION_DIR/transactions" ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_reward_reorg_activation_uses_atomic_generic_partition_barrier() -> None:
    result = run_shell(
        activation_fixture()
        + r'''
phase_value=PARTITION_PREPARED
scenario_b_clean_state_precheck() { return 0; }
scenario_b_activation_completion_barrier() {
  [[ "$3" == PARTITION_ACTIVE && "$phase_value" == PARTITION_ACTIVE ]]
}
activate_reward_reorg >/dev/null
[[ "$created:$attached:$monitor_started:$disconnected:$transitioned:$phase_value" == "1:1:1:1:1:PARTITION_ACTIVE" ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_scenario_b_activation_is_idempotent_after_success() -> None:
    result = run_shell(
        activation_fixture()
        + r'''
verify_count=0
scenario_b_verify_partition() { verify_count=$((verify_count + 1)); }
activate_scenario_b >/dev/null
touch "$FAULT_LOCK"
activate_scenario_b >/dev/null
[[ "$created:$attached:$monitor_started:$disconnected:$transitioned:$verify_count" == "1:1:1:1:1:2" ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_scenario_b_activation_accepts_existing_or_partial_attachments() -> None:
    result = run_shell(
        activation_fixture()
        + r'''
scenario_b_create_networks() { created=$((created + 1)); return 0; }
scenario_b_attach_branches() { attached=$((attached + 1)); return 0; }
activate_scenario_b >/dev/null
[[ "$created:$attached:$disconnected:$phase_value" == "1:1:1:SCENARIO_B_PARTITION_ACTIVE" ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_scenario_b_activation_accepts_fault_monitor_started_by_handoff() -> None:
    result = run_shell(
        activation_fixture()
        + r'''
scenario_b_monitor_handoff() { monitor_started=$((monitor_started + 1)); return 0; }
activate_scenario_b >/dev/null
[[ "$monitor_started:$disconnected:$phase_value" == "1:1:SCENARIO_B_PARTITION_ACTIVE" ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_scenario_b_activation_resumes_explicit_active_state_without_cutover() -> None:
    result = run_shell(
        activation_fixture()
        + r'''
phase_value=SCENARIO_B_PARTITION_ACTIVE
touch "$FAULT_LOCK"
verified=0
scenario_b_verify_partition() { verified=$((verified + 1)); }
activate_scenario_b >/dev/null
[[ "$created:$attached:$disconnected:$verified" == "0:0:0:1" ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_scenario_b_activation_interrupted_session_requires_recovery() -> None:
    result = run_shell(
        activation_fixture()
        + r'''
touch "$FAULT_LOCK"
if activate_scenario_b >/dev/null 2>&1; then exit 1; fi
[[ "$created:$attached:$disconnected:$phase_value" == "0:0:0:RECOVERY_REQUIRED" ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_scenario_b_activation_failure_injection_rolls_back() -> None:
    for failure in ("create", "attach", "monitor", "disconnect", "barrier"):
        result = run_shell(
            activation_fixture(failure)
            + r'''
if activate_scenario_b >/dev/null 2>&1; then exit 1; fi
[[ "$rolled_back:$phase_value" == "1:FINAL_CONVERGENCE" ]]
'''
        )
        assert result.returncode == 0, f"{failure}: {result.stderr}"


def test_activation_waits_for_delayed_verification_persist_and_reread() -> None:
    result = run_shell(
        activation_fixture()
        + r'''
scenario_b_verify_partition() { sleep 0.1; verified=1; }
scenario_b_activation_completion_barrier() {
  sleep 0.1
  [[ "$verified" == 1 && "$phase_value" == SCENARIO_B_PARTITION_ACTIVE ]]
  barrier_complete=1
}
verified=0; barrier_complete=0
started="$(date +%s%N)"
activate_scenario_b >/dev/null
ended="$(date +%s%N)"
[[ "$barrier_complete" == 1 ]]
[[ "$phase_value" == SCENARIO_B_PARTITION_ACTIVE ]]
(( ended - started >= 180000000 ))
'''
    )
    assert result.returncode == 0, result.stderr


def test_no_post_return_activation_transition() -> None:
    result = run_shell(
        activation_fixture()
        + r'''
scenario_b_activation_completion_barrier() {
  [[ "$phase_value" == SCENARIO_B_PARTITION_ACTIVE ]]
  printf '%s\n' "$phase_value" > "$tmp/phase-at-return"
}
activate_scenario_b >/dev/null
sleep 0.1
[[ "$(cat "$tmp/phase-at-return")" == SCENARIO_B_PARTITION_ACTIVE ]]
[[ "$phase_value" == SCENARIO_B_PARTITION_ACTIVE ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_confirm_scenario_b_tx_initializes_side_before_using_it() -> None:
    result = run_shell(
        r'''
phase() { echo SCENARIO_B_FORK_CONFIRMED; }
timestamp() { echo fixed; }
SESSION_DIR="$(mktemp -d)"; EVIDENCE="$SESSION_DIR/evidence"
mkdir -p "$SESSION_DIR/transactions/tx-a2" "$EVIDENCE"
printf '{"txid":"abc"}\n' > "$SESSION_DIR/transactions/tx-a2/manifest.json"
wait_tx_location() { printf '{"location":"chain"}\n'; }
tx_location() { printf '{}\n'; }
mempool_has() { return 1; }
transition() { [[ "$1" == SCENARIO_B_TX_A2_CONFIRMED ]]; }
confirm_scenario_b_tx a
'''
    )
    assert result.returncode == 0, result.stderr
    assert "unbound variable" not in result.stderr


def test_compose_create_compatibility_does_not_use_no_deps() -> None:
    text = HARNESS.read_text(encoding="utf-8")
    assert 'compose create --no-deps "$miner"' not in text
    assert 'compose create "$miner"' in text


def test_fault_monitor_allows_stopped_miners_during_reconnect() -> None:
    result = run_shell(
        r'''
ROOT="$(mktemp -d)"; mkdir -p "$ROOT/fault"; FAULT_LOCK="$ROOT/lock"; touch "$FAULT_LOCK"
phase() { echo RECONNECTING; }
container() { echo node-id; }
docker() { [[ "$1" == inspect ]] && echo true; }
capture_states() { printf '[{"node":"node-a"},{"node":"node-b"},{"node":"node-c"}]\n' > "$1"; }
assert_sqlite_ok() { :; }
monitor_once
'''
    )
    assert result.returncode == 0, result.stderr
    assert "EXPECTED_DIVERGENCE" in result.stdout


def test_shared_topology_without_handshake_requires_controlled_recovery() -> None:
    result = run_shell(
        r'''
ROOT="$(mktemp -d)"
compose() { printf '{"height":1,"tip_hash":"x","cumulative_work":1,"handshaken_peer_count":0}\n'; }
sleep() { :; }
SECONDS=0
if wait_for_shared_peer_recovery 1; then exit 1; fi
'''
    )
    assert result.returncode == 0, result.stderr
    assert "controlled restart may be required" in result.stderr


def test_fault_monitor_prestart_cleans_failed_previous_unit() -> None:
    result = run_shell(
        r'''
ROOT="$(mktemp -d)"; EVIDENCE="$ROOT/evidence"; mkdir -p "$EVIDENCE"
FAULT_MONITOR_META="$ROOT/meta.json"; FAULT_MONITOR_HEALTH="$ROOT/health.json"
LEGACY_FAULT_MONITOR_UNIT=legacy.service
printf '{"session_id":"old","unit_name":"old.service"}\n' > "$FAULT_MONITOR_META"
cleaned=""
fault_monitor_active() { return 1; }
fault_monitor_cleanup_unit() { cleaned="$cleaned $1"; }
fault_monitor_pre_start_cleanup new
[[ "$cleaned" == " legacy.service old.service" && ! -e "$FAULT_MONITOR_META" ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_fault_monitor_wait_helpers_initialize_timeout_before_deadline() -> None:
    result = run_shell(
        r'''
fault_monitor_property() { echo inactive; }
fault_monitor_wait_inactive test.service 1
fault_monitor_healthy() { return 0; }
fault_monitor_wait_healthy session 1
'''
    )
    assert result.returncode == 0, result.stderr
    assert "unbound variable" not in result.stderr


def test_fault_monitor_prestart_cleans_inactive_loaded_previous_unit() -> None:
    result = run_shell(
        r'''
ROOT="$(mktemp -d)"; EVIDENCE="$ROOT/evidence"; mkdir -p "$EVIDENCE"
FAULT_MONITOR_META="$ROOT/meta.json"; FAULT_MONITOR_HEALTH="$ROOT/health.json"
LEGACY_FAULT_MONITOR_UNIT=legacy.service
printf '{"session_id":"old","unit_name":"inactive-loaded.service"}\n' > "$FAULT_MONITOR_META"
fault_monitor_active() { return 1; }
fault_monitor_cleanup_unit() { [[ "$1" == legacy.service || "$1" == inactive-loaded.service ]]; }
fault_monitor_pre_start_cleanup new
[[ ! -e "$FAULT_MONITOR_META" ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_fault_monitor_accepts_healthy_active_same_session() -> None:
    result = run_shell(
        r'''
ROOT="$(mktemp -d)"; FAULT_MONITOR_META="$ROOT/meta.json"; FAULT_MONITOR_HEALTH="$ROOT/health.json"
LEGACY_FAULT_MONITOR_UNIT=legacy.service
printf '{"session_id":"same","unit_name":"same.service"}\n' > "$FAULT_MONITOR_META"
fault_monitor_cleanup_unit() { :; }
fault_monitor_active() { [[ "$1" == same.service ]]; }
fault_monitor_healthy() { [[ "$1" == same ]]; }
fault_monitor_pre_start_cleanup same
'''
    )
    assert result.returncode == 0, result.stderr


def test_fault_monitor_rejects_active_different_session() -> None:
    result = run_shell(
        r'''
ROOT="$(mktemp -d)"; FAULT_MONITOR_META="$ROOT/meta.json"; FAULT_MONITOR_HEALTH="$ROOT/health.json"
LEGACY_FAULT_MONITOR_UNIT=legacy.service
printf '{"session_id":"foreign","unit_name":"foreign.service"}\n' > "$FAULT_MONITOR_META"
fault_monitor_cleanup_unit() { :; }
fault_monitor_active() { [[ "$1" == foreign.service ]]; }
if fault_monitor_pre_start_cleanup current; then exit 1; fi
'''
    )
    assert result.returncode == 0, result.stderr
    assert "another active session" in result.stderr


def test_fault_monitor_start_fails_if_process_dies_or_health_never_arrives() -> None:
    result = run_shell(
        r'''
ROOT="$(mktemp -d)"; EVIDENCE="$ROOT/evidence"; mkdir -p "$EVIDENCE"
FAULT_LOCK="$ROOT/lock"; FAULT_MONITOR_META="$ROOT/meta.json"; FAULT_MONITOR_HEALTH="$ROOT/health.json"
printf '{"fault_session_id":"current"}\n' > "$FAULT_LOCK"
phase() { echo FINAL_CONVERGENCE; }
fault_monitor_pre_start_cleanup() { :; }
fault_monitor_unit_for_session() { echo current.service; }
systemd_run_user() { return 0; }
fault_monitor_wait_healthy() { return 1; }
cleaned=0
fault_monitor_cleanup_unit() { cleaned=$((cleaned + 1)); }
if fault_monitor_start; then exit 1; fi
[[ "$cleaned" -eq 1 ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_fault_monitor_stop_failure_preserves_ownership_metadata() -> None:
    result = run_shell(
        r'''
ROOT="$(mktemp -d)"; EVIDENCE="$ROOT/evidence"; mkdir -p "$EVIDENCE"
FAULT_LOCK="$ROOT/lock"; FAULT_MONITOR_META="$ROOT/meta.json"; FAULT_MONITOR_HEALTH="$ROOT/health.json"
LEGACY_FAULT_MONITOR_UNIT=legacy.service
printf '{"fault_session_id":"current"}\n' > "$FAULT_LOCK"
printf '{"session_id":"current","unit_name":"current.service"}\n' > "$FAULT_MONITOR_META"
fault_monitor_property() { echo inactive; }
calls=0
fault_monitor_cleanup_unit() { calls=$((calls + 1)); [[ "$1" == legacy.service ]]; }
if fault_monitor_stop >/dev/null 2>&1; then exit 1; fi
[[ -e "$FAULT_MONITOR_META" && "$calls" -eq 2 ]]
'''
    )
    assert result.returncode == 0, result.stderr


def test_fault_monitor_two_mock_sessions_leave_no_ownership_residue() -> None:
    result = run_shell(
        r'''
ROOT="$(mktemp -d)"; EVIDENCE="$ROOT/evidence"; mkdir -p "$EVIDENCE"
FAULT_LOCK="$ROOT/lock"; FAULT_MONITOR_META="$ROOT/meta.json"; FAULT_MONITOR_HEALTH="$ROOT/health.json"
LEGACY_FAULT_MONITOR_UNIT=legacy.service
phase() { echo FINAL_CONVERGENCE; }
fault_session_update() { :; }
systemd_run_user() { return 0; }
fault_monitor_pre_start_cleanup() { :; }
fault_monitor_wait_healthy() { return 0; }
fault_monitor_healthy() { return 0; }
fault_monitor_property() { [[ "$2" == MainPID ]] && echo 123 || echo inactive; }
fault_monitor_cleanup_unit() { :; }
for session in one two; do
  printf '{"fault_session_id":"%s"}\n' "$session" > "$FAULT_LOCK"
  fault_monitor_start >/dev/null
  printf '{"status":"PASS","session_id":"%s","iteration":1}\n' "$session" > "$FAULT_MONITOR_HEALTH"
  fault_monitor_stop >/dev/null
  rm -f "$FAULT_LOCK"
  [[ ! -e "$FAULT_MONITOR_META" && ! -e "$FAULT_MONITOR_HEALTH" ]]
done
'''
    )
    assert result.returncode == 0, result.stderr


def test_monitor_loop_rejects_session_ownership_mismatch() -> None:
    result = run_shell(
        r'''
ROOT="$(mktemp -d)"; mkdir -p "$ROOT/fault"
FAULT_LOCK="$ROOT/lock"; FAULT_MONITOR_HEALTH="$ROOT/health.json"
printf '{"fault_session_id":"other"}\n' > "$FAULT_LOCK"
if monitor_loop expected >/dev/null 2>&1; then exit 1; fi
[[ ! -e "$FAULT_MONITOR_HEALTH" ]]
'''
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("failure", "expected"),
    (
        ("lock", "fault lock exists"),
        ("monitor", "residual fault monitor exists"),
        ("topology", "residual fault-network attachment"),
        ("convergence", "divergent"),
    ),
)
def test_scenario_b_clean_baseline_rejects_unsafe_state(failure: str, expected: str) -> None:
    result = run_shell(
        rf'''
ROOT="$(mktemp -d)"; EVIDENCE="$ROOT/evidence"; mkdir -p "$EVIDENCE/check"
FAULT_LOCK="$ROOT/lock"; SHARED_NETWORK=shared; NETWORK_A=fault_a; NETWORK_B=fault_b
[[ "{failure}" == lock ]] && touch "$FAULT_LOCK"
fault_monitor_clean_assert() {{ [[ "{failure}" != monitor ]]; }}
docker() {{ return 0; }}
service_running() {{ return 0; }}
service_on_network() {{
  [[ "$2" == shared ]] && return 0
  [[ "{failure}" == topology && "$1" == node-a && "$2" == fault_a ]] && return 0
  return 1
}}
capture_states() {{ printf '[]\n' > "$1"; }}
assert_equal() {{ [[ "{failure}" != convergence ]] || {{ echo divergent >&2; return 1; }}; }}
capture_peer_topology() {{ :; }}
miner_assert_operational() {{ :; }}
systemctl() {{ return 0; }}
if scenario_b_clean_state_precheck "$EVIDENCE/check"; then exit 1; fi
'''
    )
    assert result.returncode == 0
    assert expected in result.stderr


def test_scenario_b_transaction_validation_rejects_submitted_transaction() -> None:
    result = run_shell(
        r'''
ROOT="$(mktemp -d)"; SESSION_DIR="$ROOT/session"; mkdir -p "$SESSION_DIR/transactions/tx-a2" "$SESSION_DIR/transactions/tx-b2" "$ROOT/check"
touch "$SESSION_DIR/transactions/tx-a2/manifest.json" "$SESSION_DIR/transactions/tx-a2/transaction.raw.hex"
touch "$SESSION_DIR/transactions/tx-b2/manifest.json" "$SESSION_DIR/transactions/tx-b2/transaction.raw.hex"
touch "$SESSION_DIR/transactions/tx-a2/submit.json"
if scenario_b_validate_transactions "$ROOT/check"; then exit 1; fi
'''
    )
    assert result.returncode == 0
    assert "already submitted" in result.stderr


def test_scenario_b_transaction_validation_rejects_spent_source() -> None:
    result = run_shell(
        r'''
ROOT="$(mktemp -d)"; SESSION_DIR="$ROOT/session"; mkdir -p "$SESSION_DIR/transactions/tx-a2" "$SESSION_DIR/transactions/tx-b2" "$ROOT/check"
for label in tx-a2 tx-b2; do
  printf 'raw-%s\n' "$label" > "$SESSION_DIR/transactions/$label/transaction.raw.hex"
  hash="$(sha256sum "$SESSION_DIR/transactions/$label/transaction.raw.hex" | cut -d' ' -f1)"
  destination="CHCQ-$label"
  jq -n --arg hash "$hash" --arg destination "$destination" --arg txid "$label" \
    '{address_kind:"pq",signature_scheme_id:10,signature_scheme_name:"mldsa44",txid:$txid,source:{address:"CHCQ-source",txid:"source",vout:0},inputs:[{scheme_id:10}],outputs:[{recipient:$destination}],raw_sha256:$hash}' \
    > "$SESSION_DIR/transactions/$label/manifest.json"
done
compose() { printf '[{"txid":"source","vout":0,"status":"spent","mature":true}]\n'; }
if scenario_b_validate_transactions "$ROOT/check"; then exit 1; fi
'''
    )
    assert result.returncode == 0
    assert "not canonical, mature, and unspent" in result.stderr
