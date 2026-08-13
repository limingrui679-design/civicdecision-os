# CivicDecision OS — Heat-access reference Decision Brief

- Run: `run-aff7c38b12c1`
- Scenario: `us.ma.suffolk.heat-access-demo.v1`
- Status: `completed`
- DecisionPack content hash: `sha256:6673fcf19094daae7f5e5554d07793bbbfec098e88ca22f68a620d7d553692a4`

## Claim boundary

This is a reproducible methods demonstration over a bounded public-data sample. It is not a deployed service, causal impact estimate, verified facility plan, municipal recommendation, or record of real-world adoption.

## Result

This option has the highest declared objective score among feasible bounded tract-centroid combinations. It is a methods demonstration, not an implementation recommendation.

Selected bounded option: `plan-25025000202-25025000502`

| Metric | Value |
|---|---:|
| selected_sites | 25025000202,25025000502 |
| estimated_need_covered | 3121.507 |
| overall_coverage_rate | 0.963518788 |
| priority_coverage_rate | 1.0 |
| cost | 16000.0 |
| objective_score | 0.813518788 |

## Evidence layers

- **observed / established:** The verified artifact contains 10 parsed census-tract rows.
- **estimated / limited:** The bounded sample contains an estimated proxy total of 3239.695 people.
- **simulated / limited:** Coverage is simulated at a 1.25 km radius around tract-centroid candidates.
- **optimized / limited:** The engine evaluated 55 combinations and found 16 feasible under declared constraints.
- **proposed / limited:** Every candidate location is a tract centroid used for demonstration, not a verified facility.

## Reversal tests

| Parameter | Baseline | Tested | Outcome | Selected after test |
|---|---:|---:|---|---|
| service_radius_km | 1.25 | 0.5 | stable | plan-25025000202-25025000502 |
| service_radius_km | 1.25 | 0.75 | reversed | plan-25025000201-25025000502 |
| service_radius_km | 1.25 | 1.0 | reversed | plan-25025000201-25025000502 |
| service_radius_km | 1.25 | 1.5 | reversed | plan-25025000101-25025000402 |
| service_radius_km | 1.25 | 2.0 | reversed | plan-25025000401 |

## Highest-priority evidence gaps

- `1.00` — **Straight-line radius may misrepresent accessible travel time.** Build a versioned pedestrian and transit network with timed routing.
- `0.98` — **Tract centroids have not been verified as operable cooling facilities.** Verify candidate facilities, hours, accessibility, capacity, and cost.
- `0.92` — **Area-level modeled prevalence does not identify actual service demand.** Collect privacy-preserving, consented service-demand evidence.

## Reproduce

```bash
civicdecision demo heat-access --data examples/data/cdc-places/cdc-places-7ccf6e7d6dc3.json --manifest examples/data/cdc-places/cdc-places-7ccf6e7d6dc3.manifest.json --scenario examples/scenarios/suffolk-heat-access-demo.yaml --config examples/configs/suffolk-heat-access-default.yaml
```
