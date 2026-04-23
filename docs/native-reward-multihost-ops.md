# Native Reward Multi-Host Reset And Test Pack

This is the operator-ready pack for the first real distributed devnet native reward test.

Status note:

- the original test plan in this document has now been validated on the public devnet
- the final corrected runtime includes automatic reward renewal, automatic attestation, automatic epoch settlement, and mining-template filtering for attestation-bundle consensus limits
- the live multi-host run closed consecutive epochs with fully automatic payouts to all three reward nodes

It reflects the corrected topology:

- `chipcom` = central bootstrap node, primary miner, reward node A, canonical comparison source, snapshot exporter
- `tilt` = reward node B, verifier node
- `tobia` = reward node C, verifier node, Codex-controlled machine
- `extra VPS` = follower full node
- `snapshot VPS` = snapshot-join node
- `hermes` is not used in this test

## Validated Outcome

The public multi-host run proved the following behavior end to end:

- `chipcom`, `tilt`, and `tobia` all remained registered reward nodes on-chain
- after warmup and activation, the automation loop renewed each reward node at epoch boundaries
- verifier nodes emitted reward attestation bundles on-chain during open epochs
- epoch-closing settlements were stored automatically
- payout outputs were materialized in the closing block coinbase and were visible through `reward-history`

Observed stable result window:

- closed epochs `3` through `11`
- `rewarded_node_count = 3` on every closed epoch in that window
- `distributed_node_reward_chipbits = 5000000000` on every closed epoch in that window

The integer split rotated the remainder chipbits across the three payout addresses exactly as expected.

## Offline Reward Node Behavior

Reward-node registration is persistent on-chain.

What happens if a reward node goes offline for hours and later returns:

- the node remains registered
- the node does not repeat warmup from genesis
- the node can still sync back to the active chain tip
- but it may miss one or more epoch renewals while offline
- if it misses the renewal timing for the current epoch, it becomes `stale`
- once back online, the automation loop can renew it again for the current epoch and restore active status after confirmation
- missed epochs are not retroactively recovered

Operational rule:

- registration persists
- epoch eligibility does not

## A. Exact Answer: Does `chipcom` need restart?

Yes, for this test you should restart `chipcom`.

Precise reason:

- no systemd unit, timer, compose file, or bootstrap service wiring changed in this track
- the code changes were in repo Python code:
  - node service
  - mining path
  - CLI
  - HTTP API
  - reward diagnostics/runtime tests
- the existing `chipcom` bootstrap wiring remains valid
- but the running `node-a` process must be restarted to load the new code
- and because you explicitly want a clean zero-state devnet run, the bootstrap seed state should also be reset so the peerbook does not carry stale peers from older devnet sessions

What changed:

- repo code only
- no deployment wiring changes

What did not change:

- no compose file changes
- no systemd service changes
- no runtime launch path changes

So the practical answer is:

- `chipcom` bootstrap setup does not need replacement
- `chipcom` runtime does need restart to load the new code
- for a clean test day, stop and reset both `node-a` and `bootstrap-seed`

## B. `chipcom` restart sequence

If `chipcom` is using the repo compose wrapper under [up.sh](/home/komarek/Documents/CODEX/Chipcoin-v2/scripts/remote-devnet/chipcom/up.sh), use this exact sequence.

Stop old services first:

```bash
cd /opt/chipcoin
./scripts/remote-devnet/chipcom/down.sh
docker ps --format '{{.Names}}' | grep -E 'chipcoin-node-a|chipcoin-bootstrap-seed' || true
ss -ltnp | grep -E ':18444|:8081|:28080' || true
```

Clean restart with image rebuild and zero state:

```bash
cd /opt/chipcoin
git fetch origin
git checkout main
git pull --ff-only origin main
git checkout 9c7cea18550329ab7d40b757f58779233cb6cf18
./scripts/remote-devnet/chipcom/down.sh -v
./scripts/remote-devnet/chipcom/up.sh
```

Why `down -v`:

- clears `bootstrap_seed_data`
- clears `node_a_data`
- guarantees no stale node DB, peerbook, or bootstrap peer registry

Health verification:

```bash
./scripts/remote-devnet/chipcom/status.sh
curl -s http://127.0.0.1:8081/v1/status | jq '{height, tip_hash, bootstrap_mode, sync_phase}'
curl -s http://127.0.0.1:28080/v1/health | jq
```

Expected:

- node HTTP responds on `8081`
- bootstrap seed responds on `28080`
- node starts from empty chain state

## C. Global Test Topology

Use this host plan:

- `chipcom`
  - bootstrap seed
  - central node runtime
  - primary miner
  - reward node A
  - canonical comparison source
  - snapshot exporter
- `tilt`
  - reward node B
  - verifier node
- `tobia`
  - reward node C
  - verifier node
  - Codex-controlled machine
- `extra follower host`
  - follower full node only
- `snapshot host`
  - snapshot import mid-cycle

Recommended common ports:

- P2P: `18444`
- HTTP: `8081`
- bootstrap seed API on `chipcom`: `28080`

Recommended common repo revision:

- `9c7cea18550329ab7d40b757f58779233cb6cf18`

## D. Wallet Handling Rules

For this clean devnet reset, regenerate these wallets:

- `chipcom`
  - miner wallet
  - reward node A wallet
- `tilt`
  - reward node B wallet
- `tobia`
  - reward node C wallet

Follower and snapshot hosts do not need reward wallets for the basic test.

After regeneration, you must re-read and re-record:

- payout address
- public key hex

Why regenerate:

- avoids confusion with stale addresses from previous test epochs
- avoids mixing old reward history with the new clean chain
- keeps the first live run easier to audit

Wallet artifacts that can stay:

- none are required to stay
- if you intentionally keep an old wallet file, it is still cryptographically valid, but you must treat it as a new empty-chain identity for this run

## E. Destructive Reset Commands

These commands are intentionally destructive. Run them only if you want a true zero-state restart.

### 1. `chipcom` destructive reset

Stop services first:

```bash
cd /opt/chipcoin
./scripts/remote-devnet/chipcom/down.sh
```

Verify ports are free:

```bash
ss -ltnp | grep -E ':18444|:8081|:28080' || true
```

Remove old compose volumes and optional local artifacts:

```bash
cd /opt/chipcoin
./scripts/remote-devnet/chipcom/down.sh -v
rm -f /tmp/reward-devnet.snapshot /tmp/devnet-reward.snapshot /tmp/devnet.snapshot
```

Verify clean state:

```bash
docker volume ls | grep -E 'bootstrap_seed_data|node_a_data' || true
docker ps --format '{{.Names}}' | grep -E 'chipcoin-node-a|chipcoin-bootstrap-seed' || true
```

### 2. `tilt` destructive reset

If `tilt` is using plain CLI/manual runtime:

Stop old processes:

```bash
pkill -f 'chipcoin.*--data /var/lib/chipcoin/tilt/node.sqlite3' || true
pkill -f 'chipcoin.* mine ' || true
ss -ltnp | grep -E ':18444|:8081' || true
```

Remove old state:

```bash
rm -f /var/lib/chipcoin/tilt/node.sqlite3
rm -rf /var/lib/chipcoin/tilt/wallets
rm -f /tmp/reward-attestation*.json /tmp/*.snapshot
mkdir -p /var/lib/chipcoin/tilt/wallets
```

Verify clean:

```bash
test ! -f /var/lib/chipcoin/tilt/node.sqlite3 && echo clean-db
find /var/lib/chipcoin/tilt/wallets -maxdepth 1 -type f
ss -ltnp | grep -E ':18444|:8081' || true
```

### 3. `tobia` destructive reset

Stop old processes:

```bash
pkill -f 'chipcoin.*node.sqlite3' || true
pkill -f 'chipcoin.* mine ' || true
ss -ltnp | grep -E ':18444|:8081' || true
```

Remove old state:

```bash
rm -f /var/lib/chipcoin/tobia/node.sqlite3
rm -rf /var/lib/chipcoin/tobia/wallets
rm -f /tmp/reward-attestation*.json /tmp/*.snapshot
mkdir -p /var/lib/chipcoin/tobia/wallets
```

Verify clean:

```bash
test ! -f /var/lib/chipcoin/tobia/node.sqlite3 && echo clean-db
find /var/lib/chipcoin/tobia/wallets -maxdepth 1 -type f
ss -ltnp | grep -E ':18444|:8081' || true
```

### 4. `extra follower host` destructive reset

Stop old runtime:

```bash
pkill -f 'chipcoin.*follower.*node.sqlite3' || true
ss -ltnp | grep -E ':18444|:8081' || true
```

Remove old state:

```bash
rm -f /var/lib/chipcoin/follower/node.sqlite3
rm -f /tmp/*.snapshot
```

Verify clean:

```bash
test ! -f /var/lib/chipcoin/follower/node.sqlite3 && echo clean-db
ss -ltnp | grep -E ':18444|:8081' || true
```

### 5. `snapshot host` destructive reset

Stop old runtime:

```bash
pkill -f 'chipcoin.*snapshot.*node.sqlite3' || true
ss -ltnp | grep -E ':18444|:8081' || true
```

Remove old state:

```bash
rm -f /var/lib/chipcoin/snapshot/node.sqlite3
rm -f /tmp/*.snapshot
```

Verify clean:

```bash
test ! -f /var/lib/chipcoin/snapshot/node.sqlite3 && echo clean-db
ss -ltnp | grep -E ':18444|:8081' || true
```

## F. Fresh Setup Commands

Run on all non-`chipcom` hosts after reset:

```bash
cd /opt/chipcoin
git fetch origin
git checkout main
git pull --ff-only origin main
git checkout 9c7cea18550329ab7d40b757f58779233cb6cf18
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e .[dev]
```

## G. Wallet Regeneration Commands

### `chipcom`

```bash
mkdir -p /var/lib/chipcoin/chipcom/wallets
/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-generate --wallet-file /var/lib/chipcoin/chipcom/wallets/miner.json
/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-generate --wallet-file /var/lib/chipcoin/chipcom/wallets/reward-a.json
/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-address --wallet-file /var/lib/chipcoin/chipcom/wallets/miner.json | jq
/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-address --wallet-file /var/lib/chipcoin/chipcom/wallets/reward-a.json | jq
```

### `tilt`

```bash
mkdir -p /var/lib/chipcoin/tilt/wallets
/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-generate --wallet-file /var/lib/chipcoin/tilt/wallets/reward-b.json
/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-address --wallet-file /var/lib/chipcoin/tilt/wallets/reward-b.json | jq
```

### `tobia`

```bash
mkdir -p /var/lib/chipcoin/tobia/wallets
/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-generate --wallet-file /var/lib/chipcoin/tobia/wallets/reward-c.json
/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-address --wallet-file /var/lib/chipcoin/tobia/wallets/reward-c.json | jq
```

You must copy out these fields from each `wallet-address` result:

- `address`
- `public_key_hex`

## H. Start Sequence Per Host

This is the exact order for the test day.

### 1. Start `chipcom` first

Bring up compose services:

```bash
cd /opt/chipcoin
./scripts/remote-devnet/chipcom/up.sh
```

Start miner locally if you are not using a dedicated separate miner service:

```bash
export MINER_ADDR="$(/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-address --wallet-file /var/lib/chipcoin/chipcom/wallets/miner.json | jq -r .address)"
tmux new -d -s chip-miner \
  "/opt/chipcoin/.venv/bin/chipcoin --network devnet mine --node-url http://127.0.0.1:8081 --miner-address $MINER_ADDR --miner-id miner-chipcom"
```

Verification:

```bash
./scripts/remote-devnet/chipcom/status.sh
curl -s http://127.0.0.1:8081/v1/status | jq '{height, tip_hash, bootstrap_mode, sync_phase, handshaken_peer_count}'
curl -s http://127.0.0.1:28080/v1/health | jq
ss -ltnp | grep -E ':18444|:8081|:28080'
```

### 2. Start `tilt` second

Start node runtime:

```bash
tmux new -d -s chip-node \
  "/opt/chipcoin/.venv/bin/chipcoin --network devnet --data /var/lib/chipcoin/tilt/node.sqlite3 run --listen-port 18444 --http-port 8081 --peer chipcoinprotocol.com:18444"
```

Verification:

```bash
curl -s http://127.0.0.1:8081/v1/status | jq '{height, tip_hash, sync_phase, handshaken_peer_count}'
/opt/chipcoin/.venv/bin/chipcoin --network devnet --data /var/lib/chipcoin/tilt/node.sqlite3 peer-summary | jq
ss -ltnp | grep -E ':18444|:8081'
```

### 3. Start `tobia` third

Start node runtime:

```bash
tmux new -d -s chip-node \
  "/opt/chipcoin/.venv/bin/chipcoin --network devnet --data /var/lib/chipcoin/tobia/node.sqlite3 run --listen-port 18444 --http-port 8081 --peer chipcoinprotocol.com:18444"
```

Verification:

```bash
curl -s http://127.0.0.1:8081/v1/status | jq '{height, tip_hash, sync_phase, handshaken_peer_count}'
/opt/chipcoin/.venv/bin/chipcoin --network devnet --data /var/lib/chipcoin/tobia/node.sqlite3 peer-summary | jq
ss -ltnp | grep -E ':18444|:8081'
```

### 4. Start follower host later

```bash
tmux new -d -s chip-node \
  "/opt/chipcoin/.venv/bin/chipcoin --network devnet --data /var/lib/chipcoin/follower/node.sqlite3 run --listen-port 18444 --http-port 8081 --peer chipcoinprotocol.com:18444"
```

Verification:

```bash
curl -s http://127.0.0.1:8081/v1/status | jq '{height, tip_hash, sync_phase, handshaken_peer_count}'
/opt/chipcoin/.venv/bin/chipcoin --network devnet --data /var/lib/chipcoin/follower/node.sqlite3 peer-summary | jq
```

### 5. Start snapshot host only mid-cycle

On `chipcom`, export snapshot:

```bash
cd /opt/chipcoin
./scripts/remote-devnet/chipcom/node-a-cli.sh snapshot-export --snapshot-file /tmp/reward-devnet.snapshot
docker cp chipcoin-node-a:/tmp/reward-devnet.snapshot /tmp/reward-devnet.snapshot
```

Copy to snapshot host, then import and start:

```bash
/opt/chipcoin/.venv/bin/chipcoin --network devnet --data /var/lib/chipcoin/snapshot/node.sqlite3 snapshot-import --snapshot-file /tmp/reward-devnet.snapshot
tmux new -d -s chip-node \
  "/opt/chipcoin/.venv/bin/chipcoin --network devnet --data /var/lib/chipcoin/snapshot/node.sqlite3 run --listen-port 18444 --http-port 8081 --peer chipcoinprotocol.com:18444"
```

Verification:

```bash
curl -s http://127.0.0.1:8081/v1/status | jq '{bootstrap_mode, snapshot_anchor_height, height, sync_phase, handshaken_peer_count}'
```

## I. Registration Commands

### `chipcom` reward node A

```bash
export REWARD_A_ADDR="$(/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-address --wallet-file /var/lib/chipcoin/chipcom/wallets/reward-a.json | jq -r .address)"
export REWARD_A_PUB="$(/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-address --wallet-file /var/lib/chipcoin/chipcom/wallets/reward-a.json | jq -r .public_key_hex)"
cd /opt/chipcoin
docker cp /var/lib/chipcoin/chipcom/wallets/reward-a.json chipcoin-node-a:/tmp/reward-a.json
./scripts/remote-devnet/chipcom/node-a-cli.sh register-reward-node \
  --wallet-file /tmp/reward-a.json \
  --node-id reward-node-a \
  --payout-address "$REWARD_A_ADDR" \
  --node-pubkey-hex "$REWARD_A_PUB" \
  --declared-host chipcoinprotocol.com \
  --declared-port 18444 \
  --connect chipcoinprotocol.com:18444 | jq
```

### `tilt` reward node B

```bash
export REWARD_B_ADDR="$(/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-address --wallet-file /var/lib/chipcoin/tilt/wallets/reward-b.json | jq -r .address)"
export REWARD_B_PUB="$(/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-address --wallet-file /var/lib/chipcoin/tilt/wallets/reward-b.json | jq -r .public_key_hex)"
/opt/chipcoin/.venv/bin/chipcoin --network devnet --data /var/lib/chipcoin/tilt/node.sqlite3 register-reward-node \
  --wallet-file /var/lib/chipcoin/tilt/wallets/reward-b.json \
  --node-id reward-node-b \
  --payout-address "$REWARD_B_ADDR" \
  --node-pubkey-hex "$REWARD_B_PUB" \
  --declared-host tiltmediaconsulting.com \
  --declared-port 18444 \
  --connect chipcoinprotocol.com:18444 | jq
```

### `tobia` reward node C

```bash
export REWARD_C_ADDR="$(/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-address --wallet-file /var/lib/chipcoin/tobia/wallets/reward-c.json | jq -r .address)"
export REWARD_C_PUB="$(/opt/chipcoin/.venv/bin/chipcoin --network devnet wallet-address --wallet-file /var/lib/chipcoin/tobia/wallets/reward-c.json | jq -r .public_key_hex)"
/opt/chipcoin/.venv/bin/chipcoin --network devnet --data /var/lib/chipcoin/tobia/node.sqlite3 register-reward-node \
  --wallet-file /var/lib/chipcoin/tobia/wallets/reward-c.json \
  --node-id reward-node-c \
  --payout-address "$REWARD_C_ADDR" \
  --node-pubkey-hex "$REWARD_C_PUB" \
  --declared-host <TOBIA_PUBLIC_DNS_OR_IP> \
  --declared-port 18444 \
  --connect chipcoinprotocol.com:18444 | jq
```

Verify on `chipcom`:

```bash
cd /opt/chipcoin
./scripts/remote-devnet/chipcom/node-a-cli.sh node-registry | jq
```

## J. Comparison Commands

Use the helper from any control machine:

```bash
cd /opt/chipcoin
./scripts/remote-devnet/compare_reward_nodes.sh \
  --epoch-index "$EPOCH" \
  chipcom=http://chipcoinprotocol.com:8081 \
  tilt=http://tiltmediaconsulting.com:8081 \
  tobia=http://<TOBIA_PUBLIC_DNS_OR_IP>:8081 \
  follower=http://<FOLLOWER_PUBLIC_DNS_OR_IP>:8081
```

Add snapshot host later:

```bash
./scripts/remote-devnet/compare_reward_nodes.sh \
  --epoch-index "$EPOCH" \
  chipcom=http://chipcoinprotocol.com:8081 \
  tilt=http://tiltmediaconsulting.com:8081 \
  tobia=http://<TOBIA_PUBLIC_DNS_OR_IP>:8081 \
  follower=http://<FOLLOWER_PUBLIC_DNS_OR_IP>:8081 \
  snapshot=http://<SNAPSHOT_PUBLIC_DNS_OR_IP>:8081
```

## K. Caveats About Stale State

### Stale wallets

- old wallet files are not dangerous by themselves
- but they are confusing in a zero-state devnet test
- regenerate miner/reward wallets for this session

### Stale registrations

- wiping node DBs removes old registry state
- registrations must be submitted again after reset

### Stale snapshots

- do not reuse old snapshot files unless that is intentional
- for this run, delete old snapshots before start
- export a new snapshot from the clean live epoch you are actually testing

### Stale peer state

- `chipcom` bootstrap peerbook is persistent inside compose volumes
- if you want a clean test, use `./scripts/remote-devnet/chipcom/down.sh -v`
- follower/reward node local DB resets also remove peer persistence

### Stale listening processes

- always stop runtime first
- only then remove DB files
- only then verify ports are free

## L. Minimal Expected Start Checks

After each host starts, run:

```bash
curl -s http://127.0.0.1:8081/v1/status | jq '{height, tip_hash, sync_phase, handshaken_peer_count, bootstrap_mode}'
```

After reward registration, on `chipcom` run:

```bash
cd /opt/chipcoin
./scripts/remote-devnet/chipcom/node-a-cli.sh node-registry | jq
```

Before attestation, compare:

```bash
./scripts/remote-devnet/compare_reward_nodes.sh --epoch-index "$EPOCH" ...
```

After attestation submission, compare again.

After epoch close, compare again and inspect:

```bash
cd /opt/chipcoin
./scripts/remote-devnet/chipcom/node-a-cli.sh reward-settlements --epoch-index "$EPOCH" | jq
./scripts/remote-devnet/chipcom/node-a-cli.sh reward-settlement-report --epoch-index "$EPOCH" | jq
```
