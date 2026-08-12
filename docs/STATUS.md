# Verified status

Updated: 2026-08-12

## Current milestone

Milestone 0 protocol and evidence foundation is verified locally. Milestone 1—expand the real
data foundation and build normalized city-adapter semantics—is in progress.

## Verified now

- Three deterministic versioned JSON Schemas regenerate byte-for-byte.
- Six evidence types have type-specific positive and rejection tests.
- Completed DecisionPacks require formal reversal tests and value-of-information guidance.
- Failed, insufficient-evidence, infeasible, and timed-out statuses validate as negative releases.
- USGS and CDC connectors safely write real public artifacts with hashes, counts, query, license,
  scope, limitations, and schema fingerprints.
- The committed public samples contain 15 records total: five USGS events and ten CDC tracts.
- One completed and one infeasible heat-access DecisionPack rebuild exactly from committed inputs.
- The completed bounded run evaluates 55 combinations, retains 16 feasible plans, and runs five
  declared service-radius sensitivity cases. These are computational results, not policy impact.
- 105 automated tests pass with 97.85% branch-aware coverage; Ruff and strict mypy pass locally.
- Portable `SHA256SUMS` entries contain filenames rather than local absolute paths.
- `scripts/verify_repository.py` independently validates and exactly rebuilds all golden artifacts.

## Implementing next

- Connector registry, licensing metadata, paging, caching, and broader global source families.
- Canonical place, geography, time, measure, network, facility, event, and policy semantics.
- Real Tier-G city catalog plus the first complete standardized/deep adapters.
- Network routing, forecast baselines, uncertainty, and scalable solver interfaces.
- REST API, Python SDK, adapter SDK, web UI, and hosted read-only demo.
- CI/security workflows require a real remote run before their results can be called verified.

## Explicitly not complete

- 250-city global layer, 30 standardized cities, or 8 deep-city adapters.
- Urban knowledge graph.
- Forecasting, causal, simulation, optimization, reversal, or value-of-information engines.
- 240 scenarios, 40 historical replays, or 100 decision tasks.
- Web/API/SDK ecosystem and public hosted demo.
- External review, real users, municipal adoption, or real-world impact.
