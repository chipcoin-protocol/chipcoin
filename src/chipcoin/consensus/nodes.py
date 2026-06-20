"""On-chain node registry and deterministic epoch reward selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..crypto.addresses import is_valid_address
from ..crypto.keys import parse_public_key_hex
from ..crypto.signatures import verify_digest
from .epoch_settlement import REGISTER_REWARD_NODE_KIND, RENEW_REWARD_NODE_KIND
from .hashes import double_sha256
from .models import Transaction
from .params import ConsensusParams


REGISTER_NODE_KIND = "register_node"
RENEW_NODE_KIND = "renew_node"
SPECIAL_NODE_SIGNATURE_DOMAIN_V2 = "chipcoin:special-node-tx:v2"
SPECIAL_NODE_SIGNATURE_VERSION_V2 = "v2"
SPECIAL_NODE_SIGNATURE_V2_ACTIVATION_HEIGHT = 11111
SPECIAL_NODE_SIGNATURE_SCHEDULED_NETWORKS = {"devnet", "testnet"}


@dataclass(frozen=True)
class NodeRecord:
    """Consensus-visible node registry record."""

    node_id: str
    payout_address: str
    owner_pubkey: bytes
    registered_height: int
    last_renewed_height: int
    node_pubkey: bytes | None = None
    declared_host: str | None = None
    declared_port: int | None = None
    reward_registration: bool = False


@dataclass(frozen=True)
class RewardedNode:
    """Deterministically selected node reward recipient."""

    node_id: str
    payout_address: str
    owner_pubkey: bytes
    score_hex: str
    reward_chipbits: int


class NodeRegistryView:
    """Minimal node-registry access contract for validation and mining."""

    def get_by_node_id(self, node_id: str) -> NodeRecord | None:
        raise NotImplementedError

    def get_by_owner_pubkey(self, owner_pubkey: bytes) -> NodeRecord | None:
        raise NotImplementedError

    def upsert(self, record: NodeRecord) -> None:
        raise NotImplementedError

    def clone(self) -> "NodeRegistryView":
        raise NotImplementedError

    def list_records(self) -> list[NodeRecord]:
        raise NotImplementedError


class InMemoryNodeRegistryView(NodeRegistryView):
    """Simple in-memory node registry view."""

    def __init__(self, entries: dict[str, NodeRecord] | None = None) -> None:
        self._entries = dict(entries or {})

    @classmethod
    def from_records(cls, records: Iterable[NodeRecord]) -> "InMemoryNodeRegistryView":
        return cls({record.node_id: record for record in records})

    def get_by_node_id(self, node_id: str) -> NodeRecord | None:
        return self._entries.get(node_id)

    def get_by_owner_pubkey(self, owner_pubkey: bytes) -> NodeRecord | None:
        for record in self._entries.values():
            if record.owner_pubkey == owner_pubkey:
                return record
        return None

    def upsert(self, record: NodeRecord) -> None:
        self._entries[record.node_id] = record

    def clone(self) -> "NodeRegistryView":
        return InMemoryNodeRegistryView(self._entries)

    def list_records(self) -> list[NodeRecord]:
        return sorted(self._entries.values(), key=lambda record: (record.node_id, record.payout_address))


def is_special_node_transaction(transaction: Transaction) -> bool:
    """Return whether a transaction is a node registry special transaction."""

    return transaction.metadata.get("kind") in {
        REGISTER_NODE_KIND,
        RENEW_NODE_KIND,
        REGISTER_REWARD_NODE_KIND,
        RENEW_REWARD_NODE_KIND,
    }


def is_legacy_register_node_transaction(transaction: Transaction) -> bool:
    return transaction.metadata.get("kind") == REGISTER_NODE_KIND


def is_legacy_renew_node_transaction(transaction: Transaction) -> bool:
    return transaction.metadata.get("kind") == RENEW_NODE_KIND


def is_register_reward_node_transaction(transaction: Transaction) -> bool:
    return transaction.metadata.get("kind") == REGISTER_REWARD_NODE_KIND


def is_renew_reward_node_transaction(transaction: Transaction) -> bool:
    return transaction.metadata.get("kind") == RENEW_REWARD_NODE_KIND


def is_register_node_transaction(transaction: Transaction) -> bool:
    return is_legacy_register_node_transaction(transaction) or is_register_reward_node_transaction(transaction)


def is_renew_node_transaction(transaction: Transaction) -> bool:
    return is_legacy_renew_node_transaction(transaction) or is_renew_reward_node_transaction(transaction)


def current_epoch(height: int, params: ConsensusParams) -> int:
    """Return the active epoch number for a given block height."""

    if height < 0:
        raise ValueError("Block height cannot be negative.")
    return height // params.epoch_length_blocks


def reward_node_warmup_complete_epoch(record: NodeRecord, params: ConsensusParams) -> int:
    """Return the first epoch index where reward warmup is satisfied."""

    if not record.reward_registration:
        return current_epoch(record.registered_height, params)
    return current_epoch(record.registered_height, params) + params.reward_node_warmup_epochs


def reward_node_warmup_complete_height(record: NodeRecord, params: ConsensusParams) -> int:
    """Return the first block height where reward warmup is satisfied."""

    return reward_node_warmup_complete_epoch(record, params) * params.epoch_length_blocks


def reward_node_eligible_from_height(record: NodeRecord, params: ConsensusParams) -> int:
    """Return the earliest possible block height where the current record can be active."""

    renewal_ready_height = record.last_renewed_height + 1
    if not record.reward_registration:
        return renewal_ready_height
    return max(renewal_ready_height, reward_node_warmup_complete_height(record, params))


def reward_node_warmup_satisfied(record: NodeRecord, *, height: int, params: ConsensusParams) -> bool:
    """Return whether reward-node warmup is satisfied at the supplied height."""

    if not record.reward_registration:
        return True
    return current_epoch(height, params) >= reward_node_warmup_complete_epoch(record, params)


def reward_node_is_active(record: NodeRecord, *, height: int, params: ConsensusParams) -> bool:
    """Return whether one node record is active for reward selection at a given height."""

    epoch = current_epoch(height, params)
    renewal_epoch = current_epoch(record.last_renewed_height, params)
    if record.last_renewed_height >= height:
        return False
    if renewal_epoch != epoch:
        return False
    return reward_node_warmup_satisfied(record, height=height, params=params)


def active_node_records(
    registry_view: NodeRegistryView,
    *,
    height: int,
    params: ConsensusParams,
) -> list[NodeRecord]:
    """Return node records active for reward selection at the supplied height."""

    return [
        record
        for record in registry_view.list_records()
        if reward_node_is_active(record, height=height, params=params)
    ]


def epoch_reward_remainder(height: int, params: ConsensusParams) -> int:
    """Return the base-unit remainder carried by deterministic equal split at one height."""

    if height < 0:
        raise ValueError("Block height cannot be negative.")
    if (height + 1) % params.epoch_length_blocks != 0:
        return 0
    return 0


def select_rewarded_nodes(
    registry_view: NodeRegistryView,
    *,
    height: int,
    previous_block_hash: str,
    node_reward_pool_chipbits: int,
    params: ConsensusParams,
) -> list[RewardedNode]:
    """Return deterministic epoch reward recipients for one block height.

    The current devnet baseline no longer uses per-block weighted winner selection.
    On epoch-closing blocks, all active node records participate in an equal split of
    the block-attached node reward amount, with deterministic remainder handling.

    `previous_block_hash` is retained for temporary call-site compatibility but is no
    longer used by the selection rule.
    """

    active_records = active_node_records(registry_view, height=height, params=params)
    if not active_records or node_reward_pool_chipbits <= 0:
        return []

    _ = previous_block_hash
    ordered_records = sorted(active_records, key=lambda record: (record.node_id, record.payout_address))
    recipient_count = len(ordered_records)
    base_reward_chipbits = node_reward_pool_chipbits // recipient_count
    remainder_chipbits = node_reward_pool_chipbits % recipient_count

    winners = []
    for index, record in enumerate(ordered_records):
        score_hex = double_sha256(
            record.node_id.encode("utf-8")
            + b"\x00"
            + record.payout_address.encode("utf-8")
        ).hex()
        winners.append(
            RewardedNode(
                node_id=record.node_id,
                payout_address=record.payout_address,
                owner_pubkey=record.owner_pubkey,
                score_hex=score_hex,
                reward_chipbits=base_reward_chipbits + (1 if index < remainder_chipbits else 0),
            )
        )
    return winners


def validate_special_node_transaction_stateless(transaction: Transaction) -> None:
    """Validate metadata shape and signatures for node special transactions."""

    if is_legacy_register_node_transaction(transaction):
        _validate_register_node_transaction(transaction)
        return
    if is_legacy_renew_node_transaction(transaction):
        _validate_renew_node_transaction(transaction)
        return
    if is_register_reward_node_transaction(transaction):
        _validate_register_reward_node_transaction(transaction)
        return
    if is_renew_reward_node_transaction(transaction):
        _validate_renew_reward_node_transaction(transaction)
        return
    raise ValueError("Transaction is not a special node transaction.")


def apply_special_node_transaction(
    transaction: Transaction,
    *,
    height: int,
    registry_view: NodeRegistryView,
) -> None:
    """Apply a validated node special transaction to registry state."""

    if is_legacy_register_node_transaction(transaction):
        owner_pubkey = parse_public_key_hex(transaction.metadata["owner_pubkey_hex"])
        registry_view.upsert(
            NodeRecord(
                node_id=transaction.metadata["node_id"],
                payout_address=transaction.metadata["payout_address"],
                owner_pubkey=owner_pubkey,
                registered_height=height,
                last_renewed_height=height,
            )
        )
        return

    if is_register_reward_node_transaction(transaction):
        owner_pubkey = parse_public_key_hex(transaction.metadata["owner_pubkey_hex"])
        existing = registry_view.get_by_node_id(transaction.metadata["node_id"])
        registered_height = height if existing is None else existing.registered_height
        registry_view.upsert(
            NodeRecord(
                node_id=transaction.metadata["node_id"],
                payout_address=transaction.metadata["payout_address"],
                owner_pubkey=owner_pubkey,
                registered_height=registered_height,
                last_renewed_height=height,
                node_pubkey=parse_public_key_hex(transaction.metadata["node_pubkey_hex"]),
                declared_host=transaction.metadata["declared_host"],
                declared_port=int(transaction.metadata["declared_port"]),
                reward_registration=True,
            )
        )
        return

    if is_legacy_renew_node_transaction(transaction):
        record = registry_view.get_by_node_id(transaction.metadata["node_id"])
        if record is None:
            raise ValueError("Cannot renew a node that is not registered.")
        registry_view.upsert(
            NodeRecord(
                node_id=record.node_id,
                payout_address=record.payout_address,
                owner_pubkey=record.owner_pubkey,
                registered_height=record.registered_height,
                last_renewed_height=height,
            )
        )
        return

    if is_renew_reward_node_transaction(transaction):
        record = registry_view.get_by_node_id(transaction.metadata["node_id"])
        if record is None:
            raise ValueError("Cannot renew a node that is not registered.")
        registry_view.upsert(
            NodeRecord(
                node_id=record.node_id,
                payout_address=record.payout_address,
                owner_pubkey=record.owner_pubkey,
                registered_height=record.registered_height,
                last_renewed_height=height,
                node_pubkey=record.node_pubkey,
                declared_host=transaction.metadata["declared_host"],
                declared_port=int(transaction.metadata["declared_port"]),
                reward_registration=record.reward_registration,
            )
        )
        return

    raise ValueError("Transaction is not a special node transaction.")


def special_node_transaction_signature_digest(transaction: Transaction) -> bytes:
    """Return the legacy digest signed by v1 special node transactions."""

    return double_sha256(_special_node_transaction_signature_payload_v1(transaction).encode("utf-8"))


def special_node_transaction_signature_digest_v2(transaction: Transaction, *, network: str) -> bytes:
    """Return the network-domain-separated digest signed by v2 special node transactions."""

    if not network:
        raise ValueError("Special node transaction v2 signatures require a network.")
    payload = "|".join(
        [
            f"{SPECIAL_NODE_SIGNATURE_DOMAIN_V2}:{network}",
            _special_node_transaction_signature_payload_v1(transaction),
        ]
    )
    return double_sha256(payload.encode("utf-8"))


def special_node_signature_version_for_height(*, network: str, height: int) -> str:
    """Return the required special-node signature version for a network height."""

    if network in SPECIAL_NODE_SIGNATURE_SCHEDULED_NETWORKS and height < SPECIAL_NODE_SIGNATURE_V2_ACTIVATION_HEIGHT:
        return ""
    return SPECIAL_NODE_SIGNATURE_VERSION_V2


def special_node_transaction_signature_is_valid(transaction: Transaction, *, network: str, height: int) -> bool:
    """Return whether the owner signature is valid for the active network.

    v2 signatures bind the signed special-node payload to an explicit network
    domain. devnet/testnet require legacy v1 signatures until the scheduled
    activation height, then require v2. mainnet requires v2 from genesis.
    """

    owner_pubkey = parse_public_key_hex(transaction.metadata["owner_pubkey_hex"])
    owner_signature = bytes.fromhex(transaction.metadata["owner_signature_hex"])
    required_version = special_node_signature_version_for_height(network=network, height=height)
    version = transaction.metadata.get("owner_signature_version", "")
    if version != required_version:
        return False
    if version == SPECIAL_NODE_SIGNATURE_VERSION_V2:
        signature_network = transaction.metadata.get("owner_signature_network", "")
        if signature_network != network:
            return False
        return verify_digest(
            owner_pubkey,
            special_node_transaction_signature_digest_v2(transaction, network=network),
            owner_signature,
        )
    return verify_digest(owner_pubkey, special_node_transaction_signature_digest(transaction), owner_signature)


def special_node_transaction_signature_is_valid_stateless(transaction: Transaction) -> bool:
    """Return whether the owner signature is internally valid without active-network context."""

    owner_pubkey = parse_public_key_hex(transaction.metadata["owner_pubkey_hex"])
    owner_signature = bytes.fromhex(transaction.metadata["owner_signature_hex"])
    version = transaction.metadata.get("owner_signature_version", "")
    if version == SPECIAL_NODE_SIGNATURE_VERSION_V2:
        signature_network = transaction.metadata.get("owner_signature_network", "")
        if not signature_network:
            return False
        return verify_digest(
            owner_pubkey,
            special_node_transaction_signature_digest_v2(transaction, network=signature_network),
            owner_signature,
        )
    if version:
        return False
    return verify_digest(owner_pubkey, special_node_transaction_signature_digest(transaction), owner_signature)


def _special_node_transaction_signature_payload_v1(transaction: Transaction) -> str:
    """Return the legacy field payload shared by v1 and v2 signatures."""

    kind = transaction.metadata.get("kind", "")
    owner_pubkey_hex = transaction.metadata.get("owner_pubkey_hex", "")
    if kind == REGISTER_NODE_KIND:
        payload = "|".join(
            [
                REGISTER_NODE_KIND,
                transaction.metadata.get("node_id", ""),
                transaction.metadata.get("payout_address", ""),
                owner_pubkey_hex,
            ]
        )
    elif kind == REGISTER_REWARD_NODE_KIND:
        payload = "|".join(
            [
                REGISTER_REWARD_NODE_KIND,
                transaction.metadata.get("node_id", ""),
                transaction.metadata.get("payout_address", ""),
                owner_pubkey_hex,
                transaction.metadata.get("node_pubkey_hex", ""),
                transaction.metadata.get("declared_host", ""),
                transaction.metadata.get("declared_port", ""),
                transaction.metadata.get("registration_fee_chipbits", ""),
            ]
        )
    elif kind == RENEW_NODE_KIND:
        payload = "|".join(
            [
                RENEW_NODE_KIND,
                transaction.metadata.get("node_id", ""),
                transaction.metadata.get("renewal_epoch", ""),
                owner_pubkey_hex,
            ]
        )
    elif kind == RENEW_REWARD_NODE_KIND:
        payload = "|".join(
            [
                RENEW_REWARD_NODE_KIND,
                transaction.metadata.get("node_id", ""),
                transaction.metadata.get("renewal_epoch", ""),
                owner_pubkey_hex,
                transaction.metadata.get("declared_host", ""),
                transaction.metadata.get("declared_port", ""),
                transaction.metadata.get("renewal_fee_chipbits", ""),
            ]
        )
    else:
        raise ValueError("Unsupported special node transaction kind.")
    return payload


def _validate_register_node_transaction(transaction: Transaction) -> None:
    _validate_node_metadata_common(transaction)
    node_id = transaction.metadata.get("node_id", "")
    payout_address = transaction.metadata.get("payout_address", "")
    if not node_id:
        raise ValueError("register_node transactions must declare a node_id.")
    if not payout_address or not is_valid_address(payout_address):
        raise ValueError("register_node transactions must declare a valid payout_address.")
    parse_public_key_hex(transaction.metadata["owner_pubkey_hex"])
    if not special_node_transaction_signature_is_valid_stateless(transaction):
        raise ValueError("register_node transaction owner signature is invalid.")


def _validate_renew_node_transaction(transaction: Transaction) -> None:
    _validate_node_metadata_common(transaction)
    node_id = transaction.metadata.get("node_id", "")
    renewal_epoch = transaction.metadata.get("renewal_epoch", "")
    if not node_id:
        raise ValueError("renew_node transactions must declare a node_id.")
    if not renewal_epoch:
        raise ValueError("renew_node transactions must declare renewal_epoch.")
    parse_public_key_hex(transaction.metadata["owner_pubkey_hex"])
    if not special_node_transaction_signature_is_valid_stateless(transaction):
        raise ValueError("renew_node transaction owner signature is invalid.")


def _validate_register_reward_node_transaction(transaction: Transaction) -> None:
    _validate_node_metadata_common(transaction)
    node_id = transaction.metadata.get("node_id", "")
    payout_address = transaction.metadata.get("payout_address", "")
    node_pubkey_hex = transaction.metadata.get("node_pubkey_hex", "")
    declared_host = transaction.metadata.get("declared_host", "")
    declared_port = transaction.metadata.get("declared_port", "")
    registration_fee_chipbits = transaction.metadata.get("registration_fee_chipbits", "")
    if not node_id:
        raise ValueError("register_reward_node transactions must declare a node_id.")
    if not payout_address or not is_valid_address(payout_address):
        raise ValueError("register_reward_node transactions must declare a valid payout_address.")
    if not node_pubkey_hex:
        raise ValueError("register_reward_node transactions must declare node_pubkey_hex.")
    parse_public_key_hex(node_pubkey_hex)
    _validate_declared_endpoint(declared_host, declared_port, kind=REGISTER_REWARD_NODE_KIND)
    if not registration_fee_chipbits or int(registration_fee_chipbits) < 0:
        raise ValueError("register_reward_node transactions must declare a non-negative registration_fee_chipbits.")
    parse_public_key_hex(transaction.metadata["owner_pubkey_hex"])
    if not special_node_transaction_signature_is_valid_stateless(transaction):
        raise ValueError("register_reward_node transaction owner signature is invalid.")


def _validate_renew_reward_node_transaction(transaction: Transaction) -> None:
    _validate_node_metadata_common(transaction)
    node_id = transaction.metadata.get("node_id", "")
    renewal_epoch = transaction.metadata.get("renewal_epoch", "")
    declared_host = transaction.metadata.get("declared_host", "")
    declared_port = transaction.metadata.get("declared_port", "")
    renewal_fee_chipbits = transaction.metadata.get("renewal_fee_chipbits", "")
    if not node_id:
        raise ValueError("renew_reward_node transactions must declare a node_id.")
    if not renewal_epoch:
        raise ValueError("renew_reward_node transactions must declare renewal_epoch.")
    _validate_declared_endpoint(declared_host, declared_port, kind=RENEW_REWARD_NODE_KIND)
    if not renewal_fee_chipbits or int(renewal_fee_chipbits) < 0:
        raise ValueError("renew_reward_node transactions must declare a non-negative renewal_fee_chipbits.")
    parse_public_key_hex(transaction.metadata["owner_pubkey_hex"])
    if not special_node_transaction_signature_is_valid_stateless(transaction):
        raise ValueError("renew_reward_node transaction owner signature is invalid.")


def _validate_node_metadata_common(transaction: Transaction) -> None:
    owner_pubkey_hex = transaction.metadata.get("owner_pubkey_hex", "")
    owner_signature_hex = transaction.metadata.get("owner_signature_hex", "")
    if transaction.inputs:
        raise ValueError("Special node transactions must not contain UTXO inputs.")
    if transaction.outputs:
        raise ValueError("Special node transactions must not contain outputs.")
    if not owner_pubkey_hex:
        raise ValueError("Special node transactions must declare owner_pubkey_hex.")
    if not owner_signature_hex:
        raise ValueError("Special node transactions must declare owner_signature_hex.")
    version = transaction.metadata.get("owner_signature_version", "")
    if version and version != SPECIAL_NODE_SIGNATURE_VERSION_V2:
        raise ValueError("Special node transactions declare an unsupported owner_signature_version.")
    if version == SPECIAL_NODE_SIGNATURE_VERSION_V2 and not transaction.metadata.get("owner_signature_network", ""):
        raise ValueError("Special node transaction v2 signatures must declare owner_signature_network.")


def _validate_declared_endpoint(host: str, port: str, *, kind: str) -> None:
    if not host:
        raise ValueError(f"{kind} transactions must declare declared_host.")
    if not port:
        raise ValueError(f"{kind} transactions must declare declared_port.")
    port_value = int(port)
    if port_value <= 0 or port_value > 65535:
        raise ValueError(f"{kind} transactions must declare a valid declared_port.")
