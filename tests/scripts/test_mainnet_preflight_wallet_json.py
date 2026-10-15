from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re

import pytest


SCRIPT = Path(__file__).parents[2] / "scripts" / "mainnet_preflight_wallet_json.py"
SPEC = importlib.util.spec_from_file_location("mainnet_preflight_wallet_json", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


VALID_WALLET = {
    "address": "CHCQtestwalletaddress",
    "address_kind": "pq",
    "scheme_id": 10,
    "scheme_name": "mldsa44",
}


@pytest.mark.parametrize(
    ("stdout", "stderr"),
    [
        (json.dumps(VALID_WALLET), ""),
        (f"Container chipcoin-node-run Creating\n{json.dumps(VALID_WALLET)}\n", ""),
        (f"{json.dumps(VALID_WALLET)}\nContainer chipcoin-node-run Removed\n", ""),
        (json.dumps(VALID_WALLET), "Container lifecycle noise\nwarning: harmless\n"),
    ],
)
def test_valid_wallet_payload_is_extracted_from_noisy_output(stdout: str, stderr: str) -> None:
    assert MODULE.validate_wallet_output(stdout, stderr, 0, "wallet") == VALID_WALLET


@pytest.mark.parametrize(
    ("stdout", "stderr", "exit_code", "message"),
    [
        ("Container started\n", "", 0, "no JSON payload"),
        ('prefix\n{"address":"CHCQ', "", 0, "malformed or truncated"),
        ('{"status":"ok"}', "", 0, "unexpected schema"),
        (
            json.dumps({**VALID_WALLET, "address_kind": "legacy"}),
            "",
            0,
            "address_kind is not pq",
        ),
        (json.dumps({**VALID_WALLET, "scheme_id": 0}), "", 0, "scheme_id is not 10"),
        (
            json.dumps({**VALID_WALLET, "scheme_name": "secp256k1-ecdsa"}),
            "",
            0,
            "scheme_name is not mldsa44",
        ),
        (json.dumps({**VALID_WALLET, "address": "CHCClegacy"}), "", 0, "address does not start with CHCQ"),
        (json.dumps(VALID_WALLET), "wallet rejected", 7, "wallet command failed (exit 7)"),
        ("", "Cannot connect to the Docker daemon", 1, "Docker/Compose execution failure (exit 1)"),
    ],
)
def test_invalid_wallet_command_output_is_rejected_distinctly(
    stdout: str,
    stderr: str,
    exit_code: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        MODULE.validate_wallet_output(stdout, stderr, exit_code, "wallet")


def test_wallet_schema_requires_typed_fields() -> None:
    payload = {**VALID_WALLET, "scheme_id": "10"}
    with pytest.raises(ValueError, match="unexpected schema"):
        MODULE.validate_wallet_output(json.dumps(payload), "", 0, "wallet")


def test_multiple_wallet_payloads_are_rejected() -> None:
    stdout = f"{json.dumps(VALID_WALLET)}\n{json.dumps(VALID_WALLET)}"
    with pytest.raises(ValueError, match="multiple wallet JSON payloads"):
        MODULE.validate_wallet_output(stdout, "", 0, "wallet")
