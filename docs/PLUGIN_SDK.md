# Data-only adapter plugin SDK

## Why the first plugin contract is data-only

Arbitrary third-party Python execution would create a large trust boundary before the project has
signed releases, sandboxing, capability permissions, or an authenticated review workflow.
Version 1 therefore validates portable data packages and never imports or executes plugin code.

A valid package has exactly this shape:

```text
example-plugin/
  plugin.json
  adapters/
    sample-city.json
```

No unmanifested file is accepted. Python files, extra assets, missing files, symbolic links,
absolute paths, parent traversal, duplicate paths, oversized documents, hash mismatches, duplicate
city IDs, registry overlaps, and packages outside the exact plugin-ID allowlist fail closed.

## Create a starter

```bash
civicdecision plugins scaffold \
  --output ./example-plugin \
  --plugin-id example.adapter \
  --name 'Example Adapter' \
  --author 'Example Author'
```

The command refuses to overwrite an existing output directory. The generated package validates
immediately but is intentionally a sample Tier-G identity with a stated evidence gap; it is not a
real city integration.

## Validate a package

```bash
civicdecision plugins validate \
  ./example-plugin \
  --expected-plugin-id example.adapter
```

The expected ID is an exact allowlist entry, not a discovery pattern. Validation checks:

1. the root is a regular directory and not a symbolic link;
2. `plugin.json` has a bounded size and satisfies `PluginManifest`;
3. the observed file inventory exactly matches the manifest;
4. every adapter path is normalized under `adapters/`;
5. each adapter file is regular, bounded, contained, and hash-matched;
6. each adapter satisfies the stable City Adapter protocol;
7. city identifiers are unique; and
8. the package hash binds the canonical manifest and verified artifact hashes.

## Registry behavior

`PluginRegistry` requires a nonempty, sorted, unique exact allowlist and a bounded package count.
It rejects duplicate plugin registration and city-ID overlap between installed packages. Registry
summaries expose plugin identity, version, capabilities, city IDs, package hash, and evidence
boundary without exposing a local filesystem path.

Registration is in-memory validation only. The REST API does not scan directories, load entry
points, merge plugins automatically, or enable packages by default.

## Manifest evidence boundary

The manifest field `enabled_by_default` is required to be `false`. A valid package proves that its
declared bytes and City Adapter documents passed the local contract. It does not prove that the
sources are true, current, licensed for every use, locally representative, analytically ready,
approved, deployed, or impactful.

Future executable plugins require a new reviewed protocol with signatures, provenance,
permission declarations, process isolation, resource limits, network/file policies, revocation,
and an audit log. They must not be introduced by silently widening this data-only contract.
