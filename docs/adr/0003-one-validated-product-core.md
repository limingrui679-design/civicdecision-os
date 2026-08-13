# ADR 0003: One validated core for every product surface

- Status: accepted
- Date: 2026-08-13

## Context

The repository now contains several evidence depths, negative releases, native artifact schemas,
and large but noninterchangeable workload counts. Independent API, UI, SDK, and CLI data logic
would create drift and make it easy for one surface to omit a limitation or upgrade a claim.

## Decision

All first-party read surfaces use `ArtifactStore` and the stable product projection models. The
store validates registry and file references, reconciles counts, resolves highest-tier city
records, preserves native payloads, and exposes a catalog fingerprint. REST, local SDK, HTTP SDK,
CLI, and Web consume these projections rather than reproducing artifact interpretation.

Plugins use a separate data-only, exact-allowlist validator and are never auto-merged into the
store.

## Consequences

- A catalog integrity failure prevents the product API from starting.
- Initial construction performs more validation work than a loosely coupled dashboard.
- A single catalog-wide ETag invalidates more responses than resource-specific ETags would.
- Negative releases and limitations remain consistent across surfaces.
- Product artifact generation can be rebuilt and compared exactly.
- Future remote/object-store operation will need a versioned snapshot backend that preserves the
  same validation semantics rather than bypassing this core.
