# Contributing

CivicDecision OS welcomes source connectors, city adapters, analytical engines, scenarios,
tests, documentation, and reproducible negative results. A contribution is accepted on the
strength of inspectable artifacts—not the size of a claim.

## Non-negotiable evidence rules

- Keep `observed`, `estimated`, `causal`, `simulated`, `optimized`, and `proposed` distinct.
- Public-data demonstrations are not client deployments or municipal adoption.
- Historical replay is not a prospective real-world effect.
- Causal evidence requires an estimand, identification strategy, diagnostics, and limitations.
- Preserve failed, infeasible, timed-out, and insufficient-evidence runs when they are valid.
- Never commit credentials, private personal data, restricted client data, or unlicensed data.
- Every downloaded artifact needs a query, retrieval time, source URL, license, hash, count,
  geographic scope, temporal scope, and limitations.

## Local quality gate

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
make check
```

The configured coverage.py combined line-and-branch floor is 90%. New analytical, connector, or
product-surface code must add positive, negative, integrity, and boundary tests. Do not reduce the
floor to make a change pass, and report statement and branch coverage separately rather than
calling the combined percentage either one.

Changes that affect product projections must also run:

```bash
civicdecision catalog build-product --root . --output catalog/product
python scripts/verify_repository.py
node --check src/civicdecision/web/assets/app.js
```

The product build is accepted only when the committed 338-file tree, 336-entry artifact manifest,
19-path OpenAPI document, 28 Schemas, web hashes, and portable checksums rebuild exactly. Browser
changes require desktop and mobile interaction inspection; a screenshot alone is not functional
evidence.

Changes to packaging, dependencies, archive handling, version metadata, or public release inputs
must also install `.[release]` and run the clean-tree process in
[`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md). Do not hand-edit the hash lock, SBOM, audit
reports, or checksum inventories. Release validation must exercise an installed wheel from a
source archive with no Git metadata; an editable install is not release evidence.

## Add a public source

1. Confirm official access, terms, attribution, geographic scope, and update behavior.
2. Add a bounded query model and safe connector under `src/civicdecision/connectors/`.
3. Write raw bytes atomically and emit a `SourceManifest` beside the artifact.
4. Test HTTP failure, invalid JSON, unsafe shape, limit overflow, hash verification, and cleanup.
5. Commit only a small lawful sample unless the repository's data policy explicitly permits more.

## Add a scenario or analytical engine

1. Validate the scenario DSL before executing analytical code.
2. Declare every assumption and hard constraint.
3. Retain infeasible and insufficient-evidence outcomes.
4. Include reversal tests and value-of-information guidance for completed DecisionPacks.
5. Generate human-readable output from the same validated DecisionPack, never a separate source.

## Add a data-only adapter plugin

1. Use `civicdecision plugins scaffold`; do not add executable plugin code to the version-1
   package contract.
2. Declare every adapter file in `plugin.json` with a normalized path, byte count, and SHA-256
   digest.
3. Keep `enabled_by_default=false` and validate against one exact plugin-ID allowlist entry.
4. Do not use symbolic links, absolute/parent paths, unmanifested assets, or overlapping city IDs.
5. Treat successful package validation as byte-and-contract validation, not proof that a source is
   true, licensed for every use, analytically ready, deployed, or impactful.

## Pull-request evidence

State exactly what changed, which claims are supported, the commands run, the test result,
the artifact hashes, and what remains unverified. Screenshots and README statements do not
replace code, manifests, logs, or reproducible outputs.

Do not describe a local candidate as a public release, hosted service, signed artifact, remote-CI
success, external validation, adoption, or impact. Those claims require separate public or
third-party evidence.
