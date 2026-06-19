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
| Special node transaction signatures | cross-network replay/domain separation | open, consensus-affecting | add v2 signature domain before mainnet |
| Reward epoch seed | miner grinding bias | open, consensus-affecting | harden before mainnet reward economics are final |
| Snapshot trust defaults | accidental trust-on-first-use | partially mitigated | use warn/enforce defaults for public/mainnet paths |
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

Open.

### Recommended Fix

Introduce a v2 signing domain, for example:

```text
chipcoin:<network>:special-node-tx:v2
```

Include the domain in the signed digest. Also include an explicit
`signature_version` or equivalent metadata so validation can distinguish old and
new signatures during migrations.

### Compatibility

Consensus-affecting.

For mainnet, start directly with v2 only. For existing testnet, either:

- activate v2 at a future height and accept v1 only before that height; or
- treat the testnet migration as a reset/re-registration event.

## 4. Reward Epoch Seed Grinding

### Finding

The reward epoch seed is derived from the previous epoch closing block hash and
the epoch index. A miner who finds that closing block can try multiple valid
block variants and choose a hash that biases the next epoch's verifier
committee or check-window assignment.

This is a classic limitation of randomness derived from a single block hash.

### Status

Open.

### Recommended Fix Options

Simple hardening:

- derive the seed from multiple recent block hashes instead of one closing
  block
- domain-separate the seed version, for example `reward-epoch-v2`
- activate at a known height/epoch

Stronger hardening:

- add commit-reveal from reward nodes or verifiers
- define liveness/fallback rules when some commits or reveals are missing

### Compatibility

Consensus-affecting.

The simple multi-block seed is easier to implement and test before mainnet. A
commit-reveal design gives stronger bias resistance but adds more protocol
surface.

## 5. Snapshot Trust Defaults

### Finding

The snapshot import path supports:

- `off`
- `warn`
- `enforce`

The setup wizard defaults public testnet configuration to `warn`, but lower
level CLI and entrypoint defaults still fall back to `off` when no explicit
configuration is provided.

### Status

Partially mitigated.

The public testnet wizard path is safer than raw defaults, but the low-level
defaults still permit unsigned/unverified snapshot import.

### Recommended Fix

For mainnet:

- make public bootstrap documentation use `enforce`
- publish and pin known snapshot signer public keys
- consider defaulting mainnet snapshot import to `warn` or `enforce`
- refuse `enforce` without configured trusted signer keys

For testnet:

- `warn` is acceptable for convenience, but operator docs should clearly show
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
4. Add special node transaction signature domain separation.
5. Harden reward epoch seed derivation.
6. Run a dedicated review of node runtime, sync, mempool pressure, and peer
   misbehavior handling.

## Notes For Operators

- Expose only the P2P port publicly.
- Keep raw node HTTP bound to localhost or behind a controlled reverse proxy.
- Treat wallet JSON files as private keys.
- Prefer signed/enforced snapshot imports for any serious environment.
- Monitor snapshot downloads and bootstrap announce/list-peers request rates for
  retry loops or misconfigured nodes.
