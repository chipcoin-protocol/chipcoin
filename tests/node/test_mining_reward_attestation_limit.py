"""Mining template regression tests for reward attestation bundle limits."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from chipcoin.consensus.epoch_settlement import RewardAttestation
from chipcoin.consensus.params import DEVNET_PARAMS
from chipcoin.consensus.models import Transaction
from chipcoin.node.service import NodeService
from chipcoin.node.runtime import NodeRuntime, RewardNodeAutomationConfig
from chipcoin.wallet.signer import TransactionSigner
from tests.helpers import wallet_key
from tests.node.test_reward_node_automation_over_emission import _register_reward_node
from tests.node.test_reward_node_automation import _apply_candidate_block, _write_wallet_file


def _mining_limit_params():
    return replace(
        DEVNET_PARAMS,
        coinbase_maturity=0,
        node_reward_activation_height=0,
        reward_node_warmup_epochs=0,
        epoch_length_blocks=5,
        reward_check_windows_per_epoch=3,
        reward_target_checks_per_epoch=3,
        reward_min_passed_checks_per_epoch=1,
        reward_verifier_committee_size=2,
        reward_verifier_quorum=1,
        reward_final_confirmation_window_blocks=1,
        max_rewarded_nodes_per_epoch=4,
        max_attestation_bundles_per_block=2,
    )


def _make_limit_service(database_path: Path, *, start_time: int) -> NodeService:
    timestamps = iter(range(start_time, start_time + 1000))
    return NodeService.open_sqlite(
        database_path,
        network="devnet",
        params=_mining_limit_params(),
        time_provider=lambda: next(timestamps),
    )


def test_build_candidate_block_caps_reward_attestation_bundles_per_block() -> None:
    with TemporaryDirectory() as tempdir:
        reward_a = wallet_key(0)
        reward_b = wallet_key(1)
        reward_c = wallet_key(2)
        service = _make_limit_service(Path(tempdir) / "node.sqlite3", start_time=1_700_090_000)
        reward_a_path = _write_wallet_file(Path(tempdir) / "reward-a.json", reward_a)
        reward_b_path = _write_wallet_file(Path(tempdir) / "reward-b.json", reward_b)
        reward_c_path = _write_wallet_file(Path(tempdir) / "reward-c.json", reward_c)
        runtime_a = NodeRuntime(
            service=service,
            reward_automation=RewardNodeAutomationConfig(
                node_id="reward-node-a",
                owner_wallet_path=reward_a_path,
                attest_wallet_path=reward_a_path,
            ),
        )
        runtime_b = NodeRuntime(
            service=service,
            reward_automation=RewardNodeAutomationConfig(
                node_id="reward-node-b",
                owner_wallet_path=reward_b_path,
                attest_wallet_path=reward_b_path,
            ),
        )
        runtime_c = NodeRuntime(
            service=service,
            reward_automation=RewardNodeAutomationConfig(
                node_id="reward-node-c",
                owner_wallet_path=reward_c_path,
                attest_wallet_path=reward_c_path,
            ),
        )

        _register_reward_node(service, wallet=reward_a, node_id="reward-node-a", declared_port=18444)
        _register_reward_node(service, wallet=reward_b, node_id="reward-node-b", declared_port=18445)
        _register_reward_node(service, wallet=reward_c, node_id="reward-node-c", declared_port=18446)
        _apply_candidate_block(service, reward_a.address)

        import asyncio

        asyncio.run(runtime_a._run_reward_automation_once())
        asyncio.run(runtime_b._run_reward_automation_once())
        asyncio.run(runtime_c._run_reward_automation_once())

        mempool_bundles = [
            tx for tx in service.list_mempool_transactions() if tx.metadata.get("kind") == "reward_attestation_bundle"
        ]
        assert len(mempool_bundles) > service.params.max_attestation_bundles_per_block

        candidate = service.build_candidate_block(reward_a.address)
        included_bundles = [
            tx for tx in candidate.block.transactions if tx.metadata.get("kind") == "reward_attestation_bundle"
        ]
        assert len(included_bundles) == service.params.max_attestation_bundles_per_block
        for tx in included_bundles:
            json.loads(tx.metadata["attestations_json"])


def test_build_candidate_block_skips_conflicting_verifier_window_attestation_bundles() -> None:
    with TemporaryDirectory() as tempdir:
        reward_a = wallet_key(0)
        reward_b = wallet_key(1)
        reward_c = wallet_key(2)
        service = _make_limit_service(Path(tempdir) / "node.sqlite3", start_time=1_700_091_000)

        _register_reward_node(service, wallet=reward_a, node_id="reward-node-a", declared_port=18444)
        _register_reward_node(service, wallet=reward_b, node_id="reward-node-b", declared_port=18445)
        _register_reward_node(service, wallet=reward_c, node_id="reward-node-c", declared_port=18446)
        _apply_candidate_block(service, reward_a.address)

        epoch_state = service.native_reward_epoch_state(epoch_index=0)
        assignments = list(epoch_state["assignments"])
        overlap: tuple[str, int, list[str]] | None = None
        candidate_endpoints = {
            str(assignment["node_id"]): f"{assignment['declared_host']}:{assignment['declared_port']}"
            for assignment in assignments
        }
        candidates_by_verifier_window: dict[tuple[str, int], list[str]] = {}
        for assignment in assignments:
            candidate_node_id = str(assignment["node_id"])
            committees = assignment["verifier_committees"]
            for raw_window_index, committee in committees.items():
                window_index = int(raw_window_index)
                for verifier_node_id in committee:
                    candidates_by_verifier_window.setdefault((str(verifier_node_id), window_index), []).append(candidate_node_id)
        for (verifier_node_id, window_index), candidate_node_ids in candidates_by_verifier_window.items():
            unique_candidates = sorted(set(candidate_node_ids))
            if len(unique_candidates) >= 2:
                overlap = (verifier_node_id, window_index, unique_candidates[:2])
                break

        assert overlap is not None
        verifier_node_id, window_index, candidate_node_ids = overlap
        verifier_wallet = {
            "reward-node-a": reward_a,
            "reward-node-b": reward_b,
            "reward-node-c": reward_c,
        }[verifier_node_id]
        signer = TransactionSigner(verifier_wallet)

        for candidate_node_id in candidate_node_ids:
            attestation = signer.sign_reward_attestation(
                RewardAttestation(
                    epoch_index=0,
                    check_window_index=window_index,
                    candidate_node_id=candidate_node_id,
                    verifier_node_id=verifier_node_id,
                    result_code="pass",
                    observed_sync_gap=0,
                    endpoint_commitment=candidate_endpoints[candidate_node_id],
                    concentration_key=f"unscoped:{candidate_node_id}",
                    signature_hex="",
                )
            )
            transaction = Transaction(
                version=1,
                inputs=(),
                outputs=(),
                metadata={
                    "kind": "reward_attestation_bundle",
                    "epoch_index": "0",
                    "bundle_window_index": str(window_index),
                    "bundle_submitter_node_id": verifier_node_id,
                    "attestation_count": "1",
                    "attestations_json": json.dumps(
                        [
                            {
                                "epoch_index": attestation.epoch_index,
                                "check_window_index": attestation.check_window_index,
                                "candidate_node_id": attestation.candidate_node_id,
                                "verifier_node_id": attestation.verifier_node_id,
                                "result_code": attestation.result_code,
                                "observed_sync_gap": attestation.observed_sync_gap,
                                "endpoint_commitment": attestation.endpoint_commitment,
                                "concentration_key": attestation.concentration_key,
                                "signature_hex": attestation.signature_hex,
                            }
                        ],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
            )
            service.receive_transaction(transaction)

        candidate = service.build_candidate_block(reward_a.address)
        included_bundles = [
            tx for tx in candidate.block.transactions if tx.metadata.get("kind") == "reward_attestation_bundle"
        ]
        assert len(included_bundles) == 1
        mined_block = service.mining.mine_block(candidate, max_nonce_attempts=10_000)
        assert mined_block is not None
        service.apply_block(mined_block)
