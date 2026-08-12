# ADR 0002: Release valid negative analytical outcomes

- Status: accepted
- Date: 2026-08-12

## Context

Publishing only successful models and feasible recommendations creates selection bias and makes
systems appear more reliable than their actual run history.

## Decision

`failed`, `insufficient_evidence`, `infeasible`, and `timed_out` are valid DecisionPack statuses.
Negative packs cannot select an option. They must state a failure reason, required next evidence,
limitations, environment, parameters, command, seed, and source hashes.

## Consequences

Benchmarks and product views must display negative runs rather than filtering them out. Aggregate
success rates must use the full run denominator. A committed infeasible reference pack exercises
the policy in the first milestone.
