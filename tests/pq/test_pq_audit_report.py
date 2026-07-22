from __future__ import annotations

import json

from chipcoin.consensus.pq_activation import PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT, PQ_TRANSACTION_VERSION
from chipcoin.crypto.addresses import PQ_ADDRESS_PREFIX, PQ_ADDRESS_VERSION
from chipcoin.crypto.pq import SIG_SCHEME_ML_DSA_44
from chipcoin.crypto.pq.mldsa import ML_DSA_44_PUBLIC_KEY_SIZE, ML_DSA_44_SIGNATURE_SIZE
from chipcoin.interfaces import cli as cli_module
from chipcoin.pq.policy import DEFAULT_PQ_POLICY_LIMITS
from chipcoin.tools.pq_audit_report import build_report


def test_pq_audit_report_uses_runtime_constants() -> None:
    report = build_report()

    assert report["scheme"]["mldsa44_scheme_id"] == SIG_SCHEME_ML_DSA_44
    assert report["activation"]["testnet"] == PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT == 30_000
    assert report["address"]["pq_prefix"] == PQ_ADDRESS_PREFIX
    assert report["address"]["pq_version"] == PQ_ADDRESS_VERSION
    assert report["transaction"]["pq_transaction_version"] == PQ_TRANSACTION_VERSION
    assert report["mldsa44"]["public_key_bytes"] == ML_DSA_44_PUBLIC_KEY_SIZE
    assert report["mldsa44"]["signature_bytes"] == ML_DSA_44_SIGNATURE_SIZE
    assert report["policy"]["max_pq_inputs"] == DEFAULT_PQ_POLICY_LIMITS.max_pq_inputs
    assert report["artifacts"]["readiness_suite"] is True
    assert report["artifacts"]["smoke_command"] is True
    assert report["artifacts"]["benchmark_command"] is True


def test_pq_audit_report_cli_json(capsys) -> None:
    code = cli_module.main(["pq-audit-report", "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scheme"]["mldsa44_scheme_id"] == SIG_SCHEME_ML_DSA_44
    assert payload["activation"]["testnet"] == 30_000
