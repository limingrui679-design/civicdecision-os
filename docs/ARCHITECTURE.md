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

### 2b. Standardized city layer

Tier S compiles three deliberately different geographic alignments without collapsing them:

- `identity-point`: GeoNames city identity, source point, timezone, and country code;
- `gridded-point`: NASA POWER daily climate values at the requested point; and
- `country-context`: World Bank national aggregates retained only as context proxies.

Each bundle embeds exact source manifests, source bindings, a six-check quality report, typed
summary metrics, and three independent screening records. The protocol rejects missing alignment
layers, unknown source references, failed required checks, incomplete values, duplicated
templates, unsafe artifact paths, and recommendation or analysis-mode upgrades. Two templates are
descriptive; the third must release `insufficient-evidence`. This layer is intentionally incapable
of issuing an intervention recommendation.

### 3. Analytical layer

Each engine consumes typed semantic inputs and returns evidence items with the weakest accurate
evidence type. Engines do not mutate source evidence. Causal analysis is gated separately from
prediction and simulation. Solver status is retained even when no feasible recommendation exists.

Forecasting preserves every baseline candidate and rolling-origin fold, selects only from training
evidence, and emits a negative status when history or regularity is inadequate. Difference in
differences separates design claims from statistical results and upgrades an association to
`causal` only when all declared identification diagnostics pass. Monte Carlo simulation uses
explicit distributions and seeds, hashes the complete canonical draw stream incrementally, and
retains a bounded inspection prefix. Paired uncertainty analysis calculates probability-best,
regret, dominance, and reversal evidence without converting modeled probabilities into policy
success probabilities.

Portfolio optimization exhaustively enumerates a declared finite integer search space up to a
deterministic evaluation cap. It serializes a zero-action baseline, retained feasible and
violating alternatives, binding and violated constraints, a Pareto subset, and solver accounting.
Only a complete search with a feasible incumbent and zero optimality gap can emit `optimal`;
complete no-solution searches emit `infeasible`, while capped searches emit `search-limited` and
withhold selection. Larger mixed-integer and graph solvers will implement the same evidence and
negative-release contracts.

### 3a. Benchmark and evidence-ledger layer

The milestone-4 builder produces 40 strictly forward public-data replays, 100 synthetic bounded
portfolio tasks, and five synthetic method-qualification runs. Every full run is written before
its SHA-256 is added to the registry. A typed evidence summary repeats reviewer-relevant fields,
binds each row back to the full artifact hash, recomputes method/status/strategy counts and work
totals, and hashes the full artifact map. Three CSV projections make row-level inspection possible
without weakening the authoritative JSON contracts.

The repository verifier validates all hashes and schemas, rebuilds the full benchmark tree in an
isolated temporary directory, and requires identical paths and bytes. This creates a chain from
source manifest to run artifact to evidence row to registry to portable checksum. It proves
deterministic implementation and stated task counts; it does not prove external validity or impact.

### 3b. Deep-city compilation layer

Tier D binds four independently reconciling municipal aggregate views, an exact ACS place row, a
legal TIGERweb boundary, and a complete NASA POWER point series. A loader verifies all source
manifests and identities before metrics or scenarios can be constructed. The quality report
separates hard failures from retained warnings such as missing operational area labels and absent
aggregate dates.

Twelve shared scenario templates declare application suite, completion strategy, source roles,
analysis modes, evidence requirements, keyword rules, minimum sample gates, intended claim,
prohibited claims, assumptions, and limitations. The compiler binds each template to eight cities.
It does not count those 96 bindings as 96 unique designs.

A completed binding writes a Policy Scenario, forecast, simulation, bounded optimization,
uncertainty analysis, DecisionPack, brief, and the encompassing scenario pack as separately hashed
artifacts. A missing causal design, routable network, or minimum matching workload produces a
negative DecisionPack without forecast, simulation, optimization, uncertainty, or selected option.
The evidence summary separately reconciles public source units, deduplicated underlying requests,
forecast inputs, simulation iterations, optimizer search/evaluation counts, uncertainty draws,
and file hashes.

### 3c. Scenario-design library layer

The library sits between reusable decision intent and city-bound execution. Thirty authored
families cover seven application suites. Each family contains exactly one diagnose, forecast,
prioritize, site, allocate, schedule, stress-test, and evaluate design, producing a complete
30×8 matrix without copying a design across cities.

Every strict design contract includes decision context, baseline, alternatives, objectives,
constraints, analysis modes, evidence types, source roles, a negative release gate, assumptions,
limitations, prohibited claims, and transfer risks. A seven-field independence key excludes title,
family, suite, and city labels; exact collisions and all 28,680 pairwise lexical similarities are
audited during the build. The maximum current pairwise token Jaccard is 0.646154 against a fixed
0.90 failure threshold.

Exactly twelve designs point to existing Tier-D templates as bounded reference implementations;
228 remain design-only. `city_bindings` is schema-constrained to an empty list and
`method_claimed` to false. A city execution therefore requires a separate artifact and cannot be
created by relabeling the design record.

The deterministic tree has 282 files and a 280-entry manifest. Registry/model/file hashes,
portable checksums, exact counts, safe paths, stale files, and isolated byte-for-byte rebuilds are
all checked independently.

### 4. Decision diagnostics

Completed DecisionPacks require at least one controlled reversal test and one ranked
value-of-information item. A reversal changes one declared parameter and reruns the same engine.
The current priority score is an explicit planning judgment; it is not described as a monetized
expected value of perfect information.

### 5. Product surfaces

`ArtifactStore` is the single product read model. At construction it validates the Tier-G,
Tier-S, Tier-D, scenario-library, reference-workflow, source-manifest, and benchmark registries;
reconciles identities, hashes, manifests, checksums, counts, family/design references, scenario
kinds, negative statuses, and DecisionPack eligibility; and computes one catalog fingerprint and
strong ETag. API parameters are never interpreted as filesystem paths.

Five product surfaces project from that store:

- the CLI offers typed city, execution, design, family, source, and benchmark browsing, library
  and product rebuilds, OpenAPI export, guarded local serving, and plugin validation;
- the REST API offers 19 versioned read-only paths with bounded pagination, closed filters,
  problem details, request IDs, conditional caching, compression, and browser security headers;
- the Python SDK offers local, synchronous HTTP, and asynchronous HTTP clients that validate the
  same Pydantic response models;
- the dependency-free browser explorer retrieves same-origin resources and computes no new
  recommendation in JavaScript; and
- the adapter plugin SDK validates exact-allowlist, data-only packages without importing or
  executing third-party code.

No surface may invent a stronger claim than the underlying pack. A Tier-S screen cannot become a
DecisionPack, and a negative DecisionPack remains retrievable with no selected option. Human
briefs are generated from validated JSON and verified against deterministic golden artifacts.

The committed product projection is a separate immutable review surface: 336 manifest-indexed
artifacts, one artifact manifest, and one portable checksum inventory. Its 338 files include 28
product/plugin/library Schemas, a 19-path deterministic OpenAPI document, 240 API-shaped design
details, 30 family details, segmented indexes, evidence records, and web-asset hashes. Static
views duplicate access shapes but never increase the authoritative design count. The plugin
registry remains separate from the live catalog: validating a package never installs, enables, or
merges it automatically.

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

Protocol serialization is canonical UTF-8 JSON with sorted keys and no NaN values. Every source,
run artifact, evidence summary, and DecisionPack has a SHA-256 content hash. Reference workflows
use fixed inputs, explicit parameters, and fixed seeds. `scripts/verify_repository.py` rebuilds
Schemas, DecisionPacks, the Tier-G and Tier-S layers, all 145 analytical benchmark artifacts, the
complete 707-file Tier-D tree, and the 282-file scenario library in temporary directories and
requires byte-for-byte equality. It also rebuilds the 338-file product projection and compares
every path and byte, including its 28 Schemas, 19-path OpenAPI document, manifest, and checksums.

## Current limits

The current milestone implements a 250-point global catalog, a small semantic seed graph, 30
standardized descriptive bundles, five analytical engine families, 40 public-data forecast
replays, 100 synthetic optimization tasks, five synthetic engine qualifications, eight deep-city
reference bundles with legal geometries and local public request evidence, and 240 audited scenario
designs. Of those designs, 228 are design-only. Tier-D action
parameters are still hypothetical, and its climate input remains a point rather than an exposure
surface. The local API, SDK, CLI, web explorer, and data-only plugin validator are implemented and
packaging-tested, but they are not a public deployment. Production network routing, externally
credible causal studies, city-calibrated intervention effects, hosted-demo operations,
authentication/authorization, quotas, production observability, external security/accessibility
review, real users, and policy impact remain incomplete.
