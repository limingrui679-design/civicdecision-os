# Python SDK

The SDK provides three typed entry paths over one model set.

## Local repository client

Use the local client when the committed repository snapshot is available:

```python
from pathlib import Path

from civicdecision.product import ProductTier, ScenarioKind, ScenarioStatus
from civicdecision.sdk import CivicDecisionSDK

sdk = CivicDecisionSDK.open(Path("."), verify_sources=True)

summary = sdk.summary()
deep_cities = sdk.cities(tier=ProductTier.DEEP, limit=100)
negative = sdk.scenarios(
    kind=ScenarioKind.DEEP_PACK,
    status=ScenarioStatus.INSUFFICIENT_EVIDENCE,
    limit=100,
)
```

`CivicDecisionSDK.open` accepts either a `pathlib.Path` or a string path and normalizes both to a
resolved repository root before validation.

`verify_sources=True` checks committed source artifacts against their manifests before exposing
the snapshot. Turning it off is intended for narrowly scoped diagnostics, not final verification.

## Synchronous HTTP client

```python
from civicdecision.sdk import CivicDecisionClient

with CivicDecisionClient("http://127.0.0.1:8000") as client:
    city = client.city("us.tx.austin")
    pack = client.decision_pack("tierd.us.tx.austin.01")
    brief = client.decision_brief("tierd.us.tx.austin.01")
```

## Asynchronous HTTP client

```python
import asyncio

from civicdecision.sdk import AsyncCivicDecisionClient


async def inspect() -> None:
    async with AsyncCivicDecisionClient("http://127.0.0.1:8000") as client:
        sources = await client.sources(publisher="City of Austin", limit=100)
        suites = await client.suites()
        benchmark = await client.benchmarks()
        print(sources.pagination.total, len(suites), benchmark.run_artifacts)


asyncio.run(inspect())
```

## Available methods

All three clients expose summary, city collection/detail, scenario collection/detail,
DecisionPack, DecisionPack brief, source collection, suite overview, and benchmark overview
methods. HTTP clients validate each response against the same Pydantic models used by the local
store; malformed or drifted payloads fail during client-side validation.

Remote non-success responses raise `SDKHTTPError`, retaining the HTTP status, problem detail, and
request ID when present. The default user-agent includes the installed CivicDecision version and
may be overridden explicitly.

## Stability boundary

The versioned HTTP path and product models are the public product contract for this milestone.
The raw `payload` inside `ScenarioDetail` retains its native source schema and may grow only in a
way consistent with that underlying versioned protocol. Callers must not infer production status,
external validity, or observed impact from successful retrieval.
