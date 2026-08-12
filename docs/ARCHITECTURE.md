# Architecture

## Product thesis

CivicDecision OS is an evidence-typed compiler for urban interventions. Its durable product
boundary is the compilation path from a versioned scenario and data lineage to a validated,
reproducible DecisionPack—not any single dashboard, model, solver, or city.

```text
official/public source
  -> bounded connector
  -> immutable raw artifact + SourceManifest
  -> normalized semantic layer + data-quality report
  -> City Adapter capability declaration
  -> validated Policy Scenario DSL
  -> descriptive / forecast / causal / simulation / optimization engines
  -> uncertainty, reversal, and value-of-information analysis
  -> DecisionPack JSON
  -> brief, API, web, SDK, CLI, and plugin views from the same pack
```

## Layer boundaries

### 1. Source and integrity layer

Connectors fetch bounded public artifacts. Raw bytes are retained exactly as received. A
`SourceManifest` records URL, query, retrieval time, upstream time, license, hash, count,
schema fingerprint, scope, headers, and limitations. Artifact verification rejects path escape,
missing files, and hash mismatch.

### 2. Protocol layer

Three versioned public contracts prevent hidden coupling:

- City Adapter: geographic identity, tier, sources, coverage, capabilities, gaps, limitations.
- Policy Scenario: intervention, baseline, time, objectives, constraints, modes, evidence needs.
- DecisionPack: sources, evidence, alternatives, recommendation or failure, reversal tests,
  value-of-information items, environment, parameters, command, random seed, and source hashes.

Extra fields are rejected at protocol boundaries so schema drift cannot pass silently.

### 2a. Semantic and graph layer

The semantic contract normalizes geography, time intervals, measure definitions, observations,
facilities, and events while retaining source references and limitations. It rejects duplicate
identifiers, missing parent geographies, missing observation measures, missing facility/event
geographies, unsupported evidence upgrades, and estimated observations without a method.

The graph contract represents evidence-typed urban nodes and edges. It rejects duplicate node or
edge identifiers, dangling endpoints, and causal or optimized labels on source relationships. The
current Tier-G seed graph contains only observed city-to-country gazetteer relationships; it is a
contract and identity foundation, not yet a routing or behavioral network.

### 3. Analytical layer

Each engine consumes typed semantic inputs and returns evidence items with the weakest accurate
evidence type. Engines do not mutate source evidence. Causal analysis is gated separately from
prediction and simulation. Solver status is retained even when no feasible recommendation exists.

The first reference engine uses exhaustive enumeration, making bounded optimality independently
checkable. Larger mixed-integer, graph, and simulation engines will implement the same result
contract and retain solver diagnostics.

### 4. Decision diagnostics

Completed DecisionPacks require at least one controlled reversal test and one ranked
value-of-information item. A reversal changes one declared parameter and reruns the same engine.
The current priority score is an explicit planning judgment; it is not described as a monetized
expected value of perfect information.

### 5. Product surfaces

CLI, REST API, Python SDK, web UI, and adapter SDK are projections over the same protocols.
No surface may invent a stronger claim than the underlying pack. Human briefs are generated
from the validated JSON and are verified against deterministic golden artifacts.

## Scale architecture

The target scale separates metadata from bulk data:

- Git: contracts, adapters, manifests, small lawful fixtures, reports, and code.
- Object storage: rebuildable partitioned raw and derived data.
- DuckDB/Parquet: local analytical samples and portable city bundles.
- Warehouse/lakehouse: billion-row cross-city computation.
- Graph store or partitioned graph files: urban people-place-network relationships.
- Stateless workers: connector, feature, replay, simulation, optimization, and rendering jobs.

Counts are deduplicated at the manifest layer. Raster pixels, repeated downloads, rendered tiles,
and copied rows do not inflate the non-raster record target.

## Determinism

Protocol serialization is canonical UTF-8 JSON with sorted keys and no NaN values. Every source
and DecisionPack has a SHA-256 content hash. Reference workflows use fixed inputs, explicit
parameters, and fixed seeds. `scripts/verify_repository.py` rebuilds Schemas and DecisionPacks in
a temporary directory and requires byte-for-byte equality with committed artifacts.

## Current limits

The current milestone implements a 250-point global catalog and a small semantic seed graph, not
250 standardized adapters or official municipal geometries. It does not yet implement production
network routing, forecasting, causal identification, large-scale simulation, API, web UI, hosted
demo, production security controls, external review, real users, or policy impact.
