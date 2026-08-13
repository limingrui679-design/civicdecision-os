# Performance budgets

[`verification/milestone-8-performance.json`](../verification/milestone-8-performance.json) records
the first versioned performance contract for the enlarged product. The benchmark uses CPython
3.12 on the recorded macOS arm64 machine, verifies source hashes, initializes the real 338-file
product projection, exercises the in-process ASGI app, and includes exact scenario-library and
product rebuilds.

| Operation | Budget (p95 or one build) | Observed | Result |
|---|---:|---:|---|
| Cold artifact-store initialization | 5,000 ms | 1,631.905 ms | pass |
| Compound store design query | 25 ms | 0.118 ms | pass |
| Store design detail | 25 ms | 0.105 ms | pass |
| API metadata | 100 ms | 1.832 ms | pass |
| API compound design query | 150 ms | 2.249 ms | pass |
| API design detail | 150 ms | 2.272 ms | pass |
| API family detail | 150 ms | 2.342 ms | pass |
| Exact 282-file library rebuild | 30,000 ms | 1,114.127 ms | pass |
| Exact 338-file product rebuild | 30,000 ms | 4,237.765 ms | pass |

Warm operations use 30 samples; cold initialization uses three; each deterministic build is run
once within the performance measurement. The JSON retains min, median, max, p95, sample count,
response size, status, ETag, catalog fingerprint, software version, and environment.

These are regression budgets, not service-level objectives. They exclude network, TLS, proxy,
container startup, concurrent users, data refresh, and production resource contention. Compare
future runs only on equivalent hardware and Python versions, or establish a new named baseline.

Run a fresh local measurement with:

```bash
python scripts/benchmark_product.py --output verification/milestone-8-performance.json
```
