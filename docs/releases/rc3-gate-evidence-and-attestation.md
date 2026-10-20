# RC3 Gate Evidence and Human Attestation Policy

## Automated RC gates

`public-mainnet-rc1-gate-catalog.json` is the canonical source for the 20
`AUTOMATED_PRE_FREEZE` entries. Each entry binds the exact argv command, working
directory, prerequisite flags, dependency IDs, required evidence references,
and named assertion contract. The plan builder copies those exact commands and
check IDs; the runner rejects command, cwd, or check-ID drift. It executes argv
directly (never a shell), stores the combined output under `commands/`, and
creates an identity-bound JSON envelope containing command exit status, the
contract checks, and the output hash. Nonzero exit is FAIL; missing prerequisite
or invalid identity/evidence is BLOCKED. Dependencies must already have
verified PASS. No gate is run by this document or by building a plan.

Build an executable plan only from a clean frozen source tree:

```sh
.venv/bin/python scripts/build-public-mainnet-rc3-gate-plan.py \
  --scope MAINNET_RC \
  --genesis-hash <approved-genesis-hash> \
  --release-tag <immutable-release-tag> \
  --output /secure-evidence/rc3-plan.json
```

Then run it with a new evidence directory and matching immutable source
identity. Browser commands execute from `apps/browser-wallet`; all other
commands execute from the repository root. The gate contract specifies the
canonical test command and assertion the command is intended to exercise.
`E-*` references identify the evidence class; the runner-generated output and
identity envelope are checksummed, while external evidence remains a required
input wherever a gate's reviewed plan names it. The pre-freeze classification
must not be relabelled as a canonical-chain result.

The 20 automated entries are:

| Gate | Command (catalog command and cwd are authoritative) | Checked assertion | Evidence / prerequisites / dependencies |
|---|---|---|---|
| CONS-CFG-002 | `.venv/bin/pytest -q tests/consensus/test_mainnet_profile.py tests/config/test_network_config.py` | Mainnet identity distinct and deterministic | E-PREFLIGHT, E-CONFIG; no dependencies; source tree only |
| CONS-CFG-003 | same as above | 600-second target; no legacy schedule | E-CONFIG; source tree only |
| CONS-CFG-004 | same as above | genesis bits `0x1d1399ad` | E-CONFIG; source tree only |
| CONS-CFG-005 | same as above | 11M cap and terminal emission | E-CONFIG; source tree only |
| CONS-CFG-006 | same as above | initial miner subsidy 50 CHC | E-CONFIG; source tree only |
| CONS-CFG-007 | same as above | halving 111000 and exact cap boundary | E-CONFIG; source tree only |
| CONS-CFG-008 | same as above | coinbase maturity 100 | E-CONFIG; source tree only |
| PQ-CFG-001 | same as above | PQ policy active at genesis | E-PREFLIGHT, E-CONFIG; source tree only |
| PQ-CFG-002 | same as above | CHCQ output policy | E-PREFLIGHT, E-CONFIG; source tree only |
| PQ-CFG-003 | same as above | ML-DSA scheme ID 10 | E-PREFLIGHT, E-MATURITY-PQ; source tree only |
| SNAP-CFG-001 | `.venv/bin/pytest -q tests/node/test_snapshots.py` | Export metadata/anchor/UTXO share one consistent state | E-SNAPSHOT-CODE; source tree only |
| SNAP-CFG-002 | same as above | Signature, checksum and signer trust enforcement | E-SNAPSHOT-CODE; source tree only |
| REWARD-CFG-001 | `.venv/bin/pytest -q tests/consensus/test_mainnet_profile.py tests/config/test_network_config.py` | Reward activation 1000, warmup 2x100, maximum 25 | E-CONFIG; source tree only |
| BW-BUILD-001 | `npm run build:chrome` (`apps/browser-wallet`) | Locked Chrome production build succeeds | E-BROWSER; locked npm install required |
| BW-BUILD-002 | `npm run build:firefox` (`apps/browser-wallet`) | Locked Firefox production build succeeds | E-BROWSER; locked npm install required |
| BW-NET-001 | `npm test -- tests/unit/cross_network_isolation.test.ts tests/unit/network_support.test.ts` (`apps/browser-wallet`) | Network mismatch rejected and state isolated | E-BROWSER; locked npm install required |
| BW-NET-002 | `npm test -- tests/unit/network_support.test.ts` (`apps/browser-wallet`) | Mainnet does not depend on hardcoded testnet endpoints | E-BROWSER; locked npm install required |
| BW-SEC-002 | `npm test -- tests/unit/provider_manifest.test.ts` (`apps/browser-wallet`) | Extension permission policy verified | E-BROWSER; locked npm install required |
| SEC-CONF-001 | `.venv/bin/pytest -q tests/config/test_network_config.py tests/consensus/test_network_identity.py` | Node network/identity separation | E-PREFLIGHT, E-BROWSER, E-EXPLORER; Explorer artifact evidence remains required |
| SEC-DEP-001 | `.venv/bin/python scripts/audit-public-mainnet-npm-production.py` | No unresolved production-reachable dependency blocker | E-EXPLORER; dependency audit evidence required |

All commands above are catalogued procedures, not assertions that these gates
have been run in this RC3 worktree. The runner reports statuses only for the
identity and evidence passed to that invocation.

## Eight RC human-attestation gates

Human attestations use Ed25519 over UTF-8 canonical JSON (sorted keys,
compact separators, ASCII escaping) of the entire attestation object except
`signature`. The explicit trust store is
`docs/releases/rc-gate-trust-store.json`. It currently has an empty
`authorized_signers` array: no human gate can pass until governance supplies
approved public keys, signer identities, roles, validity intervals, and exact
gate authorizations. Private keys are generated and retained by the signer
outside this repository; the runner never creates or requests them.

The signed object binds schema version, gate ID, signer key ID and identity,
role, UTC signing time, source commit, source tree hash, release tag, canonical
genesis hash, outcome, statement, and one or more evidence paths and SHA-256
hashes. Every evidence descriptor also binds network, chain ID, genesis, source
commit/tree, release tag, and `mainnet-public-rc` environment. The allowlist
must authorize the exact gate and role, and the key must be valid at signing
time. Timestamps in the future or older than policy are rejected. Evidence
outside the evidence root, altered hashes, TEST-ONLY/historical provenance,
wrong release identity, unknown/ambiguous keys and invalid signatures produce
BLOCKED. Only a trusted signer explicitly signing outcome `PASS` produces
PASS; signed `FAIL` and `BLOCKED` remain those outcomes. Dependency failure
blocks the attestation from being considered.

Attestation shape (the signature is Base64 Ed25519 over the canonical object
with the `signature` member omitted):

```json
{
  "schema_version": 1,
  "gate_id": "RUNBOOK-001",
  "signer_key_id": "<approved-key-id>",
  "signer_identity": "<approved-human-identity>",
  "role": "<authorized-role>",
  "signed_at": "<RFC3339-UTC>",
  "source_commit": "<40-hex-commit>",
  "source_tree_sha256": "<64-hex-tree-hash>",
  "release_tag": "<immutable-tag>",
  "genesis_hash": "<64-hex-canonical-genesis>",
  "evidence": [{
    "path": "manual/review.pdf",
    "sha256": "<64-hex-file-hash>",
    "network": "mainnet",
    "chain_id": "chipcoin-mainnet-1",
    "genesis_hash": "<same-canonical-genesis>",
    "source_commit": "<same-commit>",
    "source_tree_sha256": "<same-tree-hash>",
    "release_tag": "<same-immutable-tag>",
    "environment": "mainnet-public-rc"
  }],
  "outcome": "PASS",
  "statement": "<specific review conclusion>",
  "signature": "<base64-signature>"
}
```

The eight IDs are SEC-DEP-002, SEC-SECRET-001, SEC-SECRET-002, RUNBOOK-001,
RUNBOOK-002, RUNBOOK-003, RUNBOOK-004 and RUNBOOK-005. No authorized signers
are currently configured, so all remain BLOCKED.

## Seven public launch gates

The seven procedures and their evidence assertions remain in
`public-mainnet-launch-gate-catalog.json`: PUB-001 bootstrap/DNS/P2P, PUB-002
TLS/firewall/rate limits, PUB-003 monitoring/backups, PUB-004 signed snapshot,
PUB-005 public documentation/endpoints, PUB-006 launch/rollback drill, and
EXP-PUB-001 live Explorer/monitoring. They are explicitly manual and NOT_RUN
here. This local RC3 exercise has no public infrastructure evidence and cannot
promote them.
