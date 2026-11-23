# Mainnet reward-node automatic renewal: maturity audit

Status: investigation only. No Core correction or production operation has been performed. This audit branch is `codex/reward-node-renewal-audit`, based on `1634088`. The relevant Core files are unchanged between `171ed3e` (the reported deployed image tag) and this branch. The image binary itself and chipcom's private database/logs have not been inspected in this audit.

## Reported incident and evidence levels

The operator reports `reward-chipcom-mainnet`, owner and attestation address `CHCQCqkNLTqeYVGEZpxu8wxv18aG6D8E4GscJyL66qLcGJBLsuKsjyvP`, renewal at block 14300, no renewal at 14400, both automation flags enabled, 85 mature coinbase UTXOs, one immature coinbase UTXO, two mature non-coinbase UTXOs, and repeated `Coinbase output is not mature enough to spend.` These figures and heights are operator observations, not independently rechecked against the live chain here. The source and isolated reproduction below establish a defect capable of causing exactly this error even with ample mature funds. Without the rejected transaction's input outpoints and the chipcom database, we cannot prove which particular UTXO the live attempt selected.

## Execution path and root cause

1. `load_reward_node_automation_config_from_env()` in `src/chipcoin/node/runtime.py` reads the two flags and wallet paths. `NodeRuntime.__init__()` loads the owner and attestation wallet, allowing the same file for both.
2. `_reward_automation_loop()` calls `_run_reward_automation_once()` and logs any exception. The pass checks sync readiness, derives the next-block epoch, invokes `_maybe_auto_renew()` first, then `_maybe_auto_attest()`.
3. `_maybe_auto_renew()` checks the registered owner, current epoch and staged renewals. It builds a funded `renew_reward_node` transaction with `TransactionSigner.build_renew_reward_node_transaction()`, supplying `NodeService.list_spendable_outputs(owner.address)`. It then calls `NodeRuntime.submit_transaction()` and records successful submission.
4. `NodeService.list_spendable_outputs()` in `src/chipcoin/node/service.py` iterates all active-chain UTXOs for the address, **without checking coinbase maturity**. Its name and docstring therefore overstate what it returns.
5. `TransactionSigner._sign_special_node_metadata()` passes those candidates to `wallet.selection.select_inputs()`, which sorts ascending by amount and picks until the renewal fee is covered. A small immature coinbase output can be selected even if many mature outputs exist.
6. `NodeRuntime.submit_transaction()` calls `NodeService.receive_transaction()` and `Mempool.accept()`. The latter calls `validate_transaction()`. `_validate_funded_reward_node_payment()` in `src/chipcoin/consensus/validation.py` checks each selected input with `is_coinbase_mature()` and rejects an immature one with the exact observed error. This is a correct consensus/mempool rejection.

The mismatch between candidate enumeration and contextual validation is **demonstrated in source**. The precise input selection on chipcom is **not yet demonstrated**. A large spendable balance does not prevent the error because the selector orders individual outputs by value.

## Maturity comparison

| Layer | Function | Candidate spend height and rule |
| --- | --- | --- |
| Consensus validator | `is_coinbase_mature()` and `_validate_funded_reward_node_payment()` | A coinbase output is usable when `spend_height - origin_height >= params.coinbase_maturity`. Mainnet sets `coinbase_maturity=100` in `src/chipcoin/consensus/params.py`. |
| Wallet input selection | `select_inputs()` | Assumes all supplied candidates are spendable; has no origin height or coinbase flag in `SpendCandidate`. |
| Candidate provider | `NodeService.list_spendable_outputs()` | Currently includes all address UTXOs, including immature coinbase outputs. |
| CLI and HTTP balance/UTXO diagnostics | `NodeService.utxo_diagnostics()` / `balance_diagnostics()` | Uses next height (`tip.height + 1`) and the same numeric maturity threshold as consensus. CLI `utxos`, `balance`, `wallet-utxos`, `wallet-balance` and HTTP `/v1/address/<address>` expose those diagnostics. |

## Isolated reproduction and baseline tests

In a temporary SQLite database opened with `MAINNET_PARAMS`, three synthetic outputs were inserted for one test address: a one-chipbit coinbase at origin height 14350, a 100-chipbit coinbase at height 14300, and a 100-chipbit ordinary output at height 14399. With a synthetic tip of 14400, diagnostics reported the first output immature, but `list_spendable_outputs()` returned all three and `select_inputs(candidates, 10)` selected that immature output first. Output: `maturity 100`, `reported_immature False`, `candidate_count 3`, `selected_immature True`, `mature_alternatives 2`. The reproduction verifies the selection mismatch, **not** an on-chain Mainnet renewal or the exact chipcom transaction.

Baseline command: `PYTHONPATH=src <existing-venv>/bin/pytest -q tests/node/test_reward_node_automation.py tests/node/test_reward_node_automation_activation.py tests/node/test_reward_node_automation_over_emission.py tests/node/test_cli.py -k 'reward_node_automation or coinbase_maturity'` passed 11 tests (87 deselected). A prebuilt native extension from the same local source tree was copied into the disposable worktree so this environment could run pytest. Existing reward automation tests largely use synthetic parameters with `coinbase_maturity=0`; they do not cover the reported mixed-UTXO case.

## Restart, cache and attestation assessment

- `list_spendable_outputs()` reads persisted chainstate each call and has no UTXO-selection cache. The runtime's reward assignment cache is keyed by epoch and tip and is used for attestations, not renewal input selection. A restart alone therefore does not remove this defect. A chain change can change which UTXOs are mature or unspent.
- `_reward_automation_sync_ready()` skips a pass while the node is behind its validated tip. The reported error indicates a transaction reached validation; it does not prove whether sync delay also occurred earlier.
- The renewal is attempted before attestation in a single pass. An attestation exception cannot prevent the already attempted renewal in that pass. A renewal exception *does* prevent attestation in that pass because the two calls share one outer exception handler. This is a separate availability issue to assess after the maturity fix; changing it is not required to explain the observed renewal error.
- The in-memory set of submitted renewal epochs is not the sole guard: `_has_staged_reward_renewal()` checks the mempool, and the registry height checks confirmed renewal. Restart and epoch transition behavior still need a mixed-UTXO regression test.

## Minimal proposed correction (not yet implemented)

Filter coinbase UTXOs in `NodeService.list_spendable_outputs()` using `is_coinbase_mature(entry, next_block_height, self.params)`; preserve every mature coinbase and non-coinbase output. Reuse the consensus predicate rather than copying `>= 100` or changing the maturity parameter. This repairs all callers that use the provider for funded registration, renewal and wallet transfers. Keep the validator's existing rejection intact. Consider sharing the same predicate with `utxo_diagnostics()` to eliminate two independently maintained implementations of the rule.

Regression cases before merging any correction:

1. Mixed small immature, mature coinbase and ordinary UTXOs: diagnostics and selected inputs agree; a funded renewal submits when mature funds cover the fee.
2. Boundary heights `origin + 99` and `origin + 100`; no change to Mainnet's 100-block maturity.
3. Insufficient mature funds despite a high total balance: clear failure, no invalid transaction staged.
4. Existing wallet, same wallet for owner/attestation, node restart, staged renewal and next epoch: no duplicate or skipped renewal.
5. An attestation failure after renewal and a renewal failure before attestation: verify present ordering and logging separately.
6. CLI/API UTXO and balance diagnostics match wallet selection; reorg or tip change recomputes eligibility from active chainstate.

## Open evidence

Read-only inspection of the deployed image digest and redacted rejected transaction input outpoints would establish exact chipcom correspondence. Do not expose wallet seeds or make any Mainnet transaction for this audit. No consensus, database, wallet or production service change is proposed.
