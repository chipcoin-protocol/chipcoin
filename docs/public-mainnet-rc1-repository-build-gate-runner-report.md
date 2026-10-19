# Public Mainnet RC1 Repository, Build, and Gate Runner Report

Date: 2026-10-19. This is pre-freeze local evidence only. No genesis was
approved or frozen; no chain, active container, deployment, tag, commit, or
publication was changed.

## Repository classification

Main repository base: `63de78592f1bc577df579a53281fac5ed515e422`. The worktree
remains dirty and uncommitted. The current inventory is 60 tracked modified
files and 96 untracked paths. The file-by-file
classification and proposed commit sequence are in
`docs/public-mainnet-rc1-worktree-inventory.md`.

The dirty Explorer repository is `/home/komarek/Documents/CODEX/chipcoin-central`,
base `17a19e9e6f5d7b816e4854dd90baf1333085b066`, with 12 tracked modifications
and 2 untracked tests. It was inspected only; no Explorer file was changed.
Candidate production source/tests, docs/config, TEST-ONLY material, backups,
and release templates remain separately classified. No file was deleted,
staged, committed, or pushed.

Proposed commit order: reviewed protocol/network identity plus tests; node,
miner, wallet/browser integration plus tests (Explorer separately in its
authoritative repository); dependency/build reproducibility inputs; gate
runner and reviewed evidence mappings; only after timestamp approval the
canonical genesis and identity-dependent artifacts; deployment configuration
and release evidence last. This is a proposal, not authorization to commit.

## Builds

Python dependency inputs are pinned by `uv.lock` and the generated
hash-checked `docker/requirements-build.lock`. Dockerfile base image indexes
are pinned to official Python Trixie digests:

- Builder: `python:3.11.17-trixie@sha256:50cfccc707e8721201ee018bfd7f6a85d8eacf49c4f9f75833a2aba09a10411f`.
- Runtime: `python:3.11.17-slim-trixie@sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce`.

The Dockerfile no longer resolves mutable APT repositories; package contents
are inherited from the pinned bases and compiler package versions are checked.
Two independent no-cache `linux/amd64` builds completed and passed `pip check`.
Both built application wheels match SHA-256
`f537bf886f3b86036e0b2650f97cfd51ba64a7650fccfac85f15e4c5ccfce473`.
The initial Docker exporter exposed 206 timestamp-only differences. A second
pair of clean OCI exports with canonical timestamp rewriting is byte-identical:
tar SHA-256 `37c88176e030ad7b4b8f513d8c99df119fd479cbb503f68f0337798ae6447f89`,
manifest `e9ac0256cfba...e31f`, config `a1dfa370ec17...ed48`. This demonstrates
exact local OCI reproducibility; the outputs are still not release artifacts.

Two isolated browser copies each ran `npm ci`, then Chrome and Firefox builds.
Chrome tree hashes matched at
`49b3e09f6e17172fae750d9c900b42b36aa199f8e30074f88e44ac7f0bf6db0a`; Firefox
matched at `5f133cfddb8abdca4ebc18cf7f5fae244a058e2aeb4c8f511fb479267523f717`.
No build was copied to named production artifacts or configured with the
candidate genesis. Targeted dependency updates reduce the wallet result to
3 high development-tool findings and 0 critical; production dependencies and
the Explorer audit both report zero.

## Gate runner

`scripts/run-public-mainnet-rc-gates.py` reads the 98-gate canonical matrix,
validates evidence hashes and identity, records append-only hash-chained
attempts, supports verified resume, blocks dependent gates, and rejects
TEST-ONLY evidence for public RC status. It emits JSON and Markdown reports.
The canonical statuses remain 98 `NOT_RUN`. The catalog maps all gates and has
20 concrete pre-freeze commands. The former snapshot/final cycle is resolved
with snapshot equivalence preceding final convergence; graph validation is
fail-closed. Runtime/finalization commands remain blocked by the final genesis,
canonical chain and source freeze.

## Validation and blockers

- Browser clean installs/builds: PASS, two copies per browser; identical tree
  hashes.
- Docker build/package checks and exact OCI reproducibility: PASS.
- Gate graph/catalog/runner focused regression tests: 29 PASS; no formal RC gate promoted.
- Source configuration/identity/snapshot tests: 49 PASS; Python `py_compile`: PASS;
  `git diff --check`: PASS.
- Genesis timestamp/hash remain pending approval; all gates requiring final
  public-chain identity remain NOT_RUN.

MemPalace was consulted for prior release decisions. It did not supply a new
approved launch timestamp or change the rule that the final genesis remains
pending. No active chain or Explorer deployment was touched.
