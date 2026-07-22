import pytest

from chipcoin.consensus.models import Block, BlockHeader, OutPoint, Transaction, TxInput, TxOutput
from chipcoin.consensus.serialization import (
    deserialize_transaction,
    serialize_block,
    serialize_transaction,
    serialize_transaction_for_signing,
)


def test_transaction_serialization_is_stable() -> None:
    transaction = Transaction(
        version=1,
        inputs=(
            TxInput(
                previous_output=OutPoint(txid="AB" * 32, index=1),
                signature=b"\x01\x02",
                public_key=b"\x03\x04\x05",
                sequence=0xFFFFFFFE,
            ),
        ),
        outputs=(TxOutput(value=25, recipient="CHCabc"),),
        locktime=9,
        metadata={"purpose": "test"},
    )

    first = serialize_transaction(transaction)
    second = serialize_transaction(transaction)

    assert first == second
    assert len(first) > 0


def test_v1_transaction_serialization_byte_identity() -> None:
    transaction = Transaction(
        version=1,
        inputs=(
            TxInput(
                previous_output=OutPoint(txid="AB" * 32, index=1),
                signature=b"\x01\x02",
                public_key=b"\x03\x04\x05",
                sequence=0xFFFFFFFE,
            ),
        ),
        outputs=(TxOutput(value=25, recipient="CHCabc"),),
        locktime=9,
        metadata={"purpose": "test"},
    )

    assert serialize_transaction(transaction).hex() == (
        "0100000001"
        "abababababababababababababababababababababababababababababababab"
        "01000000"
        "020102"
        "03030405"
        "feffffff"
        "01"
        "1900000000000000"
        "06434843616263"
        "09000000"
        "01"
        "07707572706f7365"
        "0474657374"
    )


def test_v1_transaction_serialization_rejects_non_legacy_scheme_id() -> None:
    transaction = Transaction(
        version=1,
        inputs=(
            TxInput(
                previous_output=OutPoint(txid="AB" * 32, index=1),
                signature=b"\x01",
                public_key=b"\x02",
                sig_scheme_id=10,
            ),
        ),
        outputs=(TxOutput(value=25, recipient="CHCabc"),),
    )

    try:
        serialize_transaction(transaction)
    except ValueError:
        return
    raise AssertionError("Expected v1 serialization to reject non-legacy sig_scheme_id.")


def test_v2_transaction_serialization_includes_sig_scheme_id() -> None:
    transaction = Transaction(
        version=2,
        inputs=(
            TxInput(
                previous_output=OutPoint(txid="11" * 32, index=7),
                signature=b"\xaa",
                public_key=b"\xbb\xcc",
                sequence=0xFFFFFFFD,
                sig_scheme_id=10,
            ),
        ),
        outputs=(TxOutput(value=12, recipient="CHCabc"),),
        locktime=3,
    )

    encoded = serialize_transaction(transaction)
    decoded, offset = deserialize_transaction(encoded)

    assert encoded.hex() == (
        "0200000001"
        "1111111111111111111111111111111111111111111111111111111111111111"
        "07000000"
        "0a"
        "01aa"
        "02bbcc"
        "fdffffff"
        "01"
        "0c00000000000000"
        "06434843616263"
        "03000000"
        "00"
    )
    assert offset == len(encoded)
    assert decoded == transaction


def test_v2_signing_serialization_includes_scheme_id_and_network_domain() -> None:
    transaction = Transaction(
        version=2,
        inputs=(
            TxInput(
                previous_output=OutPoint(txid="11" * 32, index=7),
                signature=b"\xaa",
                public_key=b"\xbb\xcc",
                sequence=0xFFFFFFFD,
                sig_scheme_id=10,
            ),
        ),
        outputs=(TxOutput(value=12, recipient="CHCabc"),),
        locktime=3,
    )

    payload = serialize_transaction_for_signing(
        transaction,
        0,
        previous_output_value=20,
        previous_output_recipient="CHCprev",
        network="testnet",
    )

    assert b"chipcoin:tx-signature:v2:testnet" in payload
    assert "070000000a0000fdffffff" in payload.hex()
    assert payload.endswith((2).to_bytes(4, "little"))


def test_deserialize_transaction_rejects_truncated_extended_varint() -> None:
    payload = b"\x02\x00\x00\x00\xfd"

    with pytest.raises(ValueError, match="Unexpected end of payload while decoding varint"):
        deserialize_transaction(payload)


def test_block_serialization_includes_header_and_transactions() -> None:
    transaction = Transaction(
        version=1,
        inputs=(),
        outputs=(TxOutput(value=50, recipient="CHCminer"),),
        metadata={"coinbase": "true"},
    )
    header = BlockHeader(
        version=1,
        previous_block_hash="00" * 32,
        merkle_root="11" * 32,
        timestamp=1,
        bits=0x207FFFFF,
        nonce=0,
    )
    block = Block(header=header, transactions=(transaction,))

    encoded = serialize_block(block)

    assert len(encoded) > 80
    assert encoded[:4] == (1).to_bytes(4, byteorder="little", signed=False)
