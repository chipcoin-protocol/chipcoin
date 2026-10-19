# Public Mainnet RC1 Gate Integration and Security Closure

Date: 2026-10-19. MemPalace and the prior RC1 reports were consulted. No active
chain, genesis, deployment, release, commit, tag or public artifact was changed.

## Gate graph and catalog

The 98-gate graph is acyclic. `SNAP-RUN-004` now depends on snapshot restore;
`FINAL-RUN-001` depends on `SNAP-RUN-004`, preserving the intended security
ordering. Builders and runners reject duplicate IDs, missing references,
self-dependencies and cycles.

All 98 gates are represented in the execution/evidence catalog. Counts are:
20 automated pre-freeze, 8 signed manual attestations, 63 final-chain runtime,
5 source-freeze finalization, 1 final-genesis blocked and 1 runtime-dependency
blocked. Every entry specifies dependencies, identity-bound evidence fields,
PASS/FAIL criteria and prerequisites. Missing, incomplete, cross-chain or
TEST-ONLY evidence cannot produce PASS.

## Verification performed

- Gate/matrix/runner tests: 29 PASS.
- Source configuration, identity and snapshot tests: 49 PASS.
- Browser wallet, two clean installs: 178 PASS; two Chrome and two Firefox
  builds are pairwise byte-identical.
- Explorer, two clean installs: 74 PASS and 2 live tests skipped because final
  mainnet identity is intentionally unavailable; typecheck/build PASS twice.
- npm: wallet production 0; Explorer 0; wallet dev toolchain 3 high, 0 critical.
- Docker: two independent OCI exports byte-identical, including manifest,
  config, layers and final OCI tar digest.

These are pre-freeze technical checks, not formal public-chain gate PASS. The
canonical matrix remains `0 PASS / 0 FAIL / 98 NOT_RUN` because final genesis,
frozen commit, named artifacts and canonical-chain evidence do not yet exist.
The separate technical evaluation is `20 PASS / 0 FAIL / 70 BLOCKED / 8
NOT_RUN` and is recorded in
`docs/releases/public-mainnet-rc1-prefreeze-evaluation.json`; promotion is
explicitly prohibited by that record.

## Remaining blockers

Founder approval and freeze of genesis timestamp/hash; clean reviewed source
commits in both repositories; immutable named artifacts; signed disposition of
the three web-ext build-tool advisories; final Explorer genesis binding; and a
fresh isolated canonical-chain execution of all runtime/finalization gates.
