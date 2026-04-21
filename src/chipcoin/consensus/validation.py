"""Consensus validation interfaces and error types."""

from __future__ import annotations

from dataclasses import dataclass, field
from string import hexdigits

from ..crypto.addresses import public_key_to_address
from ..crypto.signatures import verify_digest
from .epoch_settlement import (
    REWARD_ATTESTATION_BUNDLE_KIND,
    REWARD_SETTLE_EPOCH_KIND,
    RewardAttestation,
    RewardAttestationBundle,
    RewardSettlement,
    RewardSettlementEntry,
    attestation_identity,
    bundle_rule_violations,
    candidate_check_windows,
    derive_reward_settlement_entries,
    epoch_close_height,
    parse_reward_attestation_bundle_metadata,
    parse_reward_settlement_metadata,
    reward_attestation_signature_digest,
    verifier_committee,
)
from .economics import (
    is_epoch_reward_height,
    renew_reward_node_fee_chipbits,
    reward_registered_node_count,
    register_reward_node_fee_chipbits,
    subsidy_split_chipbits,
)
from .hashes import double_sha256
from .merkle import merkle_root
from .models import Block, Transaction, TxOutput
from .nodes import (
    InMemoryNodeRegistryView,
    NodeRegistryView,
    active_node_records,
    apply_special_node_transaction,
    is_legacy_register_node_transaction,
    is_legacy_renew_node_transaction,
    is_register_reward_node_transaction,
    is_renew_reward_node_transaction,
    is_register_node_transaction,
    is_renew_node_transaction,
    is_special_node_transaction,
    select_rewarded_nodes,
    validate_special_node_transaction_stateless,
)
from .params import ConsensusParams, MAINNET_PARAMS
from .pow import bits_to_target, verify_proof_of_work
from .serialization import serialize_transaction, serialize_transaction_for_signing
from .utxo import UtxoView


class ValidationError(Exception):
    """Raised when a transaction or block violates consensus rules."""


class StatelessValidationError(ValidationError):
    """Raised for structure or encoding problems independent from chain state."""


class ContextualValidationError(ValidationError):
    """Raised for validation failures that depend on current chain state."""


@dataclass(frozen=True)
class ValidationContext:
    """Context needed for validation against current chain state."""

    height: int
    median_time_past: int
    params: ConsensusParams
    utxo_view: UtxoView
    node_registry_view: NodeRegistryView = field(default_factory=InMemoryNodeRegistryView)
    reward_attestation_identities: frozenset[tuple[int, int, str, str]] = field(default_factory=frozenset)
    reward_attestation_bundles: tuple[RewardAttestationBundle, ...] = ()
    settled_epoch_indexes: frozenset[int] = field(default_factory=frozenset)
    epoch_seed_by_index: dict[int, bytes] = field(default_factory=dict)
    expected_previous_block_hash: str | None = None
    expected_bits: int | None = None
    enforce_coinbase_maturity: bool = True
    reward_fee_registry_count: int | None = None


def is_coinbase_transaction(transaction: Transaction) -> bool:
    """Return whether a transaction is a block coinbase."""

    return not transaction.inputs and transaction.metadata.get("coinbase") == "true"


def validate_transaction(transaction: Transaction, context: ValidationContext) -> int:
    """Perform full validation for a transaction and return its fee."""

    validate_transaction_stateless(transaction)
    return validate_transaction_stateful(transaction, context)


def validate_transaction_stateless(transaction: Transaction) -> None:
    """Validate transaction structure independently from chain state."""

    if transaction.version <= 0:
        raise StatelessValidationError("Transaction version must be positive.")
    if is_special_node_transaction(transaction):
        try:
            validate_special_node_transaction_stateless(transaction)
        except ValueError as exc:
            raise StatelessValidationError(str(exc)) from exc
        return
    if _is_reward_attestation_bundle_transaction(transaction):
        try:
            _validate_reward_attestation_bundle_transaction_stateless(transaction)
        except ValueError as exc:
            raise StatelessValidationError(str(exc)) from exc
        return
    if _is_reward_settle_epoch_transaction(transaction):
        try:
            _validate_reward_settle_epoch_transaction_stateless(transaction)
        except ValueError as exc:
            raise StatelessValidationError(str(exc)) from exc
        return
    if not transaction.outputs:
        raise StatelessValidationError("Transaction must contain at least one output.")
    if transaction.locktime < 0:
        raise StatelessValidationError("Transaction locktime cannot be negative.")

    for output in transaction.outputs:
        if int(output.value) < 0:
            raise StatelessValidationError("Transaction outputs cannot be negative.")
        if not output.recipient:
            raise StatelessValidationError("Transaction outputs must declare a recipient.")

    if is_coinbase_transaction(transaction):
        return

    if not transaction.inputs:
        raise StatelessValidationError("Non-coinbase transactions must have at least one input.")

    seen_outpoints = set()
    for tx_input in transaction.inputs:
        _validate_outpoint(tx_input.previous_output.txid)
        if tx_input.previous_output.index < 0:
            raise StatelessValidationError("Outpoint index cannot be negative.")
        if tx_input.previous_output in seen_outpoints:
            raise StatelessValidationError("Transaction cannot spend the same outpoint twice.")
        seen_outpoints.add(tx_input.previous_output)
        if not tx_input.signature:
            raise StatelessValidationError("Non-coinbase inputs must include a signature.")
        if not tx_input.public_key:
            raise StatelessValidationError("Non-coinbase inputs must include a public key.")


def validate_transaction_stateful(transaction: Transaction, context: ValidationContext) -> int:
    """Validate a transaction against current UTXO state and return its fee."""

    if is_coinbase_transaction(transaction):
        return 0
    if is_special_node_transaction(transaction):
        _validate_special_node_transaction_stateful(transaction, context)
        return 0
    if _is_reward_attestation_bundle_transaction(transaction):
        _validate_reward_attestation_bundle_transaction_with_params(transaction, context)
        return 0
    if _is_reward_settle_epoch_transaction(transaction):
        _validate_reward_settle_epoch_transaction_with_params(transaction, context)
        return 0

    input_total_chipbits = 0
    for input_index, tx_input in enumerate(transaction.inputs):
        entry = context.utxo_view.get(tx_input.previous_output)
        if entry is None:
            raise ContextualValidationError("Referenced input does not exist in the UTXO set.")
        if context.enforce_coinbase_maturity and not is_coinbase_mature(entry, context.height, context.params):
            raise ContextualValidationError("Coinbase output is not mature enough to spend.")
        try:
            derived_recipient = public_key_to_address(tx_input.public_key)
        except ValueError as exc:
            raise ContextualValidationError("Input public key is not a valid secp256k1 public key.") from exc
        if derived_recipient != entry.output.recipient:
            raise ContextualValidationError("Input public key does not match the referenced output recipient.")
        digest = transaction_signature_digest(transaction, input_index, previous_output=entry.output)
        if not verify_digest(tx_input.public_key, digest, tx_input.signature):
            raise ContextualValidationError("Input signature is invalid.")
        input_total_chipbits += int(entry.output.value)

    output_total_chipbits = transaction_output_total(transaction)
    if input_total_chipbits < output_total_chipbits:
        raise ContextualValidationError("Transaction outputs exceed transaction inputs.")

    return input_total_chipbits - output_total_chipbits


def validate_block(block: Block, context: ValidationContext) -> int:
    """Perform full block validation and return the total fee amount."""

    validate_block_stateless(block, context)
    return validate_block_stateful(block, context)


def validate_block_stateless(block: Block, context: ValidationContext | None = None) -> None:
    """Validate a block independently from chain UTXO state."""

    if not block.transactions:
        raise StatelessValidationError("Block must contain at least one transaction.")
    if not is_coinbase_transaction(block.transactions[0]):
        raise StatelessValidationError("First block transaction must be coinbase.")
    if any(is_coinbase_transaction(transaction) for transaction in block.transactions[1:]):
        raise StatelessValidationError("Only the first block transaction may be coinbase.")

    for transaction in block.transactions:
        validate_transaction_stateless(transaction)
    if context is not None:
        bundle_count = sum(1 for transaction in block.transactions if _is_reward_attestation_bundle_transaction(transaction))
        if bundle_count > context.params.max_attestation_bundles_per_block:
            raise StatelessValidationError("Block contains too many reward_attestation_bundle transactions.")
    if block_weight_units(block) > (context.params.max_block_weight if context is not None else MAINNET_PARAMS.max_block_weight):
        raise StatelessValidationError("Block exceeds maximum block weight.")

    expected_merkle_root = merkle_root([transaction.txid() for transaction in block.transactions])
    if block.header.merkle_root != expected_merkle_root:
        raise StatelessValidationError("Block Merkle root does not match transaction contents.")
    if block.header.timestamp < 0:
        raise StatelessValidationError("Block timestamp cannot be negative.")
    if context is not None and block.header.timestamp < context.median_time_past:
        raise StatelessValidationError("Block timestamp is below median time past.")

    bits_to_target(block.header.bits)
    if not verify_proof_of_work(block.header):
        raise StatelessValidationError("Block proof of work is invalid.")


def validate_block_stateful(block: Block, context: ValidationContext) -> int:
    """Validate a block against UTXO state and return total fees."""

    if context.expected_previous_block_hash is not None:
        if block.header.previous_block_hash != context.expected_previous_block_hash:
            raise ContextualValidationError("Block does not connect to the expected previous hash.")
    if context.expected_bits is not None:
        if block.header.bits != context.expected_bits:
            raise ContextualValidationError("Block bits do not match expected difficulty target.")

    staged_view = context.utxo_view.clone()
    staged_registry = context.node_registry_view.clone()
    total_fees_chipbits = 0
    seen_spends = set()
    seen_attestations: set[tuple[int, int, str, str]] = set()
    verifier_window_counts: dict[tuple[int, str], int] = {}
    staged_attestation_identities = set(context.reward_attestation_identities)
    staged_attestation_bundles = list(context.reward_attestation_bundles)
    staged_settled_epoch_indexes = set(context.settled_epoch_indexes)
    staged_epoch_settlement: RewardSettlement | None = None

    for transaction in block.transactions[1:]:
        if _is_reward_attestation_bundle_transaction(transaction):
            bundle = _parse_reward_attestation_bundle(transaction)
            for attestation in bundle.attestations:
                identity = attestation_identity(attestation)
                if identity in seen_attestations:
                    raise ContextualValidationError("Block contains a duplicate reward attestation.")
                seen_attestations.add(identity)
                verifier_window_key = (attestation.check_window_index, attestation.verifier_node_id)
                verifier_window_counts[verifier_window_key] = verifier_window_counts.get(verifier_window_key, 0) + 1
                if verifier_window_counts[verifier_window_key] > context.params.max_attestations_per_verifier_per_window:
                    raise ContextualValidationError("Block exceeds per-window verifier attestation emission limits.")
        if not is_special_node_transaction(transaction):
            for tx_input in transaction.inputs:
                if tx_input.previous_output in seen_spends:
                    raise ContextualValidationError("Block contains a double spend.")
                seen_spends.add(tx_input.previous_output)

        staged_context = ValidationContext(
            height=context.height,
            median_time_past=context.median_time_past,
            params=context.params,
            utxo_view=staged_view,
            node_registry_view=staged_registry,
            reward_attestation_identities=frozenset(staged_attestation_identities),
            reward_attestation_bundles=tuple(staged_attestation_bundles),
            settled_epoch_indexes=frozenset(staged_settled_epoch_indexes),
            epoch_seed_by_index=dict(context.epoch_seed_by_index),
            enforce_coinbase_maturity=context.enforce_coinbase_maturity,
            reward_fee_registry_count=(
                context.reward_fee_registry_count
                if context.reward_fee_registry_count is not None
                else reward_registered_node_count(context.node_registry_view)
            ),
        )
        fee_chipbits = validate_transaction_stateful(transaction, staged_context)
        total_fees_chipbits += fee_chipbits
        if is_special_node_transaction(transaction):
            apply_special_node_transaction(transaction, height=context.height, registry_view=staged_registry)
        elif _is_reward_attestation_bundle_transaction(transaction):
            bundle = _parse_reward_attestation_bundle(transaction)
            staged_attestation_bundles.append(bundle)
            staged_attestation_identities.update(attestation_identity(attestation) for attestation in bundle.attestations)
        elif _is_reward_settle_epoch_transaction(transaction):
            settlement = _parse_reward_settlement(transaction)
            staged_settled_epoch_indexes.add(settlement.epoch_index)
            if settlement.epoch_end_height == context.height:
                staged_epoch_settlement = settlement
        else:
            staged_view.apply_transaction(transaction, context.height)

    _validate_coinbase_distribution(
        block.transactions[0],
        height=context.height,
        previous_block_hash=block.header.previous_block_hash,
        total_fees_chipbits=total_fees_chipbits,
        context=context,
        epoch_settlement=staged_epoch_settlement,
    )

    return total_fees_chipbits


def transaction_output_total(transaction: Transaction) -> int:
    """Return the total output value of a transaction."""

    return sum(int(output.value) for output in transaction.outputs)


def transaction_weight_units(transaction: Transaction) -> int:
    """Return the didactic transaction weight metric used by consensus limits."""

    return len(serialize_transaction(transaction))


def block_weight_units(block: Block) -> int:
    """Return the didactic block weight metric as the sum of serialized tx bytes."""

    return sum(transaction_weight_units(transaction) for transaction in block.transactions)


def transaction_signature_digest(transaction: Transaction, input_index: int, *, previous_output: TxOutput) -> bytes:
    """Return the digest that must be signed for one transaction input."""

    return double_sha256(
        serialize_transaction_for_signing(
            transaction,
            input_index,
            previous_output_value=int(previous_output.value),
            previous_output_recipient=previous_output.recipient,
        )
    )


def _validate_coinbase_distribution(
    coinbase_transaction: Transaction,
    *,
    height: int,
    previous_block_hash: str,
    total_fees_chipbits: int,
    context: ValidationContext,
    epoch_settlement: RewardSettlement | None = None,
) -> None:
    """Validate exact miner and node reward outputs for a coinbase transaction."""

    if not coinbase_transaction.outputs:
        raise ContextualValidationError("Coinbase transaction must contain at least one output.")

    miner_base_subsidy_chipbits, node_pool_chipbits = subsidy_split_chipbits(height, context.params)
    epoch_closing_height = is_epoch_reward_height(height, context.params)
    _ = previous_block_hash
    rewarded_outputs = []
    distributed_node_reward_chipbits = 0
    if epoch_settlement is not None:
        rewarded_outputs = [
            (entry.payout_address, entry.reward_chipbits)
            for entry in sorted(epoch_settlement.reward_entries, key=lambda entry: entry.selection_rank)
        ]
        distributed_node_reward_chipbits = epoch_settlement.distributed_node_reward_chipbits
    if not epoch_closing_height and node_pool_chipbits != 0:
        raise ContextualValidationError("Node reward can only be minted on epoch-closing blocks.")
    if not epoch_closing_height and rewarded_outputs:
        raise ContextualValidationError("Node reward recipients are not allowed on non-epoch blocks.")

    miner_amount_chipbits = miner_base_subsidy_chipbits + total_fees_chipbits

    expected_output_count = 1 + len(rewarded_outputs)
    if len(coinbase_transaction.outputs) != expected_output_count:
        raise ContextualValidationError("Coinbase outputs do not match the expected miner and node reward distribution.")
    if int(coinbase_transaction.outputs[0].value) != miner_amount_chipbits:
        raise ContextualValidationError("Coinbase miner payout amount is incorrect.")

    for index, (recipient, reward_chipbits) in enumerate(rewarded_outputs, start=1):
        actual_output = coinbase_transaction.outputs[index]
        if actual_output.recipient != recipient:
            raise ContextualValidationError("Coinbase node reward recipient ordering is incorrect.")
        if int(actual_output.value) != reward_chipbits:
            raise ContextualValidationError("Coinbase node reward amount is incorrect.")

    if rewarded_outputs and distributed_node_reward_chipbits != node_pool_chipbits:
        raise ContextualValidationError("Coinbase node reward split does not match the scheduled epoch reward.")
    if not rewarded_outputs and distributed_node_reward_chipbits != 0:
        raise ContextualValidationError("Coinbase must not mint node reward outputs when no nodes are eligible for the epoch.")


def _validate_special_node_transaction_stateful(transaction: Transaction, context: ValidationContext) -> None:
    """Validate stateful node registry rules for register and renew actions."""

    owner_pubkey = bytes.fromhex(transaction.metadata["owner_pubkey_hex"])
    fee_registry_count = (
        context.reward_fee_registry_count
        if context.reward_fee_registry_count is not None
        else reward_registered_node_count(context.node_registry_view)
    )
    if is_legacy_register_node_transaction(transaction):
        node_id = transaction.metadata["node_id"]
        if context.node_registry_view.get_by_node_id(node_id) is not None:
            raise ContextualValidationError("register_node transaction reuses an existing node_id.")
        if context.node_registry_view.get_by_owner_pubkey(owner_pubkey) is not None:
            raise ContextualValidationError("register_node transaction reuses an existing owner_pubkey.")
        return

    if is_register_reward_node_transaction(transaction):
        node_id = transaction.metadata["node_id"]
        if context.node_registry_view.get_by_node_id(node_id) is not None:
            raise ContextualValidationError("register_reward_node transaction reuses an existing node_id.")
        if context.node_registry_view.get_by_owner_pubkey(owner_pubkey) is not None:
            raise ContextualValidationError("register_reward_node transaction reuses an existing owner_pubkey.")
        node_pubkey = bytes.fromhex(transaction.metadata["node_pubkey_hex"])
        if _find_registry_record_by_node_pubkey(context.node_registry_view, node_pubkey) is not None:
            raise ContextualValidationError("register_reward_node transaction reuses an existing node_pubkey.")
        expected_fee = register_reward_node_fee_chipbits(
            registered_reward_node_count=fee_registry_count,
            params=context.params,
        )
        if int(transaction.metadata.get("registration_fee_chipbits", "-1")) != expected_fee:
            raise ContextualValidationError("register_reward_node transaction registration_fee_chipbits does not match consensus fee schedule.")
        return

    if is_legacy_renew_node_transaction(transaction):
        node_id = transaction.metadata["node_id"]
        record = context.node_registry_view.get_by_node_id(node_id)
        if record is None:
            raise ContextualValidationError("renew_node transaction references an unknown node_id.")
        if record.owner_pubkey != owner_pubkey:
            raise ContextualValidationError("renew_node transaction owner_pubkey does not match the registered node owner.")
        if transaction.metadata.get("renewal_epoch") != str(context.height // context.params.epoch_length_blocks):
            raise ContextualValidationError("renew_node transaction renewal_epoch does not match the block epoch.")
        return

    if is_renew_reward_node_transaction(transaction):
        node_id = transaction.metadata["node_id"]
        record = context.node_registry_view.get_by_node_id(node_id)
        if record is None:
            raise ContextualValidationError("renew_reward_node transaction references an unknown node_id.")
        if record.owner_pubkey != owner_pubkey:
            raise ContextualValidationError("renew_reward_node transaction owner_pubkey does not match the registered node owner.")
        if transaction.metadata.get("renewal_epoch") != str(context.height // context.params.epoch_length_blocks):
            raise ContextualValidationError("renew_reward_node transaction renewal_epoch does not match the block epoch.")
        expected_fee = renew_reward_node_fee_chipbits(
            registered_reward_node_count=fee_registry_count,
            params=context.params,
        )
        if int(transaction.metadata.get("renewal_fee_chipbits", "-1")) != expected_fee:
            raise ContextualValidationError("renew_reward_node transaction renewal_fee_chipbits does not match consensus fee schedule.")
        return

    raise ContextualValidationError("Unsupported special node transaction kind.")


def _is_reward_attestation_bundle_transaction(transaction: Transaction) -> bool:
    return transaction.metadata.get("kind") == REWARD_ATTESTATION_BUNDLE_KIND


def _is_reward_settle_epoch_transaction(transaction: Transaction) -> bool:
    return transaction.metadata.get("kind") == REWARD_SETTLE_EPOCH_KIND


def _validate_reward_attestation_bundle_transaction_stateless(transaction: Transaction) -> None:
    if transaction.inputs:
        raise ValueError("reward_attestation_bundle transactions must not contain UTXO inputs.")
    if transaction.outputs:
        raise ValueError("reward_attestation_bundle transactions must not contain outputs.")
    bundle = _parse_reward_attestation_bundle(transaction)
    if any(attestation.epoch_index != bundle.epoch_index for attestation in bundle.attestations):
        raise ValueError("reward_attestation_bundle attestations must match bundle epoch_index.")
    if any(attestation.check_window_index != bundle.bundle_window_index for attestation in bundle.attestations):
        raise ValueError("reward_attestation_bundle attestations must match bundle_window_index.")


def _validate_reward_settle_epoch_transaction_stateless(transaction: Transaction) -> None:
    if transaction.inputs:
        raise ValueError("reward_settle_epoch transactions must not contain UTXO inputs.")
    if transaction.outputs:
        raise ValueError("reward_settle_epoch transactions must not contain outputs.")
    metadata = transaction.metadata
    for key in (
        "epoch_index",
        "epoch_start_height",
        "epoch_end_height",
        "epoch_seed",
        "policy_version",
        "candidate_summary_root",
        "verified_nodes_root",
        "rewarded_nodes_root",
        "rewarded_node_count",
        "distributed_node_reward_chipbits",
        "undistributed_node_reward_chipbits",
        "reward_entries_json",
    ):
        if key not in metadata or metadata[key] == "":
            raise ValueError(f"reward_settle_epoch transactions must declare {key}.")
    if len(metadata["epoch_seed"]) != 64:
        raise ValueError("reward_settle_epoch epoch_seed must be 32-byte hex.")
    for key in ("candidate_summary_root", "verified_nodes_root", "rewarded_nodes_root"):
        if len(metadata[key]) != 64:
            raise ValueError(f"reward_settle_epoch {key} must be 32-byte hex.")
    reward_entries = _parse_reward_settlement_entries(transaction)
    rewarded_node_count = int(metadata["rewarded_node_count"])
    if rewarded_node_count != len(reward_entries):
        raise ValueError("reward_settle_epoch rewarded_node_count does not match reward_entries_json length.")
    distributed = int(metadata["distributed_node_reward_chipbits"])
    undistributed = int(metadata["undistributed_node_reward_chipbits"])
    if distributed < 0 or undistributed < 0:
        raise ValueError("reward_settle_epoch reward amounts must be non-negative.")
    expected_ranks = list(range(len(reward_entries)))
    actual_ranks = [entry.selection_rank for entry in reward_entries]
    if actual_ranks != expected_ranks:
        raise ValueError("reward_settle_epoch reward_entries_json must use contiguous zero-based selection_rank ordering.")


def _validate_reward_attestation_bundle_transaction_with_params(transaction: Transaction, context: ValidationContext) -> None:
    bundle = _parse_reward_attestation_bundle(transaction)
    violations = bundle_rule_violations(bundle, context.params)
    if violations:
        raise ContextualValidationError(f"reward_attestation_bundle violates rules: {', '.join(violations)}")
    if context.height < context.params.node_reward_activation_height:
        raise ContextualValidationError("reward_attestation_bundle transactions are not active before node_reward_activation_height.")
    if bundle.epoch_index != context.height // context.params.epoch_length_blocks:
        raise ContextualValidationError("reward_attestation_bundle epoch_index must match the current block epoch.")
    seed = context.epoch_seed_by_index.get(bundle.epoch_index)
    if seed is None:
        raise ContextualValidationError("reward_attestation_bundle epoch seed is unavailable for the declared epoch.")
    active_records = active_node_records(context.node_registry_view, height=context.height, params=context.params)
    active_by_id = {record.node_id: record for record in active_records if record.reward_registration}
    active_ids = sorted(active_by_id)
    if bundle.bundle_submitter_node_id not in active_by_id:
        raise ContextualValidationError("reward_attestation_bundle submitter must be an active reward node.")
    for attestation in bundle.attestations:
        identity = attestation_identity(attestation)
        if identity in context.reward_attestation_identities:
            raise ContextualValidationError("reward_attestation_bundle replays an attestation already recorded on chain.")
        candidate = active_by_id.get(attestation.candidate_node_id)
        verifier = active_by_id.get(attestation.verifier_node_id)
        if candidate is None:
            raise ContextualValidationError("reward_attestation_bundle references a candidate node that is not active in the current epoch.")
        if verifier is None:
            raise ContextualValidationError("reward_attestation_bundle references a verifier node that is not active in the current epoch.")
        assigned_windows = candidate_check_windows(node_id=candidate.node_id, seed=seed, params=context.params)
        if attestation.check_window_index not in assigned_windows:
            raise ContextualValidationError("reward_attestation_bundle attestation is not assigned to the candidate's deterministic check windows.")
        committee = verifier_committee(
            candidate_node_id=candidate.node_id,
            active_verifier_node_ids=active_ids,
            check_window_index=attestation.check_window_index,
            seed=seed,
            params=context.params,
        )
        if verifier.node_id not in committee:
            raise ContextualValidationError("reward_attestation_bundle attestation verifier is not in the deterministic committee.")
        if verifier.node_pubkey is None:
            raise ContextualValidationError("reward_attestation_bundle verifier is missing a native reward-node public key.")
        try:
            signature = bytes.fromhex(attestation.signature_hex)
        except ValueError as exc:
            raise ContextualValidationError("reward_attestation_bundle signature_hex is invalid.") from exc
        if not verify_digest(verifier.node_pubkey, reward_attestation_signature_digest(attestation), signature):
            raise ContextualValidationError("reward_attestation_bundle attestation signature is invalid.")


def _validate_reward_settle_epoch_transaction_with_params(transaction: Transaction, context: ValidationContext) -> None:
    settlement = _parse_reward_settlement(transaction)
    if context.height < context.params.node_reward_activation_height:
        raise ContextualValidationError("reward_settle_epoch transactions are not active before node_reward_activation_height.")
    if settlement.epoch_index in context.settled_epoch_indexes:
        raise ContextualValidationError("reward_settle_epoch duplicates an already-settled epoch.")
    if context.height != settlement.epoch_end_height:
        raise ContextualValidationError("reward_settle_epoch must appear at the declared epoch_end_height.")
    if settlement.epoch_end_height != epoch_close_height(settlement.epoch_index, context.params):
        raise ContextualValidationError("reward_settle_epoch epoch_end_height does not match consensus epoch boundaries.")
    expected_start_height = settlement.epoch_index * context.params.epoch_length_blocks
    if settlement.epoch_start_height != expected_start_height:
        raise ContextualValidationError("reward_settle_epoch epoch_start_height does not match consensus epoch boundaries.")
    expected_seed = context.epoch_seed_by_index.get(settlement.epoch_index)
    if expected_seed is None:
        raise ContextualValidationError("reward_settle_epoch epoch seed is unavailable for the declared epoch.")
    if settlement.epoch_seed_hex != expected_seed.hex():
        raise ContextualValidationError("reward_settle_epoch epoch_seed does not match the deterministic epoch seed.")
    if settlement_reward_total := sum(entry.reward_chipbits for entry in settlement.reward_entries):
        pass
    if settlement_reward_total != settlement.distributed_node_reward_chipbits:
        raise ContextualValidationError("reward_settle_epoch distributed reward does not match reward_entries_json totals.")
    scheduled_pool = subsidy_split_chipbits(settlement.epoch_end_height, context.params)[1]
    if settlement.distributed_node_reward_chipbits + settlement.undistributed_node_reward_chipbits != scheduled_pool:
        raise ContextualValidationError("reward_settle_epoch distributed and undistributed reward does not match the scheduled epoch reward.")
    if settlement.rewarded_node_count != len(settlement.reward_entries):
        raise ContextualValidationError("reward_settle_epoch rewarded_node_count does not match the reward entry count.")
    recipient_keys = [(entry.node_id, entry.payout_address) for entry in settlement.reward_entries]
    if len(recipient_keys) != len(set(recipient_keys)):
        raise ContextualValidationError("reward_settle_epoch reward_entries_json must not contain duplicate rewarded recipients.")
    bundle_attestations = [
        attestation
        for bundle in context.reward_attestation_bundles
        if bundle.epoch_index == settlement.epoch_index
        for attestation in bundle.attestations
    ]
    active_records = active_node_records(context.node_registry_view, height=context.height, params=context.params)
    active_by_id = {record.node_id: record for record in active_records if record.reward_registration}
    if settlement.reward_entries:
        expected_entries = derive_reward_settlement_entries(
            active_records_by_id=active_by_id,
            seed=expected_seed,
            attestations=bundle_attestations,
            distributed_reward_chipbits=settlement.distributed_node_reward_chipbits,
            params=context.params,
        )
        if settlement.reward_entries != expected_entries:
            raise ContextualValidationError("reward_settle_epoch reward_entries_json does not match deterministic quorum and concentration results.")
    elif settlement.undistributed_node_reward_chipbits != scheduled_pool:
        raise ContextualValidationError("reward_settle_epoch with zero rewarded nodes must leave the full scheduled pool undistributed.")


def _parse_reward_attestation_bundle(transaction: Transaction) -> RewardAttestationBundle:
    bundle = parse_reward_attestation_bundle_metadata(transaction.metadata)
    for attestation in bundle.attestations:
        _validated_hex(attestation.signature_hex, field_name="signature_hex")
    return bundle


def _parse_reward_settlement_entries(transaction: Transaction) -> tuple[RewardSettlementEntry, ...]:
    return _parse_reward_settlement(transaction).reward_entries


def _parse_reward_settlement(transaction: Transaction) -> RewardSettlement:
    settlement = parse_reward_settlement_metadata(transaction.metadata)
    _validated_hex(settlement.epoch_seed_hex, field_name="epoch_seed")
    for key, value in (
        ("candidate_summary_root", settlement.candidate_summary_root),
        ("verified_nodes_root", settlement.verified_nodes_root),
        ("rewarded_nodes_root", settlement.rewarded_nodes_root),
    ):
        _validated_hex(value, field_name=key)
    return settlement


def _validated_hex(value: str, *, field_name: str) -> str:
    bytes.fromhex(value)
    return value


def _find_registry_record_by_node_pubkey(registry_view: NodeRegistryView, node_pubkey: bytes):
    for record in registry_view.list_records():
        if record.node_pubkey == node_pubkey:
            return record
    return None


def is_coinbase_mature(entry: object, spend_height: int, params: ConsensusParams) -> bool:
    """Return whether a coinbase output can be spent at the given height."""

    if not hasattr(entry, "is_coinbase") or not hasattr(entry, "height"):
        raise TypeError("Coinbase maturity checks require a UtxoEntry-like object.")
    if not getattr(entry, "is_coinbase"):
        return True
    return spend_height - int(getattr(entry, "height")) >= params.coinbase_maturity


def _validate_outpoint(txid: str) -> None:
    """Validate that a transaction identifier is a 32-byte hex string."""

    if len(txid) != 64 or any(character not in hexdigits for character in txid):
        raise StatelessValidationError("Outpoint transaction identifiers must be 32-byte hex strings.")
