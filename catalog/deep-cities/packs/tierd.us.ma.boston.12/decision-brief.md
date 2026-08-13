# Boston — Real-time multimodal rerouting gate

- Scenario: `tierd.us.ma.boston.12`
- Application suite: `mobility-accessibility-operations`
- Status: `insufficient_evidence`
- DecisionPack content hash: `sha256:80a04e754e44354c31f6363c8c3ae014e30a84c52ece3dc12afa3cf3c8b7ec75`

## Claim boundary

An explicit insufficient-evidence release until versioned routable networks, service calendars, disruptions, and impedance validation are bound.

This artifact is a reproducible public-data planning exercise. It is not a deployed service, municipal recommendation, causal effect, observed intervention outcome, or evidence of adoption or real-world impact.

## Result

The compiler withholds an option because the scenario's explicit evidence gate is not satisfied.

Failure reason: The committed evidence contains no versioned routable network, service calendar, impedance validation, or real-time disruption state.

## Evidence ledger

- **observed / limited:** The bounded focus contains 148,160 published requests.
- **proposed / insufficient_evidence:** The committed evidence contains no versioned routable network, service calendar, impedance validation, or real-time disruption state.

## Reversal diagnostics

- No option exists, so reversal testing is not applicable.

## Required next evidence

- Bind a versioned routable network or collect enough matching local source records, then rerun the declared evidence gate.

## Reproduce

```bash
civicdecision deep build --source-directory examples/data/tier-d --output-directory catalog/deep-cities
```
