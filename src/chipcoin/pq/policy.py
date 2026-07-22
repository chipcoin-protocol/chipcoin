"""Node-local Post-Quantum transaction policy helpers.

These checks are deliberately outside consensus. They make mempool admission and
runtime diagnostics fail cheap before expensive ML-DSA verification is reached.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..consensus.models import Transaction
from ..consensus.pq_activation import PQ_TRANSACTION_VERSION
from ..consensus.serialization import serialize_transaction
from ..crypto.addresses import parse_address
from ..crypto.pq import SIG_SCHEME_LEGACY_ECDSA, SIG_SCHEME_ML_DSA_44, get_signature_scheme, is_known_signature_scheme
from ..crypto.pq.mldsa import ML_DSA_44_PUBLIC_KEY_SIZE, ML_DSA_44_SIGNATURE_SIZE


CHIPCOIN_SIGNATURE_DIGEST_BYTES = 32
MAX_PQ_SIGNATURE_SIZE = ML_DSA_44_SIGNATURE_SIZE
MAX_PQ_PUBLIC_KEY_SIZE = ML_DSA_44_PUBLIC_KEY_SIZE
MAX_PQ_INPUTS = 16
MAX_PQ_TX_SIZE = 64_000
MAX_PQ_SIGOPS_PER_TX = 16
MAX_PQ_SIGOPS_PER_BLOCK = 256
PQ_SIGOP_COST_ML_DSA_44 = 16
MAX_PQ_SIGNATURE_COST_PER_TX = MAX_PQ_SIGOPS_PER_TX * PQ_SIGOP_COST_ML_DSA_44
MAX_PQ_SIGNATURE_COST_PER_BLOCK = MAX_PQ_SIGOPS_PER_BLOCK * PQ_SIGOP_COST_ML_DSA_44


@dataclass(frozen=True)
class PQPolicyLimits:
    """Node-local PQ standardness limits."""

    max_pq_signature_size: int = MAX_PQ_SIGNATURE_SIZE
    max_pq_public_key_size: int = MAX_PQ_PUBLIC_KEY_SIZE
    max_pq_inputs: int = MAX_PQ_INPUTS
    max_pq_tx_size: int = MAX_PQ_TX_SIZE
    max_pq_sigops_per_tx: int = MAX_PQ_SIGOPS_PER_TX
    max_pq_sigops_per_block: int = MAX_PQ_SIGOPS_PER_BLOCK
    pq_sigop_cost_mldsa44: int = PQ_SIGOP_COST_ML_DSA_44

    @property
    def max_pq_signature_cost_per_tx(self) -> int:
        return self.max_pq_sigops_per_tx * self.pq_sigop_cost_mldsa44

    @property
    def max_pq_signature_cost_per_block(self) -> int:
        return self.max_pq_sigops_per_block * self.pq_sigop_cost_mldsa44


DEFAULT_PQ_POLICY_LIMITS = PQPolicyLimits()


class PQPolicyError(ValueError):
    """Raised when a transaction violates node-local PQ policy."""


def is_pq_transaction(transaction: Transaction) -> bool:
    """Return whether a transaction carries PQ inputs or CHCQ outputs."""

    return any(tx_input.sig_scheme_id != SIG_SCHEME_LEGACY_ECDSA for tx_input in transaction.inputs) or any(
        _address_kind(output.recipient) == "pq" for output in transaction.outputs
    )


def pq_sigop_count(transaction: Transaction) -> int:
    """Return the number of ML-DSA verification operations in a transaction."""

    return sum(1 for tx_input in transaction.inputs if tx_input.sig_scheme_id == SIG_SCHEME_ML_DSA_44)


def pq_signature_cost(transaction: Transaction, limits: PQPolicyLimits = DEFAULT_PQ_POLICY_LIMITS) -> int:
    """Return node-local PQ verification cost units for policy, logs and metrics."""

    return pq_sigop_count(transaction) * limits.pq_sigop_cost_mldsa44


def enforce_pq_mempool_precheck(
    transaction: Transaction,
    *,
    limits: PQPolicyLimits = DEFAULT_PQ_POLICY_LIMITS,
) -> None:
    """Reject malformed or non-standard PQ transactions before costly validation."""

    if not is_pq_transaction(transaction):
        return

    has_pq_input = any(tx_input.sig_scheme_id != SIG_SCHEME_LEGACY_ECDSA for tx_input in transaction.inputs)
    if has_pq_input and transaction.version != PQ_TRANSACTION_VERSION:
        raise PQPolicyError("PQ transaction must use transaction version 2.")

    pq_inputs = 0
    pq_sigops = 0
    for tx_input in transaction.inputs:
        if tx_input.sig_scheme_id == SIG_SCHEME_LEGACY_ECDSA:
            continue
        pq_inputs += 1
        if pq_inputs > limits.max_pq_inputs:
            raise PQPolicyError("PQ transaction exceeds mempool PQ input-count policy.")
        if not is_known_signature_scheme(tx_input.sig_scheme_id):
            raise PQPolicyError("PQ transaction input declares an unknown signature scheme.")
        scheme = get_signature_scheme(tx_input.sig_scheme_id)
        if not scheme.activated or not scheme.supports_verify:
            raise PQPolicyError("PQ transaction input uses a non-verification-capable signature scheme.")
        if tx_input.sig_scheme_id != SIG_SCHEME_ML_DSA_44:
            raise PQPolicyError("PQ transaction input uses an unsupported active signature scheme.")
        if not isinstance(tx_input.signature, bytes) or not isinstance(tx_input.public_key, bytes):
            raise PQPolicyError("PQ transaction input signature and public key must be bytes.")
        if len(tx_input.signature) != ML_DSA_44_SIGNATURE_SIZE:
            raise PQPolicyError("PQ transaction input signature has the wrong size for ML-DSA-44.")
        if len(tx_input.public_key) != ML_DSA_44_PUBLIC_KEY_SIZE:
            raise PQPolicyError("PQ transaction input public key has the wrong size for ML-DSA-44.")
        if len(tx_input.signature) > limits.max_pq_signature_size:
            raise PQPolicyError("PQ transaction input signature exceeds policy size.")
        if len(tx_input.public_key) > limits.max_pq_public_key_size:
            raise PQPolicyError("PQ transaction input public key exceeds policy size.")
        pq_sigops += 1

    if pq_sigops > limits.max_pq_sigops_per_tx:
        raise PQPolicyError("PQ transaction exceeds mempool PQ sigops policy.")
    if pq_signature_cost(transaction, limits) > limits.max_pq_signature_cost_per_tx:
        raise PQPolicyError("PQ transaction exceeds mempool PQ signature-cost policy.")

    serialized_size = len(serialize_transaction(transaction))
    if serialized_size > limits.max_pq_tx_size:
        raise PQPolicyError("PQ transaction exceeds mempool PQ size policy.")

    for output in transaction.outputs:
        try:
            address_info = parse_address(output.recipient)
        except ValueError as exc:
            raise PQPolicyError("PQ transaction output recipient is not a valid Chipcoin address.") from exc
        if address_info.kind != "pq":
            continue
        if address_info.scheme_id != SIG_SCHEME_ML_DSA_44:
            raise PQPolicyError("PQ transaction output uses an unsupported CHCQ signature scheme.")


def _address_kind(address: str) -> str | None:
    try:
        return parse_address(address).kind
    except ValueError:
        return None
