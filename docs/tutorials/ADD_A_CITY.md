# Add and validate a city

A City Adapter declares identity, geographic coverage, source references, capabilities, gaps, and
limitations. Passing the schema establishes contract validity; it does not promote a city to deep
analytical readiness.

## 1. Start from the protocol example

Copy `examples/cities/boston-cambridge.yaml` to a new file and change every field that describes
the city or its evidence. Do not retain a source ID merely because another city uses it.

Required review questions:

- Does `city_id` use a stable, unambiguous identifier?
- Does `bbox` describe the intended scope without implying unsupported administrative coverage?
- Does every `source_id` point to a real, versioned source manifest?
- Are capabilities limited to what those sources can support?
- Are missing operational, network, outcome, and subgroup data listed under `data_gaps`?
- Do limitations prevent area estimates, reports, or modeled points from becoming individual facts?

## 2. Validate the adapter

```bash
civicdecision protocol validate city-adapter \
  examples/cities/boston-cambridge.yaml
```

Expected output:

```text
valid city-adapter: examples/cities/boston-cambridge.yaml
```

## 3. Assign the evidence depth honestly

| Tier | Meaning | It does not mean |
|---|---|---|
| G | A reproducible global discovery record | Official boundary or analytical readiness |
| S | A standardized descriptive public-data bundle | Local intervention evidence |
| D | An audited municipal source bundle with gated reference executions | Deployment, adoption, or policy validity |

Do not set `tier: D` simply because a city has an open-data portal. A deep adapter needs bounded,
reconcilable municipal artifacts, context sources, quality checks, and explicit scenario gates.

## 4. Verify source artifacts before building

Every downloaded artifact should have a manifest containing retrieval time, source URL, query,
content hash, schema fingerprint, record semantics, licensing summary, and limitations.

```bash
civicdecision sources verify path/to/source.manifest.json
```

For the existing eight reference cities, source acquisition and rebuild commands are documented
in [Deep city coverage](../DEEP_CITY_COVERAGE.md). Treat those configurations as auditable
examples, not as evidence that a new city is comparable.

## 5. Add review evidence

In a pull request, include:

1. the adapter and every new source manifest;
2. the exact validation command and output;
3. the evidence-tier rationale;
4. source semantics and anti-inflation reconciliation;
5. known exclusions, gaps, and prohibited claims;
6. any generated-artifact changes separated from authored code and configuration.
