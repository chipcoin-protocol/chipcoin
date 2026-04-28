# Setup Wizard

## Purpose

The setup wizard is a guided way to create a local `.env`, prepare runtime paths, and initialize the public Chipcoin devnet stack without editing every setting by hand.

Run it from the repository root:

```bash
python3 scripts/setup/wizard.py
```

The wizard writes a local `.env` in the repository root. It does not change the protocol, and it does not modify public defaults in the repository.

The wizard is now Docker-first:

- it validates that the repository `docker-compose.yml` exists
- it prepares the runtime files that the compose stack actually mounts
- it prepares the node database before the first `docker compose up`
- it does not start services automatically
- it ends by printing the exact commands the operator should run next
- it can now prepare either a passive node or a reward-participating node

By default, the generated runtime paths point to `/var/lib/chipcoin`. On a fresh Linux host, the wizard can prepare that runtime directory with `sudo` during setup when needed.

## When To Use It

Use the wizard when:

- you want the fastest path from clone to running services
- you want guided prompts for wallet creation or import
- you want `.env` generated with a consistent runtime layout

Prefer the manual setup flow from `README.md` when:

- you want full control over every `.env` value
- you are reviewing all runtime paths explicitly
- you are integrating Chipcoin into an existing operator setup

## Setup Modes

### Quick Start

This mode uses the public devnet defaults when `devnet` is selected:

- node endpoint: `https://api.chipcoinprotocol.com`
- bootstrap peer: `chipcoinprotocol.com:18444`
- explorer URL: `https://explorer.chipcoinprotocol.com`

This is the shortest path if you want to connect quickly to the public devnet environment.

Public devnet endpoints are provided for convenience and may change or become unavailable.

When `testnet` is selected, quick mode is intentionally local/manual only:

- node endpoint: `http://127.0.0.1:28081`
- P2P port: `28444`
- bootstrap peer: empty
- snapshot manifest URL: empty
- explorer URL: empty

There is no public testnet bootstrap, snapshot publisher, faucet, or explorer in
this repository step. See `docs/testnet-launch.md` for the manual dry-run flow.

### Custom Configuration

This mode prompts for:

- node endpoint
- startup peer or peers
- explorer URL

Use it when you want guided setup but do not want the public defaults.

### Local/Self-Hosted

This mode writes local-first defaults:

- node endpoint: `http://127.0.0.1:8081`
- bootstrap peer: empty
- explorer URL: empty

Use it when you want a local node/miner stack without depending on public bootstrap or public inspection endpoints.

## Public Reachability Note

After you choose your node setup, keep this practical distinction in mind:

- outbound-only nodes can still connect to the network and sync
- publicly reachable nodes are strongly preferred for network health
- when possible, open and forward the selected network P2P port so other peers can reach your node
- devnet uses `TCP 18444`; testnet dry-runs use `TCP 28444`

The wizard does not require public exposure, but public reachability is the main way an operator contributes an additional resilient peer to the mesh.

## Node Bootstrap Modes

When the wizard configures a node, it now asks how the node should bootstrap:

- `full`
  - start from genesis
  - no snapshot manifest fetch
- `snapshot`
  - require a compatible snapshot manifest and snapshot download
  - verify checksum
  - verify snapshot signature according to the chosen trust mode
  - import snapshot into the node database
  - fail explicitly if any snapshot step fails
- `auto`
  - prefer snapshot bootstrap
  - if manifest fetch, snapshot download, checksum verification, signature verification, or import fails, fall back to full sync

For public devnet setups, the default manifest is:

- `https://chipcoinprotocol.com/downloads/snapshots/devnet/latest.manifest.json`

For testnet dry-runs, the wizard leaves snapshot manifest URLs empty and defaults
to full sync unless the operator explicitly provides a compatible testnet
manifest.

The user can:

- press Enter to accept the default official manifest URL
- provide one or more custom manifest URLs

If multiple manifest URLs are configured, the wizard tries them in order until one yields a compatible snapshot.

The manifest can advertise one or more snapshots. The wizard selects the latest compatible snapshot for the configured network.

The wizard stores these node bootstrap settings in `.env`:

Operational wizard inputs:

- `NODE_BOOTSTRAP_MODE`
- `NODE_SNAPSHOT_MANIFEST_URLS`
- `NODE_SNAPSHOT_FILE`
- `NODE_SNAPSHOT_TRUST_MODE`
- `NODE_SNAPSHOT_TRUSTED_KEYS_FILE`

Audit/debug fields:

- `NODE_SNAPSHOT_SELECTED_URL`
- `NODE_SNAPSHOT_SELECTED_HEIGHT`
- `NODE_SNAPSHOT_SELECTED_HASH`

Important:

- these snapshot-related `.env` keys are not consumed by the running node container
- they exist for wizard input and audit/debug visibility only
- the running node relies on the database state mounted from `NODE_DATA_PATH`
- after the wizard finishes, the database is the single source of truth

Trust handling follows the same snapshot trust modes supported by the node CLI:

- `off`
- `warn`
- `enforce`

In `warn` mode, the wizard continues but prints explicit warnings when:

- the snapshot is unsigned
- the signature is invalid
- the signer is not trusted
- the snapshot is old enough that post-anchor delta sync may be large

In `auto` mode, any snapshot bootstrap failure falls back to `full`.
In `snapshot` mode, the wizard exits with a clear error instead.

The wizard also guarantees clean first-run state:

- `full`
  - leaves the node database empty and ready for normal first start
- `snapshot`
  - imports the selected snapshot into `NODE_DATA_PATH` before first start
  - fails hard if manifest fetch, download, checksum verification, signature verification, or import fails
- `auto`
  - attempts snapshot bootstrap first
  - if anything fails, resets the node database back to a clean empty file and falls back to `full`

No half-imported node database should remain after an `auto` fallback.

## Wallet Handling

If you run `miner` or `both`, the wizard also offers:

- `Generate new wallet`
- `Import existing private key`

The wallet file is written to the configured runtime directory, not intended for version control.

If you run `node` or `both`, the wizard now also asks whether the node should be:

- a passive full node
- a reward node that will later register on-chain

If reward-node mode is selected, the wizard also:

- creates or imports a reward-node wallet
- writes `REWARD_NODE_AUTO_*` values into `.env`
- asks for the declared reward-node host and port
- reminds the operator that CHC is required only for reward registration and renewal, not for ordinary full-node operation
- suggests the devnet faucet or another devnet funding source
- prints a ready-to-run registration command for after the wallet is funded

## Output

The wizard writes:

- `.env` in the repository root
- runtime data file paths under the configured runtime directory
- miner wallet file under the configured runtime directory when needed
- reward-node wallet file under the configured runtime directory when reward-node mode is selected

The wizard does not create:

- browser wallet extension state
- explorer browser runtime overrides
- a mandatory bootstrap dependency

Bootstrap remains optional. If you later run with a healthy persisted peerbook or manually configured peers, bootstrap is no longer required for normal operation.

For clean installs, prefer multiple known-good startup peers when you have them. The wizard now writes:

- `NODE_DIRECT_PEERS` for the node
- `MINING_NODE_URLS` for the miner
- legacy shared `DIRECT_PEERS` and `DIRECT_PEER` stay empty unless you choose to use one shared fallback

Wizard defaults by operator mode:

- `node` + `miner` on one host
  - node uses the public devnet peer
  - miner uses `http://node:8081`
- testnet dry-run
  - node starts isolated unless manual peers are provided
  - miner uses `http://node:28081` inside the same Compose project
- miner-only host
  - miner uses `https://api.chipcoinprotocol.com`
- local/self-hosted node + miner
  - node starts isolated
  - miner uses `http://node:8081`

Practical rule:

- if the wizard is configuring both `node` and `miner` on the same host, `MINING_NODE_URLS` points at the local node service name
- if the wizard is configuring `miner` only, `MINING_NODE_URLS` points at the remote authoritative node API

Snapshot bootstrap rule:

- if the wizard is configuring a node and `NODE_BOOTSTRAP_MODE` is `snapshot` or `auto`, it downloads and imports the selected snapshot into `NODE_DATA_PATH` before the first node start
- after that, the node still connects to peers and delta-syncs from the snapshot anchor to the current tip

## What The Wizard Prepares

Operationally, the wizard prepares:

- `.env`
- the node SQLite file at `NODE_DATA_PATH`
- the miner wallet file when `miner` or `both` is selected
- the downloaded snapshot cache file at `NODE_SNAPSHOT_FILE` when snapshot bootstrap succeeds
- the node database content itself when snapshot bootstrap succeeds
- a small audit file next to the node DB when snapshot bootstrap succeeds:
  - `<NODE_DATA_PATH>.snapshot.meta.json`

The wizard does not:

- start containers
- modify `docker-compose.yml`
- create extra YAML configuration files
- change consensus or network behavior
- move snapshot logic into container startup

## Preflight Validation

Before writing `.env`, the wizard validates:

- the repository `docker-compose.yml` exists
- the selected role is valid
- the runtime parent directories exist or can be created
- the node database path is writable for node roles
- the snapshot cache path is writable for snapshot or auto modes
- the manifest URL list is syntactically valid
- the trusted keys file exists when required
- miner roles have at least one mining node endpoint

If preflight fails, the wizard exits before leaving an invalid installation behind.

## Runtime Contract

The current design is explicit:

- snapshot bootstrap is an installation-time optimization
- the wizard performs snapshot selection, download, verification, and import
- the node container does not read snapshot manifest or trust settings from `.env`
- at runtime, the node only uses:
  - the mounted SQLite DB from `NODE_DATA_PATH`
  - normal compose/network environment for P2P and HTTP

If you want to re-bootstrap from a different snapshot later, do one of these:

- rerun the wizard
- replace the node DB manually and restart the container

After the wizard completes, the normal next step is:

```bash
docker compose up -d node
docker compose logs -f node
docker compose logs -f miner
docker compose down
```

For a clean devnet restart that preserves wallets but resets chain state using the current `.env`, use:

```bash
bash scripts/runtime/reset-chain.sh
```

Expected first-start logs:

- `full`
  - `bootstrap_mode=full`
  - sync starts from the local empty database and catches up from genesis
- `snapshot`
  - `bootstrap_mode=snapshot`
  - startup begins at or near `snapshot_anchor_height`
  - only the post-anchor delta should sync if the remote tip is newer
