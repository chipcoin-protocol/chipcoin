# Public Mainnet RC3 Candidate Validation

Status: candidate only; no RC3 commit, tag, public release, or gate promotion.

## Source and scope

The isolated `rc3-candidate` branch is based on RC2 commit
`5de4080e2c32162aaf923ee6ac250b0a74288496`. The immutable RC2 tag was not
changed. The worktree remains dirty by design. Changes are confined to the
Docker build recipe, CLI/API/snapshot test fixtures, and this candidate
documentation. Production consensus, network identity, genesis, wallet,
miner, runtime, and Explorer source are unchanged.

The candidate genesis remains
`00000001fb292c1575cc647774e249a7e399b8b2c7b30743bbe9e5090476476d`.
No chain, node, miner, or public service was started.

## Failure triage and corrections

The original targeted rerun reported 21 failures and 131 passes with 2
skips across CLI, API, transport, and miner tests. Twenty CLI cases and one
API/CLI parity case reopened synthetic databases as finalized production
mainnet; strict canonical-genesis enforcement correctly rejected those test
fixtures. The fixtures now explicitly inject their synthetic consensus
parameters for local query tests, while tests that exercise actual mainnet
identity continue to use the embedded canonical genesis. No production check
was relaxed. The synthetic output-free genesis fixture now correctly has zero
genesis subsidy.

All 18 snapshot failures were fixture-context errors: synthetic chains were
exported as finalized mainnet snapshots, and signed imports omitted the
required trust policy. Synthetic roundtrip/validation tests now use the
unfinalized `devnet` profile; the finalized-mainnet trust rejection test uses
the actual embedded mainnet genesis. No snapshot verification code changed.

The focused post-fix command completed with **175 passed, 0 failed, 2
skipped**. It covered `test_cli.py`, `test_http_api.py`, `test_snapshots.py`,
`test_transport_protocol.py`, and `test_worker.py`. The skips remain skips;
this is regression evidence, not a promotion of any formal RC gate.

## Docker reproducibility

The prior independent `--load` images shared the same first five base layers;
differences began in the generated wheel layer and consequently in later
runtime layers. Independent extraction showed identical bytes for every wheel
member, but two generated `.dist-info` entries differed only in ZIP mode
metadata (`0664` versus `0644`). The Docker build environment did not pin its
umask. `Dockerfile` now sets `umask 022` before wheel generation.

Two `--no-cache --pull` Buildx OCI exports with
`--output type=oci,...,rewrite-timestamp=true` then compared byte-for-byte.
Both report manifest `sha256:bee9b05322104db7aaa542a1813b444d4c0075b303f6e468648ac04374b5f431`,
config `sha256:ad775182f153fbc7fff17029bcaeb37b69789efadb0b5ae8b37cc8c4cec4b231`,
and archive SHA-256
`9b4a8602471dff4ca13a34806150853b6ce11dbc4af9401463736166e93faf1d`.
Both builds passed `pip check`. This is reproducibility evidence for local
candidate outputs, not a published or signed release artifact.

## Gate execution

The canonical catalog remains the source of the 98 gate definitions,
dependencies, criteria, and evidence references. The existing runner requires
a clean frozen commit, a source-tree digest, a per-gate reviewed command,
hashed identity evidence, evidence paths, and explicit JSON assertions before
it can record PASS. The RC3 example plan binds the approved chain identity but
intentionally has no gate commands or assertions. All 98 formal gates remain
`NOT_RUN`; prior RC2, TEST-ONLY, or rehearsal evidence was not promoted.

The runner plan is not operationally ready until the RC3 source commit exists
and each automatable gate has an independently reviewed executable spec.
Manual gates require attributable attestations. Any gate requiring the final
canonical chain remains blocked until that chain exists.

## Explorer and blockers

The Explorer repository was not modified. Before RC3 freeze, review its
separate dirty worktree and bind its network, chain ID, and genesis hash to
this identity; build/test it from a clean source revision. Do not inherit
Explorer evidence from another commit or chain.

Remaining blockers: finalize the RC3 source commit and tree hash; complete and
review the 98-gate execution plan; integrate and validate Explorer in its
separate repository; run the formal gates on their required environments;
and obtain release-owner approval before creating an RC3 tag or publishing
artifacts. Consensus parameters are unchanged.
