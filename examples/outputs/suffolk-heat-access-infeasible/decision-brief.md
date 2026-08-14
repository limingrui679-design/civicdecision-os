# CivicDecision OS — Heat-access reference Decision Brief

- Run: `run-8a6e1c70ae7a`
- Scenario: `us.ma.suffolk.heat-access-demo.v1`
- Status: `infeasible`
- DecisionPack content hash: `sha256:f0d6f6f9bbafb3fd0a9922fcc306755785a7af321aef3c7216b97c4ae69652da`

## Claim boundary

This is a reproducible methods demonstration over a bounded public-data sample. It is not a deployed service, causal impact estimate, verified facility plan, municipal recommendation, or record of real-world adoption.

## Result

No candidate combination satisfies every declared hard constraint.

Failure reason: The bounded candidate set has no feasible plan.

## Evidence layers

- **observed / established:** The verified artifact contains 10 parsed census-tract rows.
- **estimated / limited:** The bounded sample contains an estimated proxy total of 3239.695 people.
- **simulated / limited:** Coverage is simulated at a 0.00 km radius around tract-centroid candidates.
- **optimized / limited:** The engine evaluated 10 combinations and found 0 feasible under declared constraints.
- **proposed / limited:** Every candidate location is a tract centroid used for demonstration, not a verified facility.

## Reversal tests

| Parameter | Baseline | Tested | Outcome | Selected after test |
|---|---:|---:|---|---|

## Highest-priority evidence gaps

- `1.00` — **Straight-line radius may misrepresent accessible travel time.** Build a versioned pedestrian and transit network with timed routing.
- `0.98` — **Tract centroids have not been verified as operable cooling facilities.** Verify candidate facilities, hours, accessibility, capacity, and cost.
- `0.92` — **Area-level modeled prevalence does not identify actual service demand.** Collect privacy-preserving, consented service-demand evidence.

## Reproduce

```bash
civicdecision demo heat-access --data examples/data/cdc-places/cdc-places-7ccf6e7d6dc3.json --manifest examples/data/cdc-places/cdc-places-7ccf6e7d6dc3.manifest.json --scenario examples/scenarios/suffolk-heat-access-demo.yaml --config examples/configs/suffolk-heat-access-infeasible.yaml
```
