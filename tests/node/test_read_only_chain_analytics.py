"""Regression tests for read-only historical analytics shortcuts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from chipcoin.consensus.models import OutPoint
from chipcoin.node.service import NodeService
from tests.helpers import signed_payment, wallet_key
from tests.node.test_http_api import MAINNET_PARAMS, _make_service, _mine_block
from tests.node.test_native_reward_slice import (
    _make_service as _make_reward_service,
    _mine_local_block,
    _register_reward_node,
)


def test_coinbase_only_analytics_skip_fee_replay(monkeypatch) -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "node.sqlite3")
        for _ in range(3):
            service.apply_block(_mine_block(service.build_candidate_block("CHCminer").block))

        def replay_forbidden(_height):
            raise AssertionError("coinbase-only analytics must not replay state")

        monkeypatch.setattr(service, "_replay_chain_state_before_height", replay_forbidden)
        assert len(service.reward_history("CHCminer", limit=10)) == 3
        assert service.top_miners(limit=1)[0]["total_fees_chipbits"] == 0
        history = service.mining_history("CHCminer", limit=10)
        assert len(history) == 3
        assert all(row["fees_chipbits"] == 0 for row in history)
        assert all(row["node_reward_recipient_count"] == 0 for row in history)


def test_mining_history_keeps_payment_fees_without_replay(monkeypatch) -> None:
    with TemporaryDirectory() as tempdir:
        timestamps = iter(range(1_700_000_000, 1_700_000_400))
        service = NodeService.open_sqlite(
            Path(tempdir) / "node.sqlite3",
            params=replace(MAINNET_PARAMS, coinbase_maturity=1),
            time_provider=lambda: next(timestamps),
        )
        miner = wallet_key(0)
        first = _mine_block(service.build_candidate_block(miner.address).block)
        service.apply_block(first)
        coinbase = first.transactions[0]
        payment = signed_payment(
            OutPoint(txid=coinbase.txid(), index=0),
            value=int(coinbase.outputs[0].value),
            sender=miner,
            fee=1_000,
        )
        service.receive_transaction(payment)
        second = _mine_block(service.build_candidate_block(miner.address).block)
        service.apply_block(second)
        original_replay = service._replay_chain_state_before_height
        replayed = []

        def count_replay(height):
            replayed.append(height)
            return original_replay(height)

        monkeypatch.setattr(service, "_replay_chain_state_before_height", count_replay)
        history = service.mining_history(miner.address, limit=10)
        assert [row["fees_chipbits"] for row in history] == [1_000, 0]
        assert replayed == []
        assert service.top_miners(limit=1)[0]["total_fees_chipbits"] == 1_000
        assert [row["reward_type"] for row in service.reward_history(miner.address, limit=10)] == [
            "miner_subsidy", "fees", "miner_subsidy",
        ]


def test_mining_history_uses_pre_block_registry_and_snapshot_fallback(monkeypatch) -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_reward_service(Path(tempdir) / "node.sqlite3")
        miner = wallet_key(2)
        _register_reward_node(service, wallet=wallet_key(0), node_id="reward-node-a", port=19001)
        first = _mine_local_block(service, miner.address)
        assert len(first.transactions) > 1
        _mine_local_block(service, miner.address)

        # Observe the registry supplied to winner selection. Registration in
        # block zero must be visible at height one, not at height zero.
        monkeypatch.setattr(
            "chipcoin.node.service.select_rewarded_nodes",
            lambda registry_view, **_kwargs: registry_view.list_records(),
        )
        history = service.mining_history(miner.address, limit=10, descending=False)
        assert [row["node_reward_recipient_count"] for row in history] == [0, 1]

        # Snapshot-backed nodes retain the existing historical replay path.
        replayed = []
        original_replay = service._replay_chain_state_before_height

        def count_replay(height):
            replayed.append(height)
            return original_replay(height)

        monkeypatch.setattr(service, "snapshot_anchor", lambda: SimpleNamespace(height=0))
        monkeypatch.setattr(service, "_replay_chain_state_before_height", count_replay)
        snapshot_history = service.mining_history(miner.address, limit=10, descending=False)
        assert snapshot_history == history
        assert replayed.count(1) >= 1


def test_mining_history_does_not_hide_missing_prior_block(monkeypatch) -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "node.sqlite3")
        for _ in range(2):
            service.apply_block(_mine_block(service.build_candidate_block("CHCminer").block))
        original_get = service.get_block_by_height
        monkeypatch.setattr(
            service, "get_block_by_height",
            lambda height: None if height == 0 else original_get(height),
        )
        with pytest.raises(ValueError, match="Missing active-chain block at height 0"):
            service.mining_history("CHCminer")


def test_fee_inference_falls_back_for_nonactive_block(monkeypatch) -> None:
    with TemporaryDirectory() as tempdir:
        service = _make_service(Path(tempdir) / "node.sqlite3")
        for _ in range(2):
            service.apply_block(_mine_block(service.build_candidate_block("CHCminer").block))
        block = service.get_block_by_height(1)
        assert block is not None
        fallback_calls = []

        def fallback(height, candidate):
            fallback_calls.append((height, candidate))
            return 1234

        monkeypatch.setattr(service, "_block_total_fees_chipbits", fallback)
        assert service._active_block_fees_chipbits(0, block) == 1234
        assert service._active_block_fees_chipbits(2, block) == 1234
        coinbase = block.transactions[0]
        malformed = replace(block, transactions=(
            replace(coinbase, outputs=(replace(coinbase.outputs[0], value=0),)),
        ))
        assert service._active_block_fees_chipbits(1, malformed) == 1234
        assert fallback_calls == [(0, block), (2, block), (1, malformed)]
