# CivicDecision OS 0.8.0 release notes

Version 0.8.0 is the first release candidate that unifies the full evidence-typed decision system,
the audited 240-design scenario library, and reproducible supply-chain evidence.

## What a reviewer can inspect

- 250 Tier-G global city identities, 30 standardized Tier-S public-data bundles, and eight deep
  Tier-D city bundles.
- 90 versioned source manifests, 145 analytical benchmark runs, 188 scenario executions, 98
  DecisionPacks, and explicit negative releases that preserve insufficient or infeasible evidence.
- 240 non-duplicative scenario designs in 30 families. Twelve map to reference implementations;
  228 remain design-only and do not imply city execution or a newly implemented method.
- A 338-file deterministic product projection shared by the store, CLI, SDK, 19-path read-only API,
  evidence explorer, and data-only plugin SDK.
- Exact isolated reconstruction of the Tier-G, Tier-S, benchmark, Tier-D, scenario-library, and
  product trees from committed inputs.
- A release bundle with a hash-locked runtime, strict wheel/sdist validation, installed-product
  smoke evidence, no-Git reconstruction evidence, advisory audit, secret scan, Bandit report,
  CycloneDX 1.6 SBOM, license inventory, local performance evidence, and portable checksums.

## Quantified implementation evidence

- 800 passing automated tests in the release-hardening tree.
- Milestone-8 coverage: 96.987% statements, 90.422% branches, and 95.705% combined after the
  archive-assurance layer and its adversarial release tests are included.
- 28,680 pairwise design comparisons with no collision and no pair above the declared 0.90 review
  threshold.
- 76 completed Tier-D planning-support runs and 20 explicit insufficient-evidence releases; these
  are computational results, not observed policy outcomes.
- Nine passing local performance budgets covering cold catalog initialization, store/API reads,
  compound filters, details, and exact library/product builds.

## Scope boundary

This candidate demonstrates architecture, implementation depth, internal reproducibility, and
claim discipline. It does not establish public hosting, production readiness, external validation,
real users, municipal adoption, or real-world impact. The repository keeps those external gates
visible rather than replacing them with simulated claims.
