# Reproducible release process

This process turns one clean source commit into an independently inspectable local release
candidate. It is intentionally stricter than `python -m build`: any missing tool, inconsistent
archive, unsafe path, unresolved scan result, changed golden artifact, or failed smoke test stops
the build before the output directory is created.

## Prerequisites

- CPython 3.11 or 3.12; the current evidence run uses 3.12.
- A clean Git worktree for the exact subject commit.
- Development and release dependencies installed with `python -m pip install -e '.[dev,release]'`.
- Network access for the fresh hash-locked dependency install and advisory query. Source and
  product reconstruction themselves use only committed inputs.

The runtime dependency contract is [`requirements/runtime-api.lock`](../requirements/runtime-api.lock).
Every requirement is exactly pinned and carries one or more SHA-256 distribution hashes. Regenerate
it only after intentionally reviewing dependency changes:

```bash
pip-compile pyproject.toml --extra api --strip-extras --resolver backtracking \
  --generate-hashes --output-file requirements/runtime-api.lock
```

## One-command candidate

From a clean checkout:

```bash
python scripts/build_release_candidate.py --output-dir dist/release-0.8.0
```

The builder derives `SOURCE_DATE_EPOCH` from the subject commit. An explicit epoch may be supplied
for an independent repeat:

```bash
python scripts/build_release_candidate.py \
  --source-date-epoch 1786579200 \
  --output-dir dist/release-0.8.0-repeat
```

`--allow-dirty` exists only for development of the release process. Its use is recorded as
`dirty=true` and is not acceptable final release evidence.

## Enforced gates

### Source identity and reproducible builds

1. Record the full commit, branch, clean/dirty state, version, tool versions, and normalized epoch.
2. Build the wheel and sdist twice in independent directories using the same fixed build inputs.
3. Require byte equality for the two wheels and the two sdists.
4. Validate one exact wheel and sdist inventory with archive-member and expansion limits.
5. Convert the validated sdist into a normalized source ZIP twice and require byte equality.

### Archive integrity

- Reject absolute paths, `..`, backslashes, NULs, duplicates, symlinks, hard links, devices,
  FIFOs, encrypted members, caches, bytecode, Git metadata, virtual environments, and build output.
- Require exactly one sdist root and the expected release inputs, catalog checksums, source,
  scripts, documentation, tests, workflows, lock file, and verification evidence.
- Require Metadata 2.4, package name/version, Python `>=3.11`, MIT license expression, license file,
  console entry point, type marker, and all four packaged Web assets.
- Decode every wheel `RECORD` entry and verify its URL-safe SHA-256 digest and byte count. The
  `RECORD` file must cover every file exactly once and leave only its own hash and size blank.
- Run strict Twine metadata and `check-wheel-contents` checks as independent validators.

### Fresh installed behavior

1. Create a new virtual environment.
2. Install `requirements/runtime-api.lock` using `--require-hashes --no-cache-dir`.
3. Install the wheel using `--no-index --no-deps`; dependency resolution cannot mask a lock error.
4. Run `pip check`.
5. Use isolated Python mode and prove that `civicdecision` imports from the installed environment,
   not the extracted source tree.
6. Smoke-test the installed CLI, local SDK, 258-city and 240-design catalog, 30 design families,
   19-path API, representation-scoped ETags, negative responses, security headers, Web explorer,
   and data-only plugin scaffold/validation.
7. Run the full repository verifier inside the extracted sdist, which contains no `.git`. Every
   golden artifact tree must rebuild byte-for-byte from committed inputs.

### Supply chain and security evidence

- Bandit: fail on medium-or-higher severity and confidence findings in `src/civicdecision`.
- Detect Secrets: freshly scan source, scripts, tests, docs, governance, workflows, and root config
  offline; inline allowlists are limited to identified public dataset URLs.
- pip-audit: audit the exact hashed runtime lock and fail on a known advisory at check time.
- CycloneDX: validate a reproducible 1.6 JSON SBOM for the installed runtime.
- pip-licenses: inventory the installed package name, version, declared license, and project URL.
- Performance: require all nine committed local budgets to pass for the same software version.

## Output layout

The builder publishes only after every gate passes:

```text
dist/release-0.8.0/
├── civicdecision-0.8.0-release/
│   ├── civicdecision-0.8.0-py3-none-any.whl
│   ├── civicdecision-0.8.0.tar.gz
│   ├── civicdecision-0.8.0-source.zip
│   ├── release-report.json
│   ├── installed-wheel-smoke.json
│   ├── no-git-verification.json
│   ├── dependency-audit.json
│   ├── detect-secrets.json
│   ├── bandit.json
│   ├── sbom.cdx.json
│   ├── third-party-licenses.json
│   ├── performance.json
│   ├── runtime-api.lock
│   ├── RELEASE_NOTES.md
│   └── SHA256SUMS
├── civicdecision-0.8.0-release-bundle.zip
└── civicdecision-0.8.0-release-bundle.zip.sha256
```

`SHA256SUMS` covers every individual asset by portable basename. The detached sidecar covers the
bundle, avoiding a circular self-hash. The embedded report intentionally excludes its own bundle
hash for the same reason.

## Independent verification

Verify the bundle hash before extraction:

```bash
shasum -a 256 -c civicdecision-0.8.0-release-bundle.zip.sha256
```

Then verify the individual assets from inside the extracted release directory:

```bash
shasum -a 256 -c SHA256SUMS
```

Install only after both inventories pass. A reviewer can repeat the build with the recorded source
commit, tool versions, and epoch, then compare the wheel, sdist, and source-ZIP hashes.

## Deliberately external gates

The local builder does not manufacture evidence for public state. A public release still requires
a pushed commit and tag, remote CI and CodeQL results, a published release page, and a signature or
trusted provenance mechanism. A hosted service additionally requires authentication and
authorization where applicable, TLS and reverse-proxy controls, rate limits, monitoring, backup,
privacy review, accessibility testing, penetration testing, and deployment-specific SBOM coverage.
