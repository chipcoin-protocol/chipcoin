# Stratum translation boundary

Tagged Chipcoin Core v0.1.2 offers HTTP mining methods, **not a Stratum server**. A pool backend must translate its worker protocol to the template, canonical block builder, and submission APIs. The [Crypto Connection Miner](https://github.com/gacanga/crypto-connection-miner) is an external GPL-3.0 project. Its public client source was reviewed locally at clean commit `6d40215d6e070c3022e8abc7380e5b969b98e7ad`, tagged `v0.10.2`; the historical Crypto Connection pool test used miner v0.10.1. These are distinct evidence points. The pool server source and worker traffic were not available. Do not copy external GPL code into Core without a separate license review.

| Pool responsibility | Core boundary |
| --- | --- |
| Worker connection, authorization, subscriptions, job IDs, reconnect policy | None; private pool service |
| Share difficulty and vardiff | Pool-chosen threshold; Core supplies network `bits` and `target` |
| Extra-nonce assignment | Pool partitions coinbase metadata/nonce search space and recalculates commitments |
| Share submission and duplicate detection | Pool validates share against its target; Core only accepts complete solved blocks |
| Block construction | Core returns payout, reward outputs, ordered transaction hex and header inputs; pool builds canonical bytes |
| Network block submission | `POST /mining/submit-block` legacy or full, followed by hash lookup |

The [public miner README's Chipcoin section](https://github.com/gacanga/crypto-connection-miner#chipcoin-chc) describes a **pool-specific Bitcoin Stratum V1-like dialect**:

| Method | Publicly documented worker-facing data |
| --- | --- |
| `mining.subscribe` | Subscription result with `extranonce1` of 2 bytes (4 hex digits) and extranonce2 size 2 bytes. |
| `mining.authorize` | The client sends its configured worker name and password. The public README describes a CHCQ payout address as the username; the client does not enforce that policy. The server's authorization rules are unverified. |
| `mining.notify` | `[job, previous hash in reversed 4-byte words, coinb1, coinb2, Merkle branches, version, bits, time, clean]`. |
| `mining.set_difficulty` | `[d]`. The client computes its share target from Bitcoin `diff1 / d`, with `diff1 = 0x00000000ffff0000...0000`. The public README rounds this to `2^224 / d`; the two values are not identical. This is **not** Core network difficulty. |
| `mining.submit` | `[worker, job, extranonce2, time, nonce]`. |

The [CPU client](https://github.com/gacanga/crypto-connection-miner/blob/6d40215d6e070c3022e8abc7380e5b969b98e7ad/cpu/ccm_cpu.cpp) and [GPU client](https://github.com/gacanga/crypto-connection-miner/blob/6d40215d6e070c3022e8abc7380e5b969b98e7ad/gpu/gostminer.cu) parse `mining.notify`, send `mining.subscribe`/`mining.authorize`/`mining.submit`, concatenate `coinb1 || extranonce1 || extranonce2 || coinb2`, compute double-SHA256 coinbase/branch hashes, and build an 80-byte header. Both compare the SHA-256d digest as a big-endian integer. With a 2-byte extranonce2, both allocate its upper four bits to a worker slot and lower twelve bits to a counter. The public README says the pool places these four extranonce bytes in the coinbase's `locktime`; the client itself only inserts them between the two supplied coinbase fragments and does not verify their transaction offset. The [fixture](test-vectors/v1.json) includes a locktime mutation to verify that changing it changes TXID and Merkle root. **These Stratum field conventions belong to this external miner/pool implementation; they are not standardized by Chipcoin Core.** Do not send Bitcoin coinbase/script or Bitcoin Merkle byte reversals to Chipcoin without adapting to [`serialize_transaction`](../../src/chipcoin/consensus/serialization.py), [`merkle_root`](../../src/chipcoin/consensus/merkle.py), and [`hash_to_int`](../../src/chipcoin/consensus/hashes.py).

At each new Core template: retain the exact ordered transaction bytes and required coinbase outputs, allocate distinct extra-nonces, serialize the modified coinbase, hash to TXID, calculate Merkle root, serialize the 80-byte header, and distribute the worker fields in your own protocol. On share return, reconstruct the **same** header and check share difficulty. If the header also meets network target, serialize the complete block and submit it. For late shares, distinguish a pool-stale job from an expired legacy template and from a block still valid at the same chain tip. Full-block submission avoids template-ID cache dependence but never bypasses consensus.

The [isolated pool regression](../../tests/integration/pool/test_block_submission.py) exercises block assembly and HTTP submit without asserting a Stratum wire contract. **NEEDS_JULIEN_CONFIRMATION:** server template-ID mapping, authorization policy, job retention, extra-nonce allocation/rotation, exact coinbase split, full-block reconstruction, share accounting and worker response codes. The reviewed client source does not establish these server internals. An independent pool must validate its own backend and worker traces.
