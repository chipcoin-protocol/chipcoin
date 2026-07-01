"""Wallet-side key handling and transaction signing boundary."""

from __future__ import annotations

from dataclasses import replace
import secrets

from ..consensus.models import ChipbitAmount, OutPoint, Transaction, TxInput, TxOutput
from ..consensus.epoch_settlement import RewardAttestation, reward_attestation_signature_digest
from ..consensus.nodes import (
    SPECIAL_NODE_SIGNATURE_VERSION_V2,
    special_node_signature_version_for_height,
    special_node_transaction_signature_digest,
    special_node_transaction_signature_digest_v2,
)
from ..consensus.validation import transaction_signature_digest
from ..crypto.addresses import is_valid_address, public_key_to_address, public_key_to_pq_address
from ..crypto.keys import derive_public_key, generate_private_key, serialize_public_key_hex
from ..crypto.pq import SIG_SCHEME_LEGACY_ECDSA, SIG_SCHEME_ML_DSA_44, get_signature_scheme
from ..crypto.pq.mldsa import ML_DSA_SEED_SIZE
from ..crypto.signatures import sign_digest
from .models import BuiltTransaction, SpendCandidate, WalletKey
from .selection import select_inputs


def wallet_key_from_private_key(private_key: bytes, *, compressed: bool = True) -> WalletKey:
    """Build a wallet key record from raw private key material."""

    public_key = derive_public_key(private_key, compressed=compressed)
    return WalletKey(
        private_key=private_key,
        public_key=public_key,
        address=public_key_to_address(public_key),
        compressed=compressed,
        scheme_id=SIG_SCHEME_LEGACY_ECDSA,
        scheme_name="secp256k1-ecdsa",
        address_kind="legacy",
    )


def wallet_key_from_mldsa44_seed(seed: bytes) -> WalletKey:
    """Build a CHCQ wallet key from canonical 32-byte ML-DSA-44 seed material."""

    scheme = get_signature_scheme(SIG_SCHEME_ML_DSA_44)
    private_material, public_key = scheme.derive_keypair(seed)
    return WalletKey(
        private_key=private_material,
        private_seed=seed,
        public_key=public_key,
        address=public_key_to_pq_address(public_key, scheme_id=SIG_SCHEME_ML_DSA_44),
        compressed=False,
        scheme_id=SIG_SCHEME_ML_DSA_44,
        scheme_name=scheme.name,
        address_kind="pq",
    )


def generate_wallet_key(*, compressed: bool = True, scheme: str = "secp256k1") -> WalletKey:
    """Generate a new wallet key pair."""

    if scheme in {"secp256k1", "ecdsa", "legacy"}:
        return wallet_key_from_private_key(generate_private_key(), compressed=compressed)
    if scheme == "mldsa44":
        return wallet_key_from_mldsa44_seed(secrets.token_bytes(ML_DSA_SEED_SIZE))
    raise ValueError(f"Unsupported wallet signature scheme: {scheme}")


def generate_legacy_wallet_key(*, compressed: bool = True) -> WalletKey:
    """Generate a legacy secp256k1 wallet key pair."""

    return wallet_key_from_private_key(generate_private_key(), compressed=compressed)


class TransactionSigner:
    """Sign digests and transactions outside the node core."""

    def __init__(self, wallet_key: WalletKey) -> None:
        self.wallet_key = wallet_key

    def sign(self, digest: bytes) -> bytes:
        """Sign a digest with wallet-controlled key material."""

        if self.wallet_key.scheme_id == SIG_SCHEME_ML_DSA_44:
            scheme = get_signature_scheme(self.wallet_key.scheme_id)
            seed = self.wallet_key.private_seed or self.wallet_key.private_key
            return scheme.sign(seed, digest)
        return sign_digest(self.wallet_key.private_key, digest)

    def build_signed_transaction(
        self,
        *,
        spend_candidates: list[SpendCandidate],
        recipient: str,
        amount_chipbits: int,
        fee_chipbits: int,
        change_recipient: str | None = None,
        locktime: int = 0,
        metadata: dict[str, str] | None = None,
        network: str = "mainnet",
    ) -> BuiltTransaction:
        """Construct and sign a transaction spending wallet-owned UTXOs."""

        if amount_chipbits <= 0:
            raise ValueError("Amount must be positive.")
        if fee_chipbits < 0:
            raise ValueError("Fee cannot be negative.")
        if not is_valid_address(recipient):
            raise ValueError("Recipient must be a valid Chipcoin address.")
        resolved_change_recipient = self.wallet_key.address if change_recipient is None else change_recipient
        if not is_valid_address(resolved_change_recipient):
            raise ValueError("Change recipient must be a valid Chipcoin address.")

        selection = select_inputs(spend_candidates, amount_chipbits + fee_chipbits)
        inputs = tuple(
            TxInput(
                previous_output=OutPoint(txid=candidate.txid, index=candidate.index),
                sig_scheme_id=self.wallet_key.scheme_id,
            )
            for candidate in selection.selected
        )
        outputs = [TxOutput(value=ChipbitAmount(amount_chipbits), recipient=recipient)]
        if selection.change_chipbits > 0:
            outputs.append(
                TxOutput(
                    value=ChipbitAmount(selection.change_chipbits),
                    recipient=resolved_change_recipient,
                )
            )

        transaction = Transaction(
            version=1 if self.wallet_key.scheme_id == SIG_SCHEME_LEGACY_ECDSA else 2,
            inputs=inputs,
            outputs=tuple(outputs),
            locktime=locktime,
            metadata={} if metadata is None else dict(metadata),
        )

        signed_inputs = []
        for input_index, candidate in enumerate(selection.selected):
            if candidate.recipient != self.wallet_key.address:
                raise ValueError("Spend candidate recipient does not belong to this wallet key.")
            digest = transaction_signature_digest(
                transaction,
                input_index,
                previous_output=TxOutput(value=ChipbitAmount(candidate.amount_chipbits), recipient=candidate.recipient),
                network=network,
            )
            signature = self.sign(digest)
            signed_inputs.append(
                replace(
                    transaction.inputs[input_index],
                    signature=signature,
                    public_key=self.wallet_key.public_key,
                    sig_scheme_id=self.wallet_key.scheme_id,
                )
            )

        signed_transaction = replace(transaction, inputs=tuple(signed_inputs))
        return BuiltTransaction(
            transaction=signed_transaction,
            fee_chipbits=fee_chipbits,
            change_chipbits=selection.change_chipbits,
        )

    def build_register_node_transaction(
        self,
        *,
        node_id: str,
        payout_address: str,
        network: str = "mainnet",
        height: int = 0,
    ) -> Transaction:
        """Construct and sign a special `register_node` transaction."""

        if not node_id:
            raise ValueError("Node id must not be empty.")
        if not is_valid_address(payout_address):
            raise ValueError("Payout address must be a valid CHC address.")
        metadata = {
            "kind": "register_node",
            "node_id": node_id,
            "payout_address": payout_address,
            "owner_pubkey_hex": serialize_public_key_hex(self.wallet_key.public_key),
            "owner_signature_hex": "",
        }
        return self._sign_special_node_metadata(metadata, network=network, height=height)

    def build_renew_node_transaction(
        self,
        *,
        node_id: str,
        renewal_epoch: int,
        network: str = "mainnet",
        height: int = 0,
    ) -> Transaction:
        """Construct and sign a special `renew_node` transaction."""

        if not node_id:
            raise ValueError("Node id must not be empty.")
        metadata = {
            "kind": "renew_node",
            "node_id": node_id,
            "renewal_epoch": str(renewal_epoch),
            "owner_pubkey_hex": serialize_public_key_hex(self.wallet_key.public_key),
            "owner_signature_hex": "",
        }
        return self._sign_special_node_metadata(metadata, network=network, height=height)

    def build_register_reward_node_transaction(
        self,
        *,
        node_id: str,
        payout_address: str,
        node_public_key_hex: str,
        declared_host: str,
        declared_port: int,
        registration_fee_chipbits: int,
        network: str = "mainnet",
        height: int = 0,
    ) -> Transaction:
        """Construct and sign a native `register_reward_node` transaction."""

        if not node_id:
            raise ValueError("Node id must not be empty.")
        if not is_valid_address(payout_address):
            raise ValueError("Payout address must be a valid CHC address.")
        if not node_public_key_hex:
            raise ValueError("Node public key hex must not be empty.")
        metadata = {
            "kind": "register_reward_node",
            "node_id": node_id,
            "payout_address": payout_address,
            "node_pubkey_hex": node_public_key_hex,
            "declared_host": declared_host,
            "declared_port": str(declared_port),
            "registration_fee_chipbits": str(registration_fee_chipbits),
            "owner_pubkey_hex": serialize_public_key_hex(self.wallet_key.public_key),
            "owner_signature_hex": "",
        }
        return self._sign_special_node_metadata(metadata, network=network, height=height)

    def build_renew_reward_node_transaction(
        self,
        *,
        node_id: str,
        renewal_epoch: int,
        declared_host: str,
        declared_port: int,
        renewal_fee_chipbits: int,
        network: str = "mainnet",
        height: int = 0,
    ) -> Transaction:
        """Construct and sign a native `renew_reward_node` transaction."""

        if not node_id:
            raise ValueError("Node id must not be empty.")
        metadata = {
            "kind": "renew_reward_node",
            "node_id": node_id,
            "renewal_epoch": str(renewal_epoch),
            "declared_host": declared_host,
            "declared_port": str(declared_port),
            "renewal_fee_chipbits": str(renewal_fee_chipbits),
            "owner_pubkey_hex": serialize_public_key_hex(self.wallet_key.public_key),
            "owner_signature_hex": "",
        }
        return self._sign_special_node_metadata(metadata, network=network, height=height)

    def _sign_special_node_metadata(self, metadata: dict[str, str], *, network: str, height: int) -> Transaction:
        required_version = special_node_signature_version_for_height(network=network, height=height)
        signed_metadata = dict(metadata)
        if required_version == SPECIAL_NODE_SIGNATURE_VERSION_V2:
            signed_metadata["owner_signature_version"] = SPECIAL_NODE_SIGNATURE_VERSION_V2
            signed_metadata["owner_signature_network"] = network
            unsigned = Transaction(version=1, inputs=(), outputs=(), metadata=signed_metadata)
            digest = special_node_transaction_signature_digest_v2(unsigned, network=network)
        else:
            unsigned = Transaction(version=1, inputs=(), outputs=(), metadata=signed_metadata)
            digest = special_node_transaction_signature_digest(unsigned)
        signed_metadata["owner_signature_hex"] = self.sign(digest).hex()
        return Transaction(version=1, inputs=(), outputs=(), metadata=signed_metadata)

    def sign_reward_attestation(self, attestation: RewardAttestation) -> RewardAttestation:
        """Sign one native reward attestation."""

        return replace(
            attestation,
            signature_hex=self.sign(reward_attestation_signature_digest(attestation)).hex(),
        )
