# Chipcoin Mainnet v0.1.3 — release candidate notes

Status: **local release candidate, unpublished**. The currently published
Mainnet release remains v0.1.2 (`12e4dbc8974bd76885e30e6dacdf1b7be898e126`).

## Changes from v0.1.2

- P2P peerbook enumeration and malformed-session handling are more resilient.
- Header storage ignores incomplete records during best-tip selection and
  requests missing headers through the existing P2P recovery path.
- The sync scheduler isolates recoverable failures and reports degraded state.
- Shared SQLite reads are materialized under lock to prevent concurrent cursor
  corruption between runtime and HTTP threads.
- Legacy mining submission distinguishes a template invalidated by a tip
  change while its original TTL remains from an unknown or expired template.
  Full-block submission and consensus rules are unchanged.

The Docker-first official-release installer and peer-height telemetry proposal
are **not included**.

## Compatibility and operator notes

No changes were made to Mainnet genesis, chain selection, PoW, transaction
validation, wallet format, reward rules or database schema. Existing v0.1.2
wallets and blockchain storage remain the intended persistent paths. A
controlled update should retain the previous image and a verified SQLite
backup, replace only the Core image, then check chain identity, tip, peers,
HTTP API and mining template behavior. On a critical regression, restore the
previous image without deleting persistent data.

Legacy pool clients must accept the existing `stale_template` code for
tip-invalidated templates. `unknown_or_expired_template` still covers unknown
IDs and elapsed TTL. A `stale_template` response is about the legacy template
cache; it does not itself determine consensus validity of a submitted full
block.

## Release gate

The exact source commit, Docker image revision label, image digest, source and
image archive SHA-256, and build-specific third-party inventory are recorded
in the private candidate manifest produced after the final build. This note
does not authorize a tag, public push or deployment.
