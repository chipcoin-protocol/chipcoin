from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).parents[2]


def test_rehearsal_compose_is_internal_and_uses_mainnet() -> None:
    text = (ROOT / "docker/compose/docker-compose.mainnet-rehearsal.yml").read_text()
    assert "CHIPCOIN_NETWORK: mainnet" in text
    assert re.search(r"networks:\n  rehearsal:\n    internal: true", text)
    assert "0.0.0.0:" not in text
    assert text.count('"127.0.0.1:') == 3


def test_rehearsal_wallet_mounts_are_read_only_and_outside_runtime() -> None:
    text = (ROOT / "docker/compose/docker-compose.mainnet-rehearsal.yml").read_text()
    wallet_sources = re.findall(r"source: ([^\n]*?/secrets/[^\n]+)", text)
    wallet_targets = re.findall(r"target: (/runtime/[^\n]*wallet\.json)\n        read_only: true", text)
    assert len(wallet_sources) == 6
    assert len(wallet_targets) == 6


def test_rehearsal_monitor_ignores_operational_peer_count_differences() -> None:
    script = ROOT / "scripts/mainnet-rehearsal.sh"
    text = script.read_text()
    function = "check_invariants() {" + text.split("check_invariants() {", 1)[1].split("\n}\n", 1)[0] + "\n}"
    shell = f'''
set -euo pipefail
{function}
state_json() {{
  local node="$1" peers=2
  [[ "$node" == node-a ]] && peers=4
  printf '{{"height":1234,"tip_hash":"tip","cumulative_work":42,"handshaken_peer_count":%s,"mempool_size":0,"sync_phase":"idle","sqlite":{{"quick_check":["ok"],"foreign_key_check":[]}}}}\\n' "$peers"
}}
check_invariants node-a node-b node-c
'''
    result = subprocess.run(
        ["bash", "-c", shell],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_rehearsal_monitor_still_rejects_canonical_divergence() -> None:
    script = ROOT / "scripts/mainnet-rehearsal.sh"
    text = script.read_text()
    function = "check_invariants() {" + text.split("check_invariants() {", 1)[1].split("\n}\n", 1)[0] + "\n}"
    shell = f'''
set -euo pipefail
{function}
state_json() {{
  local node="$1" height=1234
  [[ "$node" == node-b ]] && height=1235
  printf '{{"height":%s,"tip_hash":"tip","cumulative_work":42,"handshaken_peer_count":2,"mempool_size":0,"sync_phase":"idle","sqlite":{{"quick_check":["ok"],"foreign_key_check":[]}}}}\\n' "$height"
}}
check_invariants node-a node-b node-c
'''
    result = subprocess.run(
        ["bash", "-c", shell],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0


def test_fault_assert_equal_propagates_canonical_mismatch() -> None:
    harness = (ROOT / "scripts/mainnet-fault-injection.sh").read_text()
    function = harness.split("assert_equal() {", 1)[1].split("\n}", 1)[0]
    assert '>/dev/null &&' in function


def test_fault_harness_is_phase_aware_and_keeps_crash_test_gated() -> None:
    text = (ROOT / "scripts/mainnet-fault-injection.sh").read_text()
    assert "EXPECTED_DIVERGENCE" in text
    assert "CONSENSUS_FAILURE" in text
    assert "CONFIRM_SIGKILL_TEST" in text
    assert "network-self-test" in text
    assert "PARTITION_ACTIVE" in text
    assert "PRAGMA quick_check" in (ROOT / "scripts/mainnet-rehearsal-state.py").read_text()


def test_fault_harness_uses_two_internal_networks_without_consensus_overrides() -> None:
    text = (ROOT / "scripts/mainnet-fault-injection.sh").read_text()
    assert "docker network create --internal" in text
    assert "fault_a" in text
    assert "fault_b" in text
    forbidden = ("difficulty", "maturity", "activation_height", "epoch_length", "genesis_bits")
    assert not any(item in text for item in forbidden)


def test_fault_harness_owns_monitor_and_exposes_recovery_commands() -> None:
    harness = (ROOT / "scripts/mainnet-fault-injection.sh").read_text()
    rehearsal = (ROOT / "scripts/mainnet-rehearsal.sh").read_text()
    for command in (
        "status", "resume", "recover", "scenario-a-confirm", "scenario-b-confirm",
        "reward-reorg-prepare", "reward-reorg-activate", "reward-reorg-checkpoint", "reward-reorg-verify",
    ):
        assert command in harness
    assert "FAULT_LOCK" in harness
    assert "miner_control stop miner-a" in harness
    assert "miner_control stop miner-b" in harness
    assert "fault_monitor_start" in harness
    assert "fault-session lock active; global invariant shutdown suppressed" in rehearsal
    assert "fault-session lock active; milestone recording suppressed" in rehearsal


def test_fault_assertion_markers_require_runtime_observation() -> None:
    text = (ROOT / "scripts/mainnet-fault-injection.sh").read_text()
    assert "TX-A did not reenter mempool" in text
    assert 'status:"ORPHAN_TX_REENTERED_MEMPOOL"' in text
    assert 'status:"CONFLICTING_ORPHAN_TX_REJECTED"' in text
    assert "input_a" in text and "input_b" in text


def test_wait_branch_block_initializes_timeout_before_deadline() -> None:
    text = (ROOT / "scripts/mainnet-fault-injection.sh").read_text()
    function = text.split("wait_branch_block() {", 1)[1].split("\n}", 1)[0]
    assert 'local node="$1" start_height="$2" timeout="${3:-3600}" deadline state' in function
    assert "deadline=$((SECONDS + timeout))" in function


def test_wait_tx_location_initializes_timeout_before_deadline() -> None:
    text = (ROOT / "scripts/mainnet-fault-injection.sh").read_text()
    function = text.split("wait_tx_location() {", 1)[1].split("\n}", 1)[0]
    assert 'local node="$1" txid="$2" expected="$3" timeout="${4:-1800}" deadline value' in function
    assert "deadline=$((SECONDS + timeout))" in function


def test_read_only_baseline_capture_does_not_overwrite_lifecycle_phase() -> None:
    text = (ROOT / "scripts/mainnet-fault-injection.sh").read_text()
    function = text.split("baseline() {", 1)[1].split("\n}", 1)[0]
    assert 'if [[ "$(phase)" == "NONE" ]]' in function
    assert 'transition BASELINE "$dir/manifest.json"' in function


def test_scenario_b_preparation_validates_clean_baseline() -> None:
    text = (ROOT / "scripts/mainnet-fault-injection.sh").read_text()
    function = text.split("prepare_scenario_b() {", 1)[1].split("\n}", 1)[0]
    assert '"BASELINE"' in function
    assert "scenario_b_clean_state_precheck" in function
    assert "prepare_transactions" in function
    assert "scenario_b_validate_transactions" in function
    assert 'transition SCENARIO_B_PREPARED' in function
    prepare = text.split("prepare_transactions() {", 1)[1].split("\n}", 1)[0]
    assert '"$(phase)" == "BASELINE"' in prepare
