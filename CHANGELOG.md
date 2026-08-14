# Changelog

All notable changes are recorded here. CivicDecision OS follows semantic versioning only after
the first stable release; while the project is alpha, minor versions may include contract changes.

## Unreleased

## 0.8.1 — 2026-08-14

### Public product and documentation

- Published a public, read-only guided walkthrough at
  `https://civicdecision-os.limingrui2.chatgpt.site` with an evidence-gate overview, completed and
  deliberately infeasible Suffolk reference runs, explicit claim boundaries, and a local
  quickstart. This is a static product walkthrough, not a hosted analytical service.
- Rebuilt the README entry path around one user job, a verified snapshot table, the public
  walkthrough, a five-minute local start, one golden case, direct release assets, and a captured
  product image while retaining the full technical evidence inventory.
- Added a strict MkDocs build with start routing, three task-oriented tutorials, packaging status,
  an external-review protocol, a launch playbook, and adoption-metric boundaries.

### Review, community, and distribution

- Added citation metadata, a code of conduct, public roadmap, structured bug/reproduction/domain
  review forms, pull-request evidence checklist, and weekly dependency configuration.
- Added a bounded GitHub traffic snapshot script and scheduled artifact-only workflow; traffic,
  clones, downloads, forks, and stars remain explicitly separated from adoption and impact.
- Marked deterministic catalog, benchmark, schema, and verification projections as generated for
  review presentation without removing any evidence files.
- Added a tag-triggered GitHub Release workflow and exposed the verified v0.8.0 wheel, sdist,
  no-Git source ZIP, checksums, and SBOM as direct assets on the existing release.
- Added a machine-readable hosted-build identity endpoint that binds the public walkthrough to its
  clean commit, tree, release tag, package version, build time, and hosting project identifier.
- Pinned every third-party GitHub Action to an immutable reviewed commit.
- Backported the two upstream `image-size` zero-length parser fixes into a checksum-bound local
  package while upstream has no patched release; three hard-timeout adversarial tests cover ICNS,
  JXL, and HEIF inputs, and the web dependency audit reports zero known vulnerabilities.

### Boundaries

- No external reviewer, independent reproduction, PyPI publication, municipal adoption,
  production deployment, policy effectiveness, or real-world impact is claimed by these changes.

## 0.8.0 — 2026-08-13

### Scenario-design library

- Added 240 strict scenario designs across 30 substantive decision families and seven application
  suites. Each family contains diagnose, forecast, prioritize, site, allocate, schedule,
  stress-test, and evaluate designs.
- Added a full 28,680-pair anti-duplication audit with a fixed 0.90 review threshold. The committed
  library has no title, question, signature, or high-similarity collisions; its highest token
  Jaccard similarity is 0.646154.
- Bound twelve designs one-to-one to the existing Tier-D templates as reference implementations.
  The remaining 228 are explicitly design-only, have no city executions, and claim no new method.
- Added five strict library Schemas, a 280-entry manifest, portable checksums, coverage matrices,
  human-readable reports, and byte-exact isolated regeneration.

### Product surfaces

- Expanded the fail-closed artifact store, CLI, SDK, read-only REST API, static product projection,
  and evidence explorer to cover the complete design library.
- Expanded the product projection to 338 files: 336 manifest-indexed artifacts, one manifest, and
  one checksum inventory. It now contains 240 design details, 30 family details, 28 Schemas,
  19 OpenAPI paths, and four hashed browser assets.
- Added representation-scoped weak ETags bound to software version, route, and normalized query.
  Validators cannot suppress a different resource or a 404 response.
- Added compound filters, complete design and family drawers, six audit indicators, mobile layout
  checks, and strict preservation of negative releases and evidence boundaries.

### Release engineering and assurance

- Established `0.8.0` as one-source package and API version metadata with PEP 639 MIT licensing and
  Metadata 2.4 for compatibility with current publishing validators.
- Added a fully pinned, hash-locked API/runtime dependency set.
- Added fail-closed wheel and sdist validators covering safe paths, archive budgets, required
  inventory, package metadata, web assets, console entry point, link rejection, and every wheel
  `RECORD` digest and size.
- Added a clean-environment release builder that performs two byte-identical builds, two identical
  deterministic source ZIP writes, strict metadata checks, wheel-content checks, hashed-lock
  installation, `pip check`, installed CLI/SDK/API/Web/plugin smoke tests, and a full no-Git golden
  rebuild.
- Added Bandit, offline secret scanning, advisory-based dependency audit, a CycloneDX 1.6 SBOM,
  third-party license inventory, complete SHA-256 inventories, and a deterministic release bundle.
- Added a recorded 12-significant-digit Tier-D numeric contract, including pre-hash stochastic
  normalization, and aligned CI secret scanning with the release builder's controlled source-file
  inventory so supported operating systems verify the same evidence scope.
- Added nine measured local performance budgets. All passed on the recorded macOS arm64 / CPython
  3.12 environment; these measurements are not production load or SLA evidence.

### Verification scale

- Preserved 800 automated tests while adding release-archive validation to an existing integrated
  test path.
- The Milestone-8 snapshot records 97.114% statement coverage, 91.129% branch coverage, and 95.914%
  combined coverage after the release-assurance module and adversarial archive gates were added.
- Exact repository regeneration now covers the original reference DecisionPacks, Tier-G catalog,
  30 Tier-S bundles, 145 analytical benchmark runs, 707 Tier-D files, 282 scenario-library files,
  and 338 product files.

### Boundaries

- This release does not claim a public hosted service, production authorization, external domain
  review, independent penetration or accessibility testing, municipal adoption, or field impact.
- A clean local security scan or dependency audit is time-bounded evidence, not a guarantee that
  the software has no vulnerability.
