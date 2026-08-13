# Security and supply-chain assurance

## Assurance model

CivicDecision OS uses defense in depth for a local, read-only evidence product. No single scanner
is treated as proof of security. The release gate combines constrained input contracts, archive
validation, dependency locking, installed behavior, exact golden rebuilds, static analysis,
secret detection, advisory lookup, software inventory, and explicit deployment boundaries.

## Controls implemented in code

- External connectors use explicit schemas, bounded queries, record limits, timeouts, atomic writes,
  source timestamps, content hashes, and manifest reconciliation.
- Registered artifact paths are normalized and contained. Product routes resolve only fixed files
  or validated registry references; API parameters do not become filesystem paths.
- The API is read-only, emits problem details, rejects unknown enum values and mutations, defaults
  to loopback, and applies CSP, frame, sniffing, referrer, permissions, opener, and resource headers.
- Cache validators bind version, route, and normalized query. A valid ETag cannot suppress a
  different representation or an unresolved route.
- Plugins are data-only and exactly allowlisted. The loader rejects code, links, path escape,
  undeclared files, oversized files, digest drift, duplicate IDs, and registry overlap.
- Release archives reject unsafe paths, special files, unexpected roots, caches, bytecode, Git
  metadata, virtual environments, duplicate members, excessive expansion, and incomplete records.

## Automated release evidence

| Layer | Gate | Failure rule |
|---|---|---|
| Build | Two independent wheel and sdist builds | Any byte difference |
| Wheel | Member/path/metadata/asset/entry-point/`RECORD` validation | Any mismatch or omission |
| Source | Sdist and deterministic source ZIP validation | Any unsafe or missing member |
| Dependencies | Exact versions plus distribution hashes | Any unpinned or unhashed install input |
| Install | New environment, no-index wheel, no dependency resolution, `pip check` | Any install or consistency failure |
| Behavior | Installed CLI, SDK, API, Web, plugin, negative-route smoke | Any contract drift |
| Reconstruction | Full verifier in extracted no-Git source | Any non-identical golden artifact |
| Static analysis | Bandit medium severity and confidence | Any result |
| Secrets | Offline fresh Detect Secrets scan | Any unresolved result |
| Advisories | pip-audit of the exact lock | Any known finding at check time |
| Inventory | CycloneDX 1.6 SBOM and package-license inventory | Missing or invalid inventory |
| Integrity | Per-asset and bundle SHA-256 | Any mismatch |

## Limits

Static analysis does not replace code review. A dependency advisory database can be incomplete or
change after release. A secret scanner can miss a credential or flag a non-secret. An SBOM can
describe only the environment it observes. Local checks do not cover the operating system,
container base, proxy, identity provider, cloud policy, or production network.

Before a real deployment, add authenticated access, role and tenant policy, secure secret storage,
TLS termination, egress controls, rate limiting, immutable audit logs, monitoring, incident
response, backup/restore testing, data retention and privacy review, dependency provenance,
artifact signing, accessibility testing, and an independent penetration test.
