# Docker-first setup validation (development branch)

This report describes branch `codex/docker-first-setup`. It is not a production deployment or a public release.

## Root cause and implementation

The former host-Python wizard imported `src/chipcoin` and called wallet generation before the native `_mldsa_native` extension existed on a clean host. The Docker runtime image already built that extension, but the wizard ran outside the image. The new `./setup.sh` builds the pinned Core from the same clean Git checkout and starts a disposable setup image containing the wizard and installed Core. The launcher performs Docker/Compose and architecture checks. The setup image runs the existing wallet code and a deterministic ML-DSA-44 known-answer test before a Mainnet key operation. It receives a read-only checkout and the selected persistent storage base; it does not receive the Docker socket or privilege elevation.

New installations use a user-owned network tree. Existing deployed `/var/lib/chipcoin-mainnet-official` and other legacy paths are unchanged. The optional Compose override binds a writable `runtime/` directory for the node's compatibility SQLite path; new services run with the host UID/GID. Wallets are separate host bind mounts. New wallet, environment and SQLite files are private. The wizard refuses to replace existing wallets or nonidentical settings. Newly created files are tracked and removed on a normal error/interrupt before setup completes. A forced process kill or host crash can leave an already complete new file; rerunning the wizard inspects and reuses valid identities.

## Tests actually run on Tobia (Linux x86_64, Docker Engine)

| Check | Result |
| --- | --- |
| `PYTHONPATH=src .venv/bin/pytest -q tests/config/test_docker_first_setup.py tests/config/test_setup_wizard.py tests/crypto/test_mldsa_backend.py` | PASS: 62 tests. A host-compiled extension from the same pinned source was made available to the test checkout; the first attempt without it stopped in `tests/conftest.py` because this local `.venv` lacks `setuptools`. |
| `sh -n setup.sh` and `git diff --check` | PASS. |
| Docker setup image ML-DSA metadata, keygen, signature and verification known-answer test | PASS on linux/amd64. |
| `./setup.sh` through a real pseudo-terminal, passive Mainnet | PASS: built both images, wrote private config/database, printed commands, Compose config valid, started no service. |
| `./setup.sh` through a real pseudo-terminal, Mainnet node + miner + reward | PASS: distinct CHCQ/ML-DSA-44 miner and reward wallets, private files, printed registration peer `node:8333`, Compose config valid. |
| Repeat combined setup on same storage | PASS: both wallet identities and identical configuration reused without overwrite. |
| Temporary offline Mainnet node with UID 1000:1000, selected bind mounts and no published ports | PASS: opened persistent SQLite database and reported the expected Mainnet chain ID/genesis; stopped after the check. No P2P sync was attempted. |
| Direct Docker Compose `run` for mount inspection | NOT_RUN: this host's Docker daemon reported all predefined network pools exhausted. The same binds were verified with `docker run --network none`; wallet files and runtime directory were readable/writable as intended. |

The test wallets and database were created only below `/tmp/chipcoin-setup-*`. No existing Mainnet node, wallet, production Compose service or chain database was modified.

## Platform matrix and remaining tests

| Host | Code path | Actual clean-install result |
| --- | --- | --- |
| Linux x86_64 → linux/amd64 | Implemented | PASS for passive and combined setup on Tobia with Docker; fresh machine without any Python toolchain not separately provisioned, although the launcher did not call host Python. |
| Linux AArch64 → linux/arm64 | Implemented | NOT_RUN: no ARM host/runner available for native build, miner and wallet checks. |
| macOS Intel → linux/amd64 | Implemented | NOT_RUN: no Intel Mac test in this branch. Docker Desktop bind mounts/UID mapping remain unverified. |
| macOS Apple Silicon → linux/arm64 | Implemented | NOT_RUN: no Apple Silicon test in this branch. Native extension/miner build and bind mounts remain unverified. |

Also NOT_RUN: secret-import interaction in a real TTY, disk-full injection, forced-kill recovery, snapshot import in the new path, and a full isolated Docker Compose start with a working network. These checks are required before describing the corresponding platforms and failure modes as fully validated.

## External documentation

The public “Run a Node” website is maintained in the separate `chipcoin-central` repository. That source was not changed here. Before publishing this setup route, replace its host-Python wizard command with `git clone`, `cd chipcoin`, `./setup.sh`; explain that Docker builds the matching setup image, saves wallets/config/chain state under the selected network tree, and only prints later Compose commands. Link to `docs/setup-wizard.md` and retain the advanced host-Python route separately.
