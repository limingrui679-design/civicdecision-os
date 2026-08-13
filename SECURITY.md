# Security policy

## Supported versions

Until the first stable release, only the latest commit on the default branch is supported.

## Reporting a vulnerability

Do not disclose an exploitable vulnerability in a public issue. Use GitHub private vulnerability
reporting when enabled. Include the affected version or commit, reproduction steps, impact,
and any suggested mitigation. Do not include real credentials, private records, or harmful data.

## Security boundaries

CivicDecision OS processes external data and configuration as untrusted input. Connectors use
bounded queries, timeouts, schema checks, record limits, atomic writes, content hashes, and
path-containment checks. These controls reduce risk but do not make arbitrary third-party data
safe. Production deployments must add network egress controls, authenticated storage, audit
logging, rate limiting, dependency scanning, secrets management, and jurisdiction-specific
privacy review.

The local REST service is read-only and defaults to loopback. A non-loopback bind requires an
explicit acknowledgement, but that flag does not provide TLS, authentication, authorization,
quotas, reverse-proxy isolation, or deployment approval. The browser explorer uses same-origin
packaged assets and a restrictive Content Security Policy; these controls are defense in depth,
not a penetration-test result.

Version-1 adapter plugins are data-only. Validation requires an exact plugin-ID allowlist, exact
file inventory, normalized contained paths, regular files, bounded sizes, content hashes, stable
City Adapter contracts, unique city IDs, and no default enablement. The runtime does not discover,
import, execute, or automatically merge plugin code. Any future executable plugin design requires
a separately reviewed signature, provenance, permission, sandbox, resource-limit, revocation, and
audit-log protocol.

The current public samples contain public aggregate records. The repository does not claim
authorization for protected health information, personal data, confidential government data,
or client data.
