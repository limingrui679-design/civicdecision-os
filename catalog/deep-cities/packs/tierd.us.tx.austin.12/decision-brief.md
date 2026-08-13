# Austin — Real-time multimodal rerouting gate

- Scenario: `tierd.us.tx.austin.12`
- Application suite: `mobility-accessibility-operations`
- Status: `insufficient_evidence`
- DecisionPack content hash: `sha256:49aacdcd45b554d053620a7fcdd58edca1d57aa56fa74a2b7ee6a7bbd9841868`

## Claim boundary

An explicit insufficient-evidence release until versioned routable networks, service calendars, disruptions, and impedance validation are bound.

This artifact is a reproducible public-data planning exercise. It is not a deployed service, municipal recommendation, causal effect, observed intervention outcome, or evidence of adoption or real-world impact.

## Result

The compiler withholds an option because the scenario's explicit evidence gate is not satisfied.

Failure reason: The committed evidence contains no versioned routable network, service calendar, impedance validation, or real-time disruption state.

## Evidence ledger

- **observed / limited:** The bounded focus contains 164,333 published requests.
- **proposed / insufficient_evidence:** The committed evidence contains no versioned routable network, service calendar, impedance validation, or real-time disruption state.

## Reversal diagnostics

- No option exists, so reversal testing is not applicable.

## Required next evidence

- Bind a versioned routable network or collect enough matching local source records, then rerun the declared evidence gate.

## Reproduce

```bash
civicdecision deep build --source-directory examples/data/tier-d --output-directory catalog/deep-cities
```
