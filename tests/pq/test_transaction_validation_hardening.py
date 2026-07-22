from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from chipcoin.consensus.models import OutPoint, Transaction, TxInput, TxOutput
from chipcoin.crypto.pq import SIG_SCHEME_ML_DSA_44, SIG_SCHEME_ML_DSA_65_RESERVED
from chipcoin.interfaces import cli as cli_module
from chipcoin.node.service import NodeService
from chipcoin.pq.policy import (
    DEFAULT_PQ_POLICY_LIMITS,
    MAX_PQ_INPUTS,
    ML_DSA_44_PUBLIC_KEY_SIZE,
    ML_DSA_44_SIGNATURE_SIZE,
    enforce_pq_mempool_precheck,
    pq_signature_cost,
    pq_sigop_count,
)
from chipcoin.pq.readiness import make_pq_readiness_params, mine_to_height
from chipcoin.wallet.signer import TransactionSigner, wallet_key_from_mldsa44_seed
from tests.helpers import put_wallet_utxo, spend_candidates_for_wallet, wallet_key


def _make_service(database_path: Path) -> NodeService:
    timestamps = iter(range(1_900_000_000, 1_900_001_000))
    return NodeService.open_sqlite(
        database_path,
        network="testnet",
        params=make_pq_readiness_params(activation_height=20),
        time_provider=lambda: next(timestamps),
    )


def _pq_spend(service: NodeService, *, prefix: str = "70") -> Transaction:
    owner = wallet_key_from_mldsa44_seed(bytes(range(32)))
    outpoint = OutPoint(txid=prefix * 32, index=0)
    put_wallet_utxo(service, outpoint, value=100_000, owner=owner)
    return TransactionSigner(owner).build_signed_transaction(
        spend_candidates=spend_candidates_for_wallet(outpoint, value=100_000, owner=owner),
        recipient=wallet_key(1).address,
        amount_chipbits=99_000,
        fee_chipbits=1_000,
        metadata={"kind": "payment", "purpose": "pq-hardening"},
        network="testnet",
    ).transaction


def test_pq_precheck_rejects_bad_lengths_before_verify() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "node.sqlite3")
        mine_to_height(service, 19, wallet_key(2).address)
        tx = _pq_spend(service)
        malformed = replace(
            tx,
            inputs=(replace(tx.inputs[0], signature=tx.inputs[0].signature[:-1]),),
        )

        with pytest.raises(Exception) as excinfo:
            service.receive_transaction(malformed)

        assert "wrong size for ML-DSA-44" in str(excinfo.value)
        metrics = service.mempool.pq_metrics_snapshot()
        assert metrics["pq_malformed"] == 1
        assert metrics["pq_tx_rejected"] == 1
        assert metrics["pq_verify_count"] == 0


def test_pq_precheck_rejects_reserved_scheme_and_wrong_version() -> None:
    public_key = b"\x02" * ML_DSA_44_PUBLIC_KEY_SIZE
    signature = b"\x03" * ML_DSA_44_SIGNATURE_SIZE
    base_input = TxInput(
        previous_output=OutPoint(txid="71" * 32, index=0),
        public_key=public_key,
        signature=signature,
        sig_scheme_id=SIG_SCHEME_ML_DSA_44,
    )
    tx = Transaction(
        version=1,
        inputs=(base_input,),
        outputs=(TxOutput(value=99_000, recipient=wallet_key(1).address),),
        metadata={"kind": "payment"},
    )

    with pytest.raises(Exception, match="version 2"):
        enforce_pq_mempool_precheck(tx)

    reserved = replace(tx, version=2, inputs=(replace(base_input, sig_scheme_id=SIG_SCHEME_ML_DSA_65_RESERVED),))
    with pytest.raises(Exception, match="non-verification-capable"):
        enforce_pq_mempool_precheck(reserved)


def test_pq_precheck_enforces_input_and_sigops_limits() -> None:
    public_key = b"\x02" * ML_DSA_44_PUBLIC_KEY_SIZE
    signature = b"\x03" * ML_DSA_44_SIGNATURE_SIZE
    inputs = tuple(
        TxInput(
            previous_output=OutPoint(txid=f"{index + 1:064x}", index=0),
            public_key=public_key,
            signature=signature,
            sig_scheme_id=SIG_SCHEME_ML_DSA_44,
        )
        for index in range(MAX_PQ_INPUTS + 1)
    )
    tx = Transaction(
        version=2,
        inputs=inputs,
        outputs=(TxOutput(value=99_000, recipient=wallet_key(1).address),),
        metadata={"kind": "payment"},
    )

    assert pq_sigop_count(tx) == MAX_PQ_INPUTS + 1
    assert pq_signature_cost(tx, DEFAULT_PQ_POLICY_LIMITS) > DEFAULT_PQ_POLICY_LIMITS.max_pq_signature_cost_per_tx
    with pytest.raises(Exception, match="PQ input-count policy"):
        enforce_pq_mempool_precheck(tx)


def test_valid_pq_spend_updates_verify_and_accept_metrics() -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "node.sqlite3")
        mine_to_height(service, 19, wallet_key(2).address)
        tx = _pq_spend(service)

        accepted = service.receive_transaction(tx)

        assert accepted.transaction.txid() == tx.txid()
        metrics = service.mempool.pq_metrics_snapshot()
        assert metrics["pq_verify_count"] == 1
        assert metrics["pq_verify_failures"] == 0
        assert metrics["pq_tx_accepted"] == 1
        assert metrics["pq_verify_duration_seconds_total"] > 0


def test_pq_benchmark_cli_quick_json_reports_required_measurements(capsys) -> None:
    code = cli_module.main(["pq-benchmark", "--quick", "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    operations = {row["operation"] for row in payload["measurements"]}
    assert {
        "ecdsa_keygen",
        "ecdsa_sign",
        "ecdsa_verify",
        "ecdsa_verify_100",
        "ecdsa_verify_1000",
        "mldsa44_keygen",
        "mldsa44_sign",
        "mldsa44_verify",
        "mldsa44_verify_100",
        "mldsa44_verify_1000",
    }.issubset(operations)
    assert payload["digest_bytes"] == 32
    assert payload["resources"]["process_cpu_seconds"] >= 0
    assert payload["mldsa44_public_key_bytes"] == ML_DSA_44_PUBLIC_KEY_SIZE
    assert payload["mldsa44_signature_bytes"] == ML_DSA_44_SIGNATURE_SIZE
