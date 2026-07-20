"""Tests for the operational PQ smoke command."""

from __future__ import annotations

import json
from pathlib import Path

from chipcoin.consensus.pq_activation import pq_support_activation_height
from chipcoin.interfaces.cli import main as cli_main
from chipcoin.pq.readiness import TESTNET_PQ_ACTIVATION_HEIGHT, run_pq_smoke
from chipcoin.tools import pq_smoke


def test_pq_smoke_workflow_completes_successfully_and_cleans_state() -> None:
    result = run_pq_smoke(activation_height=4)

    assert result.ready is True
    assert result.final_local_height >= 4
    assert result.details["api_metadata_source"] == "HttpApiApp"
    assert result.state_preserved is False
    assert not Path(result.state_path).exists()
    assert [stage.label for stage in result.stages] == [
        "created CHCQ address",
        "pre-activation rejected",
        "activation reached",
        "CHC -> CHCQ mined",
        "CHCQ -> CHC mined",
        "API metadata OK",
    ]


def test_pq_smoke_cli_success_outputs_ready(capsys) -> None:
    code = pq_smoke.main(["--activation-height", "4"])
    output = capsys.readouterr().out

    assert code == 0
    assert "CHIPCOIN PQ SMOKE TEST" in output
    assert "PASS  CHCQ -> CHC mined" in output
    assert "READY" in output


def test_chipcoin_cli_pq_smoke_alias_outputs_ready(capsys) -> None:
    code = cli_main(["pq-smoke", "--activation-height", "4"])
    output = capsys.readouterr().out

    assert code == 0
    assert "PASS  API metadata OK" in output
    assert "READY" in output


def test_pq_smoke_cli_failure_is_nonzero_and_does_not_print_ready(capsys) -> None:
    code = pq_smoke.main(["--activation-height", "1"])
    output = capsys.readouterr().out

    assert code != 0
    assert "FAIL  configuration" in output
    assert "READY" not in output


def test_pq_smoke_json_failure_does_not_report_ready(capsys) -> None:
    code = pq_smoke.main(["--activation-height", "1", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code != 0
    assert payload["ready"] is False
    assert payload["failed_stage"] == "configuration"


def test_production_testnet_activation_height_remains_30000() -> None:
    assert pq_support_activation_height("testnet") == TESTNET_PQ_ACTIVATION_HEIGHT == 30_000
