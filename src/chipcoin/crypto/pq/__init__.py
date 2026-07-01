"""Post-quantum signature scheme registry."""

from .schemes import (
    SIG_SCHEME_FALCON_RESERVED,
    SIG_SCHEME_LEGACY_ECDSA,
    SIG_SCHEME_ML_DSA_44,
    SIG_SCHEME_ML_DSA_65_RESERVED,
    SIG_SCHEME_SPHINCS_RESERVED,
    SignatureScheme,
    get_signature_scheme,
    is_known_signature_scheme,
)

__all__ = [
    "SIG_SCHEME_FALCON_RESERVED",
    "SIG_SCHEME_LEGACY_ECDSA",
    "SIG_SCHEME_ML_DSA_44",
    "SIG_SCHEME_ML_DSA_65_RESERVED",
    "SIG_SCHEME_SPHINCS_RESERVED",
    "SignatureScheme",
    "get_signature_scheme",
    "is_known_signature_scheme",
]
