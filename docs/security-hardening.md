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
| HTTP submit body size | local/API memory or CPU DoS before validation | fixed with per-route request caps | keep HTTP private or behind a controlled proxy |
| HTTP diagnostic list size | large peerbook/mempool responses can amplify exposed API cost | fixed with pagination caps | keep raw node HTTP private and expose only intentional public APIs |
| Mempool admission ordering | avoidable CPU/DB pressure before policy rejection | fixed with cheap preflight checks | continue peer-level relay throttling review |
| Non-standard tx relay spam | repeated costly invalid tx validation from one peer | fixed with stronger policy-failure penalties and structured logs | keep tuning thresholds from testnet telemetry |
| Repeated getdata misses | peer can repeatedly request unavailable inventory | fixed with per-session miss tracking, logs, and penalties | tune thresholds from live sync telemetry |
| Duplicate getdata entries | peer can force duplicate object service work in one request | fixed with per-request dedupe, light penalty, and logs | keep telemetry for false positives |
| P2P payload decoding | malformed short payloads could raise low-level decode errors | fixed with explicit bounds checks | keep malformed-frame tests for every typed payload |
| P2P collection sizes | valid frames could carry excessive decoded collections | fixed with codec and runtime count caps | review caps if protocol inventory/header needs grow |
| Runtime log amplification | noisy peers can flood startup/sync logs with repetitive benign events | partially fixed with summarized alias logs and quiet mining-status polling | continue reducing low-signal 200 OK logs without hiding errors |
| Post-quantum transaction support | consensus split, dependency divergence, CPU DoS, or misleading claims before audit | architecture and cheap structural checks added for testnet | pin one ML-DSA-44 backend, freeze vectors, and complete audit before activation |

## Traceability

Recent hardening commits:

- `adf242c` - reject oversized P2P frames before payload reads
- `4c23fce` - harden wallet key output and file permissions
- `c4afa0f` - add special node transaction signature v2 domain separation
- `f090dba` - default snapshot trust to warning mode
- `87b4d8e` - harden reward epoch seed derivation
- `1bed9cb` - bound P2P locator request handling
- `bf6455f` - bound HTTP submit request handling
- `2f51158` - add mempool admission preflight
- `167bcbe` - strengthen non-standard transaction relay penalties/logging
- `9d91d6f` - improve peer misbehavior logs
- `285410e` - track repeated `getdata` misses
- `a34c85e` - paginate HTTP diagnostic lists
- `6d62eac` - harden truncated P2P payload decoding
- `6c55c4c` - cap decoded P2P collection sizes
- `061ac36` and `ded7c35` - quiet successful mining-status polling logs
- `6abd480` - summarize peer alias cleanup logs
- `e800c42` - deduplicate duplicate `getdata` inventory requests

## 0a. Post-Quantum Testnet Support

### Finding

Adding CHCQ post-quantum addresses changes UTXO ownership and spending rules.
It does not change mining, PoW hashes, block hashes, txids, Merkle roots, or
block format. The security risks are concentrated in address parsing,
transaction versioning, signature verification, dependency choice, and public
wording.

### Status

Architecture added for testnet/devnet only:

- `CHCQ` parses before `CHC`
- CHCQ payload version is fixed at `0x50`
- CHCQ public-key commitments use `SHA3-256`
- transaction v1 serialization remains byte-identical
- transaction v2 carries per-input `sig_scheme_id`
- v2 signatures include `chipcoin:tx-signature:v2:<network>`
- ML-DSA-44 public key/signature sizes are checked before verifier calls

### Remaining Work

- Pin one consensus ML-DSA-44 backend across all node builds.
- Add official FIPS 204 KAT coverage for the selected backend.
- Freeze v2 transaction/signature vectors before activation.
- Keep browser PQ signing disabled until CLI CHCQ spends verify on the node
  backend.
- Public wording must say "post-quantum support in testnet", "experimental",
  "not audited yet", and "designed for future quantum-resistance"; do not call
  this "quantum-proof mainnet".

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
- Runtime P2P handlers also bound peer-controlled `getheaders`/`getblocks`
  locator counts so malicious peers cannot force unbounded locator scans.

## 1a. P2P Payload Decoding Bounds

### Finding

Some typed P2P payload decoders assumed enough bytes were available for fixed
width integer fields. Malformed short payloads were rejected, but some paths
could surface lower-level `struct.error` exceptions instead of a controlled
protocol/codec error.

This is not a consensus bug, but explicit bounds are preferable for hostile
input because they make failures predictable, testable, and easier to log.

### Status

Fixed.

The binary codec now checks fixed-width reads before unpacking. Truncated
payloads are rejected through `CodecError`/malformed-message handling instead
of leaking implementation exceptions.

### Tests

`tests/node/test_codec.py` covers truncated payloads for fixed-width fields and
ensures malformed frames fail cleanly.

## 1b. P2P Decoded Collection Size Caps

### Finding

The transport frame cap prevents unbounded byte reads, but valid frames can
still encode large logical collections. If unchecked, inventory, locator,
headers, or address lists can force unnecessary allocation and CPU before
runtime policy handles the message.

### Status

Fixed.

The codec and runtime now enforce bounded collection sizes:

```python
MAX_INVENTORY_ITEMS = 500
MAX_LOCATOR_HASHES = 64
MAX_HEADERS = 2000
MAX_ADDR_RECORDS = 1000
```

Runtime handlers also close or penalize peers that exceed protocol limits in
bounded request paths.

### Tests

`tests/node/test_codec.py`, `tests/node/test_local_node.py`, and
`tests/node/test_runtime_integration.py` cover oversized inventory, locator,
headers, and chunked `getdata` behavior.

## 1c. HTTP Submit Request Size Limits

### Finding

The node HTTP API is intended to be localhost/operator-facing, but its submit
paths still process peer- or client-controlled bodies. Before hardening,
`_read_json()` trusted `CONTENT_LENGTH` and read that many bytes without a
maximum. `POST /v1/tx/submit` and `POST /mining/submit-block` then passed
`raw_hex` fields into transaction or block deserialization without an API-level
size check.

If the HTTP API is accidentally exposed, or if a reverse proxy forwards
untrusted traffic to it, a client could force excessive memory allocation or
expensive parsing before normal mempool/block validation policy runs.

### Status

Fixed.

The HTTP API now applies bounded JSON body reads and pre-deserialization hex
field caps:

```python
TX_SUBMIT_JSON_BODY_MAX_BYTES = 262_144
TX_SUBMIT_RAW_HEX_MAX_CHARS = 200_000
BLOCK_SUBMIT_JSON_BODY_MAX_BYTES = 17_000_000
BLOCK_SUBMIT_RAW_HEX_MAX_CHARS = 16_000_000
```

Malformed `CONTENT_LENGTH` values return `400 Bad Request`; oversized request
bodies or submit fields return `413 Payload Too Large`.

### Compatibility

This is not consensus-affecting. The block submit cap is sized to allow a full
serialized block up to the current 8 MB transport payload cap plus JSON
overhead. The transaction submit cap is intentionally far above normal wallet
transactions but below unbounded memory/CPU abuse.

### Tests

`tests/node/test_http_api.py` covers:

- oversized transaction submit body rejected before the tx handler
- oversized raw transaction hex rejected before the tx handler
- oversized block submit body rejected before the mining handler
- malformed `CONTENT_LENGTH` rejected as a client error

## 1d. HTTP Diagnostic Pagination

### Finding

Diagnostic list endpoints are operator-facing, but if node HTTP is accidentally
published or proxied, large peerbook or mempool responses can amplify request
cost and bandwidth use.

### Status

Fixed.

`GET /v1/mempool` and `GET /v1/peers` now apply bounded pagination:

```text
/v1/mempool?limit=<1..1000>&offset=<0..100000>
/v1/peers?limit=<1..1000>&offset=<0..100000>
```

Default response sizes are capped at 100 mempool entries and 200 peer records.
Oversized limits return `400 Bad Request` and are logged by the HTTP request
logger with the rejected path and status.

### Compatibility

This is not consensus-affecting. Clients that need full diagnostics can page
through results explicitly instead of relying on unbounded responses.

### Tests

`tests/node/test_http_api.py` covers default limits, offset paging, rejected
oversized limits, and unchanged peer-summary aggregation.

## 1e. Mempool Admission Preflight

### Finding

Mempool policy already capped transaction size, input count, output count, and
output standardness. Some of those checks, however, ran after the mempool built
an overlay UTXO view and invoked contextual transaction validation.

That ordering is safe for correctness but inefficient under spam: transactions
that are obviously non-standard can still force more CPU and repository work
than necessary before being rejected.

### Status

Fixed.

The mempool manager now runs a cheap preflight policy before contextual
validation:

- serialized transaction size
- input count
- output count
- positive output values
- output address standardness

Raw transaction submission also rejects serialized payloads above mempool policy
before deserializing.

### Compatibility

This is not consensus-affecting. Blocks may still be validated by consensus
rules; these checks only decide what the local node stores and relays from its
mempool.

### Tests

`tests/node/test_local_node.py` covers:

- pre-validation policy failures do not build a validation context
- oversized raw transaction hex is rejected before transaction deserialization

## 1f. Non-Standard Transaction Relay Penalties

### Finding

Invalid transaction relays were already penalized, but all non-benign invalid
transactions used the same small penalty. That is appropriate for contextual
failures that may occur during normal network races, but it is too weak for
clearly non-standard relays such as oversized transactions, invalid output
addresses, coinbase transactions in mempool, or excessive input/output counts.

### Status

Fixed.

The runtime now gives high-signal mempool policy failures a stronger
misbehavior delta:

```python
_NON_STANDARD_TX_MISBEHAVIOR_DELTA = 25
```

With the default thresholds, two such relays reach the disconnect threshold and
four reach the temporary ban threshold. Benign duplicate/known transaction
relays remain unpenalized, and contextual invalid transaction failures still use
the lower penalty.

Misbehavior logs now include the observed endpoint, remote `node_id` when known,
direction, handshake state, protocol error class, score delta, accumulated
score, action, `ban_until`, and the triggering error. Non-benign transaction
relay failures also log txid, tx type, reason, penalty, and action in a
single operator-readable line.

### Compatibility

This is not consensus-affecting. It only affects local peer scoring and relay
behavior for peers that repeatedly send non-standard mempool transactions.

### Tests

`tests/node/test_local_node.py` covers the stronger relay penalty
classification and verifies that misbehavior logs include peer identity and the
resulting action.

## 1g. Repeated Getdata Miss Tracking

### Finding

Inbound `getdata` requests were bounded by item count, but a peer could
repeatedly ask for inventory the node cannot serve. A single miss can be normal
under network races, but repeated fully unserved requests are useful signal for
bad peer behavior and should be visible in logs.

### Status

Fixed.

The runtime now tracks a per-session `getdata_miss_count`. A request that is at
least partially served resets the count. Repeated fully unserved requests are
logged and, after the threshold, penalized:

```python
_GETDATA_MISS_PENALTY_THRESHOLD = 3
```

The log includes peer identity, requested/served counts, miss count, threshold,
first requested block hash, penalty, and action.

### Compatibility

This is not consensus-affecting. It only scores peers that repeatedly request
inventory unavailable to the local node.

### Tests

`tests/node/test_local_node.py` covers repeated `getdata` misses, verifies the
log line, and asserts that the penalty is applied at the configured threshold.

## 1h. Duplicate Getdata Entry Deduplication

### Finding

Inbound `getdata` requests were bounded by item count, but a peer could include
the same inventory vector repeatedly in one request. If the object is available,
the node would serve it repeatedly and the logs would only show aggregate
requested/served counts.

This is cheap for an attacker and noisy for operators, especially when peers
ask for the same block or transaction many times in one frame.

### Status

Fixed.

The runtime now deduplicates `getdata` inventory within a single request before
serving blocks or transactions. Duplicate entries trigger a light peer penalty
and an explicit log:

```text
duplicate getdata requests peer=<endpoint>/<node_id> duplicate_items=<n> unique_items=<n> penalty=1 action=<action>
```

The normal service log also includes `duplicate_items=<n>` so operators can
correlate served work with duplicate request behavior.

### Compatibility

This is not consensus-affecting. It only avoids duplicate local work and scores
peers that send redundant request entries.

### Tests

`tests/node/test_local_node.py` verifies that duplicate block requests produce
only one served `block` response, apply the light penalty, and emit the
structured duplicate log.

## 1i. Runtime and HTTP Log Amplification Controls

### Finding

Some benign but frequent events created excessive operational log noise:

- mining status polling every few seconds from the local miner
- successful WSGI access logs for `GET /mining/status`
- repeated per-alias cleanup logs during inbound peer canonicalization

High-volume low-signal logs make it harder to spot malicious behavior such as
invalid relay, repeated unavailable `getdata`, duplicate inventory, retry
loops, or protocol-limit disconnects.

### Status

Partially fixed.

Implemented changes:

- successful `/mining/status` HTTP application logs are downgraded to debug
- successful `/mining/status` WSGI access logs are suppressed
- peer alias cleanup logs are summarized as one line with `count`,
  `first_alias`, `last_alias`, and `canonical`

Errors and non-200 responses remain visible. Other operational endpoints such
as `/v1/status` still log normally.

### Tests

`tests/node/test_http_api.py` covers quiet successful mining-status logs while
preserving error visibility. `tests/node/test_local_node.py` verifies summarized
peer alias cleanup logging.

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
