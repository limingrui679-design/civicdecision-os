# Audited 240-design scenario library

## Purpose and scope

The CivicDecision scenario library is a deterministic catalog of **240 urban-policy decision
designs**, organized as **30 substantive domain families × 8 decision types**. It is a planning
and implementation specification layer: it tells a future compiler what decision is being made,
what alternatives and objectives must be compared, what constraints bind, what evidence is
required, and when a recommendation must be withheld.

The library deliberately does **not** claim 240 city projects, analyses, methods, deployments,
users, or outcomes. Its current verified boundary is:

| Measure | Verified value | Interpretation |
|---|---:|---|
| Scenario designs | 240 | Typed decision contracts |
| Domain families | 30 | Eight decision types per family |
| Application suites | 7 | Cross-domain grouping |
| Reference-implemented designs | 12 | One-to-one mappings to existing Tier-D templates |
| Design-only records | 228 | No current city execution |
| City bindings counted by this library | 0 | Binding requires a separate execution artifact |
| New analytical methods claimed | 0 | Designs reuse declared method classes |
| Unordered pairs audited | 28,680 | Every possible pair among 240 designs |
| Exact substantive-signature collisions | 0 | Seven-field independence keys are unique |
| Duplicate normalized titles | 0 | Exact normalized comparison |
| Duplicate normalized questions | 0 | Exact normalized comparison |
| Similarity failure threshold | 0.90 | Fixed before audit execution |
| Maximum observed token Jaccard | 0.646154 | Below the failure threshold |
| High-similarity pairs at/above threshold | 0 | No audit failure |

Passing this audit establishes deterministic structural separation and completeness under the
declared rules. It does not establish academic novelty, external domain correctness, legal
authority, community acceptance, implementation feasibility, public deployment, adoption, or
impact.

## Coverage grammar

Every family contains exactly one design for each decision type:

| Decision type | Core question | Typical artifact boundary |
|---|---|---|
| `diagnose` | What condition, disparity, failure pattern, or unmet need exists? | Descriptive evidence; no intervention effect |
| `forecast` | What demand, hazard, capacity, or service state may occur over a declared horizon? | Estimated future values with calibration limits |
| `prioritize` | Which assets, cases, or interventions should enter a ranked queue? | Proposed ranking under explicit objectives and constraints |
| `site` | Where should facilities, assets, or service points be located? | Proposed locations; not acquired, permitted, or built |
| `allocate` | How should bounded resources be distributed? | Optimized allocation conditional on inputs and policy weights |
| `schedule` | When and in what sequence should actions occur? | Proposed operating or capital schedule |
| `stress-test` | How does the system behave under adverse or compound conditions? | Simulated resilience evidence; not an observed event outcome |
| `evaluate` | Did a program or decision process change the declared outcome? | Causal only if identification gates pass; otherwise estimated association |

The repeated eight-type grammar is a coverage matrix, not evidence of duplication. Independence is
determined from the decision's substantive axes rather than its family or title.

## Application-suite inventory

| Application suite | Families | Designs |
|---|---:|---:|
| Climate and disaster resilience | 5 | 40 |
| Mobility, accessibility, and operations | 5 | 40 |
| Population health and environmental exposure | 4 | 32 |
| Housing, land use, and regeneration | 4 | 32 |
| Public-service operations | 4 | 32 |
| Infrastructure, finance, and asset risk | 4 | 32 |
| Behavioral policy and equity | 4 | 32 |
| **Total** | **30** | **240** |

### Families 1–10: climate and mobility

| # | Family ID | Title | Designs |
|---:|---|---|---:|
| 1 | `climate.extreme-heat` | Extreme heat exposure and response | 8 |
| 2 | `climate.flood-stormwater` | Flood and stormwater resilience | 8 |
| 3 | `climate.wildfire-smoke` | Wildfire smoke and air-quality resilience | 8 |
| 4 | `climate.drought-water` | Drought and urban water security | 8 |
| 5 | `climate.coastal-storms` | Coastal storms and sea-level adaptation | 8 |
| 6 | `mobility.transit-reliability` | Transit reliability and passenger continuity | 8 |
| 7 | `mobility.pedestrian-safety` | Pedestrian safety and universal accessibility | 8 |
| 8 | `mobility.freight-curb` | Urban freight and curb operations | 8 |
| 9 | `mobility.emergency-mobility` | Evacuation and emergency mobility | 8 |
| 10 | `mobility.active-mobility` | Active mobility network and micromobility | 8 |

### Families 11–18: health and housing

| # | Family ID | Title | Designs |
|---:|---|---|---:|
| 11 | `health.heat-health` | Heat-health surveillance and prevention | 8 |
| 12 | `health.air-quality` | Air-quality exposure and respiratory health | 8 |
| 13 | `health.infectious-operations` | Infectious-disease public-health operations | 8 |
| 14 | `health.food-environment` | Food access and environmental health | 8 |
| 15 | `housing.habitability-code` | Housing habitability and code operations | 8 |
| 16 | `housing.homelessness-prevention` | Homelessness prevention and housing stability | 8 |
| 17 | `housing.affordable-supply` | Affordable housing siting and preservation | 8 |
| 18 | `housing.land-use-regeneration` | Land use, regeneration, and neighborhood change | 8 |

### Families 19–30: public service, infrastructure, and equity

| # | Family ID | Title | Designs |
|---:|---|---|---:|
| 19 | `public-service.demand` | 311 and public-service demand operations | 8 |
| 20 | `public-service.sanitation` | Sanitation, waste, and street cleanliness | 8 |
| 21 | `public-service.emergency-response` | Emergency response readiness and allocation | 8 |
| 22 | `public-service.digital-access` | Digital public access and administrative service delivery | 8 |
| 23 | `infrastructure.roads-bridges` | Road and bridge asset management | 8 |
| 24 | `infrastructure.water-wastewater` | Water and wastewater infrastructure | 8 |
| 25 | `infrastructure.energy-buildings` | Municipal energy and building decarbonization | 8 |
| 26 | `infrastructure.capital-finance` | Capital portfolio and municipal finance | 8 |
| 27 | `equity.distributional-service` | Distributional public-service equity | 8 |
| 28 | `equity.participation-communication` | Public participation and risk communication | 8 |
| 29 | `equity.compliance-incentives` | Compliance, incentives, and behavioral policy | 8 |
| 30 | `equity.algorithmic-governance` | Algorithmic decision support and governance | 8 |

## Complete design contract

Every `ScenarioDesign` is a strict model with the following layers.

### Identity and decision context

- contiguous `design_order` from 1 through 240;
- globally unique, versioned `design_id`;
- registered `family_id` and application suite;
- title and explicit decision question;
- accountable decision owner and affected system;
- decision type, horizon, cadence, and spatial unit.

### Alternatives and objectives

- one declared baseline;
- at least three non-duplicate alternatives;
- exactly one primary objective;
- additional distributional and evidence-lineage objectives;
- direction (`minimize` or `maximize`), unit, and evidence type for every objective.

### Constraints

Every design contains at least three constraints:

1. one and only one binding domain constraint;
2. a hard evidence-scope constraint requiring type, lineage, geography, time, assumptions, and
   uncertainty; and
3. a hard accountable-authority constraint preventing analytical output from bypassing lawful
   authority, human review, or an applicable appeal process.

Constraint source roles must be a subset of the design's declared source roles. Duplicate
constraint IDs and undeclared source dependencies fail validation.

### Evidence and release gate

Each design declares:

- one or more analysis modes;
- required evidence types;
- required source roles;
- a typed gate and human-readable pass condition;
- an explicit `insufficient-evidence` failure status; and
- a required negative release that names missing sources, failed diagnostics, prohibited claims,
  and the next validation action.

The schema prevents a causal analysis mode from appearing without causal evidence and a causal
identification gate. Calibration, external-validity, geographic, temporal, network, cost/capacity,
legal-authority, lineage, completeness, and equity-measurement gates remain separately typed.

### Interpretation boundary

Every design records:

- an intended claim;
- at least four prohibited claims;
- assumptions;
- limitations;
- transportability risks; and
- sorted tags containing its suite, family, decision type, and implementation status.

The design schema constrains `city_bindings` to an empty list and `method_claimed` to literal
`false`. A design therefore cannot be edited in place into a city execution or a method claim.

## Substantive independence and anti-duplication audit

### Seven-field independence key

Every design hashes the following fields:

1. decision object;
2. intervention mechanism;
3. primary outcome;
4. binding constraint;
5. evidence-gate pass condition;
6. decision horizon; and
7. spatial unit.

The design ID, title, family label, application-suite label, and city name are excluded. Renaming a
design or copying it to another city therefore cannot create a new substantive signature.

### Exact checks

The builder fails if it finds:

- a repeated substantive signature;
- a repeated exact-normalized title;
- a repeated exact-normalized decision question;
- a missing family/decision-type cell;
- a non-contiguous order;
- a reused reference-template mapping; or
- an incomplete design contract.

### Pairwise lexical check

For every one of the 28,680 unordered pairs, the audit tokenizes the title, decision question, and
seven substantive axes; lowercases terms; removes a fixed, small stopword set; and calculates set
Jaccard similarity. Any pair at or above 0.90 fails the build. The maximum current value is
0.646154.

This lexical check is intentionally transparent and supplementary. A low Jaccard score does not
prove conceptual or academic novelty; external specialists still need to review domain validity.

### Completeness checks

All ten audit counters equal 240:

- alternatives;
- assumption registers;
- claim boundaries;
- decision questions;
- evidence gates;
- hard constraints;
- limitations;
- negative-release rules;
- source requirements; and
- transportability risks.

## Reference implementation mapping

Exactly twelve library designs map one-to-one to the twelve existing Tier-D templates. The mapping
shows a bounded implementation path; it does not establish complete local inputs, external
validity, deployment, adoption, or impact.

| Scenario-library design | Existing Tier-D template | Scope |
|---|---|---|
| `scenario.climate.extreme-heat.compound-heat-continuity.v1` | `deep.climate.heat-service-surge.v1` | Compound-heat continuity stress test |
| `scenario.climate.flood-stormwater.compound-rainfall-continuity.v1` | `deep.climate.rainfall-continuity.v1` | Rainfall/outage continuity stress test |
| `scenario.mobility.pedestrian-safety.accessible-route-breaks.v1` | `deep.mobility.accessibility-request.v1` | Accessible-route diagnostic |
| `scenario.mobility.emergency-mobility.phased-evacuation.v1` | `deep.mobility.real-time-reroute.v1` | Phased evacuation schedule |
| `scenario.health.air-quality.exposure-health-discordance.v1` | `deep.health.environmental-request-screen.v1` | Exposure/health diagnostic |
| `scenario.housing.habitability-code.habitability-interventions.v1` | `deep.housing.request-triage.v1` | Habitability intervention prioritization |
| `scenario.public-service.demand.service-improvement-portfolio.v1` | `deep.public-service.total-demand.v1` | Service-improvement prioritization |
| `scenario.public-service.demand.seasonal-service-staffing.v1` | `deep.public-service.seasonal-staffing.v1` | Seasonal staffing schedule |
| `scenario.public-service.sanitation.sanitation-improvements.v1` | `deep.public-service.sanitation-workload.v1` | Sanitation improvement prioritization |
| `scenario.infrastructure.roads-bridges.maintenance-renewal.v1` | `deep.infrastructure.maintenance-portfolio.v1` | Maintenance/renewal prioritization |
| `scenario.equity.distributional-service.minimum-service-capacity.v1` | `deep.equity.area-balance.v1` | Equity-constrained capacity allocation |
| `scenario.equity.algorithmic-governance.decision-support-effect.v1` | `deep.equity.causal-service-effectiveness.v1` | Decision-support effect evaluation |

The other 228 records remain `design-only`.

## Current readiness

Readiness is computed against the source roles and method implementations currently present in the
repository. It is not a feasibility certificate.

| Readiness | Count | Meaning |
|---|---:|---|
| `reference-implemented` | 12 | A bounded Tier-D template exists |
| `blocked-missing-source` | 199 | One or more required source roles are absent |
| `blocked-multiple-gates` | 29 | Source and causal-method gates both remain |
| `blocked-method` | 0 | No design is blocked solely by the current method rule |
| `uncompiled-current-inputs` | 0 | No design currently has all inputs but no compilation |

These counts may change only through a deterministic rebuild after source-role or method status
changes. They are not manually edited success labels.

## Artifact inventory and reproducibility

The committed `catalog/scenario-library/` tree contains exactly **282 files**:

- 240 full design JSON documents;
- 30 full family JSON documents;
- one 270-entry registry covering designs and families;
- one anti-duplication audit JSON document;
- one 240-row coverage CSV;
- one human-readable summary;
- one human-readable anti-duplication report;
- five JSON Schemas;
- one 280-entry artifact manifest; and
- one portable checksum inventory covering the other 281 files.

The builder rejects symlink output roots, unsafe relative paths, missing registered artifacts,
hash drift, unexpected stale files, wrong object counts, and non-reconciling manifests. The
independent repository verifier rebuilds the complete tree in an isolated temporary directory and
requires path-for-path, byte-for-byte equality.

Build and verify:

```bash
civicdecision catalog build-scenario-library \
  --root . \
  --output catalog/scenario-library

python scripts/verify_repository.py
```

The raw library and its product projection are separate deterministic outputs. The static product
tree contains 240 API-shaped design details, 30 family details, total/status/suite/decision-type
indexes, the audit, registry, summary, schemas, OpenAPI document, and hashed web assets.

## Product access

### REST API

| Route | Result |
|---|---|
| `GET /api/v1/designs` | Paginated design summaries with compound filters |
| `GET /api/v1/designs/{design_id}` | Full design, family context, audit maximum, and claim boundary |
| `GET /api/v1/design-families` | Paginated family summaries |
| `GET /api/v1/design-families/{family_id}` | Full family plus its eight ordered design summaries |
| `GET /api/v1/evidence/scenario-library` | Concise audit and non-inflation evidence |

Design filters are `suite`, `family_id`, `decision_type`, `implementation_status`,
`current_readiness`, and `q`. Search normalizes case and punctuation so `cool roof` can match
`cool-roof`. Pagination remains bounded to `limit=1..100` and a nonnegative offset.

### Python SDK

The local, synchronous HTTP, and asynchronous HTTP clients expose the same methods:

```python
from civicdecision.scenario_library import DecisionType, ImplementationStatus
from civicdecision.sdk import CivicDecisionSDK

sdk = CivicDecisionSDK.open(".")

evaluation_designs = sdk.designs(
    decision_type=DecisionType.EVALUATE,
    implementation_status=ImplementationStatus.DESIGN_ONLY,
    limit=100,
)
design = sdk.design("scenario.climate.extreme-heat.heat-access-gaps.v1")
families = sdk.design_families(limit=100)
family = sdk.design_family("climate.extreme-heat")
audit = sdk.scenario_library_evidence()
```

### Command line

```bash
civicdecision catalog designs \
  --decision-type evaluate \
  --implementation-status design-only \
  --limit 100

civicdecision catalog design \
  scenario.climate.extreme-heat.heat-access-gaps.v1

civicdecision catalog design-families --suite climate-disaster-resilience
civicdecision catalog design-family climate.extreme-heat
civicdecision catalog scenario-library-evidence
```

### Evidence explorer

The browser surface provides:

- six headline audit indicators;
- explicit zero city-binding and zero method-claim indicators;
- all 30 family filters;
- suite, decision-type, implementation, readiness, and normalized-text filters;
- paginated design cards;
- full design details for objectives, constraints, evidence gate, source roles, assumptions,
  limitations, prohibited claims, and transportability risks;
- family details with all eight ordered decision types; and
- a dedicated anti-duplication and non-inflation evidence view.

Browser rendering and interactions were checked at the default desktop viewport and at 390 × 844.
That local check is not a public-host availability, external accessibility, or cross-browser
certification claim.

## How to turn a design into an execution

1. Select a design by decision object rather than by a desired result.
2. Create a separate city-binding execution artifact; never mutate `city_bindings` in the design.
3. Resolve geographic identity, temporal scope, units, source licenses, and every required source
   role.
4. Declare local alternatives, costs, capacities, effects, constraints, and decision authority.
5. Compile observed, estimated, causal, simulated, optimized, and proposed evidence without
   relabeling.
6. Execute the stated gate and retain diagnostics.
7. If the gate fails, publish the required `insufficient-evidence` release and withhold a selected
   option.
8. Obtain domain, legal, privacy, security, community, accessibility, and operational review as
   applicable.
9. Record deployment, adoption, user, or impact evidence only in a separate externally verifiable
   artifact after it exists.

## Reviewer checklist

A reviewer should be able to answer yes to each of the following before accepting the library as
internally reproducible:

- Are there exactly 30 families and 240 designs?
- Does every family contain all eight decision types exactly once?
- Are all design IDs, titles, questions, and substantive signatures unique?
- Does every design have one baseline and at least three alternatives?
- Does every design contain exactly one primary objective and one binding constraint?
- Do constraint and gate source roles reconcile with the design source-role set?
- Does every causal mode require causal evidence and an identification gate?
- Does every failed gate prescribe an explicit negative release?
- Are the twelve reference mappings one-to-one with the twelve Tier-D templates?
- Do the remaining 228 records remain design-only?
- Are city bindings and method claims both zero?
- Does the 28,680-pair audit pass at the fixed threshold?
- Does the manifest cover 280 base artifacts and the checksum inventory cover 281 targets?
- Does an isolated rebuild reproduce all 282 files exactly?
- Do API, SDK, CLI, browser, and static projections preserve the same claim boundary?

## Known limitations and next evidence gates

- The pairwise lexical diagnostic cannot prove conceptual novelty.
- All 240 designs have not received independent domain-specialist review.
- Affected communities have not reviewed or accepted the complete design set.
- Readiness uses current repository source roles and may not reflect a particular city's lawful or
  technically available data.
- Proposed alternatives, costs, capacities, effects, thresholds, and stressors remain hypothetical
  until bound to evidence.
- The twelve reference mappings establish bounded internal implementation behavior only.
- No public deployment, institutional adoption, independently verified real-user usage, or observed
  intervention impact is claimed by the library.
- External security, privacy, accessibility, legal, and governance certification remains outside
  this artifact.

Breadth is valuable because it makes the system's decision grammar explicit and reusable. It is
credible only while design counts remain visibly separate from execution and outcome counts.
