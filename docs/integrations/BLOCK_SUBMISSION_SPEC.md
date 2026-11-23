# Block submission API (candidate, not released)

`POST /mining/submit-block` accepts a JSON object with `serialized_block`, a lower- or upper-case hex encoding of the complete canonical Chipcoin block (`consensus.serialization.serialize_block`). The HTTP body limit is 17,000,000 bytes; the hex field limit is 16,000,000 characters. The block consists of the canonical 80-byte header, a compact transaction count, then all serialized transactions. `deserialize_block` must consume the entire payload. No incomplete header/nonce-only mode is introduced.

Legacy request, unchanged:

```json
{"template_id":"<issued ID>","miner_id":"<same miner ID>","serialized_block":"<full block hex>"}
```

Full-block request, new opt-in by omission of `template_id`:

```json
{"serialized_block":"<full block hex>"}
```

Legacy responses retain `accepted`, `reason`, `block_hash`, `became_tip`. Legacy `unknown_or_expired_template` remains possible after 15 seconds, oldest-job eviction, restart, or active-chain change. A mempool update alone no longer deletes a job. A full block does not depend on any template cache. Submission is still subject to PoW, bits, timestamp, Merkle root, transaction v2 signatures, CHCQ output policy, reward-node settlement, and all other current consensus checks.

Full-block response fields:

| Field | Meaning |
| --- | --- |
| `accepted` | `true` only if the block is on the active chain at response time. |
| `stored` | Full payload is known in block storage. Storage alone is not validation. |
| `on_active_chain` | Exact block hash is at its recorded height on the active chain. |
| `consensus_validity` | `validated` for active-chain blocks; `pending` for stored side branches; `invalid` for a detected invalid block; `not_validated` when its parent is unknown. |
| `became_tip` | Exact block hash is the current active tip. |
| `reason` | `accepted`, `already_accepted`, `stored_side_branch`, `known_side_branch`, `unknown_parent`, `validation_error:<detail>`, or `decode_error:<detail>`. |

Successful full-block storage returns HTTP 200 with structured JSON. Malformed JSON, oversized body, or missing/invalid hex are HTTP 400 with `error.code=invalid_request`. The existing API wrapper may return HTTP 500 for unhandled server failures. If a connection closes or HTTP 500 occurs, query `GET /v1/block?hash=<block hash>` and retry the identical full block. A retry of an active block returns `already_accepted`, without a second write or relay. A side-branch lookup must not be treated as active-chain confirmation.

`GET /v1/block?hash=<block hash>` and `GET /v1/block?height=<height>` also return `on_active_chain`: `true` only when that exact stored block occupies its recorded height on the active chain. The hash lookup may return a stored side-branch block with `on_active_chain=false`; a block's presence by hash alone is not confirmation. This field is additive and does not change existing block fields.

`POST /mining/get-block-template` rejects a CHCQ payout address with HTTP 400 `invalid_request` before the network's PQ activation height. Mainnet activates at height 0, Testnet at 20,000, and Devnet at 30,000 according to the current consensus parameters. The check uses the candidate block height. It does not change activation rules or mining-template expiry.

The endpoint is intended for locally bound, trusted pool-to-node access. Do not publish it through an unauthenticated Internet proxy. The Core's local API has no built-in pool identity authentication or per-client rate limiter. Deployment operators must restrict access and monitor requests. This candidate is not a promise of universal status codes across old releases.
