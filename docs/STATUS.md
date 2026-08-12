# Verified status

Updated: 2026-08-12

## Current milestone

Milestone 3—the reproducible 30-city Tier-S standardized layer—is verified locally. The next
milestone adds general forecast, uncertainty, simulation, and optimization engines before any
standardized descriptive screen is promoted to a decision workflow.

## Verified now

- Nine deterministic versioned JSON Schemas regenerate byte-for-byte.
- Six evidence types have type-specific positive and rejection tests.
- Completed DecisionPacks require formal reversal tests and value-of-information guidance.
- Failed, insufficient-evidence, infeasible, and timed-out statuses validate as negative releases.
- Eight loadable connectors span climate, demography, disaster, geography, health, public service,
  seismic, and multinational statistics. Each has bounded or fully identified source scope,
  source terms, record semantics, schema checks, and limitations in a deterministic catalog.
- Forty-one verified source manifests cover 100,842 heterogeneous source units: 34,086 GeoNames
  rows, 65,880 Tier-S NASA POWER parameter-date values, 795 Tier-S World Bank response rows, and
  81 earlier bounded units. They are not counted as interchangeable or independent policy
  observations.
- A deterministic Tier-G catalog contains 250 unique city points across 244 GeoNames country or
  territory codes: 244 source-population leaders and six global fills.
- The city build emits a 250-row coverage matrix, a 494-geography semantic bundle, a 494-node /
  250-edge evidence-typed seed graph, and four portable checksum entries.
- The verifier rebuilds all global-city artifacts from the committed GeoNames ZIP and manifest in
  a temporary directory and requires exact byte equality.
- Thirty Tier-S bundles each bind GeoNames identity, one complete 2024 NASA POWER six-parameter
  point series, and three 2023 World Bank country-context artifacts.
- All 30 Tier-S quality reports pass six required checks, including exact parsed-to-manifest count,
  366 aligned daily keys per parameter, no source fill values, and coordinate/query alignment.
- The Tier-S layer contains 330 evidence-typed metrics, 150 source bindings, and 90 independent
  scenario records: 60 descriptive screens and 30 explicit `insufficient-evidence` releases.
- Every Tier-S scenario record has `recommendation_issued=false`; none is a DecisionPack,
  forecast, causal result, simulation, optimization, or observed intervention outcome.
- The registry records one pre-target exclusion (Taipei at Tier-G rank 19) and its missing-source
  reasons; the 30th eligible bundle is Jeddah at Tier-G rank 31.
- The 30-row coverage matrix and cross-city CSV/Markdown report regenerate byte-for-byte with the
  registry, bundles, run files, and recursive checksum inventory.
- One completed and one infeasible heat-access DecisionPack rebuild exactly from committed inputs.
- The completed bounded run evaluates 55 combinations, retains 16 feasible plans, and runs five
  declared service-radius sensitivity cases. These are computational results, not policy impact.
- 240 automated tests pass with 95.12% branch-aware coverage; the 69-test Tier-S standardized
  package suite reaches 100% statement and branch coverage; Ruff and strict mypy pass locally.
- Portable `SHA256SUMS` entries contain filenames rather than local absolute paths.
- `scripts/verify_repository.py` independently validates and exactly rebuilds all golden artifacts.

## Implementing next

- Broader connector registry, licensing metadata, paging, caching, and 25–35 source families.
- Normalized network and policy semantics on top of the verified geography, time, measure,
  observation, facility, event, and graph contracts.
- The first complete deep-city adapters with official local boundaries and local sources.
- Network routing, forecast baselines, uncertainty, and scalable solver interfaces.
- REST API, Python SDK, adapter SDK, web UI, and hosted read-only demo.
- CI/security workflows require a real remote run before their results can be called verified.

## Explicitly not complete

- Eight deep-city adapters. The 30 Tier-S bundles are complete for standardized descriptive
  screening only and deliberately do not imply deep analytical readiness.
- A production-scale urban knowledge graph. The current seed graph has 494 nodes and 250 edges.
- Forecasting, causal, simulation, optimization, reversal, or value-of-information engines.
- 240 scenarios, 40 historical replays, or 100 decision tasks.
- Web/API/SDK ecosystem and public hosted demo.
- External review, real users, municipal adoption, or real-world impact.
