import asyncio
import json
import socket
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from chipcoin.consensus.epoch_settlement import RewardAttestation
from chipcoin.consensus.models import Block, Transaction
from chipcoin.consensus.params import DEVNET_PARAMS
from chipcoin.consensus.pow import verify_proof_of_work
from chipcoin.miner.config import MinerWorkerConfig
from chipcoin.miner.worker import MinerWorker
from chipcoin.node.runtime import NodeRuntime, OutboundPeer
from chipcoin.node.service import NodeService
from chipcoin.wallet.signer import TransactionSigner
from tests.helpers import wallet_key


def _local_socket_available() -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _local_socket_available(),
    reason="local TCP binds are unavailable in this environment",
)


def _reward_params():
    return replace(
        DEVNET_PARAMS,
        coinbase_maturity=0,
        node_reward_activation_height=0,
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


async def _wait_until(predicate, *, timeout: float = 8.0, interval: float = 0.05) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError("Condition was not satisfied before timeout.")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _mine_and_announce(runtime: NodeRuntime, service: NodeService, payout_address: str) -> Block:
    block = _mine_block(service.build_candidate_block(payout_address).block)
    service.apply_block(block)
    await runtime.announce_block(block)
    return block


def _register_reward_node(service: NodeService, *, wallet, node_id: str, declared_port: int) -> None:
    service.receive_transaction(
        TransactionSigner(wallet).build_register_reward_node_transaction(
            node_id=node_id,
            payout_address=wallet.address,
            node_public_key_hex=wallet.public_key.hex(),
            declared_host="127.0.0.1",
            declared_port=declared_port,
            registration_fee_chipbits=service.params.register_node_fee_chipbits,
        )
    )


def _build_attestation_bundle_transaction(
    *,
    epoch_index: int,
    window_index: int,
    candidate_node_id: str,
    verifier_node_id: str,
    verifier_wallet,
    endpoint_commitment: str,
    concentration_key: str,
) -> Transaction:
    attestation = TransactionSigner(verifier_wallet).sign_reward_attestation(
        RewardAttestation(
            epoch_index=epoch_index,
            check_window_index=window_index,
            candidate_node_id=candidate_node_id,
            verifier_node_id=verifier_node_id,
            result_code="pass",
            observed_sync_gap=0,
            endpoint_commitment=endpoint_commitment,
            concentration_key=concentration_key,
            signature_hex="",
        )
    )
    return Transaction(
        version=1,
        inputs=(),
        outputs=(),
        metadata={
            "kind": "reward_attestation_bundle",
            "epoch_index": str(epoch_index),
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


async def _wait_for_tip(service: NodeService, block_hash: str) -> None:
    await _wait_until(lambda: service.chain_tip() is not None and service.chain_tip().block_hash == block_hash)


def test_native_reward_state_matches_across_fresh_and_snapshot_nodes() -> None:
    async def scenario() -> None:
        with TemporaryDirectory() as tempdir:
            wallets = {
                "reward-node-a": wallet_key(0),
                "reward-node-b": wallet_key(1),
                "reward-node-c": wallet_key(2),
            }
            bootstrap_service = _make_reward_service(Path(tempdir) / "bootstrap.sqlite3", start_time=1_700_000_000)
            fresh_service = _make_reward_service(Path(tempdir) / "fresh.sqlite3", start_time=1_700_001_000)
            verifier_service = _make_reward_service(Path(tempdir) / "verifier.sqlite3", start_time=1_700_002_000)

            bootstrap_runtime = NodeRuntime(service=bootstrap_service, listen_host="127.0.0.1", listen_port=0, ping_interval=0.2)
            await bootstrap_runtime.start()
            fresh_runtime = NodeRuntime(
                service=fresh_service,
                listen_host="127.0.0.1",
                listen_port=0,
                outbound_peers=[OutboundPeer("127.0.0.1", bootstrap_runtime.bound_port)],
                connect_interval=0.1,
                ping_interval=0.2,
            )
            verifier_runtime = NodeRuntime(
                service=verifier_service,
                listen_host="127.0.0.1",
                listen_port=0,
                outbound_peers=[OutboundPeer("127.0.0.1", bootstrap_runtime.bound_port)],
                connect_interval=0.1,
                ping_interval=0.2,
            )
            await fresh_runtime.start()
            await verifier_runtime.start()
            snapshot_runtime = None
            try:
                await _wait_until(lambda: bootstrap_runtime.connected_peer_count() == 2)
                port_map = {
                    "reward-node-a": bootstrap_runtime.bound_port,
                    "reward-node-b": fresh_runtime.bound_port,
                    "reward-node-c": verifier_runtime.bound_port,
                }
                for node_id, wallet in wallets.items():
                    _register_reward_node(
                        bootstrap_service,
                        wallet=wallet,
                        node_id=node_id,
                        declared_port=port_map[node_id],
                    )
                first_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, wallets["reward-node-a"].address)
                await _wait_for_tip(fresh_service, first_block.block_hash())
                await _wait_for_tip(verifier_service, first_block.block_hash())

                assignment = bootstrap_service.native_reward_assignments(epoch_index=0, node_id="reward-node-a")[0]
                window_index = assignment["candidate_check_windows"][0]
                verifier_node_id = assignment["verifier_committees"][str(window_index)][0]
                runtime_by_node_id = {
                    "reward-node-a": bootstrap_runtime,
                    "reward-node-b": fresh_runtime,
                    "reward-node-c": verifier_runtime,
                }
                attestation_tx = _build_attestation_bundle_transaction(
                    epoch_index=0,
                    window_index=window_index,
                    candidate_node_id="reward-node-a",
                    verifier_node_id=verifier_node_id,
                    verifier_wallet=wallets[verifier_node_id],
                    endpoint_commitment=f"127.0.0.1:{port_map['reward-node-a']}",
                    concentration_key="demo:reward-node-a",
                )
                await runtime_by_node_id[verifier_node_id].submit_transaction(attestation_tx)
                await _wait_until(lambda: bootstrap_service.find_transaction(attestation_tx.txid()) is not None)
                second_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, wallets["reward-node-a"].address)
                await _wait_for_tip(fresh_service, second_block.block_hash())
                await _wait_for_tip(verifier_service, second_block.block_hash())

                snapshot_path = Path(tempdir) / "reward.snapshot"
                bootstrap_service.export_snapshot_file(snapshot_path)
                snapshot_service = _make_reward_service(Path(tempdir) / "snapshot.sqlite3", start_time=1_700_003_000)
                snapshot_service.import_snapshot_file(snapshot_path)
                snapshot_runtime = NodeRuntime(
                    service=snapshot_service,
                    listen_host="127.0.0.1",
                    listen_port=0,
                    outbound_peers=[OutboundPeer("127.0.0.1", bootstrap_runtime.bound_port)],
                    connect_interval=0.1,
                    ping_interval=0.2,
                )
                await snapshot_runtime.start()
                await _wait_for_tip(snapshot_service, second_block.block_hash())

                third_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, wallets["reward-node-a"].address)
                fourth_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, wallets["reward-node-a"].address)
                for service in (fresh_service, verifier_service, snapshot_service):
                    await _wait_for_tip(service, fourth_block.block_hash())

                epoch_states = [
                    bootstrap_service.native_reward_epoch_state(epoch_index=0),
                    fresh_service.native_reward_epoch_state(epoch_index=0),
                    verifier_service.native_reward_epoch_state(epoch_index=0),
                    snapshot_service.native_reward_epoch_state(epoch_index=0),
                ]
                assert all(
                    state["comparison_keys"] == epoch_states[0]["comparison_keys"]
                    for state in epoch_states[1:]
                )
                assert all(
                    state["settlement_preview"]["reward_entries"] == epoch_states[0]["settlement_preview"]["reward_entries"]
                    for state in epoch_states[1:]
                )

                closing_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, wallets["reward-node-a"].address)
                for service in (fresh_service, verifier_service, snapshot_service):
                    await _wait_for_tip(service, closing_block.block_hash())

                expected_settlement = bootstrap_service.native_reward_settlement_diagnostics(epoch_index=0)
                assert len(expected_settlement) == 1
                for service in (fresh_service, verifier_service, snapshot_service):
                    assert service.native_reward_settlement_diagnostics(epoch_index=0) == expected_settlement
                    inspect = service.inspect_block(block_hash=closing_block.block_hash())
                    assert inspect is not None
                    assert inspect["node_reward_payouts"] == [
                        {
                            "recipient": wallets["reward-node-a"].address,
                            "amount_chipbits": expected_settlement[0]["distributed_node_reward_chipbits"],
                        }
                    ]
            finally:
                if snapshot_runtime is not None:
                    await snapshot_runtime.stop()
                await verifier_runtime.stop()
                await fresh_runtime.stop()
                await bootstrap_runtime.stop()

    asyncio.run(scenario())


def test_native_reward_restart_and_reconnect_converge_on_same_settlement() -> None:
    async def scenario() -> None:
        with TemporaryDirectory() as tempdir:
            wallets = {
                "reward-node-a": wallet_key(0),
                "reward-node-b": wallet_key(1),
            }
            bootstrap_path = Path(tempdir) / "bootstrap.sqlite3"
            follower_path = Path(tempdir) / "follower.sqlite3"
            bootstrap_service = _make_reward_service(bootstrap_path, start_time=1_700_010_000)
            follower_service = _make_reward_service(follower_path, start_time=1_700_011_000)
            bootstrap_runtime = NodeRuntime(service=bootstrap_service, listen_host="127.0.0.1", listen_port=0, ping_interval=0.2)
            await bootstrap_runtime.start()
            follower_runtime = NodeRuntime(
                service=follower_service,
                listen_host="127.0.0.1",
                listen_port=0,
                outbound_peers=[OutboundPeer("127.0.0.1", bootstrap_runtime.bound_port)],
                connect_interval=0.1,
                ping_interval=0.2,
            )
            await follower_runtime.start()
            restarted_runtime = None
            try:
                await _wait_until(lambda: bootstrap_runtime.connected_peer_count() == 1)
                _register_reward_node(bootstrap_service, wallet=wallets["reward-node-a"], node_id="reward-node-a", declared_port=bootstrap_runtime.bound_port)
                _register_reward_node(bootstrap_service, wallet=wallets["reward-node-b"], node_id="reward-node-b", declared_port=follower_runtime.bound_port)
                first_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, wallets["reward-node-a"].address)
                await _wait_for_tip(follower_service, first_block.block_hash())

                assignment = bootstrap_service.native_reward_assignments(epoch_index=0, node_id="reward-node-a")[0]
                window_index = assignment["candidate_check_windows"][0]
                verifier_node_id = assignment["verifier_committees"][str(window_index)][0]
                attestation_tx = _build_attestation_bundle_transaction(
                    epoch_index=0,
                    window_index=window_index,
                    candidate_node_id="reward-node-a",
                    verifier_node_id=verifier_node_id,
                    verifier_wallet=wallets[verifier_node_id],
                    endpoint_commitment=f"127.0.0.1:{bootstrap_runtime.bound_port}",
                    concentration_key="demo:reward-node-a",
                )
                await follower_runtime.submit_transaction(attestation_tx)
                await _wait_until(lambda: bootstrap_service.find_transaction(attestation_tx.txid()) is not None)
                second_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, wallets["reward-node-a"].address)
                await _wait_for_tip(follower_service, second_block.block_hash())

                await follower_runtime.stop()
                third_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, wallets["reward-node-a"].address)
                fourth_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, wallets["reward-node-a"].address)
                closing_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, wallets["reward-node-a"].address)

                restarted_service = _make_reward_service(follower_path, start_time=1_700_012_000)
                restarted_runtime = NodeRuntime(
                    service=restarted_service,
                    listen_host="127.0.0.1",
                    listen_port=0,
                    outbound_peers=[OutboundPeer("127.0.0.1", bootstrap_runtime.bound_port)],
                    connect_interval=0.1,
                    ping_interval=0.2,
                )
                await restarted_runtime.start()
                await _wait_for_tip(restarted_service, closing_block.block_hash())

                assert restarted_service.native_reward_settlement_diagnostics(epoch_index=0) == bootstrap_service.native_reward_settlement_diagnostics(epoch_index=0)
                assert restarted_service.native_reward_epoch_state(epoch_index=0)["comparison_keys"] == bootstrap_service.native_reward_epoch_state(epoch_index=0)["comparison_keys"]
                inspect = restarted_service.inspect_block(block_hash=closing_block.block_hash())
                assert inspect is not None
                assert inspect["node_reward_payouts"] == bootstrap_service.inspect_block(block_hash=closing_block.block_hash())["node_reward_payouts"]
                assert third_block.block_hash() != fourth_block.block_hash()
            finally:
                if restarted_runtime is not None:
                    await restarted_runtime.stop()
                else:
                    await follower_runtime.stop()
                await bootstrap_runtime.stop()

    asyncio.run(scenario())


def test_native_reward_template_miner_restart_near_epoch_close_keeps_auto_settlement_consistent() -> None:
    async def scenario() -> None:
        with TemporaryDirectory() as tempdir:
            reward_a = wallet_key(0)
            reward_b = wallet_key(1)
            bootstrap_service = _make_reward_service(Path(tempdir) / "bootstrap.sqlite3", start_time=1_700_020_000)
            follower_service = _make_reward_service(Path(tempdir) / "follower.sqlite3", start_time=1_700_021_000)
            bootstrap_runtime = NodeRuntime(
                service=bootstrap_service,
                listen_host="127.0.0.1",
                listen_port=0,
                http_host="127.0.0.1",
                http_port=_free_port(),
                ping_interval=0.2,
            )
            await bootstrap_runtime.start()
            follower_runtime = NodeRuntime(
                service=follower_service,
                listen_host="127.0.0.1",
                listen_port=0,
                outbound_peers=[OutboundPeer("127.0.0.1", bootstrap_runtime.bound_port)],
                connect_interval=0.1,
                ping_interval=0.2,
            )
            await follower_runtime.start()
            try:
                await _wait_until(lambda: bootstrap_runtime.connected_peer_count() == 1)
                _register_reward_node(bootstrap_service, wallet=reward_a, node_id="reward-node-a", declared_port=bootstrap_runtime.bound_port)
                _register_reward_node(bootstrap_service, wallet=reward_b, node_id="reward-node-b", declared_port=follower_runtime.bound_port)
                first_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, reward_a.address)
                await _wait_for_tip(follower_service, first_block.block_hash())

                assignment = bootstrap_service.native_reward_assignments(epoch_index=0, node_id="reward-node-a")[0]
                window_index = assignment["candidate_check_windows"][0]
                verifier_node_id = assignment["verifier_committees"][str(window_index)][0]
                verifier_wallet = reward_a if verifier_node_id == "reward-node-a" else reward_b
                attestation_tx = _build_attestation_bundle_transaction(
                    epoch_index=0,
                    window_index=window_index,
                    candidate_node_id="reward-node-a",
                    verifier_node_id=verifier_node_id,
                    verifier_wallet=verifier_wallet,
                    endpoint_commitment=f"127.0.0.1:{bootstrap_runtime.bound_port}",
                    concentration_key="demo:reward-node-a",
                )
                await follower_runtime.submit_transaction(attestation_tx)
                await _wait_until(lambda: bootstrap_service.find_transaction(attestation_tx.txid()) is not None)
                second_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, reward_a.address)
                await _wait_for_tip(follower_service, second_block.block_hash())

                third_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, reward_a.address)
                fourth_block = await _mine_and_announce(bootstrap_runtime, bootstrap_service, reward_a.address)
                await _wait_for_tip(follower_service, fourth_block.block_hash())
                assert bootstrap_service.chain_tip() is not None and bootstrap_service.chain_tip().height == 3

                worker_one = MinerWorker(
                    MinerWorkerConfig(
                        network="devnet",
                        payout_address=reward_a.address,
                        node_urls=(f"http://127.0.0.1:{bootstrap_runtime.http_bound_port}",),
                        miner_id="reward-worker-a",
                        nonce_batch_size=250_000,
                        mining_min_interval_seconds=0.0,
                        run_seconds=0.4,
                    )
                )
                result_one = await asyncio.to_thread(worker_one.run)
                assert result_one["accepted_blocks"] >= 1
                await _wait_until(lambda: bootstrap_service.chain_tip() is not None and bootstrap_service.chain_tip().height >= 4)
                close_hash = bootstrap_service.get_block_by_height(4).block_hash()
                await _wait_for_tip(follower_service, close_hash)

                worker_two = MinerWorker(
                    MinerWorkerConfig(
                        network="devnet",
                        payout_address=reward_a.address,
                        node_urls=(f"http://127.0.0.1:{bootstrap_runtime.http_bound_port}",),
                        miner_id="reward-worker-b",
                        nonce_batch_size=250_000,
                        mining_min_interval_seconds=0.0,
                        run_seconds=0.4,
                    )
                )
                result_two = await asyncio.to_thread(worker_two.run)
                assert result_two["accepted_blocks"] >= 1

                settlements = bootstrap_service.native_reward_settlement_diagnostics(epoch_index=0)
                assert len(settlements) == 1
                assert settlements[0]["submission_mode"] == "auto"
                inspect = bootstrap_service.inspect_block(block_hash=close_hash)
                assert inspect is not None
                assert inspect["node_reward_payouts"] == [
                    {
                        "recipient": reward_a.address,
                        "amount_chipbits": settlements[0]["distributed_node_reward_chipbits"],
                    }
                ]
                assert follower_service.native_reward_settlement_diagnostics(epoch_index=0) == settlements
            finally:
                await follower_runtime.stop()
                await bootstrap_runtime.stop()

    asyncio.run(scenario())
