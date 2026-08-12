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

The current public samples contain public aggregate records. The repository does not claim
authorization for protected health information, personal data, confidential government data,
or client data.
