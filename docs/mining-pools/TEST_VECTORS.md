# Reproducible vectors

The versioned [JSON fixture](test-vectors/v1.json) was generated from integrated RC `4c0984e65de31a50db7558d468167d513769bb20`. It remains unchanged for this handbook revision and is checked against **tagged release** `12e4dbc8974bd76885e30e6dacdf1b7be898e126`. Every field is re-derived and compared by [verify.py](test-vectors/verify.py), which exits nonzero on any mismatch:

```sh
PYTHONPATH=/absolute/path/to/chipcoin-v0.1.2/src python3 docs/mining-pools/test-vectors/verify.py
```

Run the command from the handbook checkout and replace the `PYTHONPATH` placeholder with the clean tagged Core checkout. The verifier uses only public data and a public compressed secp256k1 generator point. It reads no production database, wallet or signing seed. A mismatch is a release compatibility finding: investigate before proposing a separately reviewed fixture update. **Do not invoke `--write` as part of verification.**

Fixture SHA-256: `121f67afb716678790408906dbe12979449a26081e2907c9d475177dbd2e5a64`. The JSON's top-level `core_commit` records the **generation commit**, while the command above records the release version being checked. Hex strings represent bytes in their serialized/display order unless a field explicitly says `target`; amounts are integer chipbits. The verifier checks every top-level section, including negative cases; it does not transform expected values on mismatch.

| Fixture section | Network / provenance | Inputs and expected outputs |
| --- | --- | --- |
| `mainnet_genesis` | Real embedded Mainnet block at height 0; [`canonical_genesis_block`](../../src/chipcoin/consensus/genesis.py) | Header fields/80-byte hex, full canonical block hex, genesis coinbase bytes/TXID, Merkle root, compact target, big-endian SHA-256d digest and block hash. It has no payout output. |
| `isolated_devnet_example` | Synthetic Devnet height-0 candidate using unchanged `DEVNET_PARAMS`; [`build_coinbase_transaction`](../../src/chipcoin/node/mining.py), [`serialize_block`](../../src/chipcoin/consensus/serialization.py) | Public miner address, coinbase outputs/metadata/bytes/TXID, metadata and locktime extra-nonce mutations, Merkle roots, solved header/nonce/target, complete block hex/hash, invalid-Merkle and invalid-PoW blocks with rejection text, legacy/full request envelopes. No live Devnet tip is assumed. |
| `reward_layout_encoding_only` | Synthetic Mainnet height-1,099 serialization example; no settlement context is supplied | One miner output and one ordered reward output, exact chipbit amounts and coinbase bytes. This is **not** a valid Mainnet block by itself. |
| `merkle_three_leaves` and `compact_targets` | Synthetic leaves; actual network compact target constants | Ordered leaf TXIDs, Merkle root with odd-leaf duplication, bits/expanded target/normalized bits for Mainnet, Testnet and Devnet. |
| `chcq_address` | Public test address already asserted in [`test_wallet_signer.py`](../../tests/wallet/test_wallet_signer.py); [`parse_address`](../../src/chipcoin/crypto/addresses.py) | CHCQ text, scheme ID, version, payload, commitment, checksum-corrupted negative example, and checksum-valid unsupported scheme ID example. No wallet seed or private key in the fixture. |
| `profiles` | Consensus parameter constants and PQ activation schedule | Mainnet, Testnet and Devnet activation and maturity values. |

The verifier deserializes the synthetic full block, checks PoW, validates it statelessly, and **accepts it contextually through `NodeService.accept_full_block` on a fresh temporary Devnet database**. It also checks idempotent duplicate submission, a Merkle mutation, a corrupted CHCQ checksum, and Mainnet genesis PoW. The sample Devnet block is **not** proof that a live node with a different tip or timestamp will accept those bytes. The isolated [smoke client](examples/smoke_devnet.py) exercises actual HTTP assembly/submission; for fork and retry tests use [`tests/integration/pool/test_block_submission.py`](../../tests/integration/pool/test_block_submission.py). The JSON's `legacy_submit` and `full_submit` objects are request envelopes, **not** proof that those exact bytes are valid for an arbitrary live tip.

## Crypto Connection Stratum vector (synthetic private Devnet)

Julien supplied the [original JSON bytes](test-vectors/chc_stratum_vector.json) from a private two-node Devnet using Core v0.1.2 (`12e4dbc8974bd76885e30e6dacdf1b7be898e126`), Miningcore Chipcoin module v6.1 and CryptoConnectionMiner 0.10.1. The file is **32,528 bytes**, MD5 `1784e3cc51bb48c256e8cac6badd60f4`, SHA-256 `924fc787d55f820552973a05586a0123fedd9cf87914ca068623b70409d727a6`. It is not a public Mainnet block. Its two non-coinbase transactions use legacy Devnet encoding; they are **not** examples of Mainnet ML-DSA-44-signed transactions.

From this handbook checkout, using a clean checkout of the tagged Core:

```sh
PYTHONPATH=/absolute/path/to/chipcoin-v0.1.2/src python3 docs/mining-pools/test-vectors/verify_stratum.py
```

The [verifier](test-vectors/verify_stratum.py) checks the original file checksum and JSON, `mining.notify`/`mining.submit` consistency, `coinb1 || extranonce1 || extranonce2 || coinb2`, coinbase locktime/TXID, ordered transaction bytes and TXIDs, Merkle branches/root, the exact 80-byte header, SHA-256d hash and PoW target, and the 717-byte canonical block. Canonical parsers must consume every byte; reserialization must match. It does **not** change expected bytes in the JSON or claim that the sample would be accepted by an unrelated live tip. The included 68/41/27 summary is checked for internal consistency only; node acceptance and stale outcomes remain Julien's historical report without the original Devnet logs. See [evidence notes](STRATUM_VECTOR_REQUEST.md).

Header encoding is `version:uint32 LE | previous_hash:32 raw bytes in displayed hex order | merkle_root:32 raw bytes in displayed hex order | timestamp:uint32 LE | bits:uint32 LE | nonce:uint32 LE`. Hash the 80 bytes twice with SHA-256; treat the raw digest as a **big-endian** integer. Compact `bits` expands with [`bits_to_target`](../../src/chipcoin/consensus/pow.py); compare digest integer `<= target`. No display-byte reversal is performed by this Core.

Transaction encoding is documented by [`serialize_transaction`](../../src/chipcoin/consensus/serialization.py): version `uint32 LE`, compact input count, each outpoint hash/raw index/signature scheme for v2/signature/public key/sequence, compact output count, each value `uint64 LE` and length-prefixed UTF-8 recipient, locktime `uint32 LE`, then sorted length-prefixed UTF-8 metadata pairs. The block is header + compact count + those transaction bytes. Merkle leaves are raw displayed TXID bytes, and odd levels duplicate the final leaf. See [coinbase](COINBASE_AND_PAYOUTS.md) for why the genesis coinbase is exceptional.
