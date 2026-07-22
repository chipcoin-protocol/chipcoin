from __future__ import annotations

import json
from pathlib import Path

from chipcoin.consensus.pq_activation import PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT
from chipcoin.interfaces import cli as cli_module
from chipcoin.tools import pq_dress_rehearsal


def test_pq_dress_rehearsal_command_writes_reports(tmp_path: Path) -> None:
    json_path = tmp_path / "dress.json"
    markdown_path = tmp_path / "dress.md"

    code = pq_dress_rehearsal.main(
        [
            "--activation-height",
            "4",
            "--output-json",
            str(json_path),
            "--output-markdown",
            str(markdown_path),
            "--skip-subprocess-checks",
            "--skip-browser-checks",
        ]
    )

    assert code == 0
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["activation_height"] == 4
    assert payload["pq_transactions"] >= 4
    assert payload["verify_count"] >= 1
    assert payload["verify_failures"] >= 1
    assert payload["smoke"]["ready"] is True
    assert payload["audit"]["activation"]["testnet"] == PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT
    assert markdown_path.read_text(encoding="utf-8").startswith("# Post-Quantum Testnet Dress Rehearsal Report")


def test_chipcoin_cli_pq_dress_rehearsal_alias_outputs_json(tmp_path: Path, capsys) -> None:
    code = cli_module.main(
        [
            "pq-dress-rehearsal",
            "--activation-height",
            "4",
            "--output-json",
            str(tmp_path / "dress.json"),
            "--output-markdown",
            str(tmp_path / "dress.md"),
            "--skip-subprocess-checks",
            "--skip-browser-checks",
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["activation_height"] == 4


def test_pq_dress_rehearsal_failure_is_nonzero(capsys) -> None:
    code = pq_dress_rehearsal.main(["--activation-height", "1"])

    assert code == 1
    output = capsys.readouterr().out
    assert "POST-QUANTUM DRESS REHEARSAL" in output
    assert "FAIL" in output
    assert "PASS" not in output
