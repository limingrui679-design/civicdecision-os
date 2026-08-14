# Austin — Causal service-effectiveness gate

- Scenario: `tierd.us.tx.austin.11`
- Application suite: `behavioral-policy-equity`
- Status: `insufficient_evidence`
- DecisionPack content hash: `sha256:8d4fbe46ebc70078b9aca2247cd29ce7241e95b47e52dd8e6c3d0953a075f01c`

## Claim boundary

An explicit insufficient-evidence release unless a dated intervention, comparison group, outcome panel, and identification diagnostics exist.

This artifact is a reproducible public-data planning exercise. It is not a deployed service, municipal recommendation, causal effect, observed intervention outcome, or evidence of adoption or real-world impact.

## Result

The compiler withholds an option because the scenario's explicit evidence gate is not satisfied.

Failure reason: The committed aggregate sources contain no dated intervention, comparison group, repeated outcome panel, or identification diagnostics.

## Evidence ledger

- **observed / limited:** The bounded focus contains 164,333 published requests.
- **causal / insufficient_evidence:** The committed aggregate sources contain no dated intervention, comparison group, repeated outcome panel, or identification diagnostics.

## Reversal diagnostics

- No option exists, so reversal testing is not applicable.

## Required next evidence

- Bind intervention timing, a defensible comparison group, repeated outcome panel, and pre-registered identification diagnostics.

## Reproduce

```bash
civicdecision deep build --source-directory examples/data/tier-d --output-directory catalog/deep-cities
```
