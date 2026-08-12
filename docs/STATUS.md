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
- Seven loadable connectors span climate, demography, disaster, health, public service, seismic,
  and multinational statistics. Each has query bounds, source terms, record semantics, and
  limitations in a deterministic public catalog.
- The committed public samples contain 81 defined observation units total: five USGS events,
  ten CDC tracts, one World Bank indicator value, 28 NASA point-date-parameter values, five FEMA
  declaration-area records, 27 non-null Eurostat cells, and five NYC 311 requests.
- One completed and one infeasible heat-access DecisionPack rebuild exactly from committed inputs.
- The completed bounded run evaluates 55 combinations, retains 16 feasible plans, and runs five
  declared service-radius sensitivity cases. These are computational results, not policy impact.
- 145 automated tests pass with 93.09% branch-aware coverage; Ruff and strict mypy pass locally.
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
