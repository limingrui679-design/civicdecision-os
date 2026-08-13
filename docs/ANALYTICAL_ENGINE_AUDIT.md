# Analytical engine and benchmark audit

Updated: 2026-08-13

## Audit conclusion

Milestone 4 is a reproducible analytical-software and public-data evaluation milestone. It adds
five typed engine families, 145 complete run artifacts, a machine-validated evidence ledger, three
row-level CSV projections, a human audit report, 17 generated JSON Schemas, and a portable
checksum tree. The repository verifier rebuilds the entire tree from committed sources and
requires exact bytes.

This evidence supports claims about implementation, deterministic replay, declared task volume,
failure preservation, and bounded solver behavior. It does not support claims of live forecasting,
field causal validity, policy effectiveness, users, clients, adoption, deployment, or real-world
impact.

## Evidence chain

Each benchmark result follows the same reviewable chain:

```text
committed source or synthetic qualification definition
  -> strict input model
  -> typed analytical run
  -> complete canonical JSON run artifact
  -> SHA-256 file hash
  -> row in evidence-summary.json
  -> artifact-set hash in registry.json
  -> recursive portable SHA256SUMS
  -> exact rebuild in a fresh temporary directory
```

The authoritative inventory is [`../benchmarks/milestone-4/registry.json`](../benchmarks/milestone-4/registry.json).
The reviewer-oriented ledger is
[`../benchmarks/milestone-4/evidence-summary.json`](../benchmarks/milestone-4/evidence-summary.json).
The concise audit is [`../benchmarks/milestone-4/summary.md`](../benchmarks/milestone-4/summary.md).

## Forecast engine

The forecast engine implements four transparent baselines: naive, drift, moving average, and
seasonal naive. It requires unique, ordered, regularly spaced timestamps. For every configured
method it preserves eligibility, exclusion reasons, every rolling-origin fold, actual and predicted
vectors, absolute errors, MAE, RMSE, WAPE when defined, bias, interval coverage, interval width,
and conformal-style residual radius. Selection uses training-fold WAPE, then MAE and stable method
name. The later benchmark holdout is not used for method selection.

If no method clears the declared history and fold requirements, the engine emits
`insufficient-evidence` with no selected method or forecast. Completed output is always
`estimated`, never causal or observed. Nonnegative series can clamp point and lower predictions at
zero. The intervals remain explicitly limited under distribution shift.

The historical benchmark contains 40 tasks: 20 Tier-S city-point artifacts crossed with mean
temperature (`T2M`) and precipitation (`PRECTOTCORR`). Each task trains on 336 daily observations
and evaluates a strictly later 30-day holdout. Across the full benchmark this is 13,440 training
values and 1,200 held-out values. Method selection counts are 19 moving-average, 13 naive, six
seasonal-naive, and two drift. These are 40 tasks over 20 cities and two variables—not 40 cities or
40 independent datasets.

## Identification-gated causal engine

The causal engine implements a deliberately narrow two-group balanced-panel
difference-in-differences estimator. The design must declare an estimand, treatment and comparison
definitions, assignment mechanism, no-anticipation rationale, parallel-trends rationale,
no-interference rationale, source references, and limitations.

Before a causal type can be issued, the run checks minimum treated and comparison units, minimum
pre and post periods, balanced unit-period coverage, full-confidence-interval equivalence of the
treated-minus-comparison pretrend slope, and equivalence of every pre-period placebo contrast. A
passing run retains primary and event-time effects plus every diagnostic. A failed gate preserves
computable estimates as `estimated` associations, sets `causal_claim_issued=false`, and records the
failure reason. Observable pretrend and placebo tests are never described as proof of unobservable
counterfactual assumptions.

Milestone 4 includes one synthetic pass and one synthetic failed-pretrend qualification. These
prove the claim gate and negative path. They are not counted as real causal studies, so the
separate target for externally credible identification studies remains incomplete.

## Seeded simulation engine

The Monte Carlo engine supports fixed, uniform, triangular, normal, Bernoulli, and empirical
parameter distributions. Estimated parameters require source references; proposed parameters stay
explicitly proposed. The model contract declares coefficients, units, assumptions, limitations,
and optional floors and ceilings. Parameter IDs must exactly cover model terms.

Each run records its iteration count, random seed, quantiles, retained-draw count, optional
threshold and direction, outcome summary, threshold probability, and input-output Pearson
associations. Association ranks are labeled non-causal. Rather than retaining a large in-memory
serialization of every draw, the engine incrementally hashes every canonical draw record with an
eight-byte length prefix. It keeps only the configured ordered prefix for human inspection. This
preserves deterministic replay evidence while bounding serialization memory.

Milestone 4 includes a 10,000-iteration seeded qualification run. It demonstrates engine behavior,
not a city-calibrated model or observed consequence.

## Uncertainty and reversal engine

The uncertainty engine requires at least two aligned option draw streams for joint comparisons.
It computes mean, standard deviation, central interval, probability of being best, expected and
maximum regret, dominated probability, every unique pairwise dominance comparison, and one
reversal record for each non-baseline option. Exact ties split probability-best mass equally; only
the final deterministic selection tie uses stable option ID.

A `robust-winner` must clear both the configured probability-best threshold and optional maximum
expected-regret limit. Otherwise the result is `reversal-risk`. Unaligned or insufficient options
emit `insufficient-evidence` without comparison output. The type remains estimated or simulated
according to inputs. Probability-best is expressly not probability of policy success.

Milestone 4 contains one robust-winner qualification and one crossing-draw reversal-risk
qualification, including a recorded first reversal draw.

## Portfolio optimization engine

The optimizer accepts bounded integer actions, three-scenario or other shared objective values,
expected or worst-case strategy, budget, capacity, risk, minimum benefit, group-benefit floors,
and action-count constraints. It evaluates the declared finite Cartesian search space in stable
order up to a deterministic evaluation cap. Every plan records quantities, cost, capacity, risk,
benefits, scenario objectives, objective value, feasibility, violations, binding constraints, and
limitations.

The zero-action plan is serialized separately for all runs. Complete feasible enumeration can emit
`optimal` only with zero gap. Complete enumeration without a feasible plan emits `infeasible`.
Evaluation-capped searches emit `search-limited`, preserve diagnostics and any retained incumbent,
but deliberately issue no selected plan or optimality claim. Each optimal run records its exact
objective change from the zero-action baseline.

The 100-task qualification suite is balanced across 50 expected-value and 50 worst-case problems.
It declares 24,000 candidate portfolios and actually evaluates 21,710; the difference is the ten
intentional five-evaluation caps. Across run-level solver counts, 4,333 feasible portfolios are
encountered. Outcomes are 70 optimal, 20 proven infeasible, and ten search-limited; the 70 optimal
runs carry explicit selected-versus-baseline comparisons. All actions and benefits are synthetic.

## Machine-verifiable aggregates

The typed evidence summary independently recomputes:

- row-to-full-artifact hash equality for all 145 runs;
- the hash of the complete artifact-ID-to-file-hash map;
- forecast method and parameter counts;
- optimization status and objective-strategy counts;
- total declared search space, evaluated plans, and feasible plans; and
- the number of complete selected-versus-baseline comparisons.

The registry independently recomputes artifact category and status counts, rejects unknown kinds,
unsafe paths, duplicate IDs or paths, and artifact-set drift. The verifier then checks actual file
bytes against the registry and checksum file before rebuilding the entire tree.

## Quality evidence

The historical milestone-4 suite contained 366 tests with 95.62% combined line-and-branch coverage
at its full
run. The engine-focused suites include 21 forecast, 17 causal, 30 simulation, 23 uncertainty, 22
portfolio, and eight benchmark tests. Strict mypy and Ruff pass. The independently generated
verification report is
[`../verification/milestone-4-analytical-engines.json`](../verification/milestone-4-analytical-engines.json),
and detailed coverage evidence is
[`../verification/milestone-4-coverage.json`](../verification/milestone-4-coverage.json). The
current milestone-5 suite and coverage are recorded separately in
[`../verification/milestone-5-coverage.json`](../verification/milestone-5-coverage.json).

These local results do not substitute for a remote CI run, mutation testing, security scanning,
external methodological review, or domain validation. Those remain separate release gates.

## Remaining limits

- The NASA POWER records are gridded point series, not official municipal exposure surfaces.
- Replays evaluate historical predictability, not future live-service reliability.
- The causal qualifications are synthetic, not field studies.
- The simulation model is synthetic and structurally simple.
- Optimization tasks are synthetic finite enumerations, not implementable city portfolios.
- No engine result establishes municipal adoption, institutional integration, users, or impact.
- Deep-city data, network routing, seven application suites, API/web product surfaces, large-scale
  performance work, and public release assurance remain later milestones.
