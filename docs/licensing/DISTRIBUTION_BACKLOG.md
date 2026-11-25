# Distribution licensing backlog

This is separate from the [MIT license for original Core source](../../LICENSE_SCOPE.md).
It records follow-up work identified in the v0.1.2 licensing audit; it does
not change the historical release or assert that existing artifacts are cleared.

1. **Existing official Docker artifacts:** confirm which license/copyright
   notices and source-access obligations apply to the exact Debian, Python,
   OpenSSL, `mldsa-native` and other native components shipped in each image.
   Audit already-published artifacts as well as future ones; provide any
   missing notices through a prospective distribution channel without
   altering immutable v0.1.2 archives or tags.
2. **Future Docker builds:** generate a build-specific SBOM and third-party
   notice package from the *final* image, retain vendor copyright and license
   text, and verify notice availability before publication. Do not describe
   the complete image as MIT.
3. **Browser wallet:** perform its own licensing/provenance review, including
   bundled npm dependencies, generated ZIPs, icons and fixtures, before
   assigning a license or publishing a redistribution statement.
4. **External test data:** obtain an explicit reuse/license grant or retain
   exclusions for externally supplied and provenance-uncertain fixtures.

Owner and target release for these follow-ups remain to be assigned. No Core
runtime, dependency or release artifact change is implied by this backlog.
