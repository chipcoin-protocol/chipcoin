from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from chipcoin.pq import operational_readiness as readiness


def test_operational_readiness_ready(monkeypatch) -> None:
    _fake_live(monkeypatch)
    result = readiness.collect_operational_readiness(config=readiness.OperationalReadinessConfig(no_network=False), repo_root=Path.cwd())

    assert result.status == "READY"
    assert result.exit_code == 0
    assert result.payload["activation"]["blocks_remaining"] == 8_500
    assert result.payload["pq_activity"]["last_100_blocks"]["expected_zero_before_activation"] is True
    assert result.payload["network_readiness"]["height_spread_source"] == "/v1/peers/public"


def test_height_spread_falls_back_to_status_sync_when_public_peers_unavailable(monkeypatch) -> None:
    def fake_collect_api(*, config, activation_height):
        chain = readiness._empty_chain(config=config)
        chain.update(
            {
                "api_status": "OK",
                "api_latency_ms": 30,
                "network": "testnet",
                "height": 11_500,
                "synced": True,
                "sync_phase": "synced",
                "best_block_hash": "00" * 32,
                "peer_count": 9,
                "operational_peer_count": 7,
                "height_spread": 1,
            }
        )
        return {"status": "OK", "available": True, "latency_ms": 30}, chain, [], None

    monkeypatch.setattr(readiness, "_collect_api", fake_collect_api)
    monkeypatch.setattr(readiness, "_service_checks", lambda *, config: _ok_services())

    result = readiness.collect_operational_readiness(config=readiness.OperationalReadinessConfig(no_network=False), repo_root=Path.cwd())

    assert result.payload["network_readiness"]["height_spread"] == 1
    assert result.payload["network_readiness"]["height_spread_source"] == "/v1/status sync.local_height/remote_height"
    assert result.status == "READY"


def test_operational_readiness_degraded_for_major_warning(monkeypatch) -> None:
    _fake_live(monkeypatch, operational_peers=2)
    result = readiness.collect_operational_readiness(config=readiness.OperationalReadinessConfig(no_network=False), repo_root=Path.cwd())

    assert result.status == "DEGRADED"
    assert result.exit_code == 1
    assert any("operational peer count" in reason for reason in result.payload["reasons"])


def test_operational_readiness_not_ready_for_api_failure(monkeypatch) -> None:
    def fake_collect_api(*, config, activation_height):
        chain = readiness._empty_chain(config=config)
        return {"status": "FAIL", "available": False}, chain, [], None

    monkeypatch.setattr(readiness, "_collect_api", fake_collect_api)
    monkeypatch.setattr(readiness, "_service_checks", lambda *, config: _ok_services())
    result = readiness.collect_operational_readiness(config=readiness.OperationalReadinessConfig(no_network=False), repo_root=Path.cwd())

    assert result.status == "NOT READY"
    assert result.exit_code == 2
    assert any("testnet API is not reachable" in failure for failure in result.payload["failures"])


def test_operational_readiness_unknown_when_network_disabled() -> None:
    result = readiness.collect_operational_readiness(config=readiness.OperationalReadinessConfig(no_network=True), repo_root=Path.cwd())

    assert result.status == "UNKNOWN"
    assert result.exit_code == 3
    assert "network checks disabled by --no-network" in result.payload["unknowns"]


def test_activation_eta_and_reached(monkeypatch) -> None:
    _fake_live(monkeypatch, height=30_010)
    result = readiness.collect_operational_readiness(config=readiness.OperationalReadinessConfig(no_network=False), repo_root=Path.cwd())

    assert result.payload["activation"]["blocks_remaining"] == 0
    assert result.payload["activation"]["eta_label"] == "activation reached"


def test_json_schema_does_not_confuse_unknown_with_zero(monkeypatch) -> None:
    result = readiness.collect_operational_readiness(config=readiness.OperationalReadinessConfig(no_network=True), repo_root=Path.cwd())

    payload = result.payload
    assert payload["schema_version"] == 1
    assert payload["pq_metrics"]["pq_malformed"]["availability"] == "unavailable"
    assert payload["pq_metrics"]["pq_malformed"]["value"] is None


def test_render_outputs_and_html_escaping(monkeypatch) -> None:
    _fake_live(monkeypatch)
    result = readiness.collect_operational_readiness(config=readiness.OperationalReadinessConfig(no_network=False), repo_root=Path.cwd())
    result.payload["warnings"].append("<script>alert(1)</script>")

    html = readiness.render_html(result)
    markdown = readiness.render_markdown(result)
    daily = readiness.render_daily_report_section(result)

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "# Post-Quantum Operational Readiness" in markdown
    assert "## Post-Quantum Operational Readiness" in daily


def test_atomic_writes_and_history(monkeypatch, tmp_path: Path) -> None:
    _fake_live(monkeypatch)
    result = readiness.collect_operational_readiness(config=readiness.OperationalReadinessConfig(no_network=False), repo_root=Path.cwd())

    written = readiness.write_outputs(result, output_dir=tmp_path)

    assert (tmp_path / "latest.json").exists()
    assert (tmp_path / "latest.html").exists()
    assert (tmp_path / "latest.md").exists()
    assert list((tmp_path / "history").glob("*.json"))
    assert written["latest.json"].endswith("latest.json")


def test_config_precedence(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "readiness.toml"
    config_path.write_text('api_url = "https://config.example"\ntimeout_seconds = 9\noutput_dir = "from-config"\n', encoding="utf-8")
    monkeypatch.setenv("CHIPCOIN_PQ_READINESS_API_URL", "https://env.example")

    config = readiness.build_config(config_path=config_path, api_url="https://cli.example", output_dir=tmp_path / "out")

    assert config.api_url == "https://cli.example"
    assert config.timeout_seconds == 9
    assert config.output_dir == tmp_path / "out"


def test_default_explorer_url_is_public_live_testnet() -> None:
    assert readiness.OperationalReadinessConfig().explorer_url == "https://chipcoinprotocol.com/live-testnet"


def test_cli_compact_render(monkeypatch) -> None:
    _fake_live(monkeypatch)
    result = readiness.collect_operational_readiness(config=readiness.OperationalReadinessConfig(no_network=False), repo_root=Path.cwd())

    compact = readiness.render_cli(result, compact=True)

    assert compact.startswith("status=READY")
    assert "activation_height=20000" in compact


def _fake_live(monkeypatch, *, height: int = 11_500, operational_peers: int = 7) -> None:
    now = int(datetime(2026, 7, 22, 9, 0, tzinfo=UTC).timestamp())
    blocks = [{"height": height - index, "timestamp": now - (index * 600), "transactions": []} for index in range(20)]

    def fake_collect_api(*, config, activation_height):
        chain = readiness._empty_chain(config=config)
        chain.update(
            {
                "api_status": "OK",
                "api_latency_ms": 50,
                "network": "testnet",
                "height": height,
                "synced": True,
                "sync_phase": "synced",
                "best_block_hash": "00" * 32,
                "peer_count": 9,
                "operational_peer_count": operational_peers,
                "handshaken_peer_count": 7,
            }
        )
        peers = {"peers": [{"last_known_height": height}, {"last_known_height": height - 1}, {"last_known_height": height}]}
        return {"status": "OK", "available": True, "latency_ms": 50}, chain, blocks, peers

    monkeypatch.setattr(readiness, "_collect_api", fake_collect_api)
    monkeypatch.setattr(readiness, "_service_checks", lambda *, config: _ok_services())


def _ok_services() -> dict[str, dict[str, object]]:
    return {
        name: {"status": "OK", "reachable": True, "http_status": 200, "latency_ms": 30, "error": None}
        for name in ("website", "testnet_api", "explorer", "faucet", "snapshot", "browser_wallet", "documentation")
    }
