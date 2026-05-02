"""Reward-node automation tests that avoid live TCP sockets."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from chipcoin.consensus.models import Block
from chipcoin.consensus.params import DEVNET_PARAMS
from chipcoin.consensus.pow import verify_proof_of_work
from chipcoin.node.runtime import NodeRuntime, RewardNodeAutomationConfig
from chipcoin.node.service import NodeService
from chipcoin.wallet.signer import TransactionSigner
from tests.helpers import wallet_key


def _reward_params():
    return replace(
        DEVNET_PARAMS,
        coinbase_maturity=0,
        node_reward_activation_height=0,
        reward_node_warmup_epochs=0,
        epoch_length_blocks=5,
        reward_check_windows_per_epoch=4,
        reward_target_checks_per_epoch=1,
        reward_min_passed_checks_per_epoch=1,
        reward_verifier_committee_size=1,
        reward_verifier_quorum=1,
        reward_final_confirmation_window_blocks=1,
        max_rewarded_nodes_per_epoch=4,
    )


def _make_reward_service(database_path: Path, *, start_time: int) -> NodeService:
    timestamps = iter(range(start_time, start_time + 1000))
    return NodeService.open_sqlite(
        database_path,
        network="devnet",
        params=_reward_params(),
        time_provider=lambda: next(timestamps),
    )


def _mine_block(block: Block) -> Block:
    for nonce in range(2_000_000):
        header = replace(block.header, nonce=nonce)
        if verify_proof_of_work(header):
            return replace(block, header=header)
    raise AssertionError("Expected to find a valid nonce for the easy target.")


def _apply_candidate_block(service: NodeService, payout_address: str) -> Block:
    solved = _mine_block(service.build_candidate_block(payout_address).block)
    service.apply_block(solved)
    return solved


def _register_reward_node(service: NodeService, *, wallet, node_id: str, declared_port: int) -> None:
    service.receive_transaction(
        TransactionSigner(wallet).build_register_reward_node_transaction(
            node_id=node_id,
            payout_address=wallet.address,
            node_public_key_hex=wallet.public_key.hex(),
            declared_host="127.0.0.1",
            declared_port=declared_port,
            registration_fee_chipbits=int(service.reward_node_fee_schedule()["register_fee_chipbits"]),
        )
    )


def _write_wallet_file(path: Path, wallet) -> Path:
    path.write_text(
        json.dumps(
            {
                "address": wallet.address,
                "compressed": wallet.compressed,
                "private_key_hex": wallet.private_key.hex(),
                "public_key_hex": wallet.public_key.hex(),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def test_reward_node_automation_auto_renews_for_next_epoch() -> None:
    with TemporaryDirectory() as tempdir:
        reward_a = wallet_key(0)
        service = _make_reward_service(Path(tempdir) / "node.sqlite3", start_time=1_700_050_000)
        wallet_path = _write_wallet_file(Path(tempdir) / "reward-a.json", reward_a)
        runtime = NodeRuntime(
            service=service,
            reward_automation=RewardNodeAutomationConfig(
                node_id="reward-node-a",
                owner_wallet_path=wallet_path,
                attest_wallet_path=wallet_path,
                auto_attest_enabled=False,
                poll_interval_seconds=0.05,
            ),
        )

        _register_reward_node(service, wallet=reward_a, node_id="reward-node-a", declared_port=18444)
        _apply_candidate_block(service, reward_a.address)  # height 0, registration confirmed
        _apply_candidate_block(service, reward_a.address)  # height 1
        _apply_candidate_block(service, reward_a.address)  # height 2
        _apply_candidate_block(service, reward_a.address)  # height 3
        _apply_candidate_block(service, reward_a.address)  # height 4

        asyncio.run(runtime._run_reward_automation_once())
        assert any(tx.metadata.get("kind") == "renew_reward_node" for tx in service.list_mempool_transactions())

        _apply_candidate_block(service, reward_a.address)  # height 5, renewal confirmed
        status = service.reward_node_status(node_id="reward-node-a", epoch_index=1)
        assert status["last_renewal_epoch"] == 1
        assert status["last_renewal_height"] == 5


def test_reward_node_automation_auto_attests_and_enables_settlement() -> None:
    with TemporaryDirectory() as tempdir:
        reward_a = wallet_key(0)
        reward_b = wallet_key(1)
        service = _make_reward_service(Path(tempdir) / "node.sqlite3", start_time=1_700_060_000)
        reward_a_path = _write_wallet_file(Path(tempdir) / "reward-a.json", reward_a)
        reward_b_path = _write_wallet_file(Path(tempdir) / "reward-b.json", reward_b)
        runtime_a = NodeRuntime(
            service=service,
            reward_automation=RewardNodeAutomationConfig(
                node_id="reward-node-a",
                owner_wallet_path=reward_a_path,
                attest_wallet_path=reward_a_path,
                poll_interval_seconds=0.05,
            ),
        )
        runtime_b = NodeRuntime(
            service=service,
            reward_automation=RewardNodeAutomationConfig(
                node_id="reward-node-b",
                owner_wallet_path=reward_b_path,
                attest_wallet_path=reward_b_path,
                poll_interval_seconds=0.05,
            ),
        )

        _register_reward_node(service, wallet=reward_a, node_id="reward-node-a", declared_port=18444)
        _register_reward_node(service, wallet=reward_b, node_id="reward-node-b", declared_port=18445)
        _apply_candidate_block(service, reward_a.address)  # height 0, registrations confirmed

        asyncio.run(runtime_a._run_reward_automation_once())
        asyncio.run(runtime_b._run_reward_automation_once())
        attestation_txs = [tx for tx in service.list_mempool_transactions() if tx.metadata.get("kind") == "reward_attestation_bundle"]
        assert attestation_txs

        _apply_candidate_block(service, reward_a.address)  # height 1, attestations confirmed
        _apply_candidate_block(service, reward_a.address)  # height 2
        _apply_candidate_block(service, reward_a.address)  # height 3
        closing_block = _apply_candidate_block(service, reward_a.address)  # height 4, settlement closes epoch 0

        settlements = service.native_reward_settlement_diagnostics(epoch_index=0)
        assert len(settlements) == 1
        assert settlements[0]["distributed_node_reward_chipbits"] > 0
        assert settlements[0]["rewarded_node_count"] >= 1
        inspect = service.inspect_block(block_hash=closing_block.block_hash())
        assert inspect is not None
        assert inspect["node_reward_payouts"]


def test_reward_node_automation_skips_attestations_already_staged_in_mempool() -> None:
    with TemporaryDirectory() as tempdir:
        reward_a = wallet_key(0)
        reward_b = wallet_key(1)
        service = _make_reward_service(Path(tempdir) / "node.sqlite3", start_time=1_700_070_000)
        reward_a_path = _write_wallet_file(Path(tempdir) / "reward-a.json", reward_a)

        _register_reward_node(service, wallet=reward_a, node_id="reward-node-a", declared_port=18444)
        _register_reward_node(service, wallet=reward_b, node_id="reward-node-b", declared_port=18445)
        _apply_candidate_block(service, reward_a.address)

        first_runtime = NodeRuntime(
            service=service,
            reward_automation=RewardNodeAutomationConfig(
                node_id="reward-node-a",
                owner_wallet_path=reward_a_path,
                attest_wallet_path=reward_a_path,
                poll_interval_seconds=0.05,
            ),
        )
        asyncio.run(first_runtime._run_reward_automation_once())
        first_attestation_txs = [
            tx for tx in service.list_mempool_transactions() if tx.metadata.get("kind") == "reward_attestation_bundle"
        ]
        assert first_attestation_txs

        restarted_runtime = NodeRuntime(
            service=service,
            reward_automation=RewardNodeAutomationConfig(
                node_id="reward-node-a",
                owner_wallet_path=reward_a_path,
                attest_wallet_path=reward_a_path,
                poll_interval_seconds=0.05,
            ),
        )

        def fail_reward_status(*_args, **_kwargs):
            raise AssertionError("auto-attest should not build full reward node status")

        service.reward_node_status = fail_reward_status  # type: ignore[method-assign]
        asyncio.run(restarted_runtime._run_reward_automation_once())

        attestation_txs = [
            tx for tx in service.list_mempool_transactions() if tx.metadata.get("kind") == "reward_attestation_bundle"
        ]
        assert [tx.txid() for tx in attestation_txs] == [tx.txid() for tx in first_attestation_txs]
