# Block submission and confirmation

This page gives the operator workflow for tagged Core `12e4dbc8974bd76885e30e6dacdf1b7be898e126`; [BLOCK_SUBMISSION_SPEC.md](../integrations/BLOCK_SUBMISSION_SPEC.md) records the original RC contract. Source: [`HttpApiApp._handle_submit_block`](../../src/chipcoin/interfaces/http_api.py), [`NodeService.prepare_mined_block_submission`](../../src/chipcoin/node/service.py), `prepare_full_block_submission`, `accept_full_block`, and [`NodeRuntime`](../../src/chipcoin/node/runtime.py). The submission logic is unchanged between integrated RC `4c0984e` and the tag.

Both modes use `POST /mining/submit-block` with `Content-Type: application/json` and the **entire** canonical block as hex in `serialized_block`. A block is an 80-byte header, compact transaction count, then ordered canonical transactions. The decoder must consume every byte. `header+nonce` alone is not accepted.

```json
{"template_id":"<issued ID>","miner_id":"<same miner ID>","serialized_block":"<complete block hex>"}
```

This is legacy mode. The job must still exist and match the miner ID, active parent, bits, required coinbase outputs and ordered non-coinbase transaction IDs. Extra-nonce changes in coinbase metadata are allowed when other checks and consensus pass. A template ID cannot safely be replaced with a new ID if its consensus-relevant bytes differ.

```json
{"serialized_block":"<complete block hex>"}
```

This opts into full-block mode. No template cache is required. Its result has `accepted`, `stored`, `on_active_chain`, `consensus_validity`, `became_tip`, `reason`, and `block_hash`. `accepted=true` means active-chain inclusion at response time; `stored=true` alone is insufficient. `consensus_validity=pending` means a stored side branch has not yet passed all contextual validation for activation. Existing fork-choice logic determines whether a side branch can become active later. Do not credit a payout simply because a block is stored.

| `reason` | Meaning for full mode |
| --- | --- |
| `accepted` | New block validated and placed on active chain. |
| `already_accepted` | Exact block is already on the active chain. |
| `stored_side_branch` | New side-branch block stored, contextual validation pending. |
| `known_side_branch` | Exact block was already stored off the active chain. |
| `unknown_parent` | The preceding block is unknown. |
| `not_stored` | Ingest did not establish storage; investigate and retry only after reconciliation. |
| `validation_error:<detail>` | Validation rejected the candidate. |
| `decode_error:<detail>` | Canonical block decoding failed. |

Legacy responses retain `accepted`, `reason`, `block_hash`, `became_tip`. Legacy rejection reasons in the release code include `unknown_or_expired_template`, `miner_id_mismatch`, `stale_template`, `bits_mismatch`, `missing_coinbase`, `coinbase_outputs_mismatch`, `transaction_set_mismatch`, `decode_error:<detail>`, and `validation_error:<detail>`. `unknown_or_expired_template` can follow TTL expiry, oldest-job eviction, restart or tip invalidation. This release **does not** turn a legacy retry with a missing ID into `already_accepted`; use full mode or hash lookup to reconcile.

Malformed JSON and missing fields return HTTP 400 with `error.code=invalid_request`; an oversized body or hex field returns HTTP 413 with `error.code=payload_too_large`. The JSON body limit is **17,000,000 bytes** and the hex field limit **16,000,000 characters**. Consensus and job rejections normally return HTTP 200 with `accepted=false` and structured `reason`. Unexpected server errors can return HTTP 500 `error.code=internal_error`. HTTP 200 guarantees that the handler returned a JSON result, **not** consensus validity, durable storage, or active-chain inclusion; inspect the result fields and reconcile by hash.

On timeout, broken connection, or HTTP 500 after a possible commit:

1. Compute the submitted block hash from the **exact serialized header**.
2. Request `GET /v1/block?hash=<hash>`. A 404 means not found by that node at that instant; it does not establish global invalidity.
3. Require `on_active_chain:true` for confirmed inclusion. A stored side branch has `on_active_chain:false`.
4. If not active, retry the **same complete block** in full mode, or refresh the template if your client only supports legacy mode. Do not silently rebuild different transactions under the same solved nonce.
5. Watch later tip/reorg changes and coinbase maturity before spending payouts.

The API adds `on_active_chain` to block lookups by hash and height. A new block on the same tip is not invalidated merely because mempool changed. A changed tip can make an old block a fork candidate; its acceptance depends on the normal fork-choice and consensus rules. Multiple pools may submit the same hash; the full-mode duplicate response is idempotent, while a different hash on a side branch must remain separate.

**Deployment distinction:** one production pool reports using legacy submission today. On `unknown_or_expired_template` it requests a fresh template and retries with the new ID only after comparing previous hash, bits, coinbase outputs and ordered TXIDs; after any error it checks the exact block hash. Its full-block fallback and `on_active_chain` check were tested but were **not reported as deployed**. These details describe that operator, not a requirement or limitation of Core v0.1.2, which already supports the full mode above. Reusing a new ID must never silently rebuild different block bytes under an old solved nonce. See the [Stratum reference](STRATUM_REFERENCE.md).
