# Requirement-to-evidence matrix

This file is the authoritative completion checklist. A requirement is `verified` only when the named evidence exists and has been inspected. A plan, README statement, generated count, or passing narrow test is not enough.

Status vocabulary: `planned`, `in_progress`, `implemented_unverified`, `verified`, `failed`, `blocked`.

## Full flagship scope

| ID | Requirement | Status | Required completion evidence |
|---|---|---|---|
| SCALE-001 | 250 Tier-G global cities | verified | Versioned catalog, 250-row coverage matrix, semantic bundle, seed graph, portable checksums, schema validation, exact temporary rebuild, and sampled inspection |
| SCALE-002 | 30 Tier-S standardized cities, at least 3 standard scenarios each | verified | 30 validated source-bound adapters, 30 passing quality reports, 90 independent screening records, selection/exclusion audit, cross-city CSV/Markdown report, recursive checksums, and exact tree rebuild |
| SCALE-003 | 8 Tier-D cities, at least 12 deep scenarios each | verified | 8 source-bound adapters, 8 quality reports, 96 Policy Scenarios / DecisionPacks / briefs, 76 completed planning-support packs, 20 negative releases, 49-source ledger, hashes, recursive checksums, and exact full-tree rebuild |
| SCALE-004 | 25–35 public data families | in_progress | 8 source families, 10 loadable connector implementations, and 8 audited municipal dataset configurations currently verified; registry/specifications, manifests, terms, hashes, schema and negative tests exist |
| SCALE-005 | At least 1 billion non-raster observations/relations | planned | Deduplicated manifest totals with anti-inflation audit and storage query evidence |
| SCALE-006 | 1–3 TB compressed rebuildable data catalog | planned | Object inventory, byte totals, remote/local boundary and sampled rebuild |
| SCALE-007 | Urban graph targeting 100 million nodes/edges | in_progress | Evidence-typed schema and 494-node / 250-edge seed graph verify the contract; partitioned construction, query benchmarks, and target scale remain |
| SCALE-008 | 240 non-duplicative scenarios | in_progress | Three Tier-S and twelve Tier-D template designs are explicit; 90 Tier-S and 96 Tier-D city-bound executions preserve template IDs so repeated bindings cannot be miscounted as 186 non-duplicative designs |
| SCALE-009 | At least 40 historical replays | verified | 40 complete run artifacts over 20 public city-point sources and two parameters; 13,440 training and 1,200 strictly later holdout values; immutable cutoffs, four training-only baselines, held-out metrics, row ledger, hashes, and exact tree rebuild |
| SCALE-010 | At least 100 optimization tasks | verified | 100 complete solver records; 24,000 declared / 21,710 evaluated portfolios; 70 optimal with explicit zero-action comparisons, 20 proven infeasible, ten deterministic search-limited negative releases; artifact hashes and exact rebuild |
| SCALE-011 | Up to 12 identification-gated causal studies | in_progress | Strict DID design/diagnostic/claim-gate contract plus one synthetic pass and one synthetic failed-pretrend qualification exist; real domain studies and external method review remain |
| SCALE-012 | 500–800 automated checks | in_progress | The 500-test floor is met: 711 local tests pass with 95.64% statement, 89.78% branch, and 94.48% combined line-and-branch coverage. Strict typing, lint, and formatting pass; remote CI and mutation testing remain |
| SCALE-013 | 500 static figures and 80 interactive views | planned | Generated artifact manifest plus visual inspection report |
| SCALE-014 | 100 DecisionPacks and human-readable briefs | in_progress | 96 Tier-D plus 2 earlier reference DecisionPacks and same-source briefs validate and exactly rebuild; two additional non-duplicative packs remain for the 100-pack floor |
| SCALE-015 | Web, REST API, Python SDK, CLI and adapter/plugin SDK | in_progress | Clean installs, contracts, browser/API tests, package and public demo |

## Product protocols and evidence invariants

| ID | Requirement | Status | Required completion evidence |
|---|---|---|---|
| CORE-001 | Stable City Adapter schema | verified | Generated JSON Schema, positive/rejection tests, 30 real-source Tier-S adapters, and 8 deeper local-source Tier-D adapters embedded in exact-rebuild bundles |
| CORE-002 | Stable Policy Scenario schema | verified | Generated JSON Schema, positive/rejection tests, and 96 compiler-generated Tier-D scenarios with evidence, objective, constraint, time, and city bindings |
| CORE-003 | Stable DecisionPack schema | verified | Generated JSON Schema, completed and infeasible golden examples, exact rebuild audit |
| CORE-004 | Six evidence types remain distinct | verified | Model invariants and positive/rejection tests, including explicit absence of causal evidence in the demo |
| CORE-005 | Failed, infeasible, timed-out and insufficient-evidence runs are releasable | verified | Four negative status tests plus an end-to-end infeasible golden DecisionPack |
| CORE-006 | Every source artifact has version, query, license, hash and record count | verified | 90 real public source manifests covering 258,478 declared heterogeneous source units, CLI verification, attribution audit, tamper/path/archive/shape tests, and deterministic registry/specification audit |
| CORE-007 | Deterministic canonical serialization and content hashes | verified | Exact temporary-directory rebuild of Schemas, earlier references, Tier G, Tier S, 145 analytical benchmarks, and all 707 Tier-D files |
| CORE-008 | Decision reversals and value of information are first-class outputs | verified | Required protocol fields, five-case sensitivity reruns, three ranked evidence gaps, validation tests |
| CORE-009 | Cross-city transportability failures are preserved | planned | Leave-one-city tasks and negative DecisionPacks |
| CORE-010 | Natural language cannot bypass Scenario DSL validation | planned | Constrained compiler and adversarial tests |
| CORE-011 | Canonical semantic and graph interchange contracts | verified | Generated Schemas, referential-integrity and evidence-gate tests, 494-geography semantic bundle, 494-node / 250-edge seed graph, and exact rebuild |
| CORE-012 | Transparent baseline forecast contract | verified | Four baselines, rolling-origin fold evidence, eligibility exclusions, deterministic selection, intervals, negative release, JSON Schema, 40 held-out replays and tests |
| CORE-013 | Identification-gated causal contract | verified | Declared estimand/design, balance/sample/pretrend/placebo gates, causal-type upgrade protection, association fallback, positive/negative qualification and tests |
| CORE-014 | Seeded simulation and draw-lineage contract | verified | Six distributions, source/evidence gates, fixed seed, complete incremental draw-stream hash, retained prefix, quantiles, threshold, sensitivity, negative release and tests |
| CORE-015 | Uncertainty, regret and reversal contract | verified | Paired option integrity, equal tie shares, probability-best, regret, dominance, complete reversal references, robustness gate, negative release and tests |
| CORE-016 | Bounded portfolio optimization contract | verified | Expected/worst-case objectives, encoded constraints, zero-action baseline, infeasible/search-limited releases, Pareto and solver audit, 100 tasks and tests |
| CORE-017 | Benchmark evidence-ledger integrity | verified | 145 run hashes, typed row ledger, recomputed counts/work totals, artifact-set hash, three CSV projections, 152 checksums and exact full-tree rebuild |

## Seven application suites

| ID | Suite | Status | Required completion evidence |
|---|---|---|---|
| SUITE-001 | Climate and disaster resilience | in_progress | Sixteen Tier-D heat/rainfall city bindings use real workload and climate context plus forecast, simulation, optimization, uncertainty, and briefs; hazard footprints, exposure, assets, and intervention replay remain |
| SUITE-002 | Mobility and accessibility operations | in_progress | Six accessibility-request planning packs complete and ten category/network-gated packs are negative; routable multimodal networks, disruption replay, and travel-time validation remain |
| SUITE-003 | Population health and environmental exposure | in_progress | CDC PLACES and eight environmental-request Tier-D bindings preserve guarded population/climate context; no individual outcome or exposure surface is claimed |
| SUITE-004 | Housing, land use and regeneration | in_progress | Six housing-label Tier-D planning packs complete and two fail their workload gate; parcel, permit, zoning, tenure, price, and verified-condition evidence remain |
| SUITE-005 | Public service operations | in_progress | Twenty-four Tier-D total-demand, staffing, and sanitation bindings use real service requests, forecasts, allocation portfolios, uncertainty, and briefs; routing and observed service outcomes remain |
| SUITE-006 | Infrastructure finance and asset risk | in_progress | Seven infrastructure-label portfolios complete and one fails its workload gate; asset registers, condition, lifecycle cost, approved budgets, and engineering validation remain |
| SUITE-007 | Behavioral policy and equity | in_progress | Eight area-balance planning packs and eight causal-gate negative packs preserve uncertainty and distributional limits; subgroup outcomes and causal intervention evidence remain |

## Release gates

| ID | Requirement | Status | Required completion evidence |
|---|---|---|---|
| RELEASE-001 | Clean environment install | in_progress | Current-worktree wheel installs and imports in fresh Python 3.12.13 with recorded hash; repeat from a tagged release archive before verification |
| RELEASE-002 | Rebuildable public sample | verified | One-command local verifier regenerates both earlier reference DecisionPacks, Tier-G, Tier-S, all 145 analytical runs, and all 707 Tier-D files, ledgers, reports and checksums with exact byte equality |
| RELEASE-003 | Public no-login demo | planned | External browser verification and documented sample boundary |
| RELEASE-004 | Signed release, checksums and SBOM | planned | GitHub Release assets and independent verification |
| RELEASE-005 | Security and dependency scanning | in_progress | Workflows are defined; no remote result is claimed until GitHub runs them |
| RELEASE-006 | Documentation golden paths | in_progress | Reference reproduce path exists; add-city and add-scenario paths remain |
| RELEASE-007 | Claim-language audit | planned | Repository-wide fact audit against code, runs and public state |
