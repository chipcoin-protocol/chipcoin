# Public Mainnet Genesis and RC1 Proposal

Date: 2026-10-19. Status: **approved genesis candidate integrated locally;
source freeze and deployment are not yet authorized**. MemPalace was consulted.
The final consensus audit is
`docs/public-mainnet-final-consensus-audit-rc1-preparation.md`.

## Candidate identity

| Field | Approved candidate value |
| --- | --- |
| Network profile | `mainnet` |
| Chain ID | `chipcoin-mainnet-1` |
| P2P magic | `c0897c0d`, first four bytes of SHA-256 of `chipcoin:p2p-magic:chipcoin-mainnet-1` |
| Header version | 1 |
| Previous hash | 32 zero bytes |
| Approved candidate timestamp | `2026-10-20T18:00:00Z` / `1792519200` |
| Initial bits | `0x1d1399ad` / `487823789` |
| Genesis transaction version | 1 |
| Genesis metadata | sorted keys `chain_id`, `coinbase=true`, `genesis_message`, `height=0` |
| Message | `Die Welt ist alles, was der Fall ist.` (exactly 37 UTF-8 bytes) |
| Inputs / outputs | 0 / 0 |
| Genesis reward / spendable supply | 0 / 0 chipbits |
| TXID / Merkle root | `6ec15ed32ddd62c6134b0c867c33f8fa72ba265b4551d327a57b63721cf34c77` |
| Nonce | `468059814` |
| Candidate block hash | `00000001fb292c1575cc647774e249a7e399b8b2c7b30743bbe9e5090476476d` |
| Serialized block SHA-256 | `4ecbeda4c457a50052d5999fe3ac7d851a0d602769e123ea8200e151e55f8255` |

Candidate artifacts and `SHA256SUMS` are in
`/tmp/chipcoin-public-mainnet-genesis-candidate-20261020T180000Z/`; their
checksums and verification report hashes are recorded in
`docs/releases/public-mainnet-rc1-genesis-provenance.json`. This provenance is
not a signed release manifest or published identity.

The timestamp is not inherited from TEST-ONLY. It was approved for this
candidate and independently checked on Tobia and Chipcom. The candidate is
integrated in this local worktree; source freeze and public launch remain
pending. The first retarget at candidate height 1000 uses the
elapsed time from genesis to block 999 against a 600,000-second target and
clamps the adjustment to 1/4..4, then caps the target at `genesis_bits`. Since
mainnet starts at that cap, a delay before block 1 cannot make the target
easier than its initial value, though it may prevent an isolated run's faster
timestamps from making the target fractionally harder. The approved timestamp
is `2026-10-20T18:00:00Z`; the source freeze and launch remain separate decisions.

1. select an earlier timestamp that allows the isolated final-genesis gate
   run, explicitly accepting and calculating its idle-to-public-start retarget
   effect; or
2. select a timestamp close to public exposure, accepting that the nominal
   8.3-day run through payout maturity may extend beyond November 7.

The isolated validation chain is never transferred to the public network.
The formal policy is `docs/releases/rc1-isolated-final-genesis-validation-policy.md`.

For the approved candidate timestamp, a public first block at
2026-11-01T00:00:00Z and 999 intervals averaging 600 seconds, the first
retarget span projects to 1,571,400 seconds (2.619x target); for a
2026-11-07T00:00:00Z first block it projects to 2,089,800 seconds (3.483x).
Both are within the existing 4x clamp; because they exceed target and the
target is capped at `genesis_bits`, the first public retarget remains at the
initial target. These are projections, not a mined result or consensus change.

## Canonical construction

`build_genesis_transaction` serializes transaction version 1, zero inputs,
zero outputs, locktime zero and metadata sorted by key. Strings are UTF-8 with
canonical varint lengths. TXID is double-SHA256 of those bytes. With one
transaction, the Merkle root equals the TXID. The 80-byte header serializes
little-endian version/timestamp/bits/nonce around the raw 32-byte previous and
Merkle hashes. The block hash is double-SHA256 of the header, interpreted
big-endian for target comparison. The lowest valid uint32 nonce is selected in
ordered batches, so worker count cannot change the result.

The approved candidate was generated with:

```bash
.venv/bin/python scripts/build-public-mainnet-genesis.py \
  --timestamp 1792519200 \
  --workers 2 \
  --output-dir /secure/genesis-primary \
  --acknowledge-founder-approved-timestamp
```

Do not regenerate or change the candidate. Its recorded artifacts were
reproduced on Chipcom for structure, serialization and PoW; the full lowest-
nonce scan was completed locally on Tobia. For audit replay, run:

```bash
.venv/bin/python scripts/verify-public-mainnet-genesis-independent.py \
  /secure/genesis-primary --verify-lowest-nonce --nonce-workers 2
sha256sum -c /secure/genesis-primary/SHA256SUMS
diff -ru /secure/genesis-primary /secure/genesis-secondary
```

The candidate was built by the canonical builder with 2 workers. The
independent verifier imports no Chipcoin module. It reparses
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

The reviewed block hex/hash is embedded in `consensus/genesis.py` and flows
through `config.py`. Full node startup installs or verifies it against an
empty/existing DB; P2P handshakes bind chain ID and genesis; snapshots bind
network/chain/genesis; API status exposes network magic, chain ID and genesis.
Miner startup verifies all three. CLI/reward signing binds chain ID and checks
API identity. Browser wallet pins network magic and `canonicalGenesisHash` and
remains fail-closed. The authoritative Chipcoin Central Explorer must pin the same
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

The approved candidate has already been independently reproduced, including a
full lower-nonce scan on Tobia and structural/PoW validation on Chipcom. The
remaining freeze process is to review and embed only these verified bytes, pin
all identity consumers, obtain a clean source commit, build from locked inputs,
record immutable artifact digests, and then execute
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
