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

The second implementation milestone establishes six generated public contracts, the evidence type
system, deterministic validation, eight real public-data connectors, and a reproducible Tier-G
catalog of 250 city points. Tier G means global discoverability only; it does **not** claim 250
deep city adapters, production deployment, municipal adoption, or real-world impact.

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
[`verification/milestone-2-global-cities.json`](verification/milestone-2-global-cities.json). The
independent verifier regenerates Schemas, both reference outputs, and all four global-city
artifacts in a temporary directory and requires exact bytes.

The current source catalog contains eight verified connectors across eight source families and
eight real public artifacts with 34,167 source records. GeoNames contributes 34,086 gazetteer
rows; that total is not presented as 34,167 independent analytical observations. See
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

## Core protocols

1. `city-adapter.schema.json` — how a city declares sources, coverage, capabilities, and limitations.
2. `policy-scenario.schema.json` — how an intervention declares time, actions, objectives, constraints, and evidence requirements.
3. `decision-pack.schema.json` — how a run records data versions, evidence types, alternatives, failures, reversals, and reproducibility.
4. `global-city-catalog.schema.json` — how Tier-G point selection and source limits are recorded.
5. `semantic-bundle.schema.json` — canonical geography, measure, observation, facility, and event semantics.
6. `urban-graph.schema.json` — evidence-typed nodes, edges, source references, and limitations.

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
- `src/civicdecision/demos/` — end-to-end reference compilers.
- `schemas/` — generated versioned JSON Schemas.
- `examples/data/` — small public fixtures plus manifests.
- `examples/outputs/` — completed and negative golden DecisionPacks.
- `docs/` — architecture, governance, threat model, ADRs, and scope matrix.
- `verification/` — machine-readable exact-rebuild evidence.

## Scope and claim boundary

- Public data are not client data.
- Historical replay is not production deployment.
- A gazetteer point is not an official city boundary or a deep adapter.
- Simulation is not observed impact.
- Optimization is not institutional adoption.
- Tests prove implementation behavior, not policy effectiveness.
- The project will preserve failed, infeasible, and insufficient-evidence runs as first-class releases.

## License

MIT. Data downloaded through connectors retain their upstream licenses, terms, and required
attributions; see [`docs/DATA_ATTRIBUTION.md`](docs/DATA_ATTRIBUTION.md).
