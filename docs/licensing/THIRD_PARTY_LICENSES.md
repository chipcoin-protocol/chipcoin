# Third-party components and license references

The [Core MIT grant](LICENSE_SCOPE.md) does not relicense these components.
This inventory records the dependencies identified for Core v0.1.2
(`12e4dbc8974bd76885e30e6dacdf1b7be898e126`). Exact licenses and notices
for a particular binary distribution must be checked against its contents.

| Component | Version / source | License and attribution | Use |
| --- | --- | --- | --- |
| `mldsa-native` | Vendored upstream commit `9b0ee84f4cf399043eca59eca4e5f8531ca1d61b` | [Vendored license and copyright](../../vendor/mldsa-native/LICENSE): `Apache-2.0 OR ISC OR MIT`; upstream authors include the mldsa-native and mlkem-native projects, Dougall Johnson and Arm Limited. Vendored README/BUILDING materials mark `CC-BY-4.0`. | C source compiled into the ML-DSA-44 extension. Preserve upstream notices. |
| `cryptography` | `46.0.6` | [PyCA license](https://github.com/pyca/cryptography/blob/main/LICENSE): `Apache-2.0 OR BSD-3-Clause`. | Direct Python runtime dependency, including a native binding. |
| `cffi` | `2.1.1` | [Upstream license](https://github.com/python-cffi/cffi/blob/main/LICENSE): `MIT-0` in the audited image metadata. | Transitive Python runtime dependency. |
| `pycparser` | `3.11` | [Upstream BSD license](https://github.com/eliben/pycparser/blob/main/LICENSE): `BSD-3-Clause` in the audited image metadata. | Transitive Python runtime dependency. |
| `packaging`, `pip` | `26.3`, `24.0` in the audited amd64 image | [Packaging](https://github.com/pypa/packaging/blob/main/LICENSE): `Apache-2.0 OR BSD-2-Clause`; pip's image metadata declares MIT. | Runtime image tooling; not Core-authored. |
| Python and Debian base | `python:3.11.17-slim-trixie`, pinned in `Dockerfile` | [Official Python image notice](https://hub.docker.com/_/python): constituent packages have separate licenses. | Image includes Python and Debian system libraries/tools. See the [distribution backlog](DISTRIBUTION_BACKLOG.md). |
| Browser wallet npm graph | Locked in `apps/browser-wallet/package-lock.json` | Includes MIT runtime packages and separately licensed build tools. The entire browser wallet is excluded from the Core MIT grant; its licensing is deferred. | Browser extension, not the Core runtime image. |
| Crypto Connection Stratum vector | `docs/mining-pools/test-vectors/chc_stratum_vector.json` | Operator-supplied synthetic Devnet data; permission to publish does not establish an MIT grant. | Documentation/test data, expressly excluded. |

The [distribution backlog](DISTRIBUTION_BACKLOG.md) lists
open redistribution work. Preserve upstream license files and copyright
headers already in `vendor/`. Do not label a complete Docker image, browser
extension or the website as MIT merely because original Core source is MIT.
