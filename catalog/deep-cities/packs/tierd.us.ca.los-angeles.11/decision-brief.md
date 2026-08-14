# Los Angeles — Causal service-effectiveness gate

- Scenario: `tierd.us.ca.los-angeles.11`
- Application suite: `behavioral-policy-equity`
- Status: `insufficient_evidence`
- DecisionPack content hash: `sha256:9799ff26584cec20a5653480d3e947f056cf2ac1d832751d6ef3d7a24ba70c8e`

## Claim boundary

An explicit insufficient-evidence release unless a dated intervention, comparison group, outcome panel, and identification diagnostics exist.

This artifact is a reproducible public-data planning exercise. It is not a deployed service, municipal recommendation, causal effect, observed intervention outcome, or evidence of adoption or real-world impact.

## Result

The compiler withholds an option because the scenario's explicit evidence gate is not satisfied.

Failure reason: The committed aggregate sources contain no dated intervention, comparison group, repeated outcome panel, or identification diagnostics.

## Evidence ledger

- **observed / limited:** The bounded focus contains 53,194 published requests.
- **causal / insufficient_evidence:** The committed aggregate sources contain no dated intervention, comparison group, repeated outcome panel, or identification diagnostics.

## Reversal diagnostics

- No option exists, so reversal testing is not applicable.

## Required next evidence

- Bind intervention timing, a defensible comparison group, repeated outcome panel, and pre-registered identification diagnostics.

## Reproduce

```bash
civicdecision deep build --source-directory examples/data/tier-d --output-directory catalog/deep-cities
```
