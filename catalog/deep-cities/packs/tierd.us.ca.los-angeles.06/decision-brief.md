# Los Angeles — Housing-related request triage

- Scenario: `tierd.us.ca.los-angeles.06`
- Application suite: `housing-land-use-regeneration`
- Status: `insufficient_evidence`
- DecisionPack content hash: `sha256:aced3ffb70af1dca0b6f07f2812f2f845b62abbe755568e79cd0fbbe6c70cb24`

## Claim boundary

A request-taxonomy planning subset, not a measure of housing quality, violations, tenure outcomes, or regeneration impact.

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
