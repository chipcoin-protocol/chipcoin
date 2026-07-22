"""CLI entry point for PQ operational readiness dashboard."""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from ..pq.operational_readiness import (
    DEFAULT_OUTPUT_DIR,
    OperationalReadinessConfig,
    build_config,
    collect_operational_readiness,
    render_cli,
    render_html,
    render_markdown,
    write_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = build_config(
            config_path=Path(args.config) if args.config else None,
            api_url=args.api_url,
            timeout_seconds=args.timeout,
            no_network=args.no_network,
            strict=args.strict,
            compact=args.compact,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            block_interval_window=args.block_interval_window,
        )
        result = collect_operational_readiness(config=config, run_local_checks=args.run_local_checks)
        output_dir = Path(args.output_dir) if args.output_dir else None
        write_outputs(
            result,
            output_dir=output_dir,
            output_json=Path(args.output) if args.output else None,
            output_html=Path(args.html) if args.html else None,
            output_markdown=Path(args.markdown) if args.markdown else None,
        )
    except Exception as exc:  # noqa: BLE001 - command boundary reports concise errors
        print("POST-QUANTUM OPERATIONAL READINESS")
        print()
        print("Status: UNKNOWN")
        print(f"reason: {exc}")
        if args.verbose:
            traceback.print_exception(exc)
        return 4

    if args.json:
        print(json.dumps(result.payload, indent=2, sort_keys=True))
    elif args.html_stdout:
        print(render_html(result))
    elif args.markdown_stdout:
        print(render_markdown(result), end="")
    else:
        print(render_cli(result, compact=args.compact))
    return result.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the read-only Chipcoin PQ operational readiness dashboard.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--html", help="Write standalone HTML dashboard to PATH.")
    parser.add_argument("--output", help="Write JSON report to PATH.")
    parser.add_argument("--markdown", help="Write Markdown report to PATH.")
    parser.add_argument("--output-dir", help=f"Write latest/history reports under DIR, for example {DEFAULT_OUTPUT_DIR}.")
    parser.add_argument("--api-url", help="Readonly testnet API base URL.")
    parser.add_argument("--timeout", type=float, help="Network timeout in seconds.")
    parser.add_argument("--no-network", action="store_true", help="Disable all network checks and report unavailable data as UNKNOWN.")
    parser.add_argument("--strict", action="store_true", help="Use strict scoring; reserved for operational configs.")
    parser.add_argument("--compact", action="store_true", help="Print one-line output for cron.")
    parser.add_argument("--config", help="Optional TOML config path.")
    parser.add_argument("--block-interval-window", type=int, help="Recent block window used for ETA.")
    parser.add_argument("--run-local-checks", action="store_true", help="Run light local checks only; no full tests, builds or benchmarks.")
    parser.add_argument("--html-stdout", action="store_true", help="Print HTML to stdout.")
    parser.add_argument("--markdown-stdout", action="store_true", help="Print Markdown to stdout.")
    parser.add_argument("--verbose", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
