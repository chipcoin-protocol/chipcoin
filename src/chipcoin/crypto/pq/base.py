"""Interfaces for post-quantum signature backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


Signer = Callable[[bytes, bytes], bytes]
Verifier = Callable[[bytes, bytes, bytes], bool]
KeyDeriver = Callable[[bytes], tuple[bytes, bytes]]


@dataclass(frozen=True)
class SignatureScheme:
    """Consensus-facing metadata for one signature scheme."""

    scheme_id: int
    name: str
    public_key_size: int | None
    signature_size: int | None
    supports_sign: bool
    supports_verify: bool
    supports_addresses: bool
    activated: bool
    signer: Signer | None = None
    verifier: Verifier | None = None
    key_deriver: KeyDeriver | None = None

    def sign(self, private_material: bytes, digest: bytes) -> bytes:
        if self.signer is None:
            raise RuntimeError(f"{self.name} signing backend is not configured.")
        return self.signer(private_material, digest)

    def verify(self, public_key: bytes, digest: bytes, signature: bytes) -> bool:
        if self.verifier is None:
            raise RuntimeError(f"{self.name} verification backend is not configured.")
        return self.verifier(public_key, digest, signature)

    def derive_keypair(self, seed: bytes) -> tuple[bytes, bytes]:
        if self.key_deriver is None:
            raise RuntimeError(f"{self.name} key derivation backend is not configured.")
        return self.key_deriver(seed)
