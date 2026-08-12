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

The first implementation milestone establishes the three public protocols, the evidence type system, deterministic validation, and real public-data connectors. It does **not** yet claim 250-city coverage, production deployment, municipal adoption, or real-world impact.

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
[`verification/milestone-0.json`](verification/milestone-0.json). The independent verifier
regenerates Schemas and both reference outputs in a temporary directory and requires exact bytes.

## Core protocols

1. `city-adapter.schema.json` — how a city declares sources, coverage, capabilities, and limitations.
2. `policy-scenario.schema.json` — how an intervention declares time, actions, objectives, constraints, and evidence requirements.
3. `decision-pack.schema.json` — how a run records data versions, evidence types, alternatives, failures, reversals, and reproducibility.

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
- Simulation is not observed impact.
- Optimization is not institutional adoption.
- Tests prove implementation behavior, not policy effectiveness.
- The project will preserve failed, infeasible, and insufficient-evidence runs as first-class releases.

## License

MIT. Data downloaded through connectors retain their upstream licenses, terms, and required attributions.
