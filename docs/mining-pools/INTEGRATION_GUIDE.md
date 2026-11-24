# Pool integration, from node to confirmed block

**Scope:** tagged Mainnet v0.1.2 Core at `12e4dbc8974bd76885e30e6dacdf1b7be898e126`. The [handbook index](README.md) identifies the supported profile. The API implementation is [`http_api.py`](../../src/chipcoin/interfaces/http_api.py), [`service.py`](../../src/chipcoin/node/service.py), and [`runtime.py`](../../src/chipcoin/node/runtime.py). These links resolve to this handbook's source branch during review; check the tagged release when implementing.

## 1. Install and synchronize

For an isolated Devnet smoke test, follow [the Compose quick start](README.md#isolated-quick-start). It sets an explicit network, empty bootstrap settings, no outbound peer, no P2P publication, loopback-only HTTP, and an independent database. Height remains local until you mine or connect an explicitly selected Devnet peer. A zero height by itself does not prove public network synchronization.

For **Mainnet**, use the [tagged release](https://github.com/chipcoin-protocol/chipcoin/releases/tag/mainnet-v0.1.2). The public `./setup.sh` runs the Docker-first wizard, defaults to Mainnet and prepares persistent paths and configuration; it does not start services. Run its printed Compose commands separately, keep a dedicated database and wallet backup, and configure your own P2P/bootstrap policy. Check `GET /v1/status` for `chain_id=chipcoin-mainnet-1`, genesis `00000238ef41c47992581c18fad544b4e24ecf1e79e7ffed629a215def4a337f`, tip height/hash/work, and `sync_phase`. Confirm the tip with another independent source before directing significant hashrate to the node. The published image archive is AMD64; ARM64 needs a verified native build. Do not point the pool at a wallet-safe public API; template and submit endpoints require the private full-node interface.

## 2. Request work

The same endpoint is used by the native solo miner and external pools. On Mainnet, provide a payout address **you control**, normally CHCQ. On early Devnet, CHCQ payouts are rejected until candidate height 30,000; the isolated lab uses the fixture's public legacy address solely for protocol testing.

```http
POST /mining/get-block-template HTTP/1.1
Content-Type: application/json

{"payout_address":"<network-valid address>","miner_id":"pool-1","template_mode":"full_block"}
```

Read `network`, `chain_id`, `genesis_hash`, `height`, `previous_block_hash`, `version`, `bits`, `target`, `curtime`, `template_expiry`, `coinbase_tx.outputs`, `node_reward_outputs`, and `transactions[].raw_hex`. `template_mode` accepts `full_block` and `header_and_coinbase_data`; both currently return the same template field set. The response is *data for constructing a block*, not a serialized finished block. Compare the returned chain identity to your configured network before creating work. See [templates](BLOCK_TEMPLATES.md).

## 3. Translate to worker jobs

Serialize the coinbase according to [`serialize_transaction`](../../src/chipcoin/consensus/serialization.py), preserving every required output. A pool may vary coinbase metadata for worker extra-nonces; it must recompute coinbase TXID, Merkle root, the 80-byte header, and PoW. Append the exact returned non-coinbase transaction bytes in order. Compare the raw double-SHA256 header digest as a **big-endian** integer with the network target. Pool share difficulty is a separate, operator-chosen threshold. No Core endpoint speaks Stratum; see [Stratum boundary](STRATUM_REFERENCE.md).

## 4. Submit and reconcile

For the legacy contract, send the issued `template_id`, the **same** `miner_id`, and complete `serialized_block` hex. For full-block mode, omit `template_id` and send complete `serialized_block` hex. Both use `POST /mining/submit-block`. See [submission](BLOCK_SUBMISSION.md) for request shapes and result states.

If HTTP times out, closes after commit, or returns 500, do **not** declare the solved block lost. Compute the header hash from the exact bytes, query `GET /v1/block?hash=<hash>`, and check `on_active_chain`. If absent, retry the exact full block. `already_accepted` is a full-mode active-chain duplicate result; stored side branches have a separate state. A `200` HTTP response does not by itself mean consensus acceptance; inspect `accepted`, `stored`, `on_active_chain`, and `reason`.

Refresh work on new tips, reorgs, and pool policy changes. A mempool update may yield a different new job while an older valid block on the same tip remains valid under consensus. The legacy job cache lasts 15 seconds, is capped at 256 records, and disappears on restart or tip change. Full-block mode remains independent of that cache.

## 5. Operate safely

Use a private route or tunnel with access controls; the Core's local mining API has no built-in pool authentication or per-client rate limiter. Limit request concurrency and body size at the edge. Keep mining, payout, and reward-node wallets separate; keep their keys off the pool worker fleet. Back up the SQLite database consistently (SQLite backup API or stop the node), wallet seeds, and configuration. Record block hash, request time, response state, and subsequent active-chain checks without recording private keys or worker secrets. Restart from the same persistent volume; never use `docker compose down -v` for routine upgrades. Validate the candidate in an isolated environment and retain a rollback image before production rollout.

The [historical pre-release test plan](../integrations/POOL_PRERELEASE_TEST_PLAN.md) covers old jobs, mempool changes, duplicates, and side branches. Crypto Connection reported a successful isolated pre-release test of the integrated RC; this operator report is distinguished from executable local regressions in [release alignment](RELEASE_ALIGNMENT.md). Independent pool backends still need to verify their own Stratum translation and payout policy.
