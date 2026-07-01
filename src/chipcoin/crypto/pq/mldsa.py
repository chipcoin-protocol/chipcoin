"""ML-DSA backend boundary.

The current runtime dependency set may not expose ML-DSA. This module keeps the
consensus call site stable while making backend availability explicit.
"""

from __future__ import annotations

import hashlib


ML_DSA_44_PUBLIC_KEY_SIZE = 1312
ML_DSA_44_SIGNATURE_SIZE = 2420
ML_DSA_SEED_SIZE = 32


class MLDsaBackendUnavailable(RuntimeError):
    """Raised when no pinned ML-DSA backend is available."""


def mldsa44_backend_available() -> bool:
    """Return whether the configured runtime exposes ML-DSA-44."""

    try:
        from cryptography.hazmat.primitives.asymmetric import mldsa  # noqa: F401
    except Exception:
        return False
    return True


def derive_mldsa44_keypair(seed: bytes) -> tuple[bytes, bytes]:
    """Derive an ML-DSA-44 keypair from the canonical 32-byte wallet seed."""

    if len(seed) != ML_DSA_SEED_SIZE:
        raise ValueError("ML-DSA-44 seed must be exactly 32 bytes.")
    raise MLDsaBackendUnavailable("No pinned ML-DSA-44 key derivation backend is configured.")


def sign_mldsa44(seed: bytes, digest: bytes) -> bytes:
    """Sign a transaction digest with ML-DSA-44."""

    if len(seed) != ML_DSA_SEED_SIZE:
        raise ValueError("ML-DSA-44 seed must be exactly 32 bytes.")
    if len(digest) != 32:
        raise ValueError("Transaction signature digest must be exactly 32 bytes.")
    raise MLDsaBackendUnavailable("No pinned ML-DSA-44 signing backend is configured.")


def verify_mldsa44(public_key: bytes, digest: bytes, signature: bytes) -> bool:
    """Verify an ML-DSA-44 signature with the pinned consensus backend."""

    if len(public_key) != ML_DSA_44_PUBLIC_KEY_SIZE:
        return False
    if len(signature) != ML_DSA_44_SIGNATURE_SIZE:
        return False
    if len(digest) != 32:
        return False
    raise MLDsaBackendUnavailable("No pinned ML-DSA-44 verification backend is configured.")


def derive_mldsa44_test_keypair(seed: bytes) -> tuple[bytes, bytes]:
    """Deterministic architecture-test keypair, not a production PQ backend."""

    if len(seed) != ML_DSA_SEED_SIZE:
        raise ValueError("ML-DSA-44 seed must be exactly 32 bytes.")
    public_key = hashlib.shake_256(b"chipcoin:mldsa44-test-pub:" + seed).digest(ML_DSA_44_PUBLIC_KEY_SIZE)
    return seed, public_key


def sign_mldsa44_test(seed: bytes, digest: bytes) -> bytes:
    """Deterministic architecture-test signature, not a production PQ backend."""

    _, public_key = derive_mldsa44_test_keypair(seed)
    return hashlib.shake_256(b"chipcoin:mldsa44-test-sig:" + public_key + digest).digest(ML_DSA_44_SIGNATURE_SIZE)


def verify_mldsa44_test(public_key: bytes, digest: bytes, signature: bytes) -> bool:
    """Verify deterministic architecture-test signatures."""

    if len(public_key) != ML_DSA_44_PUBLIC_KEY_SIZE:
        return False
    if len(signature) != ML_DSA_44_SIGNATURE_SIZE:
        return False
    if len(digest) != 32:
        return False
    expected = hashlib.shake_256(b"chipcoin:mldsa44-test-sig:" + public_key + digest).digest(ML_DSA_44_SIGNATURE_SIZE)
    return expected == signature
