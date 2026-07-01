"""Central signature scheme registry."""

from __future__ import annotations

from .base import SignatureScheme
from .mldsa import (
    ML_DSA_44_PUBLIC_KEY_SIZE,
    ML_DSA_44_SIGNATURE_SIZE,
    derive_mldsa44_keypair,
    sign_mldsa44,
    verify_mldsa44,
)


SIG_SCHEME_LEGACY_ECDSA = 0
SIG_SCHEME_ML_DSA_44 = 10
SIG_SCHEME_ML_DSA_65_RESERVED = 11
SIG_SCHEME_FALCON_RESERVED = 20
SIG_SCHEME_SPHINCS_RESERVED = 30


_SCHEMES: dict[int, SignatureScheme] = {
    SIG_SCHEME_LEGACY_ECDSA: SignatureScheme(
        scheme_id=SIG_SCHEME_LEGACY_ECDSA,
        name="secp256k1-ecdsa",
        public_key_size=None,
        signature_size=None,
        supports_sign=True,
        supports_verify=True,
        supports_addresses=True,
        activated=True,
    ),
    SIG_SCHEME_ML_DSA_44: SignatureScheme(
        scheme_id=SIG_SCHEME_ML_DSA_44,
        name="mldsa44",
        public_key_size=ML_DSA_44_PUBLIC_KEY_SIZE,
        signature_size=ML_DSA_44_SIGNATURE_SIZE,
        supports_sign=True,
        supports_verify=True,
        supports_addresses=True,
        activated=True,
        signer=sign_mldsa44,
        verifier=verify_mldsa44,
        key_deriver=derive_mldsa44_keypair,
    ),
    SIG_SCHEME_ML_DSA_65_RESERVED: SignatureScheme(
        scheme_id=SIG_SCHEME_ML_DSA_65_RESERVED,
        name="mldsa65-reserved",
        public_key_size=None,
        signature_size=None,
        supports_sign=False,
        supports_verify=False,
        supports_addresses=False,
        activated=False,
    ),
    SIG_SCHEME_FALCON_RESERVED: SignatureScheme(
        scheme_id=SIG_SCHEME_FALCON_RESERVED,
        name="falcon-reserved",
        public_key_size=None,
        signature_size=None,
        supports_sign=False,
        supports_verify=False,
        supports_addresses=False,
        activated=False,
    ),
    SIG_SCHEME_SPHINCS_RESERVED: SignatureScheme(
        scheme_id=SIG_SCHEME_SPHINCS_RESERVED,
        name="sphincs-plus-reserved",
        public_key_size=None,
        signature_size=None,
        supports_sign=False,
        supports_verify=False,
        supports_addresses=False,
        activated=False,
    ),
}


def get_signature_scheme(scheme_id: int) -> SignatureScheme:
    """Return registry metadata for a known signature scheme."""

    try:
        return _SCHEMES[scheme_id]
    except KeyError as exc:
        raise ValueError(f"Unknown signature scheme id: {scheme_id}") from exc


def is_known_signature_scheme(scheme_id: int) -> bool:
    """Return whether a signature scheme id is reserved or active."""

    return scheme_id in _SCHEMES
