# Native Reward Local Test

This is the smallest local end-to-end runbook for the native reward-node payout prototype.

It proves a non-empty rewarded settlement with real payout outputs on a local SQLite-backed devnet node.
It does not require HTTP runtime.

Height semantics used below:

- `status.height` is the last committed block height
- `mine-local-block` builds height `tip + 1`
- devnet native reward activation height is `300`
- epoch `3` covers block heights `300..399`
- the settlement for epoch `3` must be submitted while tip is `398`, so it is mined at height `399`

Current devnet prototype thresholds:

- `epoch_length_blocks = 100`
- `reward_target_checks_per_epoch = 3`
- `reward_min_passed_checks_per_epoch = 2`
- `reward_verifier_quorum = 2`
- `reward_final_confirmation_window_blocks = 10`

For the flow below, `reward-node-a` qualifies by:

- passing quorum in one early assigned check window
- passing quorum again in its final assigned check window

## 1. Start from a clean local database

```bash
mkdir -p ./run
rm -f ./run/native-devnet.sqlite3
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 start
```

## 2. Generate one miner wallet and four reward-node wallets

```bash
.venv/bin/chipcoin --network devnet wallet-generate --wallet-file ./run/miner.json
.venv/bin/chipcoin --network devnet wallet-generate --wallet-file ./run/reward-a.json
.venv/bin/chipcoin --network devnet wallet-generate --wallet-file ./run/reward-b.json
.venv/bin/chipcoin --network devnet wallet-generate --wallet-file ./run/reward-c.json
.venv/bin/chipcoin --network devnet wallet-generate --wallet-file ./run/reward-d.json
```

Extract addresses and node pubkeys:

```bash
MINER_ADDR="$(.venv/bin/chipcoin --network devnet wallet-address --wallet-file ./run/miner.json | jq -r .address)"

REWARD_A_ADDR="$(.venv/bin/chipcoin --network devnet wallet-address --wallet-file ./run/reward-a.json | jq -r .address)"
REWARD_B_ADDR="$(.venv/bin/chipcoin --network devnet wallet-address --wallet-file ./run/reward-b.json | jq -r .address)"
REWARD_C_ADDR="$(.venv/bin/chipcoin --network devnet wallet-address --wallet-file ./run/reward-c.json | jq -r .address)"
REWARD_D_ADDR="$(.venv/bin/chipcoin --network devnet wallet-address --wallet-file ./run/reward-d.json | jq -r .address)"

REWARD_A_PUB="$(.venv/bin/chipcoin --network devnet wallet-address --wallet-file ./run/reward-a.json | jq -r .public_key_hex)"
REWARD_B_PUB="$(.venv/bin/chipcoin --network devnet wallet-address --wallet-file ./run/reward-b.json | jq -r .public_key_hex)"
REWARD_C_PUB="$(.venv/bin/chipcoin --network devnet wallet-address --wallet-file ./run/reward-c.json | jq -r .public_key_hex)"
REWARD_D_PUB="$(.venv/bin/chipcoin --network devnet wallet-address --wallet-file ./run/reward-d.json | jq -r .public_key_hex)"
```

## 3. Mine up to the native reward activation boundary

Mine `300` local blocks so the committed tip becomes `299`:

```bash
for _ in $(seq 1 300); do
  .venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
    mine-local-block --payout-address "$MINER_ADDR" >/dev/null
done
```

Confirm the tip:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  status | jq '{height, tip_hash, sync_phase}'
```

Expected height here: `299`.

## 4. Register four reward nodes and confirm them at height 300

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 register-reward-node \
  --wallet-file ./run/reward-a.json \
  --node-id reward-node-a \
  --payout-address "$REWARD_A_ADDR" \
  --node-pubkey-hex "$REWARD_A_PUB" \
  --declared-host 127.0.0.1 \
  --declared-port 19001

.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 register-reward-node \
  --wallet-file ./run/reward-b.json \
  --node-id reward-node-b \
  --payout-address "$REWARD_B_ADDR" \
  --node-pubkey-hex "$REWARD_B_PUB" \
  --declared-host 127.0.0.1 \
  --declared-port 19002

.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 register-reward-node \
  --wallet-file ./run/reward-c.json \
  --node-id reward-node-c \
  --payout-address "$REWARD_C_ADDR" \
  --node-pubkey-hex "$REWARD_C_PUB" \
  --declared-host 127.0.0.1 \
  --declared-port 19003

.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 register-reward-node \
  --wallet-file ./run/reward-d.json \
  --node-id reward-node-d \
  --payout-address "$REWARD_D_ADDR" \
  --node-pubkey-hex "$REWARD_D_PUB" \
  --declared-host 127.0.0.1 \
  --declared-port 19004
```

Mine the registration block:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  mine-local-block --payout-address "$MINER_ADDR"
```

Inspect the registry:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  node-registry | jq
```

You should see `reward_registration: true` and the declared host/port fields for all four nodes.

## 5. Inspect epoch seed and deterministic assignments for epoch 3

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  reward-epoch-seed --epoch-index 3 | jq
```

```bash
ASSIGN_JSON="$(.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  reward-assignments --epoch-index 3 --node-id reward-node-a)"

echo "$ASSIGN_JSON" | jq
```

Derive one early check window, the final check window, and two verifiers from each committee:

```bash
WINDOW_FIRST="$(echo "$ASSIGN_JSON" | jq -r '.[0].candidate_check_windows[0]')"
WINDOW_FINAL="$(echo "$ASSIGN_JSON" | jq -r '.[0].candidate_check_windows[-1]')"

VERIFIER_FIRST_A="$(echo "$ASSIGN_JSON" | jq -r --arg w "$WINDOW_FIRST" '.[0].verifier_committees[$w][0]')"
VERIFIER_FIRST_B="$(echo "$ASSIGN_JSON" | jq -r --arg w "$WINDOW_FIRST" '.[0].verifier_committees[$w][1]')"
VERIFIER_FINAL_A="$(echo "$ASSIGN_JSON" | jq -r --arg w "$WINDOW_FINAL" '.[0].verifier_committees[$w][0]')"
VERIFIER_FINAL_B="$(echo "$ASSIGN_JSON" | jq -r --arg w "$WINDOW_FINAL" '.[0].verifier_committees[$w][1]')"
```

Map verifier node ids back to wallet files:

```bash
wallet_for_node() {
  case "$1" in
    reward-node-a) echo ./run/reward-a.json ;;
    reward-node-b) echo ./run/reward-b.json ;;
    reward-node-c) echo ./run/reward-c.json ;;
    reward-node-d) echo ./run/reward-d.json ;;
    *) echo "unknown verifier node id: $1" >&2; return 1 ;;
  esac
}
```

## 6. Submit four signed attestation bundles for reward-node-a

We submit:

- two pass attestations in the first assigned window
- two pass attestations in the final assigned window

That satisfies the current prototype rule:

- at least two passed windows
- quorum two-of-three per passed window
- one passed window must be the final assigned window

Create and submit one signed bundle:

```bash
submit_bundle() {
  local window="$1"
  local verifier_node_id="$2"
  local wallet_file
  wallet_file="$(wallet_for_node "$verifier_node_id")"
  local bundle_file="./run/bundle-${window}-${verifier_node_id}.json"

  jq -n \
    --argjson epoch 3 \
    --argjson bundle_window "$window" \
    --arg submitter "$verifier_node_id" \
    --arg candidate "reward-node-a" \
    --arg verifier "$verifier_node_id" \
    --arg endpoint "127.0.0.1:19001" \
    --arg concentration "demo:reward-node-a" \
    '{
      epoch_index: $epoch,
      bundle_window_index: $bundle_window,
      bundle_submitter_node_id: $submitter,
      attestations: [
        {
          epoch_index: $epoch,
          check_window_index: $bundle_window,
          candidate_node_id: $candidate,
          verifier_node_id: $verifier,
          result_code: "pass",
          observed_sync_gap: 0,
          endpoint_commitment: $endpoint,
          concentration_key: $concentration,
          signature_hex: ""
        }
      ]
    }' > "$bundle_file"

  .venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
    submit-reward-attestation-bundle \
    --bundle-file "$bundle_file" \
    --wallet-file "$wallet_file"
}
```

Submit the four bundles:

```bash
submit_bundle "$WINDOW_FIRST" "$VERIFIER_FIRST_A"
submit_bundle "$WINDOW_FIRST" "$VERIFIER_FIRST_B"
submit_bundle "$WINDOW_FINAL" "$VERIFIER_FINAL_A"
submit_bundle "$WINDOW_FINAL" "$VERIFIER_FINAL_B"
```

Mine one block to persist the bundles:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  mine-local-block --payout-address "$MINER_ADDR"
```

Inspect stored attestations:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  reward-attestations --epoch-index 3 | jq
```

## 7. Advance to the settlement inclusion point

Mine forward until the committed tip is `398`:

```bash
while [ "$(.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 status | jq -r .height)" -lt 398 ]; do
  .venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
    mine-local-block --payout-address "$MINER_ADDR" >/dev/null
done
```

Confirm the tip:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  status | jq '{height, tip_hash}'
```

Expected height here: `398`.

## 8. Inspect the deterministic settlement preview before close

This is now an inspection/debug step only.
The normal happy path does not require manual settlement submission.

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  reward-settlement-preview --epoch-index 3 | tee ./run/settlement-epoch3.json | jq
```

Expected outcome in the preview:

- `rewarded_node_count` is at least `1`
- `distributed_node_reward_chipbits` is non-zero
- `reward_entries` is non-empty
- one of the entries pays `reward-node-a` / `$REWARD_A_ADDR`

Optional detailed report before close:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  reward-settlement-report --epoch-index 3 | jq
```

This report explains:

- which node ranked as rewardable
- which node was not rewarded and why
- quorum / failed windows
- anti-concentration exclusions
- settlement accounting summary

## 9. Mine the closing block and let settlement auto-generate

Mine the epoch-closing block at height `399`:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  mine-local-block --payout-address "$MINER_ADDR"
```

## 10. Inspect the stored settlement and the materialized payout outputs

Inspect the stored settlement payload:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  reward-settlements --epoch-index 3 | jq
```

You should now see the settlement persisted with:

- `submission_mode = "auto"`
- non-empty `reward_entries`

If you want the richer explanation after close as well:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  reward-settlement-report --epoch-index 3 | jq
```

Inspect the closing block and its native reward outputs:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  block --height 399 | jq '{height, node_reward_payouts, transactions}'
```

Inspect UTXOs and balance for the rewarded address:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  utxos --address "$REWARD_A_ADDR" | jq

.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  balance --address "$REWARD_A_ADDR" | jq
```

Inspect reward history for the same address:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  reward-history --address "$REWARD_A_ADDR" | jq
```

The key proof points are:

- the settlement payload is stored on chain
- `submission_mode` is `auto`
- `reward_entries` is non-empty
- `block --height 399` shows matching `node_reward_payouts`
- the rewarded address now has the corresponding UTXO and balance

## 11. Optional manual override debug path

The manual submit path is still available for diagnostics and negative tests.
It is no longer the default happy path.

If you want to force a manual settlement instead of auto-generation:

```bash
.venv/bin/chipcoin --network devnet --data ./run/native-devnet.sqlite3 \
  submit-reward-settle-epoch --settlement-file ./run/settlement-epoch3.json
```

Then mine the closing block as above.
In that case `reward-settlements --epoch-index 3` should show `submission_mode = "manual"`.

## 12. Optional zero-recipient control path

To prove the negative control path instead, repeat the flow but skip the attestation submissions.

At preview time you should then see:

- `rewarded_node_count = 0`
- `distributed_node_reward_chipbits = 0`
- `undistributed_node_reward_chipbits = 5000000000`
- `reward_entries = []`

And the closing block should show:

- no `node_reward_payouts`

## 13. What this checkpoint already proves

- native reward-node registration is accepted and persisted
- deterministic epoch seed and assignment diagnostics are inspectable
- signed attestation bundles are accepted and persisted
- settlement payloads are derived from actual attestation-backed eligibility
- settlement accounting fields are real, not placeholders
- settlement is auto-generated on the epoch-closing block in the normal local flow
- the epoch-closing block materializes the corresponding native reward outputs
- rewarded address UTXOs and balances prove the payout actually happened

## 14. What is still incomplete

- automatic dispute flow is not implemented yet
- anti-concentration remains a coarse prototype filter, not a final production design
- automatic settlement exists for the local/native mining path, but broader runtime productization is still intentionally narrow
- broader runtime/API polish is deferred
