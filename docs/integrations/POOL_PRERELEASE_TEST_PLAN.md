# Pool pre-release test plan

Status: AWAITING_EXTERNAL_TEST. No pool operator has been contacted automatically and no release candidate has been published.

Local candidate test record (2026-11-23): 79 tests passed in an isolated source copy across pool, HTTP API, and native miner suites. Four selected real-TCP runtime integration tests passed when local binds were available. These are developer tests, not external pool results. The complete T1–T12 and Mainnet PQ matrix remains open.

## Environment

Use a detached, isolated Devnet node and a throwaway pool database. Do not connect test mining or payment clients to Mainnet. Devnet activates CHCQ/v2 only at height 30,000, so early Devnet acceptance is **not** evidence for Mainnet PQ behavior. Use separate tests against unchanged Mainnet validation parameters and read-only Mainnet vectors for PQ claims. Record Git commit, image digest, configuration, chain ID, test time, request ID, block hash, and result; redact wallet secrets and worker identifiers.

## Test matrix

| Case | Expected evidence | Status |
| --- | --- | --- |
| Legacy solo submit | Existing `template_id` request accepted unchanged | Local test PASS |
| 256 legacy jobs on one tip | Oldest remains usable within TTL; job 257 evicts oldest | Local test PASS |
| Full submit after mempool change | Old complete block accepted on same tip | Local test PASS |
| Legacy job after mempool change | Still usable before TTL | Local test PASS |
| Full submit after job expiry | Valid block accepted without ID | Local test PASS |
| Four simultaneous Stratum jobs, 10-second refresh | No race or silent loss, bounded cache | NOT_RUN |
| New ID retry with byte-identical job | Same block hash and coinbase retained | NOT_RUN |
| Changed transaction set, old block | Full mode accepts if independently valid; legacy new ID rejects mismatch | NOT_RUN |
| Invalid PoW, Merkle, PQ and reward outputs | All rejected, no false acceptance | Partial local test; full matrix NOT_RUN |
| Stored side branch and reorg | Pending side branch later activates under fork choice | Local test PASS |
| Stored side branch relay | Inventory announced as in existing P2P path; contextual validity still pending | Local test PASS |
| Duplicate after active acceptance | `already_accepted`; no second write | Local test PASS |
| HTTP 500 after commit | Lookup and identical retry recover truth | Local simulation PASS; pool test NOT_RUN |
| External miner and pool end-to-end | Verify live client parsing and timing | AWAITING_EXTERNAL_TEST |

Before a Core release, coordinate a private pre-release test window with an affected pool operator. Keep correspondence and any operator-specific logs outside the public repository. Record a release decision after evaluating results. If external results remain unavailable, mark AWAITING_EXTERNAL_TEST and require an explicit exception; do not label the gate PASS.
