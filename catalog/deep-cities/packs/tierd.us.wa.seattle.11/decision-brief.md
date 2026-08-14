# Seattle — Causal service-effectiveness gate

- Scenario: `tierd.us.wa.seattle.11`
- Application suite: `behavioral-policy-equity`
- Status: `insufficient_evidence`
- DecisionPack content hash: `sha256:71aeae07dc06e302b5f29b11ffd8f080b7b7f10f18467c456cb397dd015c39b1`

## Claim boundary

An explicit insufficient-evidence release unless a dated intervention, comparison group, outcome panel, and identification diagnostics exist.

This artifact is a reproducible public-data planning exercise. It is not a deployed service, municipal recommendation, causal effect, observed intervention outcome, or evidence of adoption or real-world impact.

## Result

The compiler withholds an option because the scenario's explicit evidence gate is not satisfied.

Failure reason: The committed aggregate sources contain no dated intervention, comparison group, repeated outcome panel, or identification diagnostics.

## Evidence ledger

- **observed / limited:** The bounded focus contains 186,351 published requests.
- **causal / insufficient_evidence:** The committed aggregate sources contain no dated intervention, comparison group, repeated outcome panel, or identification diagnostics.

## Reversal diagnostics

- No option exists, so reversal testing is not applicable.

## Required next evidence

- Bind intervention timing, a defensible comparison group, repeated outcome panel, and pre-registered identification diagnostics.

## Reproduce

```bash
civicdecision deep build --source-directory examples/data/tier-d --output-directory catalog/deep-cities
```
