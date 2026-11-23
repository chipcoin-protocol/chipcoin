"""Combined RC/reward regression: a renewal does not invalidate older mining work."""

from __future__ import annotations

import asyncio

import pytest

from chipcoin.consensus.models import OutPoint
from chipcoin.interfaces.http_api import HttpApiApp
from chipcoin.node.runtime import NodeRuntime, RewardNodeAutomationConfig
from tests.helpers import put_wallet_utxo
from tests.integration.pool.test_block_submission import _solved_block, _submit
from tests.node.test_mainnet_pq_end_to_end import _mine, _register_reward_node, _wallet
from tests.node.test_reward_node_automation import _write_wallet_file
from tests.node.test_reward_renewal_maturity import _mainnet_reward_service


@pytest.mark.parametrize("submit_mode", ["legacy", "full"])
def test_reward_renewal_keeps_prior_template_valid_on_same_tip(tmp_path, submit_mode):
    service = _mainnet_reward_service(tmp_path / "node.sqlite3", start_time=1_800_000_000)
    miner, owner = _wallet(1), _wallet(3)
    owner_file = _write_wallet_file(tmp_path / "owner.json", owner)
    put_wallet_utxo(service, OutPoint(txid="aa" * 32, index=0), value=300_000_000,
                    owner=owner, is_coinbase=False)
    _register_reward_node(service, wallet=owner, node_id="reward-a", port=19001)
    for _ in range(9):
        _mine(service, miner.address)
    put_wallet_utxo(service, OutPoint(txid="bb" * 32, index=0), value=1,
                    owner=owner, height=9, is_coinbase=True)

    old_template = service.get_block_template(payout_address=miner.address, miner_id="test-worker")
    old_block = _solved_block(old_template)
    runtime = NodeRuntime(service=service, reward_automation=RewardNodeAutomationConfig(
        node_id="reward-a", owner_wallet_path=owner_file, attest_wallet_path=owner_file,
        auto_attest_enabled=False,
    ))
    asyncio.run(runtime._run_reward_automation_once())
    renewal = next(tx for tx in service.list_mempool_transactions()
                   if tx.metadata.get("kind") == "renew_reward_node")
    assert OutPoint(txid="bb" * 32, index=0) not in {item.previous_output for item in renewal.inputs}

    new_template = service.get_block_template(payout_address=miner.address, miner_id="test-worker")
    assert new_template["previous_block_hash"] == old_template["previous_block_hash"]
    assert new_template["transactions"] != old_template["transactions"]
    assert old_template["template_id"] in service._mining_templates

    app = HttpApiApp(service)
    response = _submit(app, old_block, old_template["template_id"] if submit_mode == "legacy" else None)
    assert response["status"] == "200 OK"
    assert response["body"]["reason"] == "accepted"
    assert service.chain_tip().height == 10
    assert any(tx.txid() == renewal.txid() for tx in service.list_mempool_transactions())
    if submit_mode == "full":
        assert _submit(app, old_block)["body"]["reason"] == "already_accepted"

    next_template = service.get_block_template(payout_address=miner.address, miner_id="test-worker")
    assert any(row["txid"] == renewal.txid() for row in next_template["transactions"])
    next_block = _solved_block(next_template)
    assert _submit(app, next_block)["body"]["reason"] == "accepted"
    assert service.get_registered_node("reward-a").last_renewed_height == 11
