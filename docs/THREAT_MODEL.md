# Threat model

## Protected assets

- Integrity of source artifacts, manifests, scenarios, DecisionPacks, and release assets.
- Confidentiality of credentials and any future restricted configuration.
- Availability of public connectors and hosted product surfaces.
- Accuracy of evidence labels and decision limitations.
- Reproducibility of published results.

## Trust boundaries

External APIs, downloaded bytes, user-authored YAML/JSON, adapter plugins, model files, solver
outputs, browser inputs, object storage, CI dependencies, and hosted requests are untrusted until
validated. A content hash proves byte identity, not truth, safety, license, or policy relevance.

## Primary threats and current controls

| Threat | Current controls | Remaining work |
|---|---|---|
| Malicious or malformed API response | HTTP status checks, timeout, JSON shape, limit, atomic write | Size streaming, MIME allowlist, retry policy, egress proxy |
| Path traversal | Manifest artifact containment check | Apply equivalent checks to all future bundle paths |
| Silent upstream revision | Retrieval/upstream times, content hash, raw bytes | Scheduled drift monitor and signed snapshots |
| Schema drift | Field fingerprint, strict protocol models | Dataset-specific semantic drift policies |
| Evidence inflation | Six evidence types and validator gates | Repository-wide claim linter and UI enforcement |
| Unsafe plugin/adapter | No dynamic plugin execution yet | Signed packages, permissions, sandbox, capability manifest |
| Dependency or supply-chain compromise | Pinned ranges, planned CodeQL workflow | Lockfiles, SBOM, provenance, dependency review, signed releases |
| Secret leakage | Public-data-only design and `.gitignore` | Secret scanning and pre-commit protection |
| Denial of service | Bounded API limits | API quotas, job isolation, memory/time limits, cancellation |
| Privacy harm | Aggregate public fixtures and explicit prohibition | DPIA templates, aggregation thresholds, disclosure tests |
| Recommendation misuse | Claim boundary, limitations, reversal and VOI fields | UI friction, role controls, audit log, review workflow |

## Abuse cases

The project must not be used to infer sensitive traits about individuals, target vulnerable groups,
automate punitive eligibility decisions, conceal uncertainty, or present simulations as observed
impact. Future high-stakes deployments require human review, legal authority, appeal paths,
monitoring, security hardening, and local domain validation beyond this repository.
