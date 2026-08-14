# Los Angeles — Infrastructure-maintenance request portfolio

- Scenario: `tierd.us.ca.los-angeles.08`
- Application suite: `infrastructure-finance-asset-risk`
- Status: `insufficient_evidence`
- DecisionPack content hash: `sha256:0dcee2ae53f76041f2bcd18f400400944a37c86910203926a2e3600b99731315`

## Claim boundary

A request-based maintenance planning proxy, not an asset-condition survey, capital budget, engineering design, or financial return.

This artifact is a reproducible public-data planning exercise. It is not a deployed service, municipal recommendation, causal effect, observed intervention outcome, or evidence of adoption or real-world impact.

## Result

The compiler withholds an option because the scenario's explicit evidence gate is not satisfied.

Failure reason: The declared keyword rule matches 60 requests, below the minimum gate of 100.

## Evidence ledger

- **observed / limited:** The bounded focus contains 60 published requests.
- **proposed / insufficient_evidence:** The declared keyword rule matches 60 requests, below the minimum gate of 100.

## Reversal diagnostics

- No option exists, so reversal testing is not applicable.

## Required next evidence

- Bind a versioned routable network or collect enough matching local source records, then rerun the declared evidence gate.

## Reproduce

```bash
civicdecision deep build --source-directory examples/data/tier-d --output-directory catalog/deep-cities
```
