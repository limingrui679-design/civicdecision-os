# Changelog

All notable changes are recorded here. CivicDecision OS follows semantic versioning only after
the first stable release; while the project is alpha, minor versions may include contract changes.

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
- Added nine measured local performance budgets. All passed on the recorded macOS arm64 / CPython
  3.12 environment; these measurements are not production load or SLA evidence.

### Verification scale

- Preserved 800 automated tests while adding release-archive validation to an existing integrated
  test path.
- The Milestone-8 snapshot records 97.102% statement coverage, 91.091% branch coverage, and 95.896%
  combined coverage after the release-assurance module and adversarial archive gates were added.
- Exact repository regeneration now covers the original reference DecisionPacks, Tier-G catalog,
  30 Tier-S bundles, 145 analytical benchmark runs, 707 Tier-D files, 282 scenario-library files,
  and 338 product files.

### Boundaries

- This release does not claim a public hosted service, production authorization, external domain
  review, independent penetration or accessibility testing, municipal adoption, or field impact.
- A clean local security scan or dependency audit is time-bounded evidence, not a guarantee that
  the software has no vulnerability.
