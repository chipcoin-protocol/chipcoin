"""Command-line entry point for the operational PQ activation smoke test."""

from __future__ import annotations

import argparse
import json
import sys
import traceback

from ..pq.readiness import DEFAULT_PQ_SMOKE_ACTIVATION_HEIGHT, PqSmokeError, PqSmokeResult, run_pq_smoke


def main(argv: list[str] | None = None) -> int:
    """Run the PQ smoke command."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_pq_smoke(activation_height=args.activation_height, keep_state=args.keep_state)
    except KeyboardInterrupt:
        return _print_failure("interrupted", "keyboard interrupt", json_output=args.json, verbose=args.verbose)
    except PqSmokeError as exc:
        return _print_failure(exc.stage, exc.reason, json_output=args.json, verbose=args.verbose, exc=exc)
    except Exception as exc:  # noqa: BLE001 - command boundary must not expose tracebacks by default
        return _print_failure("unexpected", str(exc), json_output=args.json, verbose=args.verbose, exc=exc)

    if args.json:
        print(json.dumps(result.to_json_payload(), indent=2, sort_keys=True))
    else:
        print_report(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local Chipcoin post-quantum activation smoke test.")
    parser.add_argument(
        "--activation-height",
        type=int,
        default=DEFAULT_PQ_SMOKE_ACTIVATION_HEIGHT,
        help=f"test-only local PQ activation height (default: {DEFAULT_PQ_SMOKE_ACTIVATION_HEIGHT})",
    )
    parser.add_argument("--keep-state", action="store_true", help="preserve the temporary state directory for debugging")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable JSON result")
    parser.add_argument("--verbose", action="store_true", help="print traceback details on failure")
    return parser


def print_report(result: PqSmokeResult) -> None:
    print("========================================")
    print("CHIPCOIN PQ SMOKE TEST")
    print("========================================")
    print()
    for stage in result.stages:
        print(f"{stage.status}  {stage.label}")
    print()
    print("READY")
    print()
    print(f"activation height: {result.activation_height}")
    print(f"final local height: {result.final_local_height}")
    print(f"PQ scheme: {result.pq_scheme}")
    if result.state_preserved:
        print(f"state path: {result.state_path}")
    print()
    print("========================================")


def _print_failure(
    stage: str,
    reason: str,
    *,
    json_output: bool,
    verbose: bool,
    exc: BaseException | None = None,
) -> int:
    if json_output:
        print(json.dumps({"ready": False, "failed_stage": stage, "reason": reason}, indent=2, sort_keys=True))
    else:
        print(f"FAIL  {stage}")
        print(f"reason: {reason}")
    if verbose and exc is not None:
        traceback.print_exception(exc, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
