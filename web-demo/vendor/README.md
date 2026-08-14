# Reviewed `image-size` security backport

`image-size-2.0.3-civic.1.tgz` is a local, narrowly scoped rebuild of upstream `image-size`
`v2.0.2` (`032c3347b86f09a2e16449e17537cf5e1009520c`). It applies only the upstream fixes below:

- `bdbe560bfd98af6feab93b46aed67f2f0a77e4d5` — advance zero-sized JXL and HEIF boxes;
- `0f6a6665a166c530ba126a8ab8608a0603cb49dc` — advance a zero-sized ICNS entry.

Those commits are the heads of upstream pull requests 439 and 453. They address
GHSA-5p2g-fcmc-qvqq and GHSA-w3rx-r6r6-pgpr while upstream has no published patched package.
No other library behavior was changed. The rebuilt package keeps the upstream MIT license and is
used only to satisfy `vinext`'s exact transitive dependency.

The committed tarball has SHA-256
`a106e83d1e6539950c1b8345ed8bf661d66b1461541f03551d8f6d58ea8d045d`. The adversarial Node tests
exercise all three zero-length inputs with a hard timeout. Replace this backport with an official
upstream release as soon as one is available and passes the same tests.
