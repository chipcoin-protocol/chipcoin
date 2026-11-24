# Stratum interoperability vector: required evidence

**Status: FILE_REPORTED_NOT_ACQUIRED.** Julien reports supplying `chc_stratum_vector.json`, a synthetic trace from a private two-node Devnet using Core v0.1.2 (`12e4dbc`), Miningcore Chipcoin module v6.1 and one CPU miner. He describes an accepted height-18 block with two non-coinbase transactions and a 717-byte full block. The JSON file is **not present in this checkout**; no listed byte, hash, acceptance result or claimed count has been independently verified. The existing [Core fixture](test-vectors/v1.json) verifies native serialization and a synthetic Devnet locktime mutation; it is **not** that Stratum wire vector. Do not substitute made-up job IDs, shares, keys or hashes.

A future, scrubbed vector should include these fields, each as literal bytes or JSON and with network profile, Core revision, pool/miner version, source timestamp, and whether it is a synthetic isolated test or a production trace:

| Stage | Required values | Core-side verification |
| --- | --- | --- |
| Subscription | `extranonce1` hex (2 bytes), `extranonce2_size` (2) | Length and worker assignment are pool policy. |
| Job | Complete `mining.notify` params: job ID, previous hash, `coinb1`, `coinb2`, Merkle branches, version, bits, ntime, `clean_jobs` | Decode against one `get-block-template` response; preserve exact template outputs and ordered TXIDs. |
| Share | Complete `mining.submit` params: worker, job ID, extranonce2, ntime, nonce | Reconstruct the exact submitted candidate; distinguish pool share target from network target. |
| Coinbase | `coinb1 || extranonce1 || extranonce2 || coinb2` full hex, decoded locktime, sorted metadata, TXID | `deserialize_transaction` must consume all bytes; `serialize_transaction` must reproduce them exactly. |
| Commitments | Merkle root, 80-byte header hex, SHA-256d block hash and target | Compare with `merkle_root`, `serialize_block_header`, `hash_to_int` and `bits_to_target`. |
| Block | Canonical full block hex, Core submission request/result and hash lookup | `deserialize_block` consumes all bytes; block hash matches header and `on_active_chain` is checked separately. |

The reported file should contain `mining.subscribe`, `mining.authorize`, `mining.set_difficulty`, `mining.notify`, `mining.submit`, the Core template response, coinbase hex/TXID, Merkle root, 80-byte header, block hash, 717-byte full block hex and submit request/result. Acquire the actual JSON before adding a fixture. Then check canonical decoding, exact lengths, coinbase/TXID, Merkle root, header/hash/target, transaction ordering, template correspondence and response/active-chain evidence against tagged Core v0.1.2. A regular accepted *share* may fail the network target and cannot be described as an accepted block. Remove worker addresses or credentials if they are not public test material. Compare expected outputs without silently regenerating them. Contributions from another pool can follow the same checklist without adopting this backend's Stratum layout.
