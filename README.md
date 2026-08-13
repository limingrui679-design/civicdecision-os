# CivicDecision OS

**A local, evidence-typed compiler for urban interventions.**

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

The eighth implementation milestone establishes 27 generated core contracts, the evidence type
system, deterministic validation, ten loadable public-data connectors, a reproducible Tier-G
catalog of 250 city points, 30 Tier-S standardized descriptive bundles, five transparent
analytical engines, 40 held-out historical replays, 100 bounded benchmark optimization tasks,
eight Tier-D city adapters with 96 evidence-gated scenario packs, an audited 240-design scenario
library, five read-only product surfaces over one validated artifact store, and a reproducible
0.8.0 release-candidate pipeline. Tier D, design breadth, packaging depth, and product visibility
still do not mean production deployment, municipal adoption, policy validity, or real-world
impact.

## One validated product core, five surfaces

The local product layer exposes the same immutable snapshot through a responsive evidence
explorer, versioned REST API, local/synchronous/asynchronous Python SDKs, CLI, and data-only
adapter plugin SDK. The shared store reconciles 258 highest-available city records, 288 tier
assignments, 90 source artifacts, 188 scenario executions, 98 DecisionPacks, seven application
suites, 240 scenario designs in 30 families, and 145 analytical benchmark runs before any surface
can return them.

The committed [`catalog/product/`](catalog/product/) projection contains 338 files: 336
manifest-indexed JSON artifacts, one artifact manifest, and one portable checksum file. It
includes 28 product/plugin/library Schemas, a deterministic 19-path OpenAPI document, four hashed
web assets, 240 API-shaped design details, 30 family details, suite/type/status indexes,
city/source/execution indexes, benchmark evidence, and the catalog-wide claim boundary. The
entire tree rebuilds path-for-path and byte-for-byte.

Negative releases remain first-class. The product snapshot contains 77 completed and 21 negative
DecisionPacks; Tier-S screens are never promoted into DecisionPacks, and the browser, API, SDK,
and CLI all preserve a withheld recommendation as withheld. See
[`docs/PRODUCT_SURFACES.md`](docs/PRODUCT_SURFACES.md), [`docs/API.md`](docs/API.md),
[`docs/SDK.md`](docs/SDK.md), [`docs/WEB_EXPLORER.md`](docs/WEB_EXPLORER.md), and
[`docs/PLUGIN_SDK.md`](docs/PLUGIN_SDK.md). The design-library construction, coverage matrix,
reference mappings, audit method, and remaining evidence gates are documented in
[`docs/SCENARIO_LIBRARY.md`](docs/SCENARIO_LIBRARY.md).

## Audited 240-design scenario library

[`catalog/scenario-library/`](catalog/scenario-library/) contains 240 strict decision designs in
30 domain families. Every family covers diagnose, forecast, prioritize, site, allocate, schedule,
stress-test, and evaluate exactly once. Every design declares a baseline, at least three
alternatives, three objectives, one binding constraint, typed evidence and source requirements,
an explicit release gate, a required negative release, assumptions, limitations, prohibited
claims, and transportability risks.

All 28,680 unordered design pairs are audited. There are no exact substantive-signature,
normalized-title, or normalized-question collisions; no pair reaches the fixed 0.90 token-Jaccard
failure threshold; and the maximum observed value is 0.646154. Exactly 12 designs map one-to-one
to existing Tier-D reference templates and 228 remain design-only. The schema fixes city bindings
at zero and method claims at false.

The committed library has 282 files: 240 designs, 30 family documents, registry, audit, coverage
CSV, two human-readable reports, five Schemas, a 280-entry manifest, and portable checksums. It
rebuilds path-for-path and byte-for-byte. These counts establish authored and validated design
work—not 240 executions, delivered projects, deployments, adoptions, or impacts.

## Verified reference workflow

The repository now contains one completed and one deliberately infeasible heat-access reference
run over a bounded ten-tract CDC PLACES sample. The workflow validates the source hash, separates
artifact observation from area-level estimation, simulates straight-line coverage, exhaustively
enumerates 55 candidate combinations, retains infeasible alternatives, tests five service-radius
conditions, ranks three evidence gaps, and emits JSON plus Markdown from the same DecisionPack.

This demonstrates implementation behavior only. Tract centroids are not verified facilities,
radius is not travel time, the population proxy is not individual demand, and the selected option
is not a municipal recommendation.

Current repository and local-browser evidence is recorded in
[`verification/milestone-8-repository.json`](verification/milestone-8-repository.json),
[`verification/milestone-7-browser-qa.json`](verification/milestone-7-browser-qa.json),
[`verification/milestone-8-coverage.json`](verification/milestone-8-coverage.json), and
[`verification/milestone-8-performance.json`](verification/milestone-8-performance.json). The
machine-readable claim and dated public-state checks are documented in
[`docs/CLAIM_AUDIT.md`](docs/CLAIM_AUDIT.md). Exactly
800 tests pass with 97.100% statement, 91.076% branch, and 95.893% combined line-and-branch
coverage. The independent verifier regenerates Schemas, both earlier reference outputs, all four
global-city artifacts, the complete standardized-city and analytical-benchmark trees, all 707
Tier-D artifacts, the 282-file scenario library, and the 338-file product projection in a
temporary directory and requires exact bytes.

The release-candidate process builds byte-identical wheel, sdist, and normalized source-ZIP
iterations; verifies every wheel `RECORD` row and required archive member; installs the hash-locked
runtime and wheel in a clean environment; smoke-tests the installed CLI, SDK, API, Web explorer,
and plugin contract; and reruns the full verifier from a no-Git source archive. It also emits
Bandit, Detect Secrets, dependency-advisory, license, CycloneDX 1.6 SBOM, performance, and checksum
evidence. See [`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md),
[`docs/SECURITY_ASSURANCE.md`](docs/SECURITY_ASSURANCE.md), and
[`docs/RELEASE_NOTES_0.8.0.md`](docs/RELEASE_NOTES_0.8.0.md). These local gates do not establish a
signed or published GitHub Release, remote CI success, public hosting, or external review.

The current source catalog contains ten loadable connector implementations across eight source
families, plus eight audited municipal dataset configurations used by the generic aggregate
connector. The 90 committed source manifests cover 258,478 declared heterogeneous units: 100,842
from the earlier layers, 148,836 endpoint-side Tier-D aggregate rows, and 8,800 Tier-D context
units. The four municipal views re-express the same 4,148,633 underlying requests and are never
summed as 16,594,532 distinct requests. See
[`catalog/connectors.json`](catalog/connectors.json) for authentication, request bounds, licensing
summaries, record semantics, and primary limitations, and the
[Tier-D anti-inflation audit](catalog/deep-cities/anti-inflation-audit.md) for exact counting
rules. Eight source families remain current scope, not the final 25–35-family target.

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

## Eight deep-city reference bundles

[`catalog/deep-cities/registry.json`](catalog/deep-cities/registry.json) indexes New York City,
Boston, Chicago, San Francisco, Seattle, Austin, Los Angeles, and Philadelphia. Each bundle binds
four independently reconciled official municipal aggregates, one exact ACS incorporated-place
population row, one current TIGERweb legal boundary, and one complete six-parameter NASA POWER
point series. The build emits:

- 8 Tier-D City Adapters, 8 quality reports, 144 evidence-typed city metrics, and 56 explicit
  source bindings;
- 12 non-duplicative scenario designs bound across eight cities, producing 96 validated
  DecisionPacks and 96 briefs;
- 76 completed planning-support packs and 20 explicit `insufficient-evidence` packs, including
  causal, network, and minimum-workload gates;
- 76 forecasts over 13,908 daily input positions, 190,000 seeded simulation iterations, 76
  exhaustive optimization tasks evaluating 237,500 portfolios, and 228,000 paired uncertainty
  option values; and
- a 49-row deduplicated source ledger, 96-row scenario ledger, 144-row metric ledger, selection
  report, template catalog, anti-inflation audit, and 706-entry portable checksum inventory.

The 96 executions are not described as 96 new methods: they are eight city bindings of twelve
shared designs. Service requests remain reports rather than incidents or outcomes; ACS is a survey
estimate; NASA POWER is one gridded point; action effects, costs, capacities, and risks remain
hypothetical. See the [Tier-D evidence audit](catalog/deep-cities/summary.md).

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
18. `municipal-aggregate-artifact.schema.json` — privacy-minimized request dimensions and exact
    underlying-count reconciliation.
19. `deep-scenario-pack.schema.json` — city binding, analytical files, negative gates, and embedded
    DecisionPack.
20. `deep-city-bundle.schema.json` — Tier-D sources, quality, metrics, capabilities, and twelve
    scenario packs.
21. `tier-d-registry.schema.json` — eight-city selection, twelve shared templates, hashes, and
    anti-duplication structure.
22. `tier-d-evidence-summary.schema.json` — source, scenario, forecast, simulation, optimization,
    uncertainty, and anti-inflation workload ledger.
23. `scenario-design.schema.json` — decision context, alternatives, objectives, constraints,
    evidence gate, independence key, and claim boundary.
24. `scenario-family.schema.json` — one eight-type family, shared source roles, signatures, and
    interpretation limits.
25. `scenario-library-registry.schema.json` — 240 ordered designs, 30 ordered families, counts,
    mappings, hashes, and zero-inflation fields.
26. `scenario-library-audit.schema.json` — exact collision, pairwise similarity, completeness,
    coverage, implementation, and readiness evidence.
27. `scenario-library-manifest.schema.json` — portable byte counts, media types, record counts,
    hashes, and artifact-set binding.

The product projection adds 28 generated review contracts for health and catalog summaries, city,
scenario execution, scenario-design, family, source, suite, benchmark, plugin, artifact-manifest,
and paginated collection projections. These live under
[`catalog/product/schemas/`](catalog/product/schemas/) and are intentionally separate from the 22
domain/compiler protocols above.

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

civicdecision deep fetch-sources --output examples/data/tier-d
civicdecision deep fetch-context --output examples/data/tier-d
civicdecision deep build \
  --source-directory examples/data/tier-d \
  --output-directory catalog/deep-cities

civicdecision catalog build-scenario-library \
  --root . \
  --output catalog/scenario-library

civicdecision catalog build-product \
  --root . \
  --output catalog/product

civicdecision catalog summary --root .
civicdecision serve --root . --host 127.0.0.1 --port 8000
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

Build a clean, independently checked local release candidate only after the repository verifier
and test suite pass:

```bash
python -m pip install -e '.[dev,release]'
python scripts/build_release_candidate.py --output-dir dist/release-0.8.0
```

The local explorer opens at `http://127.0.0.1:8000/`; the versioned API is under
`/api/v1`, and the deterministic OpenAPI document is available at `/api/openapi.json`. A
non-loopback server bind requires the explicit `--allow-network` acknowledgement, which does not
add production authentication, TLS, quotas, or authorization.

## Repository map

- `src/civicdecision/protocols/` — public contracts and evidence gates.
- `src/civicdecision/connectors/` — bounded public-data ingestion.
- `src/civicdecision/semantic/` — canonical urban semantics, Tier-G catalog, and seed graph.
- `src/civicdecision/analysis/` and `optimization/` — transparent analytical primitives.
- `src/civicdecision/benchmarks/` — deterministic replay, solver-task, qualification, and
  evidence-ledger builders.
- `src/civicdecision/deep/` — audited city specifications, acquisition, evidence reconciliation,
  twelve scenario templates, compilation, ledgers, and exact-rebuild output.
- `src/civicdecision/scenario_library/` — 30-family authored matrix, 240 strict design contracts,
  anti-duplication audit, reference mappings, artifact builder, and claim boundaries.
- `src/civicdecision/product/` — fail-closed artifact store, typed product models, and deterministic
  338-file projection builder.
- `src/civicdecision/api/` — versioned read-only REST resources, problem details, ETags, and
  browser security headers.
- `src/civicdecision/sdk/` — local, synchronous HTTP, and asynchronous HTTP clients over the same
  typed models.
- `src/civicdecision/plugins/` — exact-allowlist, hash-checked, data-only adapter package contract;
  no plugin code is imported or executed.
- `src/civicdecision/web/` — dependency-free responsive evidence explorer with no third-party
  runtime assets.
- `src/civicdecision/demos/` — end-to-end reference compilers.
- `src/civicdecision/release.py` — fail-closed wheel, sdist, source-ZIP, and checksum validation.
- `src/civicdecision/claim_audit.py` — deterministic quantitative-claim, boundary, URL, and
  dated public-state checks.
- `schemas/` — generated versioned JSON Schemas.
- `requirements/runtime-api.lock` — exact, fully hashed local API/runtime dependency contract.
- `examples/data/` — small public fixtures plus manifests.
- `examples/outputs/` — completed and negative golden DecisionPacks.
- `docs/` — architecture, governance, threat model, ADRs, and scope matrix.
- `verification/` — machine-readable exact-rebuild, coverage, browser, performance, quality,
  claim-language, and public-state evidence.
- `benchmarks/` — complete runs, row-level evidence ledgers, reports, and portable hashes.
- `catalog/deep-cities/` — 8 city bundles, 96 scenario packs, 96 briefs, evidence ledgers, and
  anti-inflation audit.
- `catalog/product/` — committed API/web/SDK/CLI projection, product/plugin Schemas, OpenAPI,
  artifact manifest, and portable checksums.

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
