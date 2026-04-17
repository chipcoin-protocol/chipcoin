# Native Reward Distributed Devnet Runbook

This runbook is the practical multi-machine validation path for the current native reward prototype.

Goal:

- run 3+ reward nodes on separate machines
- run 1-2 miners
- include one fresh-sync full node
- include one snapshot-bootstrapped full node
- prove that honest nodes derive the same reward assignments, settlement preview, stored settlement, and closing-block payout outputs

This document uses the current repo surfaces only:

- `chipcoin run`
- `chipcoin mine`
- `chipcoin register-reward-node`
- `chipcoin submit-reward-attestation-bundle`
- `chipcoin reward-epoch-state`
- `chipcoin reward-assignments`
- `chipcoin reward-attestations`
- `chipcoin reward-settlements`
- `chipcoin reward-settlement-report`
- HTTP routes:
  - `GET /v1/status`
  - `GET /v1/rewards/epoch`
  - `GET /v1/rewards/assignments`
  - `GET /v1/rewards/attestations`
  - `GET /v1/rewards/settlements`
  - `GET /v1/rewards/settlement-report`

## Topology

Suggested minimum topology:

- machine A: bootstrap node, reward node A, miner A
- machine B: reward node B
- machine C: reward node C
- machine D: fresh-sync full node
- machine E: snapshot-bootstrap full node

Suggested ports:

- P2P: `18444`
- HTTP API: `8081`

Example hostnames:

- `node-a.example.net`
- `node-b.example.net`
- `node-c.example.net`
- `node-d.example.net`
- `node-e.example.net`

## 1. Start the bootstrap node

On machine A:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-a.sqlite3 run \
  --listen-port 18444 \
  --http-port 8081
```

Verify:

```bash
curl -s http://127.0.0.1:8081/v1/status | jq '{height, tip_hash, sync_phase, bootstrap_mode}'
```

## 2. Start reward nodes and fresh-sync full node

On machines B, C, and D:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node.sqlite3 run \
  --listen-port 18444 \
  --http-port 8081 \
  --peer node-a.example.net:18444
```

Verify connectivity:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node.sqlite3 peer-summary | jq
curl -s http://127.0.0.1:8081/v1/status | jq '{height, tip_hash, handshaken_peer_count, sync_phase}'
```

## 3. Create the snapshot node

On machine A, export a snapshot after the chain is initialized:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-a.sqlite3 snapshot-export \
  --snapshot-file /tmp/devnet-reward.snapshot
```

Transfer it to machine E and import:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-e.sqlite3 snapshot-import \
  --snapshot-file /tmp/devnet-reward.snapshot
```

Then start machine E:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-e.sqlite3 run \
  --listen-port 18444 \
  --http-port 8081 \
  --peer node-a.example.net:18444
```

Verify snapshot mode:

```bash
curl -s http://127.0.0.1:8081/v1/status | jq '{bootstrap_mode, snapshot_anchor_height, sync_phase, height}'
```

## 4. Start miners

Primary miner on machine A:

```bash
chipcoin --network devnet mine \
  --node-url http://127.0.0.1:8081 \
  --miner-address <MINER_A_ADDRESS> \
  --miner-id miner-a
```

Optional secondary miner on another machine:

```bash
chipcoin --network devnet mine \
  --node-url http://node-a.example.net:8081 \
  --miner-address <MINER_B_ADDRESS> \
  --miner-id miner-b
```

## 5. Register reward nodes

Generate one wallet per reward node if needed:

```bash
chipcoin wallet-generate --wallet-file reward-node-a.json
chipcoin wallet-generate --wallet-file reward-node-b.json
chipcoin wallet-generate --wallet-file reward-node-c.json
```

Show each payout address and public key:

```bash
chipcoin wallet-address --wallet-file reward-node-a.json | jq
chipcoin wallet-address --wallet-file reward-node-b.json | jq
chipcoin wallet-address --wallet-file reward-node-c.json | jq
```

Register each reward node against the bootstrap peer.

Machine A:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-a.sqlite3 register-reward-node \
  --wallet-file reward-node-a.json \
  --node-id reward-node-a \
  --payout-address <REWARD_NODE_A_ADDRESS> \
  --node-pubkey-hex <REWARD_NODE_A_PUBKEY_HEX> \
  --declared-host node-a.example.net \
  --declared-port 18444 \
  --connect node-a.example.net:18444 | jq
```

Machine B:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-b.sqlite3 register-reward-node \
  --wallet-file reward-node-b.json \
  --node-id reward-node-b \
  --payout-address <REWARD_NODE_B_ADDRESS> \
  --node-pubkey-hex <REWARD_NODE_B_PUBKEY_HEX> \
  --declared-host node-b.example.net \
  --declared-port 18444 \
  --connect node-a.example.net:18444 | jq
```

Machine C:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-c.sqlite3 register-reward-node \
  --wallet-file reward-node-c.json \
  --node-id reward-node-c \
  --payout-address <REWARD_NODE_C_ADDRESS> \
  --node-pubkey-hex <REWARD_NODE_C_PUBKEY_HEX> \
  --declared-host node-c.example.net \
  --declared-port 18444 \
  --connect node-a.example.net:18444 | jq
```

Inspect the registry from multiple machines:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-a.sqlite3 node-registry | jq
chipcoin --network devnet --data /var/lib/chipcoin/node-b.sqlite3 node-registry | jq
chipcoin --network devnet --data /var/lib/chipcoin/node-c.sqlite3 node-registry | jq
```

## 6. Inspect deterministic epoch state before attestation submission

Pick the target epoch:

```bash
EPOCH=3
```

Inspect locally:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-a.sqlite3 reward-epoch-state --epoch-index "$EPOCH" | jq
chipcoin --network devnet --data /var/lib/chipcoin/node-b.sqlite3 reward-epoch-state --epoch-index "$EPOCH" | jq
chipcoin --network devnet --data /var/lib/chipcoin/node-c.sqlite3 reward-epoch-state --epoch-index "$EPOCH" | jq
```

Inspect remotely:

```bash
curl -s "http://node-a.example.net:8081/v1/rewards/epoch?epoch_index=$EPOCH" | jq
curl -s "http://node-b.example.net:8081/v1/rewards/epoch?epoch_index=$EPOCH" | jq
curl -s "http://node-c.example.net:8081/v1/rewards/epoch?epoch_index=$EPOCH" | jq
```

For honest nodes at the same tip height, these must match:

- `comparison_keys.active_reward_nodes_digest`
- `comparison_keys.assignments_digest`
- `comparison_keys.attestations_digest`
- `comparison_keys.settlement_preview_digest`
- `comparison_keys.stored_settlements_digest`

If they do not match:

- `active_reward_nodes_digest` mismatch: registry state diverged
- `assignments_digest` mismatch: registry or epoch seed diverged
- `attestations_digest` mismatch: bundle relay or block inclusion diverged
- `settlement_preview_digest` mismatch: settlement inputs or accounting diverged

## 7. Submit reward attestation bundles

Discover assignments:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-a.sqlite3 reward-assignments --epoch-index "$EPOCH" | jq
curl -s "http://node-a.example.net:8081/v1/rewards/assignments?epoch_index=$EPOCH" | jq
```

Create one bundle JSON on the verifier machine:

```json
{
  "epoch_index": 3,
  "bundle_window_index": 0,
  "bundle_submitter_node_id": "reward-node-b",
  "attestations": [
    {
      "epoch_index": 3,
      "check_window_index": 0,
      "candidate_node_id": "reward-node-a",
      "verifier_node_id": "reward-node-b",
      "result_code": "pass",
      "observed_sync_gap": 0,
      "endpoint_commitment": "node-a.example.net:18444",
      "concentration_key": "demo:reward-node-a"
    }
  ]
}
```

Submit it:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-b.sqlite3 submit-reward-attestation-bundle \
  --bundle-file reward-attestation.json \
  --wallet-file reward-node-b.json \
  --connect node-a.example.net:18444 | jq
```

Inspect received attestations from multiple nodes:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-a.sqlite3 reward-attestations --epoch-index "$EPOCH" | jq
chipcoin --network devnet --data /var/lib/chipcoin/node-d.sqlite3 reward-attestations --epoch-index "$EPOCH" | jq
curl -s "http://node-a.example.net:8081/v1/rewards/attestations?epoch_index=$EPOCH" | jq
```

## 8. Compare settlement preview before epoch close

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-a.sqlite3 reward-settlement-report --epoch-index "$EPOCH" | jq
chipcoin --network devnet --data /var/lib/chipcoin/node-b.sqlite3 reward-settlement-report --epoch-index "$EPOCH" | jq
curl -s "http://node-a.example.net:8081/v1/rewards/settlement-report?epoch_index=$EPOCH" | jq
```

For honest nodes at the same tip, the preview must agree on:

- `epoch_seed`
- `rewarded_node_count`
- `distributed_node_reward_chipbits`
- `undistributed_node_reward_chipbits`
- `reward_entries`
- `settlement_accounting_summary`

## 9. Close the epoch and inspect stored settlement and payout outputs

Mine until the epoch-closing block is reached. The closing block auto-generates settlement if no valid manual settlement override is present.

Inspect the stored settlement:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-a.sqlite3 reward-settlements --epoch-index "$EPOCH" | jq
chipcoin --network devnet --data /var/lib/chipcoin/node-b.sqlite3 reward-settlements --epoch-index "$EPOCH" | jq
curl -s "http://node-a.example.net:8081/v1/rewards/settlements?epoch_index=$EPOCH" | jq
```

Inspect the closing block:

```bash
chipcoin --network devnet --data /var/lib/chipcoin/node-a.sqlite3 block --height <EPOCH_CLOSE_HEIGHT> | jq
chipcoin --network devnet --data /var/lib/chipcoin/node-a.sqlite3 reward-history --address <REWARDED_ADDRESS> | jq
chipcoin --network devnet --data /var/lib/chipcoin/node-a.sqlite3 utxos --address <REWARDED_ADDRESS> | jq
```

Successful close conditions:

- all honest nodes store the same settlement payload
- `submission_mode` is the same everywhere
- closing-block `node_reward_payouts` match `reward_entries` exactly
- rewarded address history and UTXOs reflect the payout

## 10. Required fault scenarios

Run these cases and re-check `reward-epoch-state`, `reward-settlement-report`, and `reward-settlements` on all honest nodes:

1. Restart during epoch
   - stop machine B mid-epoch
   - continue mining on machine A
   - restart B and confirm it converges to the same settlement

2. Delayed node
   - leave machine D disconnected until after epoch close
   - reconnect and confirm it stores the same settlement and payout block

3. Snapshot join mid-cycle
   - export snapshot from A after registration and attestation inclusion
   - import on E
   - start E and confirm settlement preview and stored settlement match A/B/C

4. Peer disconnect / reconnect
   - stop network connectivity between B and A temporarily
   - reconnect and confirm no duplicate or conflicting settlement appears

5. Miner restart near epoch close
   - stop the miner shortly before close
   - restart it and confirm the closing block still carries the same automatic settlement

## 11. What to record after each scenario

Capture from every honest node:

```bash
curl -s "http://127.0.0.1:8081/v1/status" | jq '{height, tip_hash, sync_phase, handshaken_peer_count}'
curl -s "http://127.0.0.1:8081/v1/rewards/epoch?epoch_index='$EPOCH'" | jq '{tip_height, comparison_keys, settlement_preview}'
curl -s "http://127.0.0.1:8081/v1/rewards/settlements?epoch_index='$EPOCH'" | jq
curl -s "http://127.0.0.1:8081/v1/rewards/settlement-report?epoch_index='$EPOCH'" | jq '{rewarded_node_count, reward_entries, settlement_accounting_summary}'
```

Minimal deterministic success record:

- same `tip_hash`
- same `comparison_keys`
- same `reward_entries`
- same stored settlement
- same payout outputs in the closing block

## Current scope limit

This phase validates distributed determinism, persistence, sync, snapshot join, restart behavior, and payout consistency.

It does not yet validate:

- dispute flow
- adversarial verifier collusion
- stronger anti-concentration redesign
- subjective network-condition contestation
