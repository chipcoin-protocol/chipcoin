# Mainnet v0.1.2 release alignment and evidence

This document records the evidence boundary for Handbook v1.2. The reference is the **published Core release**, not the handbook's Git ancestry. The handbook was published separately after that immutable release tag. Inspect the tagged commit for release code bytes.

## Provenance

| Item | Identity and evidence | Status |
| --- | --- | --- |
| Original submission RC | `a53f2b03dadc27681e236886c65f0db721c7dc9a`, descended from public base `163408845095171ccf94d11f626fe5dbac8688f8`; included through the two-parent integration merge. | VERIFIED Git ancestry |
| Integrated RC | `4c0984e65de31a50db7558d468167d513769bb20`; source of the unchanged `test-vectors/v1.json`. | VERIFIED local commit and vectors |
| CHCQ precheck | `15b8b190ee44b6e4ed3b8817bcf10a252f2a1e37`, child of integrated RC; rejects unsupported Mainnet CHCQ payout scheme before template issuance. | VERIFIED diff and regression |
| Published Core | Annotated tag [`mainnet-v0.1.2`](https://github.com/chipcoin-protocol/chipcoin/releases/tag/mainnet-v0.1.2) dereferences to `12e4dbc8974bd76885e30e6dacdf1b7be898e126`, a child of the CHCQ fix. Diff from integrated RC changes production code only in `src/chipcoin/node/service.py`; the other changes package test sources and extend tests. | VERIFIED Git objects |
| Published artifacts | Release `SHA256SUMS`: `1cce245d209cb676f8a8033afba4658bc422c28af5731a40b724bdabdb1590ff` for `core-image-12e4dbc.tar.gz`; `bb9b3293a047e988fbcbc5f878838a24fbc12db98b24051fcb2fff1ae71b6f79` for `source-12e4dbc.tar.gz`. Local archive hashes matched. Docker archive config is AMD64 with OCI revision `12e4dbc...`; all 469 regular source archive blobs checked against the Git tree matched. | VERIFIED artifacts; AMD64 only |
| Mainnet deployment | Operator rollout and an independently inspected native ARM64 build from the tag show deployed v0.1.2. The ARM64 image has its own image digest; it is **not** byte-identical to the published AMD64 archive. A public, per-host image attestation is not part of this handbook. | PARTIALLY_VERIFIED operational provenance |
| Original handbook | `578d96eaee01372262eab18c109d6aa92751c39d`, followed by `a9bb0cc676036b77385412ac075627ed8bf658fc`; this patch descends from the latter to preserve both original changes. | VERIFIED Git ancestry |

The original [submission specification](../integrations/BLOCK_SUBMISSION_SPEC.md), [compatibility matrix](../integrations/BLOCK_SUBMISSION_COMPATIBILITY.md), [RC notes](../integrations/BLOCK_SUBMISSION_RC.md), [rollout](../integrations/BLOCK_SUBMISSION_ROLLOUT.md), [test plan](../integrations/POOL_PRERELEASE_TEST_PLAN.md), and [audit](../integrations/SUBMIT_BLOCK_AUDIT.md) remain historical RC records. They are intentionally not rewritten into a second protocol specification. Where those documents say “candidate”, read the tagged source before applying the claim to v0.1.2.

## Traceability matrix

In this table `R` means tagged Core `12e4dbc...`; `V` means original vector source `4c0984e...`. `VERIFIED` means read in the release source and covered by the named local check; it does not imply external pool compatibility.

| Requirement | Handbook section | Core source / version | Network profile | Check or evidence | State / action |
| --- | --- | --- | --- | --- | --- |
| Network identity and setup | [Guide](INTEGRATION_GUIDE.md), [Quick start](README.md) | `consensus/network_identity.py`, `scripts/setup/wizard.py`, `setup.sh` (R) | Mainnet default; Devnet opt-in | Git source; isolated Devnet smoke | VERIFIED; keep profiles separate |
| Template request and response | [Templates](BLOCK_TEMPLATES.md) | `interfaces/http_api.py::_handle_get_block_template`, `node/service.py::get_block_template` (R) | All; Mainnet PQ precheck | Pool/API regressions | VERIFIED |
| Template TTL and cache bound | [Templates](BLOCK_TEMPLATES.md) | `node/service.py` (`15` s, `MAX_MINING_TEMPLATES=256`) (R) | All | Cache bound/expiry regressions | VERIFIED; not configurable here |
| Legacy/full submission and mempool update | [Submission](BLOCK_SUBMISSION.md) | `interfaces/http_api.py::_handle_submit_block`, `node/service.py`, `node/runtime.py` (R) | All | Pool integration tests and Devnet smoke | VERIFIED; legacy missing ID still fails |
| Side branch, duplicate, retry and active chain | [Submission](BLOCK_SUBMISSION.md), [Troubleshooting](TROUBLESHOOTING.md) | `node/service.py::accept_full_block`, `full_block_status`, `inspect_block`; `node/runtime.py` (R) | All | Pool side-branch/reorg/post-commit tests | VERIFIED in isolation; pending side branch is not fully contextually validated |
| Header, target, Merkle and canonical block | [Vectors](TEST_VECTORS.md) | `consensus/serialization.py`, `pow.py`, `hashes.py`, `merkle.py` (V, checked on R) | Mainnet genesis, synthetic Devnet | Unchanged JSON fixture + verifier | VERIFIED; no live block submission implied |
| Coinbase output count, reward split and fees | [Coinbase](COINBASE_AND_PAYOUTS.md) | `node/mining.py::build_coinbase_transaction`, `consensus/validation.py::_validate_coinbase_distribution`, `economics.py` (R) | Mainnet/Testnet/Devnet parameterized | Pool invalid-coinbase tests; encoding-only reward vector | VERIFIED rules; reward-layout vector is DOCUMENTED_ONLY for full contextual validity |
| SOLO direct CHCQ miner output | [Coinbase](COINBASE_AND_PAYOUTS.md) | `node/mining.py`, `consensus/validation.py` (R) | Mainnet | Template and consensus checks | VERIFIED for one miner output; pool ownership/accounting external |
| PPLNS direct multi-miner coinbase payout | [Coinbase](COINBASE_AND_PAYOUTS.md) | `consensus/validation.py::_validate_coinbase_distribution` (R) | All | Exact output count rule | VERIFIED UNSUPPORTED; use later signed v2 payouts |
| CHCQ codec and ML-DSA-44 payout precheck | [PQ](PQ_ADDRESSES.md) | `crypto/addresses.py`, `crypto/pq/mldsa.py`, `consensus/pq_activation.py`, `node/service.py` (R) | Mainnet height 0; Testnet 20,000; Devnet 30,000 | Address vectors; Mainnet negative/positive template regression | VERIFIED; do not use test addresses for funds |
| Worker Stratum dialect and share target | [Stratum](STRATUM_REFERENCE.md) | External miner client at `6d40215...` / v0.10.2; no Core Stratum server | Pool-specific | Local read of CPU/GPU client; anonymized operator report | OPERATOR_REPORTED for server internals; wire trace and source not independently checked |
| Docker example | [Quick start](README.md), [Compose](examples/compose.devnet.yml) | Tagged R build context | Isolated Devnet | Compose config check and local HTTP smoke | VERIFIED without Docker end-to-end run in this review |
| Public use rights | This page | No root `LICENSE` in R; `vendor/mldsa-native/LICENSE` covers only vendor material | All | Git tree audit | BLOCKED for clear third-party redistribution terms; maintainer/legal decision needed |

## Test evidence and limits

- **This review:** vector verifier against R **PASS**; 88 selected pool, HTTP API, reward and wallet tests **PASS**; a separate consensus/additional reward suite **154 PASS** (242 distinct selected tests overall); isolated local Devnet HTTP smoke with R **PASS** (full submit, active-chain lookup, identical retry); Compose configuration with R as build context **PASS**; 105 relative Markdown links resolved **PASS**. The smoke ran as a temporary Python Core process, not a Docker deployment or external Stratum test. The fixture was not regenerated.
- **Publication check:** browser ML-DSA interoperability suite returned **2 PASS** in a disposable checkout of R after `npm ci` installed the pinned browser dependencies. An earlier run without npm dependencies returned 1 PASS and 1 environment failure (`vite: not found`). The missing `pytest` import reported earlier is present in R; the two browser fixture files are present in the verified source archive.
- **Historical only:** 116 handbook-related passes and 76 link checks were reported before this review; they are **not** current test results. An external pool operator reported a successful isolated pre-release test of the integrated RC. That report is operator evidence, not a rerun by this handbook patch, and it does not establish another pool backend's behavior. No private correspondence is reproduced here.
- The three earlier failures are identified in the local final-RC readiness evidence: `test_browser_mldsa44_fixture_matches_python_backend` and `test_browser_pq_vector_fixture_matches_python_backend` failed because two browser fixtures were omitted from the old source archive (**TEST_FIXTURE / packaging**); `test_browser_mldsa44_signature_verifies_with_python_backend` encountered a missing `pytest` import on its skip path (**TEST_FIXTURE / test code**). The final RC archive includes the fixtures and the test imports pytest. The earlier report records separate PASS reruns. The dependency-complete browser rerun above passed both tests selected in that suite; it does not replace those historical results.
- The published source archive contains no operational `.env`, wallet or SQLite database; its 469 regular file blobs match the tag. It **does include public, deterministic browser test vectors containing test-only seed/private-key material**; those fixtures are not production wallets and are not copied into the runtime image. The handbook JSON itself contains public test data and no signing seed. This is a source/filename audit, not a formal secret-scanning certification.
- Docker Desktop ARM64, sustained multi-pool load, live Mainnet submission, and a full external Stratum server test are **NOT_RUN** in this review. No production database or wallet was accessed.

## Open integration questions

An operator has reported answers for some of these, but direct source or scrubbed wire evidence remains outstanding:

1. Confirm the reported one-template-per-job mapping and four-job retention with a scrubbed job/template trace; verify behavior under a mempool-only update.
2. Confirm the reported locktime split with exact `coinb1`, extranonce1/2, `coinb2` and resulting coinbase bytes. How are worker extranonces partitioned and rotated without collision?
3. The reported backend currently submits legacy and tests, but has not deployed, a full-block fallback. When a valid network share arrives after legacy TTL, does it preserve the **same full block bytes** and reconcile by hash?
4. The operator reports tip-driven job invalidation, hash lookup and its own confirmation/orphan thresholds. How are duplicate shares, stored side branches, reorgs and delayed HTTP responses reflected in pool accounting and logs?
5. For a new SOLO/PPLNS backend: is a single miner coinbase output acceptable, and can participant payouts be delayed until 100-block Mainnet maturity using signed CHCQ v2 transactions?

## Publication and editorial follow-up

- The handbook is not part of `mainnet-v0.1.2`; it was applied as a document/test-example patch onto public `main` containing tagged Core `12e4dbc...`. The earlier `4c0984e` Core tree was not merged over the release.
- The project root has no explicit public `LICENSE` at this tag. The vendor license does not license original Core code. The maintainer must resolve licensing before promising redistribution rights to third-party pool operators.
- The existing [miner-facing pool page](https://chipcoinprotocol.com/pool-mining) is not replaced. The separate [operator entry page](https://chipcoinprotocol.com/pool-integration) is live; [SITE_PAGE_DRAFT.md](SITE_PAGE_DRAFT.md) remains a historical draft. The website Docs page now identifies Mainnet as live while retaining Testnet material separately.
- **Status: PUBLIC DOCUMENTATION, OPEN TECHNICAL REVIEW.** Technical reference claims are release-aligned and locally tested as described. License clarity and external backend details remain separate follow-up items; operator feedback can be addressed incrementally.
