"""CLI entry point for the Chipcoin PQ dress rehearsal."""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from ..pq.dress_rehearsal import (
    DEFAULT_DRESS_REHEARSAL_ACTIVATION_HEIGHT,
    DressRehearsalError,
    DressRehearsalResult,
    run_dress_rehearsal,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_dress_rehearsal(
            activation_height=args.activation_height,
            output_json=Path(args.output_json),
            output_markdown=Path(args.output_markdown),
            skip_subprocess_checks=args.skip_subprocess_checks,
            skip_browser_checks=args.skip_browser_checks,
        )
    except DressRehearsalError as exc:
        print("POST-QUANTUM DRESS REHEARSAL")
        print()
        print("FAIL")
        print(f"failed_stage: {exc.stage}")
        print(f"reason: {exc.reason}")
        if args.verbose:
            traceback.print_exception(exc)
        return 1

    if args.json:
        print(json.dumps(result.to_json_payload(), indent=2, sort_keys=True))
    else:
        print_report(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local Chipcoin Post-Quantum testnet dress rehearsal.")
    parser.add_argument("--activation-height", type=int, default=DEFAULT_DRESS_REHEARSAL_ACTIVATION_HEIGHT)
    parser.add_argument("--output-json", default="pq-dress-rehearsal.json")
    parser.add_argument("--output-markdown", default="docs/post-quantum-dress-rehearsal-report.md")
    parser.add_argument("--skip-subprocess-checks", action="store_true", help="skip nested pytest checks; intended for fast command tests")
    parser.add_argument("--skip-browser-checks", action="store_true", help="skip npm browser checks; intended for constrained environments")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def print_report(result: DressRehearsalResult) -> None:
    print("POST-QUANTUM DRESS REHEARSAL")
    print()
    print(result.status)
    print()
    print(f"activation_height: {result.activation_height}")
    print(f"legacy_blocks: {result.legacy_blocks}")
    print(f"pq_blocks: {result.pq_blocks}")
    print(f"legacy_transactions: {result.legacy_transactions}")
    print(f"pq_transactions: {result.pq_transactions}")
    print(f"verify_count: {result.verify_count}")
    print(f"verify_failures: {result.verify_failures}")
    print(f"json_report: {result.json_report_path}")
    print(f"markdown_report: {result.markdown_report_path}")


if __name__ == "__main__":
    raise SystemExit(main())
