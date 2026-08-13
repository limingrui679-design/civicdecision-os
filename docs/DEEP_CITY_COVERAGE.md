# Tier-D deep-city coverage and claim boundary

## Purpose

Tier D is the first layer that binds official local demand evidence, a legal city identity,
population context, climate context, analytical engines, and `DecisionPack` governance into one
rebuildable workflow. It is deliberately deeper than Tier S, but “deep” describes the evidence and
compiler surface—not production readiness, local endorsement, policy correctness, or observed
impact.

The authoritative machine-readable artifacts are:

- [`registry.json`](../catalog/deep-cities/registry.json), which declares city selection and the
  twelve shared scenario templates;
- [`evidence-summary.json`](../catalog/deep-cities/evidence-summary.json), which reconciles every
  source, execution, file hash, and analytical workload;
- [`source-evidence.csv`](../catalog/deep-cities/source-evidence.csv), which inventories 49
  deduplicated source artifacts;
- [`scenario-ledger.csv`](../catalog/deep-cities/scenario-ledger.csv), which inventories all 96
  city-bound executions; and
- [`anti-inflation-audit.md`](../catalog/deep-cities/anti-inflation-audit.md), which states exactly
  what can and cannot be added together.

## Eight-city reference set

| # | City | Municipal platform | Underlying requests | Quality | Completed / negative packs |
|---:|---|---|---:|---|---:|
| 1 | New York City | Socrata | 1,796,655 | pass | 10 / 2 |
| 2 | Boston | CKAN DataStore | 148,160 | warn | 10 / 2 |
| 3 | Chicago | Socrata | 1,061,921 | warn | 10 / 2 |
| 4 | San Francisco | Socrata | 461,576 | warn | 10 / 2 |
| 5 | Seattle | Socrata | 186,351 | warn | 9 / 3 |
| 6 | Austin | Socrata | 164,333 | warn | 10 / 2 |
| 7 | Los Angeles | Socrata | 53,194 | warn | 7 / 5 |
| 8 | Philadelphia | CARTO SQL | 276,443 | warn | 10 / 2 |
| **Total** |  |  | **4,148,633** | 1 pass / 7 warn | **76 / 20** |

The quality warnings are retained, not repaired away. Most arise from missing operational area
labels. Los Angeles also has dates absent from its public endpoint-side aggregate; the compiler
zero-completes them to preserve a regular forecast series but explicitly states that the source
cannot distinguish true zero activity from delayed or incomplete publication.

## Seven bound source artifacts per city

Each city bundle embeds seven `SourceManifest` objects:

1. daily request count by public category label;
2. daily request count by operational area label;
3. request count by category and workflow status;
4. request count by area and workflow status;
5. the shared ACS 2024 five-year B01003 place-population artifact, with the exact city row and 90%
   margin of error selected by incorporated-place GEOID;
6. the current TIGERweb incorporated-place legal polygon for the same GEOID; and
7. a 183-day NASA POWER point series containing `T2M`, `T2M_MAX`, `T2M_MIN`, `PRECTOTCORR`,
   `WS10M`, and `RH2M`.

The four municipal views are endpoint-side grouped counts over the same local dataset and time
window. Their purpose is independent reconciliation and alternate analytical dimensions. They do
not represent four copies of distinct requests. The shared ACS artifact is likewise stored once,
not downloaded eight times to inflate the source count.

## Twelve designs, ninety-six executions

The registry contains twelve non-duplicative designs:

1. citywide request workload baseline;
2. seasonal service-capacity planning;
3. sanitation-label workload planning;
4. heat-context continuity stress test;
5. rainfall-context continuity stress test;
6. housing-label triage;
7. environmental request-label screening;
8. infrastructure-maintenance request portfolio;
9. operational area-balance planning;
10. accessibility request-label planning;
11. a causal service-effectiveness evidence gate; and
12. a real-time multimodal routing evidence gate.

Binding each design to eight cities creates 96 executions, not 96 independent methods. A
category-demand execution must match at least 100 public requests under its exact published
keyword rule. A causal execution must have intervention timing, treated and comparison panels,
outcomes, and diagnostics. A routing execution must have a versioned routable network, service
calendar, impedance validation, and disruption state. If a gate fails, the compiler emits an
`insufficient_evidence` DecisionPack with required next evidence and no selected option.

## Completed planning-support pipeline

Every one of the 76 completed executions contains seven independently hashed files:

1. validated `PolicyScenario`;
2. 14-day transparent baseline `ForecastRun`, selected from naive, drift, moving-average, and
   seasonal-naive candidates using training-only rolling-origin folds;
3. 2,500-draw seeded `SimulationRun` with a complete draw-stream hash and 50 retained prefix draws;
4. a complete enumeration of 3,125 bounded five-action portfolios;
5. a three-option, 1,000-paired-draw-per-option `UncertaintyRun` with regret, dominance, and
   reversal diagnostics;
6. a completed `DecisionPack` with typed evidence, alternatives, formal reversal tests,
   value-of-information priorities, and reproduction parameters; and
7. a human-readable brief rendered from that same `DecisionPack`.

Across the complete set this produces 13,908 forecast input positions, 190,000 simulation
iterations, 237,500 declared and evaluated portfolios, 19,152 feasible portfolios encountered,
and 228,000 uncertainty option-draw values. These are workload metrics. They are not counts of
people, incidents, independent studies, deployed actions, users, or observed outcomes.

## Interpretation rules

- A published request is a report or workflow record, not a verified incident, need, exposure,
  person, or successful resolution.
- A public category keyword match is a transparent taxonomy rule, not substantive validation.
- ACS B01003 is a five-year survey estimate. It is not a point-in-time administrative population
  count, and its margin semantics must travel with the estimate.
- A legal city polygon is an identity boundary, not a neighborhood, service, accessibility, or
  exposure geography.
- A NASA POWER point is gridded climate context, not a station, surface, neighborhood exposure, or
  causal driver of requests.
- Every action cost, capacity, risk, effectiveness state, and implementation-friction parameter is
  proposed. None is a local observed or causal effect.
- Mathematical optimality applies only to the encoded finite problem. It does not establish
  operational feasibility, budget approval, public value, equity, or implementation authority.
- Exact internal rebuilds establish repository integrity. They do not establish external review,
  domain validity, municipal adoption, production deployment, real users, or real-world impact.

## Reproduce and verify

```bash
civicdecision deep fetch-sources --output examples/data/tier-d
civicdecision deep fetch-context --output examples/data/tier-d
civicdecision deep build \
  --source-directory examples/data/tier-d \
  --output-directory catalog/deep-cities
python scripts/verify_repository.py \
  --report verification/milestone-5-deep-cities.json
```

The fetch commands verify and reuse matching committed artifacts by default. The build performs no
network access. The repository verifier rebuilds into a temporary directory and compares every
path and byte with the committed tree.
