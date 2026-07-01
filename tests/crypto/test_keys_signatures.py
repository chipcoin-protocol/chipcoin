from chipcoin.consensus.hashes import double_sha256
import pytest

from chipcoin.crypto.addresses import (
    PQ_ADDRESS_PREFIX,
    PQ_ADDRESS_VERSION,
    address_to_public_key_hash,
    address_to_pq_commitment,
    is_valid_address,
    parse_address,
    pq_public_key_commitment,
    public_key_hash,
    public_key_to_address,
    public_key_to_pq_address,
)
from chipcoin.crypto.pq import SIG_SCHEME_ML_DSA_44
from chipcoin.crypto.keys import (
    derive_public_key,
    generate_private_key,
    parse_private_key_hex,
    serialize_private_key_hex,
)
from chipcoin.crypto.signatures import sign_digest, verify_digest


def test_generate_private_key_and_roundtrip_hex() -> None:
    private_key = generate_private_key()

    assert len(private_key) == 32
    assert parse_private_key_hex(serialize_private_key_hex(private_key)) == private_key


def test_sign_and_verify_digest_with_secp256k1() -> None:
    private_key = parse_private_key_hex("0000000000000000000000000000000000000000000000000000000000000001")
    public_key = derive_public_key(private_key)
    digest = double_sha256(b"chipcoin-signed-message")
    signature = sign_digest(private_key, digest)

    assert verify_digest(public_key, digest, signature) is True
    assert verify_digest(public_key, double_sha256(b"tampered"), signature) is False


def test_address_derivation_has_checksum_and_embedded_pubkey_hash() -> None:
    private_key = parse_private_key_hex("0000000000000000000000000000000000000000000000000000000000000002")
    public_key = derive_public_key(private_key)
    address = public_key_to_address(public_key)

    assert address.startswith("CHC")
    assert is_valid_address(address) is True
    assert address_to_public_key_hash(address) == public_key_hash(public_key)


def test_address_info_parses_legacy_chc() -> None:
    private_key = parse_private_key_hex("0000000000000000000000000000000000000000000000000000000000000003")
    public_key = derive_public_key(private_key)
    address = public_key_to_address(public_key)

    info = parse_address(address)

    assert info.kind == "legacy"
    assert info.prefix == "CHC"
    assert info.version == 0x1C
    assert info.scheme_id == 0
    assert info.hash_or_commitment == public_key_hash(public_key)


def test_chcq_address_roundtrip_uses_sha3_commitment() -> None:
    public_key = b"\x42" * 1312
    address = public_key_to_pq_address(public_key, scheme_id=SIG_SCHEME_ML_DSA_44)

    info = parse_address(address)
    scheme_id, commitment = address_to_pq_commitment(address)

    assert address.startswith(PQ_ADDRESS_PREFIX)
    assert info.kind == "pq"
    assert info.prefix == PQ_ADDRESS_PREFIX
    assert info.version == PQ_ADDRESS_VERSION
    assert info.scheme_id == SIG_SCHEME_ML_DSA_44
    assert scheme_id == SIG_SCHEME_ML_DSA_44
    assert commitment == pq_public_key_commitment(public_key)
    assert is_valid_address(address) is True


def test_legacy_chc_parser_does_not_accept_chcq() -> None:
    address = public_key_to_pq_address(b"\x24" * 1312, scheme_id=SIG_SCHEME_ML_DSA_44)

    assert parse_address(address).kind == "pq"
    with pytest.raises(ValueError, match="not a legacy CHC address"):
        address_to_public_key_hash(address)
