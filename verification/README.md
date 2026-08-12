# Verification evidence

The current standardized-city milestone report is produced by:

```bash
python scripts/verify_repository.py --report verification/milestone-3-standardized-cities.json
```

The verifier checks the committed connector catalog against the loadable code registry, uses a
temporary directory, regenerates all nine public JSON Schemas, validates every committed
protocol document, verifies each source artifact against its manifest, checks
portable SHA256SUMS files, rebuilds the completed and infeasible reference workflows, and requires
byte-for-byte equality with the committed JSON and Markdown outputs. It also validates the
250-city catalog, semantic bundle, seed graph, and coverage matrix; rebuilds all four global-city
artifacts from the committed GeoNames source; and requires exact bytes and checksums.

For Tier S, it verifies all 41 source artifacts, embedded source-manifest equality, safe recursive
paths, 30 bundle hashes, 90 independent run hashes, 30 coverage rows, 30 comparison rows, zero
issued recommendations, and the recursive checksum inventory. It then recompiles the registry,
bundles, runs, coverage matrix, cross-city reports, and checksums in a fresh temporary directory
and requires the entire file tree to match byte-for-byte.

The report establishes repository integrity for this bounded milestone. It does not establish
policy correctness, causal validity, production deployment, external review, real users, or
real-world impact.

`milestone-0.json`, `milestone-1-connectors.json`, and `milestone-2-global-cities.json` are retained
as historical snapshots. They are not the current status.
