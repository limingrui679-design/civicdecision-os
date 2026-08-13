# CivicDecision OS

**The open-source compiler for urban interventions.**

CivicDecision OS turns versioned public data, urban networks, policy constraints, simulation results, and optimization runs into reproducible `DecisionPack` artifacts.

The project is being built around one strict pipeline:

```text
intervention definition
  -> evidence typing
  -> affected people and network
  -> historical replay or simulation
  -> constrained optimization
  -> decision reversal and value of information
  -> reproducible DecisionPack
```

## Current status

This repository is an early implementation. The global scale described in the project blueprint is a target, not a completed result. Current, verified capabilities are listed in [`docs/STATUS.md`](docs/STATUS.md); the complete requirement-to-evidence matrix is in [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md).

The fourth implementation milestone establishes 17 generated public contracts, the evidence type
system, deterministic validation, eight real public-data connectors, a reproducible Tier-G catalog
of 250 city points, 30 Tier-S standardized descriptive bundles, five transparent analytical
engines, 40 held-out historical replays, and 100 bounded optimization tasks. Tier G means global
discoverability and Tier S means bounded cross-city screening; neither means a deep city adapter,
production deployment, municipal adoption, or real-world impact.

## Verified reference workflow

The repository now contains one completed and one deliberately infeasible heat-access reference
run over a bounded ten-tract CDC PLACES sample. The workflow validates the source hash, separates
artifact observation from area-level estimation, simulates straight-line coverage, exhaustively
enumerates 55 candidate combinations, retains infeasible alternatives, tests five service-radius
conditions, ranks three evidence gaps, and emits JSON plus Markdown from the same DecisionPack.

This demonstrates implementation behavior only. Tract centroids are not verified facilities,
radius is not travel time, the population proxy is not individual demand, and the selected option
is not a municipal recommendation.

Current local quality evidence is recorded in
[`verification/milestone-4-analytical-engines.json`](verification/milestone-4-analytical-engines.json)
and [`verification/milestone-4-coverage.json`](verification/milestone-4-coverage.json). The
independent verifier regenerates Schemas, both reference outputs, all four global-city artifacts,
the complete standardized-city tree, and all milestone-4 benchmark artifacts in a temporary
directory and requires exact bytes.

The current source catalog contains eight verified connectors across eight source families. The 41
committed source manifests cover 100,842 declared source units: 34,086 GeoNames gazetteer rows,
65,880 NASA POWER parameter-date values for the Tier-S layer, 795 World Bank response rows for
three context indicators, and 81 earlier bounded source units. These heterogeneous units are not
presented as 100,842 independent policy observations. See
[`catalog/connectors.json`](catalog/connectors.json) for authentication, request bounds, licensing
summaries, record semantics, and primary limitations. Eight is current scope, not the final
25–35-family target.

## Reproducible global city foundation

[`catalog/global-cities/cities-tier-g.json`](catalog/global-cities/cities-tier-g.json) contains 250
deterministically selected GeoNames city points: the largest source-population record for each of
244 represented country or territory codes, followed by six globally ranked fills. The same build
emits:

- a 250-row [`coverage matrix`](catalog/global-cities/cities-tier-g.coverage.csv);
- a 494-geography [`semantic bundle`](catalog/global-cities/cities-tier-g.semantic.json);
- a 494-node, 250-edge [`seed graph`](catalog/global-cities/cities-tier-g.graph.json); and
- portable [`SHA256SUMS`](catalog/global-cities/SHA256SUMS) covering all four artifacts.

The catalog retains source population, point coordinates, timezone, source modification date,
selection rank, and limitations for every row. It is a reproducible geographic index, not a set of
official municipal boundaries or evidence that all 250 cities are analytically ready. See
[`docs/GLOBAL_CITY_COVERAGE.md`](docs/GLOBAL_CITY_COVERAGE.md) for the method and claim boundary.

## Thirty standardized city bundles

[`catalog/standardized-cities/registry.json`](catalog/standardized-cities/registry.json) indexes 30
Tier-S bundles selected by an auditable completeness rule. Every bundle binds the same five
artifacts: GeoNames identity, one complete 2024 NASA POWER six-parameter point series, and three
2023 World Bank country-context pages. The compiler emits:

- 30 embedded, validated Tier-S City Adapters and 30 passing quality reports;
- 330 evidence-typed summary metrics and 150 explicit source bindings;
- 90 independent scenario-screening records: 60 descriptive screens and 30 deliberate
  `insufficient-evidence` releases;
- a 30-row coverage matrix and [cross-city comparison
  report](catalog/standardized-cities/cross-city-comparison.md); and
- a recursive portable checksum inventory, independently rebuilt byte-for-byte.

Every screening record fixes `recommendation_issued=false`. National indicators remain explicitly
typed as country context, and the point climate series is never described as a municipal exposure
surface. See [`docs/STANDARDIZED_CITY_COVERAGE.md`](docs/STANDARDIZED_CITY_COVERAGE.md).

## Audited analytical engines and benchmarks

The analytical layer now provides five independently typed engines:

- transparent naive, drift, moving-average, and seasonal-naive forecasts selected only through
  rolling-origin training folds, with empirical residual intervals and negative releases;
- a balanced-panel difference-in-differences estimator whose output remains an estimated
  association unless every sample, balance, pretrend-equivalence, and placebo-equivalence gate
  passes;
- seeded Monte Carlo simulation over six distribution families with complete draw-stream hashes,
  retained prefixes, quantiles, thresholds, and non-causal sensitivity rankings;
- paired-draw uncertainty analysis with probability-best tie sharing, regret, dominance,
  reversals, robust-winner gates, and insufficient-evidence releases; and
- deterministic bounded integer portfolio optimization with hard constraints, infeasibility
  diagnostics, search-limit releases, Pareto records, solver audit, and a serialized zero-action
  baseline.

[`benchmarks/milestone-4/evidence-summary.json`](benchmarks/milestone-4/evidence-summary.json)
binds every metric below to the SHA-256 hash of its complete run artifact. The 40 historical tasks
use 13,440 training values and 1,200 strictly later holdout values from 20 committed NASA POWER
city-point artifacts and two parameters. The 100 synthetic solver tasks declare 24,000 portfolios,
evaluate 21,710, encounter 4,333 feasible cases across the full run set, and contain 70 explicit
selected-versus-zero-action comparisons, 20 proven infeasible releases, and 10 search-limited
releases. These are substantial, reproducible software and public-data evaluation artifacts—not
live forecasts, 40 independent cities, real interventions, clients, users, or observed impact.

The human-readable [benchmark audit](benchmarks/milestone-4/summary.md), three row-level evidence
CSVs, 145 complete run JSON files, a 152-entry portable checksum inventory, and a deterministic
registry provide separate review surfaces. See
[`docs/ANALYTICAL_ENGINE_AUDIT.md`](docs/ANALYTICAL_ENGINE_AUDIT.md) for methods, gates, tests, and
claim boundaries.

## Core protocols

1. `city-adapter.schema.json` — how a city declares sources, coverage, capabilities, and limitations.
2. `policy-scenario.schema.json` — how an intervention declares time, actions, objectives, constraints, and evidence requirements.
3. `decision-pack.schema.json` — how a run records data versions, evidence types, alternatives, failures, reversals, and reproducibility.
4. `global-city-catalog.schema.json` — how Tier-G point selection and source limits are recorded.
5. `semantic-bundle.schema.json` — canonical geography, measure, observation, facility, and event semantics.
6. `urban-graph.schema.json` — evidence-typed nodes, edges, source references, and limitations.
7. `standard-scenario-run.schema.json` — descriptive and insufficient-evidence screening outputs.
8. `standardized-city-bundle.schema.json` — source alignment, quality, metrics, and scenario gates.
9. `tier-s-registry.schema.json` — selection, exclusions, hashes, and cross-city artifact references.
10. `forecast-run.schema.json` — baseline candidates, rolling-origin folds, metrics, intervals, and negative status.
11. `historical-replay.schema.json` — immutable training cutoff, later holdout, errors, and lineage.
12. `causal-run.schema.json` — estimand, design, diagnostics, effect, interpretation, and claim gate.
13. `simulation-run.schema.json` — distributions, seeded configuration, summaries, sensitivity, and draw hash.
14. `uncertainty-run.schema.json` — option summaries, dominance, regret, reversals, and robustness status.
15. `portfolio-optimization-run.schema.json` — problem, baseline, plans, violations, frontier, and solver status.
16. `benchmark-evidence-summary.schema.json` — row evidence plus recomputed task and work totals.
17. `benchmark-registry.schema.json` — run inventory, file hashes, counts, and artifact-set binding.

## Evidence types

Every analytical output must be typed as one of:

- `observed`
- `estimated`
- `causal`
- `simulated`
- `optimized`
- `proposed`

The type system intentionally rejects unsupported upgrades—for example, a simulated benefit cannot be serialized as an observed outcome, and a causal item requires an identification strategy plus diagnostics.

## Development

Use Python 3.11 or newer.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
civicdecision schemas build
pytest
```

Fetch small, versioned public-data samples:

```bash
civicdecision sources usgs-earthquakes \
  --start 2020-01-01T00:00:00Z \
  --end 2020-01-02T00:00:00Z \
  --min-magnitude 5 \
  --limit 5

civicdecision sources cdc-places --state MA --limit 25

civicdecision sources geonames-cities

civicdecision cities build-global \
  --manifest examples/data/geonames/geonames-cities15000-98bc5fbd4deb.manifest.json \
  --target-count 250 \
  --output catalog/global-cities

civicdecision cities build-standardized \
  --catalog catalog/global-cities/cities-tier-g.json \
  --climate-directory examples/data/tier-s/nasa-power \
  --country-context-directory examples/data/tier-s/world-bank \
  --target-count 30 \
  --output catalog/standardized-cities

civicdecision benchmarks build-milestone-4 \
  --standardized-directory catalog/standardized-cities \
  --nasa-source-directory examples/data/tier-s/nasa-power \
  --replay-city-count 20 \
  --optimization-task-count 100 \
  --output benchmarks/milestone-4
```

Verify a downloaded artifact and compile the committed reference workflow:

```bash
civicdecision sources verify \
  examples/data/cdc-places/cdc-places-7ccf6e7d6dc3.manifest.json

civicdecision demo heat-access \
  --data examples/data/cdc-places/cdc-places-7ccf6e7d6dc3.json \
  --manifest examples/data/cdc-places/cdc-places-7ccf6e7d6dc3.manifest.json \
  --scenario examples/scenarios/suffolk-heat-access-demo.yaml \
  --config examples/configs/suffolk-heat-access-default.yaml

python scripts/verify_repository.py
```

## Repository map

- `src/civicdecision/protocols/` — public contracts and evidence gates.
- `src/civicdecision/connectors/` — bounded public-data ingestion.
- `src/civicdecision/semantic/` — canonical urban semantics, Tier-G catalog, and seed graph.
- `src/civicdecision/analysis/` and `optimization/` — transparent analytical primitives.
- `src/civicdecision/benchmarks/` — deterministic replay, solver-task, qualification, and
  evidence-ledger builders.
- `src/civicdecision/demos/` — end-to-end reference compilers.
- `schemas/` — generated versioned JSON Schemas.
- `examples/data/` — small public fixtures plus manifests.
- `examples/outputs/` — completed and negative golden DecisionPacks.
- `docs/` — architecture, governance, threat model, ADRs, and scope matrix.
- `verification/` — machine-readable exact-rebuild evidence.
- `benchmarks/` — complete runs, row-level evidence ledgers, reports, and portable hashes.

## Scope and claim boundary

- Public data are not client data.
- Historical replay is not production deployment.
- A gazetteer point is not an official city boundary or a deep adapter.
- A gridded point series plus national context is not a local intervention evidence base.
- Simulation is not observed impact.
- Optimization is not institutional adoption.
- Tests prove implementation behavior, not policy effectiveness.
- The project will preserve failed, infeasible, and insufficient-evidence runs as first-class releases.

## License

MIT. Data downloaded through connectors retain their upstream licenses, terms, and required
attributions; see [`docs/DATA_ATTRIBUTION.md`](docs/DATA_ATTRIBUTION.md).
