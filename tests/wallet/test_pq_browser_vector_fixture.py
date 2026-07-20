import json
from pathlib import Path

from chipcoin.consensus.hashes import double_sha256
from chipcoin.consensus.models import OutPoint, Transaction, TxInput
from chipcoin.consensus.serialization import serialize_transaction, serialize_transaction_for_signing
from chipcoin.wallet.signer import TransactionSigner, wallet_key_from_mldsa44_seed
from tests.helpers import spend_candidates_for_wallet, wallet_key


def test_browser_pq_vector_fixture_matches_python_backend() -> None:
    fixture_path = Path("apps/browser-wallet/tests/fixtures/pq-vector-1.json")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    seed = bytes.fromhex(fixture["seed_hex"])
    owner = wallet_key_from_mldsa44_seed(seed)
    outpoint = OutPoint(**fixture["funding_outpoint"])
    built = TransactionSigner(owner).build_signed_transaction(
        spend_candidates=spend_candidates_for_wallet(outpoint, value=fixture["funding_value_chipbits"], owner=owner),
        recipient=wallet_key(1).address,
        amount_chipbits=fixture["amount_chipbits"],
        fee_chipbits=fixture["fee_chipbits"],
        metadata=fixture["metadata"],
        network=fixture["network"],
    )
    unsigned = Transaction(
        version=built.transaction.version,
        inputs=tuple(
            TxInput(
                previous_output=tx_input.previous_output,
                sequence=tx_input.sequence,
                sig_scheme_id=tx_input.sig_scheme_id,
            )
            for tx_input in built.transaction.inputs
        ),
        outputs=built.transaction.outputs,
        locktime=built.transaction.locktime,
        metadata=built.transaction.metadata,
    )
    signing_payload = serialize_transaction_for_signing(
        built.transaction,
        0,
        previous_output_value=fixture["funding_value_chipbits"],
        previous_output_recipient=owner.address,
        network=fixture["network"],
    )
    raw = serialize_transaction(built.transaction)

    assert owner.address == fixture["address"]
    assert serialize_transaction(unsigned).hex() == fixture["unsigned_tx_hex"]
    assert signing_payload.hex() == fixture["signing_payload_hex"]
    assert double_sha256(signing_payload).hex() == fixture["signature_digest_hex"]
    assert built.transaction.txid() == fixture["txid"]
    assert len(raw) == fixture["raw_tx_len"]
