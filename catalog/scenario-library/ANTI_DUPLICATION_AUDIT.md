# Scenario-library anti-duplication audit

## Result

**PASS.** The audit covers all **28,680 unordered pairs** among 240 designs.

- Exact substantive-signature collisions: 0
- Exact normalized-title duplicates: 0
- Exact normalized-question duplicates: 0
- Fixed high-similarity threshold: 0.90
- Maximum pairwise token Jaccard: 0.646154
- Pairs at or above the threshold: 0

## What constitutes substantive identity

Each design hashes a seven-field independence key: decision object, intervention mechanism, primary
outcome, binding constraint, evidence gate, decision horizon, and spatial unit. Design identifier,
title, family label, suite label, and city name are excluded. A renamed or city-copied record with the
same substantive axes therefore collides.

## Similarity method

The transparent secondary diagnostic tokenizes title, question, and all seven substantive axes;
lowercases terms; removes a fixed small stopword list; and computes set Jaccard similarity. The
threshold is fixed in source at 0.90. This lexical test is intentionally
supplementary: it can identify suspicious copies but cannot prove conceptual novelty.

## Twenty closest pairs below the failure threshold

| Rank | Design A | Design B | Jaccard | Shared terms |
|---:|---|---|---:|---|
| 1 | `scenario.public-service.digital-access.assisted-digital-access.v1` | `scenario.equity.distributional-service.equitable-service-network.v1` | 0.646154 | access, accessibility, accessible, authority, beyond, capacity, capacity-aware, checks, close, control, declared, documented |
| 2 | `scenario.infrastructure.energy-buildings.decarbonization-projects.v1` | `scenario.infrastructure.capital-finance.capital-delivery.v1` | 0.640625 | access, asset, beyond, cadence, calendars, checks, commissioning, completion, dates, declared, dependency, design |
| 3 | `scenario.mobility.emergency-mobility.evacuation-exercise-effect.v1` | `scenario.health.infectious-operations.outreach-access-effect.v1` | 0.637931 | assignment, attrition, change, checks, comparison, completion, dated, declared, did, documented, encouragement, evaluate |
| 4 | `scenario.public-service.demand.service-access-points.v1` | `scenario.public-service.digital-access.assisted-digital-access.v1` | 0.625000 | access, accessibility, authority, beyond, capacity, capacity-aware, checks, control, declared, documented, environmental, evidence |
| 5 | `scenario.health.heat-health.heat-health-surge.v1` | `scenario.health.infectious-operations.multi-pathogen-surge.v1` | 0.621212 | across, capacity, care, checks, continuity, declared, demand, dependence, documented, essential, evidence, facility |
| 6 | `scenario.infrastructure.roads-bridges.maintenance-crews-equipment.v1` | `scenario.infrastructure.water-wastewater.utility-repair-capacity.v1` | 0.620690 | allocate, allocation, assigned, attributes, capacity, checks, crews, declared, denominators, distributional, documented, eligibility |
| 7 | `scenario.health.heat-health.heat-care-demand.v1` | `scenario.health.infectious-operations.care-testing-demand.v1` | 0.618182 | above, baseline, capacity, care, checks, comparison, coverage, declared, demand, detection, documented, drift |
| 8 | `scenario.mobility.emergency-mobility.evacuation-exercise-effect.v1` | `scenario.health.heat-health.heat-outreach-effect.v1` | 0.610169 | assignment, attrition, change, checks, comparison, dated, declared, did, documented, emergency, encouragement, evaluate |
| 9 | `scenario.public-service.digital-access.assisted-digital-access.v1` | `scenario.equity.participation-communication.engagement-venues.v1` | 0.606061 | access, accessibility, accessible, authority, beyond, capacity, capacity-aware, checks, close, control, declared, digital |
| 10 | `scenario.public-service.demand.service-access-points.v1` | `scenario.equity.distributional-service.equitable-service-network.v1` | 0.597015 | access, accessibility, authority, beyond, capacity, capacity-aware, checks, control, declared, documented, environmental, evidence |
| 11 | `scenario.health.heat-health.heat-health-outreach.v1` | `scenario.health.air-quality.respiratory-protection.v1` | 0.596774 | allocate, allocation, assigned, attributes, capacity, checks, clinical, declared, denominators, distributed, distributional, documented |
| 12 | `scenario.health.food-environment.inspection-assistance-demand.v1` | `scenario.equity.compliance-incentives.assistance-inspection-demand.v1` | 0.596491 | above, assistance, baseline, capacity, checks, comparison, coverage, declared, demand, detection, documented, drift |
| 13 | `scenario.equity.participation-communication.engagement-venues.v1` | `scenario.equity.algorithmic-governance.human-review-access.v1` | 0.590909 | access, accessibility, accessible, affected, authority, beyond, capacity, capacity-aware, checks, control, declared, documented |
| 14 | `scenario.health.heat-health.heat-health-surge.v1` | `scenario.health.air-quality.pollution-health-continuity.v1` | 0.588235 | across, capacity, care, checks, continuity, declared, demand, dependence, documented, during, evidence, facility |
| 15 | `scenario.health.heat-health.heat-health-surveillance.v1` | `scenario.health.air-quality.air-health-response.v1` | 0.587302 | access, activate, active, cadence, calendars, checks, citywide, clinical, completion, dates, declared, documented |
| 16 | `scenario.health.food-environment.inspection-assistance-demand.v1` | `scenario.housing.habitability-code.inspection-repair-demand.v1` | 0.586207 | above, baseline, capacity, checks, comparison, coverage, declared, demand, detection, documented, drift, error |
| 17 | `scenario.health.infectious-operations.outreach-access-effect.v1` | `scenario.public-service.digital-access.assisted-service-effect.v1` | 0.584615 | access, assignment, attrition, change, checks, comparison, completion, dated, declared, did, documented, eligible |
| 18 | `scenario.public-service.demand.service-workload.v1` | `scenario.public-service.digital-access.channel-support-demand.v1` | 0.583333 | above, baseline, capacity, channel, checks, comparison, coverage, declared, demand, detection, documented, drift |
| 19 | `scenario.health.food-environment.food-system-disruption.v1` | `scenario.equity.distributional-service.equity-under-disruption.v1` | 0.582090 | access, across, below, checks, continuity, declared, demand, dependence, disruption, documented, evidence, facility |
| 20 | `scenario.public-service.demand.service-access-points.v1` | `scenario.equity.participation-communication.engagement-venues.v1` | 0.582090 | access, accessibility, authority, beyond, capacity, capacity-aware, checks, control, declared, documented, environmental, evidence |

## Completeness checks

| Value | Count |
|---|---:|
| `alternatives` | 240 |
| `assumption_registers` | 240 |
| `claim_boundaries` | 240 |
| `decision_questions` | 240 |
| `evidence_gates` | 240 |
| `hard_constraints` | 240 |
| `limitations` | 240 |
| `negative_release_rules` | 240 |
| `source_requirements` | 240 |
| `transportability_risks` | 240 |

## Remaining review boundary

Passing this audit establishes deterministic structural uniqueness and absence of near-verbatim
design copies under the declared test. It does not establish novelty in the academic-method sense,
external domain correctness, public acceptance, legal authority, feasibility, deployment, or impact.
