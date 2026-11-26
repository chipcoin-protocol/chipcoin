# Chipcoin Core container: component notices

This notice accompanies the **v0.1.3 Core container**. The MIT grant for
original Chipcoin source is in `/usr/share/doc/chipcoin/LICENSE` and its
limits are in `LICENSE_SCOPE.md`. The combined image is not licensed as a
single MIT work.

- Vendored ML-DSA C implementation: upstream copyright and license choices
  are retained in `/usr/share/doc/chipcoin/mldsa-native-LICENSE`.
- Python distributions (`cryptography`, `cffi`, `pycparser`, `packaging`,
  `pip`): exact installed versions and license texts are retained in their
  `/usr/local/lib/python3.11/site-packages/*.dist-info/` directories.
- Python interpreter and Debian packages: their copyright/license notices
  are retained under `/usr/share/doc/<package>/copyright`. Debian package
  versions are inventoried in the build-specific SBOM distributed alongside
  the image. Source package information is available from the corresponding
  Debian release and the official Python image source; this statement does
  not replace any source-delivery obligation that may apply to redistribution.

The accompanying source archive includes Chipcoin's original source and the
vendored ML-DSA source and license. See `THIRD_PARTY_LICENSES.md` for upstream
references and use boundaries. Redistribution of a complete image must retain
the above notices and satisfy the terms of each component. The browser wallet
and externally supplied test-vector data are outside the Core MIT grant.
