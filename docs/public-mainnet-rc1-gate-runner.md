# Public Mainnet RC1 Gate Runner

The runner is `scripts/run-public-mainnet-rc-gates.py`. It reads the canonical
98-entry matrix and never writes gate statuses back to it. It accepts a reviewed
per-gate plan containing argv commands, canonical evidence reference IDs,
hashed evidence files, a mainnet identity-evidence file, and explicit JSON
pointer assertions. No command is interpreted by a shell.

## Scopes

- `PRE_FREEZE_SOURCE` permits only gates classified `SOURCE_REVALIDATION` and
  requires `genesis_hash: null`. Evidence must identify its environment as
  `mainnet-source-review`.
- `MAINNET_RC` requires a finalized 64-character genesis hash and a frozen
  source commit/tree identity. Evidence must identify `mainnet-public-rc`.

The runner independently fingerprints `HEAD` plus all tracked and non-ignored
untracked file contents, modes, symlinks, and deletions. The supplied commit,
tree SHA-256, and cleanliness flag must match the current worktree. `MAINNET_RC`
additionally requires the worktree to be clean.

For both scopes, each gate's configured `evidence_refs` must cover all entries
in the canonical matrix. PASS requires exit code zero, every declared evidence
file to exist, optional expected hashes to match, identity evidence to match
network/chain/genesis/source identity, and all explicit assertions to pass.
Missing evidence or a mismatch is BLOCKED; a nonzero command exit is FAIL.
Dependencies not already PASS are BLOCKED. TEST-ONLY, testnet, devnet, and
rehearsal environments cannot satisfy either evidence identity.

The JSONL event journal is append-only and SHA-256 hash chained. Resume skips
already recorded gate attempts, verifies their evidence hashes, and blocks
tampered evidence and dependent PASS results. A new reviewed attempt uses a
new evidence directory; it does not overwrite the previous run. The human
reviewer still adjudicates whether the asserted evidence demonstrates the
normative gate criterion.

## Invocation

Start from `docs/releases/public-mainnet-rc1-gate-plan.example.json`, fill only
reviewed source-gate commands before genesis approval, and use a new evidence
directory for each attempt:

```bash
.venv/bin/python scripts/run-public-mainnet-rc-gates.py \
  --matrix public-mainnet-rc-revalidation.json \
  --plan /secure/reviewed/rc1-gate-plan.json \
  --evidence-dir /secure/evidence/rc1-pre-freeze-run-001 \
  --report-json /secure/evidence/rc1-pre-freeze-run-001/report.json \
  --report-markdown /secure/evidence/rc1-pre-freeze-run-001/report.md
```

The current canonical matrix has 98 `NOT_RUN` gates and its genesis is pending.
The reviewed execution/evidence catalog is
`docs/releases/public-mainnet-rc1-gate-catalog.json`: 20 source checks have
concrete commands, 8 require signed manual attestations, 63 require the final
isolated chain, 5 require source/artifact freeze, and 2 have explicit genesis or
runtime-evidence blockers. Tool tests are not RC gate results.

The former `SNAP-RUN-004` / `FINAL-RUN-001` cycle was corrected: snapshot and
full-sync equivalence is an input to final convergence. Matrix generation and
the runner now reject unknown dependencies, self-dependencies and cycles.

## Current limitations

The catalog defines criteria and evidence identity for all 98 gates, but the 63
runtime commands cannot be finalized until the canonical genesis and production
orchestrator exist. Manual attestations never auto-PASS. TEST-ONLY evidence is
explicitly forbidden for public RC promotion.
