# Post-Quantum Address and Signature Support

This document describes the Chipcoin testnet architecture for post-quantum
UTXO ownership. It does not change PoW, block hashes, transaction ids, Merkle
roots, block format, or mining consensus.

Public wording must stay conservative:

- post-quantum support in testnet
- experimental
- not audited yet
- designed for future quantum-resistance

Do not describe this as quantum-proof mainnet.

## Legacy CHC Addresses

Legacy addresses remain unchanged:

```text
CHC + Base58Check(0x1c || HASH160(sec1_secp256k1_public_key))
```

Legacy transaction version `1` serialization, txid behavior, secp256k1 ECDSA
signatures, wallet files, and validation are preserved.

## CHCQ Addresses

Post-quantum addresses use the distinct prefix `CHCQ`:

```text
CHCQ + Base58Check(payload)
```

Payload:

```text
version:uint8      = 0x50
scheme_id:uint8
commitment:bytes32 = SHA3-256(raw_pq_public_key)
```

The version byte is fixed as `PQ_ADDRESS_VERSION = 0x50`. Do not change it
after test vectors are generated.

CHCQ does not use HASH160 and does not add BLAKE3. Base58Check reuses the
existing `double_sha256(payload)[:4]` checksum only for typo detection.

Address parsing is longest-prefix-first:

1. `CHCQ`
2. `CHC`

This prevents CHCQ addresses from being misparsed as legacy CHC addresses.

## Signature Scheme Registry

Scheme ids are explicit and must never be inferred from public key length.

| ID | Name | Status |
| --- | --- | --- |
| `0` | secp256k1 / ECDSA | legacy active |
| `10` | ML-DSA-44 | first post-quantum candidate |
| `11` | ML-DSA-65 | reserved |
| `20` | Falcon | reserved |
| `30` | SPHINCS+ | reserved |

Registry entries include name, public key size, signature size, signer,
verifier, activation/support status, and capabilities:

- `supports_sign`
- `supports_verify`
- `supports_addresses`

Unknown scheme ids are consensus-invalid.

## ML-DSA-44 Sizes

ML-DSA-44 consensus checks use exact sizes before verifier calls:

```text
public key: 1312 bytes
signature: 2420 bytes
seed:       32 bytes
```

Wallet backup/export material is the 32-byte ML-DSA seed. The expanded private
key is not the canonical backup format. If a backend requires storing expanded
private key material, it must be documented separately while keeping the seed
as canonical.

## Transaction Version 2

For `Transaction.version == 1`, input serialization is unchanged:

```text
previous_txid:32
previous_index:u32le
signature:varbytes
public_key:varbytes
sequence:u32le
```

Version 1 rejects non-zero `sig_scheme_id`.

For `Transaction.version >= 2`, each input serializes:

```text
previous_txid:32
previous_index:u32le
sig_scheme_id:u8
signature:varbytes
public_key:varbytes
sequence:u32le
```

Mixed CHC/CHCQ transactions are represented input-by-input. CHC inputs use
`sig_scheme_id = 0`; CHCQ inputs use the scheme id encoded in the address.

## Version 2 Signature Digest

The v2 signing serialization strips signatures and public keys but preserves
each input's `sig_scheme_id`.

The v2 digest includes a network-bound domain:

```text
chipcoin:tx-signature:v2:<network>
```

The final digest is:

```text
double_sha256(v2_signing_payload)
```

This prevents replaying signatures across devnet, testnet, and mainnet.

## Activation

Activation is centralized in `src/chipcoin/consensus/pq_activation.py`.

Current constants:

```text
mainnet: 0
devnet:  30000
testnet: 30000
```

Before activation:

- CHCQ outputs are rejected
- CHCQ spends are rejected
- v2 wallet spends are rejected unless a separate v2-CHC reason is introduced

After activation, CHC and CHCQ can coexist.

Future public mainnet can support CHCQ from genesis because mainnet is not live.

## Backend Policy

Nodes must use one pinned consensus-critical PQ verification backend. Nodes must
not choose between multiple verification backends.

`liboqs-python` is acceptable only for prototype/devnet work if pinned. No
auto-download or runtime build behavior is acceptable for mainnet consensus.

Browser wallets may later use a different library, but browser-produced
signatures must verify against the node consensus backend.

The current implementation exposes the architecture and size/format checks.
The runtime environment uses a vendored `mldsa-native` ML-DSA-44 backend pinned
at commit `9b0ee84f4cf399043eca59eca4e5f8531ca1d61b`. It is compiled into the
official package/image and does not use `liboqs`, process-global RNG overrides,
or runtime backend selection.

The vendored backend is still not sufficient for activation by itself. Official
FIPS 204/backend KAT coverage, frozen v2 transaction/signature vectors,
cross-platform CI, and review are required before any activation height is used.

Wallet warnings must also mention that deterministic ML-DSA signing is not a
replacement for protecting signing devices and backups from malware,
side-channel exposure, or physical fault-injection attacks.

## Required Frozen Vectors

Before activation, freeze vectors containing:

- private seed
- public key
- CHCQ address
- unsigned tx bytes
- v2 sighash digest
- signature
- signed tx bytes
- txid

Browser PQ signing must not start until these vectors are frozen and CLI CHCQ
spends verify on the node backend.
