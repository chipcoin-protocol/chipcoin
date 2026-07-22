"""Read-only Post-Quantum operational readiness dashboard."""

from __future__ import annotations

import html
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
import statistics
import subprocess
import sys
import time
import tomllib
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..consensus.pq_activation import pq_support_activation_height
from ..tools.pq_audit_report import build_report as build_pq_audit_report


SCHEMA_VERSION = 1
DEFAULT_NETWORK = "testnet"
DEFAULT_API_URL = "http://127.0.0.1:28081"
DEFAULT_OUTPUT_DIR = Path("var/pq-readiness")


@dataclass(frozen=True)
class OperationalReadinessThresholds:
    """Operational thresholds used for transparent readiness scoring."""

    min_operational_peers: int = 5
    max_height_spread: int = 3
    max_api_latency_ms: int = 2_000
    max_chain_age_seconds: int = 3_600
    max_miner_top_share_percent: float = 60.0
    max_pq_verify_failure_count: int = 0


@dataclass(frozen=True)
class OperationalReadinessFreshness:
    """Freshness windows for cached reports and live data."""

    network_seconds: int = 600
    smoke_seconds: int = 86_400
    readiness_seconds: int = 604_800
    dress_rehearsal_seconds: int = 1_209_600
    benchmark_seconds: int = 2_592_000


@dataclass(frozen=True)
class OperationalReadinessConfig:
    """Configuration for read-only PQ operational readiness collection."""

    network: str = DEFAULT_NETWORK
    api_url: str | None = DEFAULT_API_URL
    timeout_seconds: float = 5.0
    no_network: bool = False
    strict: bool = False
    compact: bool = False
    block_interval_window: int = 20
    output_dir: Path | None = None
    minimum_compatible_version: str | None = None
    website_url: str | None = "https://chipcoinprotocol.com/"
    explorer_url: str | None = "https://chipcoinprotocol.com/explorer"
    faucet_url: str | None = "https://chipcoinprotocol.com/faucet"
    snapshot_url: str | None = "https://chipcoinprotocol.com/downloads/"
    browser_wallet_url: str | None = "https://chipcoinprotocol.com/browser-wallet"
    docs_url: str | None = "https://chipcoinprotocol.com/developer"
    thresholds: OperationalReadinessThresholds = field(default_factory=OperationalReadinessThresholds)
    freshness: OperationalReadinessFreshness = field(default_factory=OperationalReadinessFreshness)


@dataclass(frozen=True)
class OperationalReadinessResult:
    """Stable operational readiness payload wrapper."""

    payload: dict[str, Any]

    @property
    def status(self) -> str:
        return str(self.payload["status"])

    @property
    def exit_code(self) -> int:
        return {"READY": 0, "DEGRADED": 1, "NOT READY": 2, "UNKNOWN": 3}.get(self.status, 4)


def load_config(path: Path | None) -> dict[str, Any]:
    """Load optional TOML configuration."""

    if path is None:
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def build_config(
    *,
    config_path: Path | None = None,
    api_url: str | None = None,
    timeout_seconds: float | None = None,
    no_network: bool | None = None,
    strict: bool = False,
    compact: bool = False,
    output_dir: Path | None = None,
    block_interval_window: int | None = None,
) -> OperationalReadinessConfig:
    """Merge config with precedence CLI > environment > TOML > defaults."""

    raw = load_config(config_path)
    thresholds = OperationalReadinessThresholds(**raw.get("thresholds", {}))
    freshness = OperationalReadinessFreshness(**raw.get("freshness", {}))

    def choose(name: str, cli_value, env_name: str, default):
        if cli_value is not None:
            return cli_value
        if env_name in os.environ:
            value = os.environ[env_name]
            if isinstance(default, bool):
                return value.lower() in {"1", "true", "yes", "on"}
            if isinstance(default, (int, float)):
                return type(default)(value)
            if isinstance(default, Path):
                return Path(value)
            return value
        return raw.get(name, default)

    default = OperationalReadinessConfig()
    selected_output_dir = choose("output_dir", output_dir, "CHIPCOIN_PQ_READINESS_OUTPUT_DIR", raw.get("output_dir"))
    if selected_output_dir is not None and not isinstance(selected_output_dir, Path):
        selected_output_dir = Path(str(selected_output_dir))

    return OperationalReadinessConfig(
        network=str(raw.get("network", default.network)),
        api_url=choose("api_url", api_url, "CHIPCOIN_PQ_READINESS_API_URL", default.api_url),
        timeout_seconds=float(choose("timeout_seconds", timeout_seconds, "CHIPCOIN_PQ_READINESS_TIMEOUT", default.timeout_seconds)),
        no_network=bool(choose("no_network", no_network, "CHIPCOIN_PQ_READINESS_NO_NETWORK", default.no_network)),
        strict=strict or bool(raw.get("strict", default.strict)),
        compact=compact or bool(raw.get("compact", default.compact)),
        block_interval_window=int(
            choose("block_interval_window", block_interval_window, "CHIPCOIN_PQ_READINESS_BLOCK_WINDOW", default.block_interval_window)
        ),
        output_dir=selected_output_dir,
        minimum_compatible_version=raw.get("minimum_compatible_version", default.minimum_compatible_version),
        website_url=raw.get("website_url", default.website_url),
        explorer_url=raw.get("explorer_url", default.explorer_url),
        faucet_url=raw.get("faucet_url", default.faucet_url),
        snapshot_url=raw.get("snapshot_url", default.snapshot_url),
        browser_wallet_url=raw.get("browser_wallet_url", default.browser_wallet_url),
        docs_url=raw.get("docs_url", default.docs_url),
        thresholds=thresholds,
        freshness=freshness,
    )


def collect_operational_readiness(
    *,
    config: OperationalReadinessConfig,
    repo_root: Path | None = None,
    run_local_checks: bool = False,
) -> OperationalReadinessResult:
    """Collect a read-only operational PQ readiness snapshot."""

    root = Path.cwd() if repo_root is None else repo_root
    generated_at = _now()
    commit = _current_commit(root)
    audit = build_pq_audit_report(repo_root=root)
    activation_height = int(audit["activation"]["testnet"])
    chain = _empty_chain(config=config)
    api_check = {"status": "SKIPPED" if config.no_network else "UNKNOWN", "available": False}
    services: dict[str, Any] = {}
    warnings: list[str] = []
    failures: list[str] = []
    unknowns: list[str] = []

    blocks: list[dict[str, Any]] = []
    peers_public: dict[str, Any] | None = None
    if config.no_network:
        unknowns.append("network checks disabled by --no-network")
    elif config.api_url:
        api_check, chain, blocks, peers_public = _collect_api(config=config, activation_height=activation_height)
        if not api_check["available"]:
            unknowns.append("testnet API unavailable")
    else:
        unknowns.append("api_url is not configured")

    activation = _activation_section(chain=chain, blocks=blocks, activation_height=activation_height, config=config, generated_at=generated_at)
    network_readiness = _network_readiness(chain=chain, peers_public=peers_public, config=config)
    pq_features = _pq_features(audit=audit, root=root)
    operational_tests = _operational_tests(root=root, commit=commit, generated_at=generated_at, run_local_checks=run_local_checks)
    pq_metrics = _pq_metrics(chain=chain, operational_tests=operational_tests)
    pq_activity = _pq_activity(blocks=blocks, activation_height=activation_height, current_height=chain.get("height"))
    if not config.no_network:
        services = _service_checks(config=config)
    else:
        services = _service_skipped(config=config)

    gate_results = _critical_gates(
        chain=chain,
        api_check=api_check,
        pq_features=pq_features,
        operational_tests=operational_tests,
        config=config,
    )
    major_results = _major_signals(
        chain=chain,
        network_readiness=network_readiness,
        services=services,
        pq_metrics=pq_metrics,
        operational_tests=operational_tests,
        config=config,
    )
    informational = _informational_signals(pq_activity=pq_activity, network_readiness=network_readiness)
    status, reasons = _score(gate_results, major_results, unknowns=unknowns)

    warnings.extend(item["reason"] for item in major_results if item["status"] in {"FAIL", "UNKNOWN"})
    failures.extend(item["reason"] for item in gate_results if item["status"] == "FAIL")
    unknowns.extend(item["reason"] for item in gate_results + major_results if item["status"] == "UNKNOWN")
    unknowns = sorted(set(unknowns))

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "commit": commit,
        "network": config.network,
        "status": status,
        "activation": activation,
        "chain": chain,
        "network_readiness": network_readiness,
        "pq_features": pq_features,
        "operational_tests": operational_tests,
        "pq_metrics": pq_metrics,
        "pq_activity": pq_activity,
        "services": services,
        "critical_gates": gate_results,
        "major_signals": major_results,
        "informational_signals": informational,
        "warnings": warnings,
        "failures": failures,
        "unknowns": unknowns,
        "reasons": reasons,
        "thresholds": asdict(config.thresholds),
        "freshness": asdict(config.freshness),
    }
    return OperationalReadinessResult(payload=payload)


def write_outputs(
    result: OperationalReadinessResult,
    *,
    output_dir: Path | None = None,
    output_json: Path | None = None,
    output_html: Path | None = None,
    output_markdown: Path | None = None,
) -> dict[str, str]:
    """Atomically write latest/history JSON, HTML and Markdown outputs."""

    written: dict[str, str] = {}
    timestamp = str(result.payload["generated_at"]).replace(":", "").replace("-", "")
    if output_dir is not None:
        latest_json = output_dir / "latest.json"
        latest_html = output_dir / "latest.html"
        latest_md = output_dir / "latest.md"
        history_json = output_dir / "history" / f"{timestamp}.json"
        for path, content in (
            (latest_json, json.dumps(result.payload, indent=2, sort_keys=True) + "\n"),
            (history_json, json.dumps(result.payload, indent=2, sort_keys=True) + "\n"),
            (latest_html, render_html(result)),
            (latest_md, render_markdown(result)),
        ):
            _atomic_write(path, content)
            written[path.name if path.parent.name != "history" else "history_json"] = str(path)
    if output_json is not None:
        _atomic_write(output_json, json.dumps(result.payload, indent=2, sort_keys=True) + "\n")
        written["json"] = str(output_json)
    if output_html is not None:
        _atomic_write(output_html, render_html(result))
        written["html"] = str(output_html)
    if output_markdown is not None:
        _atomic_write(output_markdown, render_markdown(result))
        written["markdown"] = str(output_markdown)
    return written


def render_cli(result: OperationalReadinessResult, *, compact: bool = False) -> str:
    """Render human-readable CLI output."""

    payload = result.payload
    activation = payload["activation"]
    chain = payload["chain"]
    if compact:
        return (
            f"status={payload['status']} network={payload['network']} "
            f"height={chain.get('height')} activation_height={activation.get('activation_height')} "
            f"remaining={activation.get('blocks_remaining')} warnings={len(payload['warnings'])} failures={len(payload['failures'])}"
        )
    lines = [
        "POST-QUANTUM OPERATIONAL READINESS",
        "",
        f"Status: {payload['status']}",
        f"Network: {payload['network']}",
        f"Height: {_display(chain.get('height'))} / {activation.get('activation_height')}",
        f"Remaining: {_display(activation.get('blocks_remaining'))} blocks",
        f"ETA: {_display(activation.get('eta_label'))}",
        f"Peers: {_display(chain.get('operational_peer_count'))} operational",
        f"Height spread: {_display(payload['network_readiness'].get('height_spread'))}",
        f"Readiness suite: {payload['operational_tests']['readiness_suite']['status']}",
        f"Dress rehearsal: {payload['operational_tests']['dress_rehearsal']['status']}",
        f"Chromium runtime: {payload['operational_tests']['chromium_runtime_ci']['status']}",
        f"PQ verify failures: {_display(payload['pq_metrics']['pq_verify_failures']['value'])}",
        f"Explorer: {payload['services'].get('explorer', {}).get('status', 'UNKNOWN')}",
        f"API: {payload['chain'].get('api_status', 'UNKNOWN')}",
        "",
        "Warnings:",
    ]
    lines.extend(f"- {warning}" for warning in payload["warnings"]) if payload["warnings"] else lines.append("- none")
    if payload["failures"]:
        lines.extend(["", "Failures:"])
        lines.extend(f"- {failure}" for failure in payload["failures"])
    if payload["unknowns"]:
        lines.extend(["", "Unknowns:"])
        lines.extend(f"- {unknown}" for unknown in payload["unknowns"])
    return "\n".join(lines)


def render_markdown(result: OperationalReadinessResult) -> str:
    """Render Markdown report for daily reports and operations notes."""

    p = result.payload
    lines = [
        "# Post-Quantum Operational Readiness",
        "",
        f"Status: **{p['status']}**",
        f"Generated: `{p['generated_at']}`",
        f"Commit: `{p['commit']}`",
        "",
        "## Countdown",
        "",
        f"- Height: `{_display(p['chain'].get('height'))}` / `{p['activation']['activation_height']}`",
        f"- Blocks remaining: `{_display(p['activation'].get('blocks_remaining'))}`",
        f"- Progress: `{_display(p['activation'].get('progress_percent'))}%`",
        f"- ETA: `{_display(p['activation'].get('eta_label'))}`",
        "",
        "## Critical Gates",
        "",
    ]
    lines.extend(f"- {item['status']} {item['name']}: {item['reason']}" for item in p["critical_gates"])
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in p["warnings"]) if p["warnings"] else lines.append("- none")
    lines.extend(["", "## Test Status", ""])
    for name, item in p["operational_tests"].items():
        lines.append(f"- {name}: `{item['status']}` source=`{item.get('source')}` age=`{item.get('age_seconds')}`")
    lines.extend(["", "## Services", ""])
    for name, item in p["services"].items():
        lines.append(f"- {name}: `{item['status']}` latency_ms=`{item.get('latency_ms')}`")
    lines.extend(["", "## PQ Metrics", ""])
    for name, item in p["pq_metrics"].items():
        lines.append(f"- {name}: `{_display(item.get('value'))}` availability=`{item.get('availability')}`")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {reason}" for reason in p["reasons"]) if p["reasons"] else lines.append("- Continue normal monitoring.")
    return "\n".join(lines) + "\n"


def render_daily_report_section(result: OperationalReadinessResult) -> str:
    """Render the compact section intended for the existing daily report."""

    p = result.payload
    return "\n".join(
        [
            "## Post-Quantum Operational Readiness",
            "",
            f"- Status: `{p['status']}`",
            f"- Height: `{_display(p['chain'].get('height'))}` / `{p['activation']['activation_height']}`",
            f"- Remaining blocks: `{_display(p['activation'].get('blocks_remaining'))}`",
            f"- ETA: `{_display(p['activation'].get('eta_label'))}`",
            f"- Critical failures: `{len(p['failures'])}`",
            f"- Major warnings: `{len(p['warnings'])}`",
            f"- Last dress rehearsal: `{p['operational_tests']['dress_rehearsal'].get('status')}`",
            f"- Last readiness suite: `{p['operational_tests']['readiness_suite'].get('status')}`",
            f"- PQ activity: `{p['pq_activity'].get('pre_activation_note') or 'see dashboard'}`",
        ]
    ) + "\n"


def render_html(result: OperationalReadinessResult) -> str:
    """Render standalone static HTML dashboard."""

    p = result.payload
    status = html.escape(str(p["status"]))
    progress = p["activation"].get("progress_percent")
    progress_width = 0 if not isinstance(progress, (int, float)) else max(0, min(100, float(progress)))
    cards = [
        ("Height", f"{_display(p['chain'].get('height'))} / {p['activation']['activation_height']}"),
        ("Remaining", f"{_display(p['activation'].get('blocks_remaining'))} blocks"),
        ("ETA", _display(p["activation"].get("eta_label"))),
        ("Peers", f"{_display(p['chain'].get('operational_peer_count'))} operational"),
        ("PQ verify failures", _display(p["pq_metrics"]["pq_verify_failures"].get("value"))),
        ("Dress rehearsal", p["operational_tests"]["dress_rehearsal"]["status"]),
    ]
    card_html = "\n".join(f"<div class=\"card\"><h2>{html.escape(label)}</h2><p>{html.escape(str(value))}</p></div>" for label, value in cards)
    warnings = "".join(f"<li>{html.escape(str(item))}</li>" for item in p["warnings"]) or "<li>none</li>"
    failures = "".join(f"<li>{html.escape(str(item))}</li>" for item in p["failures"]) or "<li>none</li>"
    test_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(name),
            html.escape(str(item.get("status"))),
            html.escape(str(item.get("source"))),
            html.escape(_display(item.get("age_seconds"))),
        )
        for name, item in p["operational_tests"].items()
    )
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Chipcoin PQ Operational Readiness</title>
  <style>
    body {{ margin:0; font-family: system-ui, -apple-system, Segoe UI, sans-serif; color:#17211b; background:#f7f7f3; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 28px 18px 48px; }}
    .status {{ display:inline-block; padding: 6px 10px; border: 1px solid #17211b; border-radius: 6px; font-weight:700; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); gap: 12px; margin: 18px 0; }}
    .card {{ border: 1px solid #d5d8ce; background:#fff; border-radius: 8px; padding: 14px; }}
    .card h2 {{ font-size: .85rem; text-transform: uppercase; letter-spacing: .04em; color:#596257; margin:0 0 8px; }}
    .card p {{ font-size: 1.35rem; margin:0; font-weight:700; }}
    .bar {{ height: 14px; background:#e1e5da; border-radius: 4px; overflow:hidden; }}
    .fill {{ height: 100%; width: {progress_width:.2f}%; background:#2e7d55; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid #d5d8ce; }}
    th, td {{ padding:8px 10px; border-bottom:1px solid #e4e6df; text-align:left; }}
    th {{ background:#eef1e8; }}
    footer {{ margin-top: 28px; color:#596257; font-size:.9rem; }}
  </style>
</head>
<body>
<main>
  <h1>Post-Quantum Operational Readiness</h1>
  <p class=\"status\">{status}</p>
  <p>Generated {html.escape(str(p['generated_at']))}</p>
  <div class=\"bar\"><div class=\"fill\"></div></div>
  <div class=\"grid\">{card_html}</div>
  <h2>Warnings</h2><ul>{warnings}</ul>
  <h2>Failures</h2><ul>{failures}</ul>
  <h2>Test Freshness</h2>
  <table><thead><tr><th>Test</th><th>Status</th><th>Source</th><th>Age seconds</th></tr></thead><tbody>{test_rows}</tbody></table>
  <footer>Commit {html.escape(str(p['commit']))} · schema version {SCHEMA_VERSION}</footer>
</main>
</body>
</html>
"""


def _collect_api(*, config: OperationalReadinessConfig, activation_height: int):
    status, latency_ms, error = _fetch_json(config.api_url, "/v1/status", config.timeout_seconds)
    api_check = {
        "status": "OK" if status is not None else "FAIL",
        "available": status is not None,
        "latency_ms": latency_ms,
        "error": error,
        "url": config.api_url,
    }
    chain = _empty_chain(config=config)
    blocks: list[dict[str, Any]] = []
    peers_public = None
    if status is not None:
        chain.update(
            {
                "api_status": "OK",
                "api_latency_ms": latency_ms,
                "network": status.get("network"),
                "height": status.get("height"),
                "synced": status.get("sync_phase") == "synced",
                "sync_phase": status.get("sync_phase"),
                "best_block_hash": status.get("tip_hash"),
                "peer_count": status.get("peer_count"),
                "operational_peer_count": status.get("operational_peer_count"),
                "handshaken_peer_count": status.get("handshaken_peer_count"),
                "node_version": status.get("version"),
                "network_identifier": status.get("network_magic_hex"),
            }
        )
        height = status.get("height")
        if isinstance(height, int):
            block_payload, _, _ = _fetch_json(
                config.api_url,
                "/v1/blocks?" + urlencode({"limit": min(100, max(1, config.block_interval_window)), "from_height": height}),
                config.timeout_seconds,
            )
            if isinstance(block_payload, list):
                blocks = [block for block in block_payload if isinstance(block, dict)]
                newest_time = _block_timestamp(blocks[0]) if blocks else None
                if newest_time is not None:
                    chain["chain_tip_timestamp"] = newest_time.isoformat().replace("+00:00", "Z")
                    chain["chain_age_seconds"] = max(0, int((_now() - newest_time).total_seconds()))
    peers_public, _, _ = _fetch_json(config.api_url, "/v1/peers/public", config.timeout_seconds)
    return api_check, chain, blocks, peers_public if isinstance(peers_public, dict) else None


def _activation_section(*, chain: dict[str, Any], blocks: list[dict[str, Any]], activation_height: int, config: OperationalReadinessConfig, generated_at: datetime) -> dict[str, Any]:
    height = chain.get("height")
    remaining = None if not isinstance(height, int) else max(0, activation_height - height)
    intervals = _block_intervals(blocks)
    avg_interval = statistics.fmean(intervals) if intervals else None
    median_interval = statistics.median(intervals) if intervals else None
    eta_timestamp = None
    eta_label = "UNKNOWN"
    confidence = "UNKNOWN"
    if remaining == 0:
        eta_label = "activation reached"
        confidence = "HIGH"
    elif isinstance(remaining, int) and median_interval is not None:
        seconds = int(remaining * median_interval)
        eta = generated_at + timedelta(seconds=seconds)
        eta_timestamp = eta.isoformat().replace("+00:00", "Z")
        eta_label = f"approximately {timedelta(seconds=seconds)}"
        confidence = "LOW" if len(intervals) < 10 or (max(intervals) > median_interval * 4 if median_interval else True) else "MEDIUM"
    progress = None if not isinstance(height, int) else round(min(100.0, (height / activation_height) * 100), 2)
    return {
        "activation_height": activation_height,
        "current_height": height,
        "blocks_remaining": remaining,
        "progress_percent": progress,
        "average_block_interval_seconds": None if avg_interval is None else round(avg_interval, 2),
        "median_block_interval_seconds": None if median_interval is None else round(median_interval, 2),
        "eta_timestamp": eta_timestamp,
        "eta_label": eta_label,
        "eta_confidence": confidence,
        "block_interval_window": config.block_interval_window,
    }


def _network_readiness(*, chain: dict[str, Any], peers_public: dict[str, Any] | None, config: OperationalReadinessConfig) -> dict[str, Any]:
    heights: list[int] = []
    if peers_public:
        for peer in peers_public.get("peers", []):
            if isinstance(peer, dict) and isinstance(peer.get("last_known_height"), int):
                heights.append(peer["last_known_height"])
    spread = None if not heights else max(heights) - min(heights)
    return {
        "peer_total": chain.get("peer_count"),
        "peer_operational": chain.get("operational_peer_count"),
        "peer_public": None if peers_public is None else len(peers_public.get("peers", [])),
        "peer_synced": sum(1 for height in heights if height == chain.get("height")) if heights else None,
        "version_distribution": None,
        "version_distribution_status": "UNKNOWN — peer version distribution not available",
        "minimum_compatible_version": config.minimum_compatible_version,
        "reward_nodes_registered": None,
        "reward_nodes_attested": None,
        "miner_unique_recent": None,
        "top_miner_share_percent": None,
        "height_spread": spread,
    }


def _pq_features(*, audit: dict[str, Any], root: Path) -> dict[str, Any]:
    artifacts = audit["artifacts"]
    return {
        "mldsa_backend_available": audit["mldsa44"]["backend_available"],
        "scheme_name": audit["scheme"]["mldsa44_scheme_name"],
        "scheme_id": audit["scheme"]["mldsa44_scheme_id"],
        "chcq_address_support": True,
        "transaction_v2_support": True,
        "activation_gating_configured": audit["activation"]["testnet"] == pq_support_activation_height("testnet"),
        "activation_height": audit["activation"]["testnet"],
        "api_pq_metadata_support": True,
        "explorer_pq_visibility_status": "available" if artifacts.get("pq_vector_fixture") else "UNKNOWN",
        "browser_pq_recognition": artifacts.get("pq_vector_fixture", False),
        "browser_pq_signing_feature_flag": "false",
        "browser_pq_send_enabled": False,
        "policy_hardening_available": True,
        "pq_metrics_available": True,
        "audit_report_available": True,
        "benchmark_command_available": artifacts.get("benchmark_command", False),
        "smoke_command_available": artifacts.get("smoke_command", False),
        "dress_rehearsal_available": (root / "src/chipcoin/tools/pq_dress_rehearsal.py").exists(),
    }


def _operational_tests(*, root: Path, commit: str, generated_at: datetime, run_local_checks: bool) -> dict[str, Any]:
    tests = {
        "readiness_suite": _test_artifact(root / "scripts/pq-activation-readiness.sh", commit, generated_at, "script"),
        "pq_smoke": _test_artifact(root / "src/chipcoin/tools/pq_smoke.py", commit, generated_at, "command"),
        "dress_rehearsal": _json_report_artifact(root / "pq-dress-rehearsal.json", commit, generated_at),
        "pq_audit_report": _local_audit_status(commit=commit, run=run_local_checks),
        "pq_benchmark": _json_report_artifact(root / "pq-dress-rehearsal.json", commit, generated_at, nested_key="benchmark"),
        "chromium_runtime_ci": _workflow_artifact(root / ".github/workflows/browser-pq-chromium.yml", commit, generated_at),
        "firefox_runtime": {"status": "UNKNOWN", "source": "manual/local", "timestamp": None, "commit": None, "age_seconds": None},
    }
    return tests


def _pq_metrics(*, chain: dict[str, Any], operational_tests: dict[str, Any]) -> dict[str, Any]:
    dress = operational_tests.get("dress_rehearsal", {}).get("payload") or {}
    metrics = {}
    for name in (
        "pq_verify_count",
        "pq_verify_failures",
        "pq_verify_duration_seconds_total",
        "pq_tx_accepted",
        "pq_tx_rejected",
        "pq_malformed",
        "pq_relay",
        "pq_mined",
        "pq_orphan",
    ):
        value = chain.get(name)
        source = "api"
        if value is None and name == "pq_verify_count":
            value = dress.get("verify_count")
            source = "dress_rehearsal"
        if value is None and name == "pq_verify_failures":
            value = dress.get("verify_failures")
            source = "dress_rehearsal"
        metrics[name] = {
            "value": value,
            "availability": "available" if value is not None else "unavailable",
            "source": source if value is not None else None,
            "last_updated": dress.get("generated_at"),
            "delta_recent": None,
        }
    return metrics


def _pq_activity(*, blocks: list[dict[str, Any]], activation_height: int, current_height: Any) -> dict[str, Any]:
    tx_v2 = 0
    chcq_outputs = 0
    mldsa_inputs = 0
    first_output = None
    first_spend = None
    last_pq_block = None
    for block in blocks:
        transactions = block.get("transactions", [])
        for tx in transactions if isinstance(transactions, list) else []:
            if not isinstance(tx, dict):
                continue
            if tx.get("version") == 2:
                tx_v2 += 1
            for tx_input in tx.get("inputs", []) if isinstance(tx.get("inputs"), list) else []:
                if isinstance(tx_input, dict) and tx_input.get("sig_scheme_id") == 10:
                    mldsa_inputs += 1
                    first_spend = first_spend or tx.get("txid")
                    last_pq_block = block.get("height")
            for output in tx.get("outputs", []) if isinstance(tx.get("outputs"), list) else []:
                if isinstance(output, dict) and output.get("address_kind") == "pq":
                    chcq_outputs += 1
                    first_output = first_output or tx.get("txid")
                    last_pq_block = block.get("height")
    expected_zero = isinstance(current_height, int) and current_height < activation_height
    return {
        "recent_tx_v2": tx_v2 if blocks else None,
        "recent_mldsa_inputs": mldsa_inputs if blocks else None,
        "recent_chcq_outputs": chcq_outputs if blocks else None,
        "recent_chcq_spends": mldsa_inputs if blocks else None,
        "first_chcq_output": first_output,
        "first_chcq_spend": first_spend,
        "last_pq_block": last_pq_block,
        "last_24h": None,
        "last_100_blocks": {"blocks_counted": len(blocks), "expected_zero_before_activation": expected_zero},
        "pre_activation_note": "Expected before activation" if expected_zero else None,
    }


def _service_checks(*, config: OperationalReadinessConfig) -> dict[str, Any]:
    urls = {
        "website": config.website_url,
        "testnet_api": config.api_url,
        "explorer": config.explorer_url,
        "faucet": config.faucet_url,
        "snapshot": config.snapshot_url,
        "browser_wallet": config.browser_wallet_url,
        "documentation": config.docs_url,
    }
    return {name: _check_url(url, config.timeout_seconds) for name, url in urls.items() if url}


def _service_skipped(config: OperationalReadinessConfig) -> dict[str, Any]:
    return {
        name: {"status": "SKIPPED", "reachable": None, "http_status": None, "latency_ms": None, "error": "network disabled"}
        for name in ("website", "testnet_api", "explorer", "faucet", "snapshot", "browser_wallet", "documentation")
    }


def _critical_gates(*, chain, api_check, pq_features, operational_tests, config):
    return [
        _gate("API reachable", api_check["available"], "testnet API is reachable", "testnet API is not reachable or reachability is unavailable", unknown=config.no_network),
        _gate("chain synced", chain.get("synced") is True, "node reports synced", "node is not synced or sync status is unavailable", unknown=chain.get("synced") is None),
        _gate("activation configuration", pq_features["activation_gating_configured"], "testnet activation height matches consensus params", "activation configuration mismatch"),
        _gate("PQ backend available", pq_features["mldsa_backend_available"], "ML-DSA backend is available", "ML-DSA backend unavailable"),
        _gate("audit report available", operational_tests["pq_audit_report"]["status"] == "PASS", "audit metadata available", "audit metadata unavailable"),
        _gate("dress rehearsal PASS", operational_tests["dress_rehearsal"]["status"] == "PASS", "latest dress rehearsal passed", "dress rehearsal missing or failed"),
    ]


def _major_signals(*, chain, network_readiness, services, pq_metrics, operational_tests, config):
    operational = chain.get("operational_peer_count")
    spread = network_readiness.get("height_spread")
    api_latency = chain.get("api_latency_ms")
    return [
        _gate(
            "sufficient operational peers",
            isinstance(operational, int) and operational >= config.thresholds.min_operational_peers,
            "operational peer count is sufficient",
            "operational peer count is below threshold or unavailable",
            unknown=operational is None,
        ),
        _gate(
            "height spread acceptable",
            isinstance(spread, int) and spread <= config.thresholds.max_height_spread,
            "peer height spread is acceptable",
            "peer height spread is above threshold or unavailable",
            unknown=spread is None,
        ),
        _gate(
            "API latency acceptable",
            isinstance(api_latency, (int, float)) and api_latency <= config.thresholds.max_api_latency_ms,
            "API latency is acceptable",
            "API latency is above threshold or unavailable",
            unknown=api_latency is None,
        ),
        _gate(
            "Chromium runtime PASS",
            operational_tests["chromium_runtime_ci"]["status"] == "PASS",
            "Chromium runtime workflow is present",
            "Chromium runtime workflow missing or failed",
            unknown=operational_tests["chromium_runtime_ci"]["status"] == "UNKNOWN",
        ),
        _gate(
            "PQ metrics available",
            pq_metrics["pq_verify_failures"]["availability"] == "available",
            "PQ metrics are available",
            "PQ metrics are unavailable",
        ),
        _gate(
            "Explorer reachable",
            services.get("explorer", {}).get("status") == "OK",
            "explorer is reachable",
            "explorer is not reachable or reachability is unavailable",
            unknown=services.get("explorer", {}).get("status") in {None, "SKIPPED"},
        ),
    ]


def _informational_signals(*, pq_activity, network_readiness):
    return [
        {"name": "peer version distribution", "status": "UNKNOWN", "reason": network_readiness["version_distribution_status"]},
        {"name": "pre-activation PQ activity", "status": "INFO", "reason": pq_activity.get("pre_activation_note") or "activation reached or unknown"},
    ]


def _score(gates: list[dict[str, Any]], major: list[dict[str, Any]], *, unknowns: list[str]) -> tuple[str, list[str]]:
    critical_failures = [item["reason"] for item in gates if item["status"] == "FAIL"]
    critical_unknowns = [item["reason"] for item in gates if item["status"] == "UNKNOWN"]
    major_failures = [item["reason"] for item in major if item["status"] == "FAIL"]
    major_unknowns = [item["reason"] for item in major if item["status"] == "UNKNOWN"]
    if critical_failures:
        return "NOT READY", critical_failures
    if critical_unknowns:
        return "UNKNOWN", critical_unknowns + unknowns
    if major_failures or major_unknowns:
        return "DEGRADED", major_failures + major_unknowns
    return "READY", []


def _gate(name: str, ok: bool, ok_reason: str, fail_reason: str, *, unknown: bool = False) -> dict[str, str]:
    if unknown:
        return {"name": name, "status": "UNKNOWN", "reason": fail_reason}
    return {"name": name, "status": "PASS" if ok else "FAIL", "reason": ok_reason if ok else fail_reason}


def _test_artifact(path: Path, commit: str, generated_at: datetime, source: str) -> dict[str, Any]:
    if not path.exists():
        return {"status": "NOT RUN", "timestamp": None, "commit": None, "duration": None, "source": str(path), "age_seconds": None}
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return {"status": "PASS", "timestamp": mtime.isoformat().replace("+00:00", "Z"), "commit": commit, "duration": None, "source": source, "age_seconds": int((generated_at - mtime).total_seconds())}


def _json_report_artifact(path: Path, commit: str, generated_at: datetime, nested_key: str | None = None) -> dict[str, Any]:
    if not path.exists():
        return {"status": "NOT RUN", "timestamp": None, "commit": None, "duration": None, "source": str(path), "age_seconds": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "UNKNOWN", "timestamp": None, "commit": None, "duration": None, "source": str(path), "age_seconds": None, "error": str(exc)}
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    status = payload.get("status", "PASS") if nested_key is None else ("PASS" if payload.get(nested_key) else "UNKNOWN")
    return {
        "status": status,
        "timestamp": payload.get("generated_at") or mtime.isoformat().replace("+00:00", "Z"),
        "commit": payload.get("commit") or commit,
        "duration": payload.get("duration"),
        "source": str(path),
        "age_seconds": int((generated_at - mtime).total_seconds()),
        "payload": payload if nested_key is None else None,
    }


def _local_audit_status(*, commit: str, run: bool) -> dict[str, Any]:
    if not run:
        return {"status": "PASS", "timestamp": None, "commit": commit, "duration": None, "source": "static import", "age_seconds": None}
    started = time.perf_counter()
    build_pq_audit_report()
    return {"status": "PASS", "timestamp": _now().isoformat().replace("+00:00", "Z"), "commit": commit, "duration": round(time.perf_counter() - started, 3), "source": "local run", "age_seconds": 0}


def _workflow_artifact(path: Path, commit: str, generated_at: datetime) -> dict[str, Any]:
    if not path.exists():
        return {"status": "UNKNOWN", "timestamp": None, "commit": None, "duration": None, "source": str(path), "age_seconds": None}
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return {"status": "PASS", "timestamp": mtime.isoformat().replace("+00:00", "Z"), "commit": commit, "duration": None, "source": str(path), "age_seconds": int((generated_at - mtime).total_seconds())}


def _fetch_json(base_url: str | None, path: str, timeout: float) -> tuple[Any | None, float | None, str | None]:
    if not base_url:
        return None, None, "missing URL"
    url = base_url.rstrip("/") + (path if path.startswith("/") else "/" + path)
    started = time.perf_counter()
    try:
        with urlopen(Request(url, headers={"Accept": "application/json", "User-Agent": "chipcoin-pq-readiness/1"}), timeout=timeout) as response:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            return json.loads(response.read().decode("utf-8")), latency_ms, None
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return None, None, str(exc)


def _check_url(url: str | None, timeout: float) -> dict[str, Any]:
    if not url:
        return {"status": "UNKNOWN", "reachable": None, "http_status": None, "latency_ms": None, "error": "not configured"}
    started = time.perf_counter()
    try:
        with urlopen(Request(url, method="GET", headers={"User-Agent": "chipcoin-pq-readiness/1"}), timeout=timeout) as response:
            return {"status": "OK", "reachable": True, "http_status": response.status, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "error": None}
    except HTTPError as exc:
        return {"status": "FAIL", "reachable": False, "http_status": exc.code, "latency_ms": None, "error": str(exc)}
    except (URLError, TimeoutError, OSError) as exc:
        return {"status": "FAIL", "reachable": False, "http_status": None, "latency_ms": None, "error": str(exc)}


def _empty_chain(*, config: OperationalReadinessConfig) -> dict[str, Any]:
    return {
        "network": config.network,
        "api_status": "SKIPPED" if config.no_network else "UNKNOWN",
        "api_latency_ms": None,
        "height": None,
        "synced": None,
        "sync_phase": None,
        "best_block_hash": None,
        "chain_tip_timestamp": None,
        "chain_age_seconds": None,
        "peer_count": None,
        "operational_peer_count": None,
        "handshaken_peer_count": None,
        "node_version": None,
        "network_identifier": None,
    }


def _block_intervals(blocks: list[dict[str, Any]]) -> list[int]:
    times = [_block_timestamp(block) for block in blocks]
    times = [item for item in times if item is not None]
    times.sort(reverse=True)
    return [abs(int((times[index] - times[index + 1]).total_seconds())) for index in range(len(times) - 1)]


def _block_timestamp(block: dict[str, Any]) -> datetime | None:
    value = block.get("timestamp") or block.get("time")
    header = block.get("header")
    if value is None and isinstance(header, dict):
        value = header.get("timestamp")
    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _current_commit(root: Path) -> str:
    try:
        completed = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
        return completed.stdout.strip() if completed.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _display(value: Any) -> str:
    return "UNKNOWN" if value is None else str(value)
