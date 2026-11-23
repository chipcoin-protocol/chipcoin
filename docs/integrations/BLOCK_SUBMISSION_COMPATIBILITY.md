# Submission compatibility matrix

This describes a local development candidate. Existing deployed nodes still use the **before** column.

| Behavior | Before | Candidate |
| --- | --- | --- |
| URL | `POST /mining/submit-block` | Same URL |
| Legacy fields | `template_id`, `miner_id`, `serialized_block` required | Same fields and semantics |
| Full block without ID | HTTP 400 `invalid_request` | Allowed with complete canonical `serialized_block` |
| Job TTL | 15 seconds | 15 seconds, unchanged |
| Mempool arrival | Clears every template | Retains still-live templates |
| Active tip/reorg | Clears templates | Still clears templates |
| Restart | Loses in-memory jobs | Still loses in-memory jobs |
| Job limit | Unbounded until expiry | 256 records, oldest evicted |
| Expired legacy ID | JSON `accepted=false`, `unknown_or_expired_template` | Same |
| Wrong `miner_id` | `miner_id_mismatch` | Same |
| Legacy invalid block | `validation_error:<detail>` | Same |
| Full active-chain block | Unsupported | `accepted=true`, `stored=true`, `on_active_chain=true`, `consensus_validity=validated` |
| Full side branch | Unsupported | `accepted=false`, `stored=true`, `on_active_chain=false`, `consensus_validity=pending` |
| Full duplicate | Unsupported | `already_accepted` or `known_side_branch` according to active-chain inclusion |
| Relay failure after commit | Can become HTTP 500 | Committed full block returned with `relay_failed=true`; legacy path reconciles after caught relay failure |

Legacy clients should continue to send their existing JSON unchanged. Full mode is opt-in by omitting `template_id`; it is not an alias for using a new ID to reconstruct an old block. In particular, a changed transaction list cannot be silently replaced by a new template. The observed Crypto Connection workaround remains possible when all consensus-relevant bytes match, subject to normal legacy checks. It cannot be claimed to solve changed jobs.

The default HTTP response status for validation results remains 200 with a structured body. Invalid request syntax is HTTP 400. Unhandled server failures remain HTTP 500. The full `reason` vocabulary is documented in [BLOCK_SUBMISSION_SPEC.md](BLOCK_SUBMISSION_SPEC.md). Request latency and exact client compatibility require pre-release testing with Crypto Connection.
