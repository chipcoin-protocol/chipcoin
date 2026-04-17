"""Unsigned transaction construction and explicit local signing only."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from typing import Protocol

from ..consensus.models import ChipbitAmount, OutPoint, Transaction, TxInput, TxOutput
from ..consensus.serialization import serialize_transaction
from ..consensus.validation import transaction_signature_digest
from ..crypto.addresses import is_valid_address
from ..crypto.keys import parse_private_key_hex
from ..wallet.signer import wallet_key_from_private_key
from .models import (
    TransactionArtifact,
    TransactionPlan,
    TransactionPlanInput,
    TransactionPlanOutput,
)


class TransactionArtifactSigner(Protocol):
    """Explicit signer boundary for local transaction artifacts."""

    signer_type: str

    def sign_input(self, digest: bytes) -> tuple[bytes, bytes]:
        """Return signature and public key for one input digest."""


class ExplicitPrivateKeySigner:
    """Single-key explicit signer for local dry-run signing."""

    signer_type = "explicit_private_key"

    def __init__(self, private_key_hex: str) -> None:
        self.wallet_key = wallet_key_from_private_key(parse_private_key_hex(private_key_hex))

    @property
    def address(self) -> str:
        return self.wallet_key.address

    def sign_input(self, digest: bytes) -> tuple[bytes, bytes]:
        from ..crypto.signatures import sign_digest

        return sign_digest(self.wallet_key.private_key, digest), self.wallet_key.public_key


class StubTransactionSigner:
    """Deterministic test signer that never leaves the process."""

    signer_type = "stub"

    def __init__(self, *, public_key: bytes = b"stub-public-key") -> None:
        self.public_key = public_key

    def sign_input(self, digest: bytes) -> tuple[bytes, bytes]:
        signature = hashlib.sha256(b"stub-signature" + digest).digest()
        return signature, self.public_key


def build_unsigned_transaction_artifact(
    *,
    plan: TransactionPlan,
    inputs: list[TransactionPlanInput],
    outputs: list[TransactionPlanOutput],
    created_at: int,
    created_by: str | None = None,
) -> tuple[TransactionArtifact, Transaction]:
    """Construct and persist a canonical unsigned transaction artifact."""

    unsigned_tx = build_unsigned_transaction(plan=plan, inputs=inputs, outputs=outputs)
    validation = validate_unsigned_transaction(
        plan=plan,
        transaction=unsigned_tx,
        inputs=inputs,
        outputs=outputs,
    )
    tx_hex = serialize_transaction(unsigned_tx).hex()
    snapshot_hash = transaction_snapshot_hash(unsigned_tx)
    artifact = TransactionArtifact(
        artifact_id=f"unsigned-{plan.plan_id}-{created_at}",
        plan_id=plan.plan_id,
        batch_id=plan.batch_id,
        status="unsigned" if validation["valid"] else "invalid",
        unsigned_tx_snapshot_hash=snapshot_hash,
        signed_tx_snapshot_hash=None,
        signer_type=None,
        created_at=created_at,
        created_by=created_by,
        validation_result="pass" if validation["valid"] else "fail",
        invalid_reason=None if validation["valid"] else validation["invalid_reason"],
        broadcasted=False,
        sent=False,
        wallet_mutation=False,
        tx_hex=tx_hex,
    )
    return artifact, unsigned_tx


def build_unsigned_transaction(
    *,
    plan: TransactionPlan,
    inputs: list[TransactionPlanInput],
    outputs: list[TransactionPlanOutput],
) -> Transaction:
    """Build one canonical unsigned transaction from a valid plan."""

    tx_inputs = tuple(
        TxInput(previous_output=OutPoint(txid=item.txid, index=item.vout))
        for item in sorted(inputs, key=lambda entry: entry.input_index)
    )
    tx_outputs = tuple(
        TxOutput(value=ChipbitAmount(item.amount_chipbits), recipient=item.recipient)
        for item in sorted(outputs, key=lambda entry: entry.output_index)
    )
    metadata = {
        "kind": "reward_payout_batch",
        "batch_id": plan.batch_id,
        "plan_id": plan.plan_id,
    }
    return Transaction(version=1, inputs=tx_inputs, outputs=tx_outputs, locktime=0, metadata=metadata)


def sign_transaction_artifact(
    *,
    artifact: TransactionArtifact,
    plan: TransactionPlan,
    inputs: list[TransactionPlanInput],
    outputs: list[TransactionPlanOutput],
    signer: TransactionArtifactSigner,
    created_at: int,
    created_by: str | None = None,
) -> tuple[TransactionArtifact, Transaction]:
    """Sign one unsigned artifact through an explicit signer interface."""

    if artifact.status != "unsigned":
        raise ValueError("only unsigned artifacts can be signed")
    unsigned_tx = build_unsigned_transaction(plan=plan, inputs=inputs, outputs=outputs)
    if isinstance(signer, ExplicitPrivateKeySigner):
        recipient_addresses = {item.recipient for item in inputs}
        if recipient_addresses != {signer.address}:
            raise ValueError("explicit signer can only sign plans funded by one matching address")

    signed_inputs = []
    for index, plan_input in enumerate(sorted(inputs, key=lambda entry: entry.input_index)):
        previous_output = TxOutput(value=ChipbitAmount(plan_input.amount_chipbits), recipient=plan_input.recipient)
        digest = transaction_signature_digest(unsigned_tx, index, previous_output=previous_output)
        signature, public_key = signer.sign_input(digest)
        signed_inputs.append(replace(unsigned_tx.inputs[index], signature=signature, public_key=public_key))
    signed_tx = replace(unsigned_tx, inputs=tuple(signed_inputs))
    validation = validate_signed_transaction_artifact(
        plan=plan,
        transaction=signed_tx,
        inputs=inputs,
        outputs=outputs,
    )
    signed_snapshot_hash = transaction_snapshot_hash(signed_tx)
    updated = TransactionArtifact(
        artifact_id=f"signed-{plan.plan_id}-{created_at}",
        plan_id=artifact.plan_id,
        batch_id=artifact.batch_id,
        status="signed" if validation["valid"] else "invalid",
        unsigned_tx_snapshot_hash=artifact.unsigned_tx_snapshot_hash,
        signed_tx_snapshot_hash=signed_snapshot_hash,
        signer_type=signer.signer_type,
        created_at=created_at,
        created_by=created_by,
        validation_result="pass" if validation["valid"] else "fail",
        invalid_reason=None if validation["valid"] else validation["invalid_reason"],
        broadcasted=False,
        sent=False,
        wallet_mutation=False,
        tx_hex=serialize_transaction(signed_tx).hex(),
    )
    return updated, signed_tx


def validate_unsigned_transaction(
    *,
    plan: TransactionPlan,
    transaction: Transaction,
    inputs: list[TransactionPlanInput],
    outputs: list[TransactionPlanOutput],
) -> dict[str, object]:
    """Validate one unsigned transaction against its plan."""

    invalid_reason = None
    if transaction.metadata.get("plan_id") != plan.plan_id or transaction.metadata.get("batch_id") != plan.batch_id:
        invalid_reason = "plan_linkage_mismatch"
    elif any(not is_valid_address(output.recipient) for output in transaction.outputs):
        invalid_reason = "invalid_recipient_address"
    elif len(transaction.inputs) != len(inputs):
        invalid_reason = "input_count_mismatch"
    elif len(transaction.outputs) != len(outputs):
        invalid_reason = "output_count_mismatch"
    elif [(item.previous_output.txid, item.previous_output.index) for item in transaction.inputs] != [
        (item.txid, item.vout) for item in sorted(inputs, key=lambda entry: entry.input_index)
    ]:
        invalid_reason = "input_mapping_mismatch"
    elif [(output.recipient, int(output.value)) for output in transaction.outputs] != [
        (item.recipient, item.amount_chipbits) for item in sorted(outputs, key=lambda entry: entry.output_index)
    ]:
        invalid_reason = "output_mapping_mismatch"
    elif not _change_policy_matches(outputs, transaction):
        invalid_reason = "change_policy_mismatch"
    elif plan.status != "planned":
        invalid_reason = "plan_not_plannable"
    return {"valid": invalid_reason is None, "invalid_reason": invalid_reason}


def validate_signed_transaction_artifact(
    *,
    plan: TransactionPlan,
    transaction: Transaction,
    inputs: list[TransactionPlanInput],
    outputs: list[TransactionPlanOutput],
) -> dict[str, object]:
    """Validate a signed transaction artifact without broadcasting it."""

    base = validate_unsigned_transaction(plan=plan, transaction=transaction, inputs=inputs, outputs=outputs)
    if not base["valid"]:
        return base
    if any(not item.signature or not item.public_key for item in transaction.inputs):
        return {"valid": False, "invalid_reason": "missing_input_signature"}
    return {"valid": True, "invalid_reason": None}


def transaction_snapshot_hash(transaction: Transaction) -> str:
    """Return deterministic content hash for a transaction artifact."""

    return hashlib.sha256(serialize_transaction(transaction)).hexdigest()


def _change_policy_matches(outputs: list[TransactionPlanOutput], transaction: Transaction) -> bool:
    planned_change = [item for item in sorted(outputs, key=lambda entry: entry.output_index) if item.output_kind == "change"]
    actual_change = [
        (index, output.recipient, int(output.value))
        for index, output in enumerate(transaction.outputs)
        if index >= len(transaction.outputs) - len(planned_change)
    ] if planned_change else []
    expected_change = [(item.output_index, item.recipient, item.amount_chipbits) for item in planned_change]
    return actual_change == expected_change
