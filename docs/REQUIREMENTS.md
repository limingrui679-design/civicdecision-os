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
| SCALE-008 | 240 non-duplicative scenarios | verified | Exactly 240 strict designs form 30 families × 8 decision types. All substantive signatures, normalized titles, and normalized questions are unique; all 28,680 unordered pairs are checked at a fixed 0.90 token-Jaccard threshold, with maximum 0.646154 and zero failures. Twelve designs map one-to-one to Tier-D templates, 228 remain design-only, city bindings and method claims are schema-fixed at zero/false, and all 282 library files exactly rebuild |
| SCALE-009 | At least 40 historical replays | verified | 40 complete run artifacts over 20 public city-point sources and two parameters; 13,440 training and 1,200 strictly later holdout values; immutable cutoffs, four training-only baselines, held-out metrics, row ledger, hashes, and exact tree rebuild |
| SCALE-010 | At least 100 optimization tasks | verified | 100 complete solver records; 24,000 declared / 21,710 evaluated portfolios; 70 optimal with explicit zero-action comparisons, 20 proven infeasible, ten deterministic search-limited negative releases; artifact hashes and exact rebuild |
| SCALE-011 | Up to 12 identification-gated causal studies | in_progress | Strict DID design/diagnostic/claim-gate contract plus one synthetic pass and one synthetic failed-pretrend qualification exist; real domain studies and external method review remain |
| SCALE-012 | 500–800 automated checks | verified | Exactly 800 local tests pass with 97.111% statement, 91.129% branch, and 95.911% combined line-and-branch coverage. The collection exercises positive, negative, tamper, exact-rebuild, API, SDK, CLI, plugin, product-package, real wheel/sdist, complete `RECORD`, deterministic ZIP, checksum, archive-budget, unsafe-path, link, inventory, metadata, quantitative-claim, public-state, and policy-drift behavior. Strict typing, lint, formatting, and JavaScript syntax checks also pass. Remote CI and mutation testing remain separate release-hardening work |
| SCALE-013 | 500 static figures and 80 interactive views | planned | Generated artifact manifest plus visual inspection report |
| SCALE-014 | 100 DecisionPacks and human-readable briefs | in_progress | 96 Tier-D plus 2 earlier reference DecisionPacks and same-source briefs validate and exactly rebuild; two additional non-duplicative packs remain for the 100-pack floor |
| SCALE-015 | Web, REST API, Python SDK, CLI and adapter/plugin SDK | verified | One validated artifact store projects 258 cities, 240 designs, 30 design families, 188 executions, 98 DecisionPacks, 90 sources, seven suites, and 145 benchmark runs through a responsive browser, 19-path read-only API, local/sync/async Python SDKs, CLI, and exact-allowlist data-only plugin SDK. The 338-file product tree exactly rebuilds; the installed 0.8.0 wheel passes isolated CLI/SDK/API/Web/plugin smoke from a no-Git source archive. Public hosting remains a separate release gate |

## Product protocols and evidence invariants

| ID | Requirement | Status | Required completion evidence |
|---|---|---|---|
| CORE-001 | Stable City Adapter schema | verified | Generated JSON Schema, positive/rejection tests, 30 real-source Tier-S adapters, and 8 deeper local-source Tier-D adapters embedded in exact-rebuild bundles |
| CORE-002 | Stable Policy Scenario schema | verified | Generated JSON Schema, positive/rejection tests, and 96 compiler-generated Tier-D scenarios with evidence, objective, constraint, time, and city bindings |
| CORE-003 | Stable DecisionPack schema | verified | Generated JSON Schema, completed and infeasible golden examples, exact rebuild audit |
| CORE-004 | Six evidence types remain distinct | verified | Model invariants and positive/rejection tests, including explicit absence of causal evidence in the demo |
| CORE-005 | Failed, infeasible, timed-out and insufficient-evidence runs are releasable | verified | Four negative status tests plus an end-to-end infeasible golden DecisionPack |
| CORE-006 | Every source artifact has version, query, license, hash and record count | verified | 90 real public source manifests covering 258,478 declared heterogeneous source units, CLI verification, attribution audit, tamper/path/archive/shape tests, and deterministic registry/specification audit |
| CORE-007 | Deterministic canonical serialization and content hashes | verified | Exact temporary-directory rebuild of 27 core/library Schemas, earlier references, Tier G, Tier S, 145 analytical benchmarks, all 707 Tier-D files, all 282 scenario-library files, and the complete 338-file product projection with 28 product/plugin/library Schemas and portable checksums |
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
| CORE-018 | Audited scenario-design library contract | verified | Strict design/family/registry/audit/manifest models; 30×8 complete matrix; seven-field substantive signatures; exact and 28,680-pair lexical audits; one primary objective and binding constraint per design; negative release gates; one-to-one Tier-D reference mapping; zero city-binding/method inflation; 280-entry manifest, 281 checksum targets, 282 total files, and exact rebuild |

## Seven application suites

| ID | Suite | Status | Required completion evidence |
|---|---|---|---|
| SUITE-001 | Climate and disaster resilience | in_progress | Five library families and 40 designs are complete; sixteen Tier-D heat/rainfall city bindings use real workload and climate context plus forecast, simulation, optimization, uncertainty, and briefs. Hazard footprints, exposure, assets, and intervention replay remain |
| SUITE-002 | Mobility and accessibility operations | in_progress | Five library families and 40 designs are complete; six accessibility-request planning packs complete and ten category/network-gated packs are negative. Routable multimodal networks, disruption replay, and travel-time validation remain |
| SUITE-003 | Population health and environmental exposure | in_progress | Four library families and 32 designs are complete; CDC PLACES and eight environmental-request Tier-D bindings preserve guarded population/climate context. No individual outcome or exposure surface is claimed |
| SUITE-004 | Housing, land use and regeneration | in_progress | Four library families and 32 designs are complete; six housing-label Tier-D planning packs complete and two fail their workload gate. Parcel, permit, zoning, tenure, price, and verified-condition evidence remain |
| SUITE-005 | Public service operations | in_progress | Four library families and 32 designs are complete; twenty-four Tier-D total-demand, staffing, and sanitation bindings use real service requests, forecasts, allocation portfolios, uncertainty, and briefs. Routing and observed service outcomes remain |
| SUITE-006 | Infrastructure finance and asset risk | in_progress | Four library families and 32 designs are complete; seven infrastructure-label portfolios complete and one fails its workload gate. Asset registers, condition, lifecycle cost, approved budgets, and engineering validation remain |
| SUITE-007 | Behavioral policy and equity | in_progress | Four library families and 32 designs are complete; eight area-balance planning packs and eight causal-gate negative packs preserve uncertainty and distributional limits. Subgroup outcomes and causal intervention evidence remain |

## Release gates

| ID | Requirement | Status | Required completion evidence |
|---|---|---|---|
| RELEASE-001 | Clean environment install | in_progress | The current 0.8.0 candidate passes two byte-identical wheel/sdist builds, strict archive/metadata/`RECORD` inspection, a fresh 23-package hash-locked runtime install, no-index/no-deps wheel install, `pip check`, installed CLI/SDK/API/Web/plugin smoke, and a complete no-Git source-archive rebuild. A published tagged archive and independent repeat remain before closing the public-release gate |
| RELEASE-002 | Rebuildable public sample | verified | One-command local verifier regenerates both earlier reference DecisionPacks, Tier-G, Tier-S, all 145 analytical runs, all 707 Tier-D files, all 282 scenario-library files, and all 338 product files, ledgers, reports and checksums with exact byte equality |
| RELEASE-003 | Public no-login demo | planned | External browser verification and documented sample boundary |
| RELEASE-004 | Signed release, checksums and SBOM | in_progress | Published GitHub Release carries a validated CycloneDX 1.6 SBOM, portable per-asset checksum inventory, deterministic release bundle, and detached bundle SHA-256. A cryptographic signature/trusted provenance and independent verification remain |
| RELEASE-005 | Security and dependency scanning | in_progress | Local release gate records zero medium-or-higher Bandit findings, zero unresolved findings across all eligible secret-scanned code/document files, and zero known advisories among 23 exact locked runtime dependencies at check time; security and CodeQL workflows exist, but no remote result is claimed until GitHub runs them |
| RELEASE-006 | Documentation golden paths | in_progress | Reference reproduce, scenario-library build/review, product build, local serving, REST API, Python SDK, CLI, web explorer, and data-only plugin paths exist; full add-city and city-bound scenario contributor paths remain |
| RELEASE-007 | Claim-language audit | verified | A deterministic policy scans governed source/document surfaces, rejects false hosted URLs and stale publication language, reconciles quantitative statements against versioned JSON evidence, requires explicit scope boundaries, verifies the declared Git remote and package project URLs, and refreshes the dated public-repository assertion against the official GitHub API. Offline release builds re-run the audit against the committed public-state snapshot without turning it into external validation |
