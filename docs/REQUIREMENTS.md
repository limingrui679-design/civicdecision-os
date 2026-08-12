# Requirement-to-evidence matrix

This file is the authoritative completion checklist. A requirement is `verified` only when the named evidence exists and has been inspected. A plan, README statement, generated count, or passing narrow test is not enough.

Status vocabulary: `planned`, `in_progress`, `implemented_unverified`, `verified`, `failed`, `blocked`.

## Full flagship scope

| ID | Requirement | Status | Required completion evidence |
|---|---|---|---|
| SCALE-001 | 250 Tier-G global cities | verified | Versioned catalog, 250-row coverage matrix, semantic bundle, seed graph, portable checksums, schema validation, exact temporary rebuild, and sampled inspection |
| SCALE-002 | 30 Tier-S standardized cities, at least 3 standard scenarios each | planned | 30 validated adapters, 90 scenario run records, cross-city comparison report |
| SCALE-003 | 8 Tier-D cities, at least 12 deep scenarios each | planned | 8 independent adapters and 96 end-to-end scenario packs |
| SCALE-004 | 25–35 public data families | in_progress | 8 loadable connector families currently verified; registry, manifests, terms, hashes, schema and negative tests exist |
| SCALE-005 | At least 1 billion non-raster observations/relations | planned | Deduplicated manifest totals with anti-inflation audit and storage query evidence |
| SCALE-006 | 1–3 TB compressed rebuildable data catalog | planned | Object inventory, byte totals, remote/local boundary and sampled rebuild |
| SCALE-007 | Urban graph targeting 100 million nodes/edges | in_progress | Evidence-typed schema and 494-node / 250-edge seed graph verify the contract; partitioned construction, query benchmarks, and target scale remain |
| SCALE-008 | 240 non-duplicative scenarios | planned | Scenario registry plus successful/negative run artifacts and semantic-duplicate audit |
| SCALE-009 | At least 40 historical replays | planned | Data-cutoff proof, replay configs, baselines and held-out results |
| SCALE-010 | At least 100 optimization tasks | planned | Solver records, baseline comparisons, infeasible/timeout preservation |
| SCALE-011 | Up to 12 identification-gated causal studies | planned | Estimands, designs, diagnostics, refutations and cautious result language |
| SCALE-012 | 500–800 automated checks | in_progress | 169 local tests and 93.59% branch-aware coverage; remote CI and mutation testing remain |
| SCALE-013 | 500 static figures and 80 interactive views | planned | Generated artifact manifest plus visual inspection report |
| SCALE-014 | 100 DecisionPacks and human-readable briefs | planned | Same-source JSON and rendered outputs, schema validation and sampled recomputation |
| SCALE-015 | Web, REST API, Python SDK, CLI and adapter/plugin SDK | in_progress | Clean installs, contracts, browser/API tests, package and public demo |

## Product protocols and evidence invariants

| ID | Requirement | Status | Required completion evidence |
|---|---|---|---|
| CORE-001 | Stable City Adapter schema | in_progress | Generated JSON Schema, validator tests, one real adapter |
| CORE-002 | Stable Policy Scenario schema | in_progress | Generated JSON Schema, positive/negative fixtures and compiler test |
| CORE-003 | Stable DecisionPack schema | verified | Generated JSON Schema, completed and infeasible golden examples, exact rebuild audit |
| CORE-004 | Six evidence types remain distinct | verified | Model invariants and positive/rejection tests, including explicit absence of causal evidence in the demo |
| CORE-005 | Failed, infeasible, timed-out and insufficient-evidence runs are releasable | verified | Four negative status tests plus an end-to-end infeasible golden DecisionPack |
| CORE-006 | Every source artifact has version, query, license, hash and record count | verified | Eight real public source artifacts, CLI verification, tamper/path/archive/shape tests, and deterministic registry audit |
| CORE-007 | Deterministic canonical serialization and content hashes | verified | Exact temporary-directory rebuild of Schemas, JSON, brief, and portable checksums |
| CORE-008 | Decision reversals and value of information are first-class outputs | verified | Required protocol fields, five-case sensitivity reruns, three ranked evidence gaps, validation tests |
| CORE-009 | Cross-city transportability failures are preserved | planned | Leave-one-city tasks and negative DecisionPacks |
| CORE-010 | Natural language cannot bypass Scenario DSL validation | planned | Constrained compiler and adversarial tests |
| CORE-011 | Canonical semantic and graph interchange contracts | verified | Generated Schemas, referential-integrity and evidence-gate tests, 494-geography semantic bundle, 494-node / 250-edge seed graph, and exact rebuild |

## Seven application suites

| ID | Suite | Status | Required completion evidence |
|---|---|---|---|
| SUITE-001 | Climate and disaster resilience | planned | Real data, replay, simulation, optimization and brief |
| SUITE-002 | Mobility and accessibility operations | planned | Multimodal network, disruption replay and allocation task |
| SUITE-003 | Population health and environmental exposure | in_progress | CDC PLACES connector, exposure model and guarded interpretation |
| SUITE-004 | Housing, land use and regeneration | planned | Real planning/permit data and policy scenario |
| SUITE-005 | Public service operations | planned | Real service-request data, forecasting and routing/allocation |
| SUITE-006 | Infrastructure finance and asset risk | planned | Public capital/asset data and constrained portfolio task |
| SUITE-007 | Behavioral policy and equity | planned | Population/behavior parameters, uncertainty and distributional report |

## Release gates

| ID | Requirement | Status | Required completion evidence |
|---|---|---|---|
| RELEASE-001 | Clean environment install | in_progress | Fresh environment log from tagged archive |
| RELEASE-002 | Rebuildable public sample | verified | One-command local verifier regenerates both reference runs and requires byte equality |
| RELEASE-003 | Public no-login demo | planned | External browser verification and documented sample boundary |
| RELEASE-004 | Signed release, checksums and SBOM | planned | GitHub Release assets and independent verification |
| RELEASE-005 | Security and dependency scanning | in_progress | Workflows are defined; no remote result is claimed until GitHub runs them |
| RELEASE-006 | Documentation golden paths | in_progress | Reference reproduce path exists; add-city and add-scenario paths remain |
| RELEASE-007 | Claim-language audit | planned | Repository-wide fact audit against code, runs and public state |
