# CivicDecision OS 0.8.1 release notes

Version 0.8.1 binds the public walkthrough and the Python release to one reviewable source state.
It preserves the 0.8.0 analytical corpus and all quantitative evidence while strengthening public
traceability, workflow integrity, documentation, and the browser dependency boundary.

## Public traceability

- The read-only walkthrough exposes `/build-info.json` with the clean commit, Git tree, immutable
  release tag, package version, build timestamp, hosting project identifier, and an explicit
  evidence boundary.
- The landing page, package metadata, install links, citation file, release builder, tests, and
  documentation all resolve to 0.8.1.
- The compact README workflow remains the primary entry point; the detailed artifact and
  anti-inflation ledger remains available without dominating the first screen.

## Release and supply-chain hardening

- Every third-party GitHub Action is pinned to an immutable reviewed commit.
- The release builder still requires two byte-identical wheels, sdists, and normalized source
  archives; strict metadata, archive, `RECORD`, checksum, fresh-install, no-Git rebuild, SBOM,
  license, secret, static-analysis, advisory, performance, quality, and claim-audit gates remain.
- `vinext` currently pins `image-size` 2.0.2 while the upstream advisory database lists no patched
  package. This release carries a checksum-bound `2.0.3-civic.1` rebuild containing only the two
  upstream zero-length parser fixes. Three hard-timeout adversarial tests cover ICNS, JXL, and
  HEIF inputs; the Node dependency audit reports no known vulnerability after the backport.

## Preserved quantitative evidence

No scenario, source, benchmark, DecisionPack, coverage result, or claimed workload was removed to
produce this release. The governed corpus remains 258 distinct highest-tier city records, 240
scenario designs, 188 executions, 98 DecisionPacks, 145 benchmark artifacts, and 800 Python tests.
The 76 completed and 20 withheld Tier-D results remain computational planning-support artifacts,
not observed interventions or policy outcomes.

## Scope boundary

A public URL and internal reproducibility do not establish production deployment, external validation,
independent security or domain review, real users, municipal adoption, or real-world impact. The
walkthrough is read-only, accepts no uploads, and does not issue municipal recommendations.
