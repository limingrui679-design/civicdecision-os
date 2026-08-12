# Verified status

Updated: 2026-08-12

## Current milestone

Milestone 2—the reproducible 250-city Tier-G foundation—is verified locally. The next milestone is
the standardized adapter layer: capability declarations, normalized city bundles, and at least
three validated scenario protocols for each of 30 Tier-S cities.

## Verified now

- Six deterministic versioned JSON Schemas regenerate byte-for-byte.
- Six evidence types have type-specific positive and rejection tests.
- Completed DecisionPacks require formal reversal tests and value-of-information guidance.
- Failed, insufficient-evidence, infeasible, and timed-out statuses validate as negative releases.
- Eight loadable connectors span climate, demography, disaster, geography, health, public service,
  seismic, and multinational statistics. Each has bounded or fully identified source scope,
  source terms, record semantics, schema checks, and limitations in a deterministic catalog.
- The eight verified source manifests cover 34,167 records: 34,086 GeoNames populated-place
  gazetteer rows plus 81 bounded analytical/public-service units across USGS, CDC PLACES, World
  Bank, NASA POWER, OpenFEMA, Eurostat, and NYC 311. The gazetteer rows are not counted as
  independent policy observations.
- A deterministic Tier-G catalog contains 250 unique city points across 244 GeoNames country or
  territory codes: 244 source-population leaders and six global fills.
- The city build emits a 250-row coverage matrix, a 494-geography semantic bundle, a 494-node /
  250-edge evidence-typed seed graph, and four portable checksum entries.
- The verifier rebuilds all global-city artifacts from the committed GeoNames ZIP and manifest in
  a temporary directory and requires exact byte equality.
- One completed and one infeasible heat-access DecisionPack rebuild exactly from committed inputs.
- The completed bounded run evaluates 55 combinations, retains 16 feasible plans, and runs five
  declared service-radius sensitivity cases. These are computational results, not policy impact.
- 169 automated tests pass with 93.59% branch-aware coverage; Ruff and strict mypy pass locally.
- Portable `SHA256SUMS` entries contain filenames rather than local absolute paths.
- `scripts/verify_repository.py` independently validates and exactly rebuilds all golden artifacts.

## Implementing next

- Broader connector registry, licensing metadata, paging, caching, and 25–35 source families.
- Normalized network and policy semantics on top of the verified geography, time, measure,
  observation, facility, event, and graph contracts.
- Thirty complete standardized adapters and the first complete deep-city adapters.
- Network routing, forecast baselines, uncertainty, and scalable solver interfaces.
- REST API, Python SDK, adapter SDK, web UI, and hosted read-only demo.
- CI/security workflows require a real remote run before their results can be called verified.

## Explicitly not complete

- 30 standardized cities or 8 deep-city adapters. The 250-city Tier-G point catalog is complete,
  but it deliberately does not imply standardized or deep analytical readiness.
- A production-scale urban knowledge graph. The current seed graph has 494 nodes and 250 edges.
- Forecasting, causal, simulation, optimization, reversal, or value-of-information engines.
- 240 scenarios, 40 historical replays, or 100 decision tasks.
- Web/API/SDK ecosystem and public hosted demo.
- External review, real users, municipal adoption, or real-world impact.
