# Mining pool troubleshooting

Applies to tagged release `12e4dbc8974bd76885e30e6dacdf1b7be898e126`. Log the request time, candidate height/tip, local block hash, HTTP status, `reason`, and later lookup result. Never log private keys or worker credentials. The exact response contract is in [block submission](BLOCK_SUBMISSION.md).

| Symptom | Likely meaning | Pool action |
| --- | --- | --- |
| `unknown_or_expired_template` | Legacy job ID absent after 15-second TTL, 256-job eviction, restart, or tip invalidation. | Query the submitted hash; if absent, retry the identical complete block in full mode or refresh the job. Do not assume the block was invalid. |
| `already_accepted` | Full-mode duplicate is on active chain. | Record the hash; confirm via `GET /v1/block?hash=` and watch reorgs. This result is **not** promised for legacy retry with an expired ID. |
| `coinbase_outputs_mismatch` | Legacy submission's ordered output list differs from its issued template. | Rebuild from that template or use full mode for an autonomous candidate; verify actual reward outputs. It is checked before transaction IDs, so a changed transaction set can also affect the reported first mismatch. |
| `transaction_set_mismatch` | Legacy non-coinbase TXIDs differ from issued job. | Never attach an older solution to a new, different job ID. Submit the original complete block in full mode if still consensus-valid. |
| CHCQ rejected on Devnet/Testnet | Candidate height precedes PQ output activation (Devnet 30,000; Testnet 20,000). | Use a valid legacy payout address only for isolated pre-activation tests, or test after natural activation; never alter activation rules. Mainnet CHCQ is active from height 0. |
| `invalid_request` for Mainnet CHCQ scheme | The address may have a correct checksum but a scheme ID other than ML-DSA-44 `0x0a`; the release rejects it before issuing work. | Parse and verify the address/scheme before requesting a template. Do not lower the consensus requirement. |
| `stale_template` | Legacy cached job's parent differs from current active tip, or submitted header parent differs. | Fetch current status/tip, reconcile hash, then issue a fresh job. A full block on a fork still needs fork-choice validation. |
| New mempool transaction | New job may contain another transaction set; old job remains cached until normal expiry/eviction/tip change. | Keep work boundaries distinct. Full old block may still be valid at unchanged tip. |
| HTTP timeout, reset, or `500 internal_error` | Response may have failed after storage/commit, or before it. | Lookup exact block hash; require `on_active_chain:true`. Retry identical full bytes if absent. Investigate repeated 500s with node logs. |
| Hash exists but `on_active_chain:false` | Stored side branch is not the active chain. | Do not credit as confirmed; monitor fork choice and reorgs. `consensus_validity=pending` does not promise eventual acceptance. |
| Node reports wrong chain ID/genesis or `sync_phase` not synced | Pool may be talking to wrong/lagging network or a local isolated chain. | Stop distributing Mainnet work; compare `GET /v1/status` with trusted network sources. |
| Coinbase output cannot be spent | It may be immature or removed by reorg. Mainnet requires 100-block height difference. | Recheck active-chain inclusion, output UTXO and maturity before payout transactions; do not lower the maturity rule. |

Use `GET /mining/status` for current tip/bits and template TTL. `GET /v1/status` can be short-lived cached depending on server configuration; a pool should use mining status and the block hash to resolve racing submissions. Validation rejections are often HTTP 200 with `accepted:false`; parse the JSON body. For structural HTTP 400 `invalid_request` or HTTP 413 `payload_too_large`, check JSON/hex lengths and required fields against [the API contract](BLOCK_SUBMISSION.md).
