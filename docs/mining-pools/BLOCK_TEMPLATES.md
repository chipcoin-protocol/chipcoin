# Mining templates

Reference: [`HttpApiApp._handle_get_block_template`](../../src/chipcoin/interfaces/http_api.py), [`NodeService.get_block_template`](../../src/chipcoin/node/service.py), [`MiningCoordinator.build_block_template`](../../src/chipcoin/node/mining.py) at tagged Core `12e4dbc8974bd76885e30e6dacdf1b7be898e126`. The CHCQ scheme precheck was added after the original integrated RC; see [PQ addresses](PQ_ADDRESSES.md).

`POST /mining/get-block-template` accepts JSON `payout_address` and `miner_id` as required nonempty strings. `payout_address` must pass address parsing; CHCQ must be active at the candidate height, and a Mainnet CHCQ payout must use ML-DSA-44 scheme ID `0x0a`. Optional `template_mode` is `full_block` (default) or `header_and_coinbase_data`; the implementation returns the same fields for both. Bad input returns HTTP 400 `error.code=invalid_request`; an oversized request body returns HTTP 413 `payload_too_large`. The JSON body limit is 16,384 bytes.

The response contains:

| Group | Fields and interpretation |
| --- | --- |
| Identity | `network`, `network_magic_hex`, `chain_id`, `genesis_hash`, `node_id` |
| Job | `template_id` (random opaque ID), `template_mode`, `height`, `previous_block_hash`, `template_expiry` (Unix time in seconds) |
| Header inputs | `version`, `bits` (integer compact target), `target` (64 hex digits), `curtime`, `mintime` |
| Coinbase | `coinbase_tx.version`, `.outputs`, `.metadata`, `payout_address`, `coinbase_value_chipbits`, `miner_reward_chipbits`, `node_reward_total_chipbits`, `node_reward_outputs` |
| Other transactions | `transactions[]` of ordered `txid`, `raw_hex`, `weight_units` |
| Limits | `block_weight_limit`, `consensus.coinbase_maturity`, `.max_block_weight`, `.rule_set` |

Amounts use **chipbits** (100,000,000 per CHC). The `coinbase_tx` object is a recipe, not canonical transaction bytes. A pool must serialize it and preserve required outputs. The template builder selects a snapshot of eligible mempool transactions and any system settlement transaction, then computes the candidate Merkle root; it does not return a completed header or a pool share target. See [coinbase](COINBASE_AND_PAYOUTS.md) and [vectors](TEST_VECTORS.md).

Issued legacy jobs live **15 seconds** in memory, at most **256 records** in this release; these are fixed `NodeService` values, not pool-configurable settings. Issuing a 257th evicts the oldest. A new mempool transaction may produce a new job but does not erase an older unexpired job. Active tip changes, reorgs, and process restarts remove job IDs. The legacy submission still checks its issuer ID, prev hash, bits, required outputs and ordered transaction IDs. Full serialized block submission is independent of this cache and goes through normal consensus validation. Template expiry is an administrative limit on reconstructing a legacy job, not the consensus lifetime of a complete block. See [submission](BLOCK_SUBMISSION.md).

[Crypto Connection](https://crypto-connection.net) reports polling `GET /v1/tip` every 500 ms, requesting a new template after a tip change and every 10 seconds on an unchanged tip, and retaining its newest four worker jobs. Same-tip refresh jobs are sent with `clean_jobs=false`. Jobs may outlive the Core's 15-second **legacy** template ID. These are pool scheduling choices, not Core settings. New jobs do not refresh old IDs. The reported Miningcore v6.1 full-block fallback can submit an unchanged complete candidate on a matching tip without its expired ID; see [submission](BLOCK_SUBMISSION.md). A tip change clears old Core IDs, so `unknown_or_expired_template` does not by itself distinguish TTL expiry from tip invalidation.

`target` is the **network** target, not a pool share target. [`bits_to_target`](../../src/chipcoin/consensus/pow.py) expands `bits`; [`hash_to_int`](../../src/chipcoin/consensus/hashes.py) reads the raw header digest big-endian. Header fields are serialized in [`serialize_block_header`](../../src/chipcoin/consensus/serialization.py). Candidate timestamp, tip, bits and reward outputs can change between jobs; never splice bytes from two templates.

The API does not provide a native Stratum job ID/extranonce protocol, share submission endpoint, or pool difficulty negotiation. Those belong to a pool backend. The `header_and_coinbase_data` selector is **not** a promise of a separate binary wire format.
