# CivicDecision 240-scenario design library

## Scope

This catalog contains **240 policy decision designs** organized as **30 domain families × 8
decision types**. It intentionally reports **0 city bindings**, **0 new methods**, and **0 claims
of deployment or impact**. Exactly **12 designs** point one-to-one to existing Tier-D reference
templates; the remaining **228 are design-only**.

The eight decision types are diagnose, forecast, prioritize, site, allocate, schedule,
stress-test, and evaluate. Repeating this decision grammar across domains is an explicit coverage
matrix; substantive independence is tested from decision object, intervention mechanism, primary
outcome, binding constraint, evidence gate, horizon, and spatial unit—not from title or city name.

## Verified inventory

- Designs: 240
- Families: 30
- Suites: 7
- Reference-implemented designs: 12
- Design-only records: 228
- City-bound executions counted: 0
- Methods claimed: 0
- Exact signature collisions: 0
- Duplicate titles: 0
- Duplicate questions: 0
- Similarity threshold: 0.90
- Maximum observed pairwise token Jaccard: 0.646154
- High-similarity pairs at or above threshold: 0

## Designs by suite

| Value | Count |
|---|---:|
| `climate-disaster-resilience` | 40 |
| `mobility-accessibility-operations` | 40 |
| `population-health-environmental-exposure` | 32 |
| `housing-land-use-regeneration` | 32 |
| `public-service-operations` | 32 |
| `infrastructure-finance-asset-risk` | 32 |
| `behavioral-policy-equity` | 32 |

## Designs by decision type

| Value | Count |
|---|---:|
| `diagnose` | 30 |
| `forecast` | 30 |
| `prioritize` | 30 |
| `site` | 30 |
| `allocate` | 30 |
| `schedule` | 30 |
| `stress-test` | 30 |
| `evaluate` | 30 |

## Current readiness

| Value | Count |
|---|---:|
| `reference-implemented` | 12 |
| `uncompiled-current-inputs` | 0 |
| `blocked-missing-source` | 199 |
| `blocked-method` | 0 |
| `blocked-multiple-gates` | 29 |

## Family inventory

| # | Suite | Family | Designs | Reference implementations |
|---:|---|---|---:|---:|
| 1 | `climate-disaster-resilience` | `climate.extreme-heat` — Extreme heat exposure and response | 8 | 1 |
| 2 | `climate-disaster-resilience` | `climate.flood-stormwater` — Flood and stormwater resilience | 8 | 1 |
| 3 | `climate-disaster-resilience` | `climate.wildfire-smoke` — Wildfire smoke and air-quality resilience | 8 | 0 |
| 4 | `climate-disaster-resilience` | `climate.drought-water` — Drought and urban water security | 8 | 0 |
| 5 | `climate-disaster-resilience` | `climate.coastal-storms` — Coastal storms and sea-level adaptation | 8 | 0 |
| 6 | `mobility-accessibility-operations` | `mobility.transit-reliability` — Transit reliability and passenger continuity | 8 | 0 |
| 7 | `mobility-accessibility-operations` | `mobility.pedestrian-safety` — Pedestrian safety and universal accessibility | 8 | 1 |
| 8 | `mobility-accessibility-operations` | `mobility.freight-curb` — Urban freight and curb operations | 8 | 0 |
| 9 | `mobility-accessibility-operations` | `mobility.emergency-mobility` — Evacuation and emergency mobility | 8 | 1 |
| 10 | `mobility-accessibility-operations` | `mobility.active-mobility` — Active mobility network and micromobility | 8 | 0 |
| 11 | `population-health-environmental-exposure` | `health.heat-health` — Heat-health surveillance and prevention | 8 | 0 |
| 12 | `population-health-environmental-exposure` | `health.air-quality` — Air-quality exposure and respiratory health | 8 | 1 |
| 13 | `population-health-environmental-exposure` | `health.infectious-operations` — Infectious-disease public-health operations | 8 | 0 |
| 14 | `population-health-environmental-exposure` | `health.food-environment` — Food access and environmental health | 8 | 0 |
| 15 | `housing-land-use-regeneration` | `housing.habitability-code` — Housing habitability and code operations | 8 | 1 |
| 16 | `housing-land-use-regeneration` | `housing.homelessness-prevention` — Homelessness prevention and housing stability | 8 | 0 |
| 17 | `housing-land-use-regeneration` | `housing.affordable-supply` — Affordable housing siting and preservation | 8 | 0 |
| 18 | `housing-land-use-regeneration` | `housing.land-use-regeneration` — Land use, regeneration, and neighborhood change | 8 | 0 |
| 19 | `public-service-operations` | `public-service.demand` — 311 and public-service demand operations | 8 | 2 |
| 20 | `public-service-operations` | `public-service.sanitation` — Sanitation, waste, and street cleanliness | 8 | 1 |
| 21 | `public-service-operations` | `public-service.emergency-response` — Emergency response readiness and allocation | 8 | 0 |
| 22 | `public-service-operations` | `public-service.digital-access` — Digital public access and administrative service delivery | 8 | 0 |
| 23 | `infrastructure-finance-asset-risk` | `infrastructure.roads-bridges` — Road and bridge asset management | 8 | 1 |
| 24 | `infrastructure-finance-asset-risk` | `infrastructure.water-wastewater` — Water and wastewater infrastructure | 8 | 0 |
| 25 | `infrastructure-finance-asset-risk` | `infrastructure.energy-buildings` — Municipal energy and building decarbonization | 8 | 0 |
| 26 | `infrastructure-finance-asset-risk` | `infrastructure.capital-finance` — Capital portfolio and municipal finance | 8 | 0 |
| 27 | `behavioral-policy-equity` | `equity.distributional-service` — Distributional public-service equity | 8 | 1 |
| 28 | `behavioral-policy-equity` | `equity.participation-communication` — Public participation and risk communication | 8 | 0 |
| 29 | `behavioral-policy-equity` | `equity.compliance-incentives` — Compliance, incentives, and behavioral policy | 8 | 0 |
| 30 | `behavioral-policy-equity` | `equity.algorithmic-governance` — Algorithmic decision support and governance | 8 | 1 |

## Evidence and release contract

Every design includes a baseline; at least three alternatives; three objectives; one binding hard
constraint plus evidence-scope and accountable-authority constraints; analysis modes; typed evidence
requirements; source roles; an evidence gate; an explicit insufficient-evidence release; assumptions;
limitations; prohibited claims; and transportability risks. A design cannot silently become an
execution: `city_bindings` is schema-constrained to an empty list and `method_claimed` is schema-
constrained to false.

## How to use the library

1. Select a family and decision type from `coverage.csv` or `registry.json`.
2. Bind a city only in a separate execution artifact; never edit the design's claim boundary.
3. Resolve all required source roles and pass the declared evidence gate.
4. Compile observed, estimated, causal, simulated, optimized, and proposed evidence without relabeling.
5. If a gate fails, publish the required insufficient-evidence record instead of a recommendation.
6. Treat external domain, legal, security, community, and operational review as additional gates.

## Claim boundary

- Breadth is a design asset, not evidence that 240 city projects were delivered.
- A reference implementation may be a negative release; it is not automatically a positive result.
- Internal reproducibility is not external validation, municipal adoption, or real-user impact.
- Counts, hashes, mappings, and audit results are reproducible from committed source definitions.
