# Claim and public-state audit

## Purpose

The claim audit makes the project's evidence boundary executable. It checks whether governed
README, status, requirement, security, architecture, release, and governance statements still
match committed machine-readable evidence. It also requires published repository and package
coordinates to match the dated public snapshot while preventing a repository URL from silently
becoming a hosted-domain, deployment, user, adoption, or impact claim.

The audit is deliberately separate from the analytical verifier. Exact reconstruction answers
whether committed artifacts can be reproduced; this audit answers whether human-facing language
describes those artifacts without upgrading their meaning.

## Four layers

1. **Surface scan.** The policy enumerates every governed Markdown/document surface plus package
   metadata, API problem identifiers, and release-builder claim boundaries. Forbidden literals
   catch unregistered hosted-domain identifiers, obsolete release
   counts, and stale assurance wording.
2. **Quantitative reconciliation.** Named facts resolve through JSON Pointers into the repository,
   product, coverage, performance, and quality reports. Derived facts use explicit operations such
   as sum, subtraction, list length, or `n × (n - 1) / 2`. Required renderings bind those values to
   the authoritative human-facing files.
3. **Boundary presence.** Required phrases keep local reproducibility distinct from public release,
   production deployment, external validation, real users, municipal adoption, and observed
   impact.
4. **Public-state check.** A dated snapshot records the exact GitHub repository API endpoint,
   returned status, declared local Git remote, matching package project URLs, and registered
   hosted-demo URL. A live run refreshes the GitHub status; an offline release run validates the
   committed snapshot for deterministic packaging. URL availability does not establish domain
   correctness, production use, external review, adoption, or impact.

## Run it

Refresh the external repository-state assertion and write the committed audit report:

```bash
python scripts/audit_claims.py \
  --root . \
  --refresh-public-state \
  --report verification/milestone-8-claim-audit.json
```

Run the deterministic offline form used by the release builder:

```bash
python scripts/audit_claims.py --root .
```

Both modes fail closed on a missing evidence pointer, unsafe path, malformed policy, value drift,
missing required phrase, forbidden literal, package URL drift, or changed local Git remote. Live
mode additionally fails when the official repository endpoint no longer matches the dated
snapshot. Repository publication updates the package URLs, public-state snapshot, policy, docs,
and release boundary together rather than weakening the check.

## Evidence map

The policy reconciles more than headline scale. It covers core schemas, connectors, manifests,
declared source units, Tier-G/S/D city counts, benchmark runs, deep executions and negative
releases, scenario designs/families/reference mappings/pairwise comparisons, library and product
inventories, product routes and shared surfaces, tests, three coverage measures, performance,
version, and locked runtime dependencies. The current policy resolves 9 local performance budgets
from the versioned performance report rather than trusting this sentence on its own.

Every evidence file and every governed surface used by an audit is individually hashed into the
report, along with the policy hash, scan size, exact check accounting, resolved quantitative
values, public-state result, live audit timestamp, and failures. The release candidate requires
the live and extracted-sdist offline hashes, scope, policy, and resolved values to agree, then
carries both reports beside the wheel, source archives, SBOM, security reports, performance
evidence, and checksums.

## Boundary

A passing audit proves that the selected governed text is internally consistent with the named
committed evidence and dated public-state assertion. It does not prove domain correctness,
novelty, causal validity, accessibility, security certification, public availability, deployment,
external review, users, adoption, or real-world impact. A snapshot can become stale; refresh it
before any publication claim.
