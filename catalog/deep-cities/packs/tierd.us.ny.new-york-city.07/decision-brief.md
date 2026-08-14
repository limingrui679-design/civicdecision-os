# New York City — Environmental request workload screen

- Scenario: `tierd.us.ny.new-york-city.07`
- Application suite: `population-health-environmental-exposure`
- Status: `completed`
- DecisionPack content hash: `sha256:6054745130d9b217d5a2641df0149c76df7f58c8a2377e8d9a3c3dfe24d7aeee`

## Claim boundary

An environmental request-label screen with population and climate context, not an exposure, diagnosis, health-risk, or causal-effect estimate.

This artifact is a reproducible public-data planning exercise. It is not a deployed service, municipal recommendation, causal effect, observed intervention outcome, or evidence of adoption or real-world impact.

## Result

The selected option follows the deterministic paired-draw probability-best and regret rule after bounded optimization. It is planning-support output only, not a city recommendation, validated intervention, or impact claim.

Selected bounded planning option: `bounded-portfolio`

| Metric | Value |
|---|---:|
| probability-best-under-declared-draws | 0.998 |
| expected-regret-index | 8.841494289e-05 |
| modeled-objective | 121.295853115 |
| abstract-cost-units | 11.9 |
| selected-action-types | 3 |
| solver-plan-id | portfolio-plan-00001902 |

## Evidence ledger

- **observed / established:** The declared focus rule matches 686,368 requests across 34 public category labels.
- **estimated / limited:** Rolling-origin selection chose seasonal-naive for a 14-day baseline forecast.
- **simulated / limited:** The engine generated 2,500 draws under declared uncalibrated action and demand assumptions.
- **optimized / limited:** The solver evaluated 3,125 of 3,125 portfolios and found 252 feasible.
- **simulated / limited:** Three options were compared over 1,000 paired hypothetical benefit-index draws.
- **proposed / limited:** Costs, capacities, risks, effectiveness states, and implementation assumptions are transparent scenario inputs rather than measured local effects.

## Reversal diagnostics

- `paired-draw-no-action`: stable; tested joint-parameter-draw = 0.0.
- `paired-draw-conservative-plan`: reversed; tested joint-parameter-draw = 0.001.

## Required next evidence

- Pre-register a prospective pilot or defensible quasi-experiment with outcome, comparison, timing, and diagnostic rules.
- Obtain versioned local cost, staffing, procurement, service-level, and capacity records with responsible-owner review.
- Define privacy-reviewed subgroup and neighborhood outcomes, reporting-access diagnostics, and an equity decision rule.

## Reproduce

```bash
civicdecision deep build --source-directory examples/data/tier-d --output-directory catalog/deep-cities
```
