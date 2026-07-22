"""Static Post-Quantum audit report for release and activation checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..consensus.pq_activation import (
    PQ_SUPPORT_DEVNET_ACTIVATION_HEIGHT,
    PQ_SUPPORT_MAINNET_ACTIVATION_HEIGHT,
    PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT,
    PQ_TRANSACTION_VERSION,
)
from ..crypto.addresses import PQ_ADDRESS_PREFIX, PQ_ADDRESS_VERSION, PQ_PUBLIC_KEY_COMMITMENT_SIZE
from ..crypto.pq import (
    SIG_SCHEME_FALCON_RESERVED,
    SIG_SCHEME_LEGACY_ECDSA,
    SIG_SCHEME_ML_DSA_44,
    SIG_SCHEME_ML_DSA_65_RESERVED,
    SIG_SCHEME_SPHINCS_RESERVED,
    get_signature_scheme,
)
from ..crypto.pq.mldsa import (
    ML_DSA_44_PUBLIC_KEY_SIZE,
    ML_DSA_44_SIGNATURE_SIZE,
    ML_DSA_SEED_SIZE,
    mldsa44_backend_available,
    mldsa44_backend_info,
)
from ..pq.policy import (
    CHIPCOIN_SIGNATURE_DIGEST_BYTES,
    DEFAULT_PQ_POLICY_LIMITS,
    MAX_PQ_PUBLIC_KEY_SIZE,
    MAX_PQ_SIGNATURE_SIZE,
    MAX_PQ_SIGOPS_PER_BLOCK,
    MAX_PQ_SIGOPS_PER_TX,
    MAX_PQ_TX_SIZE,
)


ML_DSA_44_PRIVATE_KEY_SIZE = 2560


def build_report(*, repo_root: Path | None = None) -> dict[str, Any]:
    """Return a static machine-readable PQ audit report."""

    root = Path.cwd() if repo_root is None else repo_root
    limits = DEFAULT_PQ_POLICY_LIMITS
    backend_available = mldsa44_backend_available()
    backend_info: dict[str, object] | None = None
    if backend_available:
        backend_info = mldsa44_backend_info()
    return {
        "scheme": {
            "legacy_ecdsa_scheme_id": SIG_SCHEME_LEGACY_ECDSA,
            "mldsa44_scheme_id": SIG_SCHEME_ML_DSA_44,
            "mldsa44_scheme_name": get_signature_scheme(SIG_SCHEME_ML_DSA_44).name,
            "reserved_scheme_ids": {
                "mldsa65": SIG_SCHEME_ML_DSA_65_RESERVED,
                "falcon": SIG_SCHEME_FALCON_RESERVED,
                "sphincs_plus": SIG_SCHEME_SPHINCS_RESERVED,
            },
        },
        "activation": {
            "mainnet": PQ_SUPPORT_MAINNET_ACTIVATION_HEIGHT,
            "devnet": PQ_SUPPORT_DEVNET_ACTIVATION_HEIGHT,
            "testnet": PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT,
            "test_override_module": "chipcoin.pq.readiness.make_pq_readiness_params",
        },
        "address": {
            "pq_prefix": PQ_ADDRESS_PREFIX,
            "pq_version": PQ_ADDRESS_VERSION,
            "pq_commitment_bytes": PQ_PUBLIC_KEY_COMMITMENT_SIZE,
        },
        "transaction": {
            "pq_transaction_version": PQ_TRANSACTION_VERSION,
            "digest_bytes": CHIPCOIN_SIGNATURE_DIGEST_BYTES,
            "domain_separator_template": "chipcoin:tx-signature:v2:<network>",
        },
        "mldsa44": {
            "seed_bytes": ML_DSA_SEED_SIZE,
            "public_key_bytes": ML_DSA_44_PUBLIC_KEY_SIZE,
            "private_key_bytes": ML_DSA_44_PRIVATE_KEY_SIZE,
            "signature_bytes": ML_DSA_44_SIGNATURE_SIZE,
            "backend_available": backend_available,
            "backend_info": backend_info,
        },
        "policy": {
            "max_pq_signature_size": MAX_PQ_SIGNATURE_SIZE,
            "max_pq_public_key_size": MAX_PQ_PUBLIC_KEY_SIZE,
            "max_pq_inputs": limits.max_pq_inputs,
            "max_pq_tx_size": MAX_PQ_TX_SIZE,
            "max_pq_sigops_per_tx": MAX_PQ_SIGOPS_PER_TX,
            "max_pq_sigops_per_block": MAX_PQ_SIGOPS_PER_BLOCK,
            "pq_sigop_cost_mldsa44": limits.pq_sigop_cost_mldsa44,
            "max_pq_signature_cost_per_tx": limits.max_pq_signature_cost_per_tx,
            "max_pq_signature_cost_per_block": limits.max_pq_signature_cost_per_block,
        },
        "artifacts": _artifact_status(root),
        "commands": {
            "readiness_pytest": "python -m pytest tests/pq/test_activation_readiness.py -q",
            "pq_smoke": "python -m chipcoin.tools.pq_smoke",
            "pq_benchmark": "python -m chipcoin.tools.pq_benchmark",
            "pq_audit_report": "python -m chipcoin.tools.pq_audit_report --json",
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Print the static PQ audit report."""

    parser = argparse.ArgumentParser(description="Print static Chipcoin Post-Quantum audit metadata.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)
    report = build_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    print("CHIPCOIN PQ AUDIT REPORT")
    print()
    print(f"scheme: {report['scheme']['mldsa44_scheme_name']} id={report['scheme']['mldsa44_scheme_id']}")
    print(f"testnet_activation_height: {report['activation']['testnet']}")
    print(f"pq_address: prefix={report['address']['pq_prefix']} version={report['address']['pq_version']}")
    print(f"transaction_version: {report['transaction']['pq_transaction_version']}")
    print(f"digest_bytes: {report['transaction']['digest_bytes']}")
    print(f"mldsa44_public_key_bytes: {report['mldsa44']['public_key_bytes']}")
    print(f"mldsa44_private_key_bytes: {report['mldsa44']['private_key_bytes']}")
    print(f"mldsa44_signature_bytes: {report['mldsa44']['signature_bytes']}")
    print(f"backend_available: {report['mldsa44']['backend_available']}")
    print()
    print("policy:")
    for key, value in report["policy"].items():
        print(f"  {key}: {value}")
    print()
    print("artifacts:")
    for key, value in report["artifacts"].items():
        print(f"  {key}: {value}")
    return 0


def _artifact_status(root: Path) -> dict[str, bool]:
    return {
        "pq_vector_fixture": (root / "apps/browser-wallet/tests/fixtures/pq-vector-1.json").exists(),
        "mldsa44_browser_vector_fixture": (root / "apps/browser-wallet/tests/fixtures/mldsa44-browser-vector-1.json").exists(),
        "chromium_workflow": (root / ".github/workflows/browser-pq-chromium.yml").exists(),
        "readiness_suite": (root / "tests/pq/test_activation_readiness.py").exists(),
        "smoke_command": (root / "src/chipcoin/tools/pq_smoke.py").exists(),
        "benchmark_command": (root / "src/chipcoin/tools/pq_benchmark.py").exists(),
    }


if __name__ == "__main__":
    raise SystemExit(main())
