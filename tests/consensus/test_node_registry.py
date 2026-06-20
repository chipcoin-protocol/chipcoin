from chipcoin.consensus.economics import node_reward_pool_chipbits
from chipcoin.consensus.epoch_settlement import REGISTER_REWARD_NODE_KIND, RENEW_REWARD_NODE_KIND
from chipcoin.consensus.models import Transaction
from chipcoin.consensus.nodes import (
    InMemoryNodeRegistryView,
    NodeRecord,
    active_node_records,
    apply_special_node_transaction,
    is_special_node_transaction,
    select_rewarded_nodes,
    special_node_transaction_signature_digest,
    SPECIAL_NODE_SIGNATURE_V2_ACTIVATION_HEIGHT,
    special_node_transaction_signature_digest_v2,
)
from chipcoin.consensus.params import DEVNET_PARAMS, MAINNET_PARAMS, TESTNET_PARAMS
from chipcoin.consensus.utxo import InMemoryUtxoView
from chipcoin.consensus.validation import (
    ContextualValidationError,
    ValidationContext,
    validate_transaction,
)
from chipcoin.crypto.signatures import sign_digest
from tests.helpers import wallet_key


def _register_node_transaction(*, node_id: str, owner_index: int = 0, payout_address: str | None = None) -> Transaction:
    owner = wallet_key(owner_index)
    metadata = {
        "kind": "register_node",
        "node_id": node_id,
        "payout_address": owner.address if payout_address is None else payout_address,
        "owner_pubkey_hex": owner.public_key.hex(),
        "owner_signature_hex": "",
    }
    unsigned = Transaction(version=1, inputs=(), outputs=(), metadata=metadata)
    signed_metadata = dict(metadata)
    signed_metadata["owner_signature_version"] = "v2"
    signed_metadata["owner_signature_network"] = "mainnet"
    unsigned_v2 = Transaction(version=1, inputs=(), outputs=(), metadata=signed_metadata)
    signed_metadata["owner_signature_hex"] = sign_digest(owner.private_key, special_node_transaction_signature_digest_v2(unsigned_v2, network="mainnet")).hex()
    return Transaction(version=1, inputs=(), outputs=(), metadata=signed_metadata)


def _register_reward_node_transaction(*, node_id: str, owner_index: int = 0, payout_address: str | None = None) -> Transaction:
    owner = wallet_key(owner_index)
    node_key = wallet_key((owner_index + 1) % 3)
    metadata = {
        "kind": REGISTER_REWARD_NODE_KIND,
        "node_id": node_id,
        "payout_address": owner.address if payout_address is None else payout_address,
        "owner_pubkey_hex": owner.public_key.hex(),
        "node_pubkey_hex": node_key.public_key.hex(),
        "declared_host": f"{node_id}.example",
        "declared_port": "18444",
        "registration_fee_chipbits": str(MAINNET_PARAMS.register_node_fee_chipbits),
        "owner_signature_hex": "",
    }
    unsigned = Transaction(version=1, inputs=(), outputs=(), metadata=metadata)
    signed_metadata = dict(metadata)
    signed_metadata["owner_signature_version"] = "v2"
    signed_metadata["owner_signature_network"] = "mainnet"
    unsigned_v2 = Transaction(version=1, inputs=(), outputs=(), metadata=signed_metadata)
    signed_metadata["owner_signature_hex"] = sign_digest(owner.private_key, special_node_transaction_signature_digest_v2(unsigned_v2, network="mainnet")).hex()
    return Transaction(version=1, inputs=(), outputs=(), metadata=signed_metadata)


def _renew_node_transaction(*, node_id: str, owner_index: int = 0, renewal_epoch: int = 0) -> Transaction:
    owner = wallet_key(owner_index)
    metadata = {
        "kind": "renew_node",
        "node_id": node_id,
        "renewal_epoch": str(renewal_epoch),
        "owner_pubkey_hex": owner.public_key.hex(),
        "owner_signature_hex": "",
    }
    unsigned = Transaction(version=1, inputs=(), outputs=(), metadata=metadata)
    signed_metadata = dict(metadata)
    signed_metadata["owner_signature_version"] = "v2"
    signed_metadata["owner_signature_network"] = "mainnet"
    unsigned_v2 = Transaction(version=1, inputs=(), outputs=(), metadata=signed_metadata)
    signed_metadata["owner_signature_hex"] = sign_digest(owner.private_key, special_node_transaction_signature_digest_v2(unsigned_v2, network="mainnet")).hex()
    return Transaction(version=1, inputs=(), outputs=(), metadata=signed_metadata)


def _renew_reward_node_transaction(*, node_id: str, owner_index: int = 0, renewal_epoch: int = 0) -> Transaction:
    owner = wallet_key(owner_index)
    metadata = {
        "kind": RENEW_REWARD_NODE_KIND,
        "node_id": node_id,
        "renewal_epoch": str(renewal_epoch),
        "owner_pubkey_hex": owner.public_key.hex(),
        "declared_host": f"{node_id}.renewed.example",
        "declared_port": "18445",
        "renewal_fee_chipbits": str(MAINNET_PARAMS.renew_node_fee_chipbits),
        "owner_signature_hex": "",
    }
    unsigned = Transaction(version=1, inputs=(), outputs=(), metadata=metadata)
    signed_metadata = dict(metadata)
    signed_metadata["owner_signature_version"] = "v2"
    signed_metadata["owner_signature_network"] = "mainnet"
    unsigned_v2 = Transaction(version=1, inputs=(), outputs=(), metadata=signed_metadata)
    signed_metadata["owner_signature_hex"] = sign_digest(owner.private_key, special_node_transaction_signature_digest_v2(unsigned_v2, network="mainnet")).hex()
    return Transaction(version=1, inputs=(), outputs=(), metadata=signed_metadata)


def _register_reward_node_transaction_v1(*, node_id: str, owner_index: int = 0) -> Transaction:
    owner = wallet_key(owner_index)
    node_key = wallet_key((owner_index + 1) % 3)
    metadata = {
        "kind": REGISTER_REWARD_NODE_KIND,
        "node_id": node_id,
        "payout_address": owner.address,
        "owner_pubkey_hex": owner.public_key.hex(),
        "node_pubkey_hex": node_key.public_key.hex(),
        "declared_host": f"{node_id}.example",
        "declared_port": "18444",
        "registration_fee_chipbits": str(MAINNET_PARAMS.register_node_fee_chipbits),
        "owner_signature_hex": "",
    }
    unsigned = Transaction(version=1, inputs=(), outputs=(), metadata=metadata)
    signed_metadata = dict(metadata)
    signed_metadata["owner_signature_hex"] = sign_digest(owner.private_key, special_node_transaction_signature_digest(unsigned)).hex()
    return Transaction(version=1, inputs=(), outputs=(), metadata=signed_metadata)


def _expect_contextual_rejection(
    transaction: Transaction,
    *,
    network: str,
    height: int = 1,
    params=MAINNET_PARAMS,
) -> None:
    context = ValidationContext(
        height=height,
        median_time_past=0,
        params=params,
        utxo_view=InMemoryUtxoView(),
        network=network,
        node_registry_view=InMemoryNodeRegistryView(),
    )
    try:
        validate_transaction(transaction, context)
    except ContextualValidationError:
        return
    raise AssertionError("Expected special node transaction to be rejected.")


def test_special_node_v2_signature_is_bound_to_network() -> None:
    from chipcoin.wallet.signer import TransactionSigner

    activation_height = SPECIAL_NODE_SIGNATURE_V2_ACTIVATION_HEIGHT
    devnet_tx = TransactionSigner(wallet_key(0)).build_register_reward_node_transaction(
        node_id="devnet-node",
        payout_address=wallet_key(0).address,
        node_public_key_hex=wallet_key(1).public_key.hex(),
        declared_host="devnet-node.example",
        declared_port=18444,
        registration_fee_chipbits=DEVNET_PARAMS.register_node_fee_chipbits,
        network="devnet",
        height=activation_height,
    )
    testnet_tx = TransactionSigner(wallet_key(0)).build_register_reward_node_transaction(
        node_id="testnet-node",
        payout_address=wallet_key(0).address,
        node_public_key_hex=wallet_key(1).public_key.hex(),
        declared_host="testnet-node.example",
        declared_port=18444,
        registration_fee_chipbits=TESTNET_PARAMS.register_node_fee_chipbits,
        network="testnet",
        height=activation_height,
    )

    assert devnet_tx.metadata["owner_signature_version"] == "v2"
    assert devnet_tx.metadata["owner_signature_network"] == "devnet"
    _expect_contextual_rejection(devnet_tx, network="testnet", height=activation_height, params=TESTNET_PARAMS)
    _expect_contextual_rejection(testnet_tx, network="devnet", height=activation_height, params=DEVNET_PARAMS)


def test_special_node_signature_activation_schedule() -> None:
    from chipcoin.wallet.signer import TransactionSigner

    before_activation = SPECIAL_NODE_SIGNATURE_V2_ACTIVATION_HEIGHT - 1
    at_activation = SPECIAL_NODE_SIGNATURE_V2_ACTIVATION_HEIGHT
    signer = TransactionSigner(wallet_key(0))
    pre_activation_tx = signer.build_register_reward_node_transaction(
        node_id="pre-activation",
        payout_address=wallet_key(0).address,
        node_public_key_hex=wallet_key(1).public_key.hex(),
        declared_host="pre-activation.example",
        declared_port=18444,
        registration_fee_chipbits=TESTNET_PARAMS.register_node_fee_chipbits,
        network="testnet",
        height=before_activation,
    )
    activation_tx = signer.build_register_reward_node_transaction(
        node_id="activation",
        payout_address=wallet_key(0).address,
        node_public_key_hex=wallet_key(1).public_key.hex(),
        declared_host="activation.example",
        declared_port=18444,
        registration_fee_chipbits=TESTNET_PARAMS.register_node_fee_chipbits,
        network="testnet",
        height=at_activation,
    )

    assert "owner_signature_version" not in pre_activation_tx.metadata
    assert activation_tx.metadata["owner_signature_version"] == "v2"
    assert activation_tx.metadata["owner_signature_network"] == "testnet"


def test_special_node_v1_signature_compatibility_ends_at_activation() -> None:
    before_activation = SPECIAL_NODE_SIGNATURE_V2_ACTIVATION_HEIGHT - 1
    at_activation = SPECIAL_NODE_SIGNATURE_V2_ACTIVATION_HEIGHT
    devnet_tx = _register_reward_node_transaction_v1(node_id="legacy-devnet")
    devnet_context = ValidationContext(
        height=before_activation,
        median_time_past=0,
        params=DEVNET_PARAMS,
        utxo_view=InMemoryUtxoView(),
        network="devnet",
        node_registry_view=InMemoryNodeRegistryView(),
    )
    assert validate_transaction(devnet_tx, devnet_context) == 0

    testnet_tx = _register_reward_node_transaction_v1(node_id="legacy-testnet", owner_index=1)
    testnet_context = ValidationContext(
        height=before_activation,
        median_time_past=0,
        params=TESTNET_PARAMS,
        utxo_view=InMemoryUtxoView(),
        network="testnet",
        node_registry_view=InMemoryNodeRegistryView(),
    )
    assert validate_transaction(testnet_tx, testnet_context) == 0

    _expect_contextual_rejection(devnet_tx, network="devnet", height=at_activation, params=DEVNET_PARAMS)
    _expect_contextual_rejection(testnet_tx, network="testnet", height=at_activation, params=TESTNET_PARAMS)

    mainnet_tx = _register_reward_node_transaction_v1(node_id="legacy-mainnet", owner_index=2)
    _expect_contextual_rejection(mainnet_tx, network="mainnet", params=MAINNET_PARAMS)


def test_register_node_transaction_is_special_and_updates_registry() -> None:
    registry = InMemoryNodeRegistryView()
    transaction = _register_node_transaction(node_id="node-1")

    assert is_special_node_transaction(transaction) is True
    apply_special_node_transaction(transaction, height=7, registry_view=registry)
    record = registry.get_by_node_id("node-1")
    assert record is not None
    assert record.last_renewed_height == 7


def test_register_node_rejects_duplicate_owner_pubkey() -> None:
    registry = InMemoryNodeRegistryView.from_records(
        [
            NodeRecord(
                node_id="node-1",
                payout_address=wallet_key(0).address,
                owner_pubkey=wallet_key(0).public_key,
                registered_height=5,
                last_renewed_height=5,
            )
        ]
    )
    transaction = _register_node_transaction(node_id="node-2", owner_index=0)
    context = ValidationContext(height=6, median_time_past=0, params=MAINNET_PARAMS, utxo_view=InMemoryUtxoView(), node_registry_view=registry)

    try:
        validate_transaction(transaction, context)
    except ContextualValidationError:
        return
    raise AssertionError("Expected duplicate owner_pubkey register_node transaction to be rejected.")


def test_active_node_set_excludes_same_block_registration() -> None:
    registry = InMemoryNodeRegistryView.from_records(
        [
            NodeRecord(
                node_id="node-1",
                payout_address=wallet_key(0).address,
                owner_pubkey=wallet_key(0).public_key,
                registered_height=1000,
                last_renewed_height=1000,
            )
        ]
    )

    assert active_node_records(registry, height=1000, params=MAINNET_PARAMS) == []
    assert len(active_node_records(registry, height=1001, params=MAINNET_PARAMS)) == 1


def test_reward_selection_includes_all_active_nodes_and_is_deterministic() -> None:
    records = [
        NodeRecord(
            node_id=f"node-{index}",
            payout_address=wallet_key(index % 3).address + str(index),
            owner_pubkey=wallet_key(index % 3).public_key + bytes((index,)),
            registered_height=1,
            last_renewed_height=1,
        )
        for index in range(12)
    ]
    registry = InMemoryNodeRegistryView.from_records(records)

    winners = select_rewarded_nodes(
        registry,
        height=99,
        previous_block_hash="11" * 32,
        node_reward_pool_chipbits=node_reward_pool_chipbits(99, MAINNET_PARAMS),
        params=MAINNET_PARAMS,
    )

    assert len(winners) == 12
    assert winners[0].node_id == "node-0"
    assert winners[-1].node_id == "node-9"
    assert winners == select_rewarded_nodes(
        registry,
        height=99,
        previous_block_hash="11" * 32,
        node_reward_pool_chipbits=node_reward_pool_chipbits(99, MAINNET_PARAMS),
        params=MAINNET_PARAMS,
    )


def test_register_reward_node_transaction_is_special_and_updates_reward_registry_fields() -> None:
    registry = InMemoryNodeRegistryView()
    transaction = _register_reward_node_transaction(node_id="reward-node-1")

    assert is_special_node_transaction(transaction) is True
    apply_special_node_transaction(transaction, height=9, registry_view=registry)
    record = registry.get_by_node_id("reward-node-1")
    assert record is not None
    assert record.reward_registration is True
    assert record.node_pubkey is not None
    assert record.declared_host == "reward-node-1.example"
    assert record.declared_port == 18444


def test_register_reward_node_transaction_upgrades_legacy_node_registration() -> None:
    registry = InMemoryNodeRegistryView()
    legacy_transaction = _register_node_transaction(node_id="reward-node-legacy")
    apply_special_node_transaction(legacy_transaction, height=55, registry_view=registry)
    reward_transaction = _register_reward_node_transaction(node_id="reward-node-legacy")

    apply_special_node_transaction(reward_transaction, height=3053, registry_view=registry)

    record = registry.get_by_node_id("reward-node-legacy")
    assert record is not None
    assert record.registered_height == 55
    assert record.last_renewed_height == 3053
    assert record.reward_registration is True
    assert record.node_pubkey is not None
    assert record.declared_host == "reward-node-legacy.example"
    assert record.declared_port == 18444


def test_renew_reward_node_transaction_preserves_reward_registration_and_updates_endpoint() -> None:
    registry = InMemoryNodeRegistryView()
    register_transaction = _register_reward_node_transaction(node_id="reward-node-2")
    apply_special_node_transaction(register_transaction, height=8, registry_view=registry)
    renew_transaction = _renew_reward_node_transaction(node_id="reward-node-2", renewal_epoch=1)

    apply_special_node_transaction(renew_transaction, height=101, registry_view=registry)
    record = registry.get_by_node_id("reward-node-2")
    assert record is not None
    assert record.reward_registration is True
    assert record.declared_host == "reward-node-2.renewed.example"
    assert record.declared_port == 18445
