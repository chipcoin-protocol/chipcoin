import hashlib

import pytest

from chipcoin.crypto.pq.mldsa import (
    ML_DSA_44_PUBLIC_KEY_SIZE,
    ML_DSA_44_SIGNATURE_SIZE,
    ML_DSA_SEED_SIZE,
    derive_mldsa44_keypair,
    mldsa44_backend_info,
    sign_mldsa44,
    verify_mldsa44,
)


TEST_SEED = bytes(range(ML_DSA_SEED_SIZE))
TEST_DIGEST = bytes.fromhex("00" * 31 + "01")
EXPECTED_PRIVATE_KEY_SHA256 = "04bf6b9f579166a627961dfc5c3bf9717df868db88863856356c4668c8b56b0b"
EXPECTED_PUBLIC_KEY_SHA256 = "9f107644c1084526af3bc8098680b05499a2325a644e388fb4f970e058d19d46"
EXPECTED_SIGNATURE_SHA256 = "1fad42d544aac40d1c38ac277fad988b5eb675459cd4f3f83d477b613c1b4eb4"


def test_mldsa44_backend_metadata_is_pinned() -> None:
    info = mldsa44_backend_info()

    assert info["backend"] == "mldsa-native"
    assert info["upstream_commit"] == "9b0ee84f4cf399043eca59eca4e5f8531ca1d61b"
    assert info["scheme"] == "ML-DSA-44"
    assert info["seed_size"] == ML_DSA_SEED_SIZE
    assert info["public_key_size"] == ML_DSA_44_PUBLIC_KEY_SIZE
    assert info["signature_size"] == ML_DSA_44_SIGNATURE_SIZE


def test_mldsa44_deterministic_keygen_and_signing_vector() -> None:
    private_key, public_key = derive_mldsa44_keypair(TEST_SEED)
    signature = sign_mldsa44(TEST_SEED, TEST_DIGEST)

    assert len(private_key) == 2560
    assert len(public_key) == ML_DSA_44_PUBLIC_KEY_SIZE
    assert len(signature) == ML_DSA_44_SIGNATURE_SIZE
    assert hashlib.sha256(private_key).hexdigest() == EXPECTED_PRIVATE_KEY_SHA256
    assert hashlib.sha256(public_key).hexdigest() == EXPECTED_PUBLIC_KEY_SHA256
    assert hashlib.sha256(signature).hexdigest() == EXPECTED_SIGNATURE_SHA256
    assert verify_mldsa44(public_key, TEST_DIGEST, signature) is True


def test_mldsa44_signing_is_deterministic() -> None:
    assert sign_mldsa44(TEST_SEED, TEST_DIGEST) == sign_mldsa44(TEST_SEED, TEST_DIGEST)


def test_mldsa44_verify_rejects_modified_signature() -> None:
    _, public_key = derive_mldsa44_keypair(TEST_SEED)
    signature = bytearray(sign_mldsa44(TEST_SEED, TEST_DIGEST))
    signature[0] ^= 0x01

    assert verify_mldsa44(public_key, TEST_DIGEST, bytes(signature)) is False


def test_mldsa44_rejects_wrong_seed_and_digest_sizes() -> None:
    with pytest.raises(ValueError, match="seed"):
        derive_mldsa44_keypair(b"too-short")
    with pytest.raises(ValueError, match="digest"):
        sign_mldsa44(TEST_SEED, b"too-short")
    assert verify_mldsa44(b"short", TEST_DIGEST, b"short") is False
