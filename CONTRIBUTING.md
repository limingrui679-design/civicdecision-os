# Contributing

CivicDecision OS welcomes source connectors, city adapters, analytical engines, scenarios,
tests, documentation, and reproducible negative results. A contribution is accepted on the
strength of inspectable artifacts—not the size of a claim.

## Non-negotiable evidence rules

- Keep `observed`, `estimated`, `causal`, `simulated`, `optimized`, and `proposed` distinct.
- Public-data demonstrations are not client deployments or municipal adoption.
- Historical replay is not a prospective real-world effect.
- Causal evidence requires an estimand, identification strategy, diagnostics, and limitations.
- Preserve failed, infeasible, timed-out, and insufficient-evidence runs when they are valid.
- Never commit credentials, private personal data, restricted client data, or unlicensed data.
- Every downloaded artifact needs a query, retrieval time, source URL, license, hash, count,
  geographic scope, temporal scope, and limitations.

## Local quality gate

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
make check
```

The branch-coverage floor is 90%. New analytical or connector code must add positive,
negative, integrity, and boundary tests. Do not reduce the floor to make a change pass.

## Add a public source

1. Confirm official access, terms, attribution, geographic scope, and update behavior.
2. Add a bounded query model and safe connector under `src/civicdecision/connectors/`.
3. Write raw bytes atomically and emit a `SourceManifest` beside the artifact.
4. Test HTTP failure, invalid JSON, unsafe shape, limit overflow, hash verification, and cleanup.
5. Commit only a small lawful sample unless the repository's data policy explicitly permits more.

## Add a scenario or analytical engine

1. Validate the scenario DSL before executing analytical code.
2. Declare every assumption and hard constraint.
3. Retain infeasible and insufficient-evidence outcomes.
4. Include reversal tests and value-of-information guidance for completed DecisionPacks.
5. Generate human-readable output from the same validated DecisionPack, never a separate source.

## Pull-request evidence

State exactly what changed, which claims are supported, the commands run, the test result,
the artifact hashes, and what remains unverified. Screenshots and README statements do not
replace code, manifests, logs, or reproducible outputs.
