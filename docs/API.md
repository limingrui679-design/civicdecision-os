# Read-only REST API

## Start locally

Install the API extra and start the validated local server:

```bash
python -m pip install -e '.[api]'
civicdecision serve --root . --host 127.0.0.1 --port 8000
```

The CLI refuses a non-loopback host unless `--allow-network` is provided explicitly. That flag is
only an exposure acknowledgement; it does not add authentication, TLS, quotas, a reverse proxy,
or production authorization.

## Contract

The API is read-only and versioned under `/api/v1`. It exposes OpenAPI at
`/api/openapi.json`; interactive documentation routes are deliberately disabled. The committed
deterministic copy is `catalog/product/openapi-v1.json`.

| Resource | Purpose |
|---|---|
| `GET /healthz` | Process health and current catalog fingerprint |
| `GET /readyz` | Readiness after catalog construction |
| `GET /api/v1/meta` | Reconciled catalog counts and claim boundary |
| `GET /api/v1/cities` | Highest-tier or tier-specific city index |
| `GET /api/v1/cities/{city_id}` | Typed city metrics, capabilities, gaps, and provenance |
| `GET /api/v1/scenarios` | Standard, deep, and reference execution index |
| `GET /api/v1/scenarios/{execution_id}` | Validated scenario payload and artifact hashes |
| `GET /api/v1/decision-packs` | Deep and reference DecisionPack index |
| `GET /api/v1/decision-packs/{execution_id}` | Native DecisionPack contract |
| `GET /api/v1/decision-packs/{execution_id}/brief` | Same-source Markdown brief |
| `GET /api/v1/sources` | Versioned source manifests |
| `GET /api/v1/suites` | Seven application-suite execution totals |
| `GET /api/v1/benchmarks` | Analytical benchmark projection |
| `GET /api/v1/evidence/deep` | Full Tier-D evidence ledger |

## Filters and pagination

Collection routes accept bounded pagination: `limit` is 1–100 and `offset` is nonnegative.
Supported filters include:

- cities: `tier`, `q`, and two-letter `country_code`;
- scenarios: `kind`, `city_id`, `suite`, `status`, and `q`;
- DecisionPacks: `city_id`, `status`, and `q`;
- sources: `source_id`, `publisher`, and `q`.

Scenario status is a closed enum: `completed`, `screened`, `insufficient-evidence`, and
`infeasible`. An invented status is a validation error rather than an empty result that could be
mistaken for absence of evidence.

Example:

```bash
curl -sS \
  'http://127.0.0.1:8000/api/v1/scenarios?kind=deep-pack&status=insufficient-evidence&limit=20'
```

## HTTP behavior

- Successful API GET responses include one catalog-wide strong ETag.
- `If-None-Match` returns `304` only after a real route resolves successfully; an unknown route
  cannot be converted into a cache hit.
- API responses use a short revalidation cache policy; health and HTML responses use `no-store`.
- Responses carry a generated request ID, or preserve a caller-provided ID only when it matches a
  constrained character and length policy.
- Request validation, unknown artifacts, unknown routes, disallowed methods, and catalog-integrity
  failures use `application/problem+json` with status, title, detail, instance, and request ID.
- Large JSON responses are eligible for gzip compression.

## Browser security headers

The application adds content-type sniffing protection, frame denial, no-referrer policy,
permissions restrictions, same-origin opener/resource policies, and a strict Content Security
Policy. The packaged UI uses no third-party runtime scripts, styles, fonts, or network services.

These are defense-in-depth controls for a public read-only explorer. They are not a substitute for
authentication, authorization, deployment isolation, dependency scanning, rate limiting, or an
independent penetration test.

## Failure examples

Asking for a Tier-S screen as if it were a DecisionPack returns a typed `404` explaining that the
promotion is deliberately forbidden. Asking for a negative Tier-D pack succeeds because negative
releases are valid artifacts; its recommendation remains absent.
