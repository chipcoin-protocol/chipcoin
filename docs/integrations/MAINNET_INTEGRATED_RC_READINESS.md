# Mainnet integrated release candidate — readiness (23 November 2026)

Status: **local candidate; NO-GO for production rollout** until the remaining gates below are closed. No push, merge to `main`, production restart, wallet modification, or database modification was performed.

## Source and provenance

| Item | Verified value |
| --- | --- |
| Production chipcom Core tag | `chipcoin-mainnet-core:171ed3e` |
| Production running image ID | `sha256:11993c554c9e78063268c2c338ed8b127b7409df47920b1bbca8f878c025053e` |
| Production source | `171ed3e74cf507376dfe1a8cf6fc7d83ffdf9140` |
| Reward + wizard | `a663789f43c850e443f755055a1c1c5f61de71ba` |
| Pool submission candidate | `a53f2b03dadc27681e236886c65f0db721c7dc9a` |
| Common merge base of the two branches | `163408845095171ccf94d11f626fe5dbac8688f8` |
| Integration merge | `821f04fb8e21c698bd7639f797c61aa7eee3e2a1` |
| Integrated code commit | `f2789e9171e3e6469dbcb071adf590553f601d49` |
| Local branch and checkout | `codex/mainnet-integrated-rc`, `/tmp/chipcoin-mainnet-integrated-rc` |

`171ed3e` is an ancestor of both source branches. Read-only checks on chipcom showed that the running image ID equals the ID of its `171ed3e` tag. The 92 installed Python source files had aggregate digest `f8e66161c293d00ae333dbed6fefe123c660d0f2df050d06d20df1233783ba50`, identical to the same 92 files at Git commit `171ed3e`. This establishes byte-for-byte Python source parity; it does not assert that every installed third-party package or runtime setting was independently audited.

The merge had one textual conflict: the import in `src/chipcoin/node/service.py`. It retains both `is_coinbase_mature` and `validate_block_stateless`. The reward fix, pool submission path, template lifecycle, and Docker-first wizard remain present. No commit was added to or altered in the source branches or the reconstructed pool checkout. Comparing production `171ed3e` with the integrated code showed no changed files under `src/chipcoin/consensus`, `src/chipcoin/storage`, `src/chipcoin/crypto`, or `src/chipcoin/wallet`. Changes in the Core are limited to `node/service.py`, `node/runtime.py`, and `interfaces/http_api.py`; consensus, genesis, serialization, schema and monetary rules are inherited unchanged.

## API and wallet observations A–G

| Item | Finding and network scope | Decision |
| --- | --- | --- |
| A. `/v1/block?hash` | The hash lookup returned a stored side branch but did not expose active-chain membership. Applies to all networks; no consensus impact. | **Implemented, additive API fix:** `on_active_chain` is true only when the exact hash occupies its recorded height. Tested across side branch and reorg. |
| B. CHCQ template before activation | `get-block-template` checked address syntax, while contextual validation rejected CHCQ outputs before activation. Mainnet activates at 0, Testnet at 20,000 and Devnet at 30,000 under current parameters. An early template could produce an invalid block. | **Implemented, release blocker closed:** reject the payout at candidate height with HTTP 400 before issuing a template. Testnet and Devnet boundary tests use isolated low-height parameter overrides, while the real activation constants are asserted separately. No activation heights changed. |
| C. Legacy retry after accept | The template cache is checked before decoding a legacy payload. Evicted/expired IDs therefore return `unknown_or_expired_template` even if the block was accepted. Full mode can already return `already_accepted`; hash lookup now reports active membership. | **Pending pool API agreement:** changing legacy reason semantics needs a transition decision. No silent change in this RC. Use full-block retry or hash lookup. |
| D. Tip change versus TTL | The legacy cache drops jobs on tip change; once removed, it cannot distinguish that event from TTL or oldest-job eviction. | **Pending pool API agreement:** proposed distinct reason requires storing eviction cause and specifying lifecycle/compatibility. No change in this RC. |
| E. Coinbase versus transaction mismatch | The legacy checker compares coinbase outputs before non-coinbase transaction IDs. Altered fees can therefore yield `coinbase_outputs_mismatch` before `transaction_set_mismatch`. Consensus validation remains separate. | **Pending pool API agreement:** reordering reasons would change observable behavior. No change in this RC. |
| F. `mempool_size` | `NodeService.status()` computes `len(mempool.list_transactions())` on a fresh call; HTTP caches the complete status for 1 second by default (`CHIPCOIN_HTTP_STATUS_CACHE_TTL_SECONDS`). Thus this field can lag by at most that configured TTL. Applies to all networks; no consensus impact. | **Deferred:** per-request refresh could add database work under load. Document the cache and measure before changing it. |
| G. `wallet-send` inputs | The reward fix already excludes immature coinbase outputs through the shared `list_spendable_outputs()` path. It did not exclude active-chain UTXOs already spent by a pending transaction. | **Implemented, wallet safety fix:** candidate listing now omits mempool-committed outpoints. A test builds two wallet payments and confirms the second uses a different input, while the immature output is excluded. Mempool/chain validation still handles races after selection. |

The integrated candidate `f2789e9` has **not** received a recorded external pool test. No new legacy response reason was introduced. Private operator correspondence and results are intentionally excluded from this repository.

## Executed checks

| Class | Result |
| --- | --- |
| Local Core/config/consensus/crypto/pool/miner/node/wallet pytest suite | **774 passed** on Tobia Linux x86_64. Four P2P tests and Chromium required local loopback permission; they passed when rerun with it. Browser interop: **2 passed** after installing locked npm dependencies. |
| New targeted pool/reward/activation checks after final source edits | **23 passed**; includes legacy/full template during renewal, side-branch lookup/reorg, Devnet and Testnet activation boundary, `wallet-send` maturity and pending spends. |
| Local Docker Core image | Built `chipcoin-mainnet-integrated-rc:f2789e9`, ID `sha256:faf9d7b027559f187689edbe0edfbab328e02ce0e056c455fe791ca52ef040a5`, revision label `f2789e9171e3e6469dbcb071adf590553f601d49`. All 92 Python files match the commit digest `6810c69c900e3da26b1dd2c8d254a6f3f143ea68554a6058751289431f6b730a`. |
| Local Docker setup image | Built `chipcoin-mainnet-integrated-setup:f2789e9`, ID `sha256:29b4d550953fdbc6693aecb101877531e0706c11cf47200e14a4b34bd88011f9`. Pinned native ML-DSA-44 known-answer check passed with `--network none`, read-only filesystem and no Docker socket. |
| Disposable Docker wallet | Setup image generated a new Mainnet CHCQ wallet in an external bind mount. Core image loaded that same wallet from a read-only bind mount. Setup rerun preserved the wallet byte for byte. No production wallet was used. |
| Prior wizard integration tests | The existing reward+wizard branch documents Linux x86_64 container persistence checks in `docs/reward-wizard-integration-validation.md`; the integrated source test suite passed here. |

The complete external pool end-to-end matrix, four simultaneous Stratum jobs over real pool traffic, sustained resource/latency tests, macOS and ARM64 clean-install tests, a full production configuration parity audit, and a complete Mainnet-profile isolated node soak are **NOT_RUN**. T1–T12 local coverage is partly represented by `tests/integration/pool/test_block_submission.py`; see [pre-release test plan](POOL_PRERELEASE_TEST_PLAN.md) for the remaining external cases. Isolated failure simulations are test fixtures, not evidence of specific production incidents.

## Compatibility and remaining gates

The original Mainnet consensus validator, network identity, CHCQ/ML-DSA-44 rules, coinbase maturity of 100 blocks, database schema, wallet format and persistent paths are unchanged. The wallet candidate filter and template payout preflight are policy checks before consensus; they do not relax validation. The extra `/v1/block` field is additive. Legacy pool requests retain their current fields, TTL of 15 seconds and response reasons. Full-block submission is an opt-in omission of `template_id`.

Release readiness remains **NO-GO** because the integrated candidate has not received an external pool end-to-end test, the complete T1–T12 and Mainnet-profile soak gates are open, and the actual reward-node-to-host mappings/configuration of all four hosts have not been reconfirmed. The three legacy error-code proposals C–E require a maintainer/pool compatibility decision and are intentionally absent. Production rollout requires explicit approval after these checks; no branch or image was published.

See [rollout and rollback procedure](MAINNET_INTEGRATED_RC_ROLLOUT.md) and [pool compatibility matrix](BLOCK_SUBMISSION_COMPATIBILITY.md).
