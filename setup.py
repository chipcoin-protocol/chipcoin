"""Build configuration for Chipcoin."""

from __future__ import annotations

from pathlib import Path

from setuptools import Extension, setup


ROOT = Path(__file__).parent
MLDSA_ROOT = ROOT / "vendor" / "mldsa-native" / "mldsa"


def mldsa44_extension() -> Extension:
    """Return the pinned ML-DSA-44 native extension definition."""

    return Extension(
        "chipcoin.crypto.pq._mldsa_native",
        sources=[
            "src/chipcoin/crypto/pq/_mldsa_native.c",
            "vendor/mldsa-native/mldsa/mldsa_native.c",
        ],
        include_dirs=[
            str(MLDSA_ROOT),
        ],
        define_macros=[
            ("MLD_CONFIG_PARAMETER_SET", "44"),
            ("MLD_CONFIG_NAMESPACE_PREFIX", "CHIPCOIN_MLDSA44"),
            ("MLD_CONFIG_CORE_API_ONLY", "1"),
            ("MLD_CONFIG_NO_RANDOMIZED_API", "1"),
            ("MLD_CONFIG_NO_SUPERCOP", "1"),
        ],
    )


setup(ext_modules=[mldsa44_extension()])
