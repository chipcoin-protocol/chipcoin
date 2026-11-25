# Handbook changelog

## v1.3 — 2026-11-25

- Attribute pool-specific implementation details and operator-reported test results to [Crypto Connection](https://crypto-connection.net), with Julien's permission. The Core's protocol and consensus claims remain sourced from tagged Mainnet v0.1.2 (`12e4dbc8974bd76885e30e6dacdf1b7be898e126`).
- Correct the prior statement about worker authorization: Julien reports Miningcore Chipcoin module v6.1 enforces CHCQ version `0x50` and ML-DSA-44 scheme `0x0a` in production since 2026-11-24 21:22 UTC. This is a pool login rule, separate from Core validation.
- Document Crypto Connection's reported full-block fallback in production since 2026-11-24 23:16 UTC: after a legacy missing-template result, compare candidate parent with `GET /v1/tip`, submit the unchanged full block without `template_id` only on a match, then compare its hash with the active block at its height. The tip check is race-sensitive and does not guarantee acceptance. The reported 12 restarts, 3 recovered blocks, 5 skipped stale solutions and zero side branches were not independently reproduced.
- Separate Core's fixed 15-second legacy template TTL and full-block mode from Crypto Connection's 500 ms tip poll, 10-second job refresh and four-job retention. Julien confirms Miningcore v6.1 sends `clean_jobs=true` on a new tip, dropping old jobs; unchanged-tip refreshes send `clean_jobs=false`.
- Clarify Crypto Connection's 2-byte connection extranonce plus 2-byte miner extranonce in the coinbase `uint32` little-endian locktime; confirm the Core byte order in the tagged serializer and decoder. Correct the hashrate description to use the sum of accepted share difficulties over an unspecified observation window.
- Preserve Julien's original 32,528-byte private-Devnet `chc_stratum_vector.json` and verify its example coinbase, TXID, Merkle root, header, PoW and full block against tagged Core v0.1.2. The earlier Core fixture `v1.json` remains unchanged. The vector summary's 68/41/27 counts are internally consistent, but the historical acceptance/stale outcomes remain operator evidence.

This release of the handbook changes documentation only. It does not modify the immutable Core v0.1.2 tag, APIs, consensus or the existing vector fixture.
