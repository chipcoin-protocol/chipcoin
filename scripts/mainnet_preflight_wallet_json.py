#!/usr/bin/env python3
"""Extract and validate one wallet-address JSON payload without leaking secrets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


EXPECTED_KEYS = {"address", "address_kind", "scheme_id", "scheme_name"}
DOCKER_FAILURE_RE = re.compile(
    r"(docker daemon|docker compose|cannot connect|permission denied.*docker|container .* (creating|failed)|network .* failed)",
    re.IGNORECASE,
)


def _json_objects(text: str) -> tuple[list[Any], bool]:
    decoder = json.JSONDecoder()
    objects: list[Any] = []
    saw_open_brace = "{" in text
    for match in re.finditer(r"\{", text):
        try:
            value, _end = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        objects.append(value)
    return objects, saw_open_brace


def validate_wallet_output(stdout: str, stderr: str, exit_code: int, label: str) -> dict[str, Any]:
    if exit_code != 0:
        if DOCKER_FAILURE_RE.search(stderr):
            raise ValueError(f"{label}: Docker/Compose execution failure (exit {exit_code})")
        raise ValueError(f"{label}: wallet command failed (exit {exit_code})")

    objects, saw_open_brace = _json_objects(stdout)
    payloads = [value for value in objects if isinstance(value, dict) and EXPECTED_KEYS <= set(value)]
    if not payloads:
        if objects:
            raise ValueError(f"{label}: wallet JSON has an unexpected schema")
        if saw_open_brace:
            raise ValueError(f"{label}: malformed or truncated wallet JSON")
        raise ValueError(f"{label}: wallet command returned no JSON payload")
    if len(payloads) != 1:
        raise ValueError(f"{label}: wallet command returned multiple wallet JSON payloads")

    payload = payloads[0]
    if not isinstance(payload.get("address"), str) \
            or not isinstance(payload.get("address_kind"), str) \
            or not isinstance(payload.get("scheme_id"), int) \
            or not isinstance(payload.get("scheme_name"), str):
        raise ValueError(f"{label}: wallet JSON has an unexpected schema")
    if payload["address_kind"] != "pq":
        raise ValueError(f"{label}: address_kind is not pq")
    if payload["scheme_id"] != 10:
        raise ValueError(f"{label}: scheme_id is not 10")
    if payload["scheme_name"] != "mldsa44":
        raise ValueError(f"{label}: scheme_name is not mldsa44")
    if not payload["address"].startswith("CHCQ"):
        raise ValueError(f"{label}: address does not start with CHCQ")
    return {key: payload[key] for key in sorted(EXPECTED_KEYS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdout-file", required=True)
    parser.add_argument("--stderr-file", required=True)
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    try:
        payload = validate_wallet_output(
            Path(args.stdout_file).read_text(encoding="utf-8", errors="replace"),
            Path(args.stderr_file).read_text(encoding="utf-8", errors="replace"),
            args.exit_code,
            args.label,
        )
    except ValueError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
