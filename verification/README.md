# Verification evidence

The current global-city milestone report is produced by:

```bash
python scripts/verify_repository.py --report verification/milestone-2-global-cities.json
```

The verifier checks the committed connector catalog against the loadable code registry, uses a
temporary directory, regenerates all six public JSON Schemas, validates every committed
protocol document, verifies each source artifact against its manifest, checks
portable SHA256SUMS files, rebuilds the completed and infeasible reference workflows, and requires
byte-for-byte equality with the committed JSON and Markdown outputs. It also validates the
250-city catalog, semantic bundle, seed graph, and coverage matrix; rebuilds all four global-city
artifacts from the committed GeoNames source; and requires exact bytes and checksums.

The report establishes repository integrity for this bounded milestone. It does not establish
policy correctness, causal validity, production deployment, external review, real users, or
real-world impact.

`milestone-0.json` and `milestone-1-connectors.json` are retained as historical snapshots of the
two-source protocol foundation and seven-connector expansion. They are not the current status.
