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
| Evidence inflation | Six evidence types, validator gates, deduplicated Tier-D source/scenario ledgers, and anti-inflation audit | Repository-wide claim linter and UI enforcement |
| Repeated-view count inflation | Four municipal aggregates must reconcile; underlying request totals are counted once | Generalize provenance-aware deduplication to future bulk sources |
| Unsupported local recommendation | Completed packs require reversals and VOI; causal/network/sample gates emit negative packs | Authenticated review workflow, local owner sign-off, and deployment controls |
| Product projection drift | One validated `ArtifactStore`, closed enums, client-side SDK validation, deterministic 338-file projection, manifest, hashes, and exact rebuild | Compatibility policy and signed release snapshots |
| Cache masks an invalid route | Conditional `304` is applied only after a route resolves with `200`; unknown routes retain typed `404` | Reverse-proxy cache configuration tests in the deployment environment |
| Browser injection or framing | Escaped dynamic HTML, same-origin assets, strict CSP, frame denial, no-referrer and permissions policies, content-type sniffing protection | Independent CSP review, browser matrix, accessibility audit, and penetration test |
| Unsafe plugin/adapter | Data-only exact allowlist; exact inventory; normalized contained paths; no symlinks, Python, unmanifested files, oversized documents, duplicate identities, or code execution; hash and City Adapter validation | Signed packages, provenance, revocation, permissions, sandbox, and audit log before any executable plugin protocol |
| Dependency or supply-chain compromise | Pinned ranges, planned CodeQL workflow | Lockfiles, SBOM, provenance, dependency review, signed releases |
| Secret leakage | Public-data-only design and `.gitignore` | Secret scanning and pre-commit protection |
| Denial of service | Read-only routes, construction-time catalog validation, API limit of 100 records, bounded offsets, connector limits, no browser-side bulk export, explicit non-loopback serve acknowledgement | Reverse-proxy quotas, request/body limits, job isolation, memory/time limits, cancellation, load tests, and production monitoring |
| Privacy harm | Aggregate public fixtures and explicit prohibition | DPIA templates, aggregation thresholds, disclosure tests |
| Recommendation misuse | Claim boundary, limitations, reversal and VOI fields | UI friction, role controls, audit log, review workflow |

## Abuse cases

The project must not be used to infer sensitive traits about individuals, target vulnerable groups,
automate punitive eligibility decisions, conceal uncertainty, or present simulations as observed
impact. Future high-stakes deployments require human review, legal authority, appeal paths,
monitoring, security hardening, and local domain validation beyond this repository.
