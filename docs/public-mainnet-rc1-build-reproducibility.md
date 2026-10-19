# Public Mainnet RC1 Build Reproducibility

## Python and Docker inputs

`uv.lock` is the dependency lock. `docker/requirements-build.lock` is its
hash-checked requirements export, generated with:

```bash
UV_CACHE_DIR=/tmp/chipcoin-uv-cache uv export --locked --extra build --no-dev \
  --format requirements-txt --no-emit-project --offline \
  --output-file docker/requirements-build.lock
```

The Dockerfile uses immutable official Python multi-platform manifest digests
and the Debian Trixie OS image contents embedded in those manifests:

| Stage | Base | Manifest-list digest | OS/build input |
|---|---|---|---|
| Builder | `python:3.11.17-trixie` | `sha256:50cfccc707e8721201ee018bfd7f6a85d8eacf49c4f9f75833a2aba09a10411f` | Trixie image includes the compiler toolchain; build checks `gcc` and `libc6-dev` package versions. |
| Runtime | `python:3.11.17-slim-trixie` | `sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce` | Trixie OS packages are fixed by the immutable image digest. |

The Dockerfile no longer runs `apt-get update` or installs OS packages. Thus
there are no mutable APT indexes or package selections in the Docker build;
the exact OS package set is inherited from the base manifest digest. The
builder asserts compiler package presence/version in build output. Build for
the intended production architecture and record the resolved platform-specific
manifest digests as well as the index digests above.

Python runtime and build wheels are installed from the hash-checked export of
`uv.lock`; setuptools and wheel are pinned for the local project build. The
build receives `SOURCE_DATE_EPOCH=1792069138`, which identifies the selected
source baseline rather than the genesis timestamp. No genesis candidate is
part of these inputs.

## Browser artifact evidence

Two independent temporary copies ran `npm ci`, 89 wallet tests, and built
Chrome and Firefox from the current dirty source snapshot after the reviewed
toolchain update.

| Artifact tree | Build A tree-list SHA-256 | Build B tree-list SHA-256 | Result |
|---|---|---|---|
| Chrome | `c5732aa3416cd3456506bc8bb47e85a96df982ce9991b2559528b6d860d5044c` | same | byte-identical |
| Firefox | `16bf3098c54a6d2baa628234365ad6ef699a8ea0ce6860e1131ff7282f7c8ae7` | same | byte-identical |

The Explorer was independently installed, tested, typechecked and built twice;
both output trees hash to
`f316c3c853a3ca78b58907162c1d28ae6dc963b2738e803b141ce10d1143c11d`.
None of these temporary outputs was copied into a named production path.
Security disposition is recorded in `docs/public-mainnet-rc1-npm-security.md`.

## Docker image comparison protocol

Run two no-cache builds in independent clean source copies with the same
platform, Docker/BuildKit versions, source tree, lock files, and
`SOURCE_DATE_EPOCH`. Compare OCI manifest/config digests and each uncompressed
rootfs layer digest. If top-level image metadata differs while all rootfs
layers and extracted filesystem manifests match, record the differing config
fields rather than calling the image byte-identical. Preserve the full build
logs, `docker version`, `docker buildx version`, base manifest digests, image
IDs, layer digests, and an extracted-file SHA-256 inventory.

## Docker build evidence

Two independent clean `linux/amd64` builds were run with Docker Buildx
0.30.1 / BuildKit 0.26.2, `--no-cache --pull`, the same source snapshot,
immutable base indexes, lock file, and `SOURCE_DATE_EPOCH=1792069138`.
Build output passed `pip check`; both produced the application wheel
`chipcoin_v2-0.1.2-cp311-cp311-linux_x86_64.whl` with SHA-256
`f537bf886f3b86036e0b2650f97cfd51ba64a7650fccfac85f15e4c5ccfce473`.

The initial Docker exporter comparison found 206 timestamp-only differences.
The canonical comparison was therefore repeated with a dedicated BuildKit
container builder and OCI export using `rewrite-timestamp=true`. Two independent
no-cache exports are byte-identical (`cmp` PASS) and have the same tar SHA-256:
`37c88176e030ad7b4b8f513d8c99df119fd479cbb503f68f0337798ae6447f89`.
Both have OCI manifest digest
`sha256:e9ac0256cfba91a5fc35c30059ea8963864f8c8d061d4852ad904d927413e31f`
and config digest
`sha256:a1dfa370ec17eab62d37d6b9d2615598889cba92e1c0b5be7f878f960d41ed48`.
Exact OCI reproducibility is demonstrated for this source snapshot and
toolchain. These are local pre-freeze artifacts, not RC release artifacts.

The Dockerfile also uses `pip install --no-compile` to prevent generated
timestamp-based Python bytecode from varying between builds. This removed the
only bytecode-content variance found in the initial comparison. Temporary
images use local diagnostic tags only; no chain image/container was changed.

The builder/runtime index digests were checked against the official Python
image registry pages: [Python 3.11.17 Trixie](https://hub.docker.com/layers/library/python/3.11.17-trixie/images/sha256-e4cfe10f0d4050ab59208753e342080031550b7c0686a70bac220d1e2237631d)
and [Python 3.11 slim Trixie](https://hub.docker.com/layers/library/python/3.11-slim-trixie/).
