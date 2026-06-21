# Security Hardening Notes

This document tracks concrete security hardening items identified during
pre-mainnet review. It is not a professional audit report and should not be
treated as complete coverage. It records known findings, current mitigation
status, and the remaining work needed before any mainnet launch.

## Review Scope

The review covered representative parts of:

- cryptographic helpers
- consensus validation
- special node transaction signing
- P2P transport and framing
- HTTP API exposure
- wallet CLI behavior
- snapshot bootstrap
- browser wallet storage at a high level

Large runtime paths such as `node/runtime.py`, `node/service.py`, and
`node/sync.py` still need deeper review.

## Summary

| Area | Risk | Status | Mainnet Action |
| --- | --- | --- | --- |
| P2P frame length | unauthenticated memory DoS | fixed with 8 MB payload cap | keep tests and tune if block serialization grows |
| Wallet private key output and file mode | local/operational key exposure | fixed | keep tests and avoid expanding private key output |
| Special node transaction signatures | cross-network replay/domain separation | fixed with v2 network domain | keep mainnet v2-only |
| Reward epoch seed | miner grinding bias | v2 multi-block seed scheduled | commit-reveal remains optional future hardening |
| Snapshot trust defaults | accidental trust-on-first-use | fixed with warn defaults | use enforce with pinned keys for mainnet/public bootstrap |
| Snapshot retry loops | bootstrap traffic amplification | fixed | keep server-side monitoring |

## 1. P2P Frame Size Limit

### Finding

`TCPTransport.receive()` reads the fixed frame header, extracts the
payload length from peer-controlled bytes, and then reads that many bytes from
the stream.

Without a maximum payload size, an unauthenticated peer can advertise a very
large frame length and cause the node to wait for and buffer excessive payload
data. This is reachable before any application-level handshake.

### Status

Fixed.

The transport now enforces:

```python
MAX_P2P_FRAME_PAYLOAD_SIZE = 8_000_000
```

The receive path rejects oversized frames before reading the payload. The send
path also refuses oversized outbound frames.

### Rationale

Bitcoin Core uses a hard protocol message limit of roughly 4 MB. Chipcoin's
consensus block weight is currently 4,000,000, so 8 MB is a conservative
operator-safe cap that avoids false positives from serialization overhead while
closing the unbounded allocation surface.

### Tests

`tests/node/test_transport_protocol.py` covers:

- inbound oversized frame is rejected after only the 24-byte header read
- outbound oversized frame is rejected before writing
- existing local handshake and ping/pong protocol tests still pass

### Remaining Work

- Revisit the cap before mainnet if block/message serialization changes.
- Consider separate per-command limits later, for example stricter limits for
  `version`, `addr`, and inventory messages, with the block message allowed to
  use the largest cap.

## 2. Wallet Private Key Exposure

### Finding

Wallet JSON files contain `private_key_hex` in clear text. This is expected for
the current lightweight CLI wallet model, but two behaviors were unsafe:

- wallet files inherit the process umask and are not explicitly chmodded to
  owner-only permissions
- `wallet-address` prints the full formatted wallet record, including
  `private_key_hex`

This can leak keys through shell scrollback, terminal recordings, CI logs,
command pipelines, or local multi-user filesystem permissions.

### Status

Fixed.

### Implementation

- Wallet files are written through a temporary file, chmodded to `0600`, then
  atomically moved into place.
- `wallet-address` prints only `address`, `public_key_hex`, and `compressed`.
- `wallet-generate` and `wallet-import` still print `private_key_hex`, because
  those commands intentionally create or import key material, but now emit a
  stderr warning.
- CLI tests assert owner-only wallet file permissions and verify that
  `wallet-address` does not expose `private_key_hex`.

### Compatibility

This is not consensus-affecting. It is a CLI behavior change and may be mildly
breaking for scripts that previously parsed `private_key_hex` from
`wallet-address`.

## 3. Special Node Transaction Domain Separation

### Finding

`special_node_transaction_signature_digest()` signs only transaction metadata
fields such as kind, node id, payout address, owner pubkey, declared host, and
declared port.

The digest does not include a network or chain domain. Because the address
format is not currently network-specific, a signed special node transaction
from one network could be replayed on another network if the rest of the
metadata is valid there.

This affects special node transactions such as:

- `register_node`
- `renew_node`
- `register_reward_node`
- `renew_reward_node`

### Status

Fixed.

### Implementation

Special node owner signatures now support a v2 signing domain:

```text
chipcoin:special-node-tx:v2:<network>
```

The signed v2 payload reuses all fields covered by the legacy v1 digest and
adds the network through the domain prefix. When v2 is active for the target
network height, builders add:

- `owner_signature_version=v2`
- `owner_signature_network=<network>`

CLI and runtime builders pass the configured node network and next block
height, so new
`register_node`, `renew_node`, `register_reward_node`, and `renew_reward_node`
transactions are bound to the intended chain.

### Compatibility

Consensus-affecting, implemented as a scheduled non-mainnet upgrade:

- mainnet validation requires v2 signatures from genesis
- devnet/testnet require legacy v1 signatures before height `11111`
- devnet/testnet require v2 signatures from height `11111`
- devnet/testnet v2 signatures must match the active network and cannot be
  replayed across those networks

## 4. Reward Epoch Seed Grinding

### Finding

The reward epoch seed is derived from the previous epoch closing block hash and
the epoch index. A miner who finds that closing block can try multiple valid
block variants and choose a hash that biases the next epoch's verifier
committee or check-window assignment.

This is a classic limitation of randomness derived from a single block hash.

### Status

Implemented as a scheduled consensus upgrade.

- legacy v1 remains valid for existing devnet/testnet history
- devnet/testnet switch to v2 at epoch `112` (height `11200` with 100-block
  epochs), the first epoch boundary after the special-node signature v2 height
  `11111`
- mainnet uses v2 from genesis
- v2 derives from up to 16 final block hashes from the previous epoch, not only
  the closing block
- v2 is domain-separated as `chipcoin:reward-epoch-seed:v2:<network>`

This does not eliminate grinding by a miner controlling many of the sampled
blocks, but it removes the single-closing-block control point and makes biasing
the next epoch materially harder.

### Future Option

Stronger hardening remains possible:

- add commit-reveal from reward nodes or verifiers
- define liveness/fallback rules when some commits or reveals are missing

### Compatibility

Consensus-affecting.

The multi-block seed is intentionally activated on an epoch boundary so all
nodes compute the same assignments and settlement seed for the full epoch. A
commit-reveal design gives stronger bias resistance but adds more protocol
surface and is not required before testnet continues.

## 5. Snapshot Trust Defaults

### Finding

The snapshot import path supports:

- `off`
- `warn`
- `enforce`

Snapshot import supports explicit `off` for local testing, but public/operator
paths should not silently accept unsigned or untrusted snapshots.

### Status

Fixed for default behavior.

The setup wizard, CLI snapshot import, CLI `run --snapshot-file`, and Docker
entrypoint default to `warn`. Weak trust conditions continue only with an
explicit warning. Operators can still choose `off` deliberately for local
testing, and can choose `enforce` when trusted signer keys are configured.

### Mainnet Guidance

For mainnet:

- make public bootstrap documentation use `enforce`
- publish and pin known snapshot signer public keys
- prefer `enforce` once pinned keys are available in the release profile
- refuse `enforce` without configured trusted signer keys

For testnet:

- `warn` is the default for convenience, but operator docs should clearly show
  `enforce` for stronger validation.

### Compatibility

Not consensus-affecting. It changes bootstrap UX and deployment defaults.

## 6. Snapshot Bootstrap Retry Loops

### Finding

Some nodes repeatedly downloaded `latest.manifest.json` and the same snapshot
file every few seconds, sometimes concurrently from the same IP. This can create
unnecessary server load and hides the real reason bootstrap is failing.

### Status

Fixed.

The Docker entrypoint now:

- applies persistent exponential backoff after manifest/download/import/validation
  failures
- writes the exact retry reason to logs and the retry marker
- reuses a successfully downloaded local snapshot when checksum/marker metadata
  match
- uses a local bootstrap lock to prevent concurrent snapshot bootstrap attempts
- cleans up stale locks after a configurable timeout
- writes restore metadata for successful snapshot imports
- skips all snapshot work when the node database is already initialized and
  valid

### Operational Checks

On a node with a valid database, startup should log:

```text
Snapshot bootstrap skipped mode=auto reason=node_database_already_initialized
```

Repeated manifest/snapshot requests from the same IP should not occur after the
node has pulled the fixed entrypoint and restarted.

## Recommended Pre-Mainnet Order

1. Keep the P2P frame cap and test coverage in place.
2. Fix wallet output and file permissions.
3. Set safe snapshot trust defaults for public/mainnet paths.
4. Harden reward epoch seed derivation.
5. Run a dedicated review of node runtime, sync, mempool pressure, and peer
   misbehavior handling.

## Notes For Operators

- Expose only the P2P port publicly.
- Keep raw node HTTP bound to localhost or behind a controlled reverse proxy.
- Treat wallet JSON files as private keys.
- Prefer signed/enforced snapshot imports for any serious environment.
- Monitor snapshot downloads and bootstrap announce/list-peers request rates for
  retry loops or misconfigured nodes.
