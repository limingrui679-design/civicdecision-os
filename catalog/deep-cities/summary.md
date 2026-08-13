# Tier-D deep-city evidence audit

## Verified build scope

- 8 deep-city adapters and 8 city bundles
- 12 non-duplicative scenario designs
- 96 city-bound scenario packs and DecisionPacks
- 76 completed planning-support packs
- 20 explicit insufficient-evidence packs
- 49 deduplicated source artifacts from 11 datasets
- 4,148,633 reconciled underlying municipal requests
- 148,836 endpoint-side aggregate rows
- 8,800 declared context source units

## Audited analytical workload

- 76 forecast runs over 13,908 daily input positions
- 76 simulations with 190,000 total seeded iterations
- 76 exhaustive optimization tasks declaring 237,500 portfolios and evaluating 237,500
- 19,152 feasible portfolios encountered across the complete solver task set
- 76 paired uncertainty runs with 228,000 option-draw values

## Scenario statuses

- `completed`: 76
- `insufficient-evidence`: 20

## Application-suite execution counts

- `behavioral-policy-equity`: 16
- `climate-disaster-resilience`: 16
- `housing-land-use-regeneration`: 8
- `infrastructure-finance-asset-risk`: 8
- `mobility-accessibility-operations`: 16
- `population-health-environmental-exposure`: 8
- `public-service-operations`: 24

## Claim boundary

Completed means the internal public-data planning pipeline ran and validated. It does not mean policy correctness, causal impact, implementation feasibility, production deployment, external review, municipal adoption, real users, or real-world impact. Negative packs deliberately demonstrate that the compiler refuses causal and routing claims when required evidence is absent.
