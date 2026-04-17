from chipcoin.consensus.economics import node_reward_pool_chipbits
from chipcoin.consensus.nodes import InMemoryNodeRegistryView, NodeRecord, active_node_records, select_rewarded_nodes
from chipcoin.consensus.params import MAINNET_PARAMS
from tests.helpers import wallet_key


def _registry_with_active_nodes(count: int, *, last_renewed_height: int = 0) -> InMemoryNodeRegistryView:
    records = []
    for index in range(count):
        records.append(
            NodeRecord(
                node_id=f"node-{index:02d}",
                payout_address=wallet_key(index % 3).address,
                owner_pubkey=(index + 1).to_bytes(33, "big"),
                registered_height=0,
                last_renewed_height=last_renewed_height,
            )
        )
    return InMemoryNodeRegistryView.from_records(records)


def test_zero_distributed_node_reward_when_there_are_zero_active_records() -> None:
    registry = _registry_with_active_nodes(0)
    winners = select_rewarded_nodes(
        registry,
        height=99,
        previous_block_hash="00" * 32,
        node_reward_pool_chipbits=node_reward_pool_chipbits(99, MAINNET_PARAMS),
        params=MAINNET_PARAMS,
    )

    assert winners == []


def test_zero_reward_on_non_epoch_blocks() -> None:
    registry = _registry_with_active_nodes(3)
    winners = select_rewarded_nodes(
        registry,
        height=98,
        previous_block_hash="11" * 32,
        node_reward_pool_chipbits=node_reward_pool_chipbits(98, MAINNET_PARAMS),
        params=MAINNET_PARAMS,
    )

    assert winners == []


def test_all_active_records_participate_on_epoch_closing_blocks() -> None:
    registry = _registry_with_active_nodes(3)
    winners = select_rewarded_nodes(
        registry,
        height=99,
        previous_block_hash="22" * 32,
        node_reward_pool_chipbits=node_reward_pool_chipbits(99, MAINNET_PARAMS),
        params=MAINNET_PARAMS,
    )

    assert len(winners) == 3
    assert [winner.node_id for winner in winners] == ["node-00", "node-01", "node-02"]


def test_deterministic_ordering_is_by_node_id_then_payout_address() -> None:
    registry = InMemoryNodeRegistryView.from_records(
        [
            NodeRecord(
                node_id="node-b",
                payout_address=wallet_key(2).address,
                owner_pubkey=(2).to_bytes(33, "big"),
                registered_height=0,
                last_renewed_height=0,
            ),
            NodeRecord(
                node_id="node-a",
                payout_address=wallet_key(1).address,
                owner_pubkey=(1).to_bytes(33, "big"),
                registered_height=0,
                last_renewed_height=0,
            ),
        ]
    )
    winners = select_rewarded_nodes(
        registry,
        height=99,
        previous_block_hash="33" * 32,
        node_reward_pool_chipbits=node_reward_pool_chipbits(99, MAINNET_PARAMS),
        params=MAINNET_PARAMS,
    )

    assert [winner.node_id for winner in winners] == ["node-a", "node-b"]
    assert [winner.payout_address for winner in winners] == [wallet_key(1).address, wallet_key(2).address]


def test_deterministic_remainder_distribution_is_stable() -> None:
    registry = _registry_with_active_nodes(3)
    winners = select_rewarded_nodes(
        registry,
        height=99,
        previous_block_hash="44" * 32,
        node_reward_pool_chipbits=5_000_000_000,
        params=MAINNET_PARAMS,
    )

    assert [winner.reward_chipbits for winner in winners] == [1_666_666_667, 1_666_666_667, 1_666_666_666]
    assert sum(winner.reward_chipbits for winner in winners) == 5_000_000_000


def test_exact_epoch_split_on_reward_bearing_block() -> None:
    registry = _registry_with_active_nodes(4)
    winners = select_rewarded_nodes(
        registry,
        height=99,
        previous_block_hash="55" * 32,
        node_reward_pool_chipbits=node_reward_pool_chipbits(99, MAINNET_PARAMS),
        params=MAINNET_PARAMS,
    )

    assert len(winners) == 4
    assert [winner.reward_chipbits for winner in winners] == [1_250_000_000] * 4
    assert sum(winner.reward_chipbits for winner in winners) == 5_000_000_000


def test_active_record_set_is_based_on_pre_block_registry_view() -> None:
    registry = _registry_with_active_nodes(2, last_renewed_height=0)
    active = active_node_records(registry, height=99, params=MAINNET_PARAMS)

    assert [record.node_id for record in active] == ["node-00", "node-01"]
