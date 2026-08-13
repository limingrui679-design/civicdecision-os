# Product surfaces and shared validation core

## Scope

CivicDecision exposes the same committed artifact snapshot through five product surfaces:

1. a responsive evidence explorer;
2. a versioned, read-only REST API;
3. local, synchronous HTTP, and asynchronous HTTP Python clients;
4. catalog, source, build, validation, and serving commands;
5. a data-only city-adapter plugin SDK.

These surfaces do not maintain independent copies of the project facts. They all project from
`ArtifactStore`, which loads the Tier-G, Tier-S, Tier-D, reference-workflow, source-manifest, and
benchmark registries and validates their internal references before returning a product model.
The product layer therefore cannot turn a screen into a recommendation, omit a negative release,
or upgrade a proposed value into an observed result without first violating a typed model or an
underlying artifact hash.

## Verified product snapshot

The committed `catalog/product/` tree contains 35 files:

- 33 manifest-indexed JSON artifacts;
- one manifest describing all 33 artifacts; and
- one portable checksum file covering the other 34 files.

The projection contains four city indexes, five scenario indexes, the complete source index,
seven-suite index, analytical benchmark overview, Tier-D evidence summary, deterministic OpenAPI
document, web-asset manifest, catalog summary, and 17 product/plugin JSON Schemas. The builder
reconstructs the complete tree in a temporary directory; the repository verifier requires exact
path and byte equality with the committed tree.

The snapshot exposes the following current facts without changing their meaning:

| Dimension | Verified projection |
|---|---:|
| Distinct highest-tier city records | 258 |
| Tier assignments | 288 |
| Source artifacts | 90 |
| Declared heterogeneous source units | 258,478 |
| Standard descriptive/evidence-gate screens | 90 |
| Deep city-bound scenario executions | 96 |
| Reference workflow executions | 2 |
| Total scenario executions | 188 |
| DecisionPacks | 98 |
| Completed DecisionPacks | 77 |
| Negative DecisionPacks | 21 |
| Analytical benchmark run artifacts | 145 |

The 188 executions are not described as 188 non-duplicative methods. The 96 deep executions are
eight bindings of twelve shared designs, the 90 standard screens are three bindings for each of
30 cities, and the two reference packs demonstrate one bounded workflow under completed and
infeasible configurations.

## Shared data flow

```text
committed source artifacts + manifests
                 |
                 v
Tier G / Tier S / Tier D / benchmark registries
                 |
                 v
      fail-closed ArtifactStore
                 |
       typed product projections
      /       |       |       \
     /        |       |        \
 REST API  Python SDK  CLI  evidence explorer
                              |
                    same-origin GET requests

data-only plugin package -> separate exact-allowlist validator
```

The plugin validator deliberately remains outside the runtime catalog. A validated plugin is not
automatically installed, loaded, enabled, or merged into a recommendation surface.

## Product artifact build

Build or refresh the deterministic projection:

```bash
civicdecision catalog build-product --root . --output catalog/product
```

`python scripts/build_product_artifacts.py` is the equivalent repository-maintainer entry point.

Export only the runtime OpenAPI document:

```bash
civicdecision api export-openapi \
  --root . \
  --output schemas/openapi-v1.json
```

The product builder stages every file in a temporary directory, computes its byte count and
SHA-256 digest, builds the manifest, builds portable checksums, rejects unexpected files in the
destination, and then writes the staged bytes. It does not place local absolute paths in the
manifest or checksum file.

## Product claim contract

Every surface must preserve these boundaries:

- a catalog city is not proof of official boundary coverage;
- Tier S is descriptive screening and cannot issue a recommendation;
- a completed Tier-D run means an internal planning-support pipeline completed under declared
  assumptions, not that an intervention worked;
- an insufficient-evidence or infeasible release remains visible and selectable;
- simulations and optimizations are modeled computations, not observed outcomes;
- public-data reproducibility is not external review, production deployment, adoption, users, or
  real-world impact;
- benchmark scale is not municipal outcome evidence; and
- a plugin package hash proves byte identity, not source truth or local readiness.

## Verification boundary

Local product tests establish implementation behavior, response/model consistency, negative-path
handling, deterministic generation, browser rendering, and checksum integrity. They do not
establish public-host availability, third-party security certification, external method review,
institutional use, or policy correctness. Those remain separate release and external-evidence
gates.
