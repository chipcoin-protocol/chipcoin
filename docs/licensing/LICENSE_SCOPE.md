# Scope of the Chipcoin Core MIT license

The [MIT License](../../LICENSE) grants rights only in original Chipcoin material for
which Claudio Francesconi has authority to grant those rights. Its copyright
line does not claim ownership of third-party components. The `LICENSE` file
contains only the standard MIT text so GitHub can recognize it. The
[README licensing section](../../README.md#licensing) and this document specify the
scope and exclusions; the absence of a scope note inside `LICENSE` does not
extend the grant to excluded material.

## Included

- Original Chipcoin Core code in `src/chipcoin/`, including consensus, node,
  miner, wallet primitives, CLI and HTTP API.
- Original project scripts, Dockerfiles, Compose definitions, configuration
  templates and build tooling as **source files**. This does not license a
  complete Docker image or its constituent third-party software as MIT.
- Original tests and technical documentation, except the excluded materials
  below. A test's code may be MIT while input data from another source is not.

## Excluded from this MIT grant

- All of `apps/browser-wallet/`, including its source, tests, fixtures, icons,
  generated browser extension packages and bundled dependencies. The browser
  wallet will receive a separate licensing assessment.
- Browser-wallet-specific documentation under `docs/*browser*`.
- All of `vendor/mldsa-native/`. Its C implementation retains the upstream
  [license choices](../../vendor/mldsa-native/LICENSE) and copyright notices; some
  vendored documentation identifies `CC-BY-4.0`. Linking it into the Core does
  not transfer its copyright to Chipcoin.
- Logos, icons, artwork, brand marks and the Chipcoin visual identity, wherever
  displayed or stored. The founder confirms authorship but reserves these
  materials outside this software license. Permission to use Core code does
  not grant trademark or brand rights.
- Machine-readable vector data in `docs/mining-pools/test-vectors/*.json`,
  including the Crypto Connection Stratum vector. Other standalone fixtures
  or data whose provenance is not established are likewise excluded pending
  individual clearance. Original verifier and test *code* remains covered.
- Third-party Python/npm/Debian packages, system libraries, fonts and other
  external material, whether imported, linked or distributed with Chipcoin.
  See [third-party licenses](THIRD_PARTY_LICENSES.md).
- Complete Docker/OCI images and browser extension packages as combined
  artifacts. Their components retain their own terms.
- The Chipcoin website, which is maintained in a separate repository.

If a file has its own copyright or license notice, that notice takes priority
for that file. An unclear provenance should be resolved before representing
the material as MIT-covered. This document does not retroactively change the
tagged `mainnet-v0.1.2` source archive or any previously published image.
