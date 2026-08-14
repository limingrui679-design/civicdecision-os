# Build and review a scenario

A Policy Scenario defines a decision question, alternatives, objectives, hard constraints,
analysis modes, evidence requirements, assumptions, and limitations. Schema validity is only the
first gate; a scenario still needs source and method support before it can issue a recommendation.

## 1. Begin with an explicit decision owner and question

Use `examples/scenarios/boston-heat-transit.yaml` as a protocol example. It intentionally states
that it has not run a historical replay or optimization engine.

A reviewable question should identify:

- who owns the decision;
- which population, service, or network is affected;
- the time horizon and geographic unit;
- a no-action or current-service baseline;
- alternatives that are actually distinguishable;
- objectives with units and direction;
- hard budget, capacity, equity, legal, or safety constraints;
- the evidence required to release rather than withhold a result.

## 2. Validate the scenario contract

```bash
civicdecision protocol validate policy-scenario \
  examples/scenarios/boston-heat-transit.yaml
```

Expected output:

```text
valid policy-scenario: examples/scenarios/boston-heat-transit.yaml
```

This confirms the protocol shape, not that the proposed cooling centers, shuttle costs, network
closures, capacities, or effects have been observed.

## 3. Compare with the audited design library

Search the design catalog before adding another contract:

```bash
civicdecision catalog designs --root . --query heat --limit 20
civicdecision catalog scenario-library-evidence --root .
```

Record whether the scenario is:

- a city binding of an existing design;
- a genuinely distinct design contract;
- or an unsupported proposal that should remain uncompiled.

Do not count a city binding as a new method or independent design.

## 4. Review the release gate

Before compilation, answer each question with a source or explicit negative finding:

1. Are the input artifacts versioned and hash-verified?
2. Are observed, estimated, simulated, optimized, and proposed values typed separately?
3. Is there a meaningful baseline, including zero action where appropriate?
4. Are all hard constraints executable and auditable?
5. Are forecast, causal, simulation, optimization, and uncertainty methods qualified for this use?
6. Can a failed evidence gate produce a first-class negative release?
7. Do reversal tests expose which assumptions can change the bounded result?
8. Does value-of-information point to evidence that could change the decision?

## 5. Review the resulting DecisionPack

```bash
civicdecision protocol validate decision-pack path/to/decision-pack.json
```

Then inspect status, selected option, failed constraints, source manifests, artifact hashes,
limitations, reversals, and value-of-information. A completed status still does not authorize the
words *deployed*, *adopted*, *effective*, *causal*, or *impact* unless separate external evidence
supports each claim.
