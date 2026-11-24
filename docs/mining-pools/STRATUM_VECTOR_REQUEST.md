# Stratum interoperability vector: required evidence

**Status: PENDING_OPERATOR_BYTES.** No production `mining.notify`/`mining.submit` transcript or exact pool-generated block was supplied with the operator report. The existing [Core fixture](test-vectors/v1.json) verifies native serialization and a synthetic Devnet locktime mutation; it is **not** a production Stratum wire vector. Do not substitute made-up job IDs, shares, keys or hashes.

A future, scrubbed vector should include these fields, each as literal bytes or JSON and with network profile, Core revision, pool/miner version, source timestamp, and whether it is a synthetic isolated test or a production trace:

| Stage | Required values | Core-side verification |
| --- | --- | --- |
| Subscription | `extranonce1` hex (2 bytes), `extranonce2_size` (2) | Length and worker assignment are pool policy. |
| Job | Complete `mining.notify` params: job ID, previous hash, `coinb1`, `coinb2`, Merkle branches, version, bits, ntime, `clean_jobs` | Decode against one `get-block-template` response; preserve exact template outputs and ordered TXIDs. |
| Share | Complete `mining.submit` params: worker, job ID, extranonce2, ntime, nonce | Reconstruct the exact submitted candidate; distinguish pool share target from network target. |
| Coinbase | `coinb1 || extranonce1 || extranonce2 || coinb2` full hex, decoded locktime, sorted metadata, TXID | `deserialize_transaction` must consume all bytes; `serialize_transaction` must reproduce them exactly. |
| Commitments | Merkle root, 80-byte header hex, SHA-256d block hash and target | Compare with `merkle_root`, `serialize_block_header`, `hash_to_int` and `bits_to_target`. |
| Block | Canonical full block hex, Core submission request/result and hash lookup | `deserialize_block` consumes all bytes; block hash matches header and `on_active_chain` is checked separately. |

For a publishable **accepted** vector, use a disposable Devnet or another controlled fixture and disclose its tip/height. A regular accepted *share* may fail the network target and cannot be described as an accepted block. Remove worker addresses or credentials if they are not public test material. Validate every expected output against tagged Core v0.1.2 without regenerating mismatched expectations automatically. Contributions from another pool can follow the same checklist without adopting this backend's Stratum layout.
