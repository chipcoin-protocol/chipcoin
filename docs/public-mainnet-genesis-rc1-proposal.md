# Public Mainnet Genesis and RC1 Proposal

Date: 2026-10-19. Status: **proposal only; genesis freeze and deployment are
not authorized**. MemPalace was consulted; it contains no later approved
timestamp or launch-date decision. The final consensus audit is
`docs/public-mainnet-final-consensus-audit-rc1-preparation.md`.

## Candidate identity

| Field | Proposed value |
| --- | --- |
| Network profile | `mainnet` |
| Chain ID | `chipcoin-mainnet-1` |
| P2P magic | `c0897c0d`, first four bytes of SHA-256 of `chipcoin:p2p-magic:chipcoin-mainnet-1` |
| Header version | 1 |
| Previous hash | 32 zero bytes |
| Timestamp candidate | `2026-10-19T08:00:00Z` / `1792396800` |
| Initial bits | `0x1d1399ad` / `487823789` |
| Genesis transaction version | 1 |
| Genesis metadata | sorted keys `chain_id`, `coinbase=true`, `genesis_message`, `height=0` |
| Message | `Die Welt ist alles, was der Fall ist.` (exactly 37 UTF-8 bytes) |
| Inputs / outputs | 0 / 0 |
| Genesis reward / spendable supply | 0 / 0 chipbits |
| TXID / Merkle root | `6ec15ed32ddd62c6134b0c867c33f8fa72ba265b4551d327a57b63721cf34c77` |
| Nonce | `358646568` |
| Candidate block hash | `000000049b99a576c7f281945b3a1faad26161bd828ee6a81e3772b2844565ce` |
| Serialized block SHA-256 | `2a107f6aa36e1ff424aa3247dc4a1171069c890c79b1ef2dcf7af379bd2b045e` |

Candidate artifacts and `SHA256SUMS` are in
`/tmp/public-mainnet-genesis-proposal-20261019T080000Z/`. All three file
checksums pass. The artifact directory is explicitly a candidate workspace;
it is not an embedded, signed, or published identity.

The timestamp is not inherited from TEST-ONLY. It was selected as a candidate
for this work session and the artifact finished at 08:24 UTC, about 24 minutes
later. It is valid as a serialization and PoW candidate, but is **not approved
and not recommended for freeze without an approved launch schedule**. The
first retarget at candidate height 1000 uses the elapsed
time from genesis to block 999 against a 600,000-second target and clamps the
adjustment to 1/4..4. A long private delay therefore changes the first retarget.
The founder must choose one of two explicit launch policies:

1. freeze the timestamp close to the start of the continuously maintained
   canonical chain, accepting that its pre-public blocks are public-mainnet
   history; or
2. complete pre-freeze validation with disposable candidates, then approve and
   mine the definitive genesis close to public exposure, followed by a tightly
   scheduled final identity/runtime validation.

The second policy avoids an old timestamp and pre-public economic history, but
requires final identity-dependent tests in the launch window. This report
recommends policy 2. A candidate hash does not authorize either policy.

## Canonical construction

`build_genesis_transaction` serializes transaction version 1, zero inputs,
zero outputs, locktime zero and metadata sorted by key. Strings are UTF-8 with
canonical varint lengths. TXID is double-SHA256 of those bytes. With one
transaction, the Merkle root equals the TXID. The 80-byte header serializes
little-endian version/timestamp/bits/nonce around the raw 32-byte previous and
Merkle hashes. The block hash is double-SHA256 of the header, interpreted
big-endian for target comparison. The lowest valid uint32 nonce is selected in
ordered batches, so worker count cannot change the result.

The approved final run is:

```bash
.venv/bin/python scripts/build-public-mainnet-genesis.py \
  --timestamp APPROVED_UNIX_TIMESTAMP \
  --workers 2 \
  --output-dir /secure/genesis-primary \
  --acknowledge-founder-approved-timestamp
```

Repeat from a clean checkout and preferably another host with a different
worker count, then run:

```bash
.venv/bin/python scripts/verify-public-mainnet-genesis-independent.py \
  /secure/genesis-primary --verify-lowest-nonce --nonce-workers 2
sha256sum -c /secure/genesis-primary/SHA256SUMS
diff -ru /secure/genesis-primary /secure/genesis-secondary
```

The candidate was mined by the canonical builder with 2 workers in about 24
minutes. The independent verifier imports no Chipcoin module. It reparses
bytes with the standard library and independently checks header/transaction
fields, metadata, TXID, Merkle root, PoW, block hash, zero supply, manifest and
checksums. `--verify-lowest-nonce` independently scans every lower nonce with
standard-library SHA-256; the 2026-10-19 candidate scan passed with two workers
and reported no lower valid nonce. The builder's worker-count determinism is separately
tested against serial search using an easy-PoW fixture. A final freeze also
requires two generated directories to be byte-identical. For reproducible
package builds, derive `SOURCE_DATE_EPOCH` from the frozen source commit, not
from the genesis timestamp.

## Identity consumers

The reviewed block hex/hash must be embedded in `consensus/genesis.py` and
flow through `config.py`. Full node startup installs or verifies it against an
empty/existing DB; P2P handshakes bind chain ID and genesis; snapshots bind
network/chain/genesis; API status exposes all three. Miner startup verifies API
network, chain and genesis. CLI/reward signing binds chain ID and checks API
identity. Browser wallet `canonicalGenesisHash` must replace `null` and remain
fail-closed. The authoritative Chipcoin Central Explorer must pin the same
identity. Docker image labels, RC manifest, chipcom environment, bootstrap/seed
announcements, snapshot trust manifest and monitoring probes must carry the
same hash. No TEST-ONLY constant, image, wallet, port, database or snapshot may
be reused.

## RC1 proposal

`docs/releases/public-mainnet-rc1-proposal-manifest.json` records the current
base commit, consensus/config hashes, toolchain and empty artifact slots. It is
not a release manifest: the worktree is dirty, no frozen commit/tag exists,
named browser artifacts have not been rebuilt against a canonical hash, no
node registry digest exists, and the Explorer is a separate repository. The
Python project declares `cryptography>=42.0` without a Python lock file (the
current local environment reports 46.0.6), while the browser does have a
hashed `package-lock.json`. RC1 must pin or otherwise attest the resolved
Python dependency set and base image before claiming reproducible artifacts.
The version/tag naming and tag-signing policy also require release-owner
approval.

The Python project now has `uv.lock` with exact versions and package hashes,
including the cryptography runtime and the setuptools/wheel build backend. The
locked environment was created with CPython 3.12.3. Two independent Linux
wheel builds matched byte-for-byte when supplied a fixed `SOURCE_DATE_EPOCH`
and source-prefix mapping; two Chrome and two Firefox Vite builds also had
identical directory trees. These are genesis-independent build checks, not
frozen RC artifacts. The Docker recipe is not yet reproducible: its
`python:3.11-slim` base and `apt-get update` inputs are mutable and no image
digest has been selected.

After timestamp approval: independently reproduce genesis including a full
lower-nonce scan; review and embed only the generated block/hash; pin all
identity consumers; obtain a clean source commit; build from locked inputs and
record immutable artifact digests; then execute
`docs/public-mainnet-rc1-gate-execution-plan.md`. The release matrix contains
98 `NOT_RUN` records with descriptions, dependencies and evidence references.
It is not an automatic 98-gate runner: the final per-gate runtime commands,
evidence capture and review must be completed before execution. All 98 RC
statuses and all seven public-launch statuses remain `NOT_RUN`.

## Freeze authorization checklist

Founder/release-owner decisions still required:

- exact UTC timestamp and launch timing policy;
- acceptance of resulting nonce, block bytes, hash and checksums after two
  independent reproductions;
- RC semantic version, clean source commit, annotated/signed tag policy;
- authoritative Explorer commit and final mainnet API/Explorer hostnames;
- production image platform(s), registry and distribution/licensing policy;
- chipcom/seed topology, ports, DNS, TLS, firewall and operational owners;
- snapshot trust-anchor custody and signing ceremony;
- explicit authorization to embed/freeze genesis, then separate authorizations
  for staging, publication and public launch.

Until those decisions and the 98-gate run are complete: `RC1_READY = NO` and
`PUBLIC_LAUNCH_READY = NO`.
