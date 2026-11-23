# Reward maturity and Docker-first setup integration (local validation)

Branch: `codex/reward-wizard-integration`. This is a local development branch, not a production release. It contains reward audit `70d8021`, reward fix `059b666`, Docker-first wizard commits `12b4bad`, `466fc71`, `414c272`, their merge, and an integrated regression test. The two source branches remain unchanged. Shared base: `1634088`. No source-file merge conflict occurred.

## Change and scope

`NodeService.list_spendable_outputs()` now uses the existing consensus `is_coinbase_mature()` predicate at the next candidate block height. `utxo_diagnostics()` uses the same predicate. Mainnet's 100-block parameter, transaction encoding, PQ signatures, consensus validation, mining submission and blockchain data formats are unchanged. The Docker-first launcher and setup image are inherited from their original branch.

## Tests actually run on Tobia (Linux x86_64)

| Evidence | Result |
| --- | --- |
| Reward/Core/wallet suite in reward branch: reward automation, Mainnet PQ end-to-end, CLI, HTTP API, funded reward consensus, wallet signer | 174 passed, 2 skipped. |
| Equivalent integrated suite plus wizard, native PQ backend and cross-feature test | First run 236 passed, 2 skipped, one unrelated time-sensitive CLI test failed because two successive `ban_remaining_seconds` reads differed by one second. That test passed alone; complete rerun: 237 passed, 2 skipped. |
| `tests/node/test_reward_renewal_maturity.py` | 3 passed. Covers Mainnet 99/100-block boundary, mixed UTXOs, real lack of spendable funds, PQ automatic renewal, actual attestation submission, transient submission failure, DB reopen and next epoch. Uses an isolated easy-PoW Mainnet test profile, not production chain data. |
| Integrated test `test_persistent_wizard_reward_wallet_renews_with_immature_coinbase_after_restart` | Passed: wizard-created PQ wallet loaded by the Core; renewal at two epochs across a DB reopen excluded fresh immature coinbase outputs. |
| `sh -n setup.sh`, `git diff --check`, branch ancestry and source scope | Passed. No consensus or cryptography sources changed. |
| `docker build --pull --platform linux/amd64 -f Dockerfile` and setup image build | Passed. Both images carry code commit `fd79225` as their revision label; the subsequent commit only adds this report. Runtime inspection confirmed `list_spendable_outputs()` contains the maturity predicate, and the setup image passed the ML-DSA-44 known-answer check. |
| Real `./setup.sh` using a pseudo-terminal and a fresh `/tmp` root | Passed: Mainnet passive setup completed, Compose config validated, no service started. The generated config and database are host-persistent and mode `0600`. |
| Separate setup/Core containers, both with `--network none` and a temporary host bind mount | Passed: setup image generated a CHCQ wallet, Core image loaded it and excluded an immature UTXO. Wallet mode `0600`; a database explicitly prepared by the wizard remained `0600` after Core opened it. |

The existing test virtual environment needed a native extension from the same local source tree for pytest collection. This extension was Git-ignored and excluded from the Docker build context. The Docker test built the extension independently from pinned sources in the image.

## Remaining limitations and compatibility

- No production Mainnet database, wallet, container, transaction or node was touched. No push or deployment was performed.
- ARM64, macOS Intel and macOS Apple Silicon real clean-install tests remain NOT_RUN. The integrated Docker test ran only on Linux x86_64.
- The cross-container test loaded a Docker-created wallet and checked candidate selection. Full reward renewal with a separate wizard-created wallet was verified in the integrated source-level test, not as a running Docker service.
- A raw `NodeService.open_sqlite()` call on a new path in a separate temporary check produced a mode `0644` database. The normal Docker-first wizard creates the database first with mode `0600`; that path was verified. Operators using a manual Core path should provision its private database path explicitly. This is a pre-existing behavior outside the reward fix.
- Julien's RC `a53f2b0` is **not** incorporated. Static review shows its `service.py` changes leave `list_spendable_outputs()` untouched and its `runtime.py` changes are limited to block submission. The one shared import line in `service.py` must be reconciled when applying this work to the RC: retain both `is_coinbase_mature` and `validate_block_stateless`. The RC removes template invalidation after `receive_transaction()`; the reward fix does not change that path or submit-block. Combined RC-plus-fix tests are NOT_RUN.

## Proposed future Mainnet rollout (not executed)

1. Complete Crypto Connection's isolated tests of Julien's RC and record the maintainer's release decision. Keep the RC separate until that gate passes.
2. Rebase or merge the approved RC and this integration in a fresh review branch; reconcile the `service.py` import line. Run both the pool submission tests and reward/wizard suites against the actual combined tree.
3. Build and identify the candidate image from the exact reviewed commit. Use an isolated Mainnet-profile test node with synthetic keys and mature/immature UTXOs before any production action.
4. With explicit deployment approval, back up the target host's configuration, wallet and consistent database state, retain the previous image, update one reward node at a time, and check chain identity, sync, wallet balance, renewal submission, mempool acceptance and next-epoch confirmation. Monitor attestations separately.
5. If renewal or mining submission regresses, restore the previous image and configuration while retaining persistent volumes. Do not delete the peerbook, wallets or chain database and never use `docker compose down -v`.
