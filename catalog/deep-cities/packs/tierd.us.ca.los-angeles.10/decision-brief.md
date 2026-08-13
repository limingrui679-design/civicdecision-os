# Los Angeles — Accessibility-related request planning

- Scenario: `tierd.us.ca.los-angeles.10`
- Application suite: `mobility-accessibility-operations`
- Status: `insufficient_evidence`
- DecisionPack content hash: `sha256:aa50f1dcd86f9e53714f6ab91529a218f823ac9be3ba4eee7f8d5f5a5daa7fe2`

## Claim boundary

A request-label workload plan only; it does not measure route accessibility, travel time, disability experience, or compliance.

This artifact is a reproducible public-data planning exercise. It is not a deployed service, municipal recommendation, causal effect, observed intervention outcome, or evidence of adoption or real-world impact.

## Result

The compiler withholds an option because the scenario's explicit evidence gate is not satisfied.

Failure reason: The declared keyword rule matches 0 requests, below the minimum gate of 100.

## Evidence ledger

- **observed / limited:** The bounded focus contains 0 published requests.
- **proposed / insufficient_evidence:** The declared keyword rule matches 0 requests, below the minimum gate of 100.

## Reversal diagnostics

- No option exists, so reversal testing is not applicable.

## Required next evidence

- Bind a versioned routable network or collect enough matching local source records, then rerun the declared evidence gate.

## Reproduce

```bash
civicdecision deep build --source-directory examples/data/tier-d --output-directory catalog/deep-cities
```
