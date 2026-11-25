# Node resilience RC1 — release-gate results

This is a private-candidate report. No merge, push, Mainnet deployment, or
production database access occurred. The starting candidate was
`9188fcb58d50285a42ccf8d432edf88c2d331d41`, based on public
`54d2987f00052a8f2c006512279ab286766d1b11`.

| Gate | Result | Evidence and limits |
| --- | --- | --- |
| Extended suite on original frozen commit | PASS | `pytest -q tests/node tests/storage tests/consensus tests/miner tests/rewards tests/integration --disable-warnings --tb=short`: **748 passed**, Python 3.12, local loopback permitted. The requested historical 747 count rose by one because the frozen commit already contained the additional persistent-status-error test. |
| Extended suite after necessary corrections | PASS | Same command: **752 passed**, Python 3.12, 215.72 seconds. All databases and sockets were isolated. |
| Mixed-version three-node P2P | PASS | One node ran source archived from the official `mainnet-v0.1.2` tag (`12e4dbc8974bd76885e30e6dacdf1b7be898e126`), two ran the candidate. Local loopback only. All reached height 9 after ten synthetic blocks, hash `064bcbc5d501ab621fa6caf4690dd11597104698df103a98f10ca30a54df9b74`, cumulative work 20, with active peers. One candidate also repaired a legacy NULL header via P2P. Reproduction: `tests/integration/resilience/README.md`. This is an easy-target Mainnet *profile*, not public Mainnet mining. |
| Invalid UTF-8 P2P `version` | PASS | `tests/node/test_codec.py::test_version_rejects_invalid_utf8_as_protocol_error` passed separately and in the extended suite. The payload is rejected as `CodecError`. |
| Best-header cap | PASS | A regression with 40 higher-work corrupt rows failed on the frozen commit (`best=None` after the old 32-row limit). Ordered rows are now streamed until a valid record appears; the regression finds the valid lower-work record. |
| Incomplete versus corrupt header | PASS | NULL payloads count as `incomplete`; non-NULL invalid payloads count as `corrupt`. Separate counters appear in bounded diagnostics. Both are unavailable to best-tip selection and header advertisement. Tests cover both and recovery after a validated replacement. |
| Scheduler exception handler | PASS | A test reproduced the exception escaping from `set_runtime_sync_status()` on the frozen commit. The handler now catches malformed snapshots and publication failures, keeps the task alive, and rate-limits repeated diagnostics. It cannot promise a working status API if the in-memory status setter itself is irreparably broken. |
| Missing-header P2P repair | PASS | Three-node integration asserts at least one real `getheaders` request, replacement of a legacy NULL row, and convergence without restart. A separate locator test prevents an active-chain corrupt header from being skipped in a request. |
| Full Python 3.14 suite | NOT_RUN | Focused tests passed: 53 non-socket tests plus 28 socket integration tests on the earlier candidate, and 10 final header/scheduler/codec tests after the gate corrections. This is not a full Python 3.14 certification. |
| Operator's two-node 24–48 hour trial | NOT_RUN | Requires private delivery and an operator-controlled installation window. Keep the previous package and coherent backups available. |

## Branch overlap

The historical pool-submit RC `a53f2b03dadc27681e236886c65f0db721c7dc9a`
and the Docker-first branch are ancestors of the official v0.1.2 release used
here. Compared with the pool-submit RC's own base, `runtime.py` and
`service.py` are overlapping filenames. Its edits are in mining-submission
functions; this candidate changes inbound peer admission, ban checking,
peer observation, and the sync scheduler. No shared function or line change
was identified. The Docker-first branch has no modified file in common with
this candidate. No branch integration was performed for this audit.

## Release decision

The original ZIP and commit are **superseded** because the review uncovered
real release-gate defects. Use the final commit and its matching checksum
only. The candidate is ready for an isolated private operator trial; public
release and Mainnet rollout remain unapproved.
