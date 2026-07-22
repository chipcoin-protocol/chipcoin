"""End-to-end local Post-Quantum dress rehearsal workflow."""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

from ..consensus.models import Block, OutPoint, Transaction
from ..consensus.serialization import deserialize_transaction, serialize_transaction
from ..consensus.validation import ValidationError
from ..crypto.addresses import parse_address
from ..crypto.pq import SIG_SCHEME_ML_DSA_44, SIG_SCHEME_ML_DSA_65_RESERVED
from ..crypto.pq.mldsa import ML_DSA_44_PUBLIC_KEY_SIZE, ML_DSA_44_SIGNATURE_SIZE
from ..interfaces.http_api import HttpApiApp
from ..node.service import NodeService
from ..node.sync import SyncManager
from ..pq.readiness import (
    PqSmokeError,
    call_api_json,
    make_pq_readiness_params,
    mine_easy_block,
    mine_next_block,
    mine_to_height,
    run_pq_smoke,
)
from ..tools.pq_audit_report import build_report as build_pq_audit_report
from ..tools.pq_benchmark import run_benchmark
from ..wallet.models import SpendCandidate, WalletKey
from ..wallet.signer import TransactionSigner, wallet_key_from_mldsa44_seed, wallet_key_from_private_key


DEFAULT_DRESS_REHEARSAL_ACTIVATION_HEIGHT = 8


@dataclass(frozen=True)
class DressCheck:
    """One dress rehearsal check result."""

    label: str
    status: str = "PASS"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DressRehearsalResult:
    """Structured dress rehearsal result."""

    status: str
    activation_height: int
    legacy_blocks: int
    pq_blocks: int
    legacy_transactions: int
    pq_transactions: int
    verify_count: int
    verify_failures: int
    benchmark: dict[str, Any]
    readiness: dict[str, Any]
    smoke: dict[str, Any]
    audit: dict[str, Any]
    warnings: list[str]
    errors: list[str]
    duration_seconds: float
    timeline: list[dict[str, Any]]
    checks: list[dict[str, Any]]
    markdown_report_path: str
    json_report_path: str

    def to_json_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "activation_height": self.activation_height,
            "legacy_blocks": self.legacy_blocks,
            "pq_blocks": self.pq_blocks,
            "legacy_transactions": self.legacy_transactions,
            "pq_transactions": self.pq_transactions,
            "verify_count": self.verify_count,
            "verify_failures": self.verify_failures,
            "benchmark": self.benchmark,
            "readiness": self.readiness,
            "smoke": self.smoke,
            "audit": self.audit,
            "warnings": self.warnings,
            "errors": self.errors,
            "duration": round(self.duration_seconds, 3),
            "timeline": self.timeline,
            "checks": self.checks,
            "markdown_report_path": self.markdown_report_path,
            "json_report_path": self.json_report_path,
        }


class DressRehearsalError(RuntimeError):
    """Operational failure with user-facing stage context."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = reason


def run_dress_rehearsal(
    *,
    activation_height: int = DEFAULT_DRESS_REHEARSAL_ACTIVATION_HEIGHT,
    output_json: Path = Path("pq-dress-rehearsal.json"),
    output_markdown: Path = Path("docs/post-quantum-dress-rehearsal-report.md"),
    skip_subprocess_checks: bool = False,
    skip_browser_checks: bool = False,
) -> DressRehearsalResult:
    """Run the full local PQ activation dress rehearsal."""

    started_at = time.perf_counter()
    checks: list[DressCheck] = []
    timeline: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    benchmark: dict[str, Any] = {}
    readiness: dict[str, Any] = {}
    smoke: dict[str, Any] = {}
    audit: dict[str, Any] = {}

    def stage(label: str, fn: Callable[[], dict[str, Any] | None]) -> None:
        try:
            details = fn() or {}
            checks.append(DressCheck(label=label, details=details))
            timeline.append({"stage": label, "status": "PASS", **details})
        except DressRehearsalError:
            raise
        except Exception as exc:  # noqa: BLE001 - command boundary reports concise stage failures
            raise DressRehearsalError(label, str(exc)) from exc

    with TemporaryDirectory(prefix="chipcoin-pq-dress-") as tempdir:
        state_dir = Path(tempdir)
        try:
            params = make_pq_readiness_params(activation_height=activation_height)
        except PqSmokeError as exc:
            raise DressRehearsalError("configuration", exc.reason) from exc
        node = _make_service(state_dir / "node.sqlite3", params=params, start_time=1_910_000_000)
        api = HttpApiApp(node)
        miner = _legacy_wallet(0)
        legacy_a = _legacy_wallet(1)
        legacy_b = _legacy_wallet(2)
        pq_a = wallet_key_from_mldsa44_seed(bytes(range(32)))
        pq_b = wallet_key_from_mldsa44_seed(bytes(range(32, 64)))
        counters = {
            "legacy_blocks": 0,
            "pq_blocks": 0,
            "legacy_transactions": 0,
            "pq_transactions": 0,
        }
        utxos: dict[str, tuple[OutPoint, int, WalletKey]] = {}

        def remember_utxo(name: str, tx: Transaction, index: int, owner: WalletKey) -> None:
            utxos[name] = (OutPoint(txid=tx.txid(), index=index), int(tx.outputs[index].value), owner)

        def mine(label: str) -> Block:
            block = mine_next_block(node, miner.address)
            has_pq = any(_is_pq_transaction(tx) for tx in block.transactions[1:])
            if has_pq:
                counters["pq_blocks"] += 1
            else:
                counters["legacy_blocks"] += 1
            timeline.append(
                {
                    "stage": label,
                    "height": node.chain_tip().height if node.chain_tip() else -1,
                    "block_hash": block.block_hash(),
                    "transactions": len(block.transactions),
                    "pq": has_pq,
                }
            )
            return block

        def bootstrap() -> dict[str, Any]:
            block = mine("bootstrap genesis/local funding")
            remember_utxo("miner_coinbase_0", block.transactions[0], 0, miner)
            return {
                "genesis_like_height": 0,
                "miner": miner.address,
                "legacy_wallet": legacy_a.address,
                "pq_wallet": pq_a.address,
                "api": "HttpApiApp",
            }

        stage("bootstrap", bootstrap)

        def legacy_phase() -> dict[str, Any]:
            outpoint, value, owner = utxos.pop("miner_coinbase_0")
            tx = _payment(owner, outpoint, value=value, recipient=legacy_a.address, amount=1_000_000, fee=1_000)
            node.receive_transaction(tx)
            counters["legacy_transactions"] += 1
            block = mine("legacy transaction mined")
            remember_utxo("legacy_a", tx, 0, legacy_a)
            remember_utxo("miner_change", tx, 1, owner)
            status, body = call_api_json(api, method="GET", path=f"/v1/tx/{tx.txid()}")
            _assert(status.startswith("200"), "legacy transaction API lookup failed")
            return {"txid": tx.txid(), "block_hash": block.block_hash(), "api_location": body["location"]}

        stage("legacy", legacy_phase)

        def activation_phase() -> dict[str, Any]:
            previous_height = node.chain_tip().height if node.chain_tip() else -1
            mine_to_height(node, activation_height, miner.address)
            activation_tip = node.chain_tip()
            _assert(activation_tip is not None and activation_tip.height >= activation_height, "activation height not reached")
            next_block = mine("post-activation empty block")
            return {
                "previous_height": previous_height,
                "activation_height": activation_height,
                "next_height": node.chain_tip().height,
                "post_activation_block": next_block.block_hash(),
            }

        stage("activation", activation_phase)

        def first_chcq_address() -> dict[str, Any]:
            parsed = parse_address(pq_a.address)
            status, body = call_api_json(api, method="GET", path=f"/v1/address/{pq_a.address}")
            _assert(parsed.kind == "pq" and parsed.scheme_id == SIG_SCHEME_ML_DSA_44, "CHCQ address does not parse as ML-DSA-44")
            _assert(status.startswith("200"), "CHCQ address API lookup failed")
            return {"address": pq_a.address, "address_kind": body["address_kind"], "address_scheme_id": body["address_scheme_id"]}

        stage("first CHCQ address", first_chcq_address)

        def first_chc_to_chcq() -> dict[str, Any]:
            outpoint, value, owner = utxos.pop("miner_change")
            tx = _payment(owner, outpoint, value=value, recipient=pq_a.address, amount=2_000_000, fee=1_000)
            node.receive_transaction(tx)
            node.mempool.record_pq_relay(tx)
            counters["pq_transactions"] += 1
            _assert(any(entry.txid() == tx.txid() for entry in node.list_mempool_transactions()), "CHC -> CHCQ missing from mempool")
            block = mine("first CHC -> CHCQ mined")
            remember_utxo("pq_a", tx, 0, pq_a)
            remember_utxo("miner_change_2", tx, 1, owner)
            status, body = call_api_json(api, method="GET", path=f"/v1/tx/{tx.txid()}")
            _assert(status.startswith("200") and body["transaction"]["outputs"][0]["address_kind"] == "pq", "API PQ output metadata missing")
            return {"txid": tx.txid(), "block_hash": block.block_hash(), "address_kind": body["transaction"]["outputs"][0]["address_kind"]}

        stage("first CHC -> CHCQ", first_chc_to_chcq)

        def first_chcq_spend() -> dict[str, Any]:
            outpoint, value, owner = utxos.pop("pq_a")
            tx = _payment(owner, outpoint, value=value, recipient=legacy_b.address, amount=value - 2_000, fee=1_000)
            _assert(tx.inputs[0].sig_scheme_id == SIG_SCHEME_ML_DSA_44, "CHCQ spend did not use ML-DSA-44")
            before = node.mempool.pq_metrics_snapshot()["pq_verify_count"]
            node.receive_transaction(tx)
            node.mempool.record_pq_relay(tx)
            counters["pq_transactions"] += 1
            block = mine("first CHCQ -> CHC mined")
            after = node.mempool.pq_metrics_snapshot()["pq_verify_count"]
            _assert(after > before, "PQ verify counter did not increase")
            _assert(node.chainstate.get(outpoint) is None, "spent CHCQ UTXO remains in chainstate")
            remember_utxo("legacy_b_from_pq", tx, 0, legacy_b)
            status, body = call_api_json(api, method="GET", path=f"/v1/tx/{tx.txid()}")
            _assert(status.startswith("200") and body["transaction"]["inputs"][0]["sig_scheme_id"] == SIG_SCHEME_ML_DSA_44, "API PQ input metadata missing")
            return {"txid": tx.txid(), "block_hash": block.block_hash(), "sig_scheme_id": body["transaction"]["inputs"][0]["sig_scheme_id"]}

        stage("first CHCQ spend", first_chcq_spend)

        def mixed_traffic() -> dict[str, Any]:
            created: list[str] = []
            # Legacy -> legacy.
            outpoint, value, owner = utxos.pop("legacy_b_from_pq")
            tx = _payment(owner, outpoint, value=value, recipient=legacy_a.address, amount=value - 2_000, fee=1_000)
            node.receive_transaction(tx)
            counters["legacy_transactions"] += 1
            created.append(tx.txid())
            remember_utxo("legacy_a_mixed", tx, 0, legacy_a)
            # Legacy -> CHCQ.
            outpoint, value, owner = utxos.pop("miner_change_2")
            tx = _payment(owner, outpoint, value=value, recipient=pq_a.address, amount=1_000_000, fee=1_000)
            node.receive_transaction(tx)
            node.mempool.record_pq_relay(tx)
            counters["pq_transactions"] += 1
            created.append(tx.txid())
            remember_utxo("pq_a_mixed", tx, 0, pq_a)
            remember_utxo("miner_change_3", tx, 1, owner)
            block = mine("mixed legacy and PQ outputs mined")
            # CHCQ -> legacy and CHCQ -> CHCQ.
            outpoint, value, owner = utxos.pop("pq_a_mixed")
            tx = _payment(owner, outpoint, value=value, recipient=pq_b.address, amount=value - 2_000, fee=1_000)
            node.receive_transaction(tx)
            node.mempool.record_pq_relay(tx)
            counters["pq_transactions"] += 1
            created.append(tx.txid())
            remember_utxo("pq_b_mixed", tx, 0, pq_b)
            block2 = mine("mixed CHCQ -> CHCQ mined")
            return {"txids": created, "blocks": [block.block_hash(), block2.block_hash()]}

        stage("mixed traffic", mixed_traffic)

        def moderate_stress() -> dict[str, Any]:
            txids: list[str] = []
            for index in range(4):
                outpoint, value, owner = utxos.pop("pq_b_mixed")
                recipient = pq_a.address if index % 2 == 0 else pq_b.address
                next_owner = pq_a if index % 2 == 0 else pq_b
                tx = _payment(owner, outpoint, value=value, recipient=recipient, amount=value - 2_000, fee=1_000)
                node.receive_transaction(tx)
                node.mempool.record_pq_relay(tx)
                counters["pq_transactions"] += 1
                txids.append(tx.txid())
                block = mine(f"stress PQ block {index + 1}")
                remember_utxo("pq_b_mixed", tx, 0, next_owner)
                _assert(block.transactions[1].txid() == tx.txid(), "stress PQ tx was not mined")
            metrics = node.mempool.pq_metrics_snapshot()
            _assert(metrics["pq_verify_count"] >= 5, "PQ verify count did not increase during stress")
            _assert(metrics["pq_verify_failures"] == 0, "unexpected PQ verify failure during stress")
            return {"txids": txids, "metrics": metrics}

        stage("moderate stress", moderate_stress)

        def reorg_phase() -> dict[str, Any]:
            before = _run_reorg_scenarios(state_dir / "reorgs")
            return before

        stage("reorg scenarios", reorg_phase)

        def restart_phase() -> dict[str, Any]:
            db_path = state_dir / "node.sqlite3"
            restarted = _make_service(db_path, params=params, start_time=1_920_000_000)
            restarted_api = HttpApiApp(restarted)
            tip = restarted.chain_tip()
            _assert(tip is not None and tip.height == node.chain_tip().height, "restart did not reload the same tip")
            status, body = call_api_json(restarted_api, method="GET", path="/v1/status")
            _assert(status.startswith("200") and body["height"] == tip.height, "restart API status mismatch")
            return {"height": tip.height, "mempool_size": len(restarted.list_mempool_transactions())}

        stage("restart", restart_phase)

        def fresh_sync_phase() -> dict[str, Any]:
            fresh = _make_service(state_dir / "fresh.sqlite3", params=params, start_time=1_930_000_000)
            result = SyncManager(node=fresh).synchronize(node)
            _assert(fresh.chain_tip() is not None and fresh.chain_tip().block_hash == node.chain_tip().block_hash, "fresh sync tip mismatch")
            fresh_api = HttpApiApp(fresh)
            status, body = call_api_json(fresh_api, method="GET", path="/v1/status")
            _assert(status.startswith("200") and body["height"] == fresh.chain_tip().height, "fresh sync API status mismatch")
            return {"blocks_fetched": result.blocks_fetched, "headers_received": result.headers_received, "height": fresh.chain_tip().height}

        stage("fresh sync", fresh_sync_phase)

        def negative_tests() -> dict[str, Any]:
            rejected: dict[str, str] = {}
            pre_node = _make_service(state_dir / "negative-pre.sqlite3", params=params, start_time=1_940_000_000)
            pre_block = mine_next_block(pre_node, miner.address)
            pre_outpoint = OutPoint(txid=pre_block.transactions[0].txid(), index=0)
            pre_value = int(pre_block.transactions[0].outputs[0].value)
            pre_tx = _payment(miner, pre_outpoint, value=pre_value, recipient=pq_a.address, amount=1_000_000, fee=1_000)
            rejected["pre_activation"] = _expect_rejected(lambda: pre_node.receive_transaction(pre_tx), "CHCQ outputs are not active")

            outpoint, value, owner = utxos["pq_b_mixed"]
            valid = _payment(owner, outpoint, value=value, recipient=legacy_a.address, amount=value - 2_000, fee=1_000)
            rejected["wrong_scheme"] = _expect_rejected(
                lambda: node.receive_transaction(_replace_input(valid, sig_scheme_id=SIG_SCHEME_ML_DSA_65_RESERVED)),
                "non-verification-capable",
            )
            rejected["bad_signature"] = _expect_rejected(
                lambda: node.receive_transaction(_replace_input(valid, signature=bytes((valid.inputs[0].signature[0] ^ 1,)) + valid.inputs[0].signature[1:])),
                "Input signature is invalid",
            )
            rejected["bad_public_key"] = _expect_rejected(
                lambda: node.receive_transaction(_replace_input(valid, public_key=b"\x55" * ML_DSA_44_PUBLIC_KEY_SIZE)),
                "does not match the CHCQ commitment",
            )
            rejected["truncated_signature"] = _expect_rejected(
                lambda: node.receive_transaction(_replace_input(valid, signature=valid.inputs[0].signature[:-1])),
                "wrong size",
            )
            oversized_signature = b"\x01" * (ML_DSA_44_SIGNATURE_SIZE + 1)
            oversized_tx = _replace_input(valid, signature=oversized_signature)
            rejected["oversized"] = _expect_rejected(lambda: node.receive_transaction(oversized_tx), "wrong size")
            raw = serialize_transaction(valid)
            rejected["truncated_encoding"] = _expect_parse_error(lambda: deserialize_transaction(raw[:5]))
            counters["pq_transactions"] += 0
            return rejected

        stage("negative tests", negative_tests)

        def api_phase() -> dict[str, Any]:
            status, body = call_api_json(api, method="GET", path="/v1/status")
            _assert(status.startswith("200"), "status API failed")
            _assert(body["height"] == node.chain_tip().height, "status height mismatch")
            audit_payload = build_pq_audit_report(repo_root=Path.cwd())
            _assert(audit_payload["activation"]["testnet"] == 30_000, "audit activation height mismatch")
            return {"height": body["height"], "audit_activation": audit_payload["activation"]["testnet"]}

        stage("API and audit metadata", api_phase)

        if not skip_browser_checks:
            def browser_phase() -> dict[str, Any]:
                npm_results = {
                    "npm_test": _run_subprocess(["npm", "test"], cwd=Path("apps/browser-wallet")),
                    "npm_build": _run_subprocess(["npm", "run", "build"], cwd=Path("apps/browser-wallet")),
                    "bundle": _run_subprocess(["npm", "run", "test:mldsa:bundle"], cwd=Path("apps/browser-wallet")),
                }
                return npm_results

            stage("browser fixture/parity/build", browser_phase)

        if not skip_subprocess_checks:
            def readiness_phase() -> dict[str, Any]:
                return {"pytest": _run_subprocess([sys.executable, "-m", "pytest", "tests/pq/test_activation_readiness.py", "-q"], cwd=Path.cwd())}

            stage("readiness suite", readiness_phase)

        smoke_result = run_pq_smoke(activation_height=activation_height)
        smoke = smoke_result.to_json_payload()
        checks.append(DressCheck("pq-smoke", details={"ready": smoke_result.ready, "final_local_height": smoke_result.final_local_height}))
        timeline.append({"stage": "pq-smoke", "status": "PASS", "ready": smoke_result.ready})

        benchmark = run_benchmark(verify_1000=True)
        checks.append(DressCheck("pq-benchmark", details={"measurements": len(benchmark["measurements"])}))
        timeline.append({"stage": "pq-benchmark", "status": "PASS"})

        audit = build_pq_audit_report(repo_root=Path.cwd())
        checks.append(DressCheck("pq-audit-report", details={"testnet_activation": audit["activation"]["testnet"]}))
        timeline.append({"stage": "pq-audit-report", "status": "PASS"})

        readiness = {
            "suite": "tests/pq/test_activation_readiness.py",
            "status": "PASS" if not skip_subprocess_checks else "SKIPPED",
        }

        metrics = node.mempool.pq_metrics_snapshot()
        status = "PASS"
        result = DressRehearsalResult(
            status=status,
            activation_height=activation_height,
            legacy_blocks=counters["legacy_blocks"],
            pq_blocks=counters["pq_blocks"],
            legacy_transactions=counters["legacy_transactions"],
            pq_transactions=counters["pq_transactions"],
            verify_count=int(metrics["pq_verify_count"]),
            verify_failures=int(metrics["pq_verify_failures"]),
            benchmark=benchmark,
            readiness=readiness,
            smoke=smoke,
            audit=audit,
            warnings=warnings,
            errors=errors,
            duration_seconds=time.perf_counter() - started_at,
            timeline=timeline,
            checks=[{"status": check.status, "label": check.label, "details": check.details} for check in checks],
            markdown_report_path=str(output_markdown),
            json_report_path=str(output_json),
        )

    _write_outputs(result, output_json=output_json, output_markdown=output_markdown)
    return result


def _run_reorg_scenarios(base_dir: Path) -> dict[str, Any]:
    base_dir.mkdir(parents=True, exist_ok=True)
    params = make_pq_readiness_params(activation_height=2)
    miner = _legacy_wallet(0)
    pq_owner = wallet_key_from_mldsa44_seed(bytes(range(32)))

    def new_service(name: str, start: int) -> NodeService:
        return _make_service(base_dir / f"{name}.sqlite3", params=params, start_time=start)

    # Before activation: legacy disconnected tx is re-added.
    before_target = new_service("before-target", 1_950_000_000)
    before_alt = new_service("before-alt", 1_950_010_000)
    common = mine_next_block(before_target, miner.address)
    before_alt.apply_block(common)
    spend = _payment(
        miner,
        OutPoint(txid=common.transactions[0].txid(), index=0),
        value=int(common.transactions[0].outputs[0].value),
        recipient=_legacy_wallet(1).address,
        amount=1_000_000,
        fee=1_000,
    )
    before_target.receive_transaction(spend)
    before_target.apply_block(mine_easy_block(before_target.build_candidate_block(miner.address).block))
    alt1 = mine_easy_block(before_alt.build_candidate_block(miner.address).block)
    before_alt.apply_block(alt1)
    alt2 = mine_easy_block(before_alt.build_candidate_block(miner.address).block)
    before_alt.apply_block(alt2)
    manager = SyncManager(node=before_target)
    manager.receive_block(alt1)
    before_result = manager.receive_block(alt2)
    _assert(before_result.reorged and before_target.find_transaction(spend.txid()) is not None, "pre-activation reorg did not re-add legacy tx")

    # During activation: disconnected CHCQ output tx is not re-added below activation.
    during_target = new_service("during-target", 1_951_000_000)
    common = mine_next_block(during_target, miner.address)
    common_hash = common.block_hash()
    mine_next_block(during_target, miner.address)
    pq_tx = _payment(
        miner,
        OutPoint(txid=common.transactions[0].txid(), index=0),
        value=int(common.transactions[0].outputs[0].value),
        recipient=pq_owner.address,
        amount=1_000_000,
        fee=1_000,
    )
    during_target.receive_transaction(pq_tx)
    during_target.apply_block(mine_easy_block(during_target.build_candidate_block(miner.address).block))
    during_result = during_target.activate_chain(common_hash)
    _assert(during_result.reorged and during_target.find_transaction(pq_tx.txid()) is None, "activation-boundary reorg re-added CHCQ tx")

    # After activation: disconnected CHCQ tx remains valid and is re-added.
    after_target = new_service("after-target", 1_952_000_000)
    after_alt = new_service("after-alt", 1_952_010_000)
    common = mine_next_block(after_target, miner.address)
    after_alt.apply_block(common)
    mine_next_block(after_target, miner.address)
    after_alt.apply_block(after_target.get_block_by_hash(after_target.chain_tip().block_hash))
    pq_tx = _payment(
        miner,
        OutPoint(txid=common.transactions[0].txid(), index=0),
        value=int(common.transactions[0].outputs[0].value),
        recipient=pq_owner.address,
        amount=1_000_000,
        fee=1_000,
    )
    after_target.receive_transaction(pq_tx)
    after_target.apply_block(mine_easy_block(after_target.build_candidate_block(miner.address).block))
    alt1 = mine_easy_block(after_alt.build_candidate_block(miner.address).block)
    after_alt.apply_block(alt1)
    alt2 = mine_easy_block(after_alt.build_candidate_block(miner.address).block)
    after_alt.apply_block(alt2)
    manager = SyncManager(node=after_target)
    manager.receive_block(alt1)
    after_result = manager.receive_block(alt2)
    _assert(after_result.reorged and after_target.find_transaction(pq_tx.txid()) is not None, "post-activation reorg did not re-add valid CHCQ tx")

    return {
        "before_activation_reorg_depth": before_result.reorg_depth,
        "during_activation_reorg_depth": during_result.reorg_depth,
        "after_activation_reorg_depth": after_result.reorg_depth,
    }


def _make_service(database_path: Path, *, params, start_time: int) -> NodeService:
    timestamps = iter(range(start_time, start_time + 10_000))
    return NodeService.open_sqlite(
        database_path,
        network="testnet",
        params=params,
        time_provider=lambda: next(timestamps),
    )


def _legacy_wallet(index: int) -> WalletKey:
    return wallet_key_from_private_key((index + 1).to_bytes(32, "big"))


def _payment(owner: WalletKey, outpoint: OutPoint, *, value: int, recipient: str, amount: int, fee: int) -> Transaction:
    return TransactionSigner(owner).build_signed_transaction(
        spend_candidates=[
            SpendCandidate(
                txid=outpoint.txid,
                index=outpoint.index,
                amount_chipbits=value,
                recipient=owner.address,
            )
        ],
        recipient=recipient,
        amount_chipbits=amount,
        fee_chipbits=fee,
        metadata={"kind": "payment", "purpose": "pq-dress-rehearsal"},
        network="testnet",
    ).transaction


def _replace_input(transaction: Transaction, **changes) -> Transaction:
    from dataclasses import replace

    return replace(transaction, inputs=(replace(transaction.inputs[0], **changes),))


def _is_pq_transaction(transaction: Transaction) -> bool:
    return any(tx_input.sig_scheme_id == SIG_SCHEME_ML_DSA_44 for tx_input in transaction.inputs) or any(
        output.recipient.startswith("CHCQ") for output in transaction.outputs
    )


def _expect_rejected(callable_, expected_text: str) -> str:
    try:
        callable_()
    except ValidationError as exc:
        text = str(exc)
        _assert(expected_text in text, f"expected rejection containing {expected_text!r}, got {text!r}")
        return text
    except PqSmokeError as exc:
        text = exc.reason
        _assert(expected_text in text, f"expected rejection containing {expected_text!r}, got {text!r}")
        return text
    raise DressRehearsalError("negative tests", f"expected rejection containing {expected_text!r}")


def _expect_parse_error(callable_) -> str:
    try:
        callable_()
    except (ValueError, struct.error) as exc:
        return str(exc)
    raise DressRehearsalError("negative tests", "expected parse error")


def _run_subprocess(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    if completed.returncode != 0:
        raise DressRehearsalError("subprocess", f"{' '.join(command)} failed with exit {completed.returncode}: {completed.stdout[-1200:]}")
    return {"command": command, "returncode": completed.returncode, "output_tail": completed.stdout[-1200:]}


def _write_outputs(result: DressRehearsalResult, *, output_json: Path, output_markdown: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result.to_json_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_markdown.write_text(_markdown_report(result), encoding="utf-8")


def _markdown_report(result: DressRehearsalResult) -> str:
    benchmark_rows = {row["operation"]: row for row in result.benchmark.get("measurements", [])}
    mldsa_verify = benchmark_rows.get("mldsa44_verify_1000", {})
    ecdsa_verify = benchmark_rows.get("ecdsa_verify_1000", {})
    lines = [
        "# Post-Quantum Testnet Dress Rehearsal Report",
        "",
        f"Status: **{result.status}**",
        f"Activation height: `{result.activation_height}`",
        f"Duration: `{round(result.duration_seconds, 3)}s`",
        "",
        "## Summary",
        "",
        f"- Legacy blocks: `{result.legacy_blocks}`",
        f"- PQ blocks: `{result.pq_blocks}`",
        f"- Legacy transactions: `{result.legacy_transactions}`",
        f"- PQ transactions: `{result.pq_transactions}`",
        f"- PQ verify count: `{result.verify_count}`",
        f"- PQ verify failures: `{result.verify_failures}`",
        "",
        "## Timeline",
        "",
    ]
    for item in result.timeline:
        details = ", ".join(f"{key}={value}" for key, value in item.items() if key != "stage")
        lines.append(f"- {item['stage']}: {details}")
    lines.extend(
        [
            "",
            "## Benchmark",
            "",
            f"- ECDSA verify 1000 median seconds: `{ecdsa_verify.get('median_seconds')}`",
            f"- ECDSA verify 1000 throughput/s: `{ecdsa_verify.get('throughput_per_second')}`",
            f"- ML-DSA-44 verify 1000 median seconds: `{mldsa_verify.get('median_seconds')}`",
            f"- ML-DSA-44 verify 1000 throughput/s: `{mldsa_verify.get('throughput_per_second')}`",
            "",
            "## Readiness And Smoke",
            "",
            f"- Readiness: `{result.readiness.get('status')}`",
            f"- Smoke ready: `{result.smoke.get('ready')}`",
            f"- Smoke final local height: `{result.smoke.get('final_local_height')}`",
            "",
            "## Audit",
            "",
            f"- Testnet activation height: `{result.audit.get('activation', {}).get('testnet')}`",
            f"- ML-DSA backend available: `{result.audit.get('mldsa44', {}).get('backend_available')}`",
            f"- Policy max PQ inputs: `{result.audit.get('policy', {}).get('max_pq_inputs')}`",
            "",
            "## Warnings",
            "",
        ]
    )
    lines.extend(f"- {warning}" for warning in result.warnings) if result.warnings else lines.append("- none")
    lines.extend(["", "## Errors", ""])
    lines.extend(f"- {error}" for error in result.errors) if result.errors else lines.append("- none")
    lines.extend(["", "## Checks", ""])
    for check in result.checks:
        lines.append(f"- {check['status']} {check['label']}")
    return "\n".join(lines) + "\n"


def _assert(condition: bool, reason: str) -> None:
    if not condition:
        raise DressRehearsalError("assertion", reason)
