"""Reward input selection against the Mainnet coinbase maturity boundary."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from chipcoin.consensus.genesis import mine_genesis
from chipcoin.consensus.models import OutPoint
from chipcoin.interfaces.cli import _build_wallet_transaction
from chipcoin.consensus.network_identity import PUBLIC_MAINNET_CHAIN_ID
from chipcoin.consensus.params import MAINNET_PARAMS
from chipcoin.node.runtime import NodeRuntime, RewardNodeAutomationConfig
from chipcoin.node.service import NodeService
from chipcoin.wallet.selection import select_inputs
from chipcoin.wallet.signer import TransactionSigner
from tests.helpers import put_wallet_utxo, wallet_key
from tests.node.test_mainnet_pq_end_to_end import (
    MAINNET_PQ_TEST_PARAMS,
    _mine,
    _register_reward_node,
    _wallet,
)
from tests.node.test_reward_node_automation import _write_wallet_file


def test_mainnet_spendable_outputs_use_next_block_maturity_boundary(tmp_path: Path) -> None:
    service = NodeService.open_sqlite(tmp_path / "boundary.sqlite3", network="mainnet", params=MAINNET_PARAMS)
    owner = wallet_key(0)
    service.chain_tip = lambda: SimpleNamespace(height=14398)  # type: ignore[method-assign]
    immature = OutPoint(txid="11" * 32, index=0)
    boundary = OutPoint(txid="22" * 32, index=0)
    ordinary = OutPoint(txid="33" * 32, index=0)
    put_wallet_utxo(service, immature, value=1, owner=owner, height=14300, is_coinbase=True)
    put_wallet_utxo(service, boundary, value=20, owner=owner, height=14299, is_coinbase=True)
    put_wallet_utxo(service, ordinary, value=20, owner=owner, height=14398, is_coinbase=False)

    # Candidate height 14399: origin 14300 is 99 blocks old, origin 14299 is 100.
    candidates = service.list_spendable_outputs(owner.address)
    assert {candidate.txid for candidate in candidates} == {boundary.txid, ordinary.txid}
    assert {candidate.txid for candidate in select_inputs(candidates, 10).selected} == {boundary.txid}
    diagnostics = {row["txid"]: row for row in service.utxo_diagnostics(owner.address)}
    assert diagnostics[immature.txid]["mature"] is False
    assert diagnostics[boundary.txid]["mature"] is True
    assert diagnostics[ordinary.txid]["mature"] is True
    payment = TransactionSigner(owner).build_signed_transaction(
        spend_candidates=candidates, recipient=wallet_key(1).address,
        amount_chipbits=10, fee_chipbits=1, network="mainnet",
    )
    assert immature not in {entry.previous_output for entry in payment.transaction.inputs}

    service.chain_tip = lambda: SimpleNamespace(height=14399)  # type: ignore[method-assign]
    assert {candidate.txid for candidate in service.list_spendable_outputs(owner.address)} == {
        immature.txid, boundary.txid, ordinary.txid,
    }


def test_only_immature_coinbase_outputs_cannot_fund_a_transaction(tmp_path: Path) -> None:
    service = NodeService.open_sqlite(tmp_path / "immature.sqlite3", network="mainnet", params=MAINNET_PARAMS)
    owner = wallet_key(0)
    service.chain_tip = lambda: SimpleNamespace(height=14398)  # type: ignore[method-assign]
    put_wallet_utxo(service, OutPoint(txid="44" * 32, index=0), value=1_000_000_000,
                    owner=owner, height=14300, is_coinbase=True)
    assert service.list_spendable_outputs(owner.address) == []
    assert service.balance_diagnostics(owner.address)["spendable_balance_chipbits"] == 0
    with pytest.raises(ValueError, match="Insufficient spendable balance"):
        select_inputs(service.list_spendable_outputs(owner.address), 1)
    put_wallet_utxo(service, OutPoint(txid="55" * 32, index=0), value=5,
                    owner=owner, is_coinbase=False)
    with pytest.raises(ValueError, match="Insufficient spendable balance"):
        select_inputs(service.list_spendable_outputs(owner.address), 10)


def test_wallet_send_selection_skips_immature_and_pending_inputs(tmp_path: Path) -> None:
    service = _mainnet_reward_service(tmp_path / "wallet-send.sqlite3", start_time=1_800_000_000)
    owner, recipient = _wallet(3), _wallet(4)
    immature = OutPoint(txid="11" * 32, index=0)
    first_funding = OutPoint(txid="22" * 32, index=0)
    second_funding = OutPoint(txid="33" * 32, index=0)
    put_wallet_utxo(service, immature, value=1, owner=owner, height=0, is_coinbase=True)
    put_wallet_utxo(service, first_funding, value=20, owner=owner, is_coinbase=False)
    put_wallet_utxo(service, second_funding, value=30, owner=owner, is_coinbase=False)
    args = SimpleNamespace(to=recipient.address, amount=10, fee=1, change_address=None)

    first = _build_wallet_transaction(service, owner, args)
    assert {item.previous_output for item in first.transaction.inputs} == {first_funding}
    service.receive_transaction(first.transaction)
    second = _build_wallet_transaction(service, owner, args)
    assert {item.previous_output for item in second.transaction.inputs} == {second_funding}
    service.receive_transaction(second.transaction)
    assert immature not in {item.previous_output for item in second.transaction.inputs}
    with pytest.raises(ValueError, match="Insufficient spendable balance"):
        _build_wallet_transaction(service, owner, args)


def _mainnet_reward_service(path: Path, *, start_time: int) -> NodeService:
    params = replace(MAINNET_PQ_TEST_PARAMS, coinbase_maturity=100)
    timestamps = iter(range(start_time, start_time + 1000))
    service = NodeService.open_sqlite(path, network="mainnet", params=params,
                                      time_provider=lambda: next(timestamps))
    service.install_or_verify_genesis(mine_genesis(timestamp=1_799_999_999, bits=params.genesis_bits),
                                      chain_id=PUBLIC_MAINNET_CHAIN_ID)
    return service


def test_pq_reward_renewal_recovers_and_survives_restart_and_next_epoch(tmp_path: Path) -> None:
    database = tmp_path / "reward.sqlite3"
    service = _mainnet_reward_service(database, start_time=1_800_000_000)
    miner, owner, verifier = _wallet(1), _wallet(3), _wallet(4)
    wallet_path = _write_wallet_file(tmp_path / "owner.json", owner)
    verifier_path = _write_wallet_file(tmp_path / "verifier.json", verifier)
    put_wallet_utxo(service, OutPoint(txid="aa" * 32, index=0), value=300_000_000,
                    owner=owner, is_coinbase=False)
    put_wallet_utxo(service, OutPoint(txid="bb" * 32, index=0), value=300_000_000,
                    owner=verifier, is_coinbase=False)
    _register_reward_node(service, wallet=owner, node_id="reward-a", port=19001)
    _register_reward_node(service, wallet=verifier, node_id="reward-b", port=19002)
    for _ in range(9):
        _mine(service, miner.address)
    assert service.chain_tip().height == 9
    immature = OutPoint(txid="cc" * 32, index=0)
    put_wallet_utxo(service, immature, value=1, owner=owner, height=9, is_coinbase=True)
    runtime = NodeRuntime(service=service, reward_automation=RewardNodeAutomationConfig(
        node_id="reward-a", owner_wallet_path=wallet_path, attest_wallet_path=wallet_path,
        auto_renew_enabled=True, auto_attest_enabled=True,
    ))

    original_submit = runtime.submit_transaction
    failures = 0

    async def fail_once(transaction):
        nonlocal failures
        if failures == 0:
            failures += 1
            raise OSError("transient local submission failure")
        await original_submit(transaction)

    runtime.submit_transaction = fail_once  # type: ignore[method-assign]
    with pytest.raises(OSError, match="transient"):
        asyncio.run(runtime._run_reward_automation_once())
    assert failures == 1
    assert not any(tx.metadata.get("kind") == "renew_reward_node" for tx in service.list_mempool_transactions())
    runtime.submit_transaction = original_submit  # type: ignore[method-assign]
    asyncio.run(runtime._run_reward_automation_once())
    renewals = [tx for tx in service.list_mempool_transactions()
                if tx.metadata.get("kind") == "renew_reward_node"]
    assert len(renewals) == 1
    assert immature not in {entry.previous_output for entry in renewals[0].inputs}
    _mine(service, miner.address)
    assert service.get_registered_node("reward-a").last_renewed_height == 10
    verifier_runtime = NodeRuntime(service=service, reward_automation=RewardNodeAutomationConfig(
        node_id="reward-b", owner_wallet_path=verifier_path, attest_wallet_path=verifier_path,
        auto_renew_enabled=True, auto_attest_enabled=True,
    ))
    saw_attestation = False
    for _ in range(9):
        asyncio.run(runtime._run_reward_automation_once())
        asyncio.run(verifier_runtime._run_reward_automation_once())
        saw_attestation |= any(tx.metadata.get("kind") == "reward_attestation_bundle"
                               for tx in service.list_mempool_transactions())
        _mine(service, miner.address)
    assert saw_attestation
    assert service.chain_tip().height == 19
    service.connection.close()

    restarted = _mainnet_reward_service(database, start_time=1_800_002_000)
    restarted_runtime = NodeRuntime(service=restarted, reward_automation=RewardNodeAutomationConfig(
        node_id="reward-a", owner_wallet_path=wallet_path, attest_wallet_path=wallet_path,
        auto_renew_enabled=True, auto_attest_enabled=True,
    ))
    assert restarted.chain_tip().height == 19
    new_immature = OutPoint(txid="dd" * 32, index=0)
    put_wallet_utxo(restarted, new_immature, value=1, owner=owner, height=19, is_coinbase=True)
    asyncio.run(restarted_runtime._run_reward_automation_once())
    next_renewals = [tx for tx in restarted.list_mempool_transactions()
                     if tx.metadata.get("kind") == "renew_reward_node" and tx.metadata.get("renewal_epoch") == "2"]
    assert len(next_renewals) == 1
    assert new_immature not in {entry.previous_output for entry in next_renewals[0].inputs}
    _mine(restarted, miner.address)
    assert restarted.get_registered_node("reward-a").last_renewed_height == 20
