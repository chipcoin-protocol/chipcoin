from __future__ import annotations

import json
from pathlib import Path

from chipcoin.consensus.pq_activation import PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT
from chipcoin.interfaces import cli as cli_module
from chipcoin.pq import operational_readiness as readiness
from chipcoin.tools import pq_operational_readiness


def test_pq_operational_readiness_cli_json_no_network(capsys) -> None:
    code = pq_operational_readiness.main(["--no-network", "--json"])

    assert code == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "UNKNOWN"
    assert payload["activation"]["activation_height"] == PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT


def test_chipcoin_cli_pq_operational_readiness_compact(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        pq_operational_readiness,
        "collect_operational_readiness",
        lambda *, config, run_local_checks=False: readiness.OperationalReadinessResult(
                payload={
                    "status": "READY",
                    "generated_at": "2026-07-22T09:00:00Z",
                    "commit": "test",
                    "network": "testnet",
                "activation": {"activation_height": PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT, "blocks_remaining": 1, "eta_label": "soon"},
                "chain": {"height": PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT - 1, "operational_peer_count": 7},
                "network_readiness": {"height_spread": 0},
                "operational_tests": {
                    "readiness_suite": {"status": "PASS"},
                    "dress_rehearsal": {"status": "PASS"},
                    "chromium_runtime_ci": {"status": "PASS"},
                },
                "pq_metrics": {"pq_verify_failures": {"value": 0}},
                "services": {"explorer": {"status": "OK"}},
                "warnings": [],
                "failures": [],
                "unknowns": [],
            }
        ),
    )

    code = cli_module.main(["pq-operational-readiness", "--compact", "--no-network"])

    assert code == 0
    assert "status=READY" in capsys.readouterr().out


def test_pq_operational_readiness_cli_writes_outputs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(readiness, "_service_checks", lambda *, config: {})
    out_json = tmp_path / "readiness.json"
    out_html = tmp_path / "readiness.html"
    out_md = tmp_path / "readiness.md"

    code = pq_operational_readiness.main(
        [
            "--no-network",
            "--output",
            str(out_json),
            "--html",
            str(out_html),
            "--markdown",
            str(out_md),
        ]
    )

    assert code == 3
    assert json.loads(out_json.read_text(encoding="utf-8"))["schema_version"] == 1
    assert out_html.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert out_md.read_text(encoding="utf-8").startswith("# Post-Quantum Operational Readiness")


def test_pq_operational_readiness_cli_config_error(capsys) -> None:
    code = pq_operational_readiness.main(["--config", "/does/not/exist.toml"])

    assert code == 4
    assert "Status: UNKNOWN" in capsys.readouterr().out
