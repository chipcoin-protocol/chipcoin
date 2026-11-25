# Stratum interoperability vector: evidence and limits

**Status: ACQUIRED; EXAMPLE BYTES VERIFIED AGAINST CORE.** Julien's original [JSON vector](test-vectors/chc_stratum_vector.json) is a synthetic trace from a private two-node Devnet using Core v0.1.2 (`12e4dbc`), Miningcore Chipcoin module v6.1 and one CPU miner. It includes a height-18 example with two legacy non-coinbase Devnet transactions and a 717-byte full block. The file's 32,528 bytes and checksums are recorded in [Test Vectors](TEST_VECTORS.md). The separate [Core fixture](test-vectors/v1.json) remains unchanged.

The supplied example includes the following evidence. The table is also a checklist for other pool implementations:

| Stage | Required values | Core-side verification |
| --- | --- | --- |
| Subscription | `extranonce1` hex (2 bytes), `extranonce2_size` (2) | Length and worker assignment are pool policy. |
| Job | Complete `mining.notify` params: job ID, previous hash, `coinb1`, `coinb2`, Merkle branches, version, bits, ntime, `clean_jobs` | Decode against one `get-block-template` response; preserve exact template outputs and ordered TXIDs. |
| Share | Complete `mining.submit` params: worker, job ID, extranonce2, ntime, nonce | Reconstruct the exact submitted candidate; distinguish pool share target from network target. |
| Coinbase | `coinb1 || extranonce1 || extranonce2 || coinb2` full hex, decoded locktime, sorted metadata, TXID | `deserialize_transaction` must consume all bytes; `serialize_transaction` must reproduce them exactly. |
| Commitments | Merkle root, 80-byte header hex, SHA-256d block hash and target | Compare with `merkle_root`, `serialize_block_header`, `hash_to_int` and `bits_to_target`. |
| Block | Canonical full block hex, Core submission request/result and hash lookup | `deserialize_block` consumes all bytes; block hash matches header and `on_active_chain` is checked separately. |

The [verifier](test-vectors/verify_stratum.py) checks canonical decoding, exact lengths, coinbase/TXID, Merkle root, header/hash/target, transaction ordering and full-block roundtrip against tagged Core v0.1.2. The JSON records a node submission response and two loopback active-chain observations, but those historical HTTP observations cannot be independently replayed without the original Devnet state and logs. Its summary lists 68 reconstructions, 41 accepted blocks and 27 stale second solutions; only the counts' internal consistency is locally checkable. A regular accepted *share* may fail the network target and cannot be described as an accepted block. No private-key or seed field appears in the JSON structure. Other pools can use this checklist without adopting Crypto Connection's Stratum layout.
