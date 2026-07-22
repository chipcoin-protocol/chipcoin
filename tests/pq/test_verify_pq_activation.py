from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chipcoin.consensus.pq_activation import (
    PQ_SUPPORT_DEVNET_ACTIVATION_HEIGHT,
    PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT,
)
from chipcoin.interfaces import cli as cli_module
from chipcoin.tools import verify_pq_activation


ROOT = Path(__file__).resolve().parents[2]


def test_verify_pq_activation_uses_runtime_constants() -> None:
    testnet = verify_pq_activation.verify_activation_height("testnet", 20_000)
    devnet = verify_pq_activation.verify_activation_height("devnet", 30_000)

    assert testnet.actual_activation_height == PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT == 20_000
    assert testnet.status == "PASS"
    assert devnet.actual_activation_height == PQ_SUPPORT_DEVNET_ACTIVATION_HEIGHT == 30_000
    assert devnet.status == "PASS"


def test_verify_pq_activation_cli_json(capsys) -> None:
    code = verify_pq_activation.main(["--network", "testnet", "--expected-height", "20000", "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "schema_version": 1,
        "network": "testnet",
        "actual_activation_height": 20_000,
        "expected_activation_height": 20_000,
        "status": "PASS",
    }


def test_verify_pq_activation_mismatch_exit_code(capsys) -> None:
    code = verify_pq_activation.main(["--network", "testnet", "--expected-height", "30000"])

    assert code == 1
    assert "Status: FAIL" in capsys.readouterr().out


def test_verify_pq_activation_invalid_network_exit_code(capsys) -> None:
    code = verify_pq_activation.main(["--network", "unknown", "--expected-height", "20000", "--json"])

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert "unsupported network" in payload["error"]


def test_chipcoin_cli_verify_pq_activation(capsys) -> None:
    code = cli_module.main(["verify-pq-activation", "--network", "testnet", "--expected-height", "20000"])

    assert code == 0
    assert "PQ activation height: 20000" in capsys.readouterr().out


def test_verify_pq_activation_server_script() -> None:
    env = {
        **os.environ,
        "CHIPCOIN_ROOT": str(ROOT),
        "CHIPCOIN_PYTHON": sys.executable,
        "CHIPCOIN_NETWORK": "testnet",
        "EXPECTED_PQ_HEIGHT": "20000",
    }
    result = subprocess.run(
        [str(ROOT / "scripts/verify-pq-activation.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0
    assert "Status: PASS" in result.stdout
    assert "Chipcoin module:" in result.stdout


def test_rollout_scripts_have_help() -> None:
    for script in (
        ROOT / "scripts/pq-height-20000-preflight.sh",
        ROOT / "scripts/pq-height-20000-postdeploy.sh",
        ROOT / "scripts/verify-pq-activation.sh",
    ):
        result = subprocess.run(
            [str(script), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        assert result.returncode == 0
        assert "PQ" in result.stdout or "activation" in result.stdout
