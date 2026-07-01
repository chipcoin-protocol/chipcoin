"""Address derivation helpers.

Chipcoin uses a didactic address format:

- ASCII prefix ``CHC``
- Base58Check payload containing:
  - 1 version byte
  - 20-byte HASH160 of the SEC1 public key

Post-quantum testnet addresses use:

- ASCII prefix ``CHCQ``
- Base58Check payload containing:
  - 1 version byte
  - 1 signature scheme id byte
  - 32-byte SHA3-256 public-key commitment
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Literal

from ..consensus.hashes import double_sha256
from .keys import load_public_key


ADDRESS_PREFIX = "CHC"
ADDRESS_VERSION = 0x1C
PQ_ADDRESS_PREFIX = "CHCQ"
PQ_ADDRESS_VERSION = 0x50
PQ_PUBLIC_KEY_COMMITMENT_SIZE = 32
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


@dataclass(frozen=True)
class AddressInfo:
    """Structured result from longest-prefix-first address parsing."""

    kind: Literal["legacy", "pq"]
    prefix: str
    version: int
    scheme_id: int
    payload: bytes
    hash_or_commitment: bytes


def hash160(payload: bytes) -> bytes:
    """Return HASH160(payload) = RIPEMD160(SHA256(payload))."""

    sha = hashlib.sha256(payload).digest()
    return hashlib.new("ripemd160", sha).digest()


def public_key_hash(public_key: bytes) -> bytes:
    """Return the 20-byte public-key hash used in addresses."""

    return hash160(public_key)


def pq_public_key_commitment(public_key: bytes) -> bytes:
    """Return the 32-byte SHA3-256 public-key commitment for CHCQ."""

    return hashlib.sha3_256(public_key).digest()


def public_key_to_address(public_key: bytes) -> str:
    """Derive a Chipcoin address from a public key."""

    _ = load_public_key(public_key)
    payload = bytes((ADDRESS_VERSION,)) + public_key_hash(public_key)
    return ADDRESS_PREFIX + _base58check_encode(payload)


def public_key_to_pq_address(public_key: bytes, *, scheme_id: int) -> str:
    """Derive a CHCQ address from raw post-quantum public key bytes."""

    if scheme_id < 0 or scheme_id > 0xFF:
        raise ValueError("Signature scheme id must fit in one byte.")
    commitment = pq_public_key_commitment(public_key)
    payload = bytes((PQ_ADDRESS_VERSION, scheme_id)) + commitment
    return PQ_ADDRESS_PREFIX + _base58check_encode(payload)


def parse_address(address: str) -> AddressInfo:
    """Parse a Chipcoin address using longest-prefix-first matching."""

    if address.startswith(PQ_ADDRESS_PREFIX):
        payload = _base58check_decode(address[len(PQ_ADDRESS_PREFIX) :])
        if len(payload) != 34:
            raise ValueError("CHCQ address payload has an unexpected length.")
        if payload[0] != PQ_ADDRESS_VERSION:
            raise ValueError("CHCQ address version byte is not recognised.")
        commitment = payload[2:]
        if len(commitment) != PQ_PUBLIC_KEY_COMMITMENT_SIZE:
            raise ValueError("CHCQ public-key commitment has an unexpected length.")
        return AddressInfo(
            kind="pq",
            prefix=PQ_ADDRESS_PREFIX,
            version=payload[0],
            scheme_id=payload[1],
            payload=payload,
            hash_or_commitment=commitment,
        )
    if address.startswith(ADDRESS_PREFIX):
        payload = _base58check_decode(address[len(ADDRESS_PREFIX) :])
        if len(payload) != 21:
            raise ValueError("Address payload has an unexpected length.")
        if payload[0] != ADDRESS_VERSION:
            raise ValueError("Address version byte is not recognised.")
        return AddressInfo(
            kind="legacy",
            prefix=ADDRESS_PREFIX,
            version=payload[0],
            scheme_id=0,
            payload=payload,
            hash_or_commitment=payload[1:],
        )
    raise ValueError("Address does not start with a recognised Chipcoin prefix.")


def address_to_public_key_hash(address: str) -> bytes:
    """Decode a Chipcoin address and return the contained 20-byte hash."""

    info = parse_address(address)
    if info.kind != "legacy":
        raise ValueError("Address is not a legacy CHC address.")
    return info.hash_or_commitment


def address_to_pq_commitment(address: str) -> tuple[int, bytes]:
    """Decode a CHCQ address and return its scheme id and commitment."""

    info = parse_address(address)
    if info.kind != "pq":
        raise ValueError("Address is not a CHCQ address.")
    return info.scheme_id, info.hash_or_commitment


def is_valid_address(address: str) -> bool:
    """Return whether a string is a valid Chipcoin address."""

    try:
        parse_address(address)
    except ValueError:
        return False
    return True


def _base58check_encode(payload: bytes) -> str:
    """Encode payload + checksum in Base58."""

    data = payload + double_sha256(payload)[:4]
    zeros = len(data) - len(data.lstrip(b"\x00"))
    value = int.from_bytes(data, "big")
    encoded = ""
    while value:
        value, remainder = divmod(value, 58)
        encoded = _BASE58_ALPHABET[remainder] + encoded
    return ("1" * zeros) + (encoded or "1")


def _base58check_decode(value: str) -> bytes:
    """Decode Base58Check text and validate its checksum."""

    number = 0
    for character in value:
        index = _BASE58_ALPHABET.find(character)
        if index == -1:
            raise ValueError("Address contains a non-Base58 character.")
        number = number * 58 + index

    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    zeros = len(value) - len(value.lstrip("1"))
    raw = (b"\x00" * zeros) + raw
    if len(raw) < 5:
        raise ValueError("Address payload is too short.")
    payload, checksum = raw[:-4], raw[-4:]
    if double_sha256(payload)[:4] != checksum:
        raise ValueError("Address checksum is invalid.")
    return payload
