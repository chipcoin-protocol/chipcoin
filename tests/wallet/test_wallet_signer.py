import hashlib

from chipcoin.consensus.models import OutPoint, TxOutput
from chipcoin.consensus.serialization import serialize_transaction
from chipcoin.consensus.validation import ValidationContext, validate_transaction
from chipcoin.consensus.params import MAINNET_PARAMS
from chipcoin.consensus.utxo import InMemoryUtxoView, UtxoEntry
from chipcoin.crypto.pq import SIG_SCHEME_ML_DSA_44
from chipcoin.wallet.selection import select_inputs
from chipcoin.wallet.signer import TransactionSigner, wallet_key_from_mldsa44_seed
from tests.helpers import spend_candidates_for_wallet, wallet_key


def test_select_inputs_returns_change_amount() -> None:
    candidates = [
        *spend_candidates_for_wallet(OutPoint(txid="11" * 32, index=0), value=30),
        *spend_candidates_for_wallet(OutPoint(txid="22" * 32, index=0), value=80),
    ]

    selection = select_inputs(candidates, 90)

    assert selection.total_input_chipbits == 110
    assert selection.change_chipbits == 20
    assert len(selection.selected) == 2


def test_transaction_signer_builds_valid_signed_transaction() -> None:
    owner = wallet_key(0)
    recipient = wallet_key(1).address
    outpoint = OutPoint(txid="33" * 32, index=0)
    signer = TransactionSigner(owner)
    built = signer.build_signed_transaction(
        spend_candidates=spend_candidates_for_wallet(outpoint, value=125, owner=owner),
        recipient=recipient,
        amount_chipbits=100,
        fee_chipbits=5,
        metadata={"kind": "payment"},
    )
    context = ValidationContext(
        height=2,
        median_time_past=0,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView.from_entries(
            [
                (
                    outpoint,
                    UtxoEntry(
                        output=TxOutput(value=125, recipient=owner.address),
                        height=1,
                        is_coinbase=False,
                    ),
                )
            ]
        ),
    )

    fee = validate_transaction(built.transaction, context)

    assert fee == 5
    assert built.change_chipbits == 20
    assert built.transaction.outputs[0].recipient == recipient
    assert built.transaction.outputs[1].recipient == owner.address


def test_transaction_signer_builds_post_activation_pq_vector() -> None:
    seed = bytes(range(32))
    owner = wallet_key_from_mldsa44_seed(seed)
    recipient = wallet_key(1).address
    outpoint = OutPoint(txid="66" * 32, index=1)
    signer = TransactionSigner(owner)
    built = signer.build_signed_transaction(
        spend_candidates=spend_candidates_for_wallet(outpoint, value=1_234_567_890, owner=owner),
        recipient=recipient,
        amount_chipbits=1_000_000_000,
        fee_chipbits=1_000,
        metadata={"kind": "payment", "purpose": "pq-vector-1"},
        network="testnet",
    )
    context = ValidationContext(
        height=30_000,
        median_time_past=0,
        params=MAINNET_PARAMS,
        utxo_view=InMemoryUtxoView.from_entries(
            [
                (
                    outpoint,
                    UtxoEntry(
                        output=TxOutput(value=1_234_567_890, recipient=owner.address),
                        height=29_999,
                        is_coinbase=False,
                    ),
                )
            ]
        ),
        network="testnet",
    )

    fee = validate_transaction(built.transaction, context)
    serialized = serialize_transaction(built.transaction)

    assert owner.address == "CHCQCqjJWcT8Jqxvmn9xspxBWnTojXQp93Wqu9sP5F6GkFd1f5xKiRhE"
    assert built.transaction.version == 2
    assert built.transaction.inputs[0].sig_scheme_id == SIG_SCHEME_ML_DSA_44
    assert fee == 1_000
    assert built.change_chipbits == 234_566_890
    assert built.transaction.txid() == "05eb8549e696aa818d5a20aa585a12959c80ebeaa6035c8a44272caf17f7c2ce"
    assert hashlib.sha256(owner.private_key).hexdigest() == "04bf6b9f579166a627961dfc5c3bf9717df868db88863856356c4668c8b56b0b"
    assert hashlib.sha256(owner.public_key).hexdigest() == "9f107644c1084526af3bc8098680b05499a2325a644e388fb4f970e058d19d46"
    assert hashlib.sha256(built.transaction.inputs[0].signature).hexdigest() == "d1af5447e0758334b719a99849e10062821f2b7d9fea01be35f2ed15f3a7ccfe"
    assert hashlib.sha256(serialized).hexdigest() == "a873e1e18fca2457bac12386176035be8c80a5de0e4f2eb039d5b15be9198623"
    assert len(serialized) == 3_934


def test_transaction_signer_rejects_invalid_recipient_address() -> None:
    owner = wallet_key(0)
    outpoint = OutPoint(txid="44" * 32, index=0)
    signer = TransactionSigner(owner)

    try:
        signer.build_signed_transaction(
            spend_candidates=spend_candidates_for_wallet(outpoint, value=125, owner=owner),
            recipient="CHC-not-an-address",
            amount_chipbits=100,
            fee_chipbits=5,
        )
    except ValueError as exc:
        assert "Recipient" in str(exc)
        return

    raise AssertionError("Expected invalid recipient address to be rejected.")
