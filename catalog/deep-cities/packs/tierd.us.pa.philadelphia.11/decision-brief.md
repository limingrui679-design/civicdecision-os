# Philadelphia — Causal service-effectiveness gate

- Scenario: `tierd.us.pa.philadelphia.11`
- Application suite: `behavioral-policy-equity`
- Status: `insufficient_evidence`
- DecisionPack content hash: `sha256:bb659760f82732f45d87e6cd093aef443d3323730abaa272007209e067633964`

## Claim boundary

An explicit insufficient-evidence release unless a dated intervention, comparison group, outcome panel, and identification diagnostics exist.

This artifact is a reproducible public-data planning exercise. It is not a deployed service, municipal recommendation, causal effect, observed intervention outcome, or evidence of adoption or real-world impact.

## Result

The compiler withholds an option because the scenario's explicit evidence gate is not satisfied.

Failure reason: The committed aggregate sources contain no dated intervention, comparison group, repeated outcome panel, or identification diagnostics.

## Evidence ledger

- **observed / limited:** The bounded focus contains 276,443 published requests.
- **causal / insufficient_evidence:** The committed aggregate sources contain no dated intervention, comparison group, repeated outcome panel, or identification diagnostics.

## Reversal diagnostics

- No option exists, so reversal testing is not applicable.

## Required next evidence

- Bind intervention timing, a defensible comparison group, repeated outcome panel, and pre-registered identification diagnostics.

## Reproduce

```bash
civicdecision deep build --source-directory examples/data/tier-d --output-directory catalog/deep-cities
```
